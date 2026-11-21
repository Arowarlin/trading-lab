"""Fuentes de datos del Discovery Lab: solo lectura, sin MT5 ni red.

* ``US100.cash`` se lee de la caché del EA (``data/cache/ea/...``), **nunca se
  escribe ni se refresca**. Su índice es hora de Nueva York sin zona; se
  localiza en ``America/New_York`` y se convierte a UTC.
* Los símbolos descargados por ``discovery fetch`` se leen primero de
  ``data/cache/discovery/<SYMBOL>_<TF>.parquet`` (UTC).
* El resto usa ``data/cache/mt5/<SYMBOL>_<TF>.parquet`` (o el mapa
  ``data_quality.sources`` de ``config/discovery/engine.yaml``).
* Los timestamps ambiguos o inexistentes nunca se inventan: se eligen con
  ``ambiguous="infer"`` cuando es posible y los inexistentes se descartan,
  informando cuántos se ajustaron/descartaron.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import ROOT
from .config import DataQualityConfig, SourceConfig, load_engine_config

DATA_SOURCES = ("broker", "dukascopy")


class DataSourceError(RuntimeError):
    pass


def normalize_source(value: str | None) -> str:
    key = str(value or "broker").strip().lower()
    if key not in DATA_SOURCES:
        raise DataSourceError(
            f"fuente no soportada: {value!r}; usa una de: {', '.join(DATA_SOURCES)}"
        )
    return key


@dataclass(frozen=True)
class LoadedSource:
    symbol: str
    timeframe: str
    path: str
    timezone: str
    calendar: str | None
    rows_raw: int
    rows: int
    adjusted: int
    dropped: int
    frame: pd.DataFrame = field(repr=False, compare=False)
    source: str = "broker"
    derived_from: str | None = None

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "timezone": self.timezone,
            "calendar": self.calendar,
            "rows_raw": self.rows_raw,
            "rows": self.rows,
            "adjusted": self.adjusted,
            "dropped": self.dropped,
            "source": self.source,
            "derived_from": self.derived_from,
            "read_only": True,
        }


def _safe_symbol(symbol: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(symbol)).upper()


def resolve_path(spec: SourceConfig, symbol: str, timeframe: str, *, root: Path = ROOT) -> Path:
    raw = spec.path.format(
        symbol=_safe_symbol(symbol),
        tf=str(timeframe).upper(),
    )
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _localize(index: pd.DatetimeIndex, timezone: str) -> tuple[pd.DatetimeIndex, int, int]:
    """Localiza un índice naive sin inventar velas. Devuelve (índice, ajustados, descartados)."""
    if index.tz is not None:
        return index.tz_convert(timezone), 0, 0
    probe = index.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT")
    special = int(probe.isna().sum())
    try:
        localized = index.tz_localize(timezone, ambiguous="infer", nonexistent="NaT")
    except Exception:
        localized = index.tz_localize(timezone, ambiguous=False, nonexistent="NaT")
    dropped = int(localized.isna().sum())
    adjusted = max(0, special - dropped)
    return localized, adjusted, dropped


def load_source(
    symbol: str,
    timeframe: str = "M5",
    *,
    source: str = "broker",
    config: DataQualityConfig | None = None,
    root: Path = ROOT,
) -> LoadedSource:
    """Carga una fuente configurada y la devuelve en UTC. Nunca escribe."""
    source_key = normalize_source(source)
    config = config or load_engine_config().data_quality
    spec = config.source_for(symbol)
    if source_key == "dukascopy":
        from .fetch_dukascopy import cache_path as dukascopy_path
        from .fetch_dukascopy import load_cache as load_dukascopy
        from .resample import resample_session

        path = dukascopy_path(symbol, root=root)
        if not path.exists():
            raise DataSourceError(f"Sin datos: no existe {path}")
        try:
            m1 = load_dukascopy(symbol, root=root)
        except Exception as exc:  # noqa: BLE001
            raise DataSourceError(str(exc)) from exc
        frame = (
            m1
            if str(timeframe).upper() == "M1"
            else resample_session(m1, timeframe)
        )
        calendar = spec.calendar
        if str(symbol).upper() in {"US100", "US500", "US30"}:
            calendar = "nyse"
        path_text = (
            path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        )
        return LoadedSource(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            path=path_text,
            timezone="UTC",
            calendar=calendar,
            rows_raw=int(len(m1)),
            rows=int(len(frame)),
            adjusted=0,
            dropped=0,
            frame=frame,
            source="dukascopy",
            derived_from="M1" if str(timeframe).upper() != "M1" else None,
        )
    discovery = (
        root
        / "data"
        / "cache"
        / "discovery"
        / f"{_safe_symbol(symbol)}_{str(timeframe).upper()}.parquet"
    )
    if discovery.exists():
        spec = spec.model_copy(
            update={"path": str(discovery), "timezone": "UTC"}
        )
    path = resolve_path(spec, symbol, timeframe, root=root)
    if not path.exists():
        raise DataSourceError(f"Sin datos: no existe {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise DataSourceError(
            f"Sin datos: no se pudo leer {path} ({type(exc).__name__}: {exc})"
        ) from exc
    frame = frame.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    rows_raw = int(len(frame))
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    localized, adjusted, dropped = _localize(index, spec.timezone)
    mask = ~localized.isna()
    frame = frame.loc[mask]
    frame.index = localized[mask]
    frame.index.name = "ts"
    frame = frame.sort_index()
    utc = frame.copy()
    utc.index = utc.index.tz_convert("UTC")
    return LoadedSource(
        symbol=str(symbol).upper(),
        timeframe=str(timeframe).upper(),
        path=path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path),
        timezone=spec.timezone,
        calendar=spec.calendar,
        rows_raw=int(rows_raw),
        rows=int(len(utc)),
        adjusted=int(adjusted),
        dropped=int(dropped),
        frame=utc,
        source="broker",
    )


__all__ = [
    "DATA_SOURCES",
    "DataSourceError",
    "LoadedSource",
    "load_source",
    "normalize_source",
    "resolve_path",
]
