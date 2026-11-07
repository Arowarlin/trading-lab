"""Resultados de decisiones del LLM y comparación con líneas base.

No evalúa órdenes: mide si el rating del agente aporta algo frente a comprar
siempre o no hacer nada. Con menos de 30 decisiones no se sacan conclusiones.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, timedelta
from pathlib import Path
from statistics import NormalDist

import pandas as pd

from . import data as data_mod
from .config import ROOT
from .db import connect, init_db, utcnow


def lite_prompt_version() -> tuple[str, str]:
    from .agents.lite import SCHEMA, SYSTEM

    version = "lite-v1"
    digest = hashlib.sha256(
        (SYSTEM + json.dumps(SCHEMA, sort_keys=True)).encode("utf-8")
    ).hexdigest()
    return version, digest


def record_decision(db_path: str | Path, payload: dict, *, mode: str) -> None:
    ticker = str(payload.get("ticker") or "").upper()
    decision_date = str(payload.get("date") or date.today().isoformat())
    if not ticker:
        return
    rating = str(payload.get("rating") or "REVIEW")
    confidence = payload.get("confidence")
    ref_price = (payload.get("context") or {}).get("price")
    if ref_price is None:
        try:
            df = data_mod.fetch(ticker, decision_date, date.today().isoformat(), ROOT / "data" / "cache")
            ref_price = float(df["close"].iloc[-1])
        except Exception:
            ref_price = None
    if mode == "lite":
        prompt_version, prompt_hash = lite_prompt_version()
    else:
        prompt_version, prompt_hash = f"{mode}-v1", hashlib.sha256(f"{mode}:{payload.get('model', '')}".encode()).hexdigest()

    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating, confidence, model, prompt_version, "
            "prompt_hash, ref_price) VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, decision_date, mode) DO UPDATE SET "
            "rating=excluded.rating, confidence=excluded.confidence, model=excluded.model, "
            "prompt_version=excluded.prompt_version, prompt_hash=excluded.prompt_hash, "
            "ref_price=COALESCE(excluded.ref_price, decision_outcomes.ref_price)",
            (
                utcnow(),
                ticker,
                decision_date,
                mode,
                rating,
                float(confidence) if confidence is not None else None,
                payload.get("model"),
                prompt_version,
                prompt_hash,
                float(ref_price) if ref_price is not None else None,
            ),
        )


def update_outcomes(db_path: str | Path, cache_dir: str | Path) -> int:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM decision_outcomes WHERE return_20d IS NULL"
        ).fetchall()
    updated = 0
    for row in rows:
        try:
            df = data_mod.fetch(
                row["ticker"],
                row["decision_date"],
                date.today().isoformat(),
                cache_dir,
            )
            close = df["close"].astype(float)
            if len(close) < 2:
                continue
            base = float(close.iloc[0])
            r1 = float(close.iloc[1]) / base - 1.0 if len(close) > 1 else None
            r5 = float(close.iloc[5]) / base - 1.0 if len(close) > 5 else None
            r20 = float(close.iloc[20]) / base - 1.0 if len(close) > 20 else None
            with connect(db_path) as con:
                con.execute(
                    "UPDATE decision_outcomes SET return_1d=?, return_5d=?, return_20d=?, updated_at=? "
                    "WHERE id=?",
                    (r1, r5, r20, utcnow(), row["id"]),
                )
            updated += 1
        except Exception:
            continue
    return updated


def report(db_path: str | Path) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT rating, return_1d, return_5d, return_20d FROM decision_outcomes "
            "WHERE return_20d IS NOT NULL"
        ).fetchall()
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(str(row["rating"]), []).append(row)
    out = []
    nd = NormalDist()
    for rating, items in sorted(groups.items()):
        n = len(items)
        r20 = [float(x["return_20d"]) for x in items]
        mean = statistics.mean(r20)
        std = statistics.stdev(r20) if n > 1 else 0.0
        t_stat = mean / (std / (n**0.5)) if std > 0 and n > 1 else None
        p_value = 2 * (1 - nd.cdf(abs(t_stat))) if t_stat is not None else None
        out.append(
            {
                "rating": rating,
                "n": n,
                "mean_1d": statistics.mean(float(x["return_1d"]) for x in items if x["return_1d"] is not None)
                if any(x["return_1d"] is not None for x in items)
                else None,
                "mean_5d": statistics.mean(float(x["return_5d"]) for x in items if x["return_5d"] is not None)
                if any(x["return_5d"] is not None for x in items)
                else None,
                "mean_20d": mean,
                "t_stat": t_stat,
                "p_value": p_value,
            }
        )
    return out


def trend_target_at(ticker: str, decision_date: str, cache_dir: str | Path):
    """Objetivo de la estrategia trend en la fecha de la decisión."""
    from . import data as data_mod
    from .strategies import trend_signal

    start = (date.fromisoformat(decision_date) - timedelta(days=400)).isoformat()
    df = data_mod.fetch(ticker, start, date.today().isoformat(), cache_dir)
    if len(df) < 210:
        return None
    result = trend_signal(df)
    target = result.target
    stamp = pd.Timestamp(decision_date)
    if target.index.tz is not None:
        stamp = stamp.tz_localize(target.index.tz)
    mask = target.index <= stamp
    if not mask.any():
        return None
    return float(target[mask].iloc[-1])


def compare(db_path: str | Path, cache_dir: str | Path) -> dict:
    """Compara LLM lite, buy&hold y señal trend sobre el mismo forward 20d."""
    from .agents.bridge import RATING_TO_TARGET

    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT ticker, decision_date, rating, return_20d FROM decision_outcomes "
            "WHERE return_20d IS NOT NULL ORDER BY id"
        ).fetchall()

    llm_returns = []
    bh_returns = []
    trend_returns = []
    trend_covered = 0
    trend_cache: dict[tuple[str, str], float | None] = {}

    for row in rows:
        raw = float(row["return_20d"])
        target = RATING_TO_TARGET.get(str(row["rating"]))
        position = float(target) if target is not None else 0.0
        llm_returns.append(position * raw)
        bh_returns.append(raw)

        key = (str(row["ticker"]), str(row["decision_date"]))
        if key not in trend_cache:
            try:
                trend_cache[key] = trend_target_at(key[0], key[1], cache_dir)
            except Exception:
                trend_cache[key] = None
        trend_target = trend_cache[key]
        if trend_target is not None:
            trend_returns.append(float(trend_target) * raw)
            trend_covered += 1

    def mean(values: list[float]) -> float | None:
        return statistics.mean(values) if values else None

    return {
        "n": len(rows),
        "llm_n": len(llm_returns),
        "llm_mean_20d": mean(llm_returns),
        "buy_hold_n": len(bh_returns),
        "buy_hold_mean_20d": mean(bh_returns),
        "trend_n": trend_covered,
        "trend_mean_20d": mean(trend_returns),
        "trend_coverage": trend_covered / len(rows) if rows else 0.0,
    }


__all__ = ["lite_prompt_version", "record_decision", "report", "compare", "update_outcomes"]
