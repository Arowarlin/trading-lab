from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.ea_us100 import _dynamic_risk, drop_forming_bar


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


def test_drop_forming_bar_descarta_la_vela_en_curso():
    index = pd.DatetimeIndex(
        pd.to_datetime(
            ["2026-11-24 10:00", "2026-11-24 10:05", "2026-11-24 10:10"]
        )
    )
    frame = pd.DataFrame({"open": [1.0, 2.0, 3.0]}, index=index)

    # 15:12 UTC = 10:12 NY: la vela de 10:10 cierra a las 10:15, aún no.
    forming = drop_forming_bar(
        frame, now_utc=pd.Timestamp("2026-11-24 15:12", tz="UTC")
    )
    assert list(forming.index) == [index[0], index[1]]

    # 15:15 UTC = 10:15 NY: la vela de 10:10 ya cerró.
    closed = drop_forming_bar(
        frame, now_utc=pd.Timestamp("2026-11-24 15:15", tz="UTC")
    )
    assert list(closed.index) == list(index)
