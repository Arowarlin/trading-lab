from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lmstudio_start_sin_descarga_ni_secretos():
    script = (ROOT / "scripts" / "lmstudio_start.ps1").read_text(encoding="utf-8")
    assert "lms load qwen3.8-27b" in script
    assert "--context-length 16384" in script
    assert "--parallel 1" in script
    assert "download" not in script.lower()
    assert "api_key" not in script.lower()
    assert "TradingLab-LMStudio" not in script  # la tarea se registra fuera del script


def test_calendar_csv_estructura():
    path = ROOT / "data" / "calendar" / "events.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "event_id,currency,event,scheduled_at_utc,impact,"
        "blackout_before_min,blackout_after_min,source_url"
    )


def test_open_console_y_acceso_directo():
    script = (ROOT / "scripts" / "open_console.ps1").read_text(encoding="utf-8")
    assert 'web", "--no-open"' in script
    assert "api/health" in script
    assert "8420" in script
    assert "Get-CurrentBuild" in script
    assert "Test-Current" in script
    assert "BUILD_ID" in script
    assert "create_console_shortcut.ps1" in script
    assert "f13 status" not in script.lower()
    assert "f13 freeze" not in script.lower()
    assert "order" not in script.lower()

    creator = (ROOT / "scripts" / "create_console_shortcut.ps1").read_text(encoding="utf-8")
    assert "open_console.ps1" in creator
    assert "TradingLab Console.lnk" in creator

    shortcut = ROOT / "TradingLab Console.lnk"
    assert shortcut.exists() and shortcut.stat().st_size > 0
    blob = shortcut.read_bytes()
    marker = "open_console.ps1"
    assert marker.encode("utf-8") in blob or marker.encode("utf-16-le") in blob


def test_agents_daily_incluye_decisions_update():
    script = (ROOT / "scripts" / "agents_daily.ps1").read_text(encoding="utf-8")
    assert "decisions update" in script
    assert "orchestrate" not in script.lower()
    assert "--execute" not in script.lower()


def test_telegram_scripts_preparados_sin_registrar():
    bridge = (ROOT / "scripts" / "telegram_bridge.ps1").read_text(encoding="utf-8")
    assert "telegram bridge" in bridge
    assert "config\\telegram.yaml" in bridge
    assert "Register-ScheduledTask" not in bridge

    register = (ROOT / "scripts" / "register_telegram_task.ps1").read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in register
    assert "TradingLab-Telegram" in register
    assert "AtLogOn" in register
    assert "no se ejecuta" in register.lower()


def test_f13_scripts_preparados_sin_registrar():
    daily = (ROOT / "scripts" / "f13_daily.ps1").read_text(encoding="utf-8")
    assert "orchestrate" in daily and "qqq-trend-f13" in daily
    assert "--dry-run" in daily
    assert "reconcile" in daily
    assert '"f13", "check"' in daily
    assert "no iniciado" in daily
    assert "PreflightOnly" in daily
    assert "Register-ScheduledTask" not in daily

    register = (ROOT / "scripts" / "register_f13_task.ps1").read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in register
    assert "TradingLab-F13" in register
    assert "22:20" in register
    assert "f13_daily.ps1" in register

