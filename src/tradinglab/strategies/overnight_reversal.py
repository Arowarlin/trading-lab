"""Reversión overnight: largo el tercil más bajo, corto el más alto.

Cada día se calcula el retorno overnight `open_t / close_{t-1} - 1`. Se ordena
el universo y se toma el tercil más bajo (largo) y el más alto (corto) con
pesos iguales; el resto queda plano. La ejecución es en la apertura y el
cierre en el cierre: **no hay posición nocturna**.

`simulate_daily` reproduce esa política con precios de apertura y cierre y
costes por lado. `overnight_reversal_signal` es la versión para el motor
genérico: sin `cross_section` usa la propia historia del activo (un
sustituto, no el tercil transversal).
"""

from __future__ import annotations

import pandas as pd

from .base import StrategyResult, clamp_target


def overnight_returns(df: pd.DataFrame) -> pd.Series:
    """Retorno overnight por barra: `open_t / close_{t-1} - 1`."""
    open_px = df["open"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    return (open_px / prev_close.replace(0.0, pd.NA)).astype(float) - 1.0


def select_terciles(
    cross_section: pd.DataFrame,
    *,
    long_only: bool = False,
) -> pd.DataFrame:
    """Selección diaria: 1 en el tercil más bajo, -1 en el más alto, 0 en el medio.

    Devuelve un frame con la misma forma que `cross_section` y valores -1, 0 o 1.
    """
    ranked = cross_section.rank(pct=True, axis=1)
    low = ranked < 1 / 3
    high = ranked > 2 / 3
    selection = low.astype(float) - high.astype(float)
    if long_only:
        selection = low.astype(float)
    selection = selection.where(~(low & high), 0.0)
    return selection


def simulate_daily(
    frames: dict[str, pd.DataFrame],
    selection: pd.DataFrame,
    *,
    cost_bps: float = 0.0,
) -> tuple[pd.Series, dict]:
    """Simula la reversión overnight: entra en la apertura y sale en el cierre.

    `selection` tiene una columna por símbolo con -1, 0 o 1 por día. El PnL de
    cada día es la selección × (cierre/abertura - 1) menos los costes por lado.
    **No hay posición nocturna**: la exposición es intradía.
    """
    returns: dict[str, pd.Series] = {}
    weights: dict[str, pd.Series] = {}
    intradays: dict[str, pd.Series] = {}
    for symbol, frame in frames.items():
        if symbol not in selection.columns:
            continue
        open_px = frame["open"].astype(float)
        close_px = frame["close"].astype(float)
        intraday = (close_px / open_px.replace(0.0, pd.NA)).astype(float) - 1.0
        daily = pd.DatetimeIndex(
            sorted({pd.Timestamp(stamp).normalize() for stamp in intraday.index})
        )
        weight = (
            selection[symbol]
            .reindex(daily)
            .fillna(0.0)
            .reindex(intraday.index.normalize())
            .fillna(0.0)
        )
        weight.index = intraday.index
        weights[symbol] = weight
        intradays[symbol] = intraday
    if not weights:
        return pd.Series(dtype=float), {"trades": 0, "turnover": 0.0}
    # Pesos iguales con bruto <= 1: sin normalizar, doce activos a 1/3 son 4x.
    weight_table = pd.DataFrame(weights).fillna(0.0)
    bruto = weight_table.abs().sum(axis=1)
    escala = bruto.where(bruto > 0, 1.0)
    weight_table = weight_table.div(escala, axis=0)
    returns = {
        symbol: weight_table[symbol].reindex(intradays[symbol].index).fillna(0.0)
        * intradays[symbol]
        for symbol in weights
    }
    table = pd.DataFrame(returns).fillna(0.0)
    gross = table.sum(axis=1)
    turnover = table.abs().sum(axis=1)
    net = gross - turnover * float(cost_bps) / 10_000.0
    daily_turnover = turnover.groupby(turnover.index.normalize()).sum()
    trades = int((daily_turnover > 0).sum())
    return net, {"trades": trades, "turnover": float(turnover.mean())}


def overnight_reversal_signal(
    df: pd.DataFrame,
    *,
    cross_section: pd.DataFrame | None = None,
    long_only: bool = False,
    dispersion_window: int = 60,
    min_dispersion: float | None = None,
) -> StrategyResult:
    """Objetivo de exposición por día según el tercil overnight.

    `cross_section` es un frame con una columna por símbolo (una fila por día).
    Sin él se usa la propia historia del activo.
    """
    returns = overnight_returns(df)
    index = df.index
    if cross_section is None:
        ranked = returns.rank(pct=True)
        low = ranked < 1 / 3
        high = ranked > 2 / 3
        target = (low.astype(float) - high.astype(float)) / 3.0
        if long_only:
            target = low.astype(float) / 3.0
    else:
        selection = select_terciles(cross_section, long_only=long_only)
        symbol = str(df.attrs.get("symbol") or "")
        if symbol in selection.columns:
            target = selection[symbol] / 3.0
        else:
            target = pd.Series(0.0, index=cross_section.index)
    target = target.reindex(index).fillna(0.0)
    if min_dispersion is not None and cross_section is not None:
        dispersion = cross_section.std(axis=1)
        if len(dispersion):
            median = float(
                dispersion.rolling(int(dispersion_window), min_periods=20).median().iloc[-1]
            )
            if median and float(dispersion.iloc[-1]) <= median:
                target = pd.Series(0.0, index=index)
    return StrategyResult(
        "overnight_reversal",
        clamp_target(target),
        {
            "long_only": bool(long_only),
            "dispersion_window": int(dispersion_window),
            "min_dispersion": min_dispersion,
        },
    )


__all__ = [
    "overnight_reversal_signal",
    "overnight_returns",
    "select_terciles",
    "simulate_daily",
]
