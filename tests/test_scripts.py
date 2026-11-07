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
