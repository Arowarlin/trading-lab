from __future__ import annotations

import pytest

from tradinglab.db import connect, init_db
from tradinglab.reconciliation import last_reconciliation, reconcile


class FakeBroker:
    def __init__(self, equity: float, positions: dict[str, float]) -> None:
        self.equity = equity
        self.positions = positions

    def snapshot(self, prices=None):
        return {
            "equity": self.equity,
            "cash": self.equity,
            "positions_value": 0.0,
            "positions": [
                {"ticker": t, "qty": q, "avg_price": 100.0, "value": q * 100.0, "unrealized": 0.0}
                for t, q in self.positions.items()
            ],
        }


def _seed(db, positions: dict[str, float], equity: float) -> None:
    init_db(db)
    with connect(db) as con:
        for ticker, qty in positions.items():
            con.execute(
                "INSERT INTO positions(ticker, qty, avg_price, updated_at) VALUES(?,?,?,?)",
                (ticker, qty, 100.0, "2026-11-07T00:00:00+00:00"),
            )
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            ("2026-11-07T00:00:00+00:00", equity, 0.0, equity),
        )


def test_reconciliacion_ok(tmp_path):
    db = tmp_path / "lab.db"
    _seed(db, {"SPY": 10.0}, 100_000.0)
    result = reconcile(FakeBroker(100_000.0, {"SPY": 10.0}), db, source="test")
    assert result.status == "ok"
    assert result.diff_positions == 0
    assert last_reconciliation(db)["status"] == "ok"


def test_reconciliacion_detecta_diferencias(tmp_path):
    db = tmp_path / "lab.db"
    _seed(db, {"SPY": 10.0}, 100_000.0)
    result = reconcile(FakeBroker(99_000.0, {"SPY": 11.0}), db, source="test")
    assert result.status == "mismatch"
    assert result.diff_positions == 1
    assert result.diff_equity == pytest.approx(-1_000.0)
    assert "posiciones" in result.details
