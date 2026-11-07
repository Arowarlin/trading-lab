"""Calendario macro FRED detrás de la interfaz `CalendarProvider`.

- Descubre los `release_id` por nombre con `/fred/releases` (no se inventan).
- Lee fechas con `/fred/release/dates` y
  `include_release_dates_with_no_data=true` para incluir programadas futuras.
- Guarda los eventos en `macro_events` con importancia `high`.
- Usa caché local y un límite conservador de peticiones.
- Si FRED falla, devuelve los eventos ya guardados con estado `stale`.
- Si no hay eventos guardados, devuelve `stale` vacío (nunca "sin eventos").

FRED solo publica la fecha, no la hora. Para el guard se usa la convención
operativa 08:30 America/New_York (hora habitual de CPI/NFP), documentada en
README. No es un dato que venga de FRED.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from ..config import load_secrets
from ..db import connect, init_db, utcnow
from .calendar import (
    CalendarEvent,
    CalendarResult,
    CalendarStatus,
    DbCalendarProvider,
    record_calendar_fetch,
)

FRED_BASE = "https://api.stlouisfed.org/fred"
RELEASE_NAMES = ("Consumer Price Index", "Employment Situation")
RELEASE_LABELS = {
    "Consumer Price Index": "CPI",
    "Employment Situation": "NFP",
}
RELEASE_TIME_ET = dt_time(8, 30)
RELEASE_TZ = "America/New_York"


class FredError(RuntimeError):
    pass


def _api_key() -> str | None:
    load_secrets()
    return os.getenv("FRED_API_KEY")


class FredCalendarProvider:
    """Proveedor FRED con caché, rate limit y persistencia en SQLite."""

    name = "fred"

    def __init__(
        self,
        db_path: str | Path,
        *,
        api_key: str | None = None,
        cache_dir: str | Path = "data/cache/fred",
        cache_ttl_s: float = 12 * 3600,
        min_interval_s: float = 0.6,
        client: httpx.Client | None = None,
        release_names: tuple[str, ...] = RELEASE_NAMES,
        release_time_et: dt_time = RELEASE_TIME_ET,
        release_tz: str = RELEASE_TZ,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._api_key = api_key if api_key is not None else _api_key()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_s = max(0.0, float(cache_ttl_s))
        self.min_interval_s = max(0.0, float(min_interval_s))
        self.release_names = tuple(release_names)
        self.release_time_et = release_time_et
        self.release_tz = release_tz
        self._client = client
        self._owns_client = client is None
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._last_call = 0.0
        self._release_ids: dict[str, int] = {}

    # ------------------------------------------------------------------ HTTP

    def _throttle(self) -> None:
        now = self._clock()
        wait = self.min_interval_s - (now - self._last_call)
        if wait > 0:
            self._sleeper(wait)
        self._last_call = self._clock()

    def _cache_path(self, endpoint: str, params: dict) -> Path:
        safe = {
            k: v
            for k, v in params.items()
            if k not in {"api_key", "file_type"}
        }
        digest = hashlib.sha256(
            json.dumps({"endpoint": endpoint, "params": safe}, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        return self.cache_dir / f"fred_{digest}.json"

    def _get(self, endpoint: str, params: dict) -> dict:
        if not self._api_key:
            raise FredError("falta FRED_API_KEY")
        cache_path = self._cache_path(endpoint, params)
        if cache_path.exists() and self.cache_ttl_s > 0:
            age = time.time() - cache_path.stat().st_mtime
            if age <= self.cache_ttl_s:
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
        self._throttle()
        query = dict(params)
        query["api_key"] = self._api_key
        query["file_type"] = "json"
        if self._client is None:
            self._client = httpx.Client(timeout=20)
            self._owns_client = True
        try:
            response = self._client.get(f"{FRED_BASE}/{endpoint}", params=query)
        except httpx.HTTPError as exc:
            raise FredError(f"FRED no disponible: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise FredError(f"FRED HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise FredError("FRED respuesta no JSON") from exc
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return payload

    # --------------------------------------------------------------- releases

    def _discover(self) -> dict[str, int]:
        if self._release_ids:
            return self._release_ids
        found: dict[str, int] = {}
        for name in self.release_names:
            payload = self._get(
                "releases",
                {"search_text": name, "limit": 1000},
            )
            releases = payload.get("releases") or []
            match = next(
                (
                    rel
                    for rel in releases
                    if str(rel.get("name") or "").strip().lower() == name.lower()
                ),
                None,
            )
            if match is None:
                raise FredError(f"FRED no encontró release: {name}")
            found[name] = int(match["id"])
        self._release_ids = found
        return found

    def _release_dates(self, release_id: int, start: date, end: date) -> list[date]:
        payload = self._get(
            "release/dates",
            {
                "release_id": release_id,
                "include_release_dates_with_no_data": "true",
                "realtime_start": start.isoformat(),
                "realtime_end": end.isoformat(),
                "limit": 1000,
                "sort_order": "asc",
            },
        )
        out: list[date] = []
        for item in payload.get("release_dates") or []:
            raw = str(item.get("date") or "")
            try:
                value = date.fromisoformat(raw)
            except ValueError:
                continue
            if start <= value <= end:
                out.append(value)
        return out

    def _event_ts(self, day: date) -> datetime:
        tz = ZoneInfo(self.release_tz)
        local = datetime.combine(day, self.release_time_et, tzinfo=tz)
        return local.astimezone(UTC)

    # ------------------------------------------------------------------ DB

    def _store(self, events: list[CalendarEvent]) -> None:
        init_db(self.db_path)
        with connect(self.db_path) as con:
            for event in events:
                con.execute(
                    "INSERT INTO macro_events(event, ts_utc, importance, source, fetched_at) "
                    "SELECT ?,?,?,?,? WHERE NOT EXISTS ("
                    "SELECT 1 FROM macro_events WHERE event=? AND ts_utc=? AND source=?"
                    ")",
                    (
                        event.event,
                        event.ts_utc.isoformat(),
                        event.importance,
                        event.source,
                        utcnow(),
                        event.event,
                        event.ts_utc.isoformat(),
                        event.source,
                    ),
                )

    def _sync(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        release_ids = self._discover()
        events: list[CalendarEvent] = []
        for name, release_id in release_ids.items():
            label = RELEASE_LABELS.get(name, name)
            for day in self._release_dates(release_id, start.date(), end.date()):
                events.append(
                    CalendarEvent(
                        event=label,
                        ts_utc=self._event_ts(day),
                        importance="high",
                        source=f"fred:{release_id}",
                    )
                )
        events.sort(key=lambda event: event.ts_utc)
        self._store(events)
        record_calendar_fetch(
            self.db_path,
            source="fred",
            status=CalendarStatus.OK,
            events_count=len(events),
            window_start=start,
            window_end=end,
            message="FRED release/dates; include_release_dates_with_no_data=true; ids="
            + ",".join(f"{k}={v}" for k, v in release_ids.items()),
        )
        return events

    # --------------------------------------------------------------- API

    def fetch(self, start: datetime, end: datetime) -> CalendarResult:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        start = start.astimezone(UTC)
        end = end.astimezone(UTC)
        if not self._api_key:
            return CalendarResult(
                CalendarStatus.UNCONFIGURED,
                [],
                None,
                "falta FRED_API_KEY",
            )

        cached = DbCalendarProvider(
            self.db_path,
            source="fred",
            max_age_hours=self.cache_ttl_s / 3600 if self.cache_ttl_s else 0,
        ).fetch(start, end)
        if cached.status == CalendarStatus.OK and cached.fetched_at:
            fetched_at = cached.fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
            age = datetime.now(UTC) - fetched_at.astimezone(UTC)
            if age.total_seconds() <= self.cache_ttl_s:
                return cached

        try:
            events = self._sync(start, end)
            return CalendarResult(
                CalendarStatus.OK,
                events,
                datetime.now(UTC),
                "FRED sincronizado",
            )
        except Exception as exc:
            stored = DbCalendarProvider(
                self.db_path,
                max_age_hours=24 * 365,
            ).fetch(start, end)
            message = f"FRED no disponible: {str(exc)[:160]}"
            try:
                record_calendar_fetch(
                    self.db_path,
                    source="fred",
                    status=CalendarStatus.STALE,
                    events_count=len(stored.events),
                    window_start=start,
                    window_end=end,
                    message=message,
                )
            except Exception:
                pass
            return CalendarResult(
                CalendarStatus.STALE,
                stored.events,
                stored.fetched_at,
                message,
            )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None


__all__ = [
    "FRED_BASE",
    "FredCalendarProvider",
    "FredError",
    "RELEASE_LABELS",
    "RELEASE_NAMES",
    "RELEASE_TIME_ET",
    "RELEASE_TZ",
]
