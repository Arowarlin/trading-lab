from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lmstudio_start_sin_descarga_ni_secretos():
    script = (ROOT / "scripts" / "lmstudio_start.ps1").read_text(encoding="utf-8")
    assert "qwen/qwen3-30b-a3b" in script
    assert "32768" in script
    assert "--parallel 1" in script
    assert "download" not in script.lower()
    assert "api_key" not in script.lower()
    assert "TradingLab-LMStudio" not in script  # la tarea se registra fuera del script


def test_llm_preflight_arranca_si_no_responde_y_espera_90s():
    script = (ROOT / "scripts" / "llm_preflight.ps1").read_text(encoding="utf-8")
    assert "127.0.0.1:1234/v1/models" in script
    assert "TcpClient" in script
    assert "127.0.0.1" in script
    assert "1234" in script
    assert "lmstudio_start.ps1" in script
    assert "WaitSeconds = 90" in script
    assert "Start-Sleep -Seconds 3" in script
    assert "Sin datos" in script
    assert "download" not in script.lower()
    assert "api_key" not in script.lower()


def test_tareas_llm_usan_el_preflight_comun():
    for name in (
        "intel_daily.ps1",
        "premarket_daily.ps1",
        "llm_compare_daily.ps1",
        "agents_daily.ps1",
    ):
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "llm_preflight.ps1" in script
        assert "Ensure-LMStudio" in script

    session = (ROOT / "scripts" / "ai_trader_session.ps1").read_text(
        encoding="utf-8"
    )
    assert "TRADINGLAB_AI_MODEL" in session


def test_calendar_csv_estructura():
    path = ROOT / "data" / "calendar" / "events.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "event_id,currency,event,scheduled_at_utc,impact,"
        "blackout_before_min,blackout_after_min,source_url"
    )


def test_manage_no_compite_por_el_candado_del_scalp():
    script = (ROOT / "scripts" / "ai_trader_manage.ps1").read_text(encoding="utf-8")
    assert "lock-acquire" not in script
    assert "ai-trader manage" in script


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


def test_intel_daily_con_scoring_y_finnhub_opcionales():
    script = (ROOT / "scripts" / "intel_daily.ps1").read_text(encoding="utf-8")
    assert "param(" in script
    assert "[switch]$Finnhub" in script
    assert "[switch]$Score" in script
    assert "intel finnhub" in script
    assert "intel score" in script
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


def test_premarket_scripts_nativos_sin_trading_r1():
    daily = (ROOT / "scripts" / "premarket_daily.ps1").read_text(encoding="utf-8")
    assert "briefing --session" in daily
    assert "PreflightOnly" in daily
    assert "trading_r1" not in daily.lower()
    assert "orchestrate" not in daily.lower()
    assert "--execute" not in daily.lower()

    register = (ROOT / "scripts" / "register_premarket_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "Register-ScheduledTask" in register
    assert "TradingLab-Premarket" in register
    assert "07:45" in register
    assert "premarket_daily.ps1" in register
    assert "sin ordenes" in register.lower()


def test_reboot_after_download_no_reinicia_sin_modelo():
    script = (ROOT / "scripts" / "reboot_after_download.ps1").read_text(
        encoding="utf-8"
    )
    assert "qwen3-30b-a3b" in script
    assert "shutdown.exe /r /t 120" in script
    assert "no aparece; no se reinicia" in script
    assert "shutdown /a" in script


def test_resume_after_reboot_reabre_sesion_exacta():
    resume = (ROOT / "scripts" / "resume_after_reboot.ps1").read_text(
        encoding="utf-8"
    )
    terminal = (ROOT / "scripts" / "resume_terminal.ps1").read_text(
        encoding="utf-8"
    )
    assert "resume_terminal.ps1" in resume
    assert (
        "powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File" in resume
    )
    assert "last_boot.txt" in resume
    assert "wt.exe" in resume
    assert "Unregister-ScheduledTask" not in resume  # requiere elevacion
    assert "opencode --session" in terminal
    assert "ses_e5220563affelHrJU9DmgfjCb3" in terminal

    register = (ROOT / "scripts" / "register_resume_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "TradingLab-Resume" in register
    assert "AtLogOn" in register
    assert "Register-ScheduledTask" in register
    assert "resume_after_reboot.ps1" in register


def test_trading_r1_premarket_runner_sin_ordenes():
    script = (ROOT / "scripts" / "trading_r1_premarket.ps1").read_text(
        encoding="utf-8"
    )
    assert "trading-r1" in script
    assert "backend.json" in script
    assert "/research" in script
    assert "Invoke-RestMethod" in script
    assert "PreflightOnly" in script
    assert "premarket --no-llm" in script
    assert "premarket_input" in script
    assert "No llames" in script
    assert "UTF8.GetBytes" in script
    assert "telegram send" in script
    assert "qwen3.8-27b" in script
    assert "Sin datos" in script
    assert "900" in script
    assert "order" not in script.lower()


def test_llm_compare_diario_sin_ordenes():
    daily = (ROOT / "scripts" / "llm_compare_daily.ps1").read_text(encoding="utf-8")
    assert "lab llm compare" in daily
    assert "qwen/qwen3.8-27b" in daily
    assert "qwen/qwen3-30b-a3b" in daily
    assert "lms unload" in daily
    assert "PreflightOnly" in daily
    assert "llm_compare_failed" in daily
    assert "order" not in daily.lower()

    register = (ROOT / "scripts" / "register_llm_compare_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "TradingLab-LLMCompare" in register
    assert "18:30" in register
    assert "Weekly" in register
    assert "IgnoreNew" in register


def test_deep_compare_scripts_preparados_sin_registrar():
    nightly = (ROOT / "scripts" / "deep_compare_nightly.ps1").read_text(
        encoding="utf-8"
    )
    assert "agent-compare" in nightly
    assert "PreflightOnly" in nightly
    assert "orchestrate" not in nightly.lower()
    assert "--execute" not in nightly.lower()
    assert "Register-ScheduledTask" not in nightly

    register = (ROOT / "scripts" / "register_deep_compare_task.ps1").read_text(
        encoding="utf-8"
    )
    assert "Register-ScheduledTask" in register
    assert "TradingLab-DeepCompare" in register
    assert "02:30" in register
    assert "deep_compare_nightly.ps1" in register
    assert "no envia ordenes" in register.lower()


def test_intraday_forward_scripts_signal_y_execute():
    signal = (ROOT / "scripts" / "intraday_forward_signal.ps1").read_text(
        encoding="utf-8"
    )
    assert "intraday forward --bars 5000" in signal
    assert "--execute" not in signal
    assert "intraday_forward_failed" in signal
    assert "TradingLab-IntradayForward" in signal
    assert "[Console]::OutputEncoding" in signal
    assert "PYTHONIOENCODING" in signal
    assert "Add-Content -Path $log" in signal
    assert "Register-ScheduledTask" not in signal
    assert "*>>" not in signal

    execute = (ROOT / "scripts" / "intraday_forward_execute.ps1").read_text(
        encoding="utf-8"
    )
    assert '"intraday", "forward", "--bars", "5000"' in execute
    assert '"--execute", "--confirm", "FORWARD-DEMO"' in execute
    assert "eurusd-london-pullback-forward,usdjpy-tokyo-breakout-forward" in execute
    assert "us100-trend-d1" in execute
    assert "4 * 60" in execute
    assert "intraday_forward_failed" in execute
    assert "TradingLab-IntradayForward" in execute
    assert "[Console]::OutputEncoding" in execute
    assert "PYTHONIOENCODING" in execute
    assert "Add-Content -Path $log" in execute
    assert "Register-ScheduledTask" not in execute
    assert "*>>" not in execute

    register = (
        ROOT / "scripts" / "register_intraday_forward_task.ps1"
    ).read_text(encoding="utf-8")
    assert "Register-ScheduledTask" in register
    assert "TradingLab-IntradayForward" in register
    assert "intraday_forward_execute.ps1" in register
    assert "RepetitionInterval" in register

