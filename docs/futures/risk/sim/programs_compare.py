"""Comparación de programas 50K (Topstep, MFF Rapid, Lucid Flex) con la misma estrategia hipotética.

Herramienta de INVESTIGACIÓN (no es el motor FUT-A). Ventajas HIPOTÉTICAS: no hay estrategia validada.
Misma ventaja BRUTA en R para los tres programas; cada uno descuenta SUS comisiones verificadas
(fichas de docs/futures/research/propfirms_2026-11/) y 1 tick de slippage por lado.

Modelo por camino (un proyecto con presupuesto de tarifas), 1 operación MNQ por sesión, stop de 25 puntos,
objetivo 1,5 R; números aleatorios comunes entre programas (misma semilla). Reglas de cada programa en
PROGRAMS; los supuestos llevan la marca SUPUESTO en el comentario.

Uso: python -I docs/futures/risk/sim/programs_compare.py --out docs/futures/risk/sim/programs_compare.json
"""

from __future__ import annotations

import argparse
import json

import numpy as np

MNQ_PT = 2.0
STOP_PTS = 25.0
UNIT = STOP_PTS * MNQ_PT          # riesgo por MNQ: 50 USD
RR = 1.5
SLIP_RT = 1.0                     # 1 tick por lado en MNQ = 2 × 0,50 USD
CHECKPOINTS = (126, 252, 504)     # 6, 12 y 24 meses de sesión
EDGES_GROSS_R = {"sin_ventaja_bruta": 0.0, "debil_+0.08R": 0.08, "moderada_+0.13R": 0.13,
                 "solida_+0.20R": 0.20, "elevada_+0.30R": 0.30}
RISKS = (250.0, 500.0, 1000.0)
LUCID_FEES = (75.0, 125.0, 175.0, 225.0)   # precio Sin datos: barrido para el precio de equilibrio

PROGRAMS = {
    "topstep_50k": dict(
        target=3000.0, dd=2000.0, eval_lock=0.0, consistency=0.55, min_days=2, eval_max=50,
        fee_model="subscription", eval_fee=49.0, renew_days=21, activation=149.0,
        f_mode="trailing_eod", f_dd=2000.0, f_lock=0.0, f_tiers=((0.0, 20),),   # 20 = SUPUESTO (escalado)
        elig="winning_days", win_days=5, min_day=150.0, fraction=0.5, cap=2000.0, buffer=0.0,
        min_payout=125.0, split=0.90, payout_fee=30.0, lag=10, max_payouts=0, lock_on_payout=0.0,
        cost_rt=1.22 + SLIP_RT),
    "mff_rapid_50k": dict(
        target=3000.0, dd=2000.0, eval_lock=0.0, consistency=0.50, min_days=2, eval_max=50,  # eval_lock SUPUESTO
        fee_model="one_time", eval_fee=209.0, renew_days=0, activation=0.0,
        f_mode="trailing_intraday", f_dd=2000.0, f_lock=100.0, f_tiers=((0.0, 50),),  # lock +100: discrepancia
        elig="buffer", win_days=0, min_day=0.0, fraction=1.0, cap=1e12, buffer=2100.0,   # sin tope publicado
        min_payout=500.0, split=0.90, payout_fee=0.0, lag=2, max_payouts=0, lock_on_payout=-1e12,  # fee/lag SUPUESTO
        cost_rt=1.90 + SLIP_RT),
    "lucid_flex_50k": dict(
        target=3000.0, dd=2000.0, eval_lock=100.0, consistency=0.40, min_days=0, eval_max=40,
        fee_model="one_time", eval_fee=125.0, renew_days=0, activation=0.0,            # eval_fee: se barre
        f_mode="trailing_eod", f_dd=2000.0, f_lock=100.0, f_tiers=((0.0, 20), (1000.0, 30), (2000.0, 40)),
        elig="winning_days", win_days=5, min_day=150.0, fraction=0.5, cap=2000.0, buffer=0.0,
        min_payout=500.0, split=0.90, payout_fee=0.0, lag=3, max_payouts=5, lock_on_payout=100.0,  # fee/lag SUPUESTO
        cost_rt=1.00 + SLIP_RT),
}


def max_micros(cfg: dict, bal: np.ndarray, funded: np.ndarray) -> np.ndarray:
    tier = np.full_like(bal, cfg["f_tiers"][0][1])   # el primer escalón vale también con beneficio < 0
    for min_profit, cap in cfg["f_tiers"]:
        tier = np.where(bal >= min_profit, cap, tier)
    return np.where(funded, tier, cfg["eval_max"]).astype(int)


def run(cfg: dict, mu_gross: float, risk: float, *, n: int, seed: int, budget: float) -> dict:
    rng = np.random.default_rng(seed)
    horizon = max(CHECKPOINTS)
    p = (mu_gross + 1.0) / (RR + 1.0)
    phase = np.zeros(n, dtype=np.int8)        # 0 evaluación, 1 financiada, 2 sin presupuesto
    bal = np.zeros(n)
    peak = np.zeros(n)
    thr = np.full(n, -cfg["dd"])
    best = np.zeros(n)
    traded = np.zeros(n, dtype=int)
    since_fee = np.zeros(n, dtype=int)
    wins = np.zeros(n, dtype=int)
    since_pay = np.zeros(n)
    n_pay_acc = np.zeros(n, dtype=int)
    fees = np.full(n, cfg["eval_fee"])
    bought = np.ones(n, dtype=int)
    graduated = np.zeros(n, dtype=int)
    lost_eval = np.zeros(n, dtype=int)
    lost_funded = np.zeros(n, dtype=int)
    max_pay = 400
    pay_day = np.full((n, max_pay), 10**9)
    pay_net = np.zeros((n, max_pay))
    n_pay = np.zeros(n, dtype=int)
    ruin_day = np.full(n, 10**9)
    idx = np.arange(n)
    snaps = {}
    k_pol = int(np.floor(risk / UNIT + 1e-9))
    for day in range(1, horizon + 1):
        active = phase < 2
        funded = phase == 1
        k = np.minimum(k_pol, max_micros(cfg, bal, funded))
        k = np.where(active, k, 0)
        risk_usd = k * UNIT
        cost = k * cfg["cost_rt"]
        win = rng.random(n) < p
        pnl = np.where(win, RR * risk_usd - cost, -risk_usd - cost)
        adverse = rng.random(n)
        favorable = rng.random(n)
        worst = np.where(win, -adverse * risk_usd, pnl)
        trade = k > 0
        intraday = funded & (cfg["f_mode"] == "trailing_intraday")
        # trailing intradía: en las perdedoras, el máximo favorable (SUPUESTO U(0,1)·riesgo) sube el umbral antes del stop
        peak_in = np.where(win, bal, bal + cfg.get("mfe_losers", 1.0) * favorable * risk_usd)
        thr_in = np.where(intraday, np.maximum(thr, np.minimum(peak_in - cfg["f_dd"], cfg["f_lock"])), thr)
        breach = trade & (bal + worst <= thr_in)
        ok = trade & ~breach
        bal = np.where(ok, bal + pnl, bal)
        traded = traded + ok
        best = np.where(ok & (phase == 0), np.maximum(best, pnl), best)
        peak = np.maximum(peak, bal)
        dd = np.where(funded, cfg["f_dd"], cfg["dd"])
        lock = np.where(funded, cfg["f_lock"], cfg["eval_lock"])
        thr = np.maximum(thr_in, np.minimum(peak - dd, lock))
        in_eval = active & (phase == 0)
        if cfg["fee_model"] == "subscription":
            since_fee = np.where(in_eval, since_fee + 1, since_fee)
            renew = in_eval & (since_fee >= cfg["renew_days"]) & ~breach
            fees = fees + renew * cfg["eval_fee"]
            since_fee = np.where(renew, 0, since_fee)
        need = np.maximum(cfg["target"], best / cfg["consistency"])
        passing = in_eval & ok & (bal >= need) & (traded >= cfg["min_days"])
        # payouts
        if cfg["elig"] == "buffer":
            w = bal - cfg["buffer"]
            pay = funded & ok & (w >= cfg["min_payout"])
        else:
            wins = np.where(funded & ok & (pnl >= cfg["min_day"]), wins + 1, wins)
            since_pay = np.where(funded & ok, since_pay + pnl, since_pay)
            w = np.minimum(cfg["fraction"] * bal, cfg["cap"])
            pay = funded & ok & (wins >= cfg["win_days"]) & (since_pay > 0) & (w >= cfg["min_payout"])
        pay = pay & (n_pay < max_pay)
        if pay.any():
            rows = idx[pay]
            pay_day[rows, n_pay[rows]] = day + cfg["lag"]
            pay_net[rows, n_pay[rows]] = cfg["split"] * w[rows] - cfg["payout_fee"]
            n_pay = n_pay + pay
            n_pay_acc = n_pay_acc + pay
            bal = np.where(pay, bal - w, bal)
            thr = np.where(pay, np.maximum(thr, cfg["lock_on_payout"]), thr)
            wins = np.where(pay, 0, wins)
            since_pay = np.where(pay, 0.0, since_pay)
        # cuenta que llega al máximo de payouts: pasa a Live (fuera del modelo) y se compra otra evaluación
        grad = funded & (cfg["max_payouts"] > 0) & (n_pay_acc >= max(cfg["max_payouts"], 1))
        if passing.any():
            fees = fees + passing * cfg["activation"]
            phase = np.where(passing, 1, phase)
            for arr in (bal, peak, since_pay):
                arr[passing] = 0.0
            thr[passing] = -cfg["f_dd"]
            wins[passing] = 0
            n_pay_acc[passing] = 0
        lost_eval = lost_eval + (breach & (phase == 0))
        lost_funded = lost_funded + (breach & (phase == 1))
        graduated = graduated + grad
        received_now = (pay_net * (pay_day <= day)).sum(axis=1)
        restart = breach | grad
        if restart.any():
            can = restart & (budget + received_now - fees >= cfg["eval_fee"])
            stop = restart & ~can
            phase = np.where(can, 0, phase)
            phase = np.where(stop, 2, phase)
            ruin_day = np.where(stop & breach, day, ruin_day)
            fees = fees + can * cfg["eval_fee"]
            bought = bought + can
            for arr in (bal, peak, best, since_pay):
                arr[restart] = 0.0
            thr[restart] = -cfg["dd"]
            traded[restart] = 0
            since_fee[restart] = 0
            wins[restart] = 0
            n_pay_acc[restart] = 0
        if day in CHECKPOINTS:
            received = (pay_day <= day).sum(axis=1)
            net = received_now - fees
            q = np.percentile(net, [5, 25, 50, 75, 95])
            snaps[day] = {
                "ev": round(float(net.mean()), 1), "se": round(float(net.std(ddof=1) / np.sqrt(n)), 1),
                "p5": round(float(q[0]), 0), "p25": round(float(q[1]), 0), "median": round(float(q[2]), 0),
                "p75": round(float(q[3]), 0), "p95": round(float(q[4]), 0),
                "p_net_pos": round(float((net > 0).mean()), 3),
                "p_one_payout_received": round(float((received > 0).mean()), 3),
                "payouts_received": round(float(received.mean()), 2),
                "fees": round(float(fees.mean()), 0),
                "accounts_bought": round(float(bought.mean()), 2),
                "evals_lost": round(float(lost_eval.mean()), 2),
                "funded_lost": round(float(lost_funded.mean()), 2),
                "graduated_to_live": round(float(graduated.mean()), 2),
                "p_budget_ruin": round(float((ruin_day <= day).mean()), 3),
            }
    return {"p_win": round(p, 4), "mu_net_r": round(mu_gross - cfg["cost_rt"] / UNIT, 4), "checkpoints": snaps}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--budget", type=float, default=1500.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = []
    for name, base in PROGRAMS.items():
        fees = LUCID_FEES if name.startswith("lucid") else (base["eval_fee"],)
        for fee in fees:
            cfg = dict(base, eval_fee=fee)
            for edge_name, mu in EDGES_GROSS_R.items():
                for risk in RISKS:
                    res = run(cfg, mu, risk, n=args.paths, seed=args.seed, budget=args.budget)
                    rows.append({"program": name, "eval_fee": fee, "edge": edge_name, "mu_gross_r": mu,
                                 "risk_usd": risk, **res})
    out = {"config": {"paths": args.paths, "seed": args.seed, "budget": args.budget, "stop_pts": STOP_PTS,
                      "rr": RR, "slippage_rt_mnq": SLIP_RT, "programs": PROGRAMS}, "rows": rows}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
