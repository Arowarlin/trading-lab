from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from tradinglab.db import connect
from tradinglab.intel.calendar import (
    CalendarStatus,
    DbCalendarProvider,
    calendar_block_for_rules,
)
from tradinglab.intel.fred import FredCalendarProvider
from tradinglab.prop import ftmo


class Fixture:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.fail_dates = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/releases"):
            search = request.url.params.get("search_text", "")
            if search == "Consumer Price Index":
                return httpx.Response(
                    200,
                    json={
                        "releases": [
                            {"id": 10, "name": "Consumer Price Index"},
                            {"id": 28, "name": "Consumer Price Index Excluding Energy Commodities"},
                        ]
                    },
                )
            if search == "Employment Situation":
                return httpx.Response(
                    200,
                    json={"releases": [{"id": 50, "name": "Employment Situation"}]},
                )
        if path.endswith("/release/dates"):
            if self.fail_dates:
                return httpx.Response(500, text="boom")
            release_id = request.url.params.get("release_id")
            dates = {
                "10": ["2026-01-13", "2026-11-10", "2026-12-10"],
                "50": ["2026-11-06", "2026-12-04"],
            }.get(str(release_id), [])
            return httpx.Response(
                200,
                json={
                    "release_dates": [
                        {"release_id": int(release_id), "date": day} for day in dates
                    ]
                },
            )
        return httpx.Response(404, json={"error": "not found"})


def _provider(tmp_path, fixture, **kwargs):
    return FredCalendarProvider(
        tmp_path / "lab.db",
        api_key="test-key",
        cache_dir=tmp_path / "cache",
        client=httpx.Client(transport=httpx.MockTransport(fixture)),
        min_interval_s=0,
        cache_ttl_s=3600,
        **kwargs,
    )


def test_descubre_ids_y_guarda_eventos_futuros(tmp_path):
    fixture = Fixture()
    provider = _provider(tmp_path, fixture)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    result = provider.fetch(now, now.replace(month=12, day=31))

    assert result.status == CalendarStatus.OK
    names = {event.event for event in result.events}
    assert names == {"CPI", "NFP"}
    cpi = [event for event in result.events if event.event == "CPI"]
    nfp = [event for event in result.events if event.event == "NFP"]
    assert any(event.ts_utc.date().isoformat() == "2026-11-10" for event in cpi)
    assert any(event.ts_utc.date().isoformat() == "2026-12-04" for event in nfp)
    assert all(event.importance == "high" for event in result.events)
    assert all(event.source.startswith("fred:") for event in result.events)

    with connect(tmp_path / "lab.db") as con:
        rows = con.execute("SELECT event, importance, source FROM macro_events").fetchall()
        fetch = con.execute(
            "SELECT status, events_count FROM calendar_fetches WHERE source='fred' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert {row["event"] for row in rows} == {"CPI", "NFP"}
    assert all(row["importance"] == "high" for row in rows)
    assert fetch["status"] == "ok" and fetch["events_count"] == 3
    dates_request = next(request for request in fixture.requests if request.url.path.endswith("/release/dates"))
    assert dates_request.url.params.get("include_release_dates_with_no_data") == "true"

    # La caché evita una segunda consulta HTTP.
    calls = len(fixture.requests)
    provider2 = _provider(tmp_path, fixture)
    second = provider2.fetch(now, now.replace(month=12, day=31))
    assert second.status == CalendarStatus.OK
    assert len(fixture.requests) == calls


def test_sin_api_key_no_hace_peticiones(tmp_path):
    fixture = Fixture()
    provider = FredCalendarProvider(
        tmp_path / "lab.db",
        api_key="",
        cache_dir=tmp_path / "cache",
        client=httpx.Client(transport=httpx.MockTransport(fixture)),
    )
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    result = provider.fetch(now, now)
    assert result.status == CalendarStatus.UNCONFIGURED
    assert fixture.requests == []


def test_fallo_fred_devuelve_stale_con_guardado(tmp_path):
    fixture = Fixture()
    provider = _provider(tmp_path, fixture)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    assert provider.fetch(now, now.replace(month=12, day=31)).status == CalendarStatus.OK

    failing = Fixture()
    failing.fail_dates = True
    provider2 = FredCalendarProvider(
        tmp_path / "lab.db",
        api_key="test-key",
        cache_dir=tmp_path / "cache2",
        client=httpx.Client(transport=httpx.MockTransport(failing)),
        min_interval_s=0,
        cache_ttl_s=0,
    )
    result = provider2.fetch(now, now.replace(month=12, day=31))
    assert result.status == CalendarStatus.STALE
    assert result.events
    assert "FRED no disponible" in result.message
    assert "test-key" not in result.message
    with connect(tmp_path / "lab.db") as con:
        fetch = con.execute(
            "SELECT status FROM calendar_fetches WHERE source='fred' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert fetch["status"] == "stale"
    block = calendar_block_for_rules(
        DbCalendarProvider(tmp_path / "lab.db"),
        ftmo(100_000, news_blackout_min=30),
        now=now,
    )
    assert block.blocked is True
    assert block.data_ok is False


def test_rate_limit_usa_sleeper(tmp_path):
    waits: list[float] = []
    times = iter([0.0, 0.0, 0.2, 0.2])
    provider = FredCalendarProvider(
        tmp_path / "lab.db",
        api_key="test-key",
        cache_dir=tmp_path / "cache",
        min_interval_s=1.0,
        clock=lambda: next(times),
        sleeper=waits.append,
    )
    provider._throttle()
    provider._throttle()
    assert waits == pytest.approx([1.0, 0.8])


def test_cache_no_guarda_api_key(tmp_path):
    fixture = Fixture()
    provider = _provider(tmp_path, fixture)
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    provider.fetch(now, now.replace(month=12, day=31))
    files = list((tmp_path / "cache").glob("*.json"))
    assert files
    for path in files:
        assert "test-key" not in path.read_text(encoding="utf-8")
