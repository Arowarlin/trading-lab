"""Resultados de decisiones del LLM y comparación con líneas base.

No evalúa órdenes: mide si el rating del agente aporta algo frente a comprar
siempre o no hacer nada. Con menos de 30 decisiones no se sacan conclusiones.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date
from pathlib import Path
from statistics import NormalDist

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


__all__ = ["lite_prompt_version", "record_decision", "report", "update_outcomes"]
