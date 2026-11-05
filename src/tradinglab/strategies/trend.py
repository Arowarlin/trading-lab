from __future__ import annotations

import pandas as pd

from ..indicators import ema, sma
from .base import StrategyResult, clamp_target


def trend_signal(
    df: pd.DataFrame,
    fast: int = 50,
    slow: int = 200,
    regime: int = 200,
) -> StrategyResult:
    """Seguimiento de tendencia long-only.

    Entra cuando EMA(fast) > EMA(slow) y el precio está sobre su SMA(regime).
    Sale cuando cualquiera de las dos condiciones deja de cumplirse.
    """
    close = df["close"]
    fast_ma = ema(close, fast)
    slow_ma = ema(close, slow)
    regime_ma = sma(close, regime)

    long_ok = (fast_ma > slow_ma) & (close > regime_ma)
    target = long_ok.astype(float)

    return StrategyResult(
        name="trend",
        target=clamp_target(target),
        params={"fast": fast, "slow": slow, "regime": regime},
    )
