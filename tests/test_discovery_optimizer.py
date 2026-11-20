"""Optimizer: meseta ±1 paso sobre IS, sin crear ni reoptimizar estrategias."""

from __future__ import annotations

import copy

import pytest

from tradinglab.discovery import fastbt, jobs, optimizer
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.discovery.specs import run_limits_from_strategy
from tradinglab.propfund.costs import load_profile


def _strategy() -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45"},
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 0.0},
        },
        "exit": {
            "stop": {"type": "atr", "mult": 1.5, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
            "time_exit_bars": 48,
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def test_plateau_is_one_step_only_and_does_not_mutate() -> None:
    frame = synthetic_frame(years=0.3, seed=5)
    setup = jobs.QueueSetup(instrument="US100", timeframe="M5")
    cost = fastbt.cost_from_profile(
        load_profile("CFD-001", "US100", firm="ftmo"), use_p75=True
    )
    original = _strategy()
    untouched = copy.deepcopy(original)
    limits = run_limits_from_strategy(
        optimizer.dsl.Strategy.model_validate(original), setup
    )
    prepared = fastbt.prepare(
        frame,
        cost,
        atr_windows=(14,),
        sessions=(limits,),
    )

    result = optimizer.plateau(
        original, frame, cost, setup, prepared, cache=None
    )

    assert original == untouched
    assert result["rows"] == len(result["parameters"]) > 0
    assert result["base"]["trades"] >= 1
    rows = {row["name"]: row for row in result["parameters"]}
    assert {"stop.mult", "target.rr", "time_exit_bars"} <= set(rows)
    assert {"session.start", "session.end"} <= set(rows)

    stop = rows["stop.mult"]
    assert stop["base"] == pytest.approx(1.5)
    assert stop["minus"] == pytest.approx(1.4)
    assert stop["plus"] == pytest.approx(1.6)
    assert stop["metrics"]["minus"]["trades"] >= 1
    assert stop["metrics"]["plus"]["trades"] >= 1

    start = rows["session.start"]
    assert start["base"] == pytest.approx(9 * 60 + 35)
    assert start["minus"] == pytest.approx(9 * 60 + 30)
    assert start["plus"] == pytest.approx(9 * 60 + 40)

    bars = rows["time_exit_bars"]
    assert bars["minus"] == pytest.approx(36.0)
    assert bars["plus"] == pytest.approx(60.0)


def test_plateau_skips_out_of_range_values() -> None:
    strategy = _strategy()
    strategy["exit"]["target"] = {"type": "rr", "rr": 0.05}
    frame = synthetic_frame(years=0.2, seed=6)
    setup = jobs.QueueSetup(instrument="US100", timeframe="M5")
    cost = fastbt.cost_from_profile(
        load_profile("CFD-001", "US100", firm="ftmo"), use_p75=True
    )
    model = optimizer.dsl.Strategy.model_validate(strategy)
    limits = run_limits_from_strategy(model, setup)
    prepared = fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))

    result = optimizer.plateau(strategy, frame, cost, setup, prepared)
    row = next(
        item for item in result["parameters"] if item["name"] == "target.rr"
    )
    assert row["base"] == pytest.approx(0.05)
    assert row["minus"] is None
    assert row["metrics"]["minus"] is None
    assert row["plus"] == pytest.approx(0.15)
