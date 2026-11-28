"""Simulación de investigación: asignación de riesgo y payouts netos en Topstep 50K (FUT-RISK).

NO es el motor de producción. Herramienta reproducible para docs/futures/risk/. Vectorizada sobre
caminos (numpy). Ventajas HIPOTÉTICAS: TradingLab no tiene ninguna estrategia validada.

Modelo por camino (un "proyecto" con un presupuesto de tarifas):
* 1 operación MNQ por día de sesión: stop STOP_PTS, objetivo RR·STOP_PTS, k contratos enteros.
* Gana con probabilidad p (fija o con regímenes persistentes). p sale de la expectativa NETA mu (R).
* Ganadoras con excursión adversa U(0,1)·stop antes del objetivo (MLL vigilado en tiempo real).
* Evaluación (Combine) → activación → XFA → payouts → al perder la cuenta, nueva evaluación si queda
  presupuesto (presupuesto + payouts recibidos − tarifas ≥ precio de la evaluación).
* Payout: solicitado el día d, aprobado (supuesto: siempre, si cumple las reglas), recibido el día
  d + LAG con la comisión de transferencia descontada.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

MNQ_PT = 2.0
STOP_PTS = 25.0
RR = 1.5
COST_RT = 2.5          # USD ida y vuelta por MNQ: 0,75/lado (operador) + 1 tick/lado (supuesto)

TOPSTEP = dict(        # verificado 2026-11-27 salvo lo marcado
    target=3000.0, dd=2000.0, consistency=0.55, min_days=2,
    eval_fee=49.0, renew_fee=49.0, renew_days=21, activation=149.0, eval_max_micros=50,
    funded_dd=2000.0, funded_max_micros=20,      # 20 = SUPUESTO (ejemplo "2-lot" del Scaling Plan)
    win_days=5, min_day=150.0, fraction=0.5, cap=2000.0, min_payout=125.0, split=0.90,
    payout_fee=30.0, payout_lag=10,               # transferencia internacional: 30 USD, 5-10 días hábiles + 1-3 de aprobación
)

FIXED = {"A_50": 50.0, "B_100": 100.0, "C_250": 250.0, "D_500": 500.0, "E_1000": 1000.0}
EDGES = {"sin_ventaja": None, "debil_+0.03R": 0.03, "moderada_+0.08R": 0.08,
         "solida_+0.15R": 0.15, "elevada_+0.25R": 0.25}
CHECKPOINTS = (126, 252, 504)   # 6, 12 y 24 meses de sesión


def p_from_mu(mu: float) -> float:
    unit = STOP_PTS * MNQ_PT
    return (mu * unit + unit + COST_RT) / (RR * unit + unit)


def kelly_fraction(mu: float) -> float:
    """Fracción del colchón que se pierde en un stop (Kelly binario con costes)."""
    p = p_from_mu(mu)
    unit = STOP_PTS * MNQ_PT
    win, loss = (RR * unit - COST_RT) / unit, (unit + COST_RT) / unit
    return max(0.0, p - (1 - p) * loss / win)


def run(policy: dict, mu: float, *, n: int, seed: int, budget: float, regimes: bool = False,
        rr: float = RR, edge_usd: float | None = None) -> dict:
    """Simula un proyecto. Por defecto la ventaja es `mu` en R con RR fijo (resultados de 01 §4).

    Con `edge_usd` la ventaja es NETA en USD por operación y `rr` es la relación objetivo/stop
    (ratio negativo si rr < 1): lo usan los módulos MOD-NR y MOD-PR (`structures_sweep.py`).
    """
    cfg = TOPSTEP
    rng = np.random.default_rng(seed)
    horizon = max(CHECKPOINTS)
    p0 = p_from_mu(mu)
    unit = STOP_PTS * MNQ_PT
    phase = np.zeros(n, dtype=np.int8)                  # 0 evaluación, 1 financiada, 2 sin presupuesto
    bal = np.zeros(n)
    peak = np.zeros(n)
    thr = np.full(n, -cfg["dd"])
    best = np.zeros(n)
    traded = np.zeros(n, dtype=int)
    since_fee = np.zeros(n, dtype=int)
    wins = np.zeros(n, dtype=int)
    since_pay = np.zeros(n)
    fees = np.full(n, cfg["eval_fee"])
    bought = np.ones(n, dtype=int)
    lost_eval = np.zeros(n, dtype=int)
    lost_funded = np.zeros(n, dtype=int)
    passed = np.zeros(n, dtype=int)
    max_pay = 64
    pay_day = np.full((n, max_pay), 10**9)
    pay_net = np.zeros((n, max_pay))
    n_pay = np.zeros(n, dtype=int)
    ruin_day = np.full(n, 10**9)
    max_out = np.full(n, cfg["eval_fee"])
    good = rng.random(n) < 0.5
    snaps = {}
    idx = np.arange(n)
    for day in range(1, horizon + 1):
        active = phase < 2
        funded = phase == 1
        cushion = np.maximum(bal - thr, 0.0)
        if policy["kind"] == "fixed":
            risk_t = np.full(n, policy["risk"])
        else:
            risk_t = np.minimum(policy["rmax"], policy["kappa"] * cushion)
        k = np.floor(risk_t / unit + 1e-9).astype(int)
        if policy["kind"] != "fixed":
            k = np.maximum(k, 1)  # tamaño mínimo: 1 MNQ mientras la cuenta esté viva (sin cuentas "zombi")
        k = np.minimum(k, np.where(funded, cfg["funded_max_micros"], cfg["eval_max_micros"]))
        k = np.where(active, k, 0)
        risk_usd = k * unit
        cost = k * COST_RT
        if edge_usd is not None:
            # ventaja NETA fija en USD por operación: p = (E + L) / (W + L), con W y L netos
            w_net = rr * risk_usd - cost
            l_net = risk_usd + cost
            p0 = np.clip((edge_usd + l_net) / np.maximum(w_net + l_net, 1e-9), 0.0, 0.999)
        if regimes:
            switch = rng.random(n) < 0.05
            good = np.where(switch, ~good, good)
            p = np.clip(np.where(good, p0 + 0.08, p0 - 0.08), 0.01, 0.99)
        else:
            p = p0
        win = rng.random(n) < p
        pnl = np.where(win, rr * risk_usd - cost, -risk_usd - cost)
        worst = np.where(win, -rng.random(n) * risk_usd, pnl)
        trade = k > 0
        breach = trade & (bal + worst <= thr)
        ok = trade & ~breach
        bal = np.where(ok, bal + pnl, bal)
        traded = traded + ok
        best = np.where(ok & (phase == 0), np.maximum(best, pnl), best)
        peak = np.maximum(peak, bal)
        thr = np.maximum(thr, np.minimum(peak - np.where(funded, cfg["funded_dd"], cfg["dd"]), 0.0))
        # cuota mensual de la evaluación
        in_eval = active & (phase == 0)
        since_fee = np.where(in_eval, since_fee + 1, since_fee)
        renew = in_eval & (since_fee >= cfg["renew_days"]) & ~breach
        fees = fees + renew * cfg["renew_fee"]
        since_fee = np.where(renew, 0, since_fee)
        # aprobado
        need = np.maximum(cfg["target"], best / cfg["consistency"])
        passing = in_eval & ok & (bal >= need) & (traded >= cfg["min_days"])
        # payouts
        wins = np.where(funded & ok & (pnl >= cfg["min_day"]), wins + 1, wins)
        since_pay = np.where(funded & ok, since_pay + pnl, since_pay)
        w = np.minimum(cfg["fraction"] * bal, cfg["cap"])
        pay = funded & ok & (wins >= cfg["win_days"]) & (since_pay > 0) & (w >= cfg["min_payout"]) & (n_pay < max_pay)
        if pay.any():
            rows = idx[pay]
            pay_day[rows, n_pay[rows]] = day + cfg["payout_lag"]
            pay_net[rows, n_pay[rows]] = cfg["split"] * w[rows] - cfg["payout_fee"]
            n_pay = n_pay + pay
            bal = np.where(pay, bal - w, bal)
            thr = np.where(pay, np.maximum(thr, 0.0), thr)
            wins = np.where(pay, 0, wins)
            since_pay = np.where(pay, 0.0, since_pay)
        # transiciones
        if passing.any():
            fees = fees + passing * cfg["activation"]
            passed = passed + passing
            phase = np.where(passing, 1, phase)
            for arr in (bal, peak, since_pay):
                arr[passing] = 0.0
            thr[passing] = -cfg["funded_dd"]
            wins[passing] = 0
        lost_eval = lost_eval + (breach & (phase == 0))
        lost_funded = lost_funded + (breach & (phase == 1))
        received_now = (pay_net * (pay_day <= day)).sum(axis=1)
        if breach.any():
            can = breach & (budget + received_now - fees >= cfg["eval_fee"])
            stop = breach & ~can
            phase = np.where(can, 0, phase)
            phase = np.where(stop, 2, phase)
            ruin_day = np.where(stop, day, ruin_day)
            fees = fees + can * cfg["eval_fee"]
            bought = bought + can
            for arr in (bal, peak, best, since_pay):
                arr[breach] = 0.0
            thr[breach] = -cfg["dd"]
            traded[breach] = 0
            since_fee[breach] = 0
            wins[breach] = 0
        max_out = np.maximum(max_out, fees - received_now)
        if day in CHECKPOINTS:
            requested = (pay_day - cfg["payout_lag"] <= day).sum(axis=1)
            received = (pay_day <= day).sum(axis=1)
            net = received_now - fees
            q = np.percentile(net, [5, 25, 50, 75, 95])
            snaps[day] = {
                "ev": round(float(net.mean()), 1), "se": round(float(net.std(ddof=1) / np.sqrt(n)), 1),
                "p5": round(float(q[0]), 0), "p25": round(float(q[1]), 0), "median": round(float(q[2]), 0),
                "p75": round(float(q[3]), 0), "p95": round(float(q[4]), 0),
                "p_net_pos": round(float((net > 0).mean()), 3),
                "p_one_payout_received": round(float((received > 0).mean()), 3),
                "payouts_requested": round(float(requested.mean()), 2),
                "payouts_received": round(float(received.mean()), 2),
                "fees": round(float(fees.mean()), 0),
                "accounts_bought": round(float(bought.mean()), 2),
                "evals_passed": round(float(passed.mean()), 2),
                "evals_lost": round(float(lost_eval.mean()), 2),
                "funded_lost": round(float(lost_funded.mean()), 2),
                "p_budget_ruin": round(float((ruin_day <= day).mean()), 3),
                "capital_required_p95": round(float(np.percentile(max_out, 95)), 0),
            }
    return {"p_win": round(float(np.mean(p0)), 4), "checkpoints": snaps, "net_24m": (received_now - fees)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=float, default=1500.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    policies = {name: {"kind": "fixed", "risk": r} for name, r in FIXED.items()}
    policies["F_adaptativo"] = {"kind": "cushion", "rmax": 500.0, "kappa": 0.25}
    rows, multi = [], []
    for edge_name, mu_set in EDGES.items():
        mu = -COST_RT / (STOP_PTS * MNQ_PT) if mu_set is None else mu_set
        kf = kelly_fraction(mu)
        pol = dict(policies)
        if kf > 0:
            for label, frac in (("K_full", 1.0), ("K_half", 0.5), ("K_quarter", 0.25)):
                pol[label] = {"kind": "cushion", "rmax": 1000.0, "kappa": kf * frac}
        for pname, policy in pol.items():
            res = run(policy, mu, n=args.paths, seed=args.seed, budget=args.budget)
            rows.append({"edge": edge_name, "mu_net_R": round(mu, 4), "kelly_r": round(kf, 4),
                         "policy": pname, "p_win": res["p_win"], **{f"m{d // 21}": v for d, v in res["checkpoints"].items()}})
            if pname in ("C_250", "D_500") and edge_name in ("sin_ventaja", "moderada_+0.08R"):
                x = res["net_24m"]
                r2 = np.random.default_rng(args.seed + 1)
                indep = x + x[r2.permutation(len(x))] + x[r2.permutation(len(x))]
                corr = 3 * x
                for label, arr in (("3_correladas", corr), ("3_independientes", indep)):
                    multi.append({"edge": edge_name, "policy": pname, "cuentas": label,
                                  "ev": round(float(arr.mean()), 0), "median": round(float(np.median(arr)), 0),
                                  "p5": round(float(np.percentile(arr, 5)), 0),
                                  "p_net_pos": round(float((arr > 0).mean()), 3)})
    clustering = []
    mu = 0.08
    for pname, policy in policies.items():
        base = run(policy, mu, n=args.paths, seed=args.seed, budget=args.budget)["checkpoints"][252]
        reg = run(policy, mu, n=args.paths, seed=args.seed, budget=args.budget, regimes=True)["checkpoints"][252]
        clustering.append({"policy": pname, "iid_ev_12m": base["ev"], "regimes_ev_12m": reg["ev"],
                           "iid_median": base["median"], "regimes_median": reg["median"],
                           "iid_p_net_pos": base["p_net_pos"], "regimes_p_net_pos": reg["p_net_pos"]})
    out = {"config": {"program": "Topstep 50K Combine → XFA Standard", "rules": TOPSTEP, "stop_pts": STOP_PTS,
                      "rr": RR, "cost_rt_mnq": COST_RT, "budget": args.budget, "paths": args.paths,
                      "seed": args.seed, "checkpoints_sessions": CHECKPOINTS},
           "rows": rows, "multi_account": multi, "clustering_moderate_12m": clustering}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
