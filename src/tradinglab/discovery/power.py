"""Puerta de potencia del preflight (T20).

MDE = (z_0,95 + z_0,80) · σ_R / √n ≈ 2,49 · σ_R / √n.
Solo conteos: no calcula expectativa, PF ni percentil.
"""

from __future__ import annotations

import math
from typing import Any

Z_ALPHA = 1.6448536269514722
Z_BETA = 0.8416212335729143
MDE_CONSTANT = 2.49
DEFAULT_SIGMA_R = 1.0


def mde(n: int | float, *, sigma_r: float = DEFAULT_SIGMA_R) -> float | None:
    """Efecto mínimo detectable en R para ``n`` operaciones."""

    count = float(n or 0.0)
    if count <= 0.0:
        return None
    return MDE_CONSTANT * float(sigma_r) / math.sqrt(count)


def power_check(
    n_holdout: int | float,
    delta: float | None,
    *,
    sigma_r: float = DEFAULT_SIGMA_R,
) -> dict[str, Any]:
    """Veredicto de potencia. Sin δ: aviso, no bloqueo."""

    value = mde(n_holdout, sigma_r=sigma_r)
    payload: dict[str, Any] = {
        "n_holdout": int(n_holdout or 0),
        "sigma_r": float(sigma_r),
        "mde_holdout": value,
        "plausible_edge_r": None if delta is None else float(delta),
        "potencia_ok": None,
        "potencia_status": "Sin datos: sin δ",
    }
    if delta is None:
        return payload
    if value is None:
        payload["potencia_status"] = "Sin datos: n_holdout = 0"
        return payload
    ok = bool(value <= float(delta))
    payload["potencia_ok"] = ok
    payload["potencia_status"] = (
        "potencia_ok" if ok else "sin potencia: MDE_holdout > δ"
    )
    return payload


def segment_years(segments: dict[str, Any]) -> dict[str, float]:
    """Duración en años de IS/OOS-1/OOS-2 (holdout = OOS-1 + OOS-2)."""

    import pandas as pd

    def years(pair: list[Any]) -> float:
        start = pd.Timestamp(pair[0])
        end = pd.Timestamp(pair[1]) if pair[1] else pd.Timestamp.today()
        return max(0.0, (end - start).days / 365.25)

    out = {
        "is": years(segments.get("is") or ["2020-01-01", "2020-12-31"]),
        "oos1": years(segments.get("oos1") or ["2020-01-01", "2020-12-31"]),
        "oos2": years(segments.get("oos2") or ["2020-01-01", None]),
    }
    out["holdout"] = out["oos1"] + out["oos2"]
    return out


def counts_from_is(
    trades_is: int | float,
    segments: dict[str, Any],
) -> dict[str, int]:
    """Escala los conteos de IS a desarrollo y holdout por duración."""

    years = segment_years(segments)
    ratio = years["is"] / years["holdout"] if years["holdout"] > 0 else 0.0
    is_count = int(round(float(trades_is or 0)))
    holdout = int(round(is_count / ratio)) if ratio > 0 else 0
    return {"trades_is": is_count, "trades_holdout": holdout}


__all__ = [
    "DEFAULT_SIGMA_R",
    "MDE_CONSTANT",
    "Z_ALPHA",
    "Z_BETA",
    "counts_from_is",
    "mde",
    "power_check",
    "segment_years",
]
