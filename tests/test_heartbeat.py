from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tradinglab import heartbeat


def test_ping_omitido_sin_url(monkeypatch):
    monkeypatch.setattr(heartbeat, "url_for", lambda check: None)
    result = heartbeat.ping("f13", "ok")
    assert result["ok"] is True
    assert result["skipped"] is True
    assert "no configurada" in result["reason"]


def test_ping_start_y_fail_usan_sufijo(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    monkeypatch.setattr(
        heartbeat, "url_for", lambda check: "https://hc.example/abc"
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert heartbeat.ping("ai-ny", "start", client=client)["ok"] is True
    assert heartbeat.ping("ai-ny", "fail", client=client)["ok"] is True
    client.close()
    assert seen == [
        "https://hc.example/abc/start",
        "https://hc.example/abc/fail",
    ]


def test_setup_no_imprime_url(monkeypatch):
    store = {}

    class Keyring:
        @staticmethod
        def set_password(service, key, value):
            store[(service, key)] = value

        @staticmethod
        def get_password(service, key):
            return store.get((service, key))

    monkeypatch.setattr(heartbeat, "_keyring", lambda: Keyring)
    result = heartbeat.setup("backup", "https://hc.example/secret")
    assert result == {"check": "backup", "configured": True}
    assert heartbeat.url_for("backup") == "https://hc.example/secret"
    assert "secret" not in str(result)


def test_check_desconocido():
    with pytest.raises(heartbeat.HeartbeatError):
        heartbeat.ping("no-existe")

def test_tareas_programadas_tienen_latido():
    root = Path(__file__).resolve().parents[1] / "scripts"
    checks = {
        "f13_daily.ps1": "Send-TaskHeartbeat",
        "agents_daily.ps1": "Send-TaskHeartbeat",
        "llm_compare_daily.ps1": "Send-TaskHeartbeat",
        "intraday_forward_execute.ps1": "Send-TaskHeartbeat",
        "ai_trader_scalp.ps1": "Send-TaskHeartbeat",
        "ai_trader_manage.ps1": "Send-TaskHeartbeat",
        "drill_monthly.ps1": "Send-TaskHeartbeat",
        "backup.ps1": "Send-TaskHeartbeat",
        "ai_trader_session.ps1": "Send-Heartbeat",
    }
    for name, marker in checks.items():
        assert marker in (root / name).read_text(encoding="utf-8")
    assert "TradingLab-Heartbeat" in (
        root / "register_heartbeat_task.ps1"
    ).read_text(encoding="utf-8")
