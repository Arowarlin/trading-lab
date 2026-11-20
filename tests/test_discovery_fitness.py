"""Fitness: coste_R por stop, factibilidad y pliegues sin arrastre."""

from __future__ import annotations

import copy
from dataclasses import replace

import pandas as pd

from tradinglab.discovery import fastbt, fitness, jobs
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.propfund.costs import load_profile


def _setup() -> tuple[pd.DataFrame, jobs.QueueSetup, object, fastbt.PreparedBars]:
    frame = synthetic_frame(years=1.0, seed=5)
    setup = jobs.QueueSetup(
        instrument="US100",
        timeframe="M5",
        start="2023-01-02",
        end="2023-12-31",
        bars=frame,
    )
    profile = load_profile("CFD-001", "US100", firm="ftmo")
    cost = fastbt.cost_from_profile(profile)
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
    )
    prepared = fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))
    return frame, setup, cost, prepared


def _strategy(stop_pct: float) -> dict:
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
        "short_entry": None,
        "exit": {
            "stop": {"type": "pct", "value": stop_pct},
            "target": {"type": "rr", "rr": 1.5},
            "time_exit_bars": 48,
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def test_cost_r_tight_stop_not_feasible_wide_stop_feasible() -> None:
    frame, setup, cost, prepared = _setup()
    tight = fitness.evaluate(
        _strategy(0.01), frame, cost, setup, prepared, cost_r_max=0.10
    )
    wide = fitness.evaluate(
        _strategy(2.0), frame, cost, setup, prepared, cost_r_max=0.10
    )
    assert tight["cost_r"] is not None and tight["cost_r"] > 0.10
    assert not tight["feasible"]
    assert any("coste_R" in reason for reason in tight["violations"])
    assert wide["cost_r"] is not None and wide["cost_r"] <= 0.10
    assert wide["feasible"], wide["violations"]


def test_folds_do_not_carry_state() -> None:
    frame, setup, cost, prepared = _setup()
    strategy = _strategy(2.0)
    result = fitness.evaluate(strategy, frame, cost, setup, prepared)
    folds = result["folds"]
    assert len(folds) == 4
    for row in folds:
        assert row["start_index"] <= row["end_index"]
        assert row["trades"] >= 0
    again = fitness.evaluate(
        copy.deepcopy(strategy), frame, cost, setup, prepared
    )
    assert [row["trades"] for row in again["folds"]] == [
        row["trades"] for row in folds
    ]


def test_fold_engine_starts_flat_and_ignores_prior_cooldown() -> None:
    """El fold 2 entra aunque el fold 1 dejara posición/cooldown/contador."""

    from tradinglab.discovery.compiler import Signals

    frame = synthetic_frame(years=0.05, seed=2)
    long = pd.Series(False, index=frame.index)
    long.iloc[10] = True
    long.iloc[210] = True
    signals = Signals(long.to_numpy(), pd.Series(False, index=frame.index).to_numpy(), 0)
    limits = fastbt.RunLimits(
        session_tz="UTC",
        session_start="00:00",
        session_end="00:00",
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        max_trades_per_day=1,
        cooldown_bars=300,
        close_at_end=True,
    )
    spec = fastbt.ExitSpec(stop="pct", stop_mult=50.0, target=None, time_exit_bars=1000)
    zero = fastbt.cfd_costs_from_bps(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )
    full = fastbt.run(signals, frame, spec, zero, limits)
    assert full.trades and full.trades[0].entry_index == 11
    assert all(trade.entry_index != 211 for trade in full.trades)

    fold_signals = Signals(
        signals.long_entry, signals.short_entry, valid_from=210
    )
    fold = fastbt.run(
        fold_signals,
        frame,
        spec,
        zero,
        replace(limits, end_index=299),
    )
    assert len(fold.trades) == 1
    assert fold.trades[0].entry_index == 211
    assert fold.trades[0].exit_index == 299

