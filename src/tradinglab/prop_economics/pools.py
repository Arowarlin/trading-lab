"""Pools de días para el motor EV: lectura/escritura JSONL y generador SINTÉTICO (hipotético) — FUT-A8.

Un pool real viene de operaciones forward/OOS/IS de una estrategia (``source``). El generador sintético
existe solo para escenarios hipotéticos: sus días llevan ``source="synthetic"`` y el informe lo dice.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .paths import DayPath


def dump_pool(pool: list[DayPath], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        for d in pool:
            fh.write(json.dumps({
                "session_date": d.session_date.isoformat(), "marks": [float(x) for x in d.marks],
                "n_trades": d.n_trades, "exit_idx": list(d.exit_idx), "gross_pnl": d.gross_pnl, "cost": d.cost,
                "risk_usd": d.risk_usd, "flags": sorted(d.flags), "source": d.source,
            }) + "\n")


def load_pool(path: str | Path) -> list[DayPath]:
    pool = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        d = DayPath(date.fromisoformat(r["session_date"]), np.asarray(r["marks"], dtype=np.float64), int(r["n_trades"]),
                    tuple(r["exit_idx"]), float(r["gross_pnl"]), float(r["cost"]), r.get("risk_usd"),
                    frozenset(r.get("flags", [])), r.get("source", "unknown"))
        d.validate()
        pool.append(d)
    return pool


def synthetic_pool(*, mu_gross_r: float, rr: float, risk_usd: float, cost_rt: float, n_days: int, seed: int,
                   start: date = date(2027, 1, 4)) -> list[DayPath]:
    """1 operación por día y por contrato, HIPOTÉTICA.

    p(ganar) sale de la ventaja bruta en R: ``p = (μ + 1)/(RR + 1)``. Las ganadoras sufren antes una
    excursión adversa U(0,1)·riesgo; las perdedoras alcanzan antes una favorable U(0,1)·riesgo.
    """
    if not 0 < risk_usd or rr <= 0 or cost_rt < 0:
        raise ValueError("parámetros no válidos")
    rng = np.random.default_rng(seed)
    p = (mu_gross_r + 1.0) / (rr + 1.0)
    if not 0 < p < 1:
        raise ValueError(f"p(ganar) fuera de (0, 1): {p}")
    pool = []
    for i in range(n_days):
        u = float(rng.random())
        if rng.random() < p:
            marks = [0.0, -u * risk_usd, rr * risk_usd - cost_rt]
        else:
            marks = [0.0, u * risk_usd, -risk_usd - cost_rt]
        d = DayPath(start + timedelta(days=i), np.asarray(marks), 1, (2,), marks[-1] + cost_rt, cost_rt, risk_usd,
                    frozenset(), "synthetic")
        d.validate()
        pool.append(d)
    return pool
