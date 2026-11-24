"""Métricas en R del motor rápido.

Todas las cifras salen de operaciones ya cerradas; no se inventan valores.
Cuando una métrica no está definida (sin operaciones, sin pérdidas o sin
varianza) se devuelve ``None`` y el llamador decide cómo mostrarlo.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0


def _net_rs(trades: Iterable[Any]) -> list[float]:
    values: list[float] = []
    for trade in trades:
        value = getattr(trade, "r_net", None)
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            values.append(number)
    return values


def _gross_rs(trades: Iterable[Any]) -> list[float]:
    values: list[float] = []
    for trade in trades:
        value = getattr(trade, "r_gross", None)
        if value is None:
            continue
        number = float(value)
        if math.isfinite(number):
            values.append(number)
    return values


def expectancy_r(trades: Iterable[Any]) -> float | None:
    values = _net_rs(trades)
    return float(np.mean(values)) if values else None


def profit_factor(trades: Iterable[Any]) -> float | None:
    values = np.asarray(_net_rs(trades), dtype=float)
    if values.size == 0:
        return None
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(values[values < 0].sum())
    if gross_loss == 0.0:
        return None
    return gross_profit / abs(gross_loss)


def win_rate(trades: Iterable[Any]) -> float | None:
    values = np.asarray(_net_rs(trades), dtype=float)
    if values.size == 0:
        return None
    return float((values > 0).mean())


def max_drawdown_r(daily_r: pd.Series | None) -> float | None:
    if daily_r is None or len(daily_r) == 0:
        return None
    equity = pd.concat(
        [pd.Series([0.0]), daily_r.astype(float).cumsum()], ignore_index=True
    )
    drawdown = equity - equity.cummax()
    return float(drawdown.min())


def sharpe_daily(daily_r: pd.Series | None) -> float | None:
    if daily_r is None or len(daily_r) < 2:
        return None
    values = daily_r.astype(float)
    std = float(values.std(ddof=1))
    if not math.isfinite(std) or std <= 0.0:
        return None
    return float(values.mean() / std * math.sqrt(TRADING_DAYS))


def concentration(trades: Iterable[Any]) -> float | None:
    values = np.asarray(_net_rs(trades), dtype=float)
    if values.size == 0:
        return None
    positive = values[values > 0]
    if positive.size == 0 or positive.sum() <= 0:
        return None
    return float(positive.max() / positive.sum())


def cost_sensitivity(trades: Iterable[Any], point: float = 0.01) -> tuple[float | None, float | None]:
    """Expectativa con +1 punto por lado y su caída frente a la base.

    Un "punto" es una unidad de precio (p. ej. 0.01 en US100). El coste extra
    se convierte a R con la distancia de stop de cada operación.
    """

    values = _net_rs(trades)
    if not values:
        return None, None
    base = float(np.mean(values))
    adjusted: list[float] = []
    for trade in trades:
        net = getattr(trade, "r_net", None)
        risk = getattr(trade, "risk_price", None)
        if net is None or risk is None or not math.isfinite(float(net)):
            continue
        risk_value = float(risk)
        if risk_value <= 0.0:
            continue
        adjusted.append(float(net) - 2.0 * float(point) / risk_value)
    if not adjusted:
        return None, None
    plus = float(np.mean(adjusted))
    return plus, plus - base


def summarize(trades: Iterable[Any], daily_r: pd.Series | None, point: float = 0.01) -> dict[str, Any]:
    trades = list(trades)
    values = np.asarray(_net_rs(trades), dtype=float)
    gross = np.asarray(_gross_rs(trades), dtype=float)
    plus, delta = cost_sensitivity(trades, point)
    wins = values[values > 0]
    losses = values[values < 0]
    gross_wins = gross[gross > 0]
    gross_losses = gross[gross < 0]
    risks = [
        float(trade.risk_price)
        for trade in trades
        if getattr(trade, "risk_price", None) is not None
        and math.isfinite(float(trade.risk_price))
        and float(trade.risk_price) > 0.0
    ]
    return {
        "trades": len(trades),
        "expectancy_r": expectancy_r(trades),
        "mean_risk_price": float(np.mean(risks)) if risks else None,
        "profit_factor": profit_factor(trades),
        "win_rate": win_rate(trades),
        "max_dd_r": max_drawdown_r(daily_r),
        "sharpe_daily": sharpe_daily(daily_r),
        "concentration": concentration(trades),
        "total_r": float(values.sum()) if values.size else 0.0,
        "avg_win_r": float(wins.mean()) if wins.size else None,
        "avg_loss_r": float(losses.mean()) if losses.size else None,
        "cost_plus_1pt_r": plus,
        "cost_delta_r": delta,
        # Coste 0: solo se usa para el Edge Map; no cambia la selección.
        "gross_expectancy_r": float(gross.mean()) if gross.size else None,
        "gross_total_r": float(gross.sum()) if gross.size else 0.0,
        "gross_profit_factor": (
            float(gross_wins.sum() / abs(gross_losses.sum()))
            if gross_losses.size and gross_wins.size
            else None
        ),
    }


__all__ = [
    "concentration",
    "cost_sensitivity",
    "expectancy_r",
    "max_drawdown_r",
    "profit_factor",
    "sharpe_daily",
    "summarize",
    "win_rate",
]
