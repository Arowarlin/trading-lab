"""Módulos de ratio negativo y positivo sobre el motor real (risk/modulos/MOD-NR y MOD-PR) — FUT-M1…M3.

Una estructura = riesgo por operación (USD), ratio objetivo/stop (RR) y ventaja NETA en USD por operación.
* ``structure_pool``: pool sintético (HIPOTÉTICO) con esa estructura; p = (E + L)/(W + L) con W y L netos.
* ``structure_checks``: reglas de la firma que la estructura incumple (día ganador mínimo, microscalping,
  stop mayor que el colchón). Un ratio no crea ventaja: solo cambia cómo se reparte (parada opcional).
* ``frontier``: la mejor estructura para cada tolerancia de ruina con la regla de decisión de risk/01 §5.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from .allocate import select
from .compat import MICROSCALPING_S
from .paths import DayPath
from .rules import Program

STOP_PTS = 25.0
MNQ_PT = 2.0


def structure_pool(*, risk_usd: float, rr: float, edge_net_usd: float, cost_rt_per_contract: float, n_days: int,
                   seed: int, start: date = date(2027, 1, 4)) -> tuple[list[DayPath], dict]:
    """Pool de 1 operación diaria con ``k`` MNQ (stop de 25 pt). Devuelve (pool, estructura)."""
    k = int(np.floor(risk_usd / (STOP_PTS * MNQ_PT) + 1e-9))
    if k < 1:
        raise ValueError("el riesgo no llega a 1 MNQ")
    risk = k * STOP_PTS * MNQ_PT
    cost = k * cost_rt_per_contract
    w_net, l_net = rr * risk - cost, risk + cost
    p = (edge_net_usd + l_net) / (w_net + l_net)
    if not 0 < p < 1:
        raise ValueError(f"p fuera de (0, 1): {p:.3f}")
    rng = np.random.default_rng(seed)
    pool = []
    for i in range(n_days):
        u = float(rng.random())
        win = rng.random() < p
        marks = [0.0, -u * risk, w_net] if win else [0.0, u * risk * rr, -l_net]
        pool.append(DayPath(start + timedelta(days=i), np.asarray(marks), 1, (2,), marks[-1] + cost, cost, risk,
                            frozenset(), "synthetic"))
    return pool, {"contracts": k, "risk_usd": risk, "rr": rr, "win_net": w_net, "loss_net": l_net, "p_win": p,
                  "module": "MOD-NR" if rr < 1 else "MOD-PR"}


def structure_checks(program: Program, structure: dict, *, firm_id: str, median_hold_s: float,
                     cushion_usd: float | None = None) -> list[str]:
    """Reglas de la firma que la estructura incumple (lista vacía = válida)."""
    out = []
    funded = program.phases.funded
    if funded is not None and funded.payout.eligibility.template == "winning_days":
        min_day = funded.payout.eligibility.min_day_profit or 0.0
        if structure["win_net"] < min_day:
            out.append(f"una ganadora ({structure['win_net']:.2f}) no llega al día mínimo de {min_day:g}: no hay payout")
    limit = MICROSCALPING_S.get(firm_id)
    if limit is not None and median_hold_s < 3 * limit:
        out.append(f"duración mediana {median_hold_s:g} s < 3 × {limit} s: riesgo de anulación por microscalping")
    if cushion_usd is not None and structure["loss_net"] > cushion_usd:
        out.append("el stop supera el colchón hasta el MLL: una pérdida rompe la cuenta")
    return out


def frontier(rows: list[dict], tolerances: tuple[float, ...] = (0.01, 0.05, 0.10, 0.20, 0.30)) -> dict:
    """Mejor estructura (máximo EV 12 m con mediana > 0 y P(neto>0) ≥ 60 %) para cada tolerancia de ruina."""
    return {tol: select(rows, ruin_max=tol) for tol in tolerances}
