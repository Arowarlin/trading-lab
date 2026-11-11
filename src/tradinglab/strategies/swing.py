"""Tendencia diaria con ejecución intradía y stop ATR.

Familia `trend` reutilizada: la señal es `trend_signal` (EMA rápida/lenta +
filtro de régimen) sobre barras diarias; no se copia el indicador. Encima:

- la señal del día `D-1` se aplica a las barras del día `D` (causal);
- stop de ATR: se cierra cuando el cierre cruza entrada ∓ `stop_atr` × ATR;
  tras el stop no se vuelve a entrar hasta que la señal diaria vuelva a 0.

El motor de backtest ejecuta el objetivo en la barra siguiente, así que el
stop sobre cierres es conservador (no hay ejecución intrabarra).
"""

from __future__ import annotations

import pandas as pd

from ..indicators import atr
from .base import StrategyResult, clamp_target
from .trend import trend_signal

DAILY_RULE = "1D"


def trading_day(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Día de sesión: el domingo por la noche pertenece al lunes.

    Los CFDs abren el domingo (22:00/23:00 UTC); esa sesión es el arranque del
    lunes. El sábado se descarta (no hay sesión).
    """
    days = pd.DatetimeIndex(index).normalize()
    shift = (days.day_of_week == 6).astype(int)
    return days + pd.to_timedelta(shift, unit="D")


def daily_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Barras diarias (UTC) a partir de una serie intradía.

    La sesión del domingo se suma al lunes para que la barra diaria sea la del
    día de mercado y no una barra parcial.
    """
    work = frame.copy()
    work = work[work.index.day_of_week != 5]
    work.index = trading_day(work.index)
    work = work.sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "spread" in work.columns:
        agg["spread"] = "median"
    daily = work.resample(DAILY_RULE).agg(agg)
    return daily.dropna(subset=["open", "high", "low", "close"])


def daily_target_to_intraday(
    daily_target: pd.Series,
    index: pd.DatetimeIndex,
) -> pd.Series:
    """Señal de la sesión anterior aplicada a cada barra del día siguiente.

    La barra diaria `D` solo se conoce al cierre de `D`, así que en las barras
    de `D` se usa el objetivo de `D-1`. Sin esto habría lookahead. El domingo
    por la noche usa la señal del viernes (es el lunes de mercado).
    """
    by_day = daily_target.astype(float).copy()
    by_day.index = pd.DatetimeIndex(by_day.index).normalize()
    by_day = by_day.shift(1)
    days = trading_day(index)
    values = by_day.reindex(days)
    return pd.Series(
        values.to_numpy(dtype=float),
        index=pd.DatetimeIndex(index),
        dtype=float,
    ).fillna(0.0)


def atr_close_stop(
    target: pd.Series,
    frame: pd.DataFrame,
    *,
    stop_atr: float,
    atr_window: int = 14,
) -> pd.Series:
    """Cierra la posición cuando el cierre cruza entrada ∓ `stop_atr` × ATR.

    Tras un stop no se reentra hasta que la señal vuelva a 0 y vuelva a 1: el
    stop no se puede saltar reentrando en la barra siguiente.
    """
    if float(stop_atr) <= 0:
        raise ValueError("stop_atr debe ser > 0")
    atr_s = atr(frame, window=int(atr_window))
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    out = target.astype(float).copy()
    position = 0.0
    entry: float | None = None
    stop: float | None = None
    stopped = False
    for stamp in out.index:
        desired = float(target.loc[stamp])
        if desired == 0.0:
            stopped = False
        if stopped:
            out.loc[stamp] = 0.0
            continue
        if desired != position:
            position = desired
            if position == 0.0:
                entry = stop = None
            else:
                entry = float(close.loc[stamp])
                value = float(atr_s.loc[stamp]) if stamp in atr_s.index else 0.0
                stop = entry - position * float(stop_atr) * value if value > 0 else None
        if position != 0.0 and stop is None and entry is not None:
            # ATR aún sin muestra (primeras barras): se fija en cuanto hay dato.
            value = float(atr_s.loc[stamp]) if stamp in atr_s.index else 0.0
            if value > 0:
                stop = entry - position * float(stop_atr) * value
        if position != 0.0 and stop is not None:
            price = float(close.loc[stamp])
            hit = (position > 0 and price <= stop) or (position < 0 and price >= stop)
            if hit:
                out.loc[stamp] = 0.0
                position = 0.0
                entry = stop = None
                stopped = True
    return out


def trend_daily_atr(
    df: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 100,
    regime: int = 200,
    stop_atr: float = 2.0,
    atr_window: int = 14,
) -> StrategyResult:
    """Tendencia diaria (reutiliza `trend_signal`) + stop ATR sobre `df`."""
    daily = daily_bars(df)
    if len(daily) < max(int(slow), int(regime)) + 2:
        empty = pd.Series(0.0, index=df.index, dtype=float)
        return StrategyResult(
            "trend-daily-atr",
            empty,
            {
                "fast": int(fast),
                "slow": int(slow),
                "regime": int(regime),
                "stop_atr": float(stop_atr),
                "atr_window": int(atr_window),
            },
        )
    signal = trend_signal(daily, fast=int(fast), slow=int(slow), regime=int(regime))
    mapped = daily_target_to_intraday(signal.target, pd.DatetimeIndex(df.index))
    target = atr_close_stop(
        mapped,
        df,
        stop_atr=float(stop_atr),
        atr_window=int(atr_window),
    )
    return StrategyResult(
        "trend-daily-atr",
        clamp_target(target),
        {
            "fast": int(fast),
            "slow": int(slow),
            "regime": int(regime),
            "stop_atr": float(stop_atr),
            "atr_window": int(atr_window),
        },
    )


__all__ = [
    "DAILY_RULE",
    "atr_close_stop",
    "daily_bars",
    "daily_target_to_intraday",
    "trading_day",
    "trend_daily_atr",
]
