"""T31 · Ajuste de futuros por vencimiento."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import futures_roll


def _synthetic() -> pd.DataFrame:
    index = pd.date_range(
        "2024-03-14 18:00", periods=48, freq="h", tz="America/New_York"
    )
    rng = np.random.default_rng(7)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.2, len(index)))
    # El contrato nuevo entra a 110 en la barra de las 18:00 ET del 15-mar.
    roll_stamp = pd.Timestamp("2024-03-15 18:00", tz="America/New_York")
    position = index.get_loc(roll_stamp)
    close[position:] = 110.0 + np.cumsum(
        rng.normal(0.0, 0.2, len(index) - position)
    )
    close[position] = 110.0
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * 1.001
    low = np.minimum(open_, close) * 0.999
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def test_detecta_el_roll_y_ajusta_por_diferencia_y_ratio():
    frame = _synthetic()
    rolls = futures_roll.detect_rolls(frame)
    assert len(rolls) == 1
    roll = rolls[0]
    assert roll.when == pd.Timestamp("2024-03-15 18:00", tz="America/New_York")
    before = frame.loc[frame.index < roll.when, "close"].iloc[-1]
    diff = futures_roll.adjust_diff(frame, rolls)
    ratio = futures_roll.adjust_ratio(frame, rolls)
    assert diff.loc[diff.index < roll.when, "close"].iloc[-1] == pytest.approx(
        before + roll.jump
    )
    assert ratio.loc[ratio.index < roll.when, "close"].iloc[-1] == pytest.approx(
        before * roll.ratio
    )


def test_sin_saltos_residuales_mayores_de_cinco_sigma():
    frame = _synthetic()
    rolls = futures_roll.detect_rolls(frame)
    diff = futures_roll.adjust_diff(frame, rolls)
    ratio = futures_roll.adjust_ratio(frame, rolls)
    assert futures_roll.residual_jumps(diff, rolls)["over_sigma"] == 0
    assert futures_roll.residual_jumps(ratio, rolls)["over_sigma"] == 0
