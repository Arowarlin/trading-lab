"""Derivación de horarios de sesión por fuente y símbolo (R2j-b).

No usa mínimos ni máximos: cada valor es la **moda semanal** del año. Si la moda
no cubre al menos el 60 % de las semanas con datos, el año se marca inestable y
queda **sin tramo**; los años estables a ambos lados no se fusionan. Un símbolo
puede escribirse con varios tramos parciales.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..config import ROOT
from .config import SessionConfig, SessionSegment
from .data_sources import load_source

INDEX_SYMBOLS = {"US100", "US500", "US30"}
STABLE_SHARE = 0.60


@dataclass
class YearSession:
    year: int
    friday_close: str | None = None
    friday_share: float | None = None
    sunday_open: str | None = None
    sunday_share: float | None = None
    pause_start: str | None = None
    pause_end: str | None = None
    pause_share: float | None = None
    short_close: str | None = None
    short_share: float | None = None
    stable: bool = True
    reasons: list[str] = field(default_factory=list)


def _mode(values: list) -> tuple:
    if not values:
        return None, None, 0
    counts = Counter(values)
    value, count = counts.most_common(1)[0]
    return value, count / len(values), len(values)


def _hhmm(stamp: pd.Timestamp) -> str:
    return stamp.strftime("%H:%M")


def _rounded(stamp: pd.Timestamp, step: int, *, floor: bool = False) -> str:
    minutes = stamp.hour * 60 + stamp.minute
    if floor:
        minutes = (minutes // step) * step
    else:
        minutes = ((minutes + step // 2) // step) * step
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _minutes(value: str | None) -> int | None:
    if value is None:
        return None
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _pause_pairs(frame: pd.DataFrame, tf_minutes: int) -> dict[pd.Timestamp, tuple[str, str]]:
    """Pausa intraday por fecha local (inicio, fin), solo huecos <= 6 h."""
    index = pd.DatetimeIndex(frame.index)
    pairs: dict[pd.Timestamp, tuple[str, str]] = {}
    for previous, current in zip(index[:-1], index[1:]):
        start = previous + pd.Timedelta(minutes=tf_minutes)
        if start.date() != current.date():
            continue
        minutes = (current - start).total_seconds() / 60.0
        if not (10 <= minutes <= 360):
            continue
        pairs[current.normalize()] = (_hhmm(start), _hhmm(current))
    return pairs


def derive_year(frame: pd.DataFrame, year: int, tf_minutes: int) -> YearSession:
    local = frame.index.tz_convert("America/New_York")
    mask_year = local.year == year
    if not mask_year.any():
        result = YearSession(year=year)
        result.stable = False
        result.reasons.append("sin datos")
        return result
    index = pd.DatetimeIndex(local[mask_year])
    close = index + pd.Timedelta(minutes=tf_minutes)
    result = YearSession(year=year)

    friday_mask = index.day_of_week == 4
    if friday_mask.any():
        last = pd.Series(
            [_rounded(stamp, 5) for stamp in close[friday_mask]],
            index=index[friday_mask].normalize(),
        ).groupby(level=0).last()
        result.friday_close, result.friday_share, _ = _mode(list(last))

    sunday_mask = index.day_of_week == 6
    if sunday_mask.any():
        first = pd.Series(
            [_rounded(stamp, 15, floor=True) for stamp in index[sunday_mask]],
            index=index[sunday_mask].normalize(),
        ).groupby(level=0).first()
        result.sunday_open, result.sunday_share, _ = _mode(list(first))

    start = index[:-1] + pd.Timedelta(minutes=tf_minutes)
    end = index[1:]
    minutes = (end - start).total_seconds().to_numpy(dtype="float64") / 60.0
    valid = (
        (start.date == end.date)
        & (minutes >= 10)
        & (minutes <= 360)
    )
    if valid.any():
        pairs = list(
            zip(
                [_rounded(stamp, 5) for stamp in start[valid]],
                [_rounded(stamp, 5) for stamp in end[valid]],
                index[1:][valid].normalize(),
            )
        )
        weekly: dict[tuple[int, int], tuple[str, str]] = {}
        for pair_start, pair_end, stamp in pairs:
            iso = pd.Timestamp(stamp).isocalendar()
            week = (int(iso.year), int(iso.week))
            current = weekly.get(week)
            if current is None:
                weekly[week] = (pair_start, pair_end)
            else:
                weekly[week] = Counter(
                    [current, (pair_start, pair_end)]
                ).most_common(1)[0][0]
        pause_values = list(weekly.values())
        starts = [item[0] for item in pause_values]
        ends = [item[1] for item in pause_values]
        start_mode, start_share, _ = _mode(starts)
        end_mode, end_share, _ = _mode(ends)
        result.pause_start = start_mode
        result.pause_end = end_mode
        shares = [value for value in (start_share, end_share) if value is not None]
        result.pause_share = min(shares) if shares else None

    short_mask = (index.month == 12) & index.day.isin([24, 31])
    if short_mask.any():
        short = pd.Series(
            [_rounded(stamp, 5) for stamp in close[short_mask]],
            index=index[short_mask].normalize(),
        ).groupby(level=0).last()
        result.short_close, result.short_share, _ = _mode(list(short))

    def _inside(value: str | None, low: int, high: int) -> bool:
        minutes = _minutes(value)
        return minutes is not None and low <= minutes <= high

    if not _inside(result.friday_close, 12 * 60, 20 * 60):
        result.friday_close = None
        result.reasons.append("cierre de viernes no plausible")
    if not _inside(result.sunday_open, 15 * 60, 20 * 60):
        result.sunday_open = None
        result.reasons.append("apertura de domingo no plausible")
    if not (
        _inside(result.pause_start, 15 * 60, 20 * 60)
        and _inside(result.pause_end, 15 * 60, 20 * 60)
        and _minutes(result.pause_start) < _minutes(result.pause_end)
    ):
        result.pause_start = None
        result.pause_end = None
        result.pause_share = None
    if not _inside(result.short_close, 11 * 60, 15 * 60):
        result.short_close = None
        result.short_share = None

    primary = [
        ("viernes", result.friday_share),
        ("domingo", result.sunday_share),
    ]
    for name, share in primary:
        if share is not None and share < STABLE_SHARE:
            result.stable = False
            result.reasons.append(f"{name} {share:.0%} < 60%")
    if result.friday_close is None or result.sunday_open is None:
        result.stable = False
        result.reasons.append("sin cierre de viernes o apertura de domingo")
    if result.pause_share is not None and result.pause_share < STABLE_SHARE:
        result.pause_start = None
        result.pause_end = None
        result.pause_share = None
        result.reasons.append("pausa no estable: se omite")
    if result.short_share is not None and result.short_share < STABLE_SHARE:
        result.short_close = None
        result.short_share = None
        result.reasons.append("sesión corta no estable: se omite")
    if (
        result.friday_close is None
        and result.sunday_open is None
        and result.pause_start is None
        and result.short_close is None
    ):
        result.stable = False
        result.reasons.append("sin valores derivables")
    return result


def build_segments(years: list[YearSession]) -> list[SessionSegment]:
    """Un tramo por bloque de años consecutivos estables con valores idénticos.

    Un año inestable corta el bloque: los años estables a ambos lados no se
    fusionan aunque sus valores coincidan. Un año estable sin pausa produce un
    tramo sin pausa; no se hereda del año vecino.
    """
    segments: list[SessionSegment] = []
    current: SessionSegment | None = None
    for year in years:
        if not year.stable:
            if current is not None:
                segments.append(current)
                current = None
            continue
        values = (
            year.friday_close,
            year.sunday_open,
            year.pause_start,
            year.pause_end,
            year.short_close,
        )
        if current is not None:
            same = (
                current.friday_close,
                current.sunday_open,
                current.pause_start,
                current.pause_end,
                current.short_close,
            ) == values
            if same:
                current = current.model_copy(update={"end": f"{year.year}-12-31"})
                continue
            segments.append(current)
        current = SessionSegment(
            start=f"{year.year}-01-01",
            end=f"{year.year}-12-31",
            friday_close=year.friday_close,
            sunday_open=year.sunday_open,
            pause_start=year.pause_start,
            pause_end=year.pause_end,
            short_close=year.short_close,
        )
    if current is not None:
        segments.append(current)
    return segments


def derive_sessions(
    symbol: str,
    source: str,
    *,
    root: Path = ROOT,
    start_year: int | None = None,
    end_year: int = 2026,
) -> dict:
    key = str(symbol).strip().upper()
    source_key = str(source).strip().lower()
    if source_key not in {"dukascopy", "broker", "databento"}:
        raise ValueError(f"fuente no soportada: {source}")
    if start_year is None:
        start_year = 2010 if source_key == "databento" else 2013 if key in INDEX_SYMBOLS else 2003
    timeframe = (
        "M1" if source_key == "dukascopy" else "H1" if source_key == "databento" else "M5"
    )
    loaded = load_source(key, timeframe, source=source_key, root=root)
    tf_minutes = {"M1": 1, "M5": 5, "H1": 60}[timeframe]
    years = [
        derive_year(loaded.frame, year, tf_minutes)
        for year in range(start_year, end_year + 1)
    ]
    if source_key == "broker":
        local = loaded.frame.index.tz_convert("America/New_York")
        partial = {
            year
            for year in range(start_year, end_year + 1)
            if len({stamp.date() for stamp in local[local.year == year]}) < 200
        }
        years = [year for year in years if year.year not in partial]
    all_stable = bool(years) and all(
        year.stable for year in years if year.reasons != ["sin datos"]
    )
    segments = build_segments(years)
    stable = bool(segments)
    return {
        "symbol": key,
        "source": source_key,
        "timeframe": timeframe,
        "years": years,
        "stable": stable,
        "all_stable": all_stable,
        "unstable_years": [
            year.year
            for year in years
            if not year.stable and year.reasons != ["sin datos"]
        ],
        "segments": segments,
    }


def yaml_block(result: dict) -> str:
    """YAML de ``data_quality.sessions`` para pegar tal cual."""
    if not result["segments"]:
        return f"# {result['source']}:{result['symbol']} SIN TRAMOS ESTABLES"
    lines = [f'  "{result["source"]}:{result["symbol"]}":', "    segments:"]
    for segment in result["segments"]:
        lines.append(f'      - start: "{segment.start}"')
        lines.append(f'        end: "{segment.end}"')
        for field_name in (
            "friday_close",
            "sunday_open",
            "pause_start",
            "pause_end",
            "short_close",
        ):
            value = getattr(segment, field_name)
            lines.append(
                f"        {field_name}: "
                + ("null" if value is None else f'"{value}"')
            )
    return "\n".join(lines)


def session_config(result: dict) -> SessionConfig | None:
    if not result["segments"]:
        return None
    return SessionConfig(segments=result["segments"])


__all__ = [
    "INDEX_SYMBOLS",
    "STABLE_SHARE",
    "YearSession",
    "build_segments",
    "derive_sessions",
    "derive_year",
    "session_config",
    "yaml_block",
]
