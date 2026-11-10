"""Momentum sectorial long-only con filtro de volatilidad.

Hipótesis: un ETF sectorial en momentum positivo tiende a continuar, pero
solo merece exposición cuando su volatilidad realizada no está por encima de
su propia mediana de un año. Es una estrategia de serie temporal; el carácter
"sectorial" viene del universo donde se prueba, no de una señal transversal.
"""
from __future__ import annotations

import pandas as pd

from .base import StrategyResult, clamp_target


def sector_momentum_signal(
    df: pd.DataFrame,
    lookback: int = 60,
    vol_window: int = 20,
    vol_mult: float = 1.25,
) -> StrategyResult:
    """Long si el retorno de ``lookback`` es positivo y la vol es normal."""
    close = pd.to_numeric(df["close"], errors="coerce")
    momentum = close.pct_change(lookback, fill_method=None)
    returns = close.pct_change(fill_method=None)
    volatility = returns.rolling(vol_window).std(ddof=0)
    vol_median = volatility.rolling(252, min_periods=60).median()
    long_ok = (
        (momentum > 0)
        & vol_median.notna()
        & (volatility <= vol_median * float(vol_mult))
    )
    return StrategyResult(
        name="sector_momentum",
        target=clamp_target(long_ok.astype(float)),
        params={
            "lookback": lookback,
            "vol_window": vol_window,
            "vol_mult": vol_mult,
        },
    )
