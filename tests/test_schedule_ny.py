from __future__ import annotations

from datetime import date, timedelta, timezone

from tradinglab.schedule_ny import (
    check_schedule,
    expected_times,
    load_schedule,
    ny_to_local,
)

LOCAL = timezone(timedelta(hours=-4))  # zona del PC: UTC-4 fijo
SUMMER = date(2026, 7, 15)  # NY en EDT (UTC-4)
WINTER = date(2026, 12, 15)  # NY en EST (UTC-5)
AFTER_DST = date(2026, 11, 1)  # termina el horario de verano
BEFORE_DST = date(2026, 10, 31)

SCHEDULE = {
    "tasks": [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"at": "09:35"}, {"at": "10:35"}],
        },
        {
            "name": "TradingLab-Premarket",
            "triggers": [{"at": "07:45"}],
        },
    ]
}


def test_conversor_verano_e_invierno():
    assert ny_to_local("09:35", SUMMER, LOCAL) == "09:35"
    assert ny_to_local("09:35", WINTER, LOCAL) == "10:35"
    assert ny_to_local("07:45", WINTER, LOCAL) == "08:45"
    assert ny_to_local("12:05", WINTER, LOCAL) == "13:05"


def test_conversor_cambio_de_horario():
    assert ny_to_local("09:35", BEFORE_DST, LOCAL) == "09:35"
    assert ny_to_local("09:35", AFTER_DST, LOCAL) == "10:35"


def test_horas_esperadas_por_fecha():
    assert expected_times(SCHEDULE, SUMMER, LOCAL) == {
        "TradingLab-AI-NY": ["09:35", "10:35"],
        "TradingLab-Premarket": ["07:45"],
    }
    assert expected_times(SCHEDULE, WINTER, LOCAL) == {
        "TradingLab-AI-NY": ["10:35", "11:35"],
        "TradingLab-Premarket": ["08:45"],
    }


def test_check_detecta_tarea_desfasada_y_corregida():
    old = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "09:35"}, {"start": "10:35"}],
        },
        {
            "name": "TradingLab-Premarket",
            "triggers": [{"start": "07:45"}],
        },
    ]
    problems = check_schedule(old, SCHEDULE, WINTER, LOCAL)
    assert len(problems) == 2
    assert problems[0]["task"] == "TradingLab-AI-NY"
    assert problems[0]["expected"] == ["10:35", "11:35"]
    assert problems[0]["current"] == ["09:35", "10:35"]

    fixed = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "10:35"}, {"start": "11:35"}],
        },
        {
            "name": "TradingLab-Premarket",
            "triggers": [{"start": "08:45"}],
        },
    ]
    assert check_schedule(fixed, SCHEDULE, WINTER, LOCAL) == []


def test_check_verano_no_cambia():
    current = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "09:35"}, {"start": "10:35"}],
        },
        {
            "name": "TradingLab-Premarket",
            "triggers": [{"start": "07:45"}],
        },
    ]
    assert check_schedule(current, SCHEDULE, SUMMER, LOCAL) == []


def test_check_tarea_inexistente():
    problems = check_schedule([], SCHEDULE, WINTER, LOCAL)
    assert len(problems) == 2
    assert all(item["reason"] == "tarea no encontrada" for item in problems)


def test_calendario_real_carga():
    schedule = load_schedule()
    names = {task["name"] for task in schedule["tasks"]}
    assert "TradingLab-AI-Scalp" in names
    assert "TradingLab-AI-NY" in names
    assert "TradingLab-Premarket" in names
