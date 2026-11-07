from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow
from tradinglab.drift import build_drift, classify_metric, classify_slippage


def test_classify_metric_ok_vigilar_deriva() -> None:
    assert classify_metric(1.0, 0.9, 0.5, 1.2)[0] == "ok"
    status, z = classify_metric(1.0, 1.012, 0.99, 1.01)
    assert status == "vigilar"
    assert z > 1.96
    assert classify_metric(1.0, 1.06, 0.99, 1.01)[0] == "deriva"
    assert classify_metric(None, 1.0, 0.5, 1.5)[0] == "sin datos"


def test_classify_slippage_estados() -> None:
    assert classify_slippage(3, 8.0, 12.0, backtest_bps=5.0)[0] == "sin datos"
    assert classify_slippage(10, 6.0, 12.0, backtest_bps=5.0)[0] == "ok"
    assert classify_slippage(10, 8.0, 12.0, backtest_bps=2.0)[0] == "vigilar"
    assert classify_slippage(10, 30.0, 50.0, backtest_bps=5.0)[0] == "deriva"


def _bot_eval(db: Path) -> None:
    with connect(db) as con:
        con.execute(
            "INSERT INTO bot_evaluations"
            "(ts, bot, strategy, universe, params, exposure, start_date, end_date, "
            "total_return, sharpe, max_drawdown, num_trades, win_rate, expectancy, status, details) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                "trend-spy",
                "trend",
                "SPY",
                "{}",
                0.35,
                "2015-01-01",
                "2026-11-07",
                0.8,
                0.8,
                -0.1,
                46,
                0.55,
                15.0,
                "mantener",
                "",
            ),
        )


def _trades_25(db: Path) -> None:
    with connect(db) as con:
        for index in range(25):
            day = (date(2026, 1, 5) + timedelta(days=index)).isoformat()
            buy_ts = f"{day}T15:00:00+00:00"
            sell_ts = f"{day}T16:00:00+00:00"
            pnl = 40.0 if index % 2 == 0 else -20.0
            exit_price = 100.0 + pnl
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (f"{day}T14:59:00+00:00", "SPY", "trend-spy", "long", 1.0, 99.95, "test"),
            )
            cur = con.execute(
                "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (buy_ts, "SPY", "buy", 1, "market", "filled", "trend-spy", "test"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
                (order_id, buy_ts, 1, 100.0, 0.0),
            )
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (f"{day}T15:59:00+00:00", "SPY", "trend-spy", "flat", 0.0, exit_price * 1.0005, "test"),
            )
            cur = con.execute(
                "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (sell_ts, "SPY", "sell", 1, "market", "filled", "trend-spy", "test"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
                (order_id, sell_ts, 1, exit_price, 0.0),
            )


def test_build_drift_sin_muestra_no_opina(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _bot_eval(db)
    payload = build_drift(db, Settings())
    row = next(item for item in payload["bots"] if item["bot"] == "trend-spy")
    assert row["live"]["n"] == 0
    assert row["edge_status"] == "sin datos"
    assert row["status"] == "sin datos"
    assert "mínimo" in " ".join(row["reasons"])


def test_build_drift_con_muestra_ci_y_slippage(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _bot_eval(db)
    _trades_25(db)
    payload = build_drift(db, Settings(), min_trades=20)
    row = next(item for item in payload["bots"] if item["bot"] == "trend-spy")
    assert row["live"]["n"] == 25
    assert row["sample_ok"] is True
    assert row["live"]["sharpe"] is not None
    assert row["live"]["sharpe_ci95"][0] <= row["live"]["sharpe_ci95"][1]
    assert row["live"]["expectancy_ci95"][0] <= row["live"]["expectancy_ci95"][1]
    assert row["slippage"]["fills"] == 50
    assert row["slippage"]["p50_bps"] == pytest.approx(5.0, abs=0.2)
    assert row["status"] in {"ok", "vigilar", "deriva"}
    assert payload["min_trades"] == 20
    assert payload["seed"] == 42

    second = build_drift(db, Settings(), min_trades=20)
    first_row = next(item for item in payload["bots"] if item["bot"] == "trend-spy")
    second_row = next(item for item in second["bots"] if item["bot"] == "trend-spy")
    assert first_row["live"] == second_row["live"]
    assert first_row["status"] == second_row["status"]


def test_api_drift_y_ui(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _bot_eval(db)
    _trades_25(db)
    data = web.LabData(
        Settings(), root=tmp_path, db_path=db, external=False
    )
    payload = data.drift(min_trades=20)
    assert payload["seed"] == 42
    assert any(row["bot"] == "trend-spy" for row in payload["bots"])
    text = web.INDEX_FILE.read_text(encoding="utf-8")
    assert 'id="bots-drift"' in text
    assert 'id="drift-meta"' in text
