from __future__ import annotations

import pytest

from tradinglab.db import connect, init_db
from tradinglab.execution.paper import PaperBroker
from tradinglab.orchestrator import load_bots


def test_paper_broker_roundtrip(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = PaperBroker(db, starting_cash=10_000, commission_bps=1, slippage_bps=5)

    assert broker.cash() == 10_000
    fill = broker.submit_market("XYZ", 10, 100.0, bot="test")
    assert fill["side"] == "buy"
    assert fill["qty"] == 10
    assert broker.cash() < 9_000

    snap = broker.snapshot({"XYZ": 110.0})
    assert snap["positions"][0]["qty"] == 10
    assert snap["positions"][0]["unrealized"] > 0

    broker.submit_market("XYZ", -10, 110.0, bot="test")
    assert broker.positions() == []
    assert len(broker.equity_series()) >= 2


def test_paper_broker_guarda_riesgo_inicial(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = PaperBroker(db, starting_cash=10_000, commission_bps=0, slippage_bps=0)
    broker.submit_market(
        "XYZ", 10, 100.0, bot="test", risk_usd=50.0, stop_price=95.0
    )
    with connect(db) as con:
        row = con.execute(
            "SELECT risk_usd, stop_price FROM orders ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["risk_usd"] == pytest.approx(50.0)
    assert row["stop_price"] == pytest.approx(95.0)


def test_paper_broker_rejects_oversell(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = PaperBroker(db, starting_cash=10_000)
    with pytest.raises(RuntimeError):
        broker.submit_market("XYZ", -5, 100.0)


def test_paper_broker_rejects_insufficient_cash(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = PaperBroker(db, starting_cash=1_000)
    with pytest.raises(RuntimeError):
        broker.submit_market("XYZ", 100, 100.0)


def test_bots_catalog_loads():
    bots = load_bots()
    assert bots
    assert any(b.id == "trend-spy" for b in bots)
    assert all(b.strategy for b in bots)
