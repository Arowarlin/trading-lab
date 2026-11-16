"""Tasas históricas de swap a partir de puntos MT5 y DFF de FRED.

El swap en puntos de MT5 está expresado a los precios y tipos del día de
lectura. Para un backtest histórico se convierte a tasa anual en esa fecha y
se reconstruye la tasa diaria con DFF + markup del bróker.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

from .config import ROOT, load_secrets

FRED_BASE = "https://api.stlouisfed.org/fred"
DFF_CACHE = ROOT / "data" / "cache" / "fred"


class SwapRateError(RuntimeError):
    pass


def annual_pct_from_points(
    points: float,
    *,
    point: float,
    contract_size: float,
    price: float,
    days: int = 365,
) -> float:
    """Convierte puntos de swap a % anual en la fecha de lectura."""
    if point <= 0 or contract_size <= 0 or price <= 0:
        raise SwapRateError("point, contract_size y price deben ser > 0")
    return (
        float(points)
        * float(point)
        * float(contract_size)
        * float(days)
        / float(price)
        * 100.0
    )


def _api_key(api_key: str | None = None) -> str:
    if api_key:
        return api_key
    load_secrets()
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise SwapRateError("falta FRED_API_KEY")
    return key


def _cache_path(series_id: str, start: date, end: date) -> Path:
    digest = hashlib.sha256(
        f"{series_id}|{start.isoformat()}|{end.isoformat()}".encode("utf-8")
    ).hexdigest()[:20]
    return DFF_CACHE / f"{series_id}_{digest}.json"


def load_dff(
    start: date,
    end: date,
    *,
    cache_dir: str | Path | None = None,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> pd.Series:
    """DFF diario de FRED, indexado por fecha y con forward-fill."""
    if end < start:
        raise SwapRateError("end anterior a start")
    cache = Path(cache_dir) if cache_dir else DFF_CACHE
    cache.mkdir(parents=True, exist_ok=True)
    path = _cache_path("DFF", start, end) if cache == DFF_CACHE else (
        cache / f"DFF_{start.isoformat()}_{end.isoformat()}.json"
    )
    payload = None
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
    if payload is None:
        key = _api_key(api_key)
        params = {
            "series_id": "DFF",
            "api_key": key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
        }
        own = client is None
        client = client or httpx.Client(timeout=20)
        try:
            response = client.get(
                f"{FRED_BASE}/series/observations", params=params
            )
        except httpx.HTTPError as exc:
            raise SwapRateError(f"FRED no disponible: {type(exc).__name__}") from exc
        finally:
            if own:
                client.close()
        if response.status_code >= 400:
            raise SwapRateError(f"FRED HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SwapRateError("FRED respuesta no JSON") from exc
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    values = {}
    for item in payload.get("observations") or []:
        raw = str(item.get("value") or "").strip()
        if raw in {"", "."}:
            continue
        try:
            values[pd.Timestamp(item["date"]).date()] = float(raw)
        except (KeyError, TypeError, ValueError):
            continue
    if not values:
        raise SwapRateError("DFF Sin datos")
    series = pd.Series(values, dtype=float).sort_index()
    series.index = pd.DatetimeIndex(series.index)
    return series


def dff_on(series: pd.Series | dict | None, day: date) -> float | None:
    if series is None:
        return None
    if isinstance(series, dict):
        keys = sorted(key for key in series if key <= day)
        return float(series[keys[-1]]) if keys else None
    if len(series) == 0:
        return None
    stamp = pd.Timestamp(day)
    try:
        value = series.loc[:stamp].iloc[-1]
    except (KeyError, IndexError):
        return None
    return float(value) if pd.notna(value) else None


def markup_from_today(annual_pct: float, dff_today: float | None) -> float | None:
    if dff_today is None:
        return None
    return float(annual_pct) - float(dff_today)


def historical_daily_rate(
    dff_today: float | None,
    markup: float | None,
    day: date,
    dff_series: pd.Series | dict | None,
) -> float | None:
    """Tasa anual (en fracción) para una noche histórica."""
    if markup is None:
        return None
    rate = dff_on(dff_series, day)
    if rate is None:
        return None
    return (rate + markup) / 100.0


__all__ = [
    "DFF_CACHE",
    "SwapRateError",
    "annual_pct_from_points",
    "dff_on",
    "historical_daily_rate",
    "load_dff",
    "markup_from_today",
]
