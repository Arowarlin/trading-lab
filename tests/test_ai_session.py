from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from tradinglab.ai_session import (
    lock_acquire,
    lock_release,
    preflight,
    session_window,
)
from tradinglab.ai_trader import session_activity
from tradinglab.db import connect, init_db

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
SANTO = ZoneInfo("America/Santo_Domingo")


class _Broker:
    def __init__(self, *, mode: str = "demo", tick_age_minutes: int = 0,
                 tick_time: datetime | None = None):
        self.mode = mode
        self.tick_age_minutes = tick_age_minutes
        self.tick_time = tick_time

    def health(self):
        return {
            "mode": self.mode,
            "equity": 100_000.0,
            "offset_known": True,
            "server_utc_offset_hours": 0,
        }

    def positions(self):
        return []

    def tick(self, symbol):
        stamp = (
            self.tick_time
            or datetime.now(timezone.utc) - timedelta(minutes=self.tick_age_minutes)
        )
        return {"time": stamp, "bid": 1.0, "ask": 1.0}

    def shutdown(self):
        pass


def test_ventanas_con_y_sin_horario_de_verano():
    # London: 07:05 local en invierno y 08:05 local en verano.
    assert session_window(
        "london", datetime(2026, 1, 15, 7, 5, tzinfo=LONDON)
    )[0] is True
    assert session_window(
        "london", datetime(2026, 7, 15, 8, 5, tzinfo=LONDON)
    )[0] is True
    assert session_window(
        "london", datetime(2026, 7, 15, 12, 0, tzinfo=LONDON)
    )[0] is False
    # NY: 09:35 local en invierno y en verano; 08:35 y 10:35 no.
    assert session_window(
        "ny", datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    )[0] is True
    assert session_window(
        "ny", datetime(2026, 7, 15, 9, 35, tzinfo=NEW_YORK)
    )[0] is True
    assert session_window(
        "ny", datetime(2026, 7, 15, 8, 35, tzinfo=NEW_YORK)
    )[0] is False
    assert session_window(
        "ny", datetime(2026, 7, 15, 10, 35, tzinfo=NEW_YORK)
    )[0] is False
    assert session_window(
        "daily", datetime(2026, 7, 15, 18, 15, tzinfo=NEW_YORK)
    )[0] is True
    assert session_window(
        "scalp", datetime(2026, 7, 15, 10, 0, tzinfo=NEW_YORK)
    )[0] is True
    assert session_window(
        "scalp", datetime(2026, 7, 15, 13, 0, tzinfo=NEW_YORK)
    )[0] is False
    assert session_window(
        "manage", datetime(2026, 1, 18, 17, 5, tzinfo=SANTO)
    )[0] is True
    assert session_window(
        "manage", datetime(2026, 1, 16, 17, 59, tzinfo=SANTO)
    )[0] is True
    assert session_window(
        "manage", datetime(2026, 1, 16, 18, 0, tzinfo=SANTO)
    )[0] is False
    assert session_window(
        "manage", datetime(2026, 1, 17, 12, 0, tzinfo=SANTO)
    )[0] is False


def test_candado_adquiere_bloquea_y_libera(tmp_path):
    path = tmp_path / "ai_trader.lock"
    now = datetime(2026, 1, 15, 7, 5, tzinfo=timezone.utc)
    first = lock_acquire(path, pid=123, now=now, session="london")
    assert first["ok"] is True
    assert first["lock"]["pid"] == 123
    second = lock_acquire(path, pid=456, now=now, session="ny")
    assert second["ok"] is False
    assert "PID 123" in second["reason"]
    assert lock_release(path, pid=999)["ok"] is False
    assert lock_release(path, pid=123)["ok"] is True
    assert lock_acquire(path, pid=456, now=now, session="ny")["ok"] is True


def test_preflight_sale_por_ventana_antes_de_mt5():
    now = datetime(2026, 1, 15, 8, 35, tzinfo=NEW_YORK)
    result = preflight("ny", now=now, connect=False)
    assert result["ok"] is False
    assert result["stage"] == "window"


def test_preflight_sale_por_mt5_sin_conexion(tmp_path):
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight("ny", now=now, db_path=tmp_path / "lab.db", connect=False)
    assert result["ok"] is False
    assert result["stage"] == "mt5"


def test_preflight_sale_por_killswitch(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT OR REPLACE INTO killswitch"
            "(id, active, reason, triggered_at, reset_at, equity, peak, day_start) "
            "VALUES(1, 1, 'prueba', ?, NULL, 100000, 100000, 100000)",
            (datetime.now(timezone.utc).isoformat(),),
        )
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight("ny", now=now, db_path=db, broker=_Broker())
    assert result["ok"] is False
    assert result["stage"] == "killswitch"


def test_preflight_sale_por_cuenta_no_demo(tmp_path):
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight(
        "ny", now=now, db_path=tmp_path / "lab.db", broker=_Broker(mode="live")
    )
    assert result["ok"] is False
    assert result["stage"] == "demo"


def test_preflight_sale_por_stop_global(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "status, source, magic, risk_usd, pnl, exit_ts) "
            "VALUES('loss',?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(), "intraday", "XAUUSD",
                "liquidity_sweep", "sell", "closed", "forward", 20261192,
                500, -4000, datetime.now(timezone.utc).isoformat(),
            ),
        )
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight("ny", now=now, db_path=db, broker=_Broker())
    assert result["ok"] is False
    assert result["stage"] == "global_stop"


def test_preflight_sale_por_mercado_cerrado(tmp_path):
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight(
        "ny", now=now, db_path=tmp_path / "lab.db",
        broker=_Broker(
            tick_time=now.astimezone(timezone.utc) - timedelta(minutes=30)
        ),
    )
    assert result["ok"] is False
    assert result["stage"] == "market"


def test_preflight_ok(tmp_path):
    now = datetime(2026, 1, 15, 9, 35, tzinfo=NEW_YORK)
    result = preflight(
        "ny", now=now, db_path=tmp_path / "lab.db",
        broker=_Broker(tick_time=now.astimezone(timezone.utc)),
    )
    assert result["ok"] is True
    assert result["stage"] == "ok"
    assert result["equity"] == pytest.approx(100_000.0)


def test_session_activity_lee_estado_de_tarea(tmp_path, monkeypatch):
    import tradinglab.ai_trader as module

    monkeypatch.setattr(module, "ROOT", tmp_path)
    status_dir = tmp_path / "logs" / "ai_trader" / "status"
    status_dir.mkdir(parents=True)
    now = datetime(2026, 1, 15, 10, 30, tzinfo=LONDON)
    date_key = now.astimezone(SANTO).date().isoformat()
    (status_dir / f"{date_key}_london_090000.json").write_text(
        json.dumps({
            "ts": now.astimezone(timezone.utc).isoformat(),
            "session": "london",
            "status": "ok",
            "reason": "ok",
        }),
        encoding="utf-8",
    )
    db = tmp_path / "lab.db"
    init_db(db)
    activity = session_activity(db, now=now)
    assert activity["tasks"]["london"]["ok"] is True
    assert not any("London no corrió" in warning for warning in activity["warnings"])
