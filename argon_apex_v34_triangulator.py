"""
ARGON-APEX v34: Triangulated Tennis Spacetime Engine (Live Interactive & Auto)
SofaScore Telemetry + Pinnacle Arcadia Sharp Benchmark + Altenar (TriunfoBet) Exploiter
Author: Luis Alfredo (tororex250) + Argon / Spark Quantitative Core
"""

import math
import sys
from typing import Dict, Tuple, List, Optional

# =====================================================================
# 1. MOTOR DE DESPOJO DE MARGEN (Pinnacle Sharp Truth / Devigging)
# =====================================================================

def devig_two_way(odds_a: float, odds_b: float) -> Tuple[float, float, float]:
    """
    Toma las cuotas de 2 vías de Pinnacle, calcula el sobremargen (vig)
    y devuelve las probabilidades justas reales (P_fair_a, P_fair_b).
    """
    if odds_a <= 1.0 or odds_b <= 1.0:
        return 0.5, 0.5, 0.0
    implied_a = 1.0 / odds_a
    implied_b = 1.0 / odds_b
    overround = implied_a + implied_b
    vig_pct = (overround - 1.0) * 100.0
    p_fair_a = implied_a / overround
    p_fair_b = implied_b / overround
    return p_fair_a, p_fair_b, vig_pct

# =====================================================================
# 2. MOTOR DE MARKOV JERÁRQUICO (Telemetría de SofaScore punto a punto)
# =====================================================================

def p_game_hold(p: float) -> float:
    """Calcula la probabilidad exacta de hold desde el saque individual p."""
    if p <= 0.0: return 0.0
    if p >= 1.0: return 1.0
    q = 1.0 - p
    p_before_deuce = (p**4) * (1.0 + 4.0*q + 10.0*(q**2))
    p_deuce = 20.0 * (p**3) * (q**3)
    p_win_from_deuce = (p**2) / (p**2 + q**2)
    return p_before_deuce + (p_deuce * p_win_from_deuce)


def p_tiebreak(p_a: float, p_b: float) -> float:
    """Probabilidad exacta de Tie-break a 7 puntos con saques alternados."""
    memo = {}
    def tb_prob(a: int, b: int) -> float:
        if a >= 7 and (a - b) >= 2: return 1.0
        if b >= 7 and (b - a) >= 2: return 0.0
        if a == 6 and b == 6:
            p_win_2 = p_a * (1.0 - p_b)
            p_lose_2 = (1.0 - p_a) * p_b
            if (p_win_2 + p_lose_2) == 0: return 0.5
            return p_win_2 / (p_win_2 + p_lose_2)
            
        state = (a, b)
        if state in memo: return memo[state]
        total_pts = a + b
        is_a_serving = True if (total_pts % 4 in (0, 3)) else False
        p_pt_a = p_a if is_a_serving else (1.0 - p_b)
        prob = p_pt_a * tb_prob(a + 1, b) + (1.0 - p_pt_a) * tb_prob(a, b + 1)
        memo[state] = prob
        return prob

    return tb_prob(0, 0)


def calculate_set_and_match(p_a: float, p_b: float) -> Tuple[float, float, float]:
    """Devuelve (P_Set1_A, P_Partido_A, Promedio_Games_Set)."""
    hold_a = p_game_hold(p_a)
    hold_b = p_game_hold(p_b)
    exact_scores = {}
    
    def play_set(g_a: int, g_b: int, server: int, prob_so_far: float):
        if (g_a == 6 and g_b <= 4) or (g_b == 6 and g_a <= 4):
            score = f"{g_a}-{g_b}"
            exact_scores[score] = exact_scores.get(score, 0.0) + prob_so_far
            return
        if (g_a == 7 and g_b == 5) or (g_b == 7 and g_a == 5):
            score = f"{g_a}-{g_b}"
            exact_scores[score] = exact_scores.get(score, 0.0) + prob_so_far
            return
        if g_a == 6 and g_b == 6:
            tb_a_win = p_tiebreak(p_a, p_b)
            exact_scores["7-6"] = exact_scores.get("7-6", 0.0) + prob_so_far * tb_a_win
            exact_scores["6-7"] = exact_scores.get("6-7", 0.0) + prob_so_far * (1.0 - tb_a_win)
            return

        p_win_game = hold_a if server == 0 else (1.0 - hold_b)
        play_set(g_a + 1, g_b, 1 - server, prob_so_far * p_win_game)
        play_set(g_a, g_b + 1, 1 - server, prob_so_far * (1.0 - p_win_game))

    play_set(0, 0, 0, 0.5)
    play_set(0, 0, 1, 0.5)
    
    p_set_a = sum(prob for score, prob in exact_scores.items() if int(score.split("-")[0]) > int(score.split("-")[1]))
    p_match_a = (p_set_a ** 2) + (2.0 * (p_set_a ** 2) * (1.0 - p_set_a))
    avg_games_set = sum((int(s.split("-")[0]) + int(s.split("-")[1])) * pr for s, pr in exact_scores.items())
    return p_set_a, p_match_a, avg_games_set

# =====================================================================
# 3. MOTOR DE TRIANGULACIÓN (SofaScore + Pinnacle -> Altenar TriunfoBet)
# =====================================================================

def triangulate_market_edge(
    market_name: str,
    p_markov: float,
    pinnacle_odds: Tuple[float, float],
    altenar_odds: float,
    tier: str = "CHALLENGER",
    bankroll: float = 100.0
) -> Dict:
    p_pin_fair, _, vig = devig_two_way(pinnacle_odds[0], pinnacle_odds[1])
    
    if tier.upper() in ["CHALLENGER", "ITF"]:
        w_markov, w_pin = 0.60, 0.40
    else:
        w_markov, w_pin = 0.35, 0.65
        
    p_true = (w_markov * p_markov) + (w_pin * p_pin_fair)
    p_implied_altenar = 1.0 / altenar_odds
    
    ev = (p_true * altenar_odds) - 1.0
    edge_pct = (p_true - p_implied_altenar) * 100.0
    
    if ev > 0.0:
        full_kelly = (p_true * altenar_odds - 1.0) / (altenar_odds - 1.0)
        frac_kelly = 0.25 * full_kelly
        stake_pct = min(frac_kelly, 0.035)  # Máximo 3.5% del bank
        stake_amount = round(bankroll * stake_pct, 2)
        signal = "SNIPER BUY" if ev >= 0.08 else "VALUE BUY"
    else:
        stake_amount = 0.0
        signal = "NO VALUE (-EV)"

    return {
        "market": market_name,
        "pinnacle_raw": f"{pinnacle_odds[0]}/{pinnacle_odds[1]}",
        "p_pin_fair": round(p_pin_fair * 100, 1),
        "p_markov": round(p_markov * 100, 1),
        "p_true_triangulated": round(p_true * 100, 1),
        "altenar_odds": altenar_odds,
        "p_altenar_implied": round(p_implied_altenar * 100, 1),
        "ev_pct": round(ev * 100, 2),
        "edge_pct": round(edge_pct, 2),
        "stake": stake_amount,
        "signal": signal
    }

# =====================================================================
# 4. MODO INTERACTIVO EN VIVO PARA TERMUX
# =====================================================================

def interactive_mode():
    print("\n" + "="*66)
    print("  ARGON-APEX v34: ANÁLISIS CUANTITATIVO EN VIVO (TERMUX)")
    print("="*66)
    try:
        player_a = input("[?] Nombre Jugador A (ej: Alcaraz): ").strip() or "Jugador A"
        player_b = input("[?] Nombre Jugador B (ej: Sinner): ").strip() or "Jugador B"
        t_choice = input("[?] Torneo: 1=Challenger/ITF, 2=ATP/WTA [Defecto 1]: ").strip()
        tier = "ATP" if t_choice == "2" else "CHALLENGER"
        
        print("\n[+] Telemetría SofaScore (% Puntos ganados al saque en esta pista):")
        p_a = float(input(f"    - % Saque {player_a} (ej: 66): ")) / 100.0
        p_b = float(input(f"    - % Saque {player_b} (ej: 59): ")) / 100.0
        
        print("\n[+] Cuotas de Cierre Pinnacle (Sharp Benchmark):")
        pin_a = float(input(f"    - Cuota Pinnacle {player_a}: "))
        pin_b = float(input(f"    - Cuota Pinnacle {player_b}: "))
        
        print("\n[+] Cuotas de la Casa Soft (TriunfoBet / Altenar):")
        soft_a = float(input(f"    - Cuota TriunfoBet {player_a} (Partido): "))
        soft_set1_str = input(f"    - Cuota TriunfoBet {player_a} (Set 1) [Opcional / Enter]: ").strip()
        
        b_str = input("\n[?] Tu Bankroll en USD [Defecto 100]: ").strip()
        bankroll = float(b_str) if b_str else 100.0
        
    except (ValueError, KeyboardInterrupt):
        print("\n[!] Operación cancelada.")
        return

    p_set1_m, p_match_m, avg_g = calculate_set_and_match(p_a, p_b)
    
    print("\n" + "="*66)
    print(f"  RESULTADO DEL SCOUTING: {player_a} vs {player_b} ({tier})")
    print("="*66)
    
    res = triangulate_market_edge(f"Ganador Partido ({player_a})", p_match_m, (pin_a, pin_b), soft_a, tier, bankroll)
    print(f"[+] MERCADO: {res['market']} | Señal: [{res['signal']}]")
    print(f"    Pinnacle Fair: {res['p_pin_fair']}% | SofaScore Markov: {res['p_markov']}% ➔ Triangulada: {res['p_true_triangulated']}%")
    print(f"    Cuota TriunfoBet: {res['altenar_odds']} (Implica: {res['p_altenar_implied']}%)")
    print(f"    VENTAJA (+EV): {res['ev_pct']}% | Edge: {res['edge_pct']}%")
    if res['stake'] > 0:
        print(f"    STAKE RECOMENDADO (0.25 Kelly): ${res['stake']} ({res['stake']/bankroll*100:.1f}% de tu bank)")
    else:
        print(f"    RECOMENDACIÓN: NO ENTRAR. Sin valor matemático.")
        
    if soft_set1_str:
        soft_set1 = float(soft_set1_str)
        res_s1 = triangulate_market_edge(f"Ganador Set 1 ({player_a})", p_set1_m, (pin_a * 1.04, pin_b * 0.96), soft_set1, tier, bankroll)
        print(f"\n[+] MERCADO: {res_s1['market']} | Señal: [{res_s1['signal']}]")
        print(f"    Probabilidad Real: {res_s1['p_true_triangulated']}% vs Cuota TriunfoBet: {res_s1['altenar_odds']}")
        print(f"    VENTAJA (+EV): {res_s1['ev_pct']}% | Stake: ${res_s1['stake']}")
    print("="*66 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        p_a, p_b = 0.66, 0.59
        p_s1, p_m, _ = calculate_set_and_match(p_a, p_b)
        r = triangulate_market_edge("Ganador Partido (A)", p_m, (1.54, 2.65), 1.63, "CHALLENGER", 100.0)
        print(f"[DEMO] {r['market']} | {r['signal']} | EV: {r['ev_pct']}% | Stake: ${r['stake']}")
    else:
        interactive_mode()
