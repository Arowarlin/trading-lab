from __future__ import annotations

import pytest

from tradinglab.execution.tradestation import (
    SIM_MARKER,
    TradeStationAuthError,
    TradeStationBroker,
    TradeStationError,
    TradeStationIdentityError,
)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload if payload is not None else {}

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, api_status=None):
        self.api_status = list(api_status or [])
        self.token_calls = 0
        self.requests: list[tuple[str, str]] = []

    def post(self, url, data=None, headers=None):
        self.token_calls += 1
        assert data["grant_type"] == "refresh_token"
        return FakeResponse(
            200,
            {"access_token": f"token-{self.token_calls}", "expires_in": 1200},
        )

    def request(self, method, url, params=None, json=None, headers=None):
        self.requests.append((method, url))
        if self.api_status:
            status = self.api_status.pop(0)
            if status == 401:
                return FakeResponse(401, {"error": "expired"})
        if url.endswith("/brokerage/accounts"):
            return FakeResponse(
                200,
                {
                    "Accounts": [
                        {
                            "AccountID": "SIM-123",
                            "AccountType": "Simulated",
                            "Currency": "USD",
                            "Status": "Active",
                        }
                    ]
                },
            )
        if url.endswith("/balances"):
            return FakeResponse(
                200,
                {
                    "Balances": [
                        {
                            "AccountID": "SIM-123",
                            "BalanceDetail": {"Equity": 100000, "CashBalance": 90000},
                        }
                    ]
                },
            )
        if url.endswith("/positions"):
            return FakeResponse(
                200,
                {
                    "Positions": [
                        {
                            "Symbol": "SPY",
                            "Quantity": "10",
                            "AveragePrice": "500",
                        }
                    ]
                },
            )
        if "/marketdata/quotes/" in url:
            return FakeResponse(200, {"Quotes": [{"Symbol": "SPY", "Last": 501}]})
        return FakeResponse(404, {"error": "not found"})

    def close(self):
        pass


def _broker(client, **kwargs):
    kwargs.setdefault("account_id", "SIM-123")
    return TradeStationBroker(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        base_url=f"https://{SIM_MARKER}/v3",
        http=client,
        **kwargs,
    )


def test_health_cuenta_y_lectura():
    client = FakeClient()
    broker = _broker(client)
    health = broker.health()
    assert health["ok"] is True
    assert health["simulated"] is True
    assert health["account_id"] == "SIM-123"
    assert client.token_calls == 1
    assert broker.accounts()[0]["AccountType"] == "Simulated"
    snapshot = broker.snapshot()
    assert snapshot["equity"] == pytest.approx(100000)
    assert snapshot["cash"] == pytest.approx(90000)
    assert snapshot["positions_value"] == pytest.approx(10000)
    assert broker.quotes(["spy"])[0]["Last"] == 501
    assert client.token_calls == 1  # el token se reutiliza


def test_refresh_401_y_dry_run_no_envia():
    client = FakeClient(api_status=[401])
    broker = _broker(client)
    assert broker.accounts()[0]["AccountID"] == "SIM-123"
    assert client.token_calls == 2
    assert broker.submit_market("SPY", 1, "buy")["status"] == "dry_run"
    assert broker.close_position("SPY")["status"] == "dry_run"
    with pytest.raises(TradeStationError, match="deshabilitado"):
        TradeStationBroker(
            client_id="c",
            client_secret="s",
            refresh_token="r",
            base_url=f"https://{SIM_MARKER}/v3",
            dry_run=False,
            http=FakeClient(),
        ).submit_market("SPY", 1, "buy")


def test_guard_sim_y_cuenta_esperada():
    with pytest.raises(TradeStationIdentityError, match="SIM"):
        TradeStationBroker(
            client_id="c",
            client_secret="s",
            refresh_token="r",
            base_url="https://api.tradestation.com/v3",
            require_simulated=True,
            http=FakeClient(),
        )
    broker = _broker(FakeClient(), account_id="OTRA")
    with pytest.raises(TradeStationIdentityError, match="no aparece"):
        broker.account()


def test_sin_refresh_token_es_error_claro():
    broker = TradeStationBroker(
        client_id="c",
        client_secret="s",
        refresh_token="",
        base_url=f"https://{SIM_MARKER}/v3",
        http=FakeClient(),
    )
    with pytest.raises(TradeStationAuthError, match="faltan TRADESTATION"):
        broker.health()


def test_http_401_sin_segundo_token_no_filtra_secretos():
    class Denied(FakeClient):
        def request(self, *args, **kwargs):
            return FakeResponse(401, {"error": "token client-secret"})

    broker = _broker(Denied())
    with pytest.raises(TradeStationError, match="HTTP 401"):
        broker.accounts()
