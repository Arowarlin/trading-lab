"""Perfiles de bots por clase de activo.

Un bot sin `profile` o con un perfil desconocido no se ejecuta. El perfil
define temporalidad, ventana horaria, riesgo máximo por operación, máximo de
operaciones diarias y criterios mínimos de validación.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .config import ROOT

PROFILES_FILE = ROOT / "config" / "profiles.yaml"
_DAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


@dataclass(frozen=True)
class Schedule:
    tz: str
    start: str
    end: str
    days: tuple[int, ...]

    def allows(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        local = current.astimezone(ZoneInfo(self.tz))
        if local.weekday() not in self.days:
            return False
        start_h, start_m = (int(x) for x in self.start.split(":"))
        end_h, end_m = (int(x) for x in self.end.split(":"))
        start = time(start_h, start_m)
        end = time(end_h, end_m)
        moment = local.time()
        if start <= end:
            return start <= moment <= end
        return moment >= start or moment <= end


@dataclass(frozen=True)
class ValidationCriteria:
    min_trades: int
    min_dsr: float
    max_pbo: float
    require_walk_forward: bool
    require_regimes: bool


@dataclass(frozen=True)
class BotProfile:
    id: str
    description: str
    timeframe: str
    schedule: Schedule
    max_risk_pct: float
    max_trades_per_day: int
    validation: ValidationCriteria


def _parse_profile(profile_id: str, data: dict) -> BotProfile:
    schedule = data.get("schedule") or {}
    days = tuple(
        sorted(
            _DAYS[str(day).strip().lower()[:3]]
            for day in (schedule.get("days") or [])
            if str(day).strip().lower()[:3] in _DAYS
        )
    )
    validation = data.get("validation") or {}
    return BotProfile(
        id=profile_id,
        description=str(data.get("description") or ""),
        timeframe=str(data.get("timeframe") or "1d"),
        schedule=Schedule(
            tz=str(schedule.get("tz") or "UTC"),
            start=str(schedule.get("start") or "00:00"),
            end=str(schedule.get("end") or "23:59"),
            days=days or tuple(range(7)),
        ),
        max_risk_pct=float(data.get("max_risk_pct") or 0.0),
        max_trades_per_day=int(data.get("max_trades_per_day") or 0),
        validation=ValidationCriteria(
            min_trades=int(validation.get("min_trades") or 0),
            min_dsr=float(validation.get("min_dsr") or 0.0),
            max_pbo=float(validation.get("max_pbo") or 0.30),
            require_walk_forward=bool(validation.get("require_walk_forward", True)),
            require_regimes=bool(validation.get("require_regimes", True)),
        ),
    )


def load_profiles(path: str | Path | None = None) -> dict[str, BotProfile]:
    path = Path(path) if path else PROFILES_FILE
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(name): _parse_profile(str(name), data or {})
        for name, data in (raw.get("profiles") or {}).items()
    }


def get_profile(name: str, path: str | Path | None = None) -> BotProfile | None:
    return load_profiles(path).get(name)


__all__ = [
    "BotProfile",
    "PROFILES_FILE",
    "Schedule",
    "ValidationCriteria",
    "get_profile",
    "load_profiles",
]
