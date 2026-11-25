"""T3 · Registro append-only de hipótesis, experimentos y muestras."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import ROOT

DB = ROOT / "data" / "tl3" / "tl3_research.db"
THRESHOLDS = Path(__file__).with_name("thresholds.yaml")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def structural_hash(
    mechanism: str,
    market: str,
    timeframe: str,
    rules: dict[str, Any],
) -> str:
    payload = {
        "mechanism": mechanism,
        "market": market,
        "timeframe": timeframe,
        "rules": rules,
    }
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def load_thresholds(path: str | Path = THRESHOLDS) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def thresholds_hash(path: str | Path = THRESHOLDS) -> str:
    return hashlib.sha256(_json(load_thresholds(path)).encode("utf-8")).hexdigest()


def connect(path: str | Path = DB) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    return con


def init_db(path: str | Path = DB) -> None:
    with connect(path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS hypotheses (
                hypothesis_id TEXT PRIMARY KEY,
                parent_id TEXT,
                economic_rationale TEXT NOT NULL,
                behavior TEXT NOT NULL,
                refs TEXT NOT NULL,
                market TEXT NOT NULL,
                instrument_class TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                entry TEXT NOT NULL,
                exit_rule TEXT NOT NULL,
                primary_params TEXT NOT NULL,
                plateau_grid TEXT NOT NULL,
                benchmark TEXT NOT NULL,
                primary_metric TEXT NOT NULL,
                delta REAL,
                sigma REAL,
                mde REAL,
                rejection_rule TEXT NOT NULL,
                dev_window TEXT NOT NULL,
                holdout_window TEXT NOT NULL,
                holdout_kind TEXT NOT NULL,
                structural_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                rejection_reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                hypothesis_id TEXT NOT NULL,
                git_commit TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                data_manifest_hash TEXT NOT NULL,
                thresholds_hash TEXT NOT NULL,
                cost_model_version INTEGER NOT NULL,
                seed INTEGER NOT NULL,
                n_variants INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                metrics TEXT NOT NULL,
                report_path TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sample_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        con.commit()


def add_hypothesis(
    hypothesis_id: str,
    *,
    economic_rationale: str,
    behavior: str,
    refs: str,
    market: str,
    instrument_class: str,
    timeframe: str,
    entry: str,
    exit_rule: str,
    benchmark: str,
    primary_metric: str,
    rejection_rule: str,
    dev_window: dict[str, str],
    holdout_window: dict[str, str],
    holdout_kind: str,
    structural: str,
    status: str,
    rejection_reason: str | None = None,
    parent_id: str | None = None,
    primary_params: dict[str, Any] | None = None,
    plateau_grid: dict[str, Any] | None = None,
    delta: float | None = None,
    sigma: float | None = None,
    mde: float | None = None,
    db_path: str | Path = DB,
) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                hypothesis_id,
                parent_id,
                economic_rationale,
                behavior,
                refs,
                market,
                instrument_class,
                timeframe,
                entry,
                exit_rule,
                _json(primary_params or {}),
                _json(plateau_grid or {}),
                benchmark,
                primary_metric,
                delta,
                sigma,
                mde,
                rejection_rule,
                _json(dev_window),
                _json(holdout_window),
                holdout_kind,
                structural,
                status,
                rejection_reason,
                _now(),
            ),
        )
        con.commit()


def add_status(
    hypothesis_id: str,
    parent_id: str,
    status: str,
    reason: str | None = None,
    *,
    note: str | None = None,
    db_path: str | Path = DB,
) -> None:
    """Inserta una fila de estado hija con created_at actual."""

    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM hypotheses WHERE hypothesis_id=?", (parent_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Sin datos: hipótesis padre {parent_id}")
        cols = [
            column
            for column in row.keys()
            if column
            not in ("hypothesis_id", "parent_id", "status", "rejection_reason", "created_at")
        ]
        values = [row[column] for column in cols]
        if note:
            values[cols.index("behavior")] = f"{values[cols.index('behavior')]} | {note}"
        con.execute(
            f"INSERT INTO hypotheses (hypothesis_id,parent_id,{','.join(cols)},status,rejection_reason,created_at)"
            f" VALUES (?,?,{','.join('?' for _ in cols)},?,?,?)",
            [
                hypothesis_id,
                parent_id,
                *values,
                status,
                reason,
                _now(),
            ],
        )
        con.commit()


def add_experiment(
    experiment_id: str,
    hypothesis_id: str,
    *,
    git_commit: str,
    config_hash: str,
    data_manifest_hash: str,
    thresholds: str,
    cost_model_version: int,
    seed: int,
    n_variants: int,
    metrics: dict[str, Any],
    report_path: str,
    status: str,
    db_path: str | Path = DB,
) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                experiment_id,
                hypothesis_id,
                git_commit,
                config_hash,
                data_manifest_hash,
                thresholds,
                cost_model_version,
                seed,
                n_variants,
                _now(),
                _now(),
                _json(metrics),
                report_path,
                status,
            ),
        )
        con.commit()


def add_sample(
    instrument: str,
    timeframe: str,
    start: str,
    end: str,
    hypothesis_id: str,
    kind: str,
    *,
    db_path: str | Path = DB,
) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO sample_usage (instrument,timeframe,window_start,window_end,hypothesis_id,kind,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (instrument, timeframe, start, end, hypothesis_id, kind, _now()),
        )
        con.commit()


def seed_hypotheses(db_path: str | Path = DB) -> int:
    init_db(db_path)
    with connect(db_path) as con:
        existing = con.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]
    if existing:
        return int(existing)
    common = dict(
        economic_rationale="Tomado de la auditoría TL3; no se recalcula.",
        behavior="Definido en la cola TL3.",
        refs="TL3_REPORTS",
        market="cfd",
        instrument_class="cfd",
        timeframe="D1",
        entry="Primaria prerregistrada",
        exit_rule="Primaria prerregistrada",
        benchmark="Placebo o lado aleatorio",
        primary_metric="expectancy_r",
        rejection_rule="n>=300, exp>=0.10, LCB95>0",
        dev_window={"start": "2018-01-01", "end": "2024-06-30"},
        holdout_window={"start": "2025-07-01", "end": "2026-11-25"},
        holdout_kind="out_of_period",
    )
    ideas = [
        ("H-2026-001", "fx_fix", "rejected", "gross_lt_cost"),
        ("H-2026-002", "asia_usdjpy", "rejected", "no_gross_edge"),
        ("H-2026-003", "turn_of_month", "inconclusive", "no_power_cost_v1"),
        ("H-2026-004", "rebote", "inconclusive", "no_power_cost_v1"),
        ("H-2026-005", "donchian", "inconclusive", "no_power_cost_v1"),
        ("H-2026-006", "momentum_intraday", "inconclusive", "no_power_cost_v1"),
        ("H-2026-007", "ny_open_ga", "inconclusive", "no_power_cost_v1"),
        ("H-2026-008", "ea_oop", "draft", None),
        ("H-2026-009", "h2_fomc", "draft", None),
        ("H-2026-010", "h1_overnight", "draft", None),
        ("H-2026-011", "h3_or_expansion", "draft", None),
    ]
    for index, (hypothesis_id, mechanism, status, reason) in enumerate(ideas):
        payload = dict(common)
        if mechanism == "fx_fix":
            payload.update(timeframe="H1", delta=0.05, sigma=1.0)
        if mechanism.startswith("ea_") or mechanism.startswith("h"):
            payload.update(timeframe="M5", instrument_class="cfd")
        add_hypothesis(
            hypothesis_id,
            **payload,
            structural=structural_hash(mechanism, "cfd", payload["timeframe"], {}),
            status=status,
            rejection_reason=reason,
            db_path=db_path,
        )
    return len(ideas)


__all__ = [
    "DB",
    "THRESHOLDS",
    "add_experiment",
    "add_hypothesis",
    "add_sample",
    "add_status",
    "connect",
    "init_db",
    "load_thresholds",
    "seed_hypotheses",
    "structural_hash",
    "thresholds_hash",
]
