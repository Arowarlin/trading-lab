from __future__ import annotations

from types import SimpleNamespace

from tradinglab.db import connect, init_db
from tradinglab.execution.alpaca import AlpacaBroker


class FakeOrder:
    def __init__(
        self,
        status: str,
        *,
        filled_qty: str = "0",
        filled_avg_price: str | None = None,
        filled_at: str | None = None,
        order_id: str = "order-1",
    ) -> None:
        self.id = order_id
        self.status = SimpleNamespace(value=status)
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price
        self.filled_at = filled_at
        self.submitted_at = "2026-11-13T22:20:00+00:00"


class FakeClient:
    def __init__(self, submitted: FakeOrder, filled: FakeOrder | None = None) -> None:
        self.submitted = submitted
        self.filled = filled or submitted
        self.calls: list[str] = []

    def submit_order(self, request):
        self.calls.append("submit")
        return self.submitted

    def get_order_by_id(self, order_id):
        self.calls.append(f"get:{order_id}")
        return self.filled


def _broker(tmp_path, client: FakeClient) -> AlpacaBroker:
    broker = AlpacaBroker.__new__(AlpacaBroker)
    broker.client = client
    broker.paper = True
    broker.db_path = tmp_path / "lab.db"
    broker.account_id = "alpaca_paper"
    init_db(broker.db_path)
    return broker


def test_orden_aceptada_se_registra_y_sync_registra_el_fill(tmp_path):
    client = FakeClient(
        FakeOrder("accepted"),
        FakeOrder(
            "filled",
            filled_qty="5",
            filled_avg_price="690.50",
            filled_at="2026-11-16T14:35:00+00:00",
        ),
    )
    broker = _broker(tmp_path, client)

    result = broker.submit_market(
        "QQQ", 5, 688.17, bot="qqq-trend-f13", reason="target=1.00"
    )

    assert result["status"] == "accepted"
    assert result["recorded"] is True
    with connect(broker.db_path) as con:
        order = con.execute("SELECT * FROM orders").fetchone()
        assert order["broker_id"] == "order-1"
        assert order["bot"] == "qqq-trend-f13"
        assert order["status"] == "accepted"
        assert con.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 0

    synced = broker.sync_fills(bot="qqq-trend-f13")

    assert synced["synced"] == 1
    with connect(broker.db_path) as con:
        fill = con.execute("SELECT * FROM fills").fetchone()
        assert fill["account"] == "alpaca_paper"
        assert fill["symbol"] == "QQQ"
        assert fill["side"] == "buy"
        assert fill["bot"] == "qqq-trend-f13"
        assert fill["qty"] == 5
        assert fill["price"] == 690.5
        assert fill["order_id"] == order["id"]

    again = broker.sync_fills(bot="qqq-trend-f13")
    assert again["synced"] == 0
    with connect(broker.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1


def test_fill_inmediato_no_se_duplica(tmp_path):
    client = FakeClient(
        FakeOrder(
            "filled",
            filled_qty="5",
            filled_avg_price="690.50",
            filled_at="2026-11-16T14:35:00+00:00",
        )
    )
    broker = _broker(tmp_path, client)

    result = broker.submit_market(
        "QQQ", 5, 688.17, bot="qqq-trend-f13", reason="target=1.00"
    )

    assert result["status"] == "filled"
    assert result["filled_qty"] == 5
    with connect(broker.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1

    assert broker.sync_fills(bot="qqq-trend-f13")["synced"] == 0
