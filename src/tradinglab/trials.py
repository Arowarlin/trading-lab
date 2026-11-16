"""Cementerio de estrategias probadas y presupuesto de investigación.

`strategy_trials` guarda TODO lo que se ha probado, también lo fallido. Cada
fila suma una prueba al contador único del DSR. Si se intenta reoptimizar una
familia ya descartada sobre la misma ventana, el sistema avisa; y el presupuesto
semanal por activo vive en `config/research_budget.yaml`.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from .config import ROOT
from .db import connect, init_db, utcnow

BUDGET_PATH = ROOT / "config" / "research_budget.yaml"
OUTCOMES = {"passed", "failed", "discarded", "incubating"}
DISCARDED_OUTCOMES = {"failed", "discarded"}
SOURCES = {"humano", "qwen", "optuna", "lesson", "sweep", "campaign", "cost_reeval"}


class TrialsError(ValueError):
    pass


def fingerprint(
    family: str,
    symbol: str,
    window_start: str | None = None,
    window_end: str | None = None,
) -> str:
    raw = "|".join(
        [
            str(family).strip().upper(),
            str(symbol).strip().upper(),
            str(window_start or ""),
            str(window_end or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_trial(
    db_path: str | Path,
    *,
    family: str,
    hypothesis: str,
    symbol: str,
    params: dict | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    result: dict | None = None,
    outcome: str = "failed",
    reason: str = "",
    source: str = "humano",
    run_id: str | None = None,
    lesson_id: int | None = None,
    counted: bool = True,
    dsr_v2: float | None = None,
    metric_version: str | None = None,
    sr_period: float | None = None,
    periods_per_year: float | None = None,
) -> dict:
    """Guarda un intento. Las fallidas también se registran y cuentan."""
    if outcome not in OUTCOMES:
        raise TrialsError(f"outcome inválido: {outcome}")
    if source not in SOURCES:
        raise TrialsError(f"source inválido: {source}")
    if not str(family or "").strip():
        raise TrialsError("family no puede estar vacía")
    if not str(hypothesis or "").strip():
        raise TrialsError("hypothesis no puede estar vacía")
    if not str(symbol or "").strip():
        raise TrialsError("symbol no puede estar vacío")
    init_db(db_path)
    now = utcnow()
    run = run_id or uuid.uuid4().hex[:12]
    mark = fingerprint(family, symbol, window_start, window_end)
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT INTO strategy_trials"
            "(ts, family, hypothesis, symbol, params, window_start, window_end, "
            "result, outcome, reason, source, run_id, lesson_id, fingerprint, counted, "
            "dsr_v2, metric_version, sr_period, periods_per_year) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                now,
                str(family).strip().upper(),
                str(hypothesis).strip()[:2000],
                str(symbol).strip().upper(),
                json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
                window_start,
                window_end,
                json.dumps(result or {}, ensure_ascii=False, default=str),
                outcome,
                str(reason or "")[:2000],
                source,
                run,
                lesson_id,
                mark,
                1 if counted else 0,
                dsr_v2,
                metric_version,
                sr_period,
                periods_per_year,
            ),
        )
        row = con.execute(
            "SELECT * FROM strategy_trials WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_trials(
    db_path: str | Path,
    *,
    symbol: str | None = None,
    family: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
) -> list[dict]:
    init_db(db_path)
    clauses = []
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(str(symbol).upper())
    if family:
        clauses.append("family = ?")
        params.append(str(family).upper())
    if outcome:
        clauses.append("outcome = ?")
        params.append(outcome)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, int(limit)))
    with connect(db_path) as con:
        rows = con.execute(
            f"SELECT * FROM strategy_trials{where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def discarded_trials(
    db_path: str | Path,
    *,
    family: str | None = None,
    symbol: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> list[dict]:
    """Intentos ya descartados de una familia (misma ventana si se indica)."""
    init_db(db_path)
    clauses = ["outcome IN ('failed', 'discarded')"]
    params: list = []
    if family:
        clauses.append("family = ?")
        params.append(str(family).upper())
    if symbol:
        clauses.append("symbol = ?")
        params.append(str(symbol).upper())
    if window_start or window_end:
        clauses.append("fingerprint = ?")
        params.append(fingerprint(family or "", symbol or "", window_start, window_end))
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM strategy_trials WHERE "
            + " AND ".join(clauses)
            + " ORDER BY id DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def discarded_warning(
    db_path: str | Path,
    *,
    family: str,
    symbol: str,
    window_start: str | None = None,
    window_end: str | None = None,
) -> str | None:
    """Aviso si la familia ya fue descartada sobre la misma ventana."""
    rows = discarded_trials(
        db_path,
        family=family,
        symbol=symbol,
        window_start=window_start,
        window_end=window_end,
    )
    if not rows:
        return None
    window = f" {window_start}→{window_end}" if window_start else ""
    return (
        f"AVISO: la familia {family} ya se descartó {len(rows)} veces en "
        f"{str(symbol).upper()}{window}. Revisa el motivo antes de reoptimizar."
    )


def budget_config(path: str | Path | None = None) -> dict:
    target = Path(path) if path else BUDGET_PATH
    data: dict = {}
    if target.exists():
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        data = loaded if isinstance(loaded, dict) else {}
    assets = {
        str(key).upper(): int(value)
        for key, value in (data.get("assets") or {}).items()
    }
    return {
        "default": int(data.get("max_attempts_per_week_per_asset", 5)),
        "assets": assets,
        "warn_on_discarded_family": bool(
            data.get("warn_on_discarded_family", True)
        ),
        "source": str(target),
    }


def _week_bounds(now: datetime | None = None) -> tuple[str, str]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    iso = moment.isocalendar()
    start = date.fromisocalendar(int(iso.year), int(iso.week), 1)
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


def weekly_attempts(
    db_path: str | Path,
    symbol: str,
    now: datetime | None = None,
) -> int:
    """Intentos (pasadas distintas) del activo en la semana ISO actual."""
    init_db(db_path)
    start, end = _week_bounds(now)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT DISTINCT run_id FROM strategy_trials "
            "WHERE symbol = ? AND ts >= ? AND ts < ?",
            (str(symbol).upper(), start, end),
        ).fetchall()
    return len([row for row in rows if row["run_id"]])


def budget_status(
    db_path: str | Path,
    symbol: str,
    now: datetime | None = None,
    path: str | Path | None = None,
) -> dict:
    config = budget_config(path)
    limit = config["assets"].get(str(symbol).upper(), config["default"])
    used = weekly_attempts(db_path, symbol, now)
    start, end = _week_bounds(now)
    return {
        "symbol": str(symbol).upper(),
        "week": f"{start}/{end}",
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "exceeded": used >= limit,
        "source": config["source"],
    }


def count_incubated(db_path: str | Path) -> int:
    """Bots incubados (hook de la etapa de ciclo de vida; 0 si no existe)."""
    init_db(db_path)
    with connect(db_path) as con:
        exists = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='lifecycle_bots'"
        ).fetchone()
        if not exists:
            return 0
        row = con.execute(
            "SELECT COUNT(*) AS n FROM lifecycle_bots WHERE frozen_at IS NOT NULL"
        ).fetchone()
    return int(row["n"])


__all__ = [
    "BUDGET_PATH",
    "DISCARDED_OUTCOMES",
    "OUTCOMES",
    "SOURCES",
    "TrialsError",
    "budget_config",
    "budget_status",
    "count_incubated",
    "discarded_trials",
    "discarded_warning",
    "fingerprint",
    "list_trials",
    "record_trial",
    "weekly_attempts",
]
