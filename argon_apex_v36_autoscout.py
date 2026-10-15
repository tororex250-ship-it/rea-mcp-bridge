#!/usr/bin/env python3
"""
ARGON-APEX v36 (v38 ENGINE): LIVE API TRUTH AUDITOR & REAL-TIME SCANNER
=======================================================================
REGLA DE ORO: CERO DATOS FALSOS / CERO PARTIDOS HARDCODEADOS.
Si desconectas el internet de tu teléfono, este script dará ERROR DE RED.
Jamás inventa ni rellena partidos de prueba.

Fuentes en vivo que consulta en tiempo real desde tu teléfono:
1. SofaScore API v1 (/api/v1/sport/tennis/scheduled-events/YYYY-MM-DD + /odds/1/all)
2. ESPN Open API (site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard)
3. Altenar TriunfoBet API (diagnóstico transparente de estado HTTP)
"""

import sys
import json
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Zona horaria oficial de Venezuela (UTC-4)
TZ_VE = timezone(timedelta(hours=-4))

# Colores ANSI de alto contraste para móvil
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
C_BG_RED   = "\033[41;97m"

def banner():
    print(f"\n{C_CYAN}╔════════════════════════════════════════╗{C_RESET}")
    print(f"{C_CYAN}║{C_WHITE}{C_BOLD}  ARGON-APEX // ESCÁNER 100% API REAL   {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}║{C_GREEN}   CERO DATOS FALSOS · EN VIVO (VE)     {C_CYAN}║{C_RESET}")
    print(f"{C_CYAN}╚════════════════════════════════════════╝{C_RESET}")
    now_ve = datetime.now(TZ_VE).strftime("%Y-%m-%d %I:%M:%S %p (Hora VE)")
    print(f" {C_DIM}⌚ Reloj del Sistema: {now_ve}{C_RESET}\n")

def frac_to_decimal(frac_str):
    """Convierte cuota fraccionaria de SofaScore (ej. '7/25' o '5/2') a decimal (1.28, 3.50)."""
    try:
        if "/" in str(frac_str):
            num, den = str(frac_str).split("/")
            return round(1.0 + (float(num) / float(den)), 2)
        return round(float(frac_str), 2)
    except Exception:
        return 0.0

def decimal_to_american(dec):
    """Convierte cuota decimal a formato americano (como sale en SofaScore: -358, +250)."""
    if dec <= 1.0:
        return "N/A"
    if dec >= 2.0:
        return f"+{int(round((dec - 1.0) * 100))}"
    else:
        return f"-{int(round(100.0 / (dec - 1.0)))}"

def http_get_json(url, extra_headers=None, timeout=12):
    """
    Descarga JSON real desde internet probando:
    1. curl_cffi (si está instalado, huella TLS Chrome)
    2. binario curl nativo de Termux
    3. urllib estándar de Python
    Devuelve (datos_json, estado_texto).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; POCO X6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-VE,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache"
    }
    if extra_headers:
        headers.update(extra_headers)

    # 1. Intentar con curl_cffi si está disponible
    try:
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(url, headers=headers, impersonate="chrome120", timeout=timeout)
        if r.status_code == 200:
            return r.json(), "OK (curl_cffi TLS)"
    except Exception:
        pass

    # 2. Intentar con curl nativo de Android/Termux
    try:
        cmd = ["curl", "-s", "-L", "--max-time", str(timeout)]
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
        cmd.append(url)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        out = res.stdout.strip()
        if res.returncode == 0 and out.startswith("{"):
            parsed = json.loads(out)
            if "error" not in parsed:
                return parsed, "OK (curl nativo)"
    except Exception:
        pass

    # 3. Intentar con urllib de Python
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw), f"OK (HTTP {resp.status})"
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} ({e.reason})"
    except Exception as e:
        return None, f"Error red: {str(e)[:40]}"

def fetch_sofascore_odds(event_id):
    """Consulta las cuotas reales de un partido en SofaScore."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/odds/1/all"
    data, _ = http_get_json(url, {
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com"
    }, timeout=8)
    if not data or "markets" not in data:
        return None
    
    markets_out = {}
    for m in data.get("markets", []):
        m_name = m.get("marketName", "")
        choices = m.get("choices", [])
        if m_name in ("Full time", "First set winner") and len(choices) >= 2:
            c1 = frac_to_decimal(choices[0].get("fractionalValue", "0"))
            c2 = frac_to_decimal(choices[1].get("fractionalValue", "0"))
            init1 = frac_to_decimal(choices[0].get("initialFractionalValue", "0"))
            init2 = frac_to_decimal(choices[1].get("initialFractionalValue", "0"))
            if c1 > 1.0 and c2 > 1.0:
                markets_out[m_name] = {
                    "curr": (c1, c2),
                    "init": (init1, init2)
                }
    return markets_out

def fetch_espn_fallback():
    """Consulta la API abierta de ESPN para ATP y WTA si SofaScore bloquea la IP."""
    events_out = []
    for tour in ("atp", "wta"):
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
        data, _ = http_get_json(url, timeout=10)
        if not data or "events" not in data:
            continue
        for ev in data.get("events", []):
            t_name = ev.get("name", tour.upper())
            for grp in ev.get("groupings", []):
                slug = grp.get("grouping", {}).get("slug", "")
                if "doubles" in slug:
                    continue
                for comp in grp.get("competitions", []):
                    st_type = comp.get("status", {}).get("type", {})
                    state = st_type.get("state", "")
                    if state not in ("pre", "in"):
                        continue
                    comps = comp.get("competitors", [])
                    if len(comps) < 2:
                        continue
                    p1 = comps[0].get("athlete", {}).get("displayName", "Jugador 1")
                    p2 = comps[1].get("athlete", {}).get("displayName", "Jugador 2")
                    date_str = comp.get("date", "")
                    try:
                        dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        dt_ve = dt_utc.astimezone(TZ_VE).strftime("%a %d/%m · %I:%M %p")
                        ts = int(dt_utc.timestamp())
                    except Exception:
                        dt_ve = date_str
                        ts = 0
                    events_out.append({
                        "id": comp.get("id", "ESPN"),
                        "tourney": f"{tour.upper()}: {t_name}",
                        "p1": p1,
                        "p2": p2,
                        "time_ve": dt_ve,
                        "ts": ts,
                        "status": "🔴 EN VIVO" if state == "in" else "⏳ Programado",
                        "source": "espn"
                    })
    return events_out

def render_live_card(idx, ev_obj):
    print(f"{C_CYAN}┌────────────────────────────────────────┐{C_RESET}")
    print(f"{C_CYAN}│ {C_WHITE}{C_BOLD}📡 PARTIDO REAL #{idx:02d}{C_RESET} {C_DIM}[ID:{ev_obj['id']}]{C_RESET} {C_CYAN}│{C_RESET}")
    print(f"{C_CYAN}│{C_RESET} 🏆 {C_YELLOW}{ev_obj['tourney'][:34]:<34}{C_RESET} {C_CYAN}│{C_RESET}")
    print(f"{C_CYAN}│{C_RESET} 🎾 {C_WHITE}{C_BOLD}{ev_obj['p1'][:16]} vs {ev_obj['p2'][:16]}{C_RESET} {C_CYAN}│{C_RESET}")
    print(f"{C_CYAN}│{C_RESET} ⏰ {C_CYAN}Hora VE:{C_RESET} {C_WHITE}{ev_obj['time_ve']:<26}{C_RESET} {C_CYAN}│{C_RESET}")
    print(f"{C_CYAN}│{C_RESET} 📌 {C_DIM}Estado :{C_RESET} {ev_obj['status']:<26} {C_CYAN}│{C_RESET}")
    
    if ev_obj.get("odds_ft"):
        o1, o2 = ev_obj["odds_ft"]["curr"]
        i1, i2 = ev_obj["odds_ft"]["init"]
        am1, am2 = decimal_to_american(o1), decimal_to_american(o2)
        
        # Probabilidad real devigged (quitando el margen de la casa)
        inv1, inv2 = 1.0 / o1, 1.0 / o2
        margin = (inv1 + inv2)
        p1_true = (inv1 / margin) * 100.0
        p2_true = (inv2 / margin) * 100.0
        fair1 = round(100.0 / p1_true, 2)
        fair2 = round(100.0 / p2_true, 2)
        
        # Cuota mínima que debes encontrar en TriunfoBet para tener +5% de EV real
        target1 = round(fair1 * 1.05, 2)
        target2 = round(fair2 * 1.05, 2)
        
        print(f"{C_CYAN}├────────────────────────────────────────┤{C_RESET}")
        print(f"{C_CYAN}│{C_RESET} 💵 {C_WHITE}{ev_obj['p1'][:12]:<12}:{C_RESET} {C_YELLOW}{C_BOLD}{o1:.2f}{C_RESET} ({am1}) ➔ {C_GREEN}{p1_true:.1f}%{C_RESET} {C_CYAN}│{C_RESET}")
        print(f"{C_CYAN}│{C_RESET} 💵 {C_WHITE}{ev_obj['p2'][:12]:<12}:{C_RESET} {C_YELLOW}{C_BOLD}{o2:.2f}{C_RESET} ({am2}) ➔ {C_GREEN}{p2_true:.1f}%{C_RESET} {C_CYAN}│{C_RESET}")
        
        # Detectar caída de cuota (Steam Move) respecto a la apertura
        if i1 > o1 + 0.05:
            print(f"{C_CYAN}│{C_RESET} 🔥 {C_GREEN}STEAM MOVE:{C_RESET} {ev_obj['p1'][:12]} cayó de {i1:.2f} a {o1:.2f} {C_CYAN}│{C_RESET}")
        elif i2 > o2 + 0.05:
            print(f"{C_CYAN}│{C_RESET} 🔥 {C_GREEN}STEAM MOVE:{C_RESET} {ev_obj['p2'][:12]} cayó de {i2:.2f} a {o2:.2f} {C_CYAN}│{C_RESET}")
            
        print(f"{C_CYAN}├────────────────────────────────────────┤{C_RESET}")
        print(f"{C_CYAN}│{C_RESET} 🎯 {C_WHITE}Entrar en TriunfoBet SOLO si paga:{C_RESET}  {C_CYAN}│{C_RESET}")
        print(f"{C_CYAN}│{C_RESET}    • {ev_obj['p1'][:14]:<14} >= {C_GREEN}{C_BOLD}{target1:.2f}{C_RESET} (Justa {fair1:.2f}) {C_CYAN}│{C_RESET}")
        print(f"{C_CYAN}│{C_RESET}    • {ev_obj['p2'][:14]:<14} >= {C_GREEN}{C_BOLD}{target2:.2f}{C_RESET} (Justa {fair2:.2f}) {C_CYAN}│{C_RESET}")
    else:
        print(f"{C_CYAN}├────────────────────────────────────────┤{C_RESET}")
        print(f"{C_CYAN}│{C_RESET} {C_DIM}ℹ️  Cuotas en apertura / por publicar{C_RESET}  {C_CYAN}│{C_RESET}")
    print(f"{C_CYAN}└────────────────────────────────────────┘{C_RESET}\n")

def run_live_audit(search_filter=""):
    banner()
    
    # 1. Diagnóstico transparente de Altenar (TriunfoBet)
    print(f"{C_CYAN}[1/3] Auditando API Altenar (TriunfoBet)...{C_RESET}")
    altenar_url = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetUpcoming?timezoneOffset=240&langId=4&skinName=triunfobet&configId=12&culture=es-ES&countryCode=VE&deviceType=1&numformat=en&integration=triunfobet&sportId=68"
    alt_data, alt_status = http_get_json(altenar_url, {
        "Origin": "https://triunfobet.com",
        "Referer": "https://triunfobet.com/"
    }, timeout=8)
    
    if alt_data and isinstance(alt_data, dict) and alt_data.get("events"):
        print(f"  {C_GREEN}✓ Altenar devolvió {len(alt_data['events'])} eventos en directo.{C_RESET}\n")
    else:
        print(f"  {C_YELLOW}⚠ Estado Altenar:{C_RESET} {alt_status}")
        print(f"  {C_DIM}(Altenar pide sesión de navegador; cero datos inventados).{C_RESET}\n")

    # 2. Consultar SofaScore en vivo (Hoy y Mañana en hora de Venezuela)
    now_ve = datetime.now(TZ_VE)
    dates_to_check = [
        now_ve.strftime("%Y-%m-%d"),
        (now_ve + timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    
    all_real_events = []
    for dt_str in dates_to_check:
        print(f"{C_CYAN}[2/3] Descargando cartelera real de SofaScore ({dt_str})...{C_RESET}")
        ss_url = f"https://api.sofascore.com/api/v1/sport/tennis/scheduled-events/{dt_str}"
        ss_data, ss_status = http_get_json(ss_url, {
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com"
        }, timeout=12)
        
        if ss_data and "events" in ss_data:
            evs = ss_data["events"]
            print(f"  {C_GREEN}✓ {len(evs)} partidos oficiales recibidos de SofaScore ({ss_status}).{C_RESET}")
            all_real_events.extend(evs)
        else:
            print(f"  {C_RED}✗ SofaScore ({dt_str}): {ss_status}{C_RESET}")

    filtered = []
    if all_real_events:
        seen_ids = set()
        for e in all_real_events:
            eid = e.get("id")
            if not eid or eid in seen_ids:
                continue
            seen_ids.add(eid)
            
            status_type = e.get("status", {}).get("type", "")
            if status_type not in ("notstarted", "inprogress"):
                continue
                
            t_info = e.get("tournament", {})
            cat_name = t_info.get("category", {}).get("name", "")
            t_name = t_info.get("name", "Torneo")
            
            p1 = e.get("homeTeam", {}).get("name", "Jugador 1")
            p2 = e.get("awayTeam", {}).get("name", "Jugador 2")
            
            if "/" in p1 or "/" in p2:
                continue
                
            if search_filter:
                q = search_filter.lower()
                if q not in p1.lower() and q not in p2.lower() and q not in t_name.lower() and q not in cat_name.lower():
                    continue
            else:
                if not any(k in cat_name for k in ("ATP", "WTA", "Challenger")):
                    continue

            ts = e.get("startTimestamp", 0)
            dt_ve = datetime.fromtimestamp(ts, TZ_VE).strftime("%a %d/%m · %I:%M %p") if ts else "Por definir"
            st_desc = "🔴 EN VIVO" if status_type == "inprogress" else "⏳ Programado"
            
            filtered.append({
                "id": eid,
                "tourney": f"{cat_name}: {t_name}",
                "p1": p1,
                "p2": p2,
                "time_ve": dt_ve,
                "ts": ts,
                "status": st_desc,
                "source": "sofascore"
            })
    else:
        print(f"\n{C_YELLOW}[*] Consultando respaldo en vivo de ESPN API...{C_RESET}")
        espn_evs = fetch_espn_fallback()
        if espn_evs:
            print(f"  {C_GREEN}✓ ESPN API devolvió {len(espn_evs)} partidos reales.{C_RESET}")
            for item in espn_evs:
                if search_filter:
                    q = search_filter.lower()
                    if q not in item["p1"].lower() and q not in item["p2"].lower() and q not in item["tourney"].lower():
                        continue
                filtered.append(item)

    if not filtered:
        print(f"\n{C_BG_RED} [!] SIN DATOS EN VIVO PARA MOSTRAR {C_RESET}")
        print(f"{C_WHITE}Este script NO contiene partidos de relleno. Si no hay conexión o coincidencias, se detiene aquí.{C_RESET}\n")
        return

    filtered.sort(key=lambda x: x["ts"])

    print(f"\n{C_CYAN}[3/3] Mostrando partidos reales verificados ({len(filtered)} encontrados):{C_RESET}\n")
    
    limit = 10 if not search_filter else 25
    shown = 0
    for item in filtered[:limit]:
        if item.get("source") == "sofascore":
            odds_map = fetch_sofascore_odds(item["id"])
            if odds_map:
                item["odds_ft"] = odds_map.get("Full time")
                item["odds_s1"] = odds_map.get("First set winner")
        shown += 1
        render_live_card(shown, item)

    print(f"{C_GREEN}{C_BOLD}[✓] Escaneo 100% real finalizado ({shown} partidos en pantalla).{C_RESET}")
    print(f"{C_YELLOW}🔎 Filtra por cualquier jugador o torneo real en vivo:{C_RESET}")
    print(f"   {C_CYAN}python3 argon_apex_v36_autoscout.py Landaluce{C_RESET}")
    print(f"   {C_CYAN}python3 argon_apex_v36_autoscout.py Jinan{C_RESET}")
    print(f"   {C_CYAN}python3 argon_apex_v36_autoscout.py Shanghai{C_RESET}\n")

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    run_live_audit(query)
