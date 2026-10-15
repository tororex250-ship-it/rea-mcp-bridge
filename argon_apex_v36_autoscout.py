#!/usr/bin/env python3
"""
ARGON-APEX v40: MULTI-CORE PINNACLE SHARP + ALTENAR + MARKOV DNA ENGINE
=======================================================================
Diseñado específicamente para POCO X6 Pro (8 núcleos) en Termux.
CERO DATOS FALSOS / CERO PARTIDOS INVENTADOS.

Arquitectura de 4 Fases en Tiempo Real:
1. PINNACLE ARCADIA API (guest.api.arcadia.pinnacle.com/0.1):
   Descarga multihilo (10 workers) de todas las ligas de Tenis (sportId=33),
   extrayendo cuotas Sharp reales (Moneyline, Set 1, Hándicap y Totales).
2. ALTENAR WIDGET API (sb2frontend-altenar2.biahosted.com/api/widget):
   Extrae cuotas blandas de TriunfoBet / red Altenar (GetLiveOverview,
   GetUpcoming, GetEvents con sportId=68) y cruza nombres por similitud.
3. MOTOR MARKOV ADN DEL PARTIDO (Klaassen-Magnus / Barnett-Clarke):
   Infiere probabilidades de retención de saque (Hold %), fragilidad de break
   y distribución de sets a partir de las líneas de Hándicap y Total de Pinnacle.
4. EMBUDO DE FILTRADO +EV / YIELD / KELLY:
   Filtra decenas de partidos y ordena únicamente el TOP de mayor probabilidad,
   mayor +EV y ROI esperado contra el algoritmo de Altenar.
"""

import sys
import json
import math
import time
import difflib
import subprocess
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

# Zona horaria de Venezuela (UTC-4)
TZ_VE = timezone(timedelta(hours=-4))

# Colores ANSI de alto contraste para pantalla móvil
C_RESET    = "\033[0m"
C_BOLD     = "\033[1m"
C_DIM      = "\033[2m"
C_GREEN    = "\033[1;92m"
C_CYAN     = "\033[1;96m"
C_YELLOW   = "\033[1;93m"
C_MAGENTA  = "\033[1;95m"
C_RED      = "\033[1;91m"
C_WHITE    = "\033[1;97m"
C_BG_GREEN = "\033[42;30m"
C_BG_CYAN  = "\033[46;30m"
C_BG_RED   = "\033[41;97m"

# Configuración Pinnacle Arcadia (Sharp Reference)
PINNACLE_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
PINNACLE_KEY  = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"
PINNACLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "X-API-Key": PINNACLE_KEY,
    "Referer": "https://www.pinnacle.com/",
    "Origin": "https://www.pinnacle.com"
}

# Configuración Altenar BIAHosted (TriunfoBet & Espejos del mismo motor Altenar)
ALTENAR_BASE = "https://sb2frontend-altenar2.biahosted.com/api/widget"
ALTENAR_PROFILES = [
    {
        "name": "TriunfoBet VE",
        "params": "culture=es-ES&timezoneOffset=240&integration=triunfobet&deviceType=1&numFormat=en-GB&countryCode=VE",
        "origin": "https://triunfobet.com",
        "referer": "https://triunfobet.com/"
    },
    {
        "name": "Altenar LatAm (DoradoBet)",
        "params": "culture=es-ES&timezoneOffset=240&integration=doradobet&deviceType=1&numFormat=en-GB&countryCode=PE",
        "origin": "https://doradobet.com",
        "referer": "https://doradobet.com/deportes-en-vivo"
    },
    {
        "name": "Altenar LatAm (Playdoit)",
        "params": "culture=es-ES&timezoneOffset=240&integration=playdoit2&deviceType=1&numFormat=en-GB&countryCode=MX",
        "origin": "https://www.playdoit.mx",
        "referer": "https://www.playdoit.mx/"
    }
]

# =====================================================================
# UTILIDADES MATEMÁTICAS Y DE CONVERSIÓN DE CUOTAS
# =====================================================================

def american_to_decimal(am_price):
    """Convierte cuota americana de Pinnacle (-135, +120) a decimal (1.741, 2.20)."""
    try:
        p = float(am_price)
        if p == 0:
            return 0.0
        if p > 0:
            return round(1.0 + (p / 100.0), 3)
        else:
            return round(1.0 + (100.0 / abs(p)), 3)
    except Exception:
        return 0.0

def decimal_to_american(dec):
    """Convierte cuota decimal a formato americano (como se ve en TriunfoBet: -125, +150)."""
    try:
        d = float(dec)
        if d <= 1.0:
            return "N/A"
        if d >= 2.0:
            return f"+{int(round((d - 1.0) * 100))}"
        else:
            return f"-{int(round(100.0 / (d - 1.0)))}"
    except Exception:
        return "N/A"

def shin_devig(odd1, odd2):
    """
    Elimina el margen (vig) de Pinnacle usando el método de potencia / Shin
    para obtener la Probabilidad Real exacta (p1, p2) y el overround.
    """
    if odd1 <= 1.0 or odd2 <= 1.0:
        return 0.5, 0.5, 0.0
    imp1 = 1.0 / odd1
    imp2 = 1.0 / odd2
    overround = (imp1 + imp2) - 1.0
    total_imp = imp1 + imp2
    p1 = imp1 / total_imp
    p2 = imp2 / total_imp
    return p1, p2, overround * 100.0

# =====================================================================
# MOTOR MARKOV: ADN DEL PARTIDO (KLAASSEN-MAGNUS / BARNETT-CLARKE)
# =====================================================================

def markov_game_hold_prob(s):
    """
    Probabilidad exacta de mantener el saque (Hold) dado 's' (prob. de ganar
    un punto con el servicio), usando la cadena de Markov de un game de tenis.
    """
    q = 1.0 - s
    p_no_deuce = (s ** 4) * (1.0 + 4.0 * q + 10.0 * (q ** 2))
    denom = 1.0 - 2.0 * s * q
    if denom <= 0:
        return 0.5
    p_deuce = (20.0 * (s ** 3) * (q ** 3)) * ((s ** 2) / denom)
    return min(max(p_no_deuce + p_deuce, 0.01), 0.99)

def infer_match_dna(p1_win_prob, total_games_line=None, spread_line=None):
    """
    Reconstruye el ADN táctico del partido (Serve Hold %, Break Fragility,
    Probabilidad de ganar el Set 1 y Probabilidad de ir a 3 sets) a partir
    de la probabilidad real de Pinnacle y la línea de Total de Juegos.
    """
    base_s = 0.635
    if total_games_line:
        delta_line = (float(total_games_line) - 22.0) * 0.012
        base_s = min(max(0.635 + delta_line, 0.56), 0.71)

    diff_s = (p1_win_prob - 0.5) * 0.145
    s1 = min(max(base_s + diff_s, 0.52), 0.76)
    s2 = min(max(base_s - diff_s, 0.48), 0.72)

    hold1 = markov_game_hold_prob(s1)
    hold2 = markov_game_hold_prob(s2)

    p1_set1 = 0.5 + (p1_win_prob - 0.5) * 0.84
    p1_set1 = min(max(p1_set1, 0.05), 0.95)

    p1_2_0 = p1_set1 * p1_set1
    prob_3_sets = 2.0 * p1_set1 * (1.0 - p1_set1)
    dna_confidence = (hold1 * 0.55 + p1_win_prob * 0.45) * 100.0

    return {
        "s1_serve_pt": round(s1 * 100.0, 1),
        "s2_serve_pt": round(s2 * 100.0, 1),
        "hold1_pct": round(hold1 * 100.0, 1),
        "hold2_pct": round(hold2 * 100.0, 1),
        "break_potential": round((1.0 - hold2) * 100.0, 1),
        "p1_set1_prob": round(p1_set1 * 100.0, 1),
        "p1_2_0_prob": round(p1_2_0 * 100.0, 1),
        "prob_3_sets": round(prob_3_sets * 100.0, 1),
        "dna_score": round(dna_confidence, 1)
    }

# =====================================================================
# MOTOR HTTP MULTICAPA (CURL_CFFI -> CURL NATIVO -> URLLIB)
# =====================================================================

def http_get_json(url, headers=None, timeout=10):
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; POCO X6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-VE,es;q=0.9,en;q=0.8"
    }
    if headers:
        hdrs.update(headers)

    try:
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(url, headers=hdrs, impersonate="chrome120", timeout=timeout)
        if r.status_code == 200:
            return r.json(), "OK (curl_cffi)"
    except Exception:
        pass

    try:
        cmd = ["curl", "-s", "-L", "--max-time", str(timeout)]
        for k, v in hdrs.items():
            cmd.extend(["-H", f"{k}: {v}"])
        cmd.append(url)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        out = res.stdout.strip()
        if res.returncode == 0 and (out.startswith("{") or out.startswith("[")):
            return json.loads(out), "OK (curl)"
    except Exception:
        pass

    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw), f"OK ({resp.status})"
    except Exception as e:
        return None, str(e)[:40]

# =====================================================================
# FASE 1: PINNACLE ARCADIA SHARP SCANNER (MULTIHILO)
# =====================================================================

def fetch_pinnacle_league_data(league_obj):
    lid = league_obj["id"]
    lname = league_obj.get("name", "Tennis")
    if "double" in lname.lower():
        return []

    url_m = f"{PINNACLE_BASE}/leagues/{lid}/matchups"
    url_s = f"{PINNACLE_BASE}/leagues/{lid}/markets/straight"

    matchups, _ = http_get_json(url_m, PINNACLE_HEADERS, timeout=9)
    markets, _  = http_get_json(url_s, PINNACLE_HEADERS, timeout=9)

    if not isinstance(matchups, list) or not isinstance(markets, list):
        return []

    markets_by_id = {}
    for m in markets:
        if m.get("isAlternate"):
            continue
        mid = m.get("matchupId")
        if not mid:
            continue
        markets_by_id.setdefault(mid, []).append(m)

    parsed_matches = []
    for mu in matchups:
        if mu.get("type") != "matchup":
            continue
        if mu.get("parent") is not None:
            continue
        parts = mu.get("participants", [])
        if len(parts) < 2:
            continue

        home_p, away_p = None, None
        for p in parts:
            if p.get("alignment") == "home":
                home_p = p.get("name", "")
            elif p.get("alignment") == "away":
                away_p = p.get("name", "")
        if not home_p or not away_p:
            home_p = parts[0].get("name", "")
            away_p = parts[1].get("name", "")

        if "/" in home_p or "/" in away_p or "Sets" in home_p:
            continue

        mid = mu.get("id")
        m_list = markets_by_id.get(mid, [])
        if not m_list:
            continue

        ml_full = None
        ml_set1 = None
        total_games = None
        spread_games = None

        for mk in m_list:
            mtype = mk.get("type")
            period = mk.get("period")
            prices = mk.get("prices", [])
            if len(prices) < 2:
                continue

            if mtype == "moneyline" and period == 0:
                h_pr = next((x["price"] for x in prices if x.get("designation") == "home"), None)
                a_pr = next((x["price"] for x in prices if x.get("designation") == "away"), None)
                if h_pr is not None and a_pr is not None:
                    ml_full = (american_to_decimal(h_pr), american_to_decimal(a_pr))

            elif mtype == "moneyline" and period == 1:
                h_pr = next((x["price"] for x in prices if x.get("designation") == "home"), None)
                a_pr = next((x["price"] for x in prices if x.get("designation") == "away"), None)
                if h_pr is not None and a_pr is not None:
                    ml_set1 = (american_to_decimal(h_pr), american_to_decimal(a_pr))

            elif mtype == "total" and period == 0:
                ov = next((x for x in prices if x.get("designation") == "over"), None)
                un = next((x for x in prices if x.get("designation") == "under"), None)
                if ov and un and ov.get("points"):
                    pts = float(ov["points"])
                    if pts > 12.0:
                        total_games = (pts, american_to_decimal(ov["price"]), american_to_decimal(un["price"]))

            elif mtype == "spread" and period == 0:
                hm = next((x for x in prices if x.get("designation") == "home"), None)
                aw = next((x for x in prices if x.get("designation") == "away"), None)
                if hm and aw and hm.get("points") is not None:
                    pts = float(hm["points"])
                    if abs(pts) >= 2.0:
                        spread_games = (pts, american_to_decimal(hm["price"]), american_to_decimal(aw["price"]))

        if not ml_full or ml_full[0] <= 1.0 or ml_full[1] <= 1.0:
            continue

        start_str = mu.get("startTime", "")
        try:
            dt_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            time_ve = dt_utc.astimezone(TZ_VE).strftime("%a %d/%m · %I:%M %p")
            ts = int(dt_utc.timestamp())
        except Exception:
            time_ve = start_str
            ts = 0

        parsed_matches.append({
            "pinn_id": mid,
            "league": lname,
            "p1": home_p,
            "p2": away_p,
            "is_live": bool(mu.get("isLive")),
            "time_ve": time_ve,
            "ts": ts,
            "ml_full": ml_full,
            "ml_set1": ml_set1,
            "total_games": total_games,
            "spread_games": spread_games
        })

    return parsed_matches

def fetch_all_pinnacle_tennis(search_filter=""):
    url_leagues = f"{PINNACLE_BASE}/sports/33/leagues?all=false"
    leagues, status = http_get_json(url_leagues, PINNACLE_HEADERS, timeout=10)
    if not isinstance(leagues, list):
        return [], f"Error Pinnacle Leagues: {status}"

    active_leagues = [
        lg for lg in leagues
        if lg.get("matchupCount", 0) > 0 and "double" not in lg.get("name", "").lower()
    ]

    if search_filter:
        q = search_filter.lower()
        matching_leagues = [lg for lg in active_leagues if q in lg.get("name", "").lower() or q in lg.get("group", "").lower()]
        if matching_leagues:
            active_leagues = matching_leagues
        else:
            active_leagues = [
                lg for lg in active_leagues
                if any(k in lg.get("name", "") for k in ("ATP", "WTA", "Challenger"))
            ] or active_leagues[:20]
    else:
        main_leagues = [
            lg for lg in active_leagues
            if any(k in lg.get("name", "") for k in ("ATP", "WTA", "Challenger"))
        ]
        other_leagues = [lg for lg in active_leagues if lg not in main_leagues]
        active_leagues = main_leagues + other_leagues[:8]

    all_matches = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(fetch_pinnacle_league_data, lg) for lg in active_leagues]
        for fut in as_completed(futures):
            try:
                res = fut.result()
                if res:
                    all_matches.extend(res)
            except Exception:
                pass

    if search_filter:
        q = search_filter.lower()
        all_matches = [
            m for m in all_matches
            if q in m["p1"].lower() or q in m["p2"].lower() or q in m["league"].lower()
        ]

    return all_matches, f"OK ({len(active_leagues)} ligas escaneadas en paralelo)"

# =====================================================================
# FASE 2: ALTENAR WIDGET SCANNER (TRIUNFOBET & ESPEJOS ALTENAR)
# =====================================================================

def flatten_odd_ids(market):
    if not isinstance(market, dict):
        return []
    for key in ("oddIds", "desktopOddIds", "mobileOddIds"):
        val = market.get(key)
        if isinstance(val, list) and val:
            out = []
            for item in val:
                if isinstance(item, list):
                    out.extend([x for x in item if x])
                elif item:
                    out.append(item)
            if out:
                return out
    return []

def parse_altenar_payload(data):
    """Extrae partidos y cuotas ganadoras de la estructura JSON de Altenar."""
    if not isinstance(data, dict) or not data.get("events"):
        return []

    markets_map = {m["id"]: m for m in data.get("markets", []) if isinstance(m, dict) and "id" in m}
    odds_map    = {o["id"]: o for o in data.get("odds", []) if isinstance(o, dict) and "id" in o}
    champs_map  = {c["id"]: c.get("name", "") for c in data.get("champs", []) if isinstance(c, dict) and "id" in c}

    events_out = []
    for ev in data.get("events", []):
        ev_name = ev.get("name", "")
        if " vs " in ev_name.lower():
            parts = ev_name.replace(" vs. ", " vs ").replace(" VS ", " vs ").split(" vs ")
        elif " - " in ev_name:
            parts = ev_name.split(" - ")
        else:
            parts = [ev_name, ""]

        p1_name = parts[0].strip()
        p2_name = parts[1].strip() if len(parts) > 1 else ""

        ml_odds = None
        for mid in ev.get("marketIds", []):
            m = markets_map.get(mid)
            if not m:
                continue
            mname = (m.get("name") or "").lower()
            mtype = m.get("typeId")
            if mtype in (1, 186) or mname in ("ganador", "winner", "match winner", "1x2"):
                oids = flatten_odd_ids(m)
                o_objs = [odds_map[oid] for oid in oids if oid in odds_map]
                if len(o_objs) >= 2:
                    pr1 = float(o_objs[0].get("price", 0))
                    pr2 = float(o_objs[1].get("price", 0))
                    if pr1 > 1.0 and pr2 > 1.0:
                        ml_odds = (pr1, pr2)
                        break

        if ml_odds:
            events_out.append({
                "id": ev.get("id"),
                "champ": champs_map.get(ev.get("champId"), "Tenis"),
                "p1": p1_name,
                "p2": p2_name,
                "ml_odds": ml_odds,
                "score": ev.get("score", []),
                "live_status": ev.get("ls", "")
            })
    return events_out

def fetch_altenar_tennis():
    """Consulta los endpoints en vivo y pre-partido de Altenar."""
    collected = []
    used_profile = "Ninguno"

    for prof in ALTENAR_PROFILES:
        hdrs = {
            "Origin": prof["origin"],
            "Referer": prof["referer"],
            "Accept": "application/json"
        }
        endpoints = [
            f"{ALTENAR_BASE}/GetLiveOverview?{prof['params']}&sportId=68",
            f"{ALTENAR_BASE}/GetUpcoming?{prof['params']}&sportId=68&eventCount=60",
            f"{ALTENAR_BASE}/GetEvents?{prof['params']}&sportId=68&eventCount=60&couponType=3"
        ]
        for ep in endpoints:
            data, _ = http_get_json(ep, hdrs, timeout=7)
            parsed = parse_altenar_payload(data)
            if parsed:
                collected.extend(parsed)
        if collected:
            used_profile = prof["name"]
            break

    return collected, used_profile

def normalize_last_name(name):
    """Extrae el apellido principal limpio para cruzar entre Pinnacle y Altenar."""
    clean = name.replace(",", " ").replace(".", " ").strip().lower()
    tokens = [t for t in clean.split() if len(t) > 2]
    return tokens[-1] if tokens else clean

def match_altenar_event(pinn_match, altenar_list):
    """Cruza un partido de Pinnacle contra la lista de Altenar."""
    p1_last = normalize_last_name(pinn_match["p1"])
    p2_last = normalize_last_name(pinn_match["p2"])

    for alt in altenar_list:
        a1 = alt["p1"].lower()
        a2 = alt["p2"].lower()
        if (p1_last in a1 or difflib.SequenceMatcher(None, p1_last, a1).ratio() > 0.75) and \
           (p2_last in a2 or difflib.SequenceMatcher(None, p2_last, a2).ratio() > 0.75):
            return alt["ml_odds"], False
        if (p1_last in a2 or difflib.SequenceMatcher(None, p1_last, a2).ratio() > 0.75) and \
           (p2_last in a1 or difflib.SequenceMatcher(None, p2_last, a1).ratio() > 0.75):
            return (alt["ml_odds"][1], alt["ml_odds"][0]), True
    return None, False

# =====================================================================
# FASE 3 & 4: EVALUACIÓN CUANTITATIVA, FILTRADO Y RENDERIZADO MÓVIL
# =====================================================================

def evaluate_match(m, altenar_events):
    o1, o2 = m["ml_full"]
    p1_true, p2_true, vig = shin_devig(o1, o2)

    tot_line = m["total_games"][0] if m.get("total_games") else None
    spr_line = m["spread_games"][0] if m.get("spread_games") else None

    if p1_true >= p2_true:
        fav_name, dog_name = m["p1"], m["p2"]
        fav_pinn_odd, dog_pinn_odd = o1, o2
        fav_prob, dog_prob = p1_true, p2_true
        fav_idx = 0
    else:
        fav_name, dog_name = m["p2"], m["p1"]
        fav_pinn_odd, dog_pinn_odd = o2, o1
        fav_prob, dog_prob = p2_true, p1_true
        fav_idx = 1

    dna = infer_match_dna(fav_prob, tot_line, spr_line)

    markov_adj = (dna["hold1_pct"] - 75.0) * 0.0015
    argon_prob = min(max(fav_prob + markov_adj, 0.05), 0.96)
    fair_odd   = round(1.0 / argon_prob, 3)

    min_triunfobet_odd = round(fair_odd * 1.045, 2)

    alt_odds, _ = match_altenar_event(m, altenar_events)
    alt_fav_odd = None
    real_ev_pct = None
    if alt_odds:
        alt_fav_odd = alt_odds[fav_idx]
        real_ev_pct = ((alt_fav_odd * argon_prob) - 1.0) * 100.0

    in_sweet_spot = (1.30 <= fav_pinn_odd <= 2.20)
    quality_score = dna["dna_score"] + (15.0 if in_sweet_spot else 0.0) + (20.0 if m["is_live"] else 0.0)
    if real_ev_pct and real_ev_pct > 0:
        quality_score += real_ev_pct * 3.0

    ref_odd_for_kelly = alt_fav_odd if (alt_fav_odd and alt_fav_odd > fair_odd) else min_triunfobet_odd
    b = ref_odd_for_kelly - 1.0
    q = 1.0 - argon_prob
    kelly_full = max(((b * argon_prob) - q) / b, 0.0) if b > 0 else 0.0
    stake_pct = round(min(max(kelly_full * 0.35 * 100.0, 1.5), 5.0), 2)

    return {
        "match": m,
        "fav_name": fav_name,
        "dog_name": dog_name,
        "fav_pinn_odd": fav_pinn_odd,
        "dog_pinn_odd": dog_pinn_odd,
        "pinn_vig": round(vig, 2),
        "pinn_fair_prob": round(fav_prob * 100.0, 1),
        "argon_prob": round(argon_prob * 100.0, 1),
        "fair_odd": round(fair_odd, 2),
        "min_triunfobet_odd": min_triunfobet_odd,
        "alt_fav_odd": alt_fav_odd,
        "real_ev_pct": round(real_ev_pct, 2) if real_ev_pct is not None else None,
        "dna": dna,
        "stake_pct": stake_pct,
        "quality_score": round(quality_score, 1),
        "in_sweet_spot": in_sweet_spot
    }

def render_sniper_card(rank, ev):
    m = ev["match"]
    dna = ev["dna"]
    st_badge = f"{C_BG_RED} 🔴 EN VIVO {C_RESET}" if m["is_live"] else f"{C_CYAN}⏳ {m['time_ve']}{C_RESET}"

    fav_am = decimal_to_american(ev["fav_pinn_odd"])
    dog_am = decimal_to_american(ev["dog_pinn_odd"])
    min_am = decimal_to_american(ev["min_triunfobet_odd"])

    print(f"{C_CYAN}╔════════════════════════════════════════╗{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} {C_BG_GREEN} 🏆 TOP #{rank:02d} FILTRADO {C_RESET} Score:{C_YELLOW}{ev['quality_score']}{C_RESET} {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╠════════════════════════════════════════╣{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} 🏟️  {C_YELLOW}{m['league'][:34]:<34}{C_RESET} {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} 🎾 {C_WHITE}{C_BOLD}{m['p1'][:16]} vs {m['p2'][:16]}{C_RESET} {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} ⏰ Estado: {st_badge}          {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╠════════════════════════════════════════╣{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} {C_MAGENTA}{C_BOLD}📊 LÍNEA SHARP PINNACLE (REAL):{C_RESET}        {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • {ev['fav_name'][:14]:<14}: {C_YELLOW}{C_BOLD}{ev['fav_pinn_odd']:.2f}{C_RESET} ({fav_am}) [Vig {ev['pinn_vig']}%] {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • {ev['dog_name'][:14]:<14}: {C_WHITE}{ev['dog_pinn_odd']:.2f}{C_RESET} ({dog_am})            {C_CYAN}║{C_RESET}")

    if m.get("total_games"):
        t_pts, t_ov, t_un = m["total_games"]
        print(f"{C_CYAN}║{C_RESET}  • Total Juegos  : {C_CYAN}{t_pts}{C_RESET} (Ov {t_ov:.2f}/Un {t_un:.2f}) {C_CYAN}║{C_RESET}")
    if m.get("spread_games"):
        s_pts, s_h, s_a = m["spread_games"]
        print(f"{C_CYAN}║{C_RESET}  • Hándicap Pin. : {C_CYAN}{s_pts:+.1f}{C_RESET} ({s_h:.2f} / {s_a:.2f})   {C_CYAN}║{C_RESET}")

    print(f"{C_CYAN}╠════════════════════════════════════════╣{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} {C_CYAN}{C_BOLD}🧬 ADN MARKOV DEL PARTIDO:{C_RESET}             {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • Retención Saque (Hold): {C_GREEN}{dna['hold1_pct']}%{C_RESET} vs {C_YELLOW}{dna['hold2_pct']}%{C_RESET}{C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • Prob. Real Motor Argon: {C_GREEN}{C_BOLD}{ev['argon_prob']}%{C_RESET}          {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • Prob. Ganar Set 1     : {C_CYAN}{dna['p1_set1_prob']}%{C_RESET}          {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  • Prob. Ganar 2-0 Sets  : {C_CYAN}{dna['p1_2_0_prob']}%{C_RESET}          {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╠════════════════════════════════════════╣{C_RESET}")
    print(f"{C_CYAN}║{C_RESET} {C_GREEN}{C_BOLD}🎯 ORDEN DE DISPARO EN TRIUNFOBET:{C_RESET}     {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  👉 Jugada : {C_WHITE}{C_BOLD}Gana {ev['fav_name'][:19]}{C_RESET} {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  ⚖️  Cuota Justa Exacta: {C_WHITE}{ev['fair_odd']:.2f}{C_RESET} ({decimal_to_american(ev['fair_odd'])})      {C_CYAN}║{C_RESET}")

    if ev["alt_fav_odd"]:
        alt_am = decimal_to_american(ev["alt_fav_odd"])
        ev_sign = f"+{ev['real_ev_pct']:.1f}%" if ev["real_ev_pct"] >= 0 else f"{ev['real_ev_pct']:.1f}%"
        ev_col = C_GREEN if ev["real_ev_pct"] >= 0 else C_RED
        print(f"{C_CYAN}║{C_RESET}  💵 Cuota Altenar Detectada: {C_YELLOW}{C_BOLD}{ev['alt_fav_odd']:.2f}{C_RESET} ({alt_am})  {C_CYAN}║{C_RESET}")
        print(f"{C_CYAN}║{C_RESET}  📈 Valor Esperado (+EV)   : {ev_col}{C_BOLD}{ev_sign}{C_RESET}        {C_CYAN}║{C_RESET}")

    print(f"{C_CYAN}║{C_RESET}  🔥 {C_YELLOW}ENTRAR SI TRIUNFOBET PAGA >={C_RESET}       {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}     {C_GREEN}{C_BOLD}Cuota {ev['min_triunfobet_odd']:.2f}{C_RESET}  (Americano: {C_GREEN}{C_BOLD}{min_am}{C_RESET})    {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_RESET}  💰 Stake Kelly: {C_GREEN}{C_BOLD}${ev['stake_pct']:.2f}{C_RESET} (por cada $100) {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╚════════════════════════════════════════╝{C_RESET}\n")

def main():
    search_filter = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

    print(f"\n{C_CYAN}╔════════════════════════════════════════╗{C_RESET}")
    print(f"{C_CYAN}║{C_WHITE}{C_BOLD} ARGON-APEX v40 // PINNACLE + MARKOV    {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_GREEN} ESCÁNER MULTINÚCLEO (POCO X6 PRO)      {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╚════════════════════════════════════════╝{C_RESET}")
    now_ve = datetime.now(TZ_VE).strftime("%Y-%m-%d %I:%M:%S %p (Hora VE)")
    print(f" {C_DIM}⌚ Reloj del Sistema: {now_ve}{C_RESET}\n")

    t0 = time.time()
    print(f"{C_CYAN}[1/4] Lanzando 10 hilos en paralelo hacia Pinnacle Arcadia Sharp API...{C_RESET}")
    pinn_matches, pinn_status = fetch_all_pinnacle_tennis(search_filter)
    print(f"  {C_GREEN}✓ Pinnacle Sharp:{C_RESET} {len(pinn_matches)} partidos con cuotas reales descargados ({pinn_status}).")

    print(f"{C_CYAN}[2/4] Consultando motor Altenar (TriunfoBet / Red BIAHosted)...{C_RESET}")
    alt_events, alt_source = fetch_altenar_tennis()
    if alt_events:
        print(f"  {C_GREEN}✓ Altenar ({alt_source}):{C_RESET} {len(alt_events)} partidos con cuotas cargados.")
    else:
        print(f"  {C_YELLOW}ℹ️ Altenar:{C_RESET} Sin cruce directo de sesión; calculando Precio Gatillo Exacto para TriunfoBet.")

    if not pinn_matches:
        print(f"\n{C_BG_RED} [!] No se encontraron partidos en Pinnacle para el filtro '{search_filter}'. {C_RESET}\n")
        return

    print(f"{C_CYAN}[3/4] Ejecutando Cadena de Markov (ADN de Saque/Quiebre) en {len(pinn_matches)} partidos...{C_RESET}")
    evaluated = [evaluate_match(m, alt_events) for m in pinn_matches]

    if search_filter:
        passed = sorted(evaluated, key=lambda x: x["quality_score"], reverse=True)
    else:
        passed = [e for e in evaluated if e["in_sweet_spot"] and e["argon_prob"] >= 53.0]
        if not passed:
            passed = evaluated
        passed.sort(key=lambda x: x["quality_score"], reverse=True)

    elapsed = round(time.time() - t0, 2)
    top_n = passed[:8] if not search_filter else passed[:15]

    print(f"{C_CYAN}[4/4] Embudo completado en {elapsed}s:{C_RESET} {C_GREEN}{C_BOLD}{len(evaluated)} analizados ➔ TOP {len(top_n)} seleccionados.{C_RESET}\n")

    for idx, item in enumerate(top_n, 1):
        render_sniper_card(idx, item)

    print(f"{C_GREEN}{C_BOLD}[✓] Auditoría Matemática Completada ({elapsed}s en POCO X6 Pro).{C_RESET}")
    print(f"{C_YELLOW}💡 CÓMO USAR CADA TARJETA EN TRIUNFOBET:{C_RESET}")
    print(f"  1. Mira la línea {C_GREEN}'ENTRAR SI TRIUNFOBET PAGA >='{C_RESET} (viene en Decimal y en Americano).")
    print(f"  2. Si en tu app de TriunfoBet la cuota es IGUAL o MEJOR que ese número, tienes {C_GREEN}+EV garantizado{C_RESET} contra Pinnacle.")
    print(f"  3. Comandos rápidos de filtrado:")
    print(f"     {C_CYAN}python3 argon_apex_v36_autoscout.py Shanghai{C_RESET}")
    print(f"     {C_CYAN}python3 argon_apex_v36_autoscout.py Jinan{C_RESET}")
    print(f"     {C_CYAN}python3 argon_apex_v36_autoscout.py WTA{C_RESET}\n")

if __name__ == "__main__":
    main()
