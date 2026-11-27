"""Simulación de investigación: valor esperado de una cuenta 50K de prop firm de futuros.

NO es el motor de producción (FUT-A, docs/futures/04_SPEC_PROP_EV.md). Es una herramienta de
análisis reproducible para el informe de docs/futures/research/propfirms_2026-11/.

Todo lo que no sale de una fuente oficial es un PARÁMETRO explícito (ventaja, costes por contrato,
excursión de las operaciones perdedoras). No hay ninguna ventaja validada en TradingLab: los
escenarios con ventaja > 0 son HIPOTÉTICOS y la fila "sin ventaja" es la línea base.

Modelo
------
* 1 operación por día de sesión con bracket fijo: stop S puntos, objetivo RR·S, k contratos.
* Gana con probabilidad p; p se elige para que la expectativa NETA por operación sea mu_R (en R).
* Trayectoria intradía: ganadora 0 → +objetivo; perdedora 0 → +u·objetivo → −stop con u ~ U(0,1)
  (pico antes del valle: conservador para el trailing intradía).
* Evaluación → (activación) → financiada → payouts; al perder una cuenta se compra otra evaluación
  mientras quede presupuesto. Horizonte en días de sesión (21 ≈ 1 mes).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class Program:
    name: str
    target: float                 # objetivo de la evaluación (USD)
    dd: float                     # drawdown máximo (USD)
    dd_mode: str                  # "eod" | "intraday" | "static"
    eval_lock_at_start: bool      # el trailing se bloquea en el balance inicial
    consistency: float | None     # mejor día < c · objetivo (si se supera, sube el objetivo)
    min_days: int
    eval_fee: float               # cargo al empezar cada intento
    renew_fee: float              # cargo cada `renew_days` mientras dura la evaluación (0 = pago único)
    renew_days: int
    activation: float
    funded_dd: float
    funded_dd_mode: str
    funded_lock_level: float      # nivel donde se bloquea el trailing en la financiada (USD sobre 0)
    payout_win_days: int          # días ganadores necesarios
    payout_min_day: float         # beneficio mínimo de un día ganador
    payout_fraction: float        # fracción del balance retirable
    payout_cap: float
    payout_min: float
    split: float
    lock_after_payout: bool


TOPSTEP_50K = Program(
    name="Topstep 50K Combine → XFA Standard (verificado 2026-11-27)",
    target=3000, dd=2000, dd_mode="eod", eval_lock_at_start=True, consistency=0.55, min_days=2,
    eval_fee=49, renew_fee=49, renew_days=21, activation=149,
    funded_dd=2000, funded_dd_mode="eod", funded_lock_level=0.0,
    payout_win_days=5, payout_min_day=150, payout_fraction=0.5, payout_cap=2000, payout_min=125,
    split=0.90, lock_after_payout=True,
)

PROGRAMS = {"topstep_50k": TOPSTEP_50K}

PROFILES = {
    # nombre: (contratos MNQ equivalentes, stop en puntos, RR)
    "conservador": (2, 25.0, 1.5),   # riesgo 2 · 25 · 2 = 100 USD
    "moderado": (5, 25.0, 1.5),      # riesgo 250 USD
    "agresivo": (10, 25.0, 1.5),     # 1 NQ = 10 MNQ: riesgo 500 USD
}

MNQ_POINT = 2.0  # USD por punto y contrato MNQ (0,25 pt = 0,50 USD)


def simulate(program: Program, contracts: int, stop_pts: float, rr: float, mu_r: float, *,
             cost_rt: float, horizon: int, budget: float, n_paths: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    risk = contracts * stop_pts * MNQ_POINT
    win_gross = rr * risk
    cost = contracts * cost_rt
    # expectativa neta mu_r·risk = p·(win−cost) − (1−p)·(risk+cost)  →  p
    p = (mu_r * risk + risk + cost) / (win_gross + risk)
    if not 0.0 < p < 1.0:
        raise ValueError(f"p fuera de rango: {p}")
    net_cash = np.zeros(n_paths)          # payouts recibidos − tarifas (USD)
    spent = np.zeros(n_paths)
    payouts = np.zeros(n_paths, dtype=int)
    passed_first = np.zeros(n_paths, dtype=bool)
    attempts = np.zeros(n_paths, dtype=int)
    ruined = np.zeros(n_paths, dtype=bool)
    first_payout_day = np.full(n_paths, -1)
    for i in range(n_paths):
        day = 0
        cash = 0.0
        out = 0.0
        while day < horizon:
            if out - max(cash, 0.0) + program.eval_fee > budget:
                ruined[i] = True
                break
            attempts[i] += 1
            cash -= program.eval_fee
            out += program.eval_fee
            bal, peak, best, traded, since_fee = 0.0, 0.0, 0.0, 0, 0
            thr = -program.dd
            passed = False
            while day < horizon:
                day += 1
                since_fee += 1
                if program.renew_fee and since_fee >= program.renew_days:
                    cash -= program.renew_fee
                    out += program.renew_fee
                    since_fee = 0
                win = rng.random() < p
                pnl = (win_gross - cost) if win else (-risk - cost)
                marks = (bal + pnl,) if win else (bal + rng.random() * win_gross, bal - risk - cost)
                broke = False
                for m in marks:
                    if program.dd_mode == "intraday":
                        peak = max(peak, m)
                        thr = max(thr, min(peak - program.dd, 0.0 if program.eval_lock_at_start else 1e18))
                    if m <= thr:
                        broke = True
                        break
                if broke:
                    break
                bal += pnl
                traded += 1
                best = max(best, pnl)
                if program.dd_mode == "eod":
                    peak = max(peak, bal)
                    thr = max(thr, min(peak - program.dd, 0.0 if program.eval_lock_at_start else 1e18))
                need = program.target
                if program.consistency:
                    need = max(need, best / program.consistency)
                if bal >= need and traded >= program.min_days:
                    passed = True
                    break
            if not passed:
                continue
            if attempts[i] == 1:
                passed_first[i] = True
            cash -= program.activation
            out += program.activation
            # financiada
            bal, peak, thr = 0.0, 0.0, -program.funded_dd
            wins, since_payout = 0, 0.0
            while day < horizon:
                day += 1
                win = rng.random() < p
                pnl = (win_gross - cost) if win else (-risk - cost)
                marks = (bal + pnl,) if win else (bal + rng.random() * win_gross, bal - risk - cost)
                if any(m <= thr for m in marks):
                    break
                bal += pnl
                since_payout += pnl
                if pnl >= program.payout_min_day:
                    wins += 1
                peak = max(peak, bal)
                thr = max(thr, min(peak - program.funded_dd, program.funded_lock_level))
                if wins >= program.payout_win_days and since_payout > 0:
                    w = min(program.payout_fraction * bal, program.payout_cap)
                    if w >= program.payout_min:
                        bal -= w
                        cash += program.split * w
                        payouts[i] += 1
                        if first_payout_day[i] < 0:
                            first_payout_day[i] = day
                        wins, since_payout = 0, 0.0
                        if program.lock_after_payout:
                            thr = max(thr, program.funded_lock_level)
        net_cash[i] = cash
        spent[i] = out
    se = net_cash.std(ddof=1) / np.sqrt(n_paths)
    got = first_payout_day >= 0
    return {
        "p_win": round(p, 4), "risk_usd": risk, "cost_per_trade": cost,
        "ev_net": round(float(net_cash.mean()), 1), "ev_se": round(float(se), 1),
        "ev_monthly": round(float(net_cash.mean()) * 21 / horizon, 1),
        "p_net_positive": round(float((net_cash > 0).mean()), 4),
        "p_pass_first_attempt": round(float(passed_first.mean()), 4),
        "mean_attempts": round(float(attempts.mean()), 2),
        "p_at_least_one_payout": round(float(got.mean()), 4),
        "mean_payouts": round(float(payouts.mean()), 2),
        "median_day_first_payout": int(np.median(first_payout_day[got])) if got.any() else None,
        "mean_fees_paid": round(float(spent.mean()), 1),
        "p_budget_ruin": round(float(ruined.mean()), 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", default="topstep_50k", choices=sorted(PROGRAMS))
    ap.add_argument("--horizon", type=int, default=126, help="días de sesión (126 ≈ 6 meses)")
    ap.add_argument("--budget", type=float, default=1000.0, help="presupuesto de tarifas (USD)")
    ap.add_argument("--cost-rt-mnq", type=float, default=2.5,
                    help="coste ida y vuelta por contrato MNQ: 0,75/lado (operador) + 1 tick/lado")
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    program = PROGRAMS[args.program]
    rows = []
    for profile, (k, stop, rr) in PROFILES.items():
        for label, mu in (("sin_ventaja_bruta", None), ("conservador_+0.05R", 0.05),
                          ("base_+0.10R", 0.10), ("optimista_+0.20R", 0.20)):
            cost_r = k * args.cost_rt_mnq / (k * stop * MNQ_POINT)
            mu_r = -cost_r if mu is None else mu
            res = simulate(program, k, stop, rr, mu_r, cost_rt=args.cost_rt_mnq, horizon=args.horizon,
                           budget=args.budget, n_paths=args.paths, seed=args.seed)
            rows.append({"profile": profile, "scenario": label, "mu_net_R": round(mu_r, 4), **res})
    print(json.dumps({"program": asdict(program), "horizon_days": args.horizon, "budget": args.budget,
                      "cost_rt_mnq": args.cost_rt_mnq, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
