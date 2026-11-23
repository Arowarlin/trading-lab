"""Tests sintéticos de la deriva demo vs backtest por carril (R7b)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from tradinglab.drift import (
    DemoTrade,
    LaneSpec,
    _ai_report,
    _match_ea_demo,
    _metric_summary,
    _slip_bps,
    _summarize_lane,
    _tick_execution_slip,
    load_ea_trades,
    load_forward_trades,
    replay_forward_trade,
    scan_forward_days,
)


def _bars(opens, *, closes=None, highs=None, lows=None, freq="15min") -> pd.DataFrame:
    count = len(opens)
    closes = closes or list(opens)
    highs = highs or [max(open_, close) + 0.5 for open_, close in zip(opens, closes)]
    lows = lows or [min(open_, close) - 0.5 for open_, close in zip(opens, closes)]
    index = pd.date_range(
        "2026-01-05 00:00", periods=count, freq=freq, tz="UTC"
    )
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1.0] * count,
        },
        index=index,
    )


def _spec(**overrides) -> LaneSpec:
    values = {
        "id": "test-forward",
        "label": "test forward",
        "kind": "forward",
        "bot": "forward:test",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "strategy": "pullback",
        "params": (("fast", 2), ("slow", 3)),
        "stop_atr": 2.0,
        "entry_start": time(0, 0, tzinfo=timezone.utc),
        "entry_end": time(4, 0, tzinfo=timezone.utc),
        "force_exit": time(4, 0, tzinfo=timezone.utc),
        "magic": 1,
        "backtest": "forward_replay",
    }
    values.update(overrides)
    return LaneSpec(**values)


def _op(day, *, demo=None, bt=None, signal=0, match=None, slip=None, note=""):
    return {
        "day": day,
        "demo_ts": demo.entry_ts.isoformat() if demo else None,
        "demo_side": "long" if demo and demo.side > 0 else "short" if demo else None,
        "demo_entry": demo.entry if demo else None,
        "demo_exit": demo.exit if demo else None,
        "demo_r": demo.r if demo else None,
        "demo_closed": bool(demo and demo.closed),
        "bt_ts": bt["entry_ts"].isoformat() if bt else None,
        "bt_side": "long" if bt and bt["side"] > 0 else "short" if bt else None,
        "bt_entry": bt["entry"] if bt else None,
        "bt_exit": bt["exit"] if bt else None,
        "bt_r": bt["r"] if bt else None,
        "bt_signal": signal,
        "match": match,
        "slip_bps": slip,
        "spread_bps": None,
        "spread_price": None,
        "assumed_slip_bps": 0.5,
        "assumed_spread_bps": 0.1,
        "note": note,
    }


def test_replay_forward_identical_to_backtest():
    bars = _bars([100, 100, 100, 100, 100, 104, 104, 104])
    target = pd.Series([0, 0, 1, 1, 0, 0, 0, 0], index=bars.index, dtype=float)
    atr_series = pd.Series([1.0] * len(bars), index=bars.index)
    trade = replay_forward_trade(
        bars,
        target,
        atr_series,
        2,
        1,
        stop_atr=2.0,
        max_hold=None,
        force_exit=None,
        timeframe_minutes=15,
    )
    assert trade is not None
    assert trade["entry"] == 100.0
    assert trade["stop"] == 98.0
    assert trade["exit"] == 104.0
    assert trade["r"] == pytest.approx(2.0)
    demo = DemoTrade(
        side=1,
        entry_ts=trade["entry_ts"],
        entry=100.0,
        qty=1.0,
        exit_ts=trade["exit_ts"],
        exit=104.0,
        stop=98.0,
        r=2.0,
    )
    operation = _op(
        "2026-01-05",
        demo=demo,
        bt=trade,
        signal=1,
        match=True,
        slip=0.0,
        note="coincide",
    )
    report = _summarize_lane(
        spec=_spec(),
        demo=[demo],
        operations=[operation],
        bt_signals=1,
        bt_trades=[trade],
    )
    assert report["status"] == "medido"
    assert report["match"]["matched"] == 1
    assert report["r"]["demo_total"] == pytest.approx(2.0)
    assert report["r"]["backtest_total"] == pytest.approx(2.0)
    assert report["r"]["drift_total"] == pytest.approx(0.0)


def test_slippage_known_and_percentiles():
    assert _slip_bps(1, 100.05, 100.0) == pytest.approx(5.0)
    assert _slip_bps(-1, 99.95, 100.0) == pytest.approx(5.0)
    assert _slip_bps(1, 100.0, None) is None
    summary = _metric_summary([5.0, 1.0, 3.0, 2.0, 100.0])
    assert summary["n"] == 5
    assert summary["p50"] == pytest.approx(3.0)
    assert summary["p95"] > 80.0


class _FakeTicks:
    def __init__(self, bid: float, ask: float) -> None:
        self.bid = bid
        self.ask = ask

    def ticks(self, symbol, start, end):
        return pd.DataFrame(
            {
                "ts": [pd.Timestamp("2026-01-05T10:00:00Z")],
                "bid": [self.bid],
                "ask": [self.ask],
            }
        )


def test_tick_execution_slippage_exact():
    market = _FakeTicks(bid=100.0, ask=100.05)
    moment = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    long = _tick_execution_slip(market, "EURUSD", moment, 1, 100.10)
    short = _tick_execution_slip(market, "EURUSD", moment, -1, 99.95)
    assert long is not None and long["slip_bps"] == pytest.approx(5.0, rel=1e-3)
    assert short is not None and short["slip_bps"] == pytest.approx(5.0, rel=1e-3)


def test_missed_and_extra_signals_counted():
    demo = DemoTrade(
        side=1,
        entry_ts=datetime(2026, 1, 5, 10, tzinfo=timezone.utc),
        entry=100.0,
        qty=1.0,
        exit_ts=datetime(2026, 1, 5, 11, tzinfo=timezone.utc),
        exit=102.0,
        stop=98.0,
        r=0.5,
    )
    bt_match = {
        "entry_ts": datetime(2026, 1, 5, 10, tzinfo=timezone.utc),
        "exit_ts": datetime(2026, 1, 5, 11, tzinfo=timezone.utc),
        "side": 1,
        "entry": 100.0,
        "exit": 102.0,
        "r": 0.5,
    }
    bt_missed = {
        "entry_ts": datetime(2026, 1, 6, 10, tzinfo=timezone.utc),
        "exit_ts": datetime(2026, 1, 6, 11, tzinfo=timezone.utc),
        "side": -1,
        "entry": 100.0,
        "exit": 99.0,
        "r": 0.5,
    }
    demo_extra = DemoTrade(
        side=1,
        entry_ts=datetime(2026, 1, 7, 10, tzinfo=timezone.utc),
        entry=100.0,
        qty=1.0,
        stop=98.0,
    )
    demo_opposite = DemoTrade(
        side=1,
        entry_ts=datetime(2026, 1, 8, 10, tzinfo=timezone.utc),
        entry=100.0,
        qty=1.0,
        exit_ts=datetime(2026, 1, 8, 11, tzinfo=timezone.utc),
        exit=99.0,
        stop=98.0,
        r=-0.5,
    )
    bt_opposite = {
        "entry_ts": datetime(2026, 1, 8, 10, tzinfo=timezone.utc),
        "exit_ts": datetime(2026, 1, 8, 11, tzinfo=timezone.utc),
        "side": -1,
        "entry": 100.0,
        "exit": 102.0,
        "r": 1.0,
    }
    operations = [
        _op("2026-01-05", demo=demo, bt=bt_match, signal=1, match=True, slip=0.0),
        _op("2026-01-06", demo=None, bt=bt_missed, signal=-1, match=None),
        _op("2026-01-07", demo=demo_extra, bt=None, signal=0, match=False, slip=1.0),
        _op(
            "2026-01-08",
            demo=demo_opposite,
            bt=bt_opposite,
            signal=-1,
            match=False,
            slip=2.0,
        ),
    ]
    report = _summarize_lane(
        spec=_spec(),
        demo=[demo, demo_extra, demo_opposite],
        operations=operations,
        bt_signals=3,
        bt_trades=[bt_match, bt_missed, bt_opposite],
    )
    assert report["match"]["matched"] == 1
    assert report["match"]["missed"] == 1
    assert report["match"]["extra"] == 1
    assert report["match"]["opposite"] == 1
    assert report["match"]["union_days"] == 4
    assert report["match"]["match_pct"] == pytest.approx(1 / 4)


def test_scan_forward_days_uses_entry_window():
    bars = _bars([100, 100, 100, 100, 100, 103, 103])
    target = pd.Series([0, 0, 1, 1, 0, 0, 0], index=bars.index, dtype=float)
    atr_series = pd.Series([1.0] * len(bars), index=bars.index)
    spec = _spec()
    signal = scan_forward_days(
        bars,
        target,
        atr_series,
        spec,
        date(2026, 1, 5),
        date(2026, 1, 5),
    )
    assert list(signal) == [date(2026, 1, 5)]
    assert signal[date(2026, 1, 5)]["side"] == 1
    assert signal[date(2026, 1, 5)]["trade"]["r"] == pytest.approx(1.5)


def _forward_db(tmp_path):
    path = tmp_path / "lab.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE signals (
            ts TEXT, ticker TEXT, bot TEXT, side TEXT, strength REAL,
            price REAL, reason TEXT
        );
        CREATE TABLE orders (
            ts TEXT, ticker TEXT, side TEXT, qty REAL, stop_price REAL,
            risk_usd REAL, bot TEXT, broker_id TEXT
        );
        CREATE TABLE fills (
            ts TEXT, price REAL, qty REAL, commission REAL, swap REAL,
            contract_size REAL, bot TEXT, side TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO signals VALUES (?,?,?,?,?,?,?)",
        (
            "2026-01-05T10:00:00+00:00",
            "EURUSD",
            "forward:test",
            "buy",
            1.0,
            100.0,
            "open_long executed: target=+1 ATR=1 stop=2ATR",
        ),
    )
    con.execute(
        "INSERT INTO signals VALUES (?,?,?,?,?,?,?)",
        (
            "2026-01-05T12:00:00+00:00",
            "EURUSD",
            "forward:test",
            "flat",
            0.0,
            104.0,
            "closed ticket=123 reason=señal plana",
        ),
    )
    con.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
        (
            "2026-01-05T10:00:00+00:00",
            "EURUSD",
            "buy",
            1.0,
            98.0,
            200.0,
            "forward:test",
            "123",
        ),
    )
    con.execute(
        "INSERT INTO fills VALUES (?,?,?,?,?,?,?,?)",
        (
            "2026-01-05T10:00:00+00:00",
            100.0,
            1.0,
            0.0,
            0.0,
            1.0,
            "forward:test",
            "buy",
        ),
    )
    con.commit()
    con.close()
    return path


def test_forward_inventory_from_signals_is_read_only(tmp_path):
    path = _forward_db(tmp_path)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        trades = load_forward_trades(con, _spec())
        with pytest.raises(sqlite3.OperationalError):
            con.execute("INSERT INTO signals(ts) VALUES ('x')")
    finally:
        con.close()
    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == 1
    assert trade.entry == pytest.approx(100.0)
    assert trade.exit == pytest.approx(104.0)
    assert trade.stop == pytest.approx(98.0)
    assert trade.r == pytest.approx(2.0)
    assert trade.closed is True


def _ea_db(tmp_path):
    path = tmp_path / "lab.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, price REAL, qty REAL, commission REAL, swap REAL,
            contract_size REAL, bot TEXT, side TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO fills(ts, price, qty, commission, swap, contract_size, bot, side) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "2026-01-05T10:00:00+00:00",
            100.0,
            1.0,
            0.0,
            0.0,
            1.0,
            "ea:test",
            "sell",
        ),
    )
    con.execute(
        "INSERT INTO fills(ts, price, qty, commission, swap, contract_size, bot, side) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "2026-01-05T11:00:00+00:00",
            90.0,
            1.0,
            0.0,
            0.0,
            1.0,
            "ea:test",
            "buy",
        ),
    )
    con.commit()
    con.close()
    return path


def test_ea_inventory_and_match(tmp_path):
    path = _ea_db(tmp_path)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        trades = load_ea_trades(con, _spec(bot="ea:test", kind="ea"), risk_fraction=0.01)
    finally:
        con.close()
    assert len(trades) == 1
    assert trades[0].r == pytest.approx(0.01)
    backtest = [
        {
            "entry_ts": datetime(2026, 1, 5, 10, 5, tzinfo=timezone.utc),
            "exit_ts": datetime(2026, 1, 5, 11, 5, tzinfo=timezone.utc),
            "side": -1,
            "entry": 100.0,
            "exit": 90.0,
            "r": 0.01,
        }
    ]
    matched = _match_ea_demo(trades, backtest)
    assert matched[0]["match"] is True
    opposite = _match_ea_demo(
        trades, [{**backtest[0], "side": 1, "exit": 110.0, "r": -0.01}]
    )
    assert opposite[0]["match"] is False


def test_ai_report_is_registry_only(tmp_path):
    path = tmp_path / "lab.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE ai_trades (ts TEXT, style TEXT, status TEXT, result_r REAL, r_multiple REAL)"
    )
    con.executemany(
        "INSERT INTO ai_trades VALUES (?,?,?,?,?)",
        [
            ("2026-01-05T10:00:00+00:00", "scalping", "closed", 1.5, 1.5),
            ("2026-01-06T10:00:00+00:00", "swing", "proposed", None, None),
        ],
    )
    con.commit()
    con.close()
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        report = _ai_report(
            con,
            _spec(
                id="ai-trader",
                label="ai",
                kind="ai",
                bot="ai:",
                symbol="*",
                timeframe="*",
                backtest="none",
            ),
        )
    finally:
        con.close()
    assert report["status"] == "registro"
    assert report["backtest_available"] is False
    assert report["demo"]["n"] == 2
    assert report["r"]["demo_total"] == pytest.approx(1.5)
    assert report["styles"][0]["n"] == 1


def test_lane_specs_include_all_running_lanes():
    from tradinglab.drift import lane_specs

    specs = lane_specs()
    ids = {spec.id for spec in specs}
    assert "eurusd-london-pullback-forward" in ids
    assert "usdjpy-tokyo-breakout-forward" in ids
    assert "us100-trend-d1" in ids
    assert "us100-ftmo1" in ids
    assert "ai-trader" in ids
