"""Comparación controlada de dos modelos en modo lite.

No cambia el modelo por defecto ni envía órdenes. Sirve para medir si un MoE
~30B mejora al modelo actual con el mismo prompt y la misma fecha; con muestra
insuficiente no se extraen conclusiones.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .db import connect, init_db, utcnow
from .decisions import lite_prompt_version
from .time_utils import market_today

MIN_SAMPLE = 30


class ModelCompareError(ValueError):
    pass


def _sanitize(text: str | None) -> str:
    value = str(text or "")
    value = re.sub(r"(sk-|key-|token-)[A-Za-z0-9_-]+", "[redacted]", value)
    return value[:400]


def _hash(model: str, day: str) -> str:
    import hashlib

    base = lite_prompt_version()[1]
    return hashlib.sha256(f"{base}|{model}|{day}".encode("utf-8")).hexdigest()


def _rating(result: dict | None) -> str | None:
    value = str((result or {}).get("rating") or "").strip()
    return value or None


def run_comparison(
    db_path: str | Path,
    ticker: str,
    models: list[str] | tuple[str, ...],
    *,
    day: str | None = None,
    settings: Settings | None = None,
    runner=None,
) -> dict:
    """Ejecuta los dos modelos con el mismo prompt y guarda la comparación."""
    settings = settings or Settings()
    target_day = day or market_today().isoformat()
    if target_day != market_today().isoformat():
        raise ModelCompareError(
            "solo se compara la fecha de hoy; no se puede recrear el contexto pasado"
        )
    names = [str(item).strip() for item in models if str(item).strip()]
    if len(names) != 2:
        raise ModelCompareError("indica exactamente dos modelos separados por coma")
    if names[0] == names[1]:
        raise ModelCompareError("los modelos deben ser distintos")
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ModelCompareError("ticker inválido")

    if runner is None:
        from .agents.lite import run_lite_agent

        def runner(symbol, when, cfg, model):
            return run_lite_agent(symbol, when, cfg, model=model)

    results: list[dict | None] = []
    errors: list[str | None] = []
    for model in names:
        try:
            results.append(runner(ticker, target_day, settings, model))
            errors.append(None)
        except Exception as exc:
            results.append(None)
            errors.append(_sanitize(exc))
    ratings = [_rating(item) for item in results]
    agreement = (
        ratings[0] is not None and ratings[1] is not None and ratings[0] == ratings[1]
    )
    now = utcnow()
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO lite_model_comparisons"
            "(ts, ticker, decision_date, model_a, model_b, rating_a, confidence_a, "
            "elapsed_a, rating_b, confidence_b, elapsed_b, agreement, "
            "prompt_hash_a, prompt_hash_b, error_a, error_b) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, decision_date, model_a, model_b) DO UPDATE SET "
            "ts=excluded.ts, rating_a=excluded.rating_a, "
            "confidence_a=excluded.confidence_a, elapsed_a=excluded.elapsed_a, "
            "rating_b=excluded.rating_b, confidence_b=excluded.confidence_b, "
            "elapsed_b=excluded.elapsed_b, agreement=excluded.agreement, "
            "prompt_hash_a=excluded.prompt_hash_a, prompt_hash_b=excluded.prompt_hash_b, "
            "error_a=excluded.error_a, error_b=excluded.error_b",
            (
                now,
                ticker,
                target_day,
                names[0],
                names[1],
                ratings[0],
                (results[0] or {}).get("confidence"),
                (results[0] or {}).get("elapsed_s"),
                ratings[1],
                (results[1] or {}).get("confidence"),
                (results[1] or {}).get("elapsed_s"),
                1 if agreement else 0,
                _hash(names[0], target_day),
                _hash(names[1], target_day),
                errors[0],
                errors[1],
            ),
        )
        row = con.execute(
            "SELECT * FROM lite_model_comparisons "
            "WHERE ticker=? AND decision_date=? AND model_a=? AND model_b=?",
            (ticker, target_day, names[0], names[1]),
        ).fetchone()
    return dict(row)


def report(db_path: str | Path, *, min_sample: int = MIN_SAMPLE) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM lite_model_comparisons ORDER BY id"
        ).fetchall()
    n = len(rows)
    agreements = sum(1 for row in rows if row["agreement"])
    diffs = []
    for row in rows:
        if row["confidence_a"] is not None and row["confidence_b"] is not None:
            diffs.append(float(row["confidence_b"]) - float(row["confidence_a"]))
    by_model: dict[str, dict] = {}
    for row in rows:
        for side in ("a", "b"):
            model = str(row[f"model_{side}"])
            item = by_model.setdefault(
                model, {"model": model, "n": 0, "errors": 0, "confidence": []}
            )
            item["n"] += 1
            if row[f"error_{side}"]:
                item["errors"] += 1
            if row[f"confidence_{side}"] is not None:
                item["confidence"].append(float(row[f"confidence_{side}"]))
    models = [
        {
            "model": item["model"],
            "n": item["n"],
            "errors": item["errors"],
            "mean_confidence": (
                sum(item["confidence"]) / len(item["confidence"])
                if item["confidence"]
                else None
            ),
        }
        for item in by_model.values()
    ]
    return {
        "n": n,
        "agreement_rate": (agreements / n) if n else None,
        "mean_confidence_diff": (sum(diffs) / len(diffs)) if diffs else None,
        "by_model": models,
        "insufficient": n < min_sample,
        "sample_warning": (
            f"muestra insuficiente: n={n} < {min_sample}" if n < min_sample else ""
        ),
    }


def comparisons(db_path: str | Path, *, limit: int = 50) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM lite_model_comparisons ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "MIN_SAMPLE",
    "ModelCompareError",
    "comparisons",
    "report",
    "run_comparison",
]
