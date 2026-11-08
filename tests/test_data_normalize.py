from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.data.base import normalize


def _frame(**extra):
    index = pd.bdate_range("2026-01-01", periods=5)
    data = {
        "open": [100.0] * 5,
        "high": [101.0] * 5,
        "low": [99.0] * 5,
        "close": [100.5] * 5,
        "volume": [1_000.0] * 5,
    }
    data.update(extra)
    return pd.DataFrame(data, index=index)


def test_normalize_conserva_bid_ask_y_calcula_mid_spread() -> None:
    frame = _frame(bid=[100.0] * 5, ask=[100.2] * 5)
    result = normalize(frame)
    assert {"bid", "ask", "mid", "spread"} <= set(result.columns)
    assert result["mid"].iloc[0] == pytest.approx(100.1)
    assert result["spread"].iloc[0] == pytest.approx(0.2)


def test_normalize_conserva_spread_de_mt5() -> None:
    frame = _frame(spread=[0.3] * 5)
    result = normalize(frame)
    assert "spread" in result.columns
    assert result["spread"].iloc[0] == 0.3


def test_normalize_ohlcv_sin_extras() -> None:
    result = normalize(_frame())
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
