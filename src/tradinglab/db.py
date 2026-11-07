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

CREATE TABLE IF NOT EXISTS killswitch (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    triggered_at TEXT,
    reset_at TEXT,
    equity REAL,
    peak REAL,
    day_start REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    severity TEXT,
    channel TEXT,
    ok INTEGER NOT NULL,
    error TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS reconciliation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    broker_equity REAL,
    db_equity REAL,
    diff_equity REAL,
    broker_positions INTEGER,
    db_positions INTEGER,
    diff_positions INTEGER,
    status TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS f13_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bot TEXT NOT NULL,
    symbol TEXT NOT NULL,
    start_date TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    criteria TEXT NOT NULL,
    frozen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f13_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_return REAL NOT NULL,
    drawdown REAL NOT NULL,
    spy_close REAL,
    spy_return REAL,
    open_positions INTEGER NOT NULL,
    trades INTEGER NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS bot_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot TEXT NOT NULL,
    strategy TEXT NOT NULL,
    universe TEXT NOT NULL,
    params TEXT NOT NULL,
    exposure REAL NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_return REAL,
    sharpe REAL,
    max_drawdown REAL,
    num_trades INTEGER,
    win_rate REAL,
    expectancy REAL,
    status TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS decision_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    rating TEXT NOT NULL,
    confidence REAL,
    model TEXT,
    prompt_version TEXT,
    prompt_hash TEXT,
    ref_price REAL,
    return_1d REAL,
    return_5d REAL,
    return_20d REAL,
    updated_at TEXT,
    UNIQUE(ticker, decision_date, mode)
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    published_at TEXT,
    hash TEXT NOT NULL UNIQUE,
    trusted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS news_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL,
    ticker TEXT,
    sentiment REAL,
    relevance REAL,
    model TEXT,
    version TEXT,
    scored_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    ts_utc TEXT NOT NULL,
    importance TEXT,
    forecast TEXT,
    actual TEXT,
    source TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    status TEXT NOT NULL,
    events_count INTEGER NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS sec_fetches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    cik TEXT,
    status TEXT NOT NULL,
    http_status INTEGER,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    error TEXT
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

CREATE TABLE IF NOT EXISTS account_cash_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT,
    origin TEXT NOT NULL DEFAULT 'manual'
);

CREATE INDEX IF NOT EXISTS idx_account_cash_flows_account
    ON account_cash_flows(account_id, ts);
CREATE INDEX IF NOT EXISTS idx_console_actions_ts ON console_actions(ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
CREATE INDEX IF NOT EXISTS idx_reconciliation_ts ON reconciliation(ts);
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
        _migrate_bot_evaluations(con)


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


def _migrate_bot_evaluations(con: sqlite3.Connection) -> None:
    columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(bot_evaluations)").fetchall()
    ]
    if columns and "expectancy" not in columns:
        con.execute("ALTER TABLE bot_evaluations ADD COLUMN expectancy REAL")


def log_event(path: str | Path, level: str, source: str, message: str, data: str | None = None) -> None:
    with connect(path) as con:
        con.execute(
            "INSERT INTO events(ts, level, source, message, data) VALUES(?,?,?,?,?)",
            (utcnow(), level, source, message, data),
        )
