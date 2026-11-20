"""Strategy Databank del Discovery Lab en ``data/discovery.db``.

Reglas:

* Las tablas ``disc_*`` viven en ``data/discovery.db``, **nunca** en
  ``data/lab.db`` (la usan la consola, el EA y ``ai_trader``). Este módulo
  rechaza explícitamente esa ruta.
* Se importa ``tradinglab.db.connect`` (solo fija ``busy_timeout`` y
  ``row_factory``); el ``journal_mode=WAL`` se activa únicamente aquí.
* Nada se borra: los estados pasan a ``archived``. Las evaluaciones y
  validaciones son inmutables y se deduplican por su clave.
* ``returns_blob`` es ``zlib`` sobre ``float32`` (serie diaria de R).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from ..config import ROOT
from ..db import connect
from . import __version__, dsl

DEFAULT_DISCOVERY_DB = ROOT / "data" / "discovery.db"
LAB_DB = ROOT / "data" / "lab.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS disc_campaigns (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    instrument TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    template TEXT,
    engine_profile TEXT,
    config_json TEXT NOT NULL,
    config_hash TEXT,
    is_start TEXT,
    is_end TEXT,
    oos1_start TEXT,
    oos1_end TEXT,
    oos2_start TEXT,
    oos2_end TEXT,
    dataset_hash TEXT,
    n_total INTEGER,
    n_evaluated INTEGER NOT NULL DEFAULT 0,
    n_effective INTEGER,
    status TEXT NOT NULL DEFAULT 'registered',
    engine_version TEXT,
    approved_at TEXT,
    approved_by TEXT,
    quality_json TEXT,
    reject_reason TEXT
);

CREATE TABLE IF NOT EXISTS disc_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    strategy_hash TEXT NOT NULL,
    dsl_json TEXT NOT NULL,
    family TEXT,
    instrument TEXT,
    timeframe TEXT,
    session TEXT,
    generation INTEGER NOT NULL DEFAULT 0,
    origin TEXT NOT NULL DEFAULT 'random',
    level INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'generated',
    reject_reason TEXT,
    selection_reason TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(campaign_id, strategy_hash)
);
CREATE INDEX IF NOT EXISTS idx_disc_strategies_campaign
    ON disc_strategies(campaign_id, status);

CREATE TABLE IF NOT EXISTS disc_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    parent_a INTEGER,
    parent_b INTEGER,
    operator TEXT,
    param_diff_json TEXT,
    generation INTEGER NOT NULL DEFAULT 0,
    fitness_json TEXT,
    rank INTEGER,
    crowding REAL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_disc_lineage_strategy
    ON disc_lineage(strategy_id);

CREATE TABLE IF NOT EXISTS disc_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    segment TEXT NOT NULL,
    cost_profile TEXT,
    metrics_json TEXT,
    trades_count INTEGER,
    returns_blob BLOB,
    computed_at TEXT NOT NULL,
    UNIQUE(strategy_id, segment, cost_profile)
);
CREATE INDEX IF NOT EXISTS idx_disc_evaluations_strategy
    ON disc_evaluations(strategy_id);

CREATE TABLE IF NOT EXISTS disc_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    test TEXT NOT NULL,
    result_json TEXT,
    passed INTEGER,
    computed_at TEXT NOT NULL,
    UNIQUE(strategy_id, test)
);
CREATE INDEX IF NOT EXISTS idx_disc_validations_strategy
    ON disc_validations(strategy_id);

CREATE TABLE IF NOT EXISTS disc_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'backtest_is',
    payload_json TEXT NOT NULL,
    strategy_hash TEXT,
    state TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_disc_jobs_campaign
    ON disc_jobs(campaign_id, state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_disc_jobs_dedupe
    ON disc_jobs(campaign_id, strategy_hash)
    WHERE strategy_hash IS NOT NULL AND state IN ('queued', 'running', 'done');

CREATE TABLE IF NOT EXISTS disc_holdout_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL UNIQUE,
    campaign_id TEXT NOT NULL,
    read_at TEXT NOT NULL,
    dataset_hash TEXT,
    rows INTEGER
);
CREATE INDEX IF NOT EXISTS idx_disc_holdout_campaign
    ON disc_holdout_reads(campaign_id);
"""


class DatabankError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _check_path(path: str | Path) -> Path:
    target = Path(path)
    try:
        same = target.resolve() == LAB_DB.resolve()
    except OSError:
        same = False
    if same or target.name.lower() == "lab.db":
        raise DatabankError("el Discovery Lab nunca escribe en data/lab.db")
    return target


@contextmanager
def _connection(
    path: str | Path, con: sqlite3.Connection | None
) -> Iterator[sqlite3.Connection]:
    if con is not None:
        yield con
        return
    target = _check_path(path)
    with connect(target) as opened:
        yield opened


def init_databank(
    path: str | Path | None = None, *, con: sqlite3.Connection | None = None
) -> Path:
    """Crea las tablas si faltan. WAL solo en discovery.db."""

    target = _check_path(path or DEFAULT_DISCOVERY_DB)
    with _connection(target, con) as opened:
        opened.execute("PRAGMA journal_mode=WAL")
        opened.executescript(SCHEMA)
        _migrate_campaigns(opened)
    return target


def _migrate_campaigns(con: sqlite3.Connection) -> None:
    """Añade columnas de aprobación/calidad y congela ``n_total``."""

    columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(disc_campaigns)").fetchall()
    ]
    for column, kind in (
        ("approved_at", "TEXT"),
        ("approved_by", "TEXT"),
        ("quality_json", "TEXT"),
        ("reject_reason", "TEXT"),
    ):
        if column not in columns:
            con.execute(f"ALTER TABLE disc_campaigns ADD COLUMN {column} {kind}")
    strategy_columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(disc_strategies)").fetchall()
    ]
    if "selection_reason" not in strategy_columns:
        con.execute("ALTER TABLE disc_strategies ADD COLUMN selection_reason TEXT")
    lineage_columns = [
        row["name"]
        for row in con.execute("PRAGMA table_info(disc_lineage)").fetchall()
    ]
    for column, kind in (
        ("fitness_json", "TEXT"),
        ("rank", "INTEGER"),
        ("crowding", "REAL"),
        ("reason", "TEXT"),
    ):
        if column not in lineage_columns:
            con.execute(f"ALTER TABLE disc_lineage ADD COLUMN {column} {kind}")
    con.execute(
        "CREATE TRIGGER IF NOT EXISTS disc_campaigns_n_total_immutable "
        "BEFORE UPDATE OF n_total ON disc_campaigns "
        "WHEN OLD.n_total IS NOT NULL AND NEW.n_total IS NOT OLD.n_total "
        "BEGIN SELECT RAISE(ABORT, 'disc_campaigns.n_total es inmutable'); END"
    )


def _resolve_target(
    db_path: str | Path | None, con: sqlite3.Connection | None
) -> Path:
    """Inicializa solo si la conexión la abrimos nosotros (no en lotes)."""

    target = _check_path(db_path or DEFAULT_DISCOVERY_DB)
    if con is None:
        init_databank(target)
    return target


def _metrics_json(metrics: dict[str, Any] | None) -> str | None:
    if metrics is None:
        return None
    return json.dumps(metrics, sort_keys=True, ensure_ascii=False, allow_nan=True)


def encode_returns(values: Any) -> bytes:
    """Comprime una serie de R como ``float32`` (zlib)."""

    array = np.asarray(list(values), dtype=np.float32)
    return zlib.compress(array.tobytes(), level=6)


def decode_returns(blob: bytes | None) -> np.ndarray:
    if not blob:
        return np.array([], dtype=np.float32)
    return np.frombuffer(zlib.decompress(blob), dtype=np.float32)


def add_campaign(
    campaign_id: str,
    config: dict[str, Any],
    *,
    instrument: str | None = None,
    timeframe: str | None = None,
    template: str | None = None,
    engine_profile: str | None = None,
    status: str | None = None,
    quality: dict[str, Any] | None = None,
    n_total: int | None = None,
    dataset_hash: str | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> str:
    """Inserta la campaña una vez (borrador o registrada)."""

    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise DatabankError("la campaña necesita id")
    payload = json.dumps(config or {}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    instrument = str(instrument or (config or {}).get("instrument") or "").upper()
    timeframe = str(timeframe or (config or {}).get("timeframe") or "").upper()
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        existing = opened.execute(
            "SELECT id FROM disc_campaigns WHERE id = ?", (identifier,)
        ).fetchone()
        if existing is not None:
            return identifier
        if not instrument or not timeframe:
            raise DatabankError("la campaña necesita instrument y timeframe")
        opened.execute(
            "INSERT OR IGNORE INTO disc_campaigns"
            "(id, created_at, instrument, timeframe, template, engine_profile,"
            " config_json, config_hash, is_start, is_end, oos1_start, oos1_end,"
            " oos2_start, oos2_end, dataset_hash, n_total, n_evaluated,"
            " n_effective, status, engine_version, approved_at, approved_by,"
            " quality_json, reject_reason) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?,NULL)",
            (
                identifier,
                _now(),
                instrument,
                timeframe,
                template,
                engine_profile,
                payload,
                digest,
                (config or {}).get("is_start"),
                (config or {}).get("is_end"),
                (config or {}).get("oos1_start"),
                (config or {}).get("oos1_end"),
                (config or {}).get("oos2_start"),
                (config or {}).get("oos2_end"),
                dataset_hash if dataset_hash is not None else (config or {}).get("dataset_hash"),
                n_total if n_total is not None else (config or {}).get("n_total"),
                0,
                (config or {}).get("n_effective"),
                str(status or (config or {}).get("status") or "registered"),
                __version__,
                None if quality is None else json.dumps(
                    quality, sort_keys=True, ensure_ascii=False, allow_nan=True
                ),
            ),
        )
    return identifier


def get_campaign(
    campaign_id: str,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        row = opened.execute(
            "SELECT * FROM disc_campaigns WHERE id = ?", (str(campaign_id),)
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["config"] = json.loads(data.pop("config_json") or "{}")
    data["quality"] = json.loads(data.pop("quality_json") or "{}")
    return data


def approve_campaign(
    campaign_id: str,
    *,
    approved_by: str = "operator",
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Pasa una campaña de ``draft`` a ``registered`` y la cuenta."""

    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise DatabankError("la aprobación necesita campaign_id")
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        row = opened.execute(
            "SELECT status, approved_at FROM disc_campaigns WHERE id = ?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise DatabankError(f"campaña no registrada: {identifier}")
        if row["status"] == "draft":
            opened.execute(
                "UPDATE disc_campaigns SET status = 'registered',"
                " approved_at = ?, approved_by = ? WHERE id = ? AND status = 'draft'",
                (_now(), str(approved_by), identifier),
            )
    campaign = get_campaign(identifier, db_path=target)
    if campaign is None:  # pragma: no cover
        raise DatabankError(f"campaña no registrada: {identifier}")
    return campaign


def set_campaign_rejected(
    campaign_id: str,
    reason: str,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> None:
    """Marca rechazada; ``approved_at`` no se toca (si estaba aprobada, cuenta)."""

    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "UPDATE disc_campaigns SET status = 'rejected', reject_reason = ?"
            " WHERE id = ?",
            (str(reason)[:2000], str(campaign_id)),
        )


def add_holdout_read(
    strategy_id: int,
    campaign_id: str,
    *,
    dataset_hash: str | None = None,
    rows: int | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    """Registra una lectura de OOS-2; la UNIQUE impide la segunda."""

    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        cursor = opened.execute(
            "INSERT INTO disc_holdout_reads"
            "(strategy_id, campaign_id, read_at, dataset_hash, rows) "
            "VALUES(?,?,?,?,?)",
            (
                int(strategy_id),
                str(campaign_id),
                _now(),
                dataset_hash,
                None if rows is None else int(rows),
            ),
        )
        return int(cursor.lastrowid)


def get_holdout_read(
    strategy_id: int,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        row = opened.execute(
            "SELECT * FROM disc_holdout_reads WHERE strategy_id = ?",
            (int(strategy_id),),
        ).fetchone()
    return None if row is None else dict(row)


def count_holdout_reads(
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        row = opened.execute(
            "SELECT COUNT(*) AS n FROM disc_holdout_reads"
        ).fetchone()
    return int(row["n"])


def set_campaign_status(
    campaign_id: str,
    status: str,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> None:
    if not str(status or "").strip():
        raise DatabankError("estado vacío")
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "UPDATE disc_campaigns SET status = ? WHERE id = ?",
            (str(status), str(campaign_id)),
        )


def add_strategy(
    campaign_id: str,
    strategy: dict[str, Any] | dsl.Strategy,
    *,
    family: str | None = None,
    generation: int = 0,
    origin: str = "random",
    level: int = 1,
    status: str = "generated",
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    """Dedupe por ``campaign_id + strategy_hash``. Devuelve el id existente."""

    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise DatabankError("la estrategia necesita campaña")
    canonical = dsl.canonical_json(strategy)
    digest = dsl.strategy_hash(strategy)
    model = dsl.Strategy.model_validate(strategy)
    session = json.dumps(
        model.session.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        ensure_ascii=False,
    )
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "INSERT OR IGNORE INTO disc_strategies"
            "(campaign_id, strategy_hash, dsl_json, family, instrument, timeframe,"
            " session, generation, origin, level, status, reject_reason, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
            (
                identifier,
                digest,
                canonical,
                family,
                model.instrument,
                model.timeframe,
                session,
                int(generation),
                str(origin),
                int(level),
                str(status),
                _now(),
            ),
        )
        row = opened.execute(
            "SELECT id FROM disc_strategies WHERE campaign_id = ? AND strategy_hash = ?",
            (identifier, digest),
        ).fetchone()
    if row is None:  # pragma: no cover - la inserción o el select siempre dejan fila
        raise DatabankError("no se pudo guardar la estrategia")
    return int(row["id"])


def add_evaluation(
    strategy_id: int,
    *,
    segment: str,
    cost_profile: str | None,
    metrics: dict[str, Any] | None,
    trades_count: int | None,
    returns: Any = (),
    computed_at: str | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    """Dedupe por ``strategy_id + segment + cost_profile``; no sobreescribe."""

    if not str(segment or "").strip():
        raise DatabankError("la evaluación necesita segment")
    blob = encode_returns(returns)
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "INSERT OR IGNORE INTO disc_evaluations"
            "(strategy_id, segment, cost_profile, metrics_json, trades_count,"
            " returns_blob, computed_at) VALUES(?,?,?,?,?,?,?)",
            (
                int(strategy_id),
                str(segment),
                cost_profile,
                _metrics_json(metrics),
                None if trades_count is None else int(trades_count),
                blob,
                computed_at or _now(),
            ),
        )
        row = opened.execute(
            "SELECT id FROM disc_evaluations"
            " WHERE strategy_id = ? AND segment = ? AND cost_profile IS ?",
            (int(strategy_id), str(segment), cost_profile),
        ).fetchone()
    if row is None:  # pragma: no cover
        raise DatabankError("no se pudo guardar la evaluación")
    return int(row["id"])


def add_validation(
    strategy_id: int,
    test: str,
    result: dict[str, Any] | None,
    passed: bool | None,
    *,
    computed_at: str | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    if not str(test or "").strip():
        raise DatabankError("la validación necesita test")
    payload = (
        None
        if result is None
        else json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=True)
    )
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "INSERT OR IGNORE INTO disc_validations"
            "(strategy_id, test, result_json, passed, computed_at) "
            "VALUES(?,?,?,?,?)",
            (
                int(strategy_id),
                str(test),
                payload,
                None if passed is None else int(bool(passed)),
                computed_at or _now(),
            ),
        )
        row = opened.execute(
            "SELECT id FROM disc_validations WHERE strategy_id = ? AND test = ?",
            (int(strategy_id), str(test)),
        ).fetchone()
    if row is None:  # pragma: no cover
        raise DatabankError("no se pudo guardar la validación")
    return int(row["id"])


def set_status(
    strategy_id: int,
    status: str,
    *,
    reject_reason: str | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> None:
    if not str(status or "").strip():
        raise DatabankError("estado vacío")
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "UPDATE disc_strategies SET status = ?, reject_reason = ? WHERE id = ?",
            (str(status), reject_reason, int(strategy_id)),
        )


def set_strategy_selection(
    strategy_id: int,
    status: str,
    reason: str,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> None:
    """Estado final y motivo de selección/descarte de un candidato."""

    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "UPDATE disc_strategies SET status = ?, selection_reason = ? WHERE id = ?",
            (str(status), str(reason)[:2000], int(strategy_id)),
        )


def set_campaign_counts(
    campaign_id: str,
    *,
    n_evaluated: int | None = None,
    n_effective: int | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> None:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        opened.execute(
            "UPDATE disc_campaigns SET"
            " n_evaluated = COALESCE(?, n_evaluated),"
            " n_effective = COALESCE(?, n_effective) WHERE id = ?",
            (
                None if n_evaluated is None else int(n_evaluated),
                None if n_effective is None else int(n_effective),
                str(campaign_id),
            ),
        )


def add_lineage(
    strategy_id: int,
    *,
    parent_a: int | None,
    parent_b: int | None,
    operator: str | None,
    param_diff: dict[str, Any] | None = None,
    generation: int = 0,
    fitness: dict[str, Any] | None = None,
    rank: int | None = None,
    crowding: float | None = None,
    reason: str | None = None,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> int:
    payload = (
        None
        if param_diff is None
        else json.dumps(param_diff, sort_keys=True, ensure_ascii=False)
    )
    fitness_payload = (
        None
        if fitness is None
        else json.dumps(fitness, sort_keys=True, ensure_ascii=False, allow_nan=True)
    )
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        cursor = opened.execute(
            "INSERT INTO disc_lineage"
            "(strategy_id, parent_a, parent_b, operator, param_diff_json,"
            " generation, fitness_json, rank, crowding, reason) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                int(strategy_id),
                None if parent_a is None else int(parent_a),
                None if parent_b is None else int(parent_b),
                operator,
                payload,
                int(generation),
                fitness_payload,
                None if rank is None else int(rank),
                crowding,
                reason,
            ),
        )
        return int(cursor.lastrowid)


def lineage(
    strategy_id: int,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        rows = opened.execute(
            "SELECT * FROM disc_lineage WHERE strategy_id = ? ORDER BY id",
            (int(strategy_id),),
        ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        data["param_diff"] = json.loads(data.pop("param_diff_json") or "{}")
        data["fitness"] = json.loads(data.pop("fitness_json") or "{}")
        result.append(data)
    return result


def _strategy_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["dsl"] = json.loads(data.pop("dsl_json"))
    data["session"] = json.loads(data.get("session") or "{}")
    return data


def get_strategy(
    strategy_id: int,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        row = opened.execute(
            "SELECT * FROM disc_strategies WHERE id = ?", (int(strategy_id),)
        ).fetchone()
    return None if row is None else _strategy_row(row)


def list_strategies(
    *,
    campaign_id: str | None = None,
    status: str | None = None,
    level: int | None = None,
    origin: str | None = None,
    limit: int | None = 100,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if campaign_id is not None:
        clauses.append("campaign_id = ?")
        params.append(str(campaign_id))
    if status is not None:
        clauses.append("status = ?")
        params.append(str(status))
    if level is not None:
        clauses.append("level = ?")
        params.append(int(level))
    if origin is not None:
        clauses.append("origin = ?")
        params.append(str(origin))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM disc_strategies{where} ORDER BY id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        rows = opened.execute(sql, params).fetchall()
    return [_strategy_row(row) for row in rows]


def list_evaluations(
    strategy_id: int,
    *,
    db_path: str | Path | None = None,
    con: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    target = _resolve_target(db_path, con)
    with _connection(target, con) as opened:
        rows = opened.execute(
            "SELECT * FROM disc_evaluations WHERE strategy_id = ? ORDER BY id",
            (int(strategy_id),),
        ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        data["metrics"] = json.loads(data.pop("metrics_json") or "{}")
        data["returns"] = decode_returns(data.get("returns_blob"))
        result.append(data)
    return result


__all__ = [
    "DEFAULT_DISCOVERY_DB",
    "DatabankError",
    "add_campaign",
    "add_evaluation",
    "add_holdout_read",
    "add_lineage",
    "add_strategy",
    "add_validation",
    "approve_campaign",
    "count_holdout_reads",
    "decode_returns",
    "encode_returns",
    "get_campaign",
    "get_holdout_read",
    "get_strategy",
    "init_databank",
    "lineage",
    "list_evaluations",
    "list_strategies",
    "set_campaign_rejected",
    "set_campaign_status",
    "set_campaign_counts",
    "set_status",
    "set_strategy_selection",
]
