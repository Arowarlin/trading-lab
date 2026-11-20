from __future__ import annotations

from tradinglab.intel.providers import provider_status, verify_finnhub


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.params = None

    def get(self, url, params=None):
        self.params = params
        return self.response


def test_provider_status_sin_claves():
    status = provider_status(
        secrets={"FRED_API_KEY": "missing", "FINNHUB_API_KEY": "missing"},
        finnhub_key=None,
        check_finnhub=False,
    )
    assert status["rss"]["enabled"] >= 2
    assert status["fred"]["configured"] is False
    assert status["finnhub"]["status"] == "missing"
    assert status["finnhub"]["verified"] is None
    assert isinstance(status["openbb"]["installed"], bool)


def test_verify_finnhub_ok_y_sin_clave():
    client = FakeClient(FakeResponse(200, {"c": 101.5}))
    result = verify_finnhub("test-key", client=client)
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert client.params["symbol"] == "EURUSD"
    assert client.params["token"] == "test-key"

    missing = verify_finnhub(None)
    assert missing["ok"] is False
    assert missing["status"] == "missing"


def test_verify_finnhub_no_autorizado():
    result = verify_finnhub("bad", client=FakeClient(FakeResponse(401)))
    assert result["ok"] is False
    assert result["status"] == "unauthorized"
    assert "401" in result["message"]
