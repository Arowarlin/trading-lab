"""Cadena de hash para tablas append-only (`orders`, `console_actions`).

Cada fila nueva encadena su `row_hash` con el `row_hash` de la fila anterior
de la misma tabla:

    row_hash = sha256(prev_hash + json_canonico_de_la_fila_sin_los_dos_hashes)

El JSON canónico se construye con **todas** las columnas de la tabla (las que
no se escriben valen `None`), para que el hash no dependa de qué módulo
insertó la fila. Las filas antiguas, escritas antes de la cadena, se quedan
con `row_hash` a NULL y **no rompen** la verificación: son "antes de la
cadena".

Migraciones solo aditivas: se añaden columnas, nunca se borra ni reescribe una
fila existente.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from .config import DEFAULT_DB
from .db import connect, init_db

CHAINED_TABLES = ("console_actions", "orders")
HASH_COLUMNS = ("prev_hash", "row_hash")


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    """Columnas reales de la tabla, sin las dos de la cadena."""
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return [row["name"] for row in rows if row["name"] not in HASH_COLUMNS]


def canonical_row(con: sqlite3.Connection, table: str, row: Mapping[str, Any]) -> str:
    """JSON canónico de la fila: todas las columnas, ordenadas y sin hashes."""
    payload = {column: row.get(column) for column in table_columns(con, table)}
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )


def row_hash(
    con: sqlite3.Connection,
    table: str,
    row: Mapping[str, Any],
    prev_hash: str | None,
) -> str:
    """Hash encadenado de una fila."""
    digest = hashlib.sha256()
    digest.update((prev_hash or "").encode("utf-8"))
    digest.update(canonical_row(con, table, row).encode("utf-8"))
    return digest.hexdigest()


def last_hash(con: sqlite3.Connection, table: str) -> str | None:
    """`row_hash` de la última fila encadenada de la tabla."""
    row = con.execute(
        f"SELECT row_hash FROM {table} WHERE row_hash IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return str(row["row_hash"]) if row and row["row_hash"] else None


def ensure_hash_columns(con: sqlite3.Connection, table: str) -> None:
    """Añade `prev_hash` y `row_hash` si faltan. Aditivo e idempotente."""
    columns = [row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()]
    if not columns:
        raise ValueError(f"tabla inexistente: {table}")
    if "prev_hash" not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN prev_hash TEXT")
    if "row_hash" not in columns:
        con.execute(f"ALTER TABLE {table} ADD COLUMN row_hash TEXT")


def append_hashed(
    con: sqlite3.Connection, table: str, row: Mapping[str, Any]
) -> int:
    """Inserta la fila y sella su `prev_hash` y `row_hash`.

    El `id` se conoce tras el INSERT, así que el hash se calcula y se graba
    en una segunda sentencia dentro de la misma transacción.
    """
    if table not in CHAINED_TABLES:
        raise ValueError(f"tabla sin cadena de auditoría: {table}")
    ensure_hash_columns(con, table)
    columns = list(row.keys())
    if not columns:
        raise ValueError("fila vacía")
    prev = last_hash(con, table)
    placeholders = ",".join("?" for _ in columns)
    cursor = con.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        tuple(row.values()),
    )
    row_id = int(cursor.lastrowid)
    full = dict(row)
    full["id"] = row_id
    digest = row_hash(con, table, full, prev)
    con.execute(
        f"UPDATE {table} SET prev_hash = ?, row_hash = ? WHERE id = ?",
        (prev, digest, row_id),
    )
    return row_id


def verify_chain(
    table: str,
    db_path: str | Path | None = None,
    *,
    con: sqlite3.Connection | None = None,
) -> dict:
    """Verifica la cadena de una tabla.

    Devuelve ``ok``, ``first_break_id`` (None si no hay rotura) y ``n``
    (filas revisadas). Las filas con ``row_hash`` NULL se cuentan como
    "antes de la cadena" y no fallan.
    """
    if table not in CHAINED_TABLES:
        raise ValueError(f"tabla sin cadena de auditoría: {table}")

    def _run(active: sqlite3.Connection) -> dict:
        rows = active.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        prev: str | None = None
        first_break_id: int | None = None
        hashed = 0
        legacy = 0
        for row in rows:
            stored = row["row_hash"]
            if stored is None:
                legacy += 1
                continue
            hashed += 1
            data = dict(row)
            if data.get("prev_hash") != prev:
                first_break_id = int(row["id"])
                break
            expected = row_hash(active, table, data, prev)
            if expected != stored:
                first_break_id = int(row["id"])
                break
            prev = str(stored)
        return {
            "ok": first_break_id is None,
            "first_break_id": first_break_id,
            "n": len(rows),
            "hashed": hashed,
            "legacy": legacy,
            "table": table,
        }

    if con is not None:
        return _run(con)
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    init_db(path)
    with connect(path) as active:
        return _run(active)


def chain_state(db_path: str | Path | None = None) -> dict:
    """Estado de la cadena de todas las tablas auditadas."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB
    init_db(path)
    state: dict = {"ok": True, "tables": {}}
    with connect(path) as con:
        for table in CHAINED_TABLES:
            result = verify_chain(table, con=con)
            state["tables"][table] = result
            state["ok"] = state["ok"] and result["ok"]
    return state


__all__ = [
    "CHAINED_TABLES",
    "HASH_COLUMNS",
    "append_hashed",
    "canonical_row",
    "chain_state",
    "ensure_hash_columns",
    "last_hash",
    "row_hash",
    "table_columns",
    "verify_chain",
]
