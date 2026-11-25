"""T3 · Candados de potencia, coste, identidad y muestras."""

from __future__ import annotations

import math
from typing import Any

from .registry import connect, thresholds_hash

MDE_RULE = 2.49


def power_gate(delta: float | None, sigma: float | None, n: int | float) -> dict[str, Any]:
    if delta is None or sigma is None or n is None or float(n) <= 0:
        return {"ok": False, "mde": None, "reason": "Sin datos: delta/sigma/n"}
    mde = MDE_RULE * float(sigma) / math.sqrt(float(n))
    return {
        "ok": mde <= float(delta),
        "mde": mde,
        "reason": None if mde <= float(delta) else "no_power",
    }


def cost_gate(gross_expected: float, cost_estimated: float) -> dict[str, Any]:
    ok = float(gross_expected) >= 2.0 * float(cost_estimated)
    return {"ok": ok, "reason": None if ok else "gross_lt_cost"}


def min_trades_gate(n: int | float | None, min_trades: int = 40) -> dict[str, Any]:
    """Puerta de potencia por muestra: al menos ``min_trades`` operaciones."""

    if n is None or float(n) < 0:
        return {"ok": False, "n": None, "min_trades": int(min_trades), "reason": "Sin datos: n"}
    trades = int(n)
    ok = trades >= int(min_trades)
    return {
        "ok": ok,
        "n": trades,
        "min_trades": int(min_trades),
        "reason": None if ok else f"n_trades {trades} < {int(min_trades)}",
    }


def cost_r_gate(cost_r: float | None, max_cost_r: float = 0.10) -> dict[str, Any]:
    """Puerta de coste: ``cost_r`` (coste / distancia del stop) <= máximo."""

    if cost_r is None:
        return {"ok": False, "cost_r": None, "max_cost_r": float(max_cost_r), "reason": "Sin datos: cost_r"}
    value = float(cost_r)
    ok = value <= float(max_cost_r)
    return {
        "ok": ok,
        "cost_r": value,
        "max_cost_r": float(max_cost_r),
        "reason": None if ok else f"cost_r {value:.4f} > {float(max_cost_r):.4f}",
    }


def identity_gate(
    structural: str,
    *,
    parent_id: str | None = None,
    db_path=None,
) -> dict[str, Any]:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT hypothesis_id FROM hypotheses"
            " WHERE structural_hash = ? AND status = 'rejected'",
            (structural,),
        ).fetchall()
    if not rows:
        return {"ok": True, "reason": None}
    if parent_id:
        return {"ok": True, "reason": "parent_id + holdout nuevo"}
    return {"ok": False, "reason": "identidad: hash ya rechazado"}


def holdout_gate(
    instrument: str,
    timeframe: str,
    start: str,
    end: str,
    *,
    db_path=None,
) -> dict[str, Any]:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT hypothesis_id, window_start, window_end, kind FROM sample_usage"
            " WHERE instrument = ? AND timeframe = ?"
            " AND window_start <= ? AND window_end >= ?",
            (instrument, timeframe, end, start),
        ).fetchall()
    if not rows:
        return {"ok": True, "reason": None}
    return {
        "ok": False,
        "reason": f"holdout solapado con {len(rows)} muestra(s) usada(s)",
        "matches": [dict(row) for row in rows],
    }


def experiment_valid(
    hypothesis_thresholds: str,
    current_thresholds: str | None = None,
) -> dict[str, Any]:
    current = current_thresholds or thresholds_hash()
    ok = str(hypothesis_thresholds) == str(current)
    return {
        "ok": ok,
        "status": "valid" if ok else "invalid",
        "reason": None if ok else "thresholds_hash distinto",
    }


__all__ = [
    "MDE_RULE",
    "cost_gate",
    "cost_r_gate",
    "experiment_valid",
    "holdout_gate",
    "identity_gate",
    "min_trades_gate",
    "power_gate",
]
