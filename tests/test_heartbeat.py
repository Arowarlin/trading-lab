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


def test_ping_fail_con_motivo_usa_post(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.content.decode("utf-8")))
        return httpx.Response(200)

    monkeypatch.setattr(
        heartbeat, "url_for", lambda check: "https://hc.example/abc"
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = heartbeat.ping(
        "pc", "fail", message="MT5: timeout 60s", client=client
    )
    client.close()
    assert result["ok"] is True
    assert seen == [
        ("POST", "https://hc.example/abc/fail", "MT5: timeout 60s")
    ]


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

def test_cron_desde_disparadores():
    assert heartbeat.mask_to_days(62) == [1, 2, 3, 4, 5]
    assert heartbeat.cron_from_weekly(62, ["22:20"]) == ["20 22 * * 1-5"]
    assert heartbeat.cron_from_weekly(62, ["09:35", "10:35"]) == [
        "35 9,10 * * 1-5"
    ]
    assert heartbeat.cron_from_weekly(1, ["03:00"]) == ["0 3 * * 0"]
    assert heartbeat.cron_from_daily(["13:00", "19:00"]) == ["0 13,19 * * *"]
    assert heartbeat.cron_from_times(["09:25", "09:30", "10:00"]) == [
        "0 10 * * *",
        "25 9 * * *",
        "30 9 * * *",
    ]


def test_tabla_de_12_checks_y_pc_por_periodo():
    assert len(heartbeat.CHECK_SCHEDULES) == 12
    assert heartbeat.CHECK_SCHEDULES["pc"]["mode"] == "period"
    assert heartbeat.CHECK_SCHEDULES["pc"]["period_min"] == 10
    assert heartbeat.CHECK_SCHEDULES["pc"]["grace_min"] == 10
    assert heartbeat.CHECK_SCHEDULES["ai-manage"]["cron"] == "*/15 0-17 * * 1-5"
    assert heartbeat.CHECK_SCHEDULES["ai-manage"]["grace_min"] == 30


def test_heartbeat_pc_siempre_hace_ping_y_tiene_timeout():
    text = (
        Path(__file__).resolve().parents[1] / "scripts" / "heartbeat_pc.ps1"
    ).read_text(encoding="utf-8")
    assert 'Send-TaskHeartbeat -Root $root -Check "pc" -Status "start"' in text
    assert 'Send-TaskHeartbeat -Root $root -Check "pc" -Status "fail"' in text
    assert 'Send-TaskHeartbeat -Root $root -Check "pc" -Status "ok"' in text
    assert "WaitForExit(60000)" in text
    assert "-Message $message" in text


def test_tareas_programadas_tienen_latido():
    root = Path(__file__).resolve().parents[1] / "scripts"
    checks = {
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
