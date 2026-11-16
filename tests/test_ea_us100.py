from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.ea_us100 import _dynamic_risk


def _values(daily_stop: float = 100.0) -> dict:
    return {
        "InpDynBase": 1.0,
        "InpDynDD1": 2.0,
        "InpDynDD2": 4.0,
        "InpDynDD3": 6.0,
        "InpDynR1": 0.6,
        "InpDynR2": 0.35,
        "InpDynR3": 0.25,
        "InpMaxDDPct": 8.0,
        "InpDailyLossPct": daily_stop,
    }


def test_dynamic_risk_devuelve_retornos_diarios():
    result = _dynamic_risk(pd.Series([1.0, -2.0, 0.5, 0.0]), _values())

    assert result["daily_returns"] == pytest.approx(
        [0.01, -2000.0 / 101_000.0, 500.0 / 99_000.0, 0.0]
    )
    assert result["equity"] == pytest.approx(99_500.0)
    assert result["max_drawdown"] == pytest.approx(99_000.0 / 101_000.0 - 1.0)
    assert result["killed"] is False


def test_dynamic_risk_aplica_el_tope_diario():
    result = _dynamic_risk(pd.Series([-10.0]), _values(daily_stop=1.5))

    assert result["daily_returns"] == pytest.approx([-0.015])
    assert result["equity"] == pytest.approx(98_500.0)
