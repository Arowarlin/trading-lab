from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.strategies import trend_ls_signal, trend_signal


def frame(closes: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": 1_000.0,
        },
        index=pd.date_range("2025-01-01", periods=len(closes), freq="h", tz="UTC"),
    )


def test_trend_ls_goes_long_in_uptrend():
    df = frame(100 + np.arange(400) * 0.5)
    sig = trend_ls_signal(df)
    assert sig.target.iloc[-1] == 1.0
    assert sig.target.min() >= -1.0 and sig.target.max() <= 1.0


def test_trend_ls_goes_short_in_downtrend():
    df = frame(400 - np.arange(400) * 0.5)
    sig = trend_ls_signal(df)
    assert sig.target.iloc[-1] == -1.0


def test_trend_long_only_never_shorts():
    df = frame(400 - np.arange(400) * 0.5)
    sig = trend_signal(df)
    assert sig.target.iloc[-1] == 0.0
    assert sig.target.min() >= 0.0


def test_trend_ls_needs_enough_history():
    df = frame(100 + np.arange(50) * 0.5)
    sig = trend_ls_signal(df)
    assert (sig.target == 0).all()
