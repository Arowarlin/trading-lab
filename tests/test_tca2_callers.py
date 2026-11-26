"""TL2-TCA2 · signal_price desde ai_trader y paper."""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.ai_trader import execute, load_config
from tradinglab.db import connect, init_db
from tradinglab.execution.paper import PaperBroker


class _Broker:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def health(self):
        return {"mode": "demo", "equity": 100_000.0}

    def rates(self, symbol, timeframe, count):
        end = pd.Timestamp.now(tz="UTC").floor("5min") - pd.Timedelta(minutes=5)
        index = pd.date_range(end=end, periods=100, freq="5min", tz="UTC")
        close = [101.0] * len(index)
        return pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close},
            index=index,
        )

    def tick(self, symbol):
        return {"bid": 100.9, "ask": 101.1}

    def submit_market(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"order_id": 123, "price": 101.1, "volume": 1.0}

    def positions(self, symbol=None):
        return []

    def history_deals(self, start, end):
        return []


def _proposal(db, *, entry=101.0):
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, symbol, setup, side, thesis, "
            "confidence, playbook_version, entry, sl, tp, volume, risk_usd, magic, "
            "status, style, timeframe, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "p-tca2",
                pd.Timestamp.now(tz="UTC").isoformat(),
                "US100.cash",
                "orb_5m",
                "buy",
                "prueba tca2",
                3,
                1,
                entry,
                99.0,
                105.0,
                1.0,
                100.0,
                20261191,
                "proposed",
                "scalping",
                "M5",
                pd.Timestamp.now(tz="UTC").isoformat(),
                pd.Timestamp.now(tz="UTC").isoformat(),
            ),
        )


def test_ai_trader_pasa_el_precio_de_la_propuesta(tmp_path):
    db = tmp_path / "lab.db"
    _proposal(db)
    broker = _Broker()

    execute("p-tca2", broker=broker, config=load_config(), db_path=db)

    assert broker.calls
    args, kwargs = broker.calls[0]
    assert args[0] == "US100.cash"
    assert kwargs["signal_price"] == pytest.approx(101.0)
    assert "age_ms=" in kwargs["reason"]


def test_paper_sin_signal_price_conserva_el_comportamiento_previo(tmp_path):
    db = tmp_path / "paper.db"
    init_db(db)
    broker = PaperBroker(db, commission_bps=0.0, slippage_bps=0.0)

    broker.submit_market("SPY", 10, 100.0, bot="manual")

    with connect(db) as con:
        row = con.execute(
            "SELECT signal_px, order_px, fill_px, slippage_bps, tca_version FROM tca"
        ).fetchone()
    assert row["signal_px"] == pytest.approx(100.0)
    assert row["order_px"] == pytest.approx(100.0)
    assert row["fill_px"] == pytest.approx(100.0)
    assert row["slippage_bps"] == pytest.approx(0.0)
    assert row["tca_version"] == 2


def test_paper_usa_signal_price_para_medir_slippage(tmp_path):
    db = tmp_path / "paper.db"
    init_db(db)
    broker = PaperBroker(db, commission_bps=0.0, slippage_bps=0.0)

    broker.submit_market("SPY", 10, 100.0, bot="manual", signal_price=99.5)

    with connect(db) as con:
        row = con.execute(
            "SELECT signal_px, order_px, fill_px, slippage_bps FROM tca"
        ).fetchone()
    assert row["signal_px"] == pytest.approx(99.5)
    assert row["order_px"] == pytest.approx(100.0)
    assert row["fill_px"] == pytest.approx(100.0)
    assert row["slippage_bps"] == pytest.approx(50.251, abs=0.01)
