"""Estado runtime y auditoría del modo operador (SQLite, sin tocar YAML)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .audit import append_hashed
from .db import connect, init_db, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_runtime_state (
    bot TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS bot_runtime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    before_enabled INTEGER,
    after_enabled INTEGER NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS console_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    ok INTEGER NOT NULL,
    actor TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_console_actions_ts ON console_actions(ts);
CREATE TABLE IF NOT EXISTS operator_pin_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    failures INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);
"""


def init_runtime(db_path: str | Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.executescript(SCHEMA)


def _read_row(db_path: str | Path, bot: str) -> dict | None:
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
    except sqlite3.Error:
        return None
    try:
        row = con.execute(
            "SELECT * FROM bot_runtime_state WHERE bot = ?", (bot,)
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def effective_enabled(
    db_path: str | Path, bot: str, yaml_enabled: bool
) -> bool:
    """enabled efectivo = YAML AND estado en SQLite (sin fila = YAML)."""
    if not yaml_enabled:
        return False
    row = _read_row(db_path, bot)
    if row is None:
        return True
    return bool(row["enabled"])


def get_bot_state(db_path: str | Path, bot: str) -> dict | None:
    return _read_row(db_path, bot)


def set_bot_enabled(
    db_path: str | Path,
    *,
    bot: str,
    enabled: bool,
    yaml_enabled: bool,
    actor: str,
    reason: str = "",
) -> dict:
    """Guarda el estado runtime y su historial. No edita config/*.yaml."""
    init_runtime(db_path)
    before = effective_enabled(db_path, bot, yaml_enabled)
    after = bool(yaml_enabled and enabled)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO bot_runtime_state(bot, enabled, updated_at, updated_by, reason) "
            "VALUES(?,?,?,?,?) ON CONFLICT(bot) DO UPDATE SET "
            "enabled=excluded.enabled, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by, reason=excluded.reason",
            (bot, int(after), utcnow(), actor, reason[:500]),
        )
        con.execute(
            "INSERT INTO bot_runtime_history"
            "(ts, bot, before_enabled, after_enabled, actor, reason, source) "
            "VALUES(?,?,?,?,?,?,?)",
            (utcnow(), bot, int(before), int(after), actor, reason[:500], "console"),
        )
    return {
        "bot": bot,
        "yaml_enabled": bool(yaml_enabled),
        "before_enabled": before,
        "enabled": after,
        "reason": reason,
    }


def record_console_action(
    db_path: str | Path,
    *,
    action: str,
    params: dict[str, Any],
    result: str,
    ok: bool,
    actor: str = "console",
    detail: str = "",
) -> None:
    """Audita una acción sin secretos ni tokens."""
    init_runtime(db_path)
    safe = {
        key: value
        for key, value in params.items()
        if key.lower() not in {"pin", "token", "password", "secret"}
    }
    with connect(db_path) as con:
        append_hashed(
            con,
            "console_actions",
            {
                "ts": utcnow(),
                "action": action,
                "params": json.dumps(safe, ensure_ascii=False, default=str)[:4000],
                "result": result[:2000],
                "ok": int(ok),
                "actor": actor,
                "detail": detail[:1000],
            },
        )


def console_actions(db_path: str | Path, limit: int = 50) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
        con.row_factory = sqlite3.Row
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT * FROM console_actions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["params"] = json.loads(item["params"])
            except (ValueError, TypeError):
                pass
            item["ok"] = bool(item["ok"])
            out.append(item)
        return out
    except sqlite3.Error:
        return []
    finally:
        con.close()


__all__ = [
    "SCHEMA",
    "console_actions",
    "effective_enabled",
    "get_bot_state",
    "init_runtime",
    "record_console_action",
    "set_bot_enabled",
]
