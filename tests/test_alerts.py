from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradinglab.alerts import AlertConfig, heartbeat, last_alerts, send, send_once


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


class FakeClient:
    def __init__(self, fail: Exception | None = None) -> None:
        self.posts: list[dict] = []
        self.gets: list[str] = []
        self.fail = fail

    def post(self, url, content=None, json=None, headers=None):
        if self.fail:
            raise self.fail
        self.posts.append({"url": url, "content": content, "json": json, "headers": headers})
        return FakeResponse()

    def get(self, url):
        self.gets.append(url)
        return FakeResponse()

    def close(self) -> None:
        return None


def _cfg(**overrides) -> AlertConfig:
    base = dict(
        enabled=True,
        channel="ntfy",
        ntfy_url="https://ntfy.test",
        ntfy_topic="tradinglab-test",
        ntfy_token="",
        telegram_token="",
        telegram_chat="",
        cooldown_s=0,
        heartbeat_url="",
    )
    base.update(overrides)
    return AlertConfig(**base)


def test_ntfy_envia_y_registra(tmp_path):
    client = FakeClient()
    result = send(
        "test",
        "hola",
        config=_cfg(),
        db_path=tmp_path / "lab.db",
        client=client,
        now=datetime(2026, 11, 7, 3, tzinfo=timezone.utc),
    )
    assert result.ok
    assert result.channel == "ntfy"
    assert client.posts[0]["url"] == "https://ntfy.test/tradinglab-test"
    assert client.posts[0]["content"] == b"hola"
    assert last_alerts(1, tmp_path / "lab.db")[0]["event"] == "test"


def test_dedupe_por_evento(tmp_path):
    client = FakeClient()
    now = datetime(2026, 11, 7, 3, tzinfo=timezone.utc)
    first = send("guard", "bloqueo", config=_cfg(cooldown_s=300), db_path=tmp_path / "lab.db", client=client, now=now)
    second = send(
        "guard",
        "bloqueo",
        config=_cfg(cooldown_s=300),
        db_path=tmp_path / "lab.db",
        client=client,
        now=now + timedelta(seconds=10),
    )
    assert first.ok and not first.skipped
    assert second.skipped
    assert len(client.posts) == 1


def test_telegram_no_filtra_token(tmp_path):
    token = "123456:SUPERSECRETO"
    client = FakeClient(fail=RuntimeError(f"https://api.telegram.org/bot{token}/sendMessage"))
    result = send(
        "test",
        "hola",
        config=_cfg(channel="telegram", telegram_token=token, telegram_chat="42"),
        db_path=tmp_path / "lab.db",
        client=client,
    )
    assert not result.ok
    assert token not in result.error


def test_sin_canal_no_envia(tmp_path):
    client = FakeClient()
    result = send("test", "hola", config=_cfg(ntfy_topic=""), db_path=tmp_path / "lab.db", client=client)
    assert result.skipped
    assert result.channel == "none"
    assert client.posts == []


def test_heartbeat(tmp_path):
    client = FakeClient()
    result = heartbeat(
        config=_cfg(heartbeat_url="https://hc.test/ping/abc"),
        client=client,
        db_path=tmp_path / "lab.db",
    )
    assert result.ok
    assert client.gets == ["https://hc.test/ping/abc"]
    assert heartbeat(config=_cfg(), db_path=tmp_path / "lab.db").skipped



def test_send_once_dedupe_persistente(tmp_path):
    client = FakeClient()
    db = tmp_path / "lab.db"
    first = send_once(
        "stale_data:test",
        "datos viejos",
        config=_cfg(),
        db_path=db,
        client=client,
    )
    second = send_once(
        "stale_data:test",
        "datos viejos",
        config=_cfg(),
        db_path=db,
        client=client,
    )
    assert first.ok and not first.skipped
    assert second.skipped
    assert len(client.posts) == 1
