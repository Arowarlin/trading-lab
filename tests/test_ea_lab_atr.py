from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.ea_lab.atr import AtrError, atr_ratio, true_ranges, wilder_atr


def _bars(start: str, periods: int, *, base: float = 9.5) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="5min")
    add = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "open": base + add,
            "high": base + add + 0.5,
            "low": base + add - 0.5,
            "close": base + add,
            "tickvol": 100.0,
            "spread": 10.0,
        },
        index=index,
    )


def test_wilder_atr_sigue_la_definicion_del_motor():
    frame = _bars("2026-11-19 09:30", 20)
    frame["high"] = 10 + np.arange(20)
    frame["low"] = 9 + np.arange(20)
    frame["close"] = 9.5 + np.arange(20)
    ranges = true_ranges(frame)
    assert ranges.iloc[0] == pytest.approx(1.0)
    assert ranges.iloc[1] == pytest.approx(1.5)

    atr = wilder_atr(frame, 14)
    first = (1.0 + 13 * 1.5) / 14
    assert atr.iloc[13] == pytest.approx(first)
    assert atr.iloc[14] == pytest.approx((first * 13 + 1.5) / 14)
    assert atr.iloc[:13].isna().all()


def test_atr_ratio_escala_mitad_de_precio():
    us100 = _bars("2026-11-19 09:30", 80)
    us500 = us100.copy()
    for column in ("open", "high", "low", "close"):
        us500[column] = us500[column] * 0.5
    result = atr_ratio(us500, us100, start="2026-11-19", end="2026-11-19")
    assert result["ratio"] == pytest.approx(0.5, rel=1e-6)
    assert result["us500_bars"] == result["us100_bars"]


def test_median_rth_excluye_fuera_de_sesion():
    frame = _bars("2026-11-19 16:00", 20)
    with pytest.raises(AtrError):
        atr_ratio(frame, frame, start="2026-11-19", end="2026-11-19")


def test_atr_sin_datos_falla():
    frame = _bars("2026-11-19 09:30", 3)
    with pytest.raises(AtrError):
        atr_ratio(frame, frame, start="2026-11-19", end="2026-11-19")
