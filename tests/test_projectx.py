from __future__ import annotations

import json

import httpx
import pytest

from tradinglab.db import connect, init_db
from tradinglab.execution.projectx import (
    ProjectXAuthError,
    ProjectXBroker,
    ProjectXIdentityError,
)

ACCOUNT = {
    "id": 1,
    "name": "PRAC-50K",
    "balance": 50000.0,
    "canTrade": True,
    "isVisible": True,
    "simulated": True,
}

CONTRACTS = [
    {"id": "c-1", "name": "NQZ5", "description": "E-mini Nasdaq", "tickSize": 0.25, "tickValue": 5.0, "activeContract": True},
    {"id": "c-2", "name": "NQ", "description": "Nasdaq", "tickSize": 0.25, "tickValue": 5.0, "activeContract": False},
    {"id": "c-3", "name": "NQ", "description": "Nasdaq activo", "tickSize": 0.25, "tickValue": 5.0, "activeContract": True},
]


class FakeGateway:
    def __init__(self, *, simulated: bool = True, login_ok: bool = True) -> None:
        self.simulated = simulated
        self.login_ok = login_ok
        self.calls: list[tuple[str, dict | None, str | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, payload, request.headers.get("Authorization")))

        if request.url.path == "/api/Auth/loginKey":
            if not self.login_ok:
                return httpx.Response(200, json={"success": False, "errorMessage": "bad key"})
            return httpx.Response(200, json={"success": True, "token": "tok-123"})

        if request.url.path == "/api/Account/search":
            account = dict(ACCOUNT, simulated=self.simulated)
            return httpx.Response(200, json={"success": True, "accounts": [account]})

        if request.url.path == "/api/Contract/search":
            return httpx.Response(200, json={"success": True, "contracts": CONTRACTS})

        if request.url.path == "/api/Order/place":
            return httpx.Response(200, json={"success": True, "orderId": 987})

        if request.url.path == "/api/Position/searchOpen":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "positions": [
                        {
                            "id": 5,
                            "contractId": "c-1",
                            "contractDisplayName": "NQZ5",
                            "type": 1,
                            "size": 2,
                            "averagePrice": 20500.25,
                        }
                    ],
                },
            )

        if request.url.path == "/api/Position/closeContract":
            return httpx.Response(200, json={"success": True})

        return httpx.Response(404, json={"success": False, "errorMessage": "not found"})

    def broker(self, **kwargs) -> ProjectXBroker:
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return ProjectXBroker(
            username="user",
            api_key="key",
            account_id=1,
            http=client,
            **kwargs,
        )

    def paths(self) -> list[str]:
        return [c[0] for c in self.calls]


def test_health_and_auth_header():
    gateway = FakeGateway()
    broker = gateway.broker()

    health = broker.health()

    assert health["account_id"] == 1
    assert health["simulated"] is True
    assert health["can_trade"] is True
    account_call = next(c for c in gateway.calls if c[0] == "/api/Account/search")
    assert account_call[2] == "Bearer tok-123"
    login_call = next(c for c in gateway.calls if c[0] == "/api/Auth/loginKey")
    assert login_call[2] is None


def test_login_failure():
    broker = FakeGateway(login_ok=False).broker()
    with pytest.raises(ProjectXAuthError):
        broker.health()


def test_real_account_blocked_by_default():
    broker = FakeGateway(simulated=False).broker()
    with pytest.raises(ProjectXIdentityError, match="no es simulada"):
        broker.health()


def test_real_account_requires_allow_live(monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE", raising=False)
    broker = FakeGateway(simulated=False).broker(require_simulated=False)
    with pytest.raises(ProjectXIdentityError, match="ALLOW_LIVE"):
        broker.health()

    monkeypatch.setenv("ALLOW_LIVE", "YES")
    broker2 = FakeGateway(simulated=False).broker(require_simulated=False)
    assert broker2.health()["simulated"] is False


def test_dry_run_order_does_not_post():
    gateway = FakeGateway()
    broker = gateway.broker()

    result = broker.place_order("c-1", "buy", 2, stop_loss_ticks=8, take_profit_ticks=16)

    assert result["status"] == "preview"
    assert result["dry_run"] is True
    assert "/api/Order/place" not in gateway.paths()


def test_live_order_payload_brackets_and_db(tmp_path, monkeypatch):
    monkeypatch.delenv("ALLOW_LIVE", raising=False)
    db = tmp_path / "lab.db"
    init_db(db)
    gateway = FakeGateway()
    broker = gateway.broker(dry_run=False, db_path=db)

    result = broker.place_order(
        "c-1",
        "sell",
        3,
        stop_loss_ticks=10,
        take_profit_ticks=20,
        custom_tag="lab:MNQ",
        bot="test-bot",
        reason="unit",
    )

    assert result["order_id"] == 987
    payload = next(c[1] for c in gateway.calls if c[0] == "/api/Order/place")
    assert payload["side"] == 0
    assert payload["type"] == 2
    assert payload["size"] == 3
    assert payload["stopLossBracket"] == {"ticks": 10, "type": 4}
    assert payload["takeProfitBracket"] == {"ticks": 20, "type": 1}

    with connect(db) as con:
        row = con.execute("SELECT ticker, side, qty, status, broker_id, bot FROM orders").fetchone()
    assert row["ticker"] == "c-1"
    assert row["side"] == "sell"
    assert row["qty"] == 3
    assert row["broker_id"] == "987"
    assert row["bot"] == "test-bot"


def test_resolve_contract_prefers_exact_active():
    broker = FakeGateway().broker()
    contract = broker.resolve_contract("NQ")
    assert contract["id"] == "c-3"


def test_positions_and_close_dry_run():
    gateway = FakeGateway()
    broker = gateway.broker()

    positions = broker.positions()
    assert positions[0]["side"] == "long"
    assert positions[0]["size"] == 2

    result = broker.close_position("c-1")
    assert result["status"] == "preview"
    assert "/api/Position/closeContract" not in gateway.paths()
