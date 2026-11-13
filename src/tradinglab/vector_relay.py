"""Relevo de alertas de Vector a los canales del laboratorio.

Vector escribe `logs/vector/alerts.jsonl` (una línea JSON por evento warn o
critical). Este módulo lee solo las líneas nuevas, guarda el offset en SQLite,
deduplica por (fuente, patrón) durante 30 minutos y envía solo las critical con
`alerts.send`, respetando el presupuesto semanal. Las warn no se envían: solo
quedan contadas para el resumen diario.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .alerts import send as send_alert
from .alerts_budget import weekly_budget
from .config import DEFAULT_DB, ROOT
from .db import connect, init_db, utcnow

DEFAULT_PATH = ROOT / "logs" / "vector" / "alerts.jsonl"
DEFAULT_WINDOW_MINUTES = 30


def _ensure_tables(con) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS vector_relay ("
        "path TEXT PRIMARY KEY,"
        "offset INTEGER NOT NULL DEFAULT 0,"
        "updated_at TEXT NOT NULL,"
        "last_run_at TEXT,"
        "sent INTEGER NOT NULL DEFAULT 0,"
        "skipped INTEGER NOT NULL DEFAULT 0,"
        "warned INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS vector_alert_dedupe ("
        "key TEXT PRIMARY KEY,"
        "first_ts TEXT NOT NULL,"
        "last_ts TEXT NOT NULL,"
        "count INTEGER NOT NULL DEFAULT 0,"
        "escalated_at TEXT"
        ")"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS vector_daily ("
        "day TEXT PRIMARY KEY,"
        "warn INTEGER NOT NULL DEFAULT 0,"
        "critical INTEGER NOT NULL DEFAULT 0,"
        "sent INTEGER NOT NULL DEFAULT 0"
        ")"
    )


def _parse_moment(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _daily_inc(con, day: str, field: str, amount: int = 1) -> None:
    if field not in {"warn", "critical", "sent"}:
        raise ValueError(f"campo diario inválido: {field}")
    con.execute(
        "INSERT INTO vector_daily(day, warn, critical, sent) VALUES(?,0,0,0) "
        "ON CONFLICT(day) DO NOTHING",
        (day,),
    )
    con.execute(
        f"UPDATE vector_daily SET {field} = {field} + ? WHERE day = ?",
        (amount, day),
    )


def relay(
    db_path: str | Path = DEFAULT_DB,
    *,
    path: str | Path | None = None,
    sender=None,
    now: datetime | None = None,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> dict:
    target = Path(path) if path else DEFAULT_PATH
    base = {
        "path": str(target),
        "sent": 0,
        "warned": 0,
        "skipped_dedupe": 0,
        "skipped_budget": 0,
        "skipped_channel": 0,
        "bad_lines": 0,
    }
    if not target.exists():
        return {
            **base,
            "ok": True,
            "skipped": True,
            "reason": "sin archivo alerts.jsonl",
        }

    init_db(db_path)
    sender = sender or send_alert
    moment = now or datetime.now(timezone.utc)
    window = timedelta(minutes=max(1, int(window_minutes)))
    remaining_budget = int(weekly_budget(db_path).get("remaining") or 0)

    with connect(db_path) as con:
        _ensure_tables(con)
        state = con.execute(
            "SELECT * FROM vector_relay WHERE path = ?", (str(target),)
        ).fetchone()
        offset = int(state["offset"]) if state else 0
        size = target.stat().st_size
        if size < offset:
            offset = 0
        with target.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()

    lines: list[bytes] = []
    consumed = 0
    for raw in data.splitlines(keepends=True):
        if not raw.endswith(b"\n"):
            break
        lines.append(raw)
        consumed += len(raw)

    if not lines:
        with connect(db_path) as con:
            _ensure_tables(con)
            con.execute(
                "INSERT INTO vector_relay(path, offset, updated_at, last_run_at) "
                "VALUES(?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                "updated_at=excluded.updated_at, last_run_at=excluded.last_run_at",
                (str(target), offset, utcnow(), moment.isoformat()),
            )
        return {
            **base,
            "ok": True,
            "skipped": False,
            "processed": 0,
            "offset_start": offset,
            "offset_end": offset,
        }

    counters = {
        "sent": 0,
        "warned": 0,
        "skipped_dedupe": 0,
        "skipped_budget": 0,
        "skipped_channel": 0,
        "bad_lines": 0,
    }
    with connect(db_path) as con:
        _ensure_tables(con)
        for raw in lines:
            try:
                event = json.loads(raw.decode("utf-8", errors="replace"))
            except (TypeError, ValueError):
                counters["bad_lines"] += 1
                continue
            if not isinstance(event, dict):
                counters["bad_lines"] += 1
                continue
            severity = str(event.get("severity") or "").lower()
            if severity not in {"warn", "critical"}:
                continue
            source = str(event.get("source") or "unknown")
            pattern = str(event.get("pattern") or "unknown")
            key = f"{source}|{pattern}"
            event_moment = _parse_moment(
                event.get("timestamp") if isinstance(event.get("timestamp"), str) else None,
                moment,
            )
            row = con.execute(
                "SELECT * FROM vector_alert_dedupe WHERE key = ?", (key,)
            ).fetchone()
            escalate = False
            if row is not None:
                last = _parse_moment(row["last_ts"], event_moment)
                if event_moment - last <= window:
                    count = int(row["count"]) + 1
                    # Una sola desconexión es warn; la segunda en la ventana
                    # se trata como critical (MT5 inestable).
                    if pattern == "mt5_connection" and count == 2:
                        escalate = True
                        severity = "critical"
                    con.execute(
                        "UPDATE vector_alert_dedupe SET last_ts = ?, count = ? "
                        "WHERE key = ?",
                        (event_moment.isoformat(), count, key),
                    )
                    if not escalate:
                        counters["skipped_dedupe"] += 1
                        continue
                else:
                    con.execute(
                        "INSERT OR REPLACE INTO vector_alert_dedupe"
                        "(key, first_ts, last_ts, count, escalated_at) "
                        "VALUES(?,?,?,?,NULL)",
                        (key, event_moment.isoformat(), event_moment.isoformat(), 1),
                    )
            else:
                con.execute(
                    "INSERT INTO vector_alert_dedupe"
                    "(key, first_ts, last_ts, count, escalated_at) "
                    "VALUES(?,?,?,?,NULL)",
                    (key, event_moment.isoformat(), event_moment.isoformat(), 1),
                )

            day = event_moment.date().isoformat()
            if severity == "warn":
                counters["warned"] += 1
                _daily_inc(con, day, "warn")
                continue

            if remaining_budget <= 0:
                counters["skipped_budget"] += 1
                continue
            raw_message = str(event.get("message") or "").strip()
            task = str(event.get("task") or "").strip()
            symbol = str(event.get("symbol") or "").strip()
            detail = f"{event_moment.isoformat()} · {source}"
            if task:
                detail += f" · {task}"
            if symbol:
                detail += f" · {symbol}"
            detail += f" · {pattern}: {raw_message}"
            result = sender(
                event=f"vector_{pattern}",
                message=detail[:1000],
                severity="critical",
                db_path=db_path,
            )
            _daily_inc(con, day, "critical")
            if getattr(result, "ok", False) and not getattr(result, "skipped", False):
                counters["sent"] += 1
                remaining_budget -= 1
                _daily_inc(con, day, "sent")
                con.execute(
                    "INSERT INTO alert_budget(ts, event, channel, severity) "
                    "VALUES(?,?,?,?)",
                    (
                        utcnow(),
                        f"vector_{pattern}",
                        getattr(result, "channel", None),
                        "critical",
                    ),
                )
            else:
                counters["skipped_channel"] += 1

        con.execute(
            "INSERT INTO vector_relay(path, offset, updated_at, last_run_at, sent, "
            "skipped, warned) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET offset=excluded.offset, "
            "updated_at=excluded.updated_at, last_run_at=excluded.last_run_at, "
            "sent=vector_relay.sent + excluded.sent, "
            "skipped=vector_relay.skipped + excluded.skipped, "
            "warned=vector_relay.warned + excluded.warned",
            (
                str(target),
                offset + consumed,
                utcnow(),
                moment.isoformat(),
                counters["sent"],
                counters["skipped_dedupe"] + counters["skipped_budget"],
                counters["warned"],
            ),
        )

    return {
        **base,
        "ok": True,
        "skipped": False,
        "processed": len(lines),
        "offset_start": offset,
        "offset_end": offset + consumed,
        **counters,
    }


def last_relay(db_path: str | Path = DEFAULT_DB) -> dict | None:
    init_db(db_path)
    with connect(db_path) as con:
        _ensure_tables(con)
        row = con.execute(
            "SELECT * FROM vector_relay ORDER BY last_run_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


__all__ = ["DEFAULT_PATH", "last_relay", "relay"]
