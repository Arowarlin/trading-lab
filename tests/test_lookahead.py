from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.indicators import atr, ema, rsi, sma, zscore
from tradinglab.strategies import meanrev_signal, trend_ls_signal, trend_signal


def _frame(rows: int = 500) -> pd.DataFrame:
    index = pd.bdate_range("2019-01-01", periods=rows)
    x = np.arange(rows, dtype=float)
    close = 100.0 + 0.02 * x + 8.0 * np.sin(x / 25.0)
    return pd.DataFrame(
        {
            "open": close + 0.3 * np.sin(x / 7.0),
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def test_estrategias_no_usan_datos_futuros() -> None:
    frame = _frame()
    strategies = [
        (trend_signal, {"fast": 20, "slow": 50, "regime": 100}),
        (trend_ls_signal, {"fast": 20, "slow": 50, "regime": 100}),
        (meanrev_signal, {"window": 20, "entry_z": -1.5, "exit_z": 0.0, "max_hold": 10}),
    ]
    for strategy, params in strategies:
        full = strategy(frame, **params).target
        for cut in (250, 350, 450):
            truncated = strategy(frame.iloc[:cut], **params).target
            pd.testing.assert_series_equal(
                full.iloc[:cut],
                truncated,
                check_names=False,
                check_freq=False,
            )


def test_indicadores_no_usan_datos_futuros() -> None:
    frame = _frame()
    indicators = [
        lambda df: sma(df["close"], 20),
        lambda df: ema(df["close"], 20),
        lambda df: atr(df, 14),
        lambda df: rsi(df["close"], 14),
        lambda df: zscore(df["close"], 20),
    ]
    for indicator in indicators:
        full = indicator(frame)
        for cut in (250, 350, 450):
            truncated = indicator(frame.iloc[:cut])
            pd.testing.assert_series_equal(
                full.iloc[:cut],
                truncated,
                check_names=False,
                check_freq=False,
            )
