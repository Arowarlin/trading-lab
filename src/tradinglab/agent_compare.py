"""Comparación lite vs deep sobre el mismo activo y fecha.

Solo mide; ninguna decisión envía órdenes. Las pasadas retrospectivas se
marcan y se excluyen de toda estadística forward.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

from .agents.bridge import RATING_TO_TARGET
from .config import DEFAULT_DB, Settings
from .db import connect, init_db, utcnow
from .decisions import (
    deep_prompt_hash,
    lite_prompt_version,
    record_decision,
    report_by_source,
)
from .time_utils import market_today

DEFAULT_ANALYSTS = ("market", "news", "fundamentals", "social")
MIN_SAMPLE = 30

# Dirección (no peso objetivo) de cada rating: sirve para el acierto a 20 días.
RATING_DIRECTION: dict[str, float] = {
    "buy": 1.0,
    "overweight": 1.0,
    "sell": -1.0,
    "underweight": -1.0,
}


class CompareError(ValueError):
    pass


def _target(rating: str | None) -> float | None:
    return RATING_TO_TARGET.get(str(rating or ""))


def _sanitize(text: str | None) -> str:
    value = str(text or "")
    value = re.sub(r"(sk-|key-|token-)[A-Za-z0-9_-]+", "[redacted]", value)
    return value[:400]


def _run_deep(
    ticker: str,
    day: str,
    analysts: list[str],
    runner,
    *,
    budget: dict | None = None,
) -> tuple[dict | None, list[str], str | None]:
    """Intenta todos los analistas; si falla, usa el primero que funcione solo.

    `budget["remaining"]` es el presupuesto total del deep en segundos: los
    reintentos uno a uno consumen el mismo presupuesto, no uno nuevo por
    analista (antes 4 analistas podían colgar el proceso 2,5 h).
    """

    def left() -> float | None:
        return None if budget is None else float(budget.get("remaining", 0.0))

    try:
        if (left() is not None and left() < 120):
            return None, list(analysts), "presupuesto del deep agotado"
        result = runner(ticker, day, ",".join(analysts))
        return result, list(analysts), None
    except Exception as exc:
        first_error = _sanitize(exc)
    failed: list[str] = []
    for analyst in analysts:
        if left() is not None and left() < 120:
            failed.append(analyst)
            continue
        try:
            result = runner(ticker, day, analyst)
            return result, [analyst], None
        except Exception:
            failed.append(analyst)
    return None, failed, first_error


def run_comparison(
    db_path: str | Path,
    ticker: str,
    *,
    day: str | None = None,
    analysts: tuple[str, ...] | list[str] = DEFAULT_ANALYSTS,
    settings: Settings | None = None,
    retrospective: bool = False,
    lite_runner=None,
    deep_runner=None,
    deep_timeout: int = 1800,
) -> dict:
    settings = settings or Settings()
    target_day = day or market_today().isoformat()
    if target_day != market_today().isoformat() and not retrospective:
        raise CompareError(
            "solo se compara la fecha de hoy; usa --retrospective para una pasada histórica"
        )
    ticker = str(ticker).strip().upper()
    if not ticker or ticker == "REPORT":
        raise CompareError("ticker inválido")
    analyst_list = [str(item).strip() for item in analysts if str(item).strip()]
    if not analyst_list:
        raise CompareError("lista de analistas vacía")

    if lite_runner is None:
        from .agents.lite import run_lite_agent

        def lite_runner(symbol, when, cfg):
            return run_lite_agent(symbol, when, cfg)

    budget = {"remaining": float(max(120, int(deep_timeout)))}
    if deep_runner is None:
        import time

        from .agents.bridge import run_tradingagents

        def deep_runner(symbol, when, names):
            timeout = max(60, int(budget["remaining"]))
            started = time.monotonic()
            try:
                return run_tradingagents(symbol, when, names, save=True, timeout=timeout)
            finally:
                budget["remaining"] -= time.monotonic() - started

    lite: dict | None = None
    lite_error = None
    try:
        lite = lite_runner(ticker, target_day, settings)
    except Exception as exc:
        lite_error = _sanitize(exc)
    deep, deep_analysts, deep_error = _run_deep(
        ticker,
        target_day,
        analyst_list,
        deep_runner,
        budget=budget if deep_runner is not None else None,
    )

    if lite:
        record_decision(
            db_path,
            {**lite, "ticker": ticker, "date": target_day, "analysts": ["lite"]},
            mode="lite",
        )
    if deep:
        record_decision(
            db_path,
            {
                **deep,
                "ticker": ticker,
                "date": target_day,
                "analysts": deep_analysts,
            },
            mode="deep",
        )

    lite_rating = str((lite or {}).get("rating") or "") or None
    deep_rating = str((deep or {}).get("rating") or "") or None
    lite_confidence = (lite or {}).get("confidence")
    deep_confidence = (deep or {}).get("confidence")
    lite_target = _target(lite_rating)
    deep_target = _target(deep_rating)
    lite_model = (lite or {}).get("model")
    deep_model = (deep or {}).get("model")
    lite_hash = lite_prompt_version()[1] if lite else None
    deep_hash = (
        deep_prompt_hash(deep_model, deep_analysts, target_day) if deep else None
    )
    agreement = (
        lite_rating is not None
        and deep_rating is not None
        and lite_rating == deep_rating
    )

    init_db(db_path)
    now = utcnow()
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO agent_comparisons"
            "(ts, ticker, decision_date, lite_rating, lite_confidence, lite_target, "
            "deep_rating, deep_confidence, deep_target, lite_model, deep_model, "
            "lite_prompt_hash, deep_prompt_hash, lite_analysts, deep_analysts, "
            "lite_duration_s, deep_duration_s, agreement, retrospective, "
            "lite_error, deep_error) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, decision_date, retrospective) DO UPDATE SET "
            "lite_rating=excluded.lite_rating, lite_confidence=excluded.lite_confidence, "
            "lite_target=excluded.lite_target, deep_rating=excluded.deep_rating, "
            "deep_confidence=excluded.deep_confidence, deep_target=excluded.deep_target, "
            "lite_model=excluded.lite_model, deep_model=excluded.deep_model, "
            "lite_prompt_hash=excluded.lite_prompt_hash, "
            "deep_prompt_hash=excluded.deep_prompt_hash, "
            "lite_analysts=excluded.lite_analysts, deep_analysts=excluded.deep_analysts, "
            "lite_duration_s=excluded.lite_duration_s, "
            "deep_duration_s=excluded.deep_duration_s, "
            "agreement=excluded.agreement, lite_error=excluded.lite_error, "
            "deep_error=excluded.deep_error",
            (
                now,
                ticker,
                target_day,
                lite_rating,
                float(lite_confidence) if lite_confidence is not None else None,
                lite_target,
                deep_rating,
                float(deep_confidence) if deep_confidence is not None else None,
                deep_target,
                lite_model,
                deep_model,
                lite_hash,
                deep_hash,
                "lite",
                ",".join(deep_analysts or []),
                float((lite or {}).get("elapsed_s")) if lite else None,
                float((deep or {}).get("elapsed_s")) if deep else None,
                1 if agreement else 0,
                1 if retrospective else 0,
                lite_error,
                deep_error,
            ),
        )
        row = con.execute(
            "SELECT * FROM agent_comparisons "
            "WHERE ticker=? AND decision_date=? AND retrospective=?",
            (ticker, target_day, 1 if retrospective else 0),
        ).fetchone()
    return dict(row)


def report(db_path: str | Path, *, min_sample: int = MIN_SAMPLE) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM agent_comparisons WHERE retrospective = 0 "
            "AND (deep_error IS NULL OR deep_error = '') ORDER BY id"
        ).fetchall()
        deep_errors = con.execute(
            "SELECT COUNT(*) AS n FROM agent_comparisons "
            "WHERE retrospective = 0 AND deep_error IS NOT NULL "
            "AND deep_error != ''"
        ).fetchone()["n"]
    n = len(rows)
    agreements = sum(1 for row in rows if row["agreement"])
    matrix: dict[str, dict[str, int]] = {}
    diffs: list[float] = []
    for row in rows:
        lite = str(row["lite_rating"] or "—")
        deep = str(row["deep_rating"] or "—")
        matrix.setdefault(lite, {})
        matrix[lite][deep] = matrix[lite].get(deep, 0) + 1
        if row["lite_target"] is not None and row["deep_target"] is not None:
            diffs.append(float(row["deep_target"]) - float(row["lite_target"]))
    return {
        "n": n,
        "deep_errors": int(deep_errors),
        "agreement_rate": (agreements / n) if n else None,
        "matrix": matrix,
        "mean_target_diff": (sum(diffs) / len(diffs)) if diffs else None,
        "insufficient": n < min_sample,
        "sample_warning": (
            f"muestra insuficiente: n={n} < {min_sample}" if n < min_sample else ""
        ),
        "by_source": report_by_source(db_path, min_sample=min_sample),
    }


def comparisons(db_path: str | Path, *, limit: int = 50) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM agent_comparisons ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


# ------------------------------------------------------------------ ranking


def _clean_model(value: Any) -> str:
    return str(value or "").strip()


def model_ranking(
    db_path: str | Path = DEFAULT_DB,
    *,
    min_sample: int = MIN_SAMPLE,
) -> list[dict]:
    """Ranking de modelos por acierto a 20 días.

    Junta `lite_model_comparisons`, `agent_comparisons` y `decision_outcomes`
    para contar las decisiones de cada modelo, y `llm_calls` para la tasa de
    `schema_ok`. El acierto se mide con el retorno de 20 días **con el signo
    de la dirección que dio el modelo**; el retorno medio usa ese mismo
    retorno con signo.

    Con menos de `min_sample` decisiones por modelo la fila se marca
    `insufficient`. Sin datos devuelve una lista vacía.
    """
    init_db(db_path)
    with connect(db_path) as con:
        outcomes = con.execute("SELECT * FROM decision_outcomes").fetchall()
        pairs = con.execute("SELECT * FROM agent_comparisons").fetchall()
        lite_pairs = con.execute("SELECT * FROM lite_model_comparisons").fetchall()
        calls = con.execute(
            "SELECT model, schema_ok, latency_ms FROM llm_calls"
        ).fetchall()

    decisions: dict[str, set[tuple[str, str]]] = {}
    returns: dict[str, list[float]] = {}
    latencies: dict[str, list[float]] = {}
    agreements: dict[str, list[int]] = {}
    schema: dict[str, list[int]] = {}

    def _touch(model: str, ticker: str, day: str) -> None:
        name = _clean_model(model)
        if not name:
            return
        decisions.setdefault(name, set()).add((str(ticker), str(day)))

    def _latency(model: str, value: Any) -> None:
        name = _clean_model(model)
        if name and value is not None:
            latencies.setdefault(name, []).append(float(value))

    def _agreement(models: list[str], value: Any) -> None:
        if value is None:
            return
        for model in models:
            name = _clean_model(model)
            if name:
                agreements.setdefault(name, []).append(int(value))

    for row in outcomes:
        model = _clean_model(row["model"])
        if not model:
            continue
        _touch(model, row["ticker"], row["decision_date"])
        _latency(model, row["duration_s"])
        if row["return_20d"] is not None:
            direction = RATING_DIRECTION.get(str(row["rating"] or "").strip().lower())
            if direction is not None:
                returns.setdefault(model, []).append(float(row["return_20d"]) * direction)

    for row in pairs:
        lite_model = _clean_model(row["lite_model"])
        deep_model = _clean_model(row["deep_model"])
        _touch(lite_model, row["ticker"], row["decision_date"])
        _touch(deep_model, row["ticker"], row["decision_date"])
        _latency(lite_model, row["lite_duration_s"])
        _latency(deep_model, row["deep_duration_s"])
        _agreement([lite_model, deep_model], row["agreement"])

    for row in lite_pairs:
        model_a = _clean_model(row["model_a"])
        model_b = _clean_model(row["model_b"])
        _touch(model_a, row["ticker"], row["decision_date"])
        _touch(model_b, row["ticker"], row["decision_date"])
        _latency(model_a, row["elapsed_a"])
        _latency(model_b, row["elapsed_b"])
        _agreement([model_a, model_b], row["agreement"])

    for row in calls:
        model = _clean_model(row["model"])
        if model and row["schema_ok"] is not None:
            schema.setdefault(model, []).append(int(row["schema_ok"]))
        if model and row["latency_ms"] is not None:
            latencies.setdefault(model, []).append(float(row["latency_ms"]) / 1000.0)

    out: list[dict] = []
    for model, keys in decisions.items():
        rets = returns.get(model, [])
        lats = latencies.get(model, [])
        agrees = agreements.get(model, [])
        sch = schema.get(model, [])
        n = len(keys)
        out.append(
            {
                "model": model,
                "n": n,
                "n_with_outcome": len(rets),
                "hit_rate_20d": (
                    sum(1 for value in rets if value > 0.0) / len(rets) if rets else None
                ),
                "mean_return_20d": (sum(rets) / len(rets)) if rets else None,
                "median_latency_s": (statistics.median(lats) if lats else None),
                "schema_ok_rate": (sum(sch) / len(sch)) if sch else None,
                "agreement_rate": (sum(agrees) / len(agrees)) if agrees else None,
                "insufficient": n < min_sample,
                "sample_warning": (
                    f"muestra insuficiente: n={n} < {min_sample}" if n < min_sample else ""
                ),
            }
        )
    out.sort(
        key=lambda row: (
            row["hit_rate_20d"] is None,
            -(row["hit_rate_20d"] or 0.0),
            row["model"],
        )
    )
    return out


__all__ = [
    "CompareError",
    "DEFAULT_ANALYSTS",
    "MIN_SAMPLE",
    "comparisons",
    "model_ranking",
    "report",
    "run_comparison",
]
