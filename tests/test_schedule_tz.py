from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from tradinglab.ai_session import session_window
from tradinglab.schedule_tz import (
    LONDON,
    NY,
    anchor_to_local,
    check_schedule,
    expected_times,
    load_schedule,
    ny_to_local,
)

LOCAL = timezone(timedelta(hours=-4))  # zona del PC: UTC-4 fijo
US_SUMMER = date(2026, 7, 15)  # NY en EDT (UTC-4)
US_WINTER = date(2026, 12, 15)  # NY en EST (UTC-5)
US_BEFORE_SPRING = date(2026, 3, 7)
US_AFTER_SPRING = date(2026, 3, 8)
US_BEFORE_FALL = date(2026, 10, 31)
US_AFTER_FALL = date(2026, 11, 1)
UK_SUMMER = date(2026, 7, 15)  # Londres en BST (UTC+1)
UK_WINTER = date(2026, 12, 15)  # Londres en GMT (UTC+0)
UK_BEFORE_SPRING = date(2026, 3, 28)
UK_AFTER_SPRING = date(2026, 3, 29)
UK_BEFORE_FALL = date(2026, 10, 24)
UK_AFTER_FALL = date(2026, 10, 25)
MANAGE_SUNDAY_WINTER = date(2026, 12, 13)
MANAGE_SUNDAY_SUMMER = date(2026, 7, 12)

SCHEDULE = {
    "default_anchor": "local",
    "tasks": [
        {
            "name": "TradingLab-AI-NY",
            "anchor": "America/New_York",
            "manage": True,
            "triggers": [{"at": "09:35"}, {"at": "10:35"}],
        },
        {
            "name": "TradingLab-AI-London",
            "anchor": "Europe/London",
            "manage": True,
            "triggers": [{"at": "08:05"}],
        },
        {
            "name": "TradingLab-WakeLondon",
            "anchor": "Europe/London",
            "manage": True,
            "triggers": [{"at": "07:59"}],
        },
        {
            "name": "TradingLab-AI-Daily",
            "anchor": "local",
            "manage": False,
            "triggers": [{"at": "18:15"}],
        },
    ],
}


def test_conversor_ny_verano_e_invierno():
    assert anchor_to_local("09:35", US_SUMMER, "America/New_York", LOCAL) == "09:35"
    assert anchor_to_local("09:35", US_WINTER, "America/New_York", LOCAL) == "10:35"
    assert anchor_to_local("07:45", US_WINTER, "America/New_York", LOCAL) == "08:45"
    assert anchor_to_local("12:05", US_WINTER, "America/New_York", LOCAL) == "13:05"
    assert ny_to_local("09:35", US_WINTER, LOCAL) == "10:35"


def test_conversor_londres_verano_e_invierno():
    assert anchor_to_local("08:05", UK_SUMMER, "Europe/London", LOCAL) == "03:05"
    assert anchor_to_local("08:05", UK_WINTER, "Europe/London", LOCAL) == "04:05"
    assert anchor_to_local("07:59", UK_SUMMER, "Europe/London", LOCAL) == "02:59"
    assert anchor_to_local("07:59", UK_WINTER, "Europe/London", LOCAL) == "03:59"


def test_conversor_local_no_cambia():
    assert anchor_to_local("18:15", US_WINTER, "local", LOCAL) == "18:15"
    assert anchor_to_local("23:09", UK_SUMMER, "local", LOCAL) == "23:09"


def test_conversor_cambio_de_horario_ee_uu():
    assert anchor_to_local("09:35", US_BEFORE_SPRING, "America/New_York", LOCAL) == "10:35"
    assert anchor_to_local("09:35", US_AFTER_SPRING, "America/New_York", LOCAL) == "09:35"
    assert anchor_to_local("09:35", US_BEFORE_FALL, "America/New_York", LOCAL) == "09:35"
    assert anchor_to_local("09:35", US_AFTER_FALL, "America/New_York", LOCAL) == "10:35"


def test_conversor_cambio_de_horario_reino_unido():
    assert anchor_to_local("08:05", UK_BEFORE_SPRING, "Europe/London", LOCAL) == "04:05"
    assert anchor_to_local("08:05", UK_AFTER_SPRING, "Europe/London", LOCAL) == "03:05"
    assert anchor_to_local("08:05", UK_BEFORE_FALL, "Europe/London", LOCAL) == "03:05"
    assert anchor_to_local("08:05", UK_AFTER_FALL, "Europe/London", LOCAL) == "04:05"


def test_horas_esperadas_por_ancla():
    assert expected_times(SCHEDULE, US_SUMMER, LOCAL) == {
        "TradingLab-AI-NY": ["09:35", "10:35"],
        "TradingLab-AI-London": ["03:05"],
        "TradingLab-WakeLondon": ["02:59"],
    }
    assert expected_times(SCHEDULE, US_WINTER, LOCAL) == {
        "TradingLab-AI-NY": ["10:35", "11:35"],
        "TradingLab-AI-London": ["04:05"],
        "TradingLab-WakeLondon": ["03:59"],
    }


def test_check_detecta_tareas_desfasadas_y_corregidas():
    old = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "09:35"}, {"start": "10:35"}],
        },
        {"name": "TradingLab-AI-London", "triggers": [{"start": "03:05"}]},
        {"name": "TradingLab-WakeLondon", "triggers": [{"start": "02:59"}]},
    ]
    problems = check_schedule(old, SCHEDULE, US_WINTER, LOCAL)
    assert len(problems) == 3
    by_name = {item["task"]: item for item in problems}
    assert by_name["TradingLab-AI-NY"]["expected"] == ["10:35", "11:35"]
    assert by_name["TradingLab-AI-NY"]["current"] == ["09:35", "10:35"]
    assert by_name["TradingLab-AI-London"]["expected"] == ["04:05"]
    assert by_name["TradingLab-WakeLondon"]["expected"] == ["03:59"]

    fixed = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "10:35"}, {"start": "11:35"}],
        },
        {"name": "TradingLab-AI-London", "triggers": [{"start": "04:05"}]},
        {"name": "TradingLab-WakeLondon", "triggers": [{"start": "03:59"}]},
    ]
    assert check_schedule(fixed, SCHEDULE, US_WINTER, LOCAL) == []


def test_check_verano_no_cambia():
    current = [
        {
            "name": "TradingLab-AI-NY",
            "triggers": [{"start": "09:35"}, {"start": "10:35"}],
        },
        {"name": "TradingLab-AI-London", "triggers": [{"start": "03:05"}]},
        {"name": "TradingLab-WakeLondon", "triggers": [{"start": "02:59"}]},
    ]
    assert check_schedule(current, SCHEDULE, US_SUMMER, LOCAL) == []


def test_check_ignora_tarea_de_inventario():
    problems = check_schedule([], SCHEDULE, US_WINTER, LOCAL)
    assert len(problems) == 3
    assert all(item["reason"] == "tarea no encontrada" for item in problems)
    assert "TradingLab-AI-Daily" not in {item["task"] for item in problems}


def test_check_ignora_trigger_temporal_de_recuperacion():
    records = [
        {
            "name": "TradingLab-AI-Manage",
            "triggers": [
                {"start": "18:00", "type": "MSFT_TaskWeeklyTrigger"},
                {"start": "13:30", "type": "MSFT_TaskTimeTrigger"},
            ],
        }
    ]
    schedule = {
        "tasks": [
            {
                "name": "TradingLab-AI-Manage",
                "anchor": "America/New_York",
                "manage": True,
                "triggers": [{"at": "17:00"}],
            }
        ]
    }
    assert check_schedule(records, schedule, US_WINTER, LOCAL) == []


def test_ai_manage_cubre_cinco_dias_sin_huecos():
    schedule = load_schedule()
    task = next(t for t in schedule["tasks"] if t["name"] == "TradingLab-AI-Manage")
    trigger = task["triggers"][0]
    assert task["anchor"] == "America/New_York"
    assert trigger["at"] == "17:00"
    assert trigger["duration_days"] == 5
    assert trigger["duration_hours"] == 0
    assert trigger["interval_minutes"] == 15

    for sunday, first_local in (
        (MANAGE_SUNDAY_WINTER, "18:00"),
        (MANAGE_SUNDAY_SUMMER, "17:00"),
    ):
        start = datetime.combine(sunday, time(17, 0), tzinfo=NY)
        points = [
            start + timedelta(minutes=15 * index)
            for index in range(5 * 24 * 4 + 1)
        ]
        assert (points[-1] - points[0]) == timedelta(days=5)
        assert all((b - a) == timedelta(minutes=15) for a, b in zip(points, points[1:]))
        assert len(points) - 1 == 480
        assert points[0].astimezone(LOCAL).strftime("%H:%M") == first_local
        assert points[-1].astimezone(LOCAL).strftime("%H:%M") == first_local
        assert points[-1].strftime("%A") == "Friday"


def test_london_0805_cae_en_la_ventana_del_codigo():
    inside = datetime(2026, 12, 15, 8, 5, tzinfo=ZoneInfo("Europe/London"))
    ok, detail = session_window("london", inside)
    assert ok is True
    assert "07:00-10:00" in detail

    # WakeLondon 07:59 London tambien esta dentro de la ventana 07:00-10:00:
    # despierta el PC 6 minutos antes de AI-London (08:05); la ventana del
    # codigo ya esta abierta desde las 07:00.
    wake = datetime(2026, 12, 15, 7, 59, tzinfo=ZoneInfo("Europe/London"))
    ok_wake, _ = session_window("london", wake)
    assert ok_wake is True

    before = datetime(2026, 12, 15, 6, 59, tzinfo=ZoneInfo("Europe/London"))
    ok_before, _ = session_window("london", before)
    assert ok_before is False


def test_calendario_real_inventario_completo():
    schedule = load_schedule()
    assert schedule["version"] == 2
    assert schedule["default_anchor"] == "local"
    names = {task["name"] for task in schedule["tasks"]}
    expected = {
        "TradingLab-Agents",
        "TradingLab-AI-Daily",
        "TradingLab-AI-London",
        "TradingLab-AI-Manage",
        "TradingLab-AI-NY",
        "TradingLab-AI-Scalp",
        "TradingLab-Backup",
        "TradingLab-DeepCompare",
        "TradingLab-Drill",
        "TradingLab-DryRun",
        "TradingLab-F13",
        "TradingLab-Heartbeat",
        "TradingLab-Intel",
        "TradingLab-IntradayForward",
        "TradingLab-LLMCompare",
        "TradingLab-LMStudio",
        "TradingLab-OrchestrateSPY",
        "TradingLab-Premarket",
        "TradingLab-RebootAfterDownload",
        "TradingLab-Resume",
        "TradingLab-Suspend",
        "TradingLab-Suspend-20min",
        "TradingLab-Telegram",
        "TradingLab-WakeDeepCompare",
        "TradingLab-WakeLondon",
        "TradingLab-WakeTokyo",
        "TradingLab-WakeUS100",
        "TradingLab-Web",
    }
    assert names == expected
    assert {task["anchor"] for task in schedule["tasks"]} == {
        "America/New_York",
        "Europe/London",
        "local",
    }

    by_name = {task["name"]: task for task in schedule["tasks"]}
    assert by_name["TradingLab-AI-London"]["anchor"] == "Europe/London"
    assert by_name["TradingLab-AI-London"]["triggers"][0]["at"] == "08:05"
    assert by_name["TradingLab-WakeLondon"]["anchor"] == "Europe/London"
    assert by_name["TradingLab-WakeLondon"]["triggers"][0]["at"] == "07:59"
    assert by_name["TradingLab-WakeLondon"]["wake_to_run"] is True
    assert by_name["TradingLab-Heartbeat"]["wake_to_run"] is True
    assert by_name["TradingLab-IntradayForward"]["wake_to_run"] is True
    assert by_name["TradingLab-Heartbeat"]["manage"] is False

    maintenance = schedule["maintenance"]
    assert maintenance["name"] == "TradingLab-ScheduleTZ"
    assert maintenance["frequency"] == "daily"
    assert maintenance["at"] == "16:00"
    assert maintenance["script"] == "scripts/register_tasks_tz.ps1"


def test_london_constantes_del_calendario():
    assert str(NY) == "America/New_York"
    assert str(LONDON) == "Europe/London"
