"""Estructura del VIX: VIXCLS / VXVCLS desde FRED, solo lectura.

VIX/VIX3M > 1 = backwardation; < 1 = contango. Sin clave FRED se usa la caché
local; si tampoco hay caché, el resultado es ``Sin datos``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from ..config import ROOT, load_secrets

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {"vix": "VIXCLS", "vix3m": "VXVCLS"}
CACHE_DIR = ROOT / "data" / "cache" / "fred"
CACHE_FILE = CACHE_DIR / "vix_structure.json"


class VixError(RuntimeError):
    pass


def compute_structure(vix: pd.Series, vix3m: pd.Series) -> pd.DataFrame:
    """DataFrame causal con ratio y flag de estructura."""
    left = pd.to_numeric(vix, errors="coerce").dropna()
    right = pd.to_numeric(vix3m, errors="coerce").dropna()
    left.index = pd.to_datetime(left.index, utc=True)
    right.index = pd.to_datetime(right.index, utc=True)
    frame = pd.concat(
        {"vix": left, "vix3m": right}, axis=1, join="inner"
    ).dropna()
    frame = frame[frame["vix3m"] > 0].copy()
    frame["ratio"] = frame["vix"] / frame["vix3m"]
    frame["structure"] = "flat"
    frame.loc[frame["ratio"] > 1.0, "structure"] = "backwardation"
    frame.loc[frame["ratio"] < 1.0, "structure"] = "contango"
    frame["vix_backwardation"] = frame["structure"] == "backwardation"
    return frame.sort_index()


def _api_key() -> str | None:
    load_secrets()
    return os.getenv("FRED_API_KEY") or None


def _fetch_series(
    series_id: str,
    *,
    api_key: str,
    client: httpx.Client,
    start: str = "2010-01-01",
) -> pd.Series:
    response = client.get(
        FRED_BASE,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
        },
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("observations") or []
    values = {}
    for row in rows:
        try:
            values[pd.Timestamp(row["date"], tz="UTC")] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
    return pd.Series(values, dtype=float).sort_index()


def fetch_vix_structure(
    *,
    api_key: str | None = None,
    client: httpx.Client | None = None,
    start: str = "2010-01-01",
) -> dict:
    key = api_key or _api_key()
    if not key:
        cached = load_cached()
        if cached is not None:
            return {
                "status": "cache",
                "latest": cached[-1] if cached else None,
                "observations": len(cached),
            }
        return {"status": "sin datos", "reason": "falta FRED_API_KEY"}
    own = client is None
    http = client or httpx.Client(timeout=25)
    try:
        vix = _fetch_series(SERIES["vix"], api_key=key, client=http, start=start)
        vix3m = _fetch_series(SERIES["vix3m"], api_key=key, client=http, start=start)
    finally:
        if own:
            http.close()
    frame = compute_structure(vix, vix3m)
    if frame.empty:
        return {"status": "sin datos", "reason": "FRED sin observaciones"}
    records = [
        {
            "date": str(stamp.date()),
            "vix": round(float(row["vix"]), 4),
            "vix3m": round(float(row["vix3m"]), 4),
            "ratio": round(float(row["ratio"]), 4),
            "structure": str(row["structure"]),
            "vix_backwardation": bool(row["vix_backwardation"]),
        }
        for stamp, row in frame.iterrows()
    ]
    save_cached(records)
    return {
        "status": "ok",
        "latest": records[-1],
        "observations": len(records),
    }


def save_cached(records: list[dict], path: str | Path | None = None) -> Path:
    target = Path(path) if path else CACHE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def load_cached(path: str | Path | None = None) -> list[dict]:
    target = Path(path) if path else CACHE_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def latest_structure(
    as_of: datetime | None = None,
    path: str | Path | None = None,
) -> dict:
    moment = as_of or datetime.now(timezone.utc)
    day = pd.Timestamp(moment).date().isoformat()
    rows = [row for row in load_cached(path) if str(row.get("date")) <= day]
    if not rows:
        return {"status": "sin datos", "latest": None}
    return {"status": "cache", "latest": rows[-1], "observations": len(rows)}


__all__ = [
    "CACHE_FILE",
    "VixError",
    "compute_structure",
    "fetch_vix_structure",
    "latest_structure",
    "load_cached",
    "save_cached",
]
