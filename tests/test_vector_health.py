from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from tradinglab import vector_health


def _market_time() -> datetime:
    # Viernes 2026-11-13, 11:00 en Nueva York (16:00 UTC).
    return datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)


def test_mercado_abierto_y_cerrado():
    assert vector_health.market_open(_market_time()) is True
    assert vector_health.market_open(
        datetime(2026, 11, 13, 22, 0, tzinfo=timezone.utc)
    ) is False
    assert vector_health.market_open(
        datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc)
    ) is False


def test_vector_no_instalado_no_avisa(monkeypatch):
    monkeypatch.setattr(vector_health, "vector_binary", lambda: None)
    monkeypatch.setattr(vector_health, "process_running", lambda: False)
    monkeypatch.setattr(vector_health, "latest_all_file", lambda: None)

    result = vector_health.doctor_status(now=_market_time())

    assert result["installed"] is False
    assert result["warn"] is False


def test_vector_instalado_sin_servicio_avisa(monkeypatch):
    monkeypatch.setattr(vector_health, "vector_binary", lambda: Path("vector.exe"))
    monkeypatch.setattr(vector_health, "process_running", lambda: False)
    monkeypatch.setattr(vector_health, "latest_all_file", lambda: None)

    result = vector_health.doctor_status(now=_market_time())

    assert result["installed"] is True
    assert result["running"] is False
    assert result["warn"] is True
    assert "proceso no corre" in result["detail"]


def test_vector_all_viejo_en_mercado_avisa(tmp_path, monkeypatch):
    path = tmp_path / "all-2026-11-13.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    old = _market_time().timestamp() - 20 * 60
    os.utime(path, (old, old))

    monkeypatch.setattr(vector_health, "vector_binary", lambda: Path("vector.exe"))
    monkeypatch.setattr(vector_health, "process_running", lambda: True)
    monkeypatch.setattr(vector_health, "latest_all_file", lambda: path)

    result = vector_health.doctor_status(now=_market_time())

    assert result["stale"] is True
    assert result["warn"] is True
    assert "20 min" in result["detail"]


def test_vector_all_viejo_fuera_de_mercado_no_avisa(tmp_path, monkeypatch):
    path = tmp_path / "all-2026-11-13.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    old = _market_time().timestamp() - 20 * 60
    os.utime(path, (old, old))

    monkeypatch.setattr(vector_health, "vector_binary", lambda: Path("vector.exe"))
    monkeypatch.setattr(vector_health, "process_running", lambda: True)
    monkeypatch.setattr(vector_health, "latest_all_file", lambda: path)
    after_close = datetime(2026, 11, 13, 22, 0, tzinfo=timezone.utc)

    result = vector_health.doctor_status(now=after_close)

    assert result["stale"] is False
    assert result["warn"] is False
