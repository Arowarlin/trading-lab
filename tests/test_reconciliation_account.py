from __future__ import annotations

from tradinglab.db import connect, init_db
from tradinglab.reconciliation import expected_positions, last_reconciliation, reconcile_account


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
                {
                    "ticker": ticker,
                    "qty": qty,
                    "avg_price": 100.0,
                    "value": qty * 100.0,
                    "unrealized": 0.0,
                }
                for ticker, qty in self.positions.items()
            ],
        }


def _fill(db, *, bot: str, symbol: str, side: str, qty: float, account="alpaca_paper"):
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO fills(order_id, ts, qty, price, commission, bot, account, "
            "symbol, side, volume) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                1,
                "2026-11-16T14:35:00+00:00",
                qty,
                100.0,
                0.0,
                bot,
                account,
                symbol,
                side,
                qty,
            ),
        )


def test_reconciliacion_separa_f13_del_daytrader(tmp_path):
    db = tmp_path / "lab.db"
    _fill(db, bot="qqq-trend-f13", symbol="QQQ", side="buy", qty=5)
    _fill(db, bot="daytrader", symbol="AAPL", side="buy", qty=10)
    broker = FakeBroker(100_000.0, {"QQQ": 5.0, "AAPL": 10.0})

    result = reconcile_account(broker, db, account_id="alpaca_paper")

    assert result.status == "ok"
    assert result.diff_positions == 0
    assert result.broker_positions == 2
    assert result.db_positions == 2
    assert "qqq-trend-f13: QQQ=5" in result.details
    assert "daytrader: AAPL=10" in result.details
    assert last_reconciliation(db)["source"] == "account:alpaca_paper"


def test_reconciliacion_detecta_cantidad_distinta(tmp_path):
    db = tmp_path / "lab.db"
    _fill(db, bot="qqq-trend-f13", symbol="QQQ", side="buy", qty=5)
    broker = FakeBroker(100_000.0, {"QQQ": 6.0})

    result = reconcile_account(broker, db, account_id="alpaca_paper")

    assert result.status == "mismatch"
    assert result.diff_positions == 1
    assert "QQQ broker=6 db=5" in result.details


def test_reconciliacion_detecta_posicion_ajena(tmp_path):
    db = tmp_path / "lab.db"
    _fill(db, bot="qqq-trend-f13", symbol="QQQ", side="buy", qty=5)
    broker = FakeBroker(100_000.0, {"QQQ": 5.0, "TSLA": 2.0})

    result = reconcile_account(broker, db, account_id="alpaca_paper")

    assert result.status == "mismatch"
    assert result.diff_positions == 1
    assert "TSLA broker=2 db=0" in result.details


def test_reconciliacion_solo_lee_la_cuenta_pedida(tmp_path):
    db = tmp_path / "lab.db"
    _fill(db, bot="qqq-trend-f13", symbol="QQQ", side="buy", qty=5)
    _fill(
        db,
        bot="qqq-trend-f13",
        symbol="SPY",
        side="buy",
        qty=99,
        account="paper_main",
    )

    expected, by_bot = expected_positions(db, account_id="alpaca_paper")

    assert expected == {"QQQ": 5.0}
    assert by_bot == {"qqq-trend-f13": {"QQQ": 5.0}}
