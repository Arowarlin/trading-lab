from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    bot TEXT,
    params TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id INTEGER,
    ticker TEXT NOT NULL,
    bot TEXT NOT NULL,
    side TEXT NOT NULL,
    strength REAL,
    price REAL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'market',
    limit_price REAL,
    status TEXT NOT NULL,
    broker_id TEXT,
    bot TEXT,
    reason TEXT,
    run_id INTEGER
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    equity REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model TEXT,
    purpose TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    ok INTEGER NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT,
    message TEXT,
    data TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(ts);
CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity(ts);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(path: str | Path) -> None:
    with connect(path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        _migrate_equity(con)


def _migrate_equity(con: sqlite3.Connection) -> None:
    """`equity` pasó de ts como PK a id autoincremental (varios snapshots por segundo)."""
    columns = [row["name"] for row in con.execute("PRAGMA table_info(equity)").fetchall()]
    if columns and "id" not in columns:
        con.executescript(
            """
            ALTER TABLE equity RENAME TO equity_old;
            CREATE TABLE equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                equity REAL NOT NULL
            );
            INSERT INTO equity(ts, cash, positions_value, equity)
                SELECT ts, cash, positions_value, equity FROM equity_old ORDER BY ts;
            DROP TABLE equity_old;
            CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity(ts);
            """
        )


def log_event(path: str | Path, level: str, source: str, message: str, data: str | None = None) -> None:
    with connect(path) as con:
        con.execute(
            "INSERT INTO events(ts, level, source, message, data) VALUES(?,?,?,?,?)",
            (utcnow(), level, source, message, data),
        )
