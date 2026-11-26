"""TCA v2 · migración de la columna y versión de las filas nuevas."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from tradinglab.db import init_db
from tradinglab.tca import TCA_VERSION, record_fill

OLD_COLUMNS = (
    "fill_id, bot, account, symbol, side, signal_px, order_px, fill_px, "
    "slippage_bps, latency_ms, expected_cost_bps, realized_cost_bps, "
    "bid, ask, requested_price, order_type, origin, ts_utc"
)

OLD_SCHEMA = """
CREATE TABLE tca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fill_id INTEGER,
    bot TEXT,
    account TEXT,
    symbol TEXT NOT NULL,
    side TEXT,
    signal_px REAL,
    order_px REAL,
    fill_px REAL,
    slippage_bps REAL,
    latency_ms REAL,
    expected_cost_bps REAL,
    realized_cost_bps REAL,
    bid REAL,
    ask REAL,
    requested_price REAL,
    order_type TEXT,
    origin TEXT,
    ts_utc TEXT NOT NULL
);
"""


def _columns(db) -> set[str]:
    with sqlite3.connect(db) as con:
        return {row[1] for row in con.execute("PRAGMA table_info(tca)")}


def _hash(db, columns: str = OLD_COLUMNS) -> str:
    with sqlite3.connect(db) as con:
        rows = [tuple(row) for row in con.execute(f"SELECT {columns} FROM tca ORDER BY id")]
    return hashlib.sha256(json.dumps(rows, default=str).encode("utf-8")).hexdigest()


def _old_db(db) -> None:
    with sqlite3.connect(db) as con:
        con.executescript(OLD_SCHEMA)
        con.executemany(
            "INSERT INTO tca(symbol, side, signal_px, order_px, fill_px, slippage_bps, ts_utc)"
            " VALUES(?,?,?,?,?,?,?)",
            [
                ("SPY", "buy", 100.0, 100.0, 100.0, 0.0, "2026-11-20T10:00:00+00:00"),
                ("QQQ", "sell", 200.0, 200.0, 200.0, 0.0, "2026-11-20T10:01:00+00:00"),
            ],
        )


def test_migracion_anade_tca_version_sin_tocar_filas(tmp_path):
    db = tmp_path / "old.db"
    _old_db(db)
    before = _hash(db)
    assert "tca_version" not in _columns(db)

    init_db(db)

    assert "tca_version" in _columns(db)
    assert _hash(db) == before
    with sqlite3.connect(db) as con:
        values = [row[0] for row in con.execute("SELECT tca_version FROM tca ORDER BY id")]
    assert values == [None, None]


def test_migracion_es_idempotente(tmp_path):
    db = tmp_path / "old.db"
    _old_db(db)
    init_db(db)
    first = _columns(db)
    before = _hash(db)
    init_db(db)
    assert _columns(db) == first
    assert _hash(db) == before
    assert "tca_version" in first


def test_fila_nueva_lleva_version_2(tmp_path):
    db = tmp_path / "new.db"
    init_db(db)
    record_fill(
        db,
        bot="bot",
        symbol="SPY",
        side="buy",
        signal_px=100.0,
        order_px=100.0,
        fill_px=100.02,
        slippage_bps=2.0,
    )
    with sqlite3.connect(db) as con:
        version = con.execute("SELECT tca_version FROM tca").fetchone()[0]
    assert version == TCA_VERSION == 2
