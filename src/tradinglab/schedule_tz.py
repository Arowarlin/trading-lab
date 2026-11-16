"""Horario de las tareas: config/schedule.yaml -> hora local.

Cada tarea declara su zona de anclaje: ``America/New_York``, ``Europe/London``
o ``local``. Las horas ``at`` se convierten a la hora local del PC para la
fecha indicada, así que el horario de verano de cada zona se aplica solo cuando
corresponde. ``local`` se deja tal cual.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import CONFIG_DIR

NY = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")
ANCHORS: dict[str, ZoneInfo | None] = {
    "America/New_York": NY,
    "Europe/London": LONDON,
    "local": None,
}
SCHEDULE_PATH = CONFIG_DIR / "schedule.yaml"
DEFAULT_ANCHOR = "local"


def _local_tz(value: timezone | Any | None = None):
    if value is not None:
        return value
    return datetime.now().astimezone().tzinfo or timezone.utc


def load_schedule(path: str | Path | None = None) -> dict:
    target = Path(path) if path else SCHEDULE_PATH
    fallback = {"version": 2, "default_anchor": DEFAULT_ANCHOR, "tasks": []}
    if not target.exists():
        return fallback
    try:
        import yaml

        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback
    data.setdefault("default_anchor", DEFAULT_ANCHOR)
    return data


def anchor_to_local(
    hhmm: str,
    day: date,
    anchor: str = DEFAULT_ANCHOR,
    local_tz: Any | None = None,
) -> str:
    """Convierte una hora HH:MM de ``anchor`` a la hora local del PC en ``day``."""
    raw = str(hhmm).strip()
    hour_text, minute_text = raw.split(":", 1)
    hour, minute = int(hour_text), int(minute_text)
    zone = ANCHORS.get(str(anchor or DEFAULT_ANCHOR))
    if zone is None:
        return f"{hour:02d}:{minute:02d}"
    moment = datetime.combine(day, time(hour, minute), tzinfo=zone)
    return moment.astimezone(_local_tz(local_tz)).strftime("%H:%M")


def ny_to_local(
    hhmm: str,
    day: date,
    local_tz: Any | None = None,
) -> str:
    """Compatibilidad: convierte una hora de Nueva York a la hora local."""
    return anchor_to_local(hhmm, day, "America/New_York", local_tz)


def _task_anchor(task: dict, default: str = DEFAULT_ANCHOR) -> str:
    anchor = str(task.get("anchor") or default or DEFAULT_ANCHOR)
    return anchor if anchor in ANCHORS else DEFAULT_ANCHOR


def _managed(task: dict) -> bool:
    return bool(task.get("manage", True))


def _triggers(task: dict) -> list[dict]:
    return [
        trigger
        for trigger in task.get("triggers") or []
        if isinstance(trigger, dict) and trigger.get("at")
    ]


def expected_times(
    schedule: dict | None = None,
    day: date | None = None,
    local_tz: Any | None = None,
) -> dict[str, list[str]]:
    """Hora local esperada para cada tarea gestionada del YAML en ``day``."""
    data = schedule if schedule is not None else load_schedule()
    moment = day or datetime.now().astimezone().date()
    default = str(data.get("default_anchor") or DEFAULT_ANCHOR)
    out: dict[str, list[str]] = {}
    for task in data.get("tasks") or []:
        if not isinstance(task, dict) or not _managed(task):
            continue
        name = str(task.get("name") or "")
        triggers = _triggers(task)
        if not name or not triggers:
            continue
        anchor = _task_anchor(task, default)
        out[name] = [
            anchor_to_local(str(trigger["at"]), moment, anchor, local_tz)
            for trigger in triggers
        ]
    return out


def _current_times(records: list[dict] | None) -> dict[str, set[str]]:
    """Horas de los triggers semanales; ignora los one-shot de recuperación."""
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
            kind = str(trigger.get("type") or "")
            if kind and "Weekly" not in kind:
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
    """Lista de tareas gestionadas cuya hora local no coincide con el YAML."""
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


# Acciones que suspenden, hibernan, reinician o apagan el PC.
_POWER_RE = re.compile(
    r"(?i)(?:"
    r"shutdown(?:\.exe)?\s+(?:/r|/s|/h|/hybrid|/fw)|"
    r"restart-computer|stop-computer|"
    r"set-?suspendstate|psshutdown|"
    r"rundll32(?:\.exe)?\s+\S*powrprof|"
    r"poweroff|"
    r"systemctl\s+(?:reboot|poweroff|suspend|hibernate)"
    r")"
)
_POWER_NAME_RE = re.compile(r"(?i)(suspend|reboot|shutdown|hibernate|poweroff)")
_SCRIPT_RE = re.compile(r"(?i)([a-z]:\\[^\"']+?\.(?:ps1|bat|cmd))")


def _action_text(record: dict) -> str:
    return " ".join(
        str(record.get(key) or "") for key in ("action", "execute", "arguments")
    ).strip()


def _is_power_task(record: dict) -> bool:
    name = str(record.get("name") or "")
    if _POWER_NAME_RE.search(name):
        return True
    text = _action_text(record)
    if _POWER_RE.search(text):
        return True
    for match in _SCRIPT_RE.finditer(text):
        try:
            script = Path(match.group(1))
            if not script.is_file() or script.stat().st_size > 2_000_000:
                continue
            if _POWER_RE.search(script.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def _in_trading_week(moment: datetime) -> bool:
    """True si la hora NY cae entre domingo 17:00 y viernes 17:00."""
    weekday = moment.weekday()  # lunes=0 ... domingo=6
    if weekday <= 3:  # lunes a jueves
        return True
    if weekday == 4:  # viernes, antes del cierre
        return moment.time() < time(17, 0)
    if weekday == 6:  # domingo, desde la apertura
        return moment.time() >= time(17, 0)
    return False


def _trigger_in_week(trigger: dict, day: date, local_tz: Any | None = None) -> bool:
    start_text = str(trigger.get("start") or "").strip()
    if not start_text:
        return False
    try:
        hour, minute = (int(part) for part in start_text[:5].split(":", 1))
    except ValueError:
        return False
    days = int(trigger.get("days") or 0)
    zone = _local_tz(local_tz)
    for offset in range(7):
        candidate = day + timedelta(days=offset)
        windows_day = (candidate.weekday() + 1) % 7  # domingo=0 ... sabado=6
        if days and not (days & (1 << windows_day)):
            continue
        local = datetime.combine(candidate, time(hour, minute), tzinfo=zone)
        if _in_trading_week(local.astimezone(NY)):
            return True
    return False


def power_problems(
    records: list[dict] | None,
    day: date | None = None,
    local_tz: Any | None = None,
) -> list[dict]:
    """Tareas de energía habilitadas que caen en la semana de trading."""
    moment = day or datetime.now().astimezone().date()
    problems: list[dict] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        name = str(record.get("name") or "")
        if not name.startswith("TradingLab"):
            continue
        if str(record.get("state") or "").lower() == "disabled":
            continue
        if not _is_power_task(record):
            continue
        triggers = [
            trigger
            for trigger in record.get("triggers") or []
            if isinstance(trigger, dict) and _trigger_in_week(trigger, moment, local_tz)
        ]
        if not triggers:
            continue
        problems.append(
            {
                "task": name,
                "action": _action_text(record)[:180],
                "triggers": [
                    {
                        "start": str(trigger.get("start") or ""),
                        "days": int(trigger.get("days") or 0),
                        "type": str(trigger.get("type") or ""),
                    }
                    for trigger in triggers
                ],
            }
        )
    problems.sort(key=lambda item: item["task"])
    return problems


def energy_status(
    day: date | None = None,
    *,
    local_tz: Any | None = None,
    records: list[dict] | None = None,
) -> dict:
    """Estado para `lab doctor`: FAIL si hay energía habilitada en la semana."""
    if records is None:
        try:
            from .task_health import collect_tradinglab_tasks

            records = collect_tradinglab_tasks()
        except Exception as exc:
            return {
                "status": "aviso",
                "problems": [],
                "detail": f"sin datos del Programador: {exc}"[:180],
            }
    problems = power_problems(records, day, local_tz)
    if not problems:
        return {
            "status": "ok",
            "problems": [],
            "detail": "sin tareas de energía habilitadas en la semana",
        }
    sample = []
    for item in problems[:4]:
        starts = ",".join(
            trigger["start"] or "?"
            for trigger in item["triggers"]
        )
        sample.append(f"{item['task'].replace('TradingLab-', '')} {starts}")
    if len(problems) > 4:
        sample.append(f"+{len(problems) - 4} más")
    return {
        "status": "falla",
        "problems": problems,
        "detail": f"{len(problems)} tareas de energía: " + "; ".join(sample),
    }


def doctor_status(
    day: date | None = None,
    *,
    schedule_path: str | Path | None = None,
    local_tz: Any | None = None,
) -> dict:
    """Estado para ``lab doctor``: falla si una tarea gestionada está desfasada."""
    schedule = load_schedule(schedule_path)
    tasks = [
        task
        for task in schedule.get("tasks") or []
        if isinstance(task, dict) and _managed(task) and _triggers(task)
    ]
    if not tasks:
        return {
            "status": "aviso",
            "problems": [],
            "detail": "sin config/schedule.yaml o sin tareas gestionadas",
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
            "detail": f"{len(tasks)} tareas ancladas alineadas",
        }
    sample = []
    for item in problems[:4]:
        current = ",".join(item["current"]) or "sin tarea"
        wanted = ",".join(item["expected"]) or "-"
        sample.append(f"{item['task'].replace('TradingLab-', '')} {current}->{wanted}")
    if len(problems) > 4:
        sample.append(f"+{len(problems) - 4} más")
    return {
        "status": "falla",
        "problems": problems,
        "detail": f"{len(problems)}/{len(tasks)} desfasadas · " + "; ".join(sample),
    }


__all__ = [
    "ANCHORS",
    "DEFAULT_ANCHOR",
    "LONDON",
    "NY",
    "SCHEDULE_PATH",
    "anchor_to_local",
    "check_schedule",
    "doctor_status",
    "energy_status",
    "expected_times",
    "load_schedule",
    "ny_to_local",
    "power_problems",
]
