"""Commitments of Traders (CFTC), solo lectura y sin coste.

Los informes se publican los viernes (15:30 ET) con datos del martes anterior.
Este módulo guarda **ambas** fechas y expone `latest_as_of()` para que ningún
uso posterior pueda mirar datos antes de su publicación.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from ..config import ROOT

CFTC_BASE = "https://publicreporting.cftc.gov/resource"
DATASETS = {
    "legacy": "6dca-aqww",
    "financial": "gpe5-46if",
}
CONTRACTS = {
    "nasdaq": {
        "name": "NASDAQ MINI", "dataset": "financial", "label": "E-mini Nasdaq",
    },
    "sp500": {
        "name": "E-MINI S&P 500", "dataset": "financial",
        "label": "E-mini S&P 500",
    },
    "gold": {"name": "GOLD", "dataset": "legacy", "label": "Gold"},
    "eur": {"name": "EURO FX", "dataset": "legacy", "label": "Euro FX"},
    "gbp": {"name": "BRITISH POUND", "dataset": "legacy", "label": "British Pound"},
    "jpy": {"name": "JAPANESE YEN", "dataset": "legacy", "label": "Japanese Yen"},
}
PUBLISH_TZ = ZoneInfo("America/New_York")
PUBLISH_TIME = time(15, 30)
CACHE_DIR = ROOT / "data" / "cache" / "cot"


class CotError(RuntimeError):
    pass


def publication_date(report_date) -> datetime:
    """Viernes siguiente al martes de referencia, 15:30 ET, en UTC."""
    day = pd.Timestamp(report_date).date()
    candidate = day + timedelta(days=3)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    local = datetime.combine(candidate, PUBLISH_TIME, tzinfo=PUBLISH_TZ)
    return local.astimezone(timezone.utc)


def _query_url(dataset: str, contract: str, limit: int) -> str:
    dataset_id = DATASETS.get(dataset)
    if dataset_id is None:
        raise CotError(f"dataset desconocido: {dataset}")
    return f"{CFTC_BASE}/{dataset_id}.json"


def _params(contract: str, limit: int) -> dict:
    return {
        "$where": f"contract_market_name = '{contract}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": max(1, int(limit)),
    }


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def _row(key: str, raw: dict, dataset: str) -> dict:
    report = pd.Timestamp(raw["report_date_as_yyyy_mm_dd"]).date()
    return {
        "contract": key,
        "label": CONTRACTS[key]["label"],
        "dataset": dataset,
        "report_date": report.isoformat(),
        "published_at": publication_date(report).isoformat(),
        "market": raw.get("market_and_exchange_names"),
        "open_interest": _num(raw.get("open_interest_all")),
        "noncommercial_long": _num(raw.get("noncomm_positions_long_all")),
        "noncommercial_short": _num(raw.get("noncomm_positions_short_all")),
        "commercial_long": _num(raw.get("comm_positions_long_all")),
        "commercial_short": _num(raw.get("comm_positions_short_all")),
        "asset_manager_long": _num(raw.get("asset_mgr_positions_long")),
        "asset_manager_short": _num(raw.get("asset_mgr_positions_short")),
        "leveraged_long": _num(raw.get("lev_money_positions_long")),
        "leveraged_short": _num(raw.get("lev_money_positions_short")),
    }


def fetch_cot(
    *,
    contracts: tuple[str, ...] | None = None,
    limit: int = 8,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Descarga los últimos informes públicos; no requiere API key."""
    selected = contracts or tuple(CONTRACTS)
    own = client is None
    http = client or httpx.Client(timeout=25, follow_redirects=True)
    rows: list[dict] = []
    try:
        for key in selected:
            spec = CONTRACTS.get(str(key).lower())
            if spec is None:
                raise CotError(f"contrato desconocido: {key}")
            response = http.get(
                _query_url(spec["dataset"], spec["name"], limit),
                params=_params(spec["name"], limit),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise CotError(f"respuesta CFTC inválida para {key}")
            for raw in payload:
                rows.append(_row(str(key).lower(), raw, spec["dataset"]))
    finally:
        if own:
            http.close()
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["report_date", "contract"]).reset_index(drop=True)


def save_cot(frame: pd.DataFrame, path: str | Path | None = None) -> Path:
    target = Path(path) if path else CACHE_DIR / "cot.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)
    return target


def load_cot(path: str | Path | None = None) -> pd.DataFrame:
    target = Path(path) if path else CACHE_DIR / "cot.parquet"
    if not target.exists():
        raise CotError(f"sin datos COT: {target}")
    return pd.read_parquet(target)


def latest_as_of(
    frame: pd.DataFrame,
    as_of: datetime | None = None,
    *,
    contract: str | None = None,
) -> pd.DataFrame:
    """Solo filas cuya `published_at` ya ocurrió en `as_of`."""
    moment = as_of or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    data = frame.copy()
    data["published_at"] = pd.to_datetime(data["published_at"], utc=True)
    data = data[data["published_at"] <= pd.Timestamp(moment)]
    if contract:
        data = data[data["contract"] == str(contract).lower()]
    return data.sort_values("published_at")


__all__ = [
    "CACHE_DIR",
    "CONTRACTS",
    "CotError",
    "fetch_cot",
    "latest_as_of",
    "load_cot",
    "publication_date",
    "save_cot",
]
