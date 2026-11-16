from __future__ import annotations

from datetime import datetime, timezone

from tradinglab import task_health

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

RECORDS = [
    {
        "name": "TradingLab-AI-Scalp",
        "state": "Ready",
        "last_run": "2026-11-13T13:05:00+00:00",
        "next_run": None,
        "missed": 88,
        "result": 0,
    },
    {
        "name": "TradingLab-AI-NY",
        "state": "Ready",
        "last_run": "2026-11-16T11:00:00+00:00",
        "next_run": None,
        "missed": 2,
        "result": 0,
    },
    {
        "name": "TradingLab-Heartbeat",
        "state": "Ready",
        "last_run": "2026-11-16T11:55:00+00:00",
        "next_run": None,
        "missed": 0,
        "result": 0,
    },
    {
        "name": "Otra-Tarea",
        "state": "Ready",
        "last_run": "2026-11-13T13:05:00+00:00",
        "next_run": None,
        "missed": 50,
        "result": 0,
    },
    {
        "name": "TradingLab-DeepCompare",
        "state": "Disabled",
        "last_run": "2026-11-11T02:30:00+00:00",
        "next_run": None,
        "missed": 5,
        "result": 0,
    },
]


def test_missed_tasks_solo_tradinglab_activas_y_con_perdidas():
    problems = task_health.missed_tasks(RECORDS, now=NOW)

    assert [item["name"] for item in problems] == [
        "TradingLab-AI-Scalp",
        "TradingLab-AI-NY",
    ]
    assert problems[0]["missed"] == 88
    assert problems[0]["stale"] is True
    assert problems[1]["missed"] == 2
    assert problems[1]["stale"] is False


def test_doctor_status_semilla_y_solo_avisa_nuevas(monkeypatch, tmp_path):
    state = tmp_path / "seen.json"
    monkeypatch.setattr(
        task_health, "collect_tradinglab_tasks", lambda: RECORDS
    )

    # La primera lectura fija la línea base: el histórico no es una pérdida nueva.
    first = task_health.doctor_status(now=NOW, state_path=state)
    assert first["status"] == "ok"
    assert first["tasks"] == []
    assert "sin ejecuciones perdidas nuevas" in first["detail"]

    again = task_health.doctor_status(now=NOW, state_path=state)
    assert again["status"] == "ok"

    updated = [
        dict(RECORDS[0], missed=90),
        dict(RECORDS[1], missed=3),
    ] + RECORDS[2:]
    monkeypatch.setattr(
        task_health, "collect_tradinglab_tasks", lambda: updated
    )
    result = task_health.doctor_status(now=NOW, state_path=state)

    assert result["status"] == "warn"
    assert "AI-Scalp +2 (total 90" in result["detail"]
    assert {item["name"]: item["missed"] for item in result["tasks"]} == {
        "TradingLab-AI-Scalp": 2,
        "TradingLab-AI-NY": 1,
    }


def test_doctor_status_ok_sin_perdidas(monkeypatch, tmp_path):
    monkeypatch.setattr(
        task_health,
        "collect_tradinglab_tasks",
        lambda: [RECORDS[2]],
    )

    result = task_health.doctor_status(
        now=NOW, state_path=tmp_path / "seen.json"
    )

    assert result["status"] == "ok"
    assert "sin ejecuciones perdidas nuevas" in result["detail"]


def test_doctor_status_warn_si_no_puede_leer(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("PowerShell no disponible")

    monkeypatch.setattr(task_health, "collect_tradinglab_tasks", boom)

    result = task_health.doctor_status(
        now=NOW, state_path=tmp_path / "seen.json"
    )

    assert result["status"] == "warn"
    assert "sin datos del Programador" in result["detail"]
    assert result["tasks"] == []


def test_parse_fechas_con_y_sin_zona():
    assert task_health._parse("2026-11-16T10:00:00") is not None
    assert task_health._parse("2026-11-16T10:00:00Z") is not None
    assert task_health._parse("") is None
    assert task_health._parse("no es fecha") is None


def test_no_toca_el_programador(monkeypatch):
    calls = []

    class Result:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_run(args, **kwargs):
        calls.append(args)
        return Result()

    monkeypatch.setattr(task_health.subprocess, "run", fake_run)

    assert task_health.collect_tradinglab_tasks() == []
    assert calls and calls[0][0] == "powershell.exe"
    assert "-NoProfile" in calls[0]
