"""Retester: estrategia congelada, costes ×1,5/×2, slippage +1/+2 y transfer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt, jobs, retester
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


def _parts():
    frame = synthetic_frame(years=0.3, seed=8)
    split = int(len(frame) * 0.75)
    setup = jobs.QueueSetup(instrument="US100", timeframe="M5")
    cost = fastbt.cost_from_profile(
        load_profile("CFD-001", "US100", firm="ftmo"), use_p75=True
    )
    return frame.iloc[:split], frame.iloc[split:], setup, cost


def test_retest_scenarios_are_monotone_and_base_matches() -> None:
    is_frame, oos1_frame, setup, cost = _parts()
    strategy = _strategy()
    result = retester.retest(strategy, is_frame, oos1_frame, cost, setup)

    model = retester.dsl.Strategy.model_validate(strategy)
    bars = pd.concat([is_frame, oos1_frame], axis=0, sort=False)
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    prepared = fastbt.prepare(bars, cost, atr_windows=(14,), sessions=(limits,))
    direct = fastbt.run(
        retester.compiler.compile(model, bars),
        bars,
        retester.exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
    )
    for name in ("base", "cost_x1_5", "cost_x2", "slippage_plus_1", "slippage_plus_2"):
        assert result[name]["trades"] >= 1
    assert result["spread_p75"]["trades"] >= 1
    assert result["base"]["expectancy_r"] == pytest.approx(
        direct.metrics["expectancy_r"]
    )
    assert result["base"]["trades"] == direct.metrics["trades"]
    assert result["stress_cost_x1_5_ok"] == (
        result["cost_x1_5"]["expectancy_r"] > 0
    )
    assert result["slippage_plus_2_ok"] == (
        result["slippage_plus_2"]["expectancy_r"] > 0
    )
    assert result["transfer"] == {}

    def expectancy(key: str) -> float:
        return float(result[key]["expectancy_r"])

    assert expectancy("cost_x1_5") <= expectancy("base") + 1e-12
    assert expectancy("cost_x2") <= expectancy("cost_x1_5") + 1e-12
    assert expectancy("slippage_plus_2") <= expectancy("slippage_plus_1") + 1e-12
    assert expectancy("slippage_plus_2") <= expectancy("base") + 1e-12


def test_scenario_panel_scales_all_components() -> None:
    is_frame, oos1_frame, _setup, cost = _parts()
    bars = pd.concat([is_frame, oos1_frame], axis=0, sort=False)
    panel = cost.panel(bars)

    doubled = retester._scenario_panel(panel, cost, bars, factor=2.0)
    assert np.allclose(doubled.entry_bps, panel.entry_bps * 2.0)
    assert np.allclose(doubled.stop_bps, panel.stop_bps * 2.0)
    assert np.allclose(doubled.target_bps, panel.target_bps * 2.0)
    assert np.allclose(doubled.spread_bps, panel.spread_bps * 2.0)

    slipped = retester._scenario_panel(
        panel,
        cost,
        bars,
        slippage_points=0.02,
    )
    expected = 0.02 / bars["close"].to_numpy(dtype=float) * 10_000.0
    assert np.allclose(slipped.entry_bps, panel.entry_bps + expected)
    assert np.allclose(slipped.stop_bps, panel.stop_bps + expected)
    assert np.allclose(slipped.target_bps, panel.target_bps + expected)


def test_transfer_is_informative_only() -> None:
    is_frame, oos1_frame, setup, cost = _parts()
    payload = retester.transfer(
        _strategy(),
        {"US100": (is_frame, oos1_frame)},
        {"US100": cost},
        {"US100": setup},
    )
    assert payload["US100"]["transfer"] is True
    assert payload["US100"]["counts_as_validation"] is False
    assert payload["US100"]["trades"] >= 1
