"""Calidad de datos por fuente (bróker/Dukascopy) y temporalidad.

Reutiliza ``data_quality.check_dataset`` sin duplicar sus comprobaciones. Solo
cambia los umbrales de hueco según el timeframe para que un fin de semana no se
confunda con un hueco en H4/D1, y añade el recuento de días hábiles sin barras.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT
from .calendars import FX_METAL, NYSE
from .config import DataQualityConfig, SourceConfig, load_engine_config
from .data_quality import check_dataset
from .data_sources import DataSourceError, load_source, normalize_source
from .fetch_dukascopy import SYMBOLS
from .resample import TIMEFRAMES

NYSE_SYMBOLS = {"US100", "US500", "US30"}
FX_METAL_SYMBOLS = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}

# (gap_factor, max_gap_hours) por temporalidad. Los huecos >= max_gap son
# cierres de sesión/fin de semana; el resto se cuenta como hueco real.
_GAP_RULES = {
    "M1": (3.0, 4.0),
    "M5": (3.0, 4.0),
    "M15": (3.0, 4.0),
    "M30": (3.0, 4.0),
    "H1": (1.5, 6.0),
    "H4": (1.5, 24.0),
    "D1": (1.5, 72.0),
}


def quality_config(
    base: DataQualityConfig,
    symbol: str,
    timeframe: str,
    source: str,
) -> DataQualityConfig:
    key = str(timeframe).strip().upper()
    gap_factor, max_gap = _GAP_RULES.get(key, (3.0, 4.0))
    updates: dict[str, Any] = {
        "gap_factor": gap_factor,
        "max_gap_hours": max_gap,
    }
    if str(symbol).upper() in NYSE_SYMBOLS:
        sources = dict(base.sources)
        sources[str(symbol).upper()] = SourceConfig(
            path="", timezone="UTC", calendar=NYSE
        )
        updates["sources"] = sources
    elif str(symbol).upper() in FX_METAL_SYMBOLS:
        sources = dict(base.sources)
        sources[str(symbol).upper()] = SourceConfig(
            path="", timezone="UTC", calendar=FX_METAL
        )
        updates["sources"] = sources
    return base.model_copy(update=updates)


def missing_weekdays(
    frame: pd.DataFrame, timeframe: str = "M5"
) -> tuple[int, list[str]]:
    """Sesiones esperadas sin ninguna barra.

    Se excluye el sábado. En D1 la etiqueta es la apertura 17:00 NY: la sesión
    del viernes se etiqueta como jueves, así que se esperan domingo-jueves. En
    las temporalidades intradía se esperan domingo-viernes.
    """
    if frame is None or len(frame) == 0:
        return 0, []
    key = str(timeframe).strip().upper()
    expected = {6, 0, 1, 2, 3} if key == "D1" else {6, 0, 1, 2, 3, 4}
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    local = index.tz_convert("America/New_York").normalize()
    present = set(local)
    days = pd.date_range(local.min(), local.max(), freq="D", tz="America/New_York")
    missing = [
        stamp for stamp in days if stamp.weekday() in expected and stamp not in present
    ]
    return len(missing), [stamp.date().isoformat() for stamp in missing[:10]]


def quality_for_source(
    symbol: str,
    timeframe: str = "M5",
    *,
    source: str = "broker",
    config: DataQualityConfig | None = None,
    root: Path = ROOT,
    segments: dict[str, tuple] | None = None,
) -> dict[str, Any]:
    """Informe de una fuente/TF; nunca descarga ni escribe."""
    source_key = normalize_source(source)
    base = config or load_engine_config().data_quality
    key = str(timeframe).strip().upper()
    try:
        loaded = load_source(
            symbol,
            key,
            source=source_key,
            config=base,
            root=root,
        )
    except DataSourceError as exc:
        return {
            "symbol": str(symbol).upper(),
            "timeframe": key,
            "status": "fail",
            "issues": [str(exc)],
            "dataset_hash": "",
            "rows": 0,
            "start": None,
            "end": None,
            "segments": {},
            "scheduled_pauses": [],
            "calendar_gaps": [],
            "non_scheduled_gaps": 0,
            "gap_thresholds": {},
            "granularity": {"useful_start": None, "bad_months": []},
            "calendar": {},
            "source": {"source": source_key, "read_only": True},
            "datacheck": {},
            "source_name": source_key,
            "missing_weekdays": 0,
            "missing_weekdays_sample": [],
        }
    qconfig = quality_config(base, symbol, key, source_key)
    report = check_dataset(
        loaded.frame,
        symbol,
        key,
        segments=segments,
        cache_path=loaded.path,
        config=qconfig,
        source=loaded.as_dict(),
        data_source=source_key,
    )
    data = report.as_dict()
    missing, sample = missing_weekdays(loaded.frame, key)
    data["source_name"] = source_key
    data["missing_weekdays"] = int(missing)
    data["missing_weekdays_sample"] = sample
    return data


def quality_matrix(
    symbol: str,
    *,
    source: str = "broker",
    config: DataQualityConfig | None = None,
    root: Path = ROOT,
    segments: dict[str, tuple] | None = None,
) -> list[dict[str, Any]]:
    return [
        quality_for_source(
            symbol,
            timeframe,
            source=source,
            config=config,
            root=root,
            segments=segments,
        )
        for timeframe in TIMEFRAMES
    ]


def all_symbols() -> tuple[str, ...]:
    return SYMBOLS


__all__ = [
    "NYSE_SYMBOLS",
    "all_symbols",
    "missing_weekdays",
    "quality_config",
    "quality_for_source",
    "quality_matrix",
]
