"""Lease de ejecución entre hosts.

Una fila con caducidad de 2 minutos. El mismo host puede renovarla; otro host
no puede operar mientras el lease siga vigente. No sustituye al candado local
de las tareas: evita que dos máquinas abran el mismo carril a la vez.
"""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db

TTL_SECONDS = 120


class LeaseError(RuntimeError):
    pass


def hostname() -> str:
    return socket.gethostname().strip() or "host-desconocido"


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def acquire(
    db_path: str | Path,
    *,
    session: str = "",
    host: str | None = None,
    pid: int | None = None,
    now: datetime | None = None,
    ttl_seconds: int = TTL_SECONDS,
) -> dict:
    moment = _utc(now)
    current = host or hostname()
    ttl = max(1, int(ttl_seconds))
    expires = moment + timedelta(seconds=ttl)
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM execution_lease WHERE id=1").fetchone()
        if row is not None:
            try:
                previous_expiry = _utc(datetime.fromisoformat(row["expires_at"]))
            except (TypeError, ValueError):
                previous_expiry = moment - timedelta(seconds=1)
            if previous_expiry > moment and str(row["host"]) != current:
                return {
                    "ok": False,
                    "reason": (
                        f"lease de {row['host']} hasta "
                        f"{previous_expiry.isoformat()}"
                    ),
                    "lease": dict(row),
                }
        con.execute(
            "INSERT INTO execution_lease"
            "(id, host, pid, session, acquired_at, expires_at) "
            "VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "host=excluded.host, pid=excluded.pid, session=excluded.session, "
            "acquired_at=excluded.acquired_at, expires_at=excluded.expires_at",
            (
                current,
                int(pid if pid is not None else os.getpid()),
                str(session or ""),
                moment.isoformat(),
                expires.isoformat(),
            ),
        )
        con.commit()
        row = con.execute("SELECT * FROM execution_lease WHERE id=1").fetchone()
    return {"ok": True, "reason": "lease adquirido", "lease": dict(row)}


def release(
    db_path: str | Path,
    *,
    host: str | None = None,
    pid: int | None = None,
) -> dict:
    current = host or hostname()
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM execution_lease WHERE id=1").fetchone()
        if row is None:
            return {"ok": True, "reason": "sin lease"}
        if str(row["host"]) != current:
            return {"ok": False, "reason": f"lease de {row['host']}"}
        if pid is not None and int(row["pid"] or 0) not in (0, int(pid)):
            return {"ok": False, "reason": f"lease de otro PID {row['pid']}"}
        con.execute("DELETE FROM execution_lease WHERE id=1")
        con.commit()
    return {"ok": True, "reason": "lease liberado"}


def status(db_path: str | Path, *, now: datetime | None = None) -> dict:
    init_db(db_path)
    moment = _utc(now)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM execution_lease WHERE id=1").fetchone()
    if row is None:
        return {"active": False, "lease": None}
    data = dict(row)
    try:
        expiry = _utc(datetime.fromisoformat(data["expires_at"]))
        data["expired"] = expiry <= moment
    except (TypeError, ValueError):
        data["expired"] = True
    return {"active": not data["expired"], "lease": data}


__all__ = ["LeaseError", "TTL_SECONDS", "acquire", "hostname", "release", "status"]
