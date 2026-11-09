"""Comparación lite vs deep sobre el mismo activo y fecha.

Solo mide; ninguna decisión envía órdenes. Las pasadas retrospectivas se
marcan y se excluyen de toda estadística forward.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .agents.bridge import RATING_TO_TARGET
from .config import Settings
from .db import connect, init_db, utcnow
from .decisions import (
    deep_prompt_hash,
    lite_prompt_version,
    record_decision,
    report_by_source,
)

DEFAULT_ANALYSTS = ("market", "news", "fundamentals", "social")
MIN_SAMPLE = 30


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
) -> tuple[dict | None, list[str], str | None]:
    """Intenta todos los analistas; si falla, usa el primero que funcione solo."""
    try:
        result = runner(ticker, day, ",".join(analysts))
        return result, list(analysts), None
    except Exception as exc:
        first_error = _sanitize(exc)
    failed: list[str] = []
    for analyst in analysts:
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
) -> dict:
    settings = settings or Settings()
    target_day = day or date.today().isoformat()
    if target_day != date.today().isoformat() and not retrospective:
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

    if deep_runner is None:
        from .agents.bridge import run_tradingagents

        def deep_runner(symbol, when, names):
            return run_tradingagents(symbol, when, names, save=True)

    lite: dict | None = None
    lite_error = None
    try:
        lite = lite_runner(ticker, target_day, settings)
    except Exception as exc:
        lite_error = _sanitize(exc)
    deep, deep_analysts, deep_error = _run_deep(
        ticker, target_day, analyst_list, deep_runner
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
            "SELECT * FROM agent_comparisons WHERE retrospective = 0 ORDER BY id"
        ).fetchall()
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


__all__ = [
    "CompareError",
    "DEFAULT_ANALYSTS",
    "MIN_SAMPLE",
    "comparisons",
    "report",
    "run_comparison",
]
