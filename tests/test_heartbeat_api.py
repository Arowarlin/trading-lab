from __future__ import annotations

from tradinglab import heartbeat


class Response:
    def __init__(self, data: dict, status: int = 200) -> None:
        self.data = data
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self) -> dict:
        return self.data


class Client:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.checks = [
            {"uuid": f"uuid-{name}", "name": f"TradingLab-{name}", "slug": name}
            for name in heartbeat.CHECK_SCHEDULES
        ]

    def get(self, url, headers=None):
        assert url.endswith("/api/v3/checks/")
        assert headers["X-Api-Key"] == "test-key"
        return Response({"checks": self.checks})

    def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        return Response({})


def test_dry_run_no_escribe():
    client = Client()

    result = heartbeat.apply_schedules(api_key="test-key", client=client)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["matched"] == 12
    assert result["applied"] == 0
    assert client.posts == []
    pc = next(item for item in result["checks"] if item["check"] == "pc")
    assert pc["payload"]["timeout"] == 600
    assert pc["payload"]["grace"] == 600


def test_apply_escribe_los_12():
    client = Client()

    result = heartbeat.apply_schedules(
        api_key="test-key", client=client, apply=True
    )

    assert result["ok"] is True
    assert result["dry_run"] is False
    assert result["matched"] == 12
    assert result["applied"] == 12
    assert len(client.posts) == 12
    f13 = next(
        post for post in client.posts if post["url"].endswith("uuid-f13")
    )
    assert f13["json"]["schedule"] == "20 22 * * 1-5"
    assert f13["json"]["tz"] == "America/Santo_Domingo"
    assert f13["json"]["grace"] == 3600


def test_sin_api_key_no_toca_nada():
    result = heartbeat.apply_schedules(api_key=None)

    assert result["ok"] is False
    assert "API key no configurada" in result["error"]
    assert result["matched"] == 0
