"""Reglas del motor rápido: sesión, límites, salidas y costes."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery.fastbt import (
    CfdBpsCosts,
    ExitSpec,
    FastBtError,
    FuturesCosts,
    MissingCostData,
    RunLimits,
    Signals,
    Trade,
    cfd_costs_from_bps,
    cost_from_profile,
    run,
)
from tradinglab.discovery.metrics import summarize
from tradinglab.propfund.costs import load_profile

WEEK = tuple(range(7))


def _frame(n: int = 60, start: str = "2024-01-10 09:00", price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"open": price, "high": price + 0.2, "low": price - 0.2, "close": price},
        index=index,
    )


def _signals(bars: pd.DataFrame, stamps: list[str], side: str = "long") -> Signals:
    long = np.zeros(len(bars), dtype=bool)
    short = np.zeros(len(bars), dtype=bool)
    target = long if side == "long" else short
    for stamp in stamps:
        target[bars.index.get_loc(pd.Timestamp(stamp, tz="UTC"))] = True
    return Signals(long, short)


def _cost() -> CfdBpsCosts:
    return cfd_costs_from_bps(commission_bps=1.0, slippage_bps=1.0, spread_bps=2.0)


def _limits(**kwargs) -> RunLimits:
    base = {"session_tz": "UTC", "weekdays": WEEK, "close_at_end": False}
    base.update(kwargs)
    return RunLimits(**base)


def test_flat_at_uses_instrument_timezone() -> None:
    bars = _frame(n=110, start="2024-01-10 13:00")
    bars["close"] = 100.0
    bars.loc[pd.Timestamp("2024-01-10 20:45", tz="UTC"), "close"] = 100.5
    signals = _signals(bars, ["2024-01-10 15:00"])
    result = run(
        signals,
        bars,
        ExitSpec(stop="pct", stop_mult=5.0, target="rr", target_rr=2.0),
        _cost(),
        _limits(
            session_tz="America/New_York",
            session_start="09:35",
            session_end="11:30",
            flat_at="15:45",
        ),
    )
    assert result.rejected == 0
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == pd.Timestamp("2024-01-10 15:05", tz="UTC")
    assert trade.exit_time == pd.Timestamp("2024-01-10 20:45", tz="UTC")
    assert trade.reason == "force_exit"
    assert trade.exit_price == 100.5


def test_session_blocks_entries_but_allows_exits() -> None:
    bars = _frame(n=110, start="2024-01-10 13:00")
    bars.loc[pd.Timestamp("2024-01-10 16:45", tz="UTC"), "high"] = 101.0
    limits = _limits(
        session_tz="America/New_York",
        session_start="09:35",
        session_end="11:30",
        flat_at="15:45",
    )
    spec = ExitSpec(stop="pct", stop_mult=5.0, target="fixed", target_price=100.8)

    outside = run(_signals(bars, ["2024-01-10 13:00"]), bars, spec, _cost(), limits)
    assert outside.trades == []

    inside = run(_signals(bars, ["2024-01-10 15:00"]), bars, spec, _cost(), limits)
    assert len(inside.trades) == 1
    trade = inside.trades[0]
    assert trade.entry_time == pd.Timestamp("2024-01-10 15:05", tz="UTC")
    assert trade.exit_time == pd.Timestamp("2024-01-10 16:45", tz="UTC")
    assert trade.reason == "target"


def test_weekend_has_no_entries() -> None:
    bars = _frame(n=60, start="2024-01-13 09:00")
    result = run(
        _signals(bars, ["2024-01-13 09:30"]),
        bars,
        ExitSpec(stop="pct", stop_mult=5.0, target="rr", target_rr=2.0),
        _cost(),
        _limits(weekdays=(0, 1, 2, 3, 4)),
    )
    assert result.trades == []


def test_time_exit_bars() -> None:
    bars = _frame(n=40)
    result = run(
        _signals(bars, ["2024-01-10 09:05"]),
        bars,
        ExitSpec(
            stop="pct", stop_mult=5.0, target="rr", target_rr=5.0, time_exit_bars=2
        ),
        _cost(),
        _limits(),
    )
    trade = result.trades[0]
    assert trade.entry_index == 2
    assert trade.exit_index == 4
    assert trade.reason == "time_exit"
    assert trade.bars_held == 2


def test_max_trades_per_day() -> None:
    bars = _frame(n=60)
    result = run(
        _signals(bars, ["2024-01-10 09:15", "2024-01-10 10:15"]),
        bars,
        ExitSpec(stop="pct", stop_mult=5.0, target="rr", target_rr=5.0, time_exit_bars=1),
        _cost(),
        _limits(max_trades_per_day=1),
    )
    assert len(result.trades) == 1
    assert result.trades[0].entry_time == pd.Timestamp("2024-01-10 09:20", tz="UTC")


def test_cooldown_bars() -> None:
    bars = _frame(n=60)
    result = run(
        _signals(bars, ["2024-01-10 09:05", "2024-01-10 09:15", "2024-01-10 10:05"]),
        bars,
        ExitSpec(stop="pct", stop_mult=5.0, target="rr", target_rr=5.0, time_exit_bars=1),
        _cost(),
        _limits(cooldown_bars=10),
    )
    assert len(result.trades) == 2
    assert result.trades[0].entry_time == pd.Timestamp("2024-01-10 09:10", tz="UTC")
    assert result.trades[1].entry_time == pd.Timestamp("2024-01-10 10:10", tz="UTC")


def test_breakeven_moves_stop_from_next_bar() -> None:
    bars = _frame(n=30)
    bars.loc[pd.Timestamp("2024-01-10 09:50", tz="UTC")] = [
        100.5,
        101.2,
        100.5,
        101.0,
    ]
    bars.loc[pd.Timestamp("2024-01-10 09:55", tz="UTC")] = [
        101.0,
        101.3,
        99.9,
        100.2,
    ]
    result = run(
        _signals(bars, ["2024-01-10 09:25"]),
        bars,
        ExitSpec(
            stop="pct",
            stop_mult=1.0,
            target="rr",
            target_rr=5.0,
            breakeven_at_r=1.0,
        ),
        _cost(),
        _limits(),
    )
    trade = result.trades[0]
    assert trade.entry_price == 100.0
    assert trade.reason == "stop"
    assert trade.exit_price == 100.0
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:55", tz="UTC")


def test_trailing_stop_follows_atr() -> None:
    bars = _frame(n=30)
    bars.loc[pd.Timestamp("2024-01-10 09:50", tz="UTC")] = [
        100.5,
        103.0,
        100.9,
        103.0,
    ]
    bars.loc[pd.Timestamp("2024-01-10 09:55", tz="UTC")] = [
        102.0,
        102.5,
        99.5,
        99.8,
    ]
    result = run(
        _signals(bars, ["2024-01-10 09:25"]),
        bars,
        ExitSpec(
            stop="pct",
            stop_mult=5.0,
            target=None,
            trail_atr_mult=1.0,
            trail_n=1,
        ),
        _cost(),
        _limits(),
    )
    trade = result.trades[0]
    assert trade.reason == "stop"
    assert trade.exit_price == 100.0
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:55", tz="UTC")


def test_opposite_signal_exits_at_next_open() -> None:
    bars = _frame(n=40)
    long = np.zeros(len(bars), dtype=bool)
    short = np.zeros(len(bars), dtype=bool)
    long[bars.index.get_loc(pd.Timestamp("2024-01-10 09:05", tz="UTC"))] = True
    short[bars.index.get_loc(pd.Timestamp("2024-01-10 09:30", tz="UTC"))] = True
    result = run(
        Signals(long, short),
        bars,
        ExitSpec(
            stop="pct",
            stop_mult=5.0,
            target=None,
            opposite_signal=True,
        ),
        _cost(),
        _limits(),
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == pd.Timestamp("2024-01-10 09:10", tz="UTC")
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:35", tz="UTC")
    assert trade.reason == "opposite_signal"
    assert trade.exit_price == 100.0


def test_on_signal_end_exits_at_next_open() -> None:
    bars = _frame(n=40)
    result = run(
        _signals(bars, ["2024-01-10 09:05", "2024-01-10 09:10"]),
        bars,
        ExitSpec(
            stop="pct",
            stop_mult=5.0,
            target=None,
            on_signal_end=True,
        ),
        _cost(),
        _limits(),
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == pd.Timestamp("2024-01-10 09:10", tz="UTC")
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:20", tz="UTC")
    assert trade.reason == "signal_end"


def test_close_at_end() -> None:
    bars = _frame(n=20)
    result = run(
        _signals(bars, ["2024-01-10 09:05"]),
        bars,
        ExitSpec(stop="pct", stop_mult=50.0, target=None),
        _cost(),
        _limits(close_at_end=True),
    )
    trade = result.trades[0]
    assert trade.reason == "end_of_data"
    assert trade.exit_index == len(bars) - 1


def test_valid_from_masks_signals() -> None:
    bars = _frame(n=30)
    signal = np.ones(len(bars), dtype=bool)
    result = run(
        Signals(signal, np.zeros(len(bars), dtype=bool), valid_from=10),
        bars,
        ExitSpec(stop="pct", stop_mult=5.0, target="rr", target_rr=2.0, time_exit_bars=1),
        _cost(),
        _limits(max_trades_per_day=1),
    )
    assert result.trades[0].entry_index == 11


def test_event_mode_requires_stop() -> None:
    bars = _frame(n=10)
    with pytest.raises(FastBtError, match="necesita un stop"):
        run(
            _signals(bars, ["2024-01-10 09:05"]),
            bars,
            ExitSpec(stop=None, target=None),
            _cost(),
            _limits(),
        )


def test_invalid_bars_and_signals() -> None:
    bars = _frame(n=10)
    naive = bars.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(FastBtError, match="zona horaria"):
        run(Signals(np.zeros(10, bool), np.zeros(10, bool)), naive, ExitSpec(), _cost(), _limits())

    duplicate = pd.concat([bars.iloc[:5], bars.iloc[[4]], bars.iloc[5:]])
    with pytest.raises(FastBtError, match="duplicados"):
        run(
            Signals(np.zeros(len(duplicate), bool), np.zeros(len(duplicate), bool)),
            duplicate,
            ExitSpec(),
            _cost(),
            _limits(),
        )

    with pytest.raises(FastBtError, match="longitud"):
        run(Signals(np.zeros(3, bool), np.zeros(3, bool)), bars, ExitSpec(), _cost(), _limits())


def test_cfd_profile_costs_from_propfund() -> None:
    profile = load_profile("CFD-001", "US100", firm="ftmo")
    costs = cost_from_profile(profile)
    bars = pd.DataFrame(
        {"open": 20000.0, "high": 20010.0, "low": 19990.0, "close": 20000.0},
        index=pd.date_range("2024-01-10 10:00", periods=3, freq="5min", tz="UTC"),
    )
    panel = costs.panel(bars)
    assert (panel.entry_bps > 0).all()
    assert (panel.target_bps == 0).all()
    assert np.allclose(panel.entry_bps, panel.stop_bps)


def test_missing_cost_data_is_never_zero() -> None:
    with pytest.raises(MissingCostData, match="Sin datos"):
        CfdBpsCosts(commission_bps=1.0, slippage_bps=1.0)
    with pytest.raises(MissingCostData, match="Sin datos"):
        FuturesCosts(
            commission_per_contract=None,
            exchange_fee_per_side=1.0,
            clearing_fee_per_side=1.0,
            nfa_fee_per_side=0.2,
            slippage_ticks=1.0,
            tick_size=0.25,
            tick_value=5.0,
        )
    profile = load_profile("FUT-001", "MNQ")
    with pytest.raises(MissingCostData, match="Sin datos"):
        cost_from_profile(profile)


def test_futures_costs_are_per_contract() -> None:
    costs = FuturesCosts(
        commission_per_contract=2.0,
        exchange_fee_per_side=1.0,
        clearing_fee_per_side=1.0,
        nfa_fee_per_side=0.5,
        slippage_ticks=1.0,
        tick_size=0.25,
        tick_value=5.0,
    )
    assert costs.usd_per_side == pytest.approx(9.5)
    assert costs.unit_value == pytest.approx(20.0)
    assert costs.fut_price == pytest.approx(0.475)

    bars = _frame(n=20)
    result = run(
        _signals(bars, ["2024-01-10 09:05"]),
        bars,
        ExitSpec(stop="pct", stop_mult=1.0, target="rr", target_rr=2.0, time_exit_bars=1),
        costs,
        _limits(),
    )
    trade = result.trades[0]
    assert trade.risk_price == pytest.approx(1.0)
    assert trade.entry_cost_bps == 0.0
    assert trade.r_cost == pytest.approx(0.95)


def test_compiler_signals_integration() -> None:
    import yaml

    from tradinglab.config import ROOT
    from tradinglab.discovery.compiler import compile as compile_strategy

    index = pd.date_range("2024-01-08 00:00", periods=12 * 24 * 10, freq="5min", tz="UTC")
    rng = np.random.default_rng(5)
    close = 20000.0 + np.cumsum(rng.normal(0.0, 4.0, len(index)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, len(index))
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, len(index))
    bars = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )
    path = ROOT / "config" / "discovery" / "templates" / "ny_open_vol_filter.yaml"
    strategy = yaml.safe_load(path.read_text(encoding="utf-8"))["strategy"]
    signals = compile_strategy(strategy, bars)
    assert signals.valid_from > 0

    result = run(
        signals,
        bars,
        ExitSpec(
            stop="atr",
            stop_mult=1.5,
            stop_n=14,
            target="rr",
            target_rr=2.0,
            time_exit_bars=48,
        ),
        _cost(),
        RunLimits(
            session_tz="America/New_York",
            session_start="09:35",
            session_end="11:30",
            flat_at="15:45",
            max_trades_per_day=2,
            cooldown_bars=5,
        ),
    )
    assert result.rejected == 0
    for trade in result.trades:
        assert trade.entry_index >= signals.valid_from


def _bias_dataset(
    n: int = 400_000, seed: int = 20261120
) -> tuple[pd.DataFrame, Signals]:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-02", periods=n, freq="5min", tz="UTC")
    steps = rng.normal(0.0, 0.001, n)
    close = 100.0 * np.exp(np.cumsum(steps))
    open_ = np.r_[close[0], close[:-1]]
    span = np.abs(rng.normal(0.0, 0.0005, n))
    high = np.maximum(open_, close) * (1.0 + span)
    low = np.minimum(open_, close) * (1.0 - span)
    bars = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )
    draw = rng.integers(0, 3, n)
    return bars, Signals(draw == 1, draw == 2, 0)


def _bias_stats(result) -> tuple[int, float, float]:
    values = np.array(
        [trade.r_net for trade in result.trades if trade.r_net is not None],
        dtype=float,
    )
    count = int(values.size)
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    return count, mean, mean / (std / np.sqrt(count))


def test_signals_is_compiler_alias() -> None:
    from tradinglab.discovery import compiler, fastbt

    assert fastbt.Signals is compiler.Signals


def test_bias_zero_cost_random_walk() -> None:
    bars, signals = _bias_dataset()
    result = run(
        signals,
        bars,
        ExitSpec(stop="pct", stop_mult=0.5, target="pct", target_pct=0.5),
        cfd_costs_from_bps(commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0),
        RunLimits(session_tz="UTC", weekdays=WEEK, close_at_end=False),
    )
    count, _mean, t_stat = _bias_stats(result)
    assert count >= 2_000
    assert abs(t_stat) < 3.0


def test_bias_costs_make_expectancy_negative() -> None:
    bars, signals = _bias_dataset()
    result = run(
        signals,
        bars,
        ExitSpec(stop="pct", stop_mult=0.5, target="pct", target_pct=0.5),
        cfd_costs_from_bps(commission_bps=0.5, slippage_bps=1.0, spread_bps=2.0),
        RunLimits(session_tz="UTC", weekdays=WEEK, close_at_end=False),
    )
    count, mean, _t_stat = _bias_stats(result)
    assert count >= 2_000
    assert mean < 0.0


def test_metrics_summary() -> None:
    trades = [
        SimpleNamespace(r_net=1.0, risk_price=2.0),
        SimpleNamespace(r_net=-0.5, risk_price=1.0),
        SimpleNamespace(r_net=2.0, risk_price=1.0),
    ]
    daily = pd.Series([1.0, -0.5, 2.0], index=pd.date_range("2024-01-10", periods=3))
    metrics = summarize(trades, daily)
    assert metrics["trades"] == 3
    assert metrics["expectancy_r"] == pytest.approx(2.5 / 3.0)
    assert metrics["profit_factor"] == pytest.approx(6.0)
    assert metrics["win_rate"] == pytest.approx(2.0 / 3.0)
    assert metrics["max_dd_r"] == pytest.approx(-0.5)
    assert metrics["concentration"] == pytest.approx(2.0 / 3.0)
    assert metrics["cost_plus_1pt_r"] < metrics["expectancy_r"]
    assert metrics["cost_delta_r"] == pytest.approx(
        metrics["cost_plus_1pt_r"] - metrics["expectancy_r"]
    )


def test_trade_cost_bps_is_entry_plus_exit() -> None:
    bars = _frame(n=20)
    result = run(
        _signals(bars, ["2024-01-10 09:05"]),
        bars,
        ExitSpec(stop="pct", stop_mult=1.0, target="rr", target_rr=2.0, time_exit_bars=1),
        _cost(),
        _limits(),
    )
    trade: Trade = result.trades[0]
    assert trade.cost_bps == pytest.approx(
        trade.entry_cost_bps + trade.exit_cost_bps
    )
