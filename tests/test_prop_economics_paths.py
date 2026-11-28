"""FUT-A2: DayPath, constructor desde operaciones y desplazamiento de la ventaja (04 §2 y §7.1)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.prop_economics.paths import DayPath, TradeSpec, from_trades, shift

D = date(2026, 11, 30)


def _two_trades() -> DayPath:
    return from_trades(D, [TradeSpec(100, 150, 40, 2.5), TradeSpec(-50, 20, 60, 2.5)])


def test_from_trades_exact():
    day = _two_trades()
    assert day.marks.tolist() == [0, 150, -40, 100, 120, 40, 50]
    assert day.n_trades == 2
    assert day.gross_pnl == 55.0
    assert day.cost == 5.0
    assert day.exit_idx == (3, 6)
    day.validate()


def test_shift_exact():
    moved = shift(_two_trades(), 10)
    assert moved.marks.tolist() == [0, 150, -40, 110, 130, 50, 70]
    assert moved.gross_pnl == 75.0
    moved.validate()


def test_shift_does_not_mutate_original():
    day = _two_trades()
    shift(day, 10)
    assert day.marks.tolist() == [0, 150, -40, 100, 120, 40, 50]


def test_invalid_trade_raises():
    with pytest.raises(ValueError):
        TradeSpec(200, 150, 40, 0)


def test_empty_day():
    day = from_trades(D, [])
    assert day.marks.tolist() == [0.0]
    assert (day.n_trades, day.gross_pnl, day.cost, day.exit_idx) == (0, 0.0, 0.0, ())
    day.validate()


@pytest.mark.parametrize("marks, gross, cost", [
    ([1.0, 2.0], 2.0, 0.0),
    ([0.0, float("nan")], 0.0, 0.0),
    ([0.0, 1.0], 1.0, -1.0),
    ([0.0, 1.0], 5.0, 0.0),
])
def test_validate_rejects(marks, gross, cost):
    with pytest.raises(ValueError):
        DayPath(D, np.asarray(marks), 1, (1,), gross, cost).validate()
