from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.f13 import (
    config_check,
    config_hash,
    execution_metrics,
    freeze,
    load_criteria,
    record_snapshot,
    signal_check,
    status,
)
from tradinglab.orchestrator import BotSpec


class FakeBroker:
    def snapshot(self, prices=None):
        return {
            "equity": 100_100.0,
            "cash": 90_000.0,
            "positions_value": 10_100.0,
            "positions": [{"ticker": "QQQ", "qty": 10.0}],
        }


def test_hash_y_criterios():
    assert len(config_hash()) == 64
    criteria = load_criteria()
    assert criteria["window_weeks"] == 8
    assert "hard_stops" in criteria
    assert config_hash() == config_hash()


def test_freeze_y_status(tmp_path):
    db = tmp_path / "lab.db"
    row = freeze(db, bot="qqq-trend-f13", symbol="QQQ", start_date="2026-11-09")
    assert row["bot"] == "qqq-trend-f13"
    assert len(row["config_hash"]) == 64
    assert status(db)["start_date"] == "2026-11-09"
    assert config_check(db)["ok"] is True


def test_record_snapshot(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    result = record_snapshot(db, FakeBroker(), bot="qqq-trend-f13", spy_close=600.0)
    assert result["equity"] == pytest.approx(100_100.0)
    with connect(db) as con:
        row = con.execute("SELECT * FROM f13_metrics").fetchone()
    assert row["open_positions"] == 1
    assert row["notes"] == "qqq-trend-f13"


def test_execution_metrics_slippage(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
            "VALUES(?,?,?,?,?,?,?)",
            ("2026-11-07T14:00:00+00:00", "QQQ", "qqq-trend-f13", "long", 1.0, 100.0, "test"),
        )
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status, bot) VALUES(?,?,?,?,?,?)",
            ("2026-11-07T14:30:00+00:00", "QQQ", "buy", 10, "filled", "qqq-trend-f13"),
        )
        order_id = con.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        con.execute(
            "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
            (order_id, "2026-11-07T14:30:00+00:00", 10, 101.0, 0.0),
        )
    metrics = execution_metrics(db, bot="qqq-trend-f13", start_date="2026-11-01")
    assert metrics["fills"] == 1
    assert metrics["slippage_p50_bps"] == pytest.approx(100.0)
    assert metrics["size_error_max"] == pytest.approx(0.0)


def test_signal_check_recalcula(monkeypatch, tmp_path):
    dates = pd.date_range("2024-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "open": range(100, 400),
            "high": range(101, 401),
            "low": range(99, 399),
            "close": [100 + i for i in range(300)],
            "volume": [1_000] * 300,
        },
        index=dates,
    )
    monkeypatch.setattr("tradinglab.data.fetch", lambda *args, **kwargs: df)
    spec = BotSpec(
        id="qqq-trend-f13",
        type="deterministic",
        strategy="trend",
        universe=["QQQ"],
        enabled=False,
        params={"fast": 50, "slow": 200, "regime": 200},
        exposure=0.35,
    )
    result = signal_check(Settings(), spec, tmp_path / "lab.db")
    assert result["ok"]
    assert result["target"] == pytest.approx(1.0)
    assert result["match"] is None
