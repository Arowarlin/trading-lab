from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.intel.calendar import (
    CalendarEvent,
    CalendarStatus,
    CsvCalendarProvider,
    DbCalendarProvider,
    StaticCalendarProvider,
    add_calendar_event,
    calendar_block_for_rules,
    calendar_block_for_settings,
    check_blackout,
    record_calendar_fetch,
)
from tradinglab.prop import AccountState, PropGuard, ftmo

NOW = datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc)


def _event(minutes: int, importance: str = "high") -> CalendarEvent:
    return CalendarEvent("FOMC", NOW + timedelta(minutes=minutes), importance)


def test_blackout_evento_alto():
    result = check_blackout(
        StaticCalendarProvider([_event(10)]),
        NOW,
        minutes_before=30,
        require_data=True,
    )
    assert result.blocked
    assert result.data_ok
    assert "FOMC" in result.reason


def test_blackout_fomc_nfp_cpi_antes_y_despues():
    names = ["FOMC", "NFP", "CPI"]
    for name in names:
        before = check_blackout(
            StaticCalendarProvider([CalendarEvent(name, NOW + timedelta(minutes=10), "high")]),
            NOW,
            minutes_before=30,
            minutes_after=30,
        )
        after = check_blackout(
            StaticCalendarProvider([CalendarEvent(name, NOW - timedelta(minutes=10), "high")]),
            NOW,
            minutes_before=30,
            minutes_after=30,
        )
        outside = check_blackout(
            StaticCalendarProvider([CalendarEvent(name, NOW + timedelta(minutes=31), "high")]),
            NOW,
            minutes_before=30,
            minutes_after=30,
        )
        assert before.blocked and name in before.reason
        assert after.blocked and name in after.reason
        assert not outside.blocked


def test_calendar_block_for_rules_usa_ventana_antes_y_despues(tmp_path):
    db = tmp_path / "lab.db"
    for name, minutes in (("FOMC", 10), ("NFP", -10), ("CPI", 40)):
        add_calendar_event(
            db,
            event=name,
            ts_utc=NOW + timedelta(minutes=minutes),
            importance="high",
        )
    rules = ftmo(100_000, news_blackout_min=30)
    provider = DbCalendarProvider(db)
    result = calendar_block_for_rules(provider, rules, now=NOW)
    assert result.blocked
    assert result.data_ok
    assert "FOMC" in result.reason or "NFP" in result.reason

    outside = calendar_block_for_rules(
        DbCalendarProvider(db),
        rules,
        now=NOW + timedelta(minutes=90),
    )
    assert not outside.blocked


def test_calendar_block_for_rules_sin_datos_bloquea(tmp_path):
    rules = ftmo(100_000, news_blackout_min=30)
    provider = StaticCalendarProvider([], status=CalendarStatus.UNCONFIGURED)
    result = calendar_block_for_rules(provider, rules, now=NOW)
    assert result.blocked
    assert result.data_ok is False


def test_blackout_evento_bajo_no_bloquea():
    result = check_blackout(
        StaticCalendarProvider([_event(10, "low")]),
        NOW,
        minutes_before=30,
        min_importance="high",
    )
    assert not result.blocked
    assert result.data_ok


def test_blackout_ok_sin_eventos_no_bloquea():
    result = check_blackout(
        StaticCalendarProvider([], status=CalendarStatus.OK),
        NOW,
        minutes_before=30,
    )
    assert not result.blocked
    assert result.data_ok


def test_blackout_sin_datos_distingue_y_bloquea_si_require_data():
    provider = StaticCalendarProvider([], status=CalendarStatus.UNCONFIGURED)
    estricto = check_blackout(provider, NOW, minutes_before=30, require_data=True)
    permisivo = check_blackout(provider, NOW, minutes_before=30, require_data=False)
    assert estricto.blocked
    assert not estricto.data_ok
    assert not permisivo.blocked
    assert not permisivo.data_ok


def test_db_provider_estado_y_stale(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    provider = DbCalendarProvider(db)

    assert provider.fetch(NOW - timedelta(days=1), NOW + timedelta(days=1)).status == CalendarStatus.UNCONFIGURED

    add_calendar_event(db, event="FOMC", ts_utc=NOW + timedelta(minutes=10), importance="high")
    result = provider.fetch(NOW - timedelta(days=1), NOW + timedelta(days=1))
    assert result.status == CalendarStatus.OK
    assert len(result.events) == 1

    record_calendar_fetch(
        db,
        source="manual",
        status=CalendarStatus.OK,
        events_count=0,
    )
    assert provider.fetch(NOW - timedelta(days=1), NOW + timedelta(days=1)).status == CalendarStatus.OK

    with connect(db) as con:
        con.execute(
            "INSERT INTO calendar_fetches"
            "(source, fetched_at, status, events_count, message) VALUES(?,?,?,?,?)",
            ("manual", "2020-01-01T00:00:00+00:00", "ok", 0, "viejo"),
        )
    assert provider.fetch(NOW - timedelta(days=1), NOW + timedelta(days=1)).status == CalendarStatus.STALE


def test_guard_bloquea_apertura_y_permite_cierre():
    rules = ftmo(100_000)
    state = AccountState(
        balance=100_000,
        equity=100_000,
        initial_balance=100_000,
        day_start_balance=100_000,
        day_start_equity=100_000,
        peak_balance=100_000,
        peak_equity=100_000,
    )
    guard = PropGuard(rules)
    blocked = guard.evaluate(state, blocked_by_calendar=True, calendar_reason="FOMC")
    assert not blocked.allowed
    assert "calendario" in blocked.reason

    closing = guard.evaluate(state, closing=True, blocked_by_calendar=True)
    assert closing.allowed


def test_calendar_block_for_settings_desactivado():
    result = calendar_block_for_settings("data/lab.db", Settings())
    assert not result.blocked


def test_csv_ausente_vacio_y_valido(tmp_path):
    missing = CsvCalendarProvider(tmp_path / "missing.csv")
    assert missing.fetch(NOW, NOW).status == CalendarStatus.UNCONFIGURED

    empty = tmp_path / "empty.csv"
    empty.write_text("event_id,currency,event,scheduled_at_utc,impact,blackout_before_min,blackout_after_min,source_url\n", encoding="utf-8")
    assert CsvCalendarProvider(empty).fetch(NOW - timedelta(days=1), NOW + timedelta(days=1)).status == CalendarStatus.OK

    valid = tmp_path / "events.csv"
    valid.write_text(
        "event_id,currency,event,scheduled_at_utc,impact,blackout_before_min,blackout_after_min,source_url\n"
        "1,USD,FOMC,2026-11-07T18:10:00Z,high,30,30,https://example.com\n",
        encoding="utf-8",
    )
    result = CsvCalendarProvider(valid).fetch(NOW - timedelta(days=1), NOW + timedelta(days=1))
    assert result.status == CalendarStatus.OK
    assert len(result.events) == 1


def test_csv_ventana_por_evento(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text(
        "event_id,currency,event,scheduled_at_utc,impact,blackout_before_min,blackout_after_min,source_url\n"
        "1,USD,FOMC,2026-11-07T18:10:00Z,high,30,30,https://example.com\n",
        encoding="utf-8",
    )
    provider = CsvCalendarProvider(path)
    # La ventana global es 5 min, pero el evento pide 30.
    result = check_blackout(provider, NOW, minutes_before=5, minutes_after=0)
    assert result.blocked
    assert result.data_ok


def test_csv_invalido_es_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "event_id,currency,event,scheduled_at_utc,impact,blackout_before_min,blackout_after_min,source_url\n"
        "1,USD,FOMC,no-es-fecha,high,30,30,https://example.com\n",
        encoding="utf-8",
    )
    result = CsvCalendarProvider(path).fetch(NOW - timedelta(days=1), NOW + timedelta(days=1))
    assert result.status == CalendarStatus.ERROR
