"""Horario de las tareas NY: config/schedule.yaml → hora local.

Las horas del YAML están en America/New_York. El PC puede estar en otra zona
(por ejemplo UTC-4 fijo): la conversión se hace para la fecha indicada, así que
el horario de verano de EE. UU. se aplica solo cuando corresponde.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import CONFIG_DIR

NY = ZoneInfo("America/New_York")
SCHEDULE_PATH = CONFIG_DIR / "schedule.yaml"


def _local_tz(value: timezone | Any | None = None):
    if value is not None:
        return value
    return datetime.now().astimezone().tzinfo or timezone.utc


def load_schedule(path: str | Path | None = None) -> dict:
    target = Path(path) if path else SCHEDULE_PATH
    if not target.exists():
        return {"version": 1, "timezone": "America/New_York", "tasks": []}
    try:
        import yaml

        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"version": 1, "timezone": "America/New_York", "tasks": []}
    return data if isinstance(data, dict) else {}


def ny_to_local(
    hhmm: str,
    day: date,
    local_tz: Any | None = None,
) -> str:
    """Convierte una hora NY (HH:MM) a la hora local del PC en `day`."""
    hour, minute = (int(part) for part in str(hhmm).split(":", 1))
    ny = datetime.combine(day, time(hour, minute), tzinfo=NY)
    return ny.astimezone(_local_tz(local_tz)).strftime("%H:%M")


def expected_times(
    schedule: dict | None = None,
    day: date | None = None,
    local_tz: Any | None = None,
) -> dict[str, list[str]]:
    """Hora local esperada para cada tarea del YAML en `day`."""
    data = schedule if schedule is not None else load_schedule()
    moment = day or datetime.now().astimezone().date()
    out: dict[str, list[str]] = {}
    for task in data.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        name = str(task.get("name") or "")
        if not name:
            continue
        times = [
            ny_to_local(str(trigger.get("at")), moment, local_tz)
            for trigger in task.get("triggers") or []
            if isinstance(trigger, dict) and trigger.get("at")
        ]
        out[name] = times
    return out


def _current_times(records: list[dict] | None) -> dict[str, set[str]]:
    current: dict[str, set[str]] = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        name = str(record.get("name") or "")
        if not name:
            continue
        times: set[str] = set()
        for trigger in record.get("triggers") or []:
            if not isinstance(trigger, dict):
                continue
            start = str(trigger.get("start") or "").strip()
            if start:
                times.add(start[:5])
        current[name] = times
    return current


def check_schedule(
    records: list[dict] | None,
    schedule: dict | None = None,
    day: date | None = None,
    local_tz: Any | None = None,
) -> list[dict]:
    """Lista de tareas cuya hora local no coincide con el YAML."""
    expected = expected_times(schedule, day, local_tz)
    current = _current_times(records)
    problems: list[dict] = []
    for name, wanted in expected.items():
        if name not in current:
            problems.append(
                {
                    "task": name,
                    "expected": sorted(set(wanted)),
                    "current": [],
                    "reason": "tarea no encontrada",
                }
            )
            continue
        wanted_set = set(wanted)
        if current[name] != wanted_set:
            problems.append(
                {
                    "task": name,
                    "expected": sorted(wanted_set),
                    "current": sorted(current[name]),
                    "reason": "hora distinta",
                }
            )
    problems.sort(key=lambda item: item["task"])
    return problems


def doctor_status(
    day: date | None = None,
    *,
    schedule_path: str | Path | None = None,
    local_tz: Any | None = None,
) -> dict:
    """Estado para `lab doctor`: falla si alguna tarea NY está desfasada."""
    schedule = load_schedule(schedule_path)
    tasks = schedule.get("tasks") or []
    if not tasks:
        return {
            "status": "aviso",
            "problems": [],
            "detail": "sin config/schedule.yaml o sin tareas NY",
        }
    try:
        from .task_health import collect_tradinglab_tasks

        records = collect_tradinglab_tasks()
    except Exception as exc:
        return {
            "status": "aviso",
            "problems": [],
            "detail": f"sin datos del Programador: {exc}"[:180],
        }
    problems = check_schedule(records, schedule, day, local_tz)
    if not problems:
        return {
            "status": "ok",
            "problems": [],
            "detail": f"{len(tasks)} tareas NY alineadas",
        }
    sample = []
    for item in problems[:4]:
        current = ",".join(item["current"]) or "sin tarea"
        wanted = ",".join(item["expected"]) or "—"
        sample.append(f"{item['task'].replace('TradingLab-', '')} {current}→{wanted}")
    if len(problems) > 4:
        sample.append(f"+{len(problems) - 4} más")
    return {
        "status": "falla",
        "problems": problems,
        "detail": f"{len(problems)}/{len(tasks)} desfasadas · " + "; ".join(sample),
    }


__all__ = [
    "NY",
    "SCHEDULE_PATH",
    "check_schedule",
    "doctor_status",
    "expected_times",
    "load_schedule",
    "ny_to_local",
]
