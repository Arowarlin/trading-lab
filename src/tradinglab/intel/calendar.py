"""Calendario macro con proveedor abstracto y estados explícitos.

Un resultado vacío no es lo mismo que "no hay proveedor" o "proveedor caído".
El guard puede distinguir los tres casos y bloquear aperturas si no hay datos
fiables cuando el blackout está activado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..db import connect, init_db, utcnow
from ..prop import PropRules, from_yaml, ftmo


class CalendarStatus(StrEnum):
    OK = "ok"  # consultado; puede haber 0 eventos
    UNCONFIGURED = "unconfigured"
    ERROR = "error"
    STALE = "stale"


@dataclass(frozen=True)
class CalendarEvent:
    event: str
    ts_utc: datetime
    importance: str = "medium"
    source: str = "manual"


@dataclass
class CalendarResult:
    status: CalendarStatus
    events: list[CalendarEvent] = field(default_factory=list)
    fetched_at: datetime | None = None
    message: str = ""


@dataclass(frozen=True)
class BlackoutResult:
    blocked: bool
    status: CalendarStatus
    reason: str
    events: list[CalendarEvent] = field(default_factory=list)
    data_ok: bool = True


class CalendarProvider(Protocol):
    name: str

    def fetch(self, start: datetime, end: datetime) -> CalendarResult: ...


class StaticCalendarProvider:
    """Proveedor de fixtures: no toca red ni DB."""

    def __init__(
        self,
        events: list[CalendarEvent] | None = None,
        *,
        status: CalendarStatus = CalendarStatus.OK,
        message: str = "",
        fetched_at: datetime | None = None,
    ) -> None:
        self.events = list(events or [])
        self.status = status
        self.message = message
        self.fetched_at = fetched_at
        self.name = "fixture"

    def fetch(self, start: datetime, end: datetime) -> CalendarResult:
        in_window = [e for e in self.events if start <= e.ts_utc <= end]
        return CalendarResult(self.status, in_window, self.fetched_at, self.message)


class DbCalendarProvider:
    """Lee macro_events y el último estado de calendar_fetches."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        source: str = "manual",
        max_age_hours: float = 48.0,
    ) -> None:
        self.db_path = Path(db_path)
        self.source = source
        self.max_age_hours = max_age_hours
        self.name = f"db:{source}"

    def fetch(self, start: datetime, end: datetime) -> CalendarResult:
        init_db(self.db_path)
        with connect(self.db_path) as con:
            fetch = con.execute(
                "SELECT * FROM calendar_fetches WHERE source = ? ORDER BY id DESC LIMIT 1",
                (self.source,),
            ).fetchone()
            rows = con.execute(
                "SELECT event, ts_utc, importance, source FROM macro_events "
                "WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc",
                (start.isoformat(), end.isoformat()),
            ).fetchall()

        events = []
        for row in rows:
            events.append(
                CalendarEvent(
                    event=row["event"],
                    ts_utc=datetime.fromisoformat(row["ts_utc"]),
                    importance=str(row["importance"] or "medium"),
                    source=str(row["source"] or self.source),
                )
            )

        if fetch is None:
            if events:
                return CalendarResult(CalendarStatus.OK, events, None, "datos manuales")
            return CalendarResult(
                CalendarStatus.UNCONFIGURED,
                [],
                None,
                "sin proveedor de calendario configurado",
            )

        status = CalendarStatus(str(fetch["status"]))
        fetched_at = datetime.fromisoformat(str(fetch["fetched_at"]))
        if status == CalendarStatus.OK:
            age = datetime.now(timezone.utc) - fetched_at
            if age > timedelta(hours=self.max_age_hours):
                status = CalendarStatus.STALE
        return CalendarResult(status, events, fetched_at, str(fetch["message"] or ""))


def record_calendar_fetch(
    db_path: str | Path,
    *,
    source: str,
    status: CalendarStatus,
    events_count: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    message: str = "",
) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO calendar_fetches"
            "(source, fetched_at, window_start, window_end, status, events_count, message) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                source,
                utcnow(),
                window_start.isoformat() if window_start else None,
                window_end.isoformat() if window_end else None,
                status.value,
                int(events_count),
                message[:500],
            ),
        )


def add_calendar_event(
    db_path: str | Path,
    *,
    event: str,
    ts_utc: datetime,
    importance: str = "high",
    source: str = "manual",
) -> None:
    init_db(db_path)
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=timezone.utc)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO macro_events(event, ts_utc, importance, source, fetched_at) "
            "VALUES(?,?,?,?,?)",
            (event, ts_utc.astimezone(timezone.utc).isoformat(), importance, source, utcnow()),
        )
    record_calendar_fetch(
        db_path,
        source=source,
        status=CalendarStatus.OK,
        events_count=1,
        message="evento manual",
    )


def check_blackout(
    provider: CalendarProvider,
    now: datetime,
    *,
    minutes_before: int,
    minutes_after: int = 0,
    min_importance: str = "high",
    require_data: bool = True,
) -> BlackoutResult:
    """Blackout alrededor de eventos de alta importancia.

    - `OK` sin eventos: no bloquea.
    - `UNCONFIGURED`, `ERROR`, `STALE`: si `require_data`, bloquea aperturas
      (no se puede afirmar que no haya eventos).
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(minutes=max(0, minutes_after))
    end = now + timedelta(minutes=max(0, minutes_before))
    result = provider.fetch(start, end)

    if result.status != CalendarStatus.OK:
        return BlackoutResult(
            blocked=bool(require_data),
            status=result.status,
            reason=f"calendario {result.status.value}: {result.message or 'sin datos'}",
            events=[],
            data_ok=False,
        )

    rank = {"low": 1, "medium": 2, "high": 3}
    threshold = rank.get(min_importance.lower(), 3)
    relevant = [
        event for event in result.events if rank.get(event.importance.lower(), 0) >= threshold
    ]
    if relevant:
        event = relevant[0]
        return BlackoutResult(
            blocked=True,
            status=result.status,
            reason=f"evento {event.event} a las {event.ts_utc.isoformat()}",
            events=relevant,
            data_ok=True,
        )
    return BlackoutResult(
        blocked=False,
        status=result.status,
        reason="sin eventos relevantes",
        events=[],
        data_ok=True,
    )


def rules_from_settings(settings: Settings) -> PropRules:
    try:
        return from_yaml(
            settings.prop.firm,
            settings.prop.phase,
            settings.prop.account_size,
            buffer_pct=settings.prop.buffer_pct,
        )
    except KeyError:
        return ftmo(
            settings.prop.account_size,
            settings.prop.phase,
            buffer_pct=settings.prop.buffer_pct,
        )


def calendar_block_for_settings(
    db_path: str | Path,
    settings: Settings,
    *,
    now: datetime | None = None,
    source: str = "manual",
) -> BlackoutResult:
    """Atajo para el orquestador/CLI; no hace nada si news_blackout_min=0."""
    rules = rules_from_settings(settings)
    if rules.news_blackout_min <= 0:
        return BlackoutResult(False, CalendarStatus.OK, "blackout desactivado")
    provider = DbCalendarProvider(db_path, source=source)
    return check_blackout(
        provider,
        now or datetime.now(timezone.utc),
        minutes_before=rules.news_blackout_min,
        require_data=True,
    )


__all__ = [
    "BlackoutResult",
    "CalendarEvent",
    "CalendarProvider",
    "CalendarResult",
    "CalendarStatus",
    "DbCalendarProvider",
    "StaticCalendarProvider",
    "add_calendar_event",
    "calendar_block_for_settings",
    "check_blackout",
    "record_calendar_fetch",
    "rules_from_settings",
]
