"""Cálculo de ``data_quality.usable_from`` por fuente, símbolo y TF (R2j-b).

Una fecha es usable si, desde ahí hasta el final:

* todos los años tienen tramo de sesión estable, o no tienen huecos reales, y
* el data-check de la historia recortada no es FAIL.

No cambia umbrales ni escribe nada salvo que el llamador lo pida.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from ..config import ROOT
from .config import DataQualityConfig, load_engine_config
from .data_quality import _gap_analysis, check_dataset
from .data_sources import load_source
from .source_quality import quality_config
from .timeframes import TIMEFRAMES, timeframe_minutes

SOURCES = ("dukascopy", "broker", "databento")
SYMBOLS = ("US100", "US500", "US30", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY")


def usable_key(source: str, symbol: str, timeframe: str) -> str:
    return (
        f"{str(source).strip().lower()}:"
        f"{str(symbol).strip().upper()}:"
        f"{str(timeframe).strip().upper()}"
    )


def _first_bar_from(frame: pd.DataFrame, year: int, pause_tz: str) -> pd.Timestamp | None:
    local = frame.index.tz_convert(pause_tz)
    subset = frame.loc[local.year >= year]
    return None if subset.empty else subset.index[0]


def compute_usable_from(
    symbol: str,
    source: str,
    timeframe: str,
    *,
    config: DataQualityConfig | None = None,
    root: Path = ROOT,
    frame: pd.DataFrame | None = None,
) -> dict:
    """Primera fecha usable de una fuente:símbolo:TF (sin escribir nada)."""
    config = config or load_engine_config().data_quality
    qconfig = quality_config(config, symbol, timeframe, source)
    if frame is None:
        frame = load_source(
            symbol, timeframe, source=source, config=config, root=root
        ).frame
    result = {
        "key": usable_key(source, symbol, timeframe),
        "source": str(source).strip().lower(),
        "symbol": str(symbol).strip().upper(),
        "timeframe": str(timeframe).strip().upper(),
        "date": None,
        "year": None,
        "status": "fail",
        "gaps": 0,
        "reason": "",
    }
    if frame is None or len(frame) == 0:
        result["reason"] = "sin datos"
        return result

    local = frame.index.tz_convert(qconfig.pause_tz)
    years = sorted({int(year) for year in local.year})
    analyzed = _gap_analysis(
        frame,
        timeframe_minutes(timeframe),
        qconfig,
        pause_tz=qconfig.pause_tz,
        calendar=qconfig.source_for(symbol).calendar,
        symbol=symbol,
        source=source,
    )
    gaps_by_year = Counter(gap["start"].year for gap in analyzed[2])

    for candidate in years:
        covered = True
        for year in years:
            if year < candidate:
                continue
            session = qconfig.session_for(source, symbol, date(year, 1, 1))
            if session is None and gaps_by_year.get(year, 0) > 0:
                covered = False
                break
        if not covered:
            continue
        first = _first_bar_from(frame, candidate, qconfig.pause_tz)
        if first is None:
            continue
        slice_frame = frame.loc[frame.index >= first]
        report = check_dataset(
            slice_frame,
            symbol,
            timeframe,
            config=qconfig,
            data_source=source,
        )
        if report.status == "fail":
            continue
        result.update(
            {
                "date": first.date().isoformat(),
                "year": candidate,
                "status": report.status,
                "gaps": report.non_scheduled_gaps,
            }
        )
        return result

    result["reason"] = "ningún año cumple"
    return result


def compute_all(
    *,
    config: DataQualityConfig | None = None,
    root: Path = ROOT,
    sources: tuple[str, ...] = SOURCES,
    symbols: tuple[str, ...] = SYMBOLS,
    timeframes: tuple[str, ...] = TIMEFRAMES,
) -> dict[str, dict]:
    config = config or load_engine_config().data_quality
    results: dict[str, dict] = {}
    for source in sources:
        for symbol in symbols:
            for timeframe in timeframes:
                key = usable_key(source, symbol, timeframe)
                try:
                    results[key] = compute_usable_from(
                        symbol,
                        source,
                        timeframe,
                        config=config,
                        root=root,
                    )
                except Exception as exc:  # noqa: BLE001
                    results[key] = {
                        "key": key,
                        "source": source,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "date": None,
                        "year": None,
                        "status": "fail",
                        "gaps": 0,
                        "reason": str(exc)[:240],
                    }
    return results


def yaml_block(results: dict[str, dict]) -> str:
    lines = ["  usable_from:"]
    rows = [
        (key, item["date"])
        for key, item in results.items()
        if item.get("date")
    ]
    for key, value in sorted(rows):
        lines.append(f'    "{key}": "{value}"')
    return "\n".join(lines)


def write_usable_from(
    results: dict[str, dict], path: str | Path | None = None
) -> Path:
    """Sustituye el bloque ``data_quality.usable_from`` conservando el resto."""
    from .config import ENGINE_PATH

    target = Path(path) if path else ENGINE_PATH
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line == "  usable_from:":
            skipping = True
            continue
        if skipping:
            if line.startswith("    "):
                continue
            skipping = False
        output.append(line)
    block = yaml_block(results).splitlines()
    output.extend(block)
    target.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    return target


__all__ = [
    "SOURCES",
    "SYMBOLS",
    "compute_all",
    "compute_usable_from",
    "usable_key",
    "write_usable_from",
    "yaml_block",
]
