"""SPRT para confirmación forward (T24).

Λ_n = (δ/σ²)·ΣR − n·δ²/(2σ²), con umbrales
A = ln((1−β)/α) y B = ln(β/(1−α)).
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np


def sprt(
    returns: Iterable[float],
    *,
    delta: float,
    alpha: float = 0.05,
    beta: float = 0.2,
    sigma: float | None = None,
) -> dict[str, Any]:
    values = np.asarray([float(value) for value in returns], dtype=float)
    values = values[np.isfinite(values)]
    if float(delta) <= 0.0:
        raise ValueError("delta debe ser > 0")
    if not (0.0 < alpha < 1.0) or not (0.0 < beta < 1.0):
        raise ValueError("alpha y beta deben estar en (0, 1)")
    if sigma is None:
        if len(values) < 2:
            return {
                "decision": "continuar",
                "reason": "Sin datos: menos de 2 operaciones y sin sigma",
                "n": int(len(values)),
                "llr": 0.0,
                "sigma": None,
                "A": math.log((1.0 - beta) / alpha),
                "B": math.log(beta / (1.0 - alpha)),
            }
        sigma_value = float(values.std(ddof=1))
    else:
        sigma_value = float(sigma)
    if sigma_value <= 0.0:
        raise ValueError("sigma debe ser > 0")
    a_threshold = math.log((1.0 - beta) / alpha)
    b_threshold = math.log(beta / (1.0 - alpha))
    cumulative = 0.0
    llr = 0.0
    decision = "continuar"
    stopped_at = None
    for index, value in enumerate(values, start=1):
        cumulative += float(value)
        llr = (
            float(delta) / (sigma_value ** 2) * cumulative
            - index * float(delta) ** 2 / (2.0 * sigma_value ** 2)
        )
        if llr >= a_threshold:
            decision = "aceptar_ventaja"
            stopped_at = index
            break
        if llr <= b_threshold:
            decision = "rechazar"
            stopped_at = index
            break
    return {
        "decision": decision,
        "n": int(len(values)),
        "n_stopped": stopped_at,
        "llr": float(llr),
        "sigma": sigma_value,
        "delta": float(delta),
        "alpha": float(alpha),
        "beta": float(beta),
        "A": a_threshold,
        "B": b_threshold,
        "reason": (
            "Λ ≥ A"
            if decision == "aceptar_ventaja"
            else "Λ ≤ B"
            if decision == "rechazar"
            else "B < Λ < A"
        ),
    }


def wald_expected_n(
    delta: float,
    sigma: float = 1.0,
    *,
    alpha: float = 0.05,
    beta: float = 0.2,
) -> float:
    """E[N | μ = δ] de Wald: [(1−β)·A + β·B] / (δ²/(2σ²))."""

    a_threshold = math.log((1.0 - beta) / alpha)
    b_threshold = math.log(beta / (1.0 - alpha))
    drift = float(delta) ** 2 / (2.0 * float(sigma) ** 2)
    return float(((1.0 - beta) * a_threshold + beta * b_threshold) / drift)


def wald_expected_n_null(
    delta: float,
    sigma: float = 1.0,
    *,
    alpha: float = 0.05,
    beta: float = 0.2,
) -> float:
    """E[N | μ = 0]: [α·A + (1−α)·B] / (−δ²/(2σ²))."""

    a_threshold = math.log((1.0 - beta) / alpha)
    b_threshold = math.log(beta / (1.0 - alpha))
    drift = -(float(delta) ** 2) / (2.0 * float(sigma) ** 2)
    return float((alpha * a_threshold + (1.0 - alpha) * b_threshold) / drift)


def load_forward_returns(
    strategy: str,
    *,
    db_path=None,
) -> tuple[list[float], str]:
    """R por operación del forward demo; solo lectura."""

    from ..config import DEFAULT_DB
    from ..journal import load_closed_trades

    target = db_path or DEFAULT_DB
    try:
        trades, _ = load_closed_trades(target)
    except Exception as exc:  # noqa: BLE001
        return [], f"Sin datos: {type(exc).__name__}"
    wanted = str(strategy or "").strip()
    allowed = {wanted, f"forward:{wanted}"}
    values: list[float] = []
    for trade in trades:
        bot = str(getattr(trade, "bot", "") or "")
        if bot in allowed:
            value = getattr(trade, "r_multiple", None)
            if value is not None:
                values.append(float(value))
    if not values:
        return [], "Sin datos: no hay operaciones forward con R"
    return values, "OK"


__all__ = [
    "load_forward_returns",
    "sprt",
    "wald_expected_n",
    "wald_expected_n_null",
]
