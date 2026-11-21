"""Calidad de datos CFD para el Discovery Lab.

Reglas (Fase 1b):

* **Granularidad homogénea:** la mediana del intervalo de cada mes debe ser el
  timeframe. Se informa el ``inicio útil`` (primer mes desde el que todos los
  meses siguientes son homogéneos) y los datos anteriores no se usan.
* **Pausa programada en hora del servidor:** la recurrencia ≥ 20 % se calcula
  sobre ``HH:MM`` en ``data_quality.pause_tz`` (America/New_York para FTMO), no
  en UTC ni en la zona de trading del instrumento. Una pausa a las 16:50 NY que
  en UTC alterna 20:50/21:50 es la misma.
* **Festivos/cierres tempranos:** para índices de EE. UU. se importa
  ``tradinglab.nyse_calendar``; los huecos en esas fechas son informativos y no
  cuentan. Fuera de su cobertura (2021-2027) se avisa "sin calendario".
* **Tramos:** se leen de ``data_quality.default_segments``; OOS-2 termina en la
  última vela disponible y está sellado (solo filas/rango/cobertura).

No descarga datos, no llama a MT5 y no escribe archivos.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import DataQualityConfig, load_engine_config
from .data_sources import DataSourceError, load_source

DEFAULT_TIMEZONE = "UTC"
SEALED_SEGMENTS = {"oos2"}

_TF_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}
_OHLC = ("open", "high", "low", "close")
_CALENDAR_COVERAGE = (2021, 2027)


class DataQualityError(ValueError):
    pass


@dataclass(frozen=True)
class SegmentReport:
    name: str
    rows: int
    start: str | None
    end: str | None
    expected_rows: int | None
    coverage_pct: float | None
    sealed: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "start": self.start,
            "end": self.end,
            "expected_rows": self.expected_rows,
            "coverage_pct": self.coverage_pct,
            "sealed": self.sealed,
            "note": self.note,
        }


@dataclass(frozen=True)
class QualityReport:
    symbol: str
    timeframe: str
    status: str
    issues: list[str] = field(default_factory=list)
    dataset_hash: str = ""
    rows: int = 0
    start: str | None = None
    end: str | None = None
    segments: dict[str, SegmentReport] = field(default_factory=dict)
    scheduled_pauses: list[dict] = field(default_factory=list)
    calendar_gaps: list[dict] = field(default_factory=list)
    non_scheduled_gaps: int = 0
    gap_thresholds: dict = field(default_factory=dict)
    granularity: dict = field(default_factory=dict)
    calendar: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)
    datacheck: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "status": self.status,
            "issues": list(self.issues),
            "dataset_hash": self.dataset_hash,
            "rows": self.rows,
            "start": self.start,
            "end": self.end,
            "segments": {key: value.as_dict() for key, value in self.segments.items()},
            "scheduled_pauses": list(self.scheduled_pauses),
            "calendar_gaps": list(self.calendar_gaps),
            "non_scheduled_gaps": self.non_scheduled_gaps,
            "gap_thresholds": dict(self.gap_thresholds),
            "granularity": dict(self.granularity),
            "calendar": dict(self.calendar),
            "source": dict(self.source),
            "datacheck": self.datacheck,
        }


def _tf_minutes(timeframe: str) -> int:
    key = str(timeframe or "").strip().upper()
    if key in _TF_MINUTES:
        return _TF_MINUTES[key]
    aliases = {
        "1M": "M1",
        "5M": "M5",
        "15M": "M15",
        "30M": "M30",
        "1H": "H1",
        "4H": "H4",
        "1D": "D1",
    }
    key = aliases.get(key, key)
    if key in _TF_MINUTES:
        return _TF_MINUTES[key]
    raise DataQualityError(f"timeframe no soportado: {timeframe}")


def _utc_index(index: pd.Index) -> pd.DatetimeIndex:
    try:
        dt = pd.DatetimeIndex(pd.to_datetime(index))
    except Exception as exc:
        raise DataQualityError("índice temporal inválido") from exc
    if dt.tz is None:
        dt = dt.tz_localize(DEFAULT_TIMEZONE)
    else:
        dt = dt.tz_convert(DEFAULT_TIMEZONE)
    return dt


def dataset_hash(frame: pd.DataFrame) -> str:
    """SHA-256 estable del índice y las columnas OHLC (sin importar el orden)."""
    missing = [column for column in _OHLC if column not in frame.columns]
    if missing:
        raise DataQualityError(f"faltan columnas OHLC: {', '.join(missing)}")
    ordered = frame.loc[:, list(_OHLC)].copy()
    ordered.index = _utc_index(frame.index)
    ordered = ordered.sort_index()
    digest = hashlib.sha256()
    digest.update(b"tradinglab.discovery.dataset.v1\n")
    digest.update("\n".join(ts.isoformat() for ts in ordered.index).encode("utf-8"))
    digest.update(b"\n")
    for column in _OHLC:
        digest.update(column.encode("ascii") + b":")
        values = np.asarray(ordered[column], dtype="<f8")
        digest.update(values.tobytes())
    return digest.hexdigest()


def _granularity(index: pd.DatetimeIndex, tf_minutes: int) -> dict:
    """Mediana por mes y primer mes desde el que todos los siguientes son homogéneos."""
    if len(index) == 0:
        return {
            "raw_rows": 0,
            "raw_start": None,
            "raw_end": None,
            "useful_start": None,
            "bad_months": [],
        }
    series = pd.Series(index, index=index)
    months: list[dict] = []
    for period, group in series.groupby(series.index.strftime("%Y-%m")):
        stamps = pd.DatetimeIndex(group)
        if len(stamps) < 2:
            median = None
        else:
            median = (
                pd.Series(stamps).diff().dt.total_seconds().div(60).median()
            )
        # Un mes con una sola barra es un borde de la serie (p. ej. la sesión
        # D1 que empieza el último día del mes anterior); no se puede evaluar
        # su granularidad y no debe invalidar los meses anteriores.
        good = (
            len(stamps) == 1
            or (median is not None and abs(float(median) - tf_minutes) < 0.5)
        )
        months.append(
            {
                "month": str(period),
                "rows": len(stamps),
                "median_minutes": None if median is None else round(float(median), 3),
                "ok": good,
                "first": stamps[0],
            }
        )
    last_bad = -1
    for position, item in enumerate(months):
        if not item["ok"]:
            last_bad = position
    useful = months[last_bad + 1]["first"] if last_bad + 1 < len(months) else None
    return {
        "raw_rows": int(len(index)),
        "raw_start": index[0].isoformat(),
        "raw_end": index[-1].isoformat(),
        "useful_start": useful.isoformat() if useful is not None else None,
        "bad_months": [
            {
                "month": item["month"],
                "rows": item["rows"],
                "median_minutes": item["median_minutes"],
            }
            for item in months
            if not item["ok"]
        ],
    }


def _segment_range(value: Any, last: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise DataQualityError("cada tramo debe ser (inicio, fin)")
    start_raw, end_raw = value
    start = pd.Timestamp(start_raw, tz=DEFAULT_TIMEZONE) if start_raw else last
    if end_raw:
        end = pd.Timestamp(end_raw, tz=DEFAULT_TIMEZONE)
        if len(str(end_raw)) == 10:
            end = end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    else:
        end = last
    if end < start and end_raw:
        raise DataQualityError(f"tramo inválido: fin {end} < inicio {start}")
    return start, end


def _expected_bars(index: pd.DatetimeIndex, tf_minutes: int) -> int:
    """Velas esperadas sumando el tramo diario observado (sin noches/fines de semana)."""
    if len(index) == 0:
        return 0
    series = pd.Series(index, index=index)
    total = 0
    for _, group in series.groupby(series.index.date):
        stamps = pd.DatetimeIndex(group)
        total += int((stamps[-1] - stamps[0]).total_seconds() / 60.0 // tf_minutes) + 1
    return max(total, len(index))


def _segments_report(
    frame: pd.DataFrame,
    segments: dict[str, tuple] | None,
    tf_minutes: int,
    *,
    config: DataQualityConfig,
    useful_start: pd.Timestamp | None,
) -> tuple[dict[str, SegmentReport], list[str]]:
    last = _utc_index(frame.index)[-1]
    definition = segments or config.default_segments
    out: dict[str, SegmentReport] = {}
    issues: list[str] = []
    for name, value in definition.items():
        start, end = _segment_range(value, last)
        if useful_start is not None and start.date() < useful_start.date():
            issues.append(
                f"tramo {name} empieza antes del inicio útil "
                f"({start.date()} < {useful_start.date()})"
            )
        subset = frame.loc[(frame.index >= start) & (frame.index <= end)]
        rows = int(len(subset))
        expected = _expected_bars(pd.DatetimeIndex(subset.index), tf_minutes) if rows else 0
        coverage = (rows / expected * 100.0) if expected else None
        out[str(name)] = SegmentReport(
            name=str(name),
            rows=rows,
            start=subset.index[0].isoformat() if rows else None,
            end=subset.index[-1].isoformat() if rows else None,
            expected_rows=expected,
            coverage_pct=round(coverage, 2) if coverage is not None else None,
            sealed=str(name) in SEALED_SEGMENTS,
            note="sellado: solo cobertura, sin métricas de rendimiento"
            if str(name) in SEALED_SEGMENTS
            else "",
        )
    return out, issues


def _calendar_module() -> tuple[dict[int, str], dict[int, int]] | None:
    try:
        from ..nyse_calendar import EARLY_CLOSES, FULL_HOLIDAYS

        return FULL_HOLIDAYS, EARLY_CLOSES
    except Exception:
        return None


def _gap_analysis(
    frame: pd.DataFrame,
    tf_minutes: int,
    config: DataQualityConfig,
    *,
    pause_tz: str,
    calendar: str | None,
) -> tuple[list[dict], int, list[dict], list[dict], int]:
    index = _utc_index(frame.index).sort_values()
    if len(index) < 2:
        return [], 0, [], [], 0
    local_index = index.tz_convert(ZoneInfo(pause_tz))
    gaps: list[dict] = []
    threshold = float(config.gap_factor) * tf_minutes
    max_gap = float(config.max_gap_hours) * 60.0
    for previous, current in zip(index[:-1], index[1:]):
        minutes = (current - previous).total_seconds() / 60.0
        if minutes <= threshold or minutes >= max_gap:
            continue
        start = previous + pd.Timedelta(minutes=tf_minutes)
        local_start = start.tz_convert(ZoneInfo(pause_tz))
        gaps.append(
            {
                "start": local_start,
                "start_utc": start,
                "resume": current.tz_convert(ZoneInfo(pause_tz)),
                "resume_utc": current,
                "minutes": round(minutes, 2),
                "hhmm": local_start.strftime("%H:%M"),
            }
        )
    days = len({stamp.date() for stamp in local_index})
    counts: dict[str, int] = {}
    for gap in gaps:
        counts[gap["hhmm"]] = counts.get(gap["hhmm"], 0) + 1

    calendar_data = _calendar_module() if calendar == "nyse" else None
    scheduled: list[dict] = []
    non_scheduled: list[dict] = []
    calendar_gaps: list[dict] = []
    outside_calendar = 0
    for gap in gaps:
        share = counts[gap["hhmm"]] / days if days else 0.0
        if share >= float(config.scheduled_gap_share):
            gap["share"] = round(share, 4)
            scheduled.append(gap)
            continue
        day = int(gap["start"].strftime("%Y%m%d"))
        if calendar_data is not None:
            full, early = calendar_data
            year = gap["start"].year
            if not (_CALENDAR_COVERAGE[0] <= year <= _CALENDAR_COVERAGE[1]):
                outside_calendar += 1
                non_scheduled.append(gap)
                continue
            if day in full:
                gap["reason"] = full[day]
                calendar_gaps.append(gap)
                continue
            if day in early:
                gap["reason"] = f"cierre temprano {early[day]:04d}"
                calendar_gaps.append(gap)
                continue
        non_scheduled.append(gap)
    grouped: dict[str, dict] = {}
    for gap in scheduled:
        key = gap["hhmm"]
        item = grouped.setdefault(
            key,
            {"start_hhmm": key, "count": 0, "share": gap["share"], "minutes": gap["minutes"]},
        )
        item["count"] += 1
    return (
        sorted(grouped.values(), key=lambda item: item["start_hhmm"]),
        len(non_scheduled),
        non_scheduled,
        [
            {
                "start": item["start"].isoformat(),
                "resume": item["resume"].isoformat(),
                "minutes": item["minutes"],
                "reason": item.get("reason") or "",
            }
            for item in calendar_gaps
        ],
        outside_calendar,
    )


def check_dataset(
    frame: pd.DataFrame,
    symbol: str,
    timeframe: str = "M5",
    *,
    segments: dict[str, tuple] | None = None,
    cache_path: str | Path | None = None,
    config: DataQualityConfig | None = None,
    source: dict | None = None,
) -> QualityReport:
    """Valida un DataFrame OHLC ya cargado. No descarga ni escribe nada."""
    config = config or load_engine_config().data_quality
    tf_minutes = _tf_minutes(timeframe)
    session_tz = config.tz_for(symbol)
    pause_tz = config.pause_tz
    issues: list[str] = []
    if frame is None or len(frame) == 0:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=["Sin datos: el DataFrame está vacío"],
            granularity={"useful_start": None, "bad_months": []},
            calendar={"name": config.source_for(symbol).calendar},
            source=source or {},
        )

    work = frame.copy()
    work.columns = [str(column).lower() for column in work.columns]
    missing = [column for column in _OHLC if column not in work.columns]
    if missing:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=[f"faltan columnas OHLC: {', '.join(missing)}"],
            calendar={"name": config.source_for(symbol).calendar},
            source=source or {},
        )

    index = _utc_index(work.index)
    work.index = index
    work = work.sort_index()

    granularity = _granularity(index, tf_minutes)
    useful_start = (
        pd.Timestamp(granularity["useful_start"]) if granularity.get("useful_start") else None
    )
    if useful_start is None:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=["granularidad incorrecta en todos los meses; no hay inicio útil"],
            rows=int(len(work)),
            start=index[0].isoformat() if len(index) else None,
            end=index[-1].isoformat() if len(index) else None,
            granularity=granularity,
            calendar={"name": config.source_for(symbol).calendar},
            source=source or {},
        )
    if granularity["bad_months"]:
        issues.append(
            f"granularidad incorrecta en {len(granularity['bad_months'])} meses; "
            f"inicio útil {useful_start.date()}"
        )
    work = work.loc[work.index >= useful_start]
    index = pd.DatetimeIndex(work.index)
    if len(work) == 0:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=["Sin datos desde el inicio útil"],
            granularity=granularity,
            calendar={"name": config.source_for(symbol).calendar},
            source=source or {},
        )

    duplicates = int(index.duplicated().sum())
    if duplicates:
        issues.append(f"duplicados: {duplicates} timestamps repetidos")
        status = "fail"
    else:
        status = "ok"

    high = pd.to_numeric(work["high"], errors="coerce")
    low = pd.to_numeric(work["low"], errors="coerce")
    open_ = pd.to_numeric(work["open"], errors="coerce")
    close = pd.to_numeric(work["close"], errors="coerce")
    invalid = (
        high.isna()
        | low.isna()
        | open_.isna()
        | close.isna()
        | (high < low)
        | (high < open_)
        | (high < close)
        | (low > open_)
        | (low > close)
        | (open_ <= 0)
        | (high <= 0)
        | (low <= 0)
        | (close <= 0)
    )
    invalid_rows = int(invalid.sum())
    if invalid_rows:
        issues.append(f"OHLC inválido: {invalid_rows} velas")
        status = "fail"

    try:
        digest = dataset_hash(work)
    except DataQualityError as exc:
        issues.append(str(exc))
        digest = ""
        status = "fail"

    segment_rows, segment_issues = _segments_report(
        work,
        segments,
        tf_minutes,
        config=config,
        useful_start=useful_start,
    )
    if segment_issues:
        issues.extend(segment_issues)
        status = "fail"
    for name, report in segment_rows.items():
        if report.rows == 0:
            issues.append(f"tramo {name}: Sin datos en el rango")
            status = "fail"

    calendar_name = config.source_for(symbol).calendar
    scheduled, non_scheduled, gap_samples, calendar_gaps, outside_calendar = _gap_analysis(
        work,
        tf_minutes,
        config,
        pause_tz=pause_tz,
        calendar=calendar_name,
    )
    if calendar_name is None:
        issues.append("sin calendario: festivos no verificables (no se inventan fechas)")
        if status == "ok":
            status = "warn"
    if outside_calendar:
        issues.append(
            f"sin calendario: {outside_calendar} huecos fuera de "
            f"{_CALENDAR_COVERAGE[0]}-{_CALENDAR_COVERAGE[1]}"
        )
        if status == "ok":
            status = "warn"
    expected_bars = _expected_bars(index, tf_minutes)
    gap_pct = (non_scheduled / expected_bars) if expected_bars else 0.0
    if non_scheduled > config.warn_if_gaps_gt:
        issues.append(
            f"huecos no programados: {non_scheduled} "
            f"({gap_pct:.3%} de {expected_bars} velas esperadas)"
        )
        if gap_pct > config.fail_if_gap_pct_gt:
            status = "fail"
        elif status == "ok":
            status = "warn"
    if scheduled:
        issues.append(
            "pausas programadas (informativas): "
            + ", ".join(f"{item['start_hhmm']} local × {item['count']}" for item in scheduled)
        )
    if calendar_gaps:
        issues.append(
            f"huecos en festivos/cierres tempranos (informativos): {len(calendar_gaps)}"
        )

    try:
        from ..datacheck import check_frame

        datacheck = check_frame(
            work,
            symbol,
            timeframe=timeframe,
            cache_path=cache_path,
        )
    except Exception as exc:  # datacheck no debe romper el informe
        datacheck = {"status": "sin datos", "error": str(exc)[:240]}

    return QualityReport(
        symbol=str(symbol).upper(),
        timeframe=str(timeframe).upper(),
        status=status,
        issues=issues,
        dataset_hash=digest,
        rows=int(len(work)),
        start=index[0].isoformat() if len(index) else None,
        end=index[-1].isoformat() if len(index) else None,
        segments=segment_rows,
        scheduled_pauses=scheduled,
        calendar_gaps=calendar_gaps,
        non_scheduled_gaps=non_scheduled,
        gap_thresholds={
            "gap_factor": config.gap_factor,
            "max_gap_hours": config.max_gap_hours,
            "warn_if_gaps_gt": config.warn_if_gaps_gt,
            "fail_if_gap_pct_gt": config.fail_if_gap_pct_gt,
            "scheduled_gap_share": config.scheduled_gap_share,
            "session_tz": session_tz,
            "pause_tz": pause_tz,
            "gap_pct": round(gap_pct, 6),
            "expected_bars": expected_bars,
            "non_scheduled_samples": [
                {
                    "start": gap["start_utc"].isoformat(),
                    "start_local": gap["start"].isoformat(),
                    "resume": gap["resume_utc"].isoformat(),
                    "minutes": gap["minutes"],
                }
                for gap in gap_samples[:10]
            ],
        },
        granularity=granularity,
        calendar={
            "name": calendar_name,
            "coverage": list(_CALENDAR_COVERAGE) if calendar_name == "nyse" else None,
            "gaps": len(calendar_gaps),
            "note": "sin calendario" if calendar_name is None else "",
        },
        source=source or {},
        datacheck=datacheck,
    )


def load_and_check(
    symbol: str,
    timeframe: str = "M5",
    *,
    segments: dict[str, tuple] | None = None,
    cache_dir: str | Path | None = None,
    config: DataQualityConfig | None = None,
) -> QualityReport:
    """Carga la fuente configurada (solo lectura) y valida. Sin MT5 ni red."""
    config = config or load_engine_config().data_quality
    if cache_dir is not None:
        # Compatibilidad: si se pasa cache_dir, se usa el path MT5 estándar.
        from .data_sources import SourceConfig

        source_config = config.model_copy(
            update={
                "sources": {
                    **config.sources,
                    "default": SourceConfig(
                        path=str(Path(cache_dir) / "mt5" / "{symbol}_{tf}.parquet"),
                        timezone="UTC",
                        calendar=None,
                    ),
                }
            }
        )
        config = source_config
    try:
        loaded = load_source(symbol, timeframe, config=config)
    except DataSourceError as exc:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=[str(exc)],
            source={"read_only": True},
        )
    report = check_dataset(
        loaded.frame,
        symbol,
        timeframe,
        segments=segments,
        cache_path=loaded.path,
        config=config,
        source=loaded.as_dict(),
    )
    return report


__all__ = [
    "DataQualityError",
    "QualityReport",
    "SegmentReport",
    "check_dataset",
    "dataset_hash",
    "load_and_check",
]
