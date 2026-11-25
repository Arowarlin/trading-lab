"""TL3 · Manifiesto de datos y cargador con comprobaciones."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT

CACHE = ROOT / "data" / "cache"
OUTPUT = ROOT / "data" / "tl3"
MANIFEST = OUTPUT / "manifest.json"
REPORT = ROOT / "TL3_REPORTS" / "data_manifest.md"
NOMINAL = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}
ROOT_TO_FUTURE = {
    "US100": "NQ.c.0",
    "US500": "ES.c.0",
    "US30": "YM.c.0",
    "XAUUSD": "GC.c.0",
    "EURUSD": "6E.c.0",
    "GBPUSD": "6B.c.0",
    "USDJPY": "6J.c.0",
}
FUTURE_ROOTS = set(ROOT_TO_FUTURE)


class TL3DataError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileInfo:
    path: str
    source: str
    instrument_real: str
    instrument_class: str
    timeframe: str
    rows: int
    has_ask: float
    usable_from: int | None
    dominant_step_by_year: dict[str, float]
    sha256: str


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timeframe(path: Path) -> str:
    stem = path.stem.upper()
    for key in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        if f"_{key}" in stem or stem.endswith(key):
            return key
    return ""


def _class_and_instrument(path: Path) -> tuple[str, str]:
    relative = path.relative_to(CACHE).as_posix()
    stem = path.stem
    if relative.startswith("databento/"):
        internal = stem.split("_")[0].upper()
        return "future", ROOT_TO_FUTURE.get(internal, f"{internal}.c.0")
    if relative.startswith("ea/"):
        symbol = stem.replace("_CASH_", "|").split("|")[0]
        return "cfd", f"{symbol}.cash"
    if relative.startswith("dukascopy/"):
        symbol = stem.split("_")[0].upper()
        if symbol == "US100":
            return "cfd", "Dukascopy USATECHIDXUSD"
        return "cfd", f"Dukascopy {symbol}"
    if relative.startswith("mt5/"):
        return "cfd", f"MT5 {stem}"
    return "cfd", stem


def _dominant_by_year(index: pd.DatetimeIndex) -> dict[str, float]:
    if len(index) < 2:
        return {}
    stamps = pd.Series(index)
    deltas = stamps.diff().dt.total_seconds().dropna()
    years = stamps.iloc[1:].dt.year.to_numpy()
    out: dict[str, float] = {}
    for year in sorted(set(years)):
        values = deltas[years == year]
        if values.empty:
            continue
        mode = values.mode()
        out[str(int(year))] = float(mode.iloc[0] if not mode.empty else values.median())
    return out


def _has_ask(frame: pd.DataFrame) -> float:
    columns = [column for column in frame.columns if column.startswith("ask_")]
    if not columns:
        return 0.0
    return float(frame[columns].notna().all(axis=1).mean())


def _info(path: Path) -> FileInfo:
    frame = pd.read_parquet(path)
    index = pd.DatetimeIndex(frame.index)
    timeframe = _timeframe(path)
    nominal = NOMINAL.get(timeframe)
    by_year = _dominant_by_year(index)
    usable = None
    if nominal is not None:
        for year, step in by_year.items():
            if abs(step - nominal) <= max(1.0, nominal * 0.05):
                usable = int(year)
                break
    instrument_class, instrument = _class_and_instrument(path)
    return FileInfo(
        path=path.relative_to(ROOT).as_posix(),
        source=path.parent.name,
        instrument_real=instrument,
        instrument_class=instrument_class,
        timeframe=timeframe,
        rows=int(len(frame)),
        has_ask=_has_ask(frame),
        usable_from=usable,
        dominant_step_by_year=by_year,
        sha256=_hash(path),
    )


def build_manifest() -> dict[str, Any]:
    files = []
    for directory in ("ea", "dukascopy", "databento", "mt5"):
        base = CACHE / directory
        if not base.exists():
            continue
        for path in sorted(base.glob("*.parquet")):
            files.append(_info(path).__dict__)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache": CACHE.relative_to(ROOT).as_posix(),
        "files": files,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    lines = [
        "# TL3 · Manifiesto de datos",
        "",
        "| Archivo | Instrumento | Clase | TF | Filas | ASK | usable_from |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for item in files:
        lines.append(
            f"| {item['path']} | {item['instrument_real']} | "
            f"{item['instrument_class']} | {item['timeframe']} | "
            f"{item['rows']} | {item['has_ask']:.2%} | "
            f"{item['usable_from'] if item['usable_from'] is not None else 'Sin datos'} |"
        )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def _manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        return build_manifest()
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def dominant_step(index: pd.DatetimeIndex) -> float | None:
    if len(index) < 2:
        return None
    deltas = pd.Series(index).diff().dt.total_seconds().dropna()
    if deltas.empty:
        return None
    mode = deltas.mode()
    return float(mode.iloc[0] if not mode.empty else deltas.median())


def load(
    path: str | Path,
    timeframe: str,
    start: str | None,
    end: str | None,
    instrument_class: str,
) -> pd.DataFrame:
    """Carga una ventana y falla si la granularidad o la clase no coinciden."""

    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    relative = target.relative_to(ROOT).as_posix()
    files = _manifest()["files"]
    entry = next((item for item in files if item["path"] == relative), None)
    if entry is None:
        matches = [item for item in files if item["path"].endswith(target.name)]
        entry = matches[0] if len(matches) == 1 else None
    if entry is None:
        raise TL3DataError(f"Sin datos: {path} no está en el manifiesto")
    if entry["instrument_class"] != instrument_class:
        raise TL3DataError(
            f"Sin datos: {path} es {entry['instrument_class']}, "
            f"no {instrument_class}"
        )
    frame = pd.read_parquet(target)
    index = pd.DatetimeIndex(frame.index)
    if start:
        start_ts = pd.Timestamp(start)
        if index.tz is not None and start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize(index.tz)
        elif index.tz is None and start_ts.tzinfo is not None:
            start_ts = start_ts.tz_convert(None)
        frame = frame.loc[start_ts:]
    if end:
        end_ts = pd.Timestamp(end)
        if index.tz is not None and end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(index.tz)
        elif index.tz is None and end_ts.tzinfo is not None:
            end_ts = end_ts.tz_convert(None)
        frame = frame.loc[:end_ts]
    if frame.empty:
        raise TL3DataError(f"Sin datos: ventana vacía en {path}")
    nominal = NOMINAL.get(str(timeframe).upper())
    actual = dominant_step(pd.DatetimeIndex(frame.index))
    if nominal is None or actual is None:
        raise TL3DataError(f"Sin datos: granularidad de {path}")
    if abs(actual - nominal) > max(1.0, nominal * 0.05):
        raise TL3DataError(
            f"Sin datos: granularidad {actual:.0f}s no coincide con {timeframe}"
        )
    return frame


__all__ = [
    "CACHE",
    "MANIFEST",
    "REPORT",
    "TL3DataError",
    "build_manifest",
    "dominant_step",
    "load",
]
