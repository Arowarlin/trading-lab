"""Overlay de defensa aplicado a retornos históricos.

No es un backtest de una estrategia: toma retornos ya calculados y simula qué
habría pasado si el tamaño se hubiera reducido por zonas de drawdown y el
circuit breaker diario hubiera cortado el resto del día. Sirve para medir el
efecto del overlay antes de llevarlo a `enforce`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from .defense import DefenseError, zone_for_utilization


@dataclass(frozen=True)
class OverlayResult:
    returns: pd.Series
    equity: pd.Series
    size_factor: pd.Series
    breaker_days: int
    max_drawdown_pct: float
    total_return: float
    cagr: float
    calmar: float


def _years(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 0.0
    seconds = (index[-1] - index[0]).total_seconds()
    return max(seconds / (365.25 * 24 * 3600), 1e-9)


def apply_overlay(
    returns: pd.Series,
    *,
    max_drawdown_pct: float = 0.09,
    max_daily_loss_pct: float = 0.045,
    start_equity: float = 100_000.0,
    tz: str = "UTC",
) -> OverlayResult:
    """Escala cada retorno por el factor de la zona y aplica el breaker.

    El factor se decide con el equity y el HWM **antes** del retorno de la
    barra; después se actualiza el HWM. El breaker se latcha al cruzar la
    pérdida diaria y se rearma al cambiar de día en ``tz``.
    """
    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)
    series = pd.to_numeric(returns, errors="coerce").astype(float)
    series = series.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(-0.95, 1.0)
    if series.empty:
        raise DefenseError("la serie de retornos está vacía")
    if not isinstance(series.index, pd.DatetimeIndex):
        try:
            series = series.set_axis(pd.to_datetime(series.index))
        except Exception as exc:
            raise DefenseError("el índice debe ser de fechas") from exc
    index = series.index
    if index.tz is None:
        index = index.tz_localize("UTC")
    if start_equity <= 0:
        raise DefenseError("start_equity debe ser positivo")
    if not 0.0 < max_drawdown_pct < 1.0:
        raise DefenseError("max_drawdown_pct debe estar entre 0 y 1")
    if not 0.0 < max_daily_loss_pct < 1.0:
        raise DefenseError("max_daily_loss_pct debe estar entre 0 y 1")

    local_days = np.asarray(index.tz_convert(tz).date)
    values = series.to_numpy(dtype=float)
    count = len(values)
    equity = float(start_equity)
    hwm = equity
    factors = np.empty(count)
    equities = np.empty(count)
    day_start = equity
    current_day: date | None = None
    breaker = False
    breaker_days: set[date] = set()

    for i in range(count):
        day = local_days[i]
        if day != current_day:
            current_day = day
            day_start = equity
            breaker = False

        drawdown = max(0.0, (hwm - equity) / hwm) if hwm > 0 else 0.0
        utilization = drawdown / max_drawdown_pct
        _, factor = zone_for_utilization(utilization)
        if breaker:
            factor = 0.0

        equity *= 1.0 + values[i] * factor
        if not np.isfinite(equity):
            equity = 0.0
        equity = max(equity, 0.0)
        if equity > hwm:
            hwm = equity

        factors[i] = factor
        equities[i] = equity

        if (day_start - equity) / day_start >= max_daily_loss_pct:
            breaker = True
            breaker_days.add(day)

    equity_series = pd.Series(equities, index=index, name="equity")
    drawdowns = equity_series / equity_series.cummax() - 1.0
    max_dd = float(drawdowns.min()) if len(drawdowns) else 0.0
    final_equity = float(equity_series.iloc[-1])
    total_return = final_equity / start_equity - 1.0
    years = _years(index)
    cagr = (
        float((final_equity / start_equity) ** (1.0 / years) - 1.0)
        if years > 0 and final_equity > 0
        else -1.0
    )
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    return OverlayResult(
        returns=pd.Series(values * factors, index=index, name="returns"),
        equity=equity_series,
        size_factor=pd.Series(factors, index=index, name="size_factor"),
        breaker_days=len(breaker_days),
        max_drawdown_pct=max_dd,
        total_return=total_return,
        cagr=cagr,
        calmar=calmar,
    )


__all__ = ["OverlayResult", "apply_overlay"]
