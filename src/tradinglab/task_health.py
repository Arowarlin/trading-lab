"""Salud de las tareas programadas de TradingLab.

Lee el Programador de tareas de Windows en modo **solo lectura** y avisa si
alguna tarea ``TradingLab*`` acumula ejecuciones perdidas **nuevas** desde la
última comprobación. El contador ``NumberOfMissedRuns`` es acumulado, así que
se guarda el último valor visto por tarea en ``data/task_missed_seen.json`` y
solo se avisa del incremento. No crea, modifica, detiene ni lanza tareas.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT

PREFIX = "TradingLab"
MAX_AGE_HOURS = 24
STATE_FILE = ROOT / "data" / "task_missed_seen.json"

_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-ScheduledTask | Where-Object { $_.TaskName -like 'TradingLab*' } | ForEach-Object {
  $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath
  $last = $null
  if ($info.LastRunTime -and $info.LastRunTime.Year -gt 1900) {
    $last = $info.LastRunTime.ToString('o')
  }
  $next = $null
  if ($info.NextRunTime -and $info.NextRunTime.Year -gt 1900) {
    $next = $info.NextRunTime.ToString('o')
  }
  [pscustomobject]@{
    name = $_.TaskName
    state = [string]$_.State
    last_run = $last
    next_run = $next
    missed = [int]$info.NumberOfMissedRuns
    result = [long]$info.LastTaskResult
    action = (@($_.Actions | ForEach-Object {
      ([string]$_.Execute + " " + [string]$_.Arguments).Trim()
    }) -join " ; ")
    triggers = @($_.Triggers | ForEach-Object {
      $start = $null
      if ($_.StartBoundary) {
        try { $start = ([datetime]$_.StartBoundary).ToString('HH:mm') } catch { $start = $null }
      }
      [pscustomobject]@{
        start = $start
        days = [int]$_.DaysOfWeek
        type = $_.CimClass.CimClassName
      }
    })
  }
} | ConvertTo-Json -Compress -Depth 5
"""


def _now(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def collect_tradinglab_tasks(timeout: float = 20.0) -> list[dict]:
    """Lee las tareas TradingLab del Programador. Solo lectura."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"no se pudo leer el Programador: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"PowerShell {result.returncode}: {result.stderr[:160]}")
    raw = result.stdout.strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("salida del Programador no JSON") from exc
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise RuntimeError("salida del Programador inesperada")
    rows: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        triggers = item.get("triggers") or []
        if isinstance(triggers, dict):
            triggers = [triggers]
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "state": str(item.get("state") or ""),
                "last_run": item.get("last_run"),
                "next_run": item.get("next_run"),
                "missed": int(item.get("missed") or 0),
                "result": int(item.get("result") or 0),
                "action": str(item.get("action") or ""),
                "triggers": [
                    {
                        "start": str(trigger.get("start") or ""),
                        "days": int(trigger.get("days") or 0),
                        "type": str(trigger.get("type") or ""),
                    }
                    for trigger in triggers
                    if isinstance(trigger, dict)
                ],
            }
        )
    return rows


def missed_tasks(
    records: list[dict] | None,
    *,
    now: datetime | None = None,
    max_age_hours: float = MAX_AGE_HOURS,
) -> list[dict]:
    """Tareas TradingLab con ejecuciones perdidas; ordenadas por gravedad."""
    moment = _now(now)
    problems: list[dict] = []
    for record in records or []:
        name = str(record.get("name") or "")
        if not name.startswith(PREFIX):
            continue
        if str(record.get("state") or "").lower() == "disabled":
            continue
        missed = int(record.get("missed") or 0)
        if missed <= 0:
            continue
        last = _parse(record.get("last_run"))
        age_h = (moment - last).total_seconds() / 3600.0 if last else None
        problems.append(
            {
                "name": name,
                "missed": missed,
                "last_run": last.isoformat() if last else None,
                "age_hours": round(age_h, 1) if age_h is not None else None,
                "stale": age_h is None or age_h >= float(max_age_hours),
            }
        )
    problems.sort(key=lambda item: (-item["missed"], item["name"]))
    return problems


def _short_local(value: Any) -> str:
    parsed = _parse(value)
    if parsed is None:
        return "nunca"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def _load_seen(path: str | Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_seen(path: str | Path, seen: dict) -> None:
    """Guarda el contador visto; un fallo de escritura no rompe el doctor."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(
            json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(target)
    except OSError:
        return


def new_misses(
    records: list[dict] | None,
    seen: dict,
    *,
    now: datetime | None = None,
    max_age_hours: float = MAX_AGE_HOURS,
) -> tuple[list[dict], dict]:
    """Ejecuciones perdidas nuevas y estado actualizado por tarea.

    La primera vez que se ve una tarea se fija su contador como línea base y
    no se avisa: el histórico (AI-Scalp 160, etc.) no es una pérdida nueva.
    """
    moment = _now(now)
    problems: list[dict] = []
    updated: dict[str, dict] = {}
    for record in records or []:
        name = str(record.get("name") or "")
        if not name.startswith(PREFIX):
            continue
        if str(record.get("state") or "").lower() == "disabled":
            continue
        missed = int(record.get("missed") or 0)
        previous = seen.get(name)
        previous_missed = None
        if isinstance(previous, dict):
            try:
                previous_missed = int(previous.get("missed"))
            except (TypeError, ValueError):
                previous_missed = None
        delta = missed - previous_missed if previous_missed is not None else 0
        delta = max(0, delta)
        updated[name] = {
            "missed": missed,
            "seen_at": moment.isoformat(timespec="seconds"),
        }
        if delta <= 0:
            continue
        last = _parse(record.get("last_run"))
        age_h = (moment - last).total_seconds() / 3600.0 if last else None
        problems.append(
            {
                "name": name,
                "missed": delta,
                "total": missed,
                "last_run": last.isoformat() if last else None,
                "age_hours": round(age_h, 1) if age_h is not None else None,
                "stale": age_h is None or age_h >= float(max_age_hours),
            }
        )
    problems.sort(key=lambda item: (-item["missed"], item["name"]))
    return problems, updated


def doctor_status(
    now: datetime | None = None,
    *,
    state_path: str | Path | None = None,
) -> dict:
    """Estado para `lab doctor`: WARN solo por pérdidas nuevas."""
    try:
        records = collect_tradinglab_tasks()
    except Exception as exc:
        return {
            "status": "warn",
            "detail": f"sin datos del Programador: {exc}"[:180],
            "tasks": [],
        }
    path = Path(state_path) if state_path else STATE_FILE
    problems, updated = new_misses(records, _load_seen(path), now=now)
    _save_seen(path, updated)
    if not problems:
        return {
            "status": "ok",
            "detail": "sin ejecuciones perdidas nuevas",
            "tasks": [],
        }
    detail = "; ".join(
        f"{item['name'].replace('TradingLab-', '')} +{item['missed']}"
        f" (total {item['total']}, últ. {_short_local(item['last_run'])})"
        for item in problems[:6]
    )
    if len(problems) > 6:
        detail += f"; +{len(problems) - 6} más"
    return {"status": "warn", "detail": detail[:220], "tasks": problems}


__all__ = [
    "MAX_AGE_HOURS",
    "PREFIX",
    "STATE_FILE",
    "collect_tradinglab_tasks",
    "doctor_status",
    "missed_tasks",
    "new_misses",
]
