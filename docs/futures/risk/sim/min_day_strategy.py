"""Investigación: "arriesgar casi todo el drawdown para ganar el día mínimo de 150 USD" en Topstep 50K.

Propuesta del operador (2026-11-27): stop ≈ todo el colchón hasta el MLL, objetivo = 150 USD netos (lo
justo para que el día cuente para el payout), una operación al día. Se mide contra las reglas
verificadas de Topstep (Combine → XFA Standard) y se compara con el perfil D de risk_sim.py.

Modelo: 10 MNQ (= 1 NQ en USD); coste 2,5 USD ida y vuelta por MNQ (25 USD por operación).
Objetivo bruto = 150 + 25 = 175 USD. Stop neto = colchón − 10 USD de margen (para no tocar el MLL).
Ventaja expresada en USD por operación sobre el resultado BRUTO: p = (stop_bruto + ventaja) /
(stop_bruto + 175). Sin ventaja (ventaja = 0) el juego es justo antes de costes.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

CFG = dict(target=3000.0, dd=2000.0, consistency=0.55, min_days=2, eval_fee=49.0, renew_days=21,
           activation=149.0, win_days=5, min_day=150.0, fraction=0.5, cap=2000.0, min_payout=125.0,
           split=0.90, payout_fee=30.0)
COST = 25.0
WIN_GROSS = 150.0 + COST
MARGIN = 10.0


def run(edge_usd: float, *, n: int, horizon: int, budget: float, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    nets, pays, ruins, first_cycle_ok, passes, bought = [], [], [], [], [], []
    for _ in range(n):
        day, fees, received, npay, accounts, passed_n = 0, CFG["eval_fee"], 0.0, 0, 1, 0
        ruined = False
        cycle1 = None
        while day < horizon:
            # Combine: balance relativo, MLL trailing EOD bloqueado en el inicio (0)
            bal, peak, thr, best, traded, since_fee = 0.0, 0.0, -CFG["dd"], 0.0, 0, 0
            ok = False
            while day < horizon:
                day += 1
                since_fee += 1
                if since_fee >= CFG["renew_days"]:
                    fees += CFG["eval_fee"]
                    since_fee = 0
                stop_net = (bal - thr) - MARGIN
                stop_gross = stop_net - COST
                p = min(0.999, (stop_gross + edge_usd) / (stop_gross + WIN_GROSS))
                if rng.random() < p:
                    bal += WIN_GROSS - COST
                    best = max(best, WIN_GROSS - COST)
                    traded += 1
                    peak = max(peak, bal)
                    thr = max(thr, min(peak - CFG["dd"], 0.0))
                    if bal >= max(CFG["target"], best / CFG["consistency"]) and traded >= CFG["min_days"]:
                        ok = True
                        break
                else:
                    break  # el stop deja la cuenta a 10 USD del MLL: se da por perdida
            if ok:
                passed_n += 1
                fees += CFG["activation"]
                # XFA: balance 0, MLL −2.000 trailing EOD, bloqueo en 0 al llegar a +2.000 o tras un payout
                bal, peak, thr, wins, since_pay = 0.0, 0.0, -CFG["dd"], 0, 0.0
                cycle_paid = False
                while day < horizon:
                    day += 1
                    stop_net = (bal - thr) - MARGIN
                    stop_gross = stop_net - COST
                    if stop_gross <= 0:
                        break
                    p = min(0.999, (stop_gross + edge_usd) / (stop_gross + WIN_GROSS))
                    if rng.random() < p:
                        bal += WIN_GROSS - COST
                        since_pay += WIN_GROSS - COST
                        wins += 1
                        peak = max(peak, bal)
                        thr = max(thr, min(peak - CFG["dd"], 0.0))
                        if wins >= CFG["win_days"] and since_pay > 0:
                            w = min(CFG["fraction"] * bal, CFG["cap"])
                            if w >= CFG["min_payout"]:
                                bal -= w
                                received += CFG["split"] * w - CFG["payout_fee"]
                                npay += 1
                                cycle_paid = True
                                thr = max(thr, 0.0)
                                wins, since_pay = 0, 0.0
                    else:
                        break
                if cycle1 is None:
                    cycle1 = cycle_paid
            if day >= horizon:
                break
            if budget + received - fees < CFG["eval_fee"]:
                ruined = True
                break
            fees += CFG["eval_fee"]
            accounts += 1
        nets.append(received - fees)
        pays.append(npay)
        ruins.append(ruined)
        passes.append(passed_n)
        bought.append(accounts)
        if cycle1 is not None:
            first_cycle_ok.append(cycle1)
    nets = np.array(nets)
    q = np.percentile(nets, [5, 25, 50, 75, 95])
    return {
        "edge_usd_per_trade": edge_usd,
        "p_win_combine_start": round((2000 - MARGIN - COST + edge_usd) / (2000 - MARGIN - COST + WIN_GROSS), 4),
        "ev": round(float(nets.mean()), 1), "se": round(float(nets.std(ddof=1) / np.sqrt(n)), 1),
        "p5": round(float(q[0])), "p25": round(float(q[1])), "median": round(float(q[2])),
        "p75": round(float(q[3])), "p95": round(float(q[4])),
        "p_net_pos": round(float((nets > 0).mean()), 3),
        "mean_payouts": round(float(np.mean(pays)), 2),
        "mean_combines_passed": round(float(np.mean(passes)), 2),
        "mean_accounts_bought": round(float(np.mean(bought)), 2),
        "p_first_xfa_gets_payout": round(float(np.mean(first_cycle_ok)), 3) if first_cycle_ok else None,
        "p_budget_ruin": round(float(np.mean(ruins)), 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--horizon", type=int, default=252)
    ap.add_argument("--budget", type=float, default=1500.0)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = [run(e, n=args.paths, horizon=args.horizon, budget=args.budget, seed=args.seed)
            for e in (0.0, 10.0, 20.0, 40.0, 65.0)]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"config": {**CFG, "cost_per_trade": COST, "win_gross": WIN_GROSS, "margin": MARGIN,
                              "horizon_sessions": args.horizon, "budget": args.budget, "paths": args.paths,
                              "seed": args.seed}, "rows": rows}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
