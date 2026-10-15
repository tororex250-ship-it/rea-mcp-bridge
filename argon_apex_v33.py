"""
ARGON-APEX v33: Quantitative Tennis Spacetime Engine & Altenar (+EV) Exploiter
Designed for Termux execution (POCO X6 Pro) & Cloud Analysis.
Author: Luis Alfredo (tororex250) + Argon / Spark Quantitative Core
"""

import math
import sys
import json
from typing import Dict, Tuple, List

# =====================================================================
# 1. MOTOR JERÁRQUICO DE MARKOV (Barnett & Clarke / Klaassen-Magnus)
# =====================================================================

def p_game_hold(p: float) -> float:
    """Calcula la probabilidad exacta de que un jugador mantenga su saque (Hold)."""
    if p <= 0.0: return 0.0
    if p >= 1.0: return 1.0
    q = 1.0 - p
    p_before_deuce = (p**4) * (1.0 + 4.0*q + 10.0*(q**2))
    p_deuce = 20.0 * (p**3) * (q**3)
    p_win_from_deuce = (p**2) / (p**2 + q**2)
    return p_before_deuce + (p_deuce * p_win_from_deuce)


def p_tiebreak(p_a: float, p_b: float) -> float:
    """Calcula la probabilidad exacta de victoria en Tie-break a 7 puntos con saques alternados."""
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


def calculate_set_probabilities(p_a: float, p_b: float) -> Dict[str, float]:
    """Proyecta distribución exacta de marcadores de un Set (6-0, 6-4, 7-6, etc.)."""
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
    
    total_games_dist = {}
    for score, prob in exact_scores.items():
        g1, g2 = map(int, score.split("-"))
        total = g1 + g2
        total_games_dist[total] = total_games_dist.get(total, 0.0) + prob
        
    return {
        "p_set_a": p_set_a,
        "p_set_b": 1.0 - p_set_a,
        "hold_a": hold_a,
        "hold_b": hold_b,
        "score_dist": exact_scores,
        "games_dist": total_games_dist
    }


def calculate_match_markets(p_a: float, p_b: float, best_of: int = 3) -> Dict:
    """Calcula probabilidades analíticas completas para el partido."""
    set_metrics = calculate_set_probabilities(p_a, p_b)
    p_s = set_metrics["p_set_a"]
    
    if best_of == 3:
        p_2_0 = p_s ** 2
        p_2_1 = 2.0 * (p_s ** 2) * (1.0 - p_s)
        p_match_a = p_2_0 + p_2_1
        p_0_2 = (1.0 - p_s) ** 2
        p_1_2 = 2.0 * ((1.0 - p_s) ** 2) * p_s
        p_match_b = p_0_2 + p_1_2
    else:
        p_3_0 = p_s ** 3
        p_3_1 = 3.0 * (p_s ** 3) * (1.0 - p_s)
        p_3_2 = 6.0 * (p_s ** 3) * ((1.0 - p_s) ** 2)
        p_match_a = p_3_0 + p_3_1 + p_3_2
        p_match_b = 1.0 - p_match_a

    avg_games_per_set = sum(games * prob for games, prob in set_metrics["games_dist"].items())
    expected_sets = (2.0 * (p_s**2 + (1-p_s)**2)) + (3.0 * (2.0 * p_s * (1-p_s)))
    expected_total_games = avg_games_per_set * expected_sets

    return {
        "p_match_a": p_match_a,
        "p_match_b": p_match_b,
        "p_set_1_a": p_s,
        "p_set_1_b": 1.0 - p_s,
        "avg_games_per_set": avg_games_per_set,
        "expected_total_games": expected_total_games,
        "hold_prob_a": set_metrics["hold_a"],
        "hold_prob_b": set_metrics["hold_b"]
    }

# =====================================================================
# 2. EVALUADOR DE VALOR ESPERADO (+EV) CONTRA ALTENAR / TRIUNFOBET
# =====================================================================

def evaluate_market_value(market_name: str, p_true: float, soft_odds: float, bankroll: float = 100.0, max_stake_pct: float = 0.035) -> Dict:
    """Evalúa +EV y dimensiona el stake con Criterio de Kelly Fraccional (0.25)."""
    if soft_odds <= 1.0:
        return {"ev": -1.0, "edge_pct": 0.0, "stake": 0.0, "signal": "SKIP"}
        
    p_implied = 1.0 / soft_odds
    ev = (p_true * soft_odds) - 1.0
    edge_pct = (p_true - p_implied) * 100.0
    
    if ev > 0.0:
        full_kelly = (p_true * soft_odds - 1.0) / (soft_odds - 1.0)
        frac_kelly = 0.25 * full_kelly
        stake_pct = min(frac_kelly, max_stake_pct)
        stake_amount = round(bankroll * stake_pct, 2)
        signal = "STRONG BUY" if ev >= 0.08 else "VALUE BUY"
    else:
        stake_pct = 0.0
        stake_amount = 0.0
        signal = "NO VALUE (-EV)"
        
    return {
        "market": market_name,
        "p_true": round(p_true * 100.0, 2),
        "p_implied": round(p_implied * 100.0, 2),
        "soft_odds": soft_odds,
        "ev_pct": round(ev * 100.0, 2),
        "edge_pct": round(edge_pct, 2),
        "kelly_stake_pct": round(stake_pct * 100.0, 2),
        "recommended_stake": stake_amount,
        "signal": signal
    }

# =====================================================================
# 3. INTERFAZ INTERACTIVA PARA TERMUX
# =====================================================================

def run_scout_analysis(player_a: str, player_b: str, p_a: float, p_b: float, odds_set1_a: float, odds_match_a: float, odds_over_games: float, over_line: float = 21.5, bankroll: float = 100.0):
    print(f"\n==================================================================")
    print(f"  ARGON-APEX v33: {player_a} vs {player_b}")
    print(f"==================================================================")
    
    match = calculate_match_markets(p_a, p_b, best_of=3)
    
    print(f"[*] Telemetría Pura:")
    print(f"    - Hold {player_a}: {match['hold_prob_a']*100:.2f}% (p={p_a})")
    print(f"    - Hold {player_b}: {match['hold_prob_b']*100:.2f}% (p={p_b})")
    print(f"    - Promedio Games Proyectados: {match['expected_total_games']:.2f}")
    
    # Evaluación contra líneas de TriunfoBet (Altenar)
    markets = [
        evaluate_market_value(f"Ganador Set 1 ({player_a})", match['p_set_1_a'], odds_set1_a, bankroll),
        evaluate_market_value(f"Ganador Partido ({player_a})", match['p_match_a'], odds_match_a, bankroll),
        evaluate_market_value(f"Over {over_line} Games", 0.582 if match['expected_total_games'] >= over_line else 0.45, odds_over_games, bankroll)
    ]
    
    print(f"\n[*] Matriz de Explotación de Cuotas Altenar (TriunfoBet):")
    print(f"{'MERCADO':<30} | {'CUOTA':<6} | {'P.REAL':<7} | {'P.CASA':<7} | {'+EV%':<7} | {'STAKE':<6} | {'SEÑAL'}")
    print("-" * 88)
    for m in markets:
        print(f"{m['market']:<30} | {m['soft_odds']:<6.2f} | {m['p_true']:<6.1f}% | {m['p_implied']:<6.1f}% | {m['ev_pct']:<6.1f}% | ${m['recommended_stake']:<5} | {m['signal']}")
    print("==================================================================\n")

if __name__ == "__main__":
    # Ejecución de prueba por defecto
    run_scout_analysis(
        player_a="Sacador Hard (Ej: M. Berrettini)",
        player_b="Restador Base (Ej: D. Schwartzman)",
        p_a=0.68,
        p_b=0.57,
        odds_set1_a=1.65,
        odds_match_a=1.52,
        odds_over_games=1.92,
        over_line=21.5,
        bankroll=100.0
    )
