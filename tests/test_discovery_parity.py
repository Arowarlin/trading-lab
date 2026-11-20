"""Paridad de fastbt con los motores protegidos (solo lectura).

* ``backtest_intraday`` es una serie close-to-close; se replica con
  ``execution="close_signal"`` y su ledger de barras.
* ``run_event_backtest`` es el motor de eventos; se replica con
  ``execution="open_next"`` (el modo por defecto).
* numba y Python comparten la misma función: no puede haber diferencias.
"""

from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery.fastbt import (
    HAVE_NUMBA,
    ExitSpec,
    RunLimits,
    Signals,
    cfd_costs_from_bps,
    run,
    set_backend,
)
from tradinglab.intraday import backtest_intraday, run_event_backtest

WEEK = tuple(range(7))
SIGNAL_TS = pd.Timestamp("2024-01-10 09:55", tz="UTC")
END_TS = pd.Timestamp("2024-01-10 16:00", tz="UTC")


def _walk(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-10 14:00", periods=n, freq="5min", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.05, n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.02
    low = np.minimum(open_, close) - 0.02
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def _event_frame(case: str) -> pd.DataFrame:
    index = pd.date_range("2024-01-10 09:30", "2024-01-10 16:00", freq="5min", tz="UTC")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0}, index=index
    )
    stamp = pd.Timestamp("2024-01-10 10:30", tz="UTC")
    if case == "tie":
        bars.loc[stamp, ["open", "high", "low", "close"]] = [100.0, 103.0, 98.0, 100.5]
    elif case == "gap_stop":
        bars.loc[stamp, ["open", "high", "low", "close"]] = [98.5, 99.5, 98.0, 98.8]
    elif case == "gap_target":
        bars.loc[stamp, ["open", "high", "low", "close"]] = [103.0, 104.0, 102.5, 103.2]
    elif case == "short_gate":
        bars.loc[stamp, ["open", "high", "low", "close"]] = [99.2, 99.5, 98.95, 99.1]
    elif case == "short_ok":
        bars.loc[stamp, ["open", "high", "low", "close"]] = [99.2, 99.5, 98.5, 98.8]
    elif case == "force":
        bars.loc[
            pd.Timestamp("2024-01-10 15:45", tz="UTC"), "close"
        ] = 100.7
    else:  # pragma: no cover
        raise AssertionError(case)
    return bars


def _one_signal(bars: pd.DataFrame, side: str) -> tuple[np.ndarray, np.ndarray]:
    n = len(bars)
    long = np.zeros(n, dtype=bool)
    short = np.zeros(n, dtype=bool)
    position = bars.index.get_loc(SIGNAL_TS)
    (long if side == "buy" else short)[position] = True
    return long, short


def test_series_returns_match_backtest_intraday() -> None:
    bars = _walk()
    n = len(bars)
    signal = np.zeros(n, dtype=bool)
    signal[10:60] = True
    signal[100:160] = True
    signal[250:300] = True
    target = pd.Series(signal.astype(float), index=bars.index)

    reference = backtest_intraday(
        bars,
        target,
        timeframe="M5",
        commission_bps=1.0,
        slippage_bps=2.0,
        spread_override_bps=10.0,
        point=0.01,
        spread_override_reliable=True,
    )
    cost = cfd_costs_from_bps(
        commission_bps=1.0, slippage_bps=2.0, spread_bps=10.0
    )
    result = run(
        Signals(signal, np.zeros(n, dtype=bool)),
        bars,
        ExitSpec(stop=None, target=None),
        cost,
        RunLimits(
            execution="close_signal",
            series_ledger=True,
            weekdays=WEEK,
        ),
    )

    assert result.bar_returns is not None
    diff = float((result.bar_returns - reference["returns"]).abs().max())
    assert diff <= 1e-12
    assert [(t.entry_index, t.exit_index) for t in result.trades] == [
        (10, 60),
        (100, 160),
        (250, 300),
    ]
    assert result.rejected == 0


@pytest.mark.parametrize(
    ("case", "side", "stop", "target"),
    [
        ("tie", "buy", 99.0, 102.0),
        ("gap_stop", "buy", 99.0, 102.0),
        ("gap_target", "buy", 99.0, 102.0),
        ("short_gate", "sell", 101.0, 99.0),
        ("short_ok", "sell", 101.0, 99.0),
        ("force", "buy", 99.0, 102.0),
    ],
)
def test_event_matches_run_event_backtest(
    case: str, side: str, stop: float, target: float
) -> None:
    bars = _event_frame(case)
    order = {
        "side": side,
        "type": "market",
        "stop": stop,
        "target": target,
        "created_at": SIGNAL_TS,
        "expires_at": END_TS,
    }
    reference = run_event_backtest(
        bars,
        [order],
        point=0.01,
        commission_bps=1.0,
        spread_bps=10.0,
        slippage_bps=2.0,
        max_trades_per_day=5,
        force_exit_time=time(15, 45),
        session_offset_hours=0.0,
        session_window=(time(0, 0), time(0, 0)),
        session_tz="UTC",
        session_weekdays=WEEK,
        asset_class="cfd",
    )
    assert reference["trades"], "el motor protegido no generó la operación de prueba"

    long, short = _one_signal(bars, side)
    cost = cfd_costs_from_bps(
        commission_bps=1.0, slippage_bps=2.0, spread_bps=10.0
    )
    result = run(
        Signals(long, short),
        bars,
        ExitSpec(stop="fixed", stop_price=stop, target="fixed", target_price=target),
        cost,
        RunLimits(
            session_tz="UTC",
            flat_at="15:45",
            weekdays=WEEK,
            max_trades_per_day=5,
            close_at_end=False,
        ),
    )
    assert result.rejected == 0
    assert len(result.trades) == len(reference["trades"]) == 1

    expected = reference["trades"][0]
    got = result.trades[0]
    assert got.side == ("long" if expected["side"] == "buy" else "short")
    assert got.entry_time == expected["entry_time"]
    assert got.exit_time == expected["exit_time"]
    assert got.entry_price == expected["entry_price"]
    assert got.exit_price == expected["exit_price"]
    assert got.reason == expected["exit_reason"]
    assert got.entry_cost_bps == pytest.approx(
        sum(expected["entry_costs"].values()), abs=1e-12
    )
    assert got.exit_cost_bps == pytest.approx(
        sum(expected["exit_costs"].values()), abs=1e-12
    )


def test_numba_and_python_identical() -> None:
    if not HAVE_NUMBA:
        pytest.skip("numba no está instalado")
    bars = _walk(n=300, seed=11)
    n = len(bars)
    signal = np.zeros(n, dtype=bool)
    signal[20:60] = True
    signal[140:210] = True
    signals = Signals(signal, np.zeros(n, dtype=bool))
    spec = ExitSpec(
        stop="atr",
        stop_mult=1.2,
        stop_n=10,
        target="rr",
        target_rr=1.8,
        breakeven_at_r=0.8,
        trail_atr_mult=1.0,
        trail_n=10,
        time_exit_bars=30,
    )
    cost = cfd_costs_from_bps(commission_bps=0.5, slippage_bps=1.0, spread_bps=4.0)
    limits = RunLimits(
        session_tz="UTC", weekdays=WEEK, max_trades_per_day=2, close_at_end=True
    )

    set_backend("python")
    python_result = run(signals, bars, spec, cost, limits)
    set_backend("numba")
    numba_result = run(signals, bars, spec, cost, limits)

    assert python_result.backend == "python"
    assert numba_result.backend == "numba"
    assert len(python_result.trades) == len(numba_result.trades) > 0
    for left, right in zip(python_result.trades, numba_result.trades):
        assert left.side == right.side
        assert left.entry_index == right.entry_index
        assert left.exit_index == right.exit_index
        assert left.reason == right.reason
        assert left.entry_price == right.entry_price
        assert left.exit_price == right.exit_price
        assert left.stop == right.stop
        assert left.target == right.target
        assert left.entry_cost_bps == right.entry_cost_bps
        assert left.exit_cost_bps == right.exit_cost_bps
        assert left.r_gross == right.r_gross
        assert left.r_cost == right.r_cost
        assert left.r_net == right.r_net
    assert python_result.rejected == numba_result.rejected
    assert python_result.daily_r.equals(numba_result.daily_r)
