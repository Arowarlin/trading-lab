"""Calidad de datos CFD para el Discovery Lab.

Reutiliza ``tradinglab.datacheck.check_frame`` (importado, no copiado) y añade:

* duplicados, OHLC inválido y huecos entre velas consecutivas;
* pausas programadas: un hueco que empieza a la misma hora:minuto UTC en al
  menos ``scheduled_gap_share`` de los días con datos se informa, no avisa;
* cobertura de los tres tramos IS / OOS-1 / OOS-2 (solo filas y rango; OOS-2
  está sellado y no se calculan métricas de rendimiento);
* hash SHA-256 estable del dataset (índice + OHLC).

No descarga datos, no llama a MT5 y no escribe archivos.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import ROOT
from .config import DataQualityConfig, load_engine_config

DEFAULT_TIMEZONE = "UTC"
DEFAULT_SEGMENTS: dict[str, tuple[str, str | None]] = {
    "is": ("2018-01-01", "2023-12-31"),
    "oos1": ("2024-01-01", "2025-06-30"),
    # El final se resuelve a la última vela disponible en caché.
    "oos2": ("2025-07-01", None),
}
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
    non_scheduled_gaps: int = 0
    gap_thresholds: dict = field(default_factory=dict)
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
            "non_scheduled_gaps": self.non_scheduled_gaps,
            "gap_thresholds": dict(self.gap_thresholds),
            "datacheck": self.datacheck,
        }


def _tf_minutes(timeframe: str) -> int:
    key = str(timeframe or "").strip().upper()
    if key in _TF_MINUTES:
        return _TF_MINUTES[key]
    aliases = {"1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30", "1H": "H1", "4H": "H4", "1D": "D1"}
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
) -> dict[str, SegmentReport]:
    last = _utc_index(frame.index)[-1]
    definition = segments or DEFAULT_SEGMENTS
    out: dict[str, SegmentReport] = {}
    for name, value in definition.items():
        start, end = _segment_range(value, last)
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
    return out


def _gap_analysis(
    frame: pd.DataFrame,
    tf_minutes: int,
    config: DataQualityConfig,
) -> tuple[list[dict], int, list[str]]:
    index = _utc_index(frame.index).sort_values()
    if len(index) < 2:
        return [], 0, []
    gaps: list[dict] = []
    threshold = float(config.gap_factor) * tf_minutes
    max_gap = float(config.max_gap_hours) * 60.0
    for previous, current in zip(index[:-1], index[1:]):
        minutes = (current - previous).total_seconds() / 60.0
        if minutes <= threshold or minutes >= max_gap:
            continue
        start = previous + pd.Timedelta(minutes=tf_minutes)
        gaps.append(
            {
                "start": start,
                "resume": current,
                "minutes": round(minutes, 2),
                "start_hhmm": start.strftime("%H:%M"),
            }
        )
    days = len({stamp.date() for stamp in index})
    counts: dict[str, int] = {}
    for gap in gaps:
        counts[gap["start_hhmm"]] = counts.get(gap["start_hhmm"], 0) + 1
    scheduled: list[dict] = []
    non_scheduled: list[dict] = []
    for gap in gaps:
        share = counts[gap["start_hhmm"]] / days if days else 0.0
        if share >= float(config.scheduled_gap_share):
            gap["share"] = round(share, 4)
            scheduled.append(gap)
        else:
            non_scheduled.append(gap)
    # Agrupa las pausas programadas por hora:minuto para el informe.
    grouped: dict[str, dict] = {}
    for gap in scheduled:
        key = gap["start_hhmm"]
        item = grouped.setdefault(
            key,
            {"start_hhmm": key, "count": 0, "share": gap["share"], "minutes": gap["minutes"]},
        )
        item["count"] += 1
    return sorted(grouped.values(), key=lambda item: item["start_hhmm"]), len(non_scheduled), non_scheduled


def check_dataset(
    frame: pd.DataFrame,
    symbol: str,
    timeframe: str = "M5",
    *,
    segments: dict[str, tuple] | None = None,
    cache_path: str | Path | None = None,
    config: DataQualityConfig | None = None,
) -> QualityReport:
    """Valida un DataFrame OHLC ya cargado. No descarga ni escribe nada."""
    config = config or load_engine_config().data_quality
    tf_minutes = _tf_minutes(timeframe)
    issues: list[str] = []
    if frame is None or len(frame) == 0:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=["Sin datos: el DataFrame está vacío"],
            gap_thresholds={
                "gap_factor": config.gap_factor,
                "max_gap_hours": config.max_gap_hours,
                "warn_if_gaps_gt": config.warn_if_gaps_gt,
                "fail_if_gap_pct_gt": config.fail_if_gap_pct_gt,
            },
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
        )

    index = _utc_index(work.index)
    work.index = index
    work = work.sort_index()

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

    segment_rows = _segments_report(work, segments, tf_minutes)
    for name, report in segment_rows.items():
        if report.rows == 0:
            issues.append(f"tramo {name}: Sin datos en el rango")
            status = "fail"

    scheduled, non_scheduled, gap_samples = _gap_analysis(work, tf_minutes, config)
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
            + ", ".join(f"{item['start_hhmm']} × {item['count']}" for item in scheduled)
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
        non_scheduled_gaps=non_scheduled,
        gap_thresholds={
            "gap_factor": config.gap_factor,
            "max_gap_hours": config.max_gap_hours,
            "warn_if_gaps_gt": config.warn_if_gaps_gt,
            "fail_if_gap_pct_gt": config.fail_if_gap_pct_gt,
            "scheduled_gap_share": config.scheduled_gap_share,
            "gap_pct": round(gap_pct, 6),
            "expected_bars": expected_bars,
            "non_scheduled_samples": [
                {
                    "start": gap["start"].isoformat(),
                    "resume": gap["resume"].isoformat(),
                    "minutes": gap["minutes"],
                }
                for gap in gap_samples[:10]
            ],
        },
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
    """Carga el parquet de caché MT5 y valida. Sin red y sin MT5."""
    from ..intraday import cache_file, load_bars

    cache = Path(cache_dir) if cache_dir else ROOT / "data" / "cache"
    path = cache_file(cache, symbol, timeframe)
    try:
        frame = load_bars(cache, symbol, timeframe)
    except FileNotFoundError:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=[f"Sin datos: no hay caché MT5 para {symbol} {timeframe} en {cache}"],
        )
    except Exception as exc:
        return QualityReport(
            symbol=str(symbol).upper(),
            timeframe=str(timeframe).upper(),
            status="fail",
            issues=[f"Sin datos: no se pudo leer la caché ({type(exc).__name__}: {exc})"],
        )
    return check_dataset(
        frame,
        symbol,
        timeframe,
        segments=segments,
        cache_path=path,
        config=config,
    )


__all__ = [
    "DEFAULT_SEGMENTS",
    "DataQualityError",
    "QualityReport",
    "SegmentReport",
    "check_dataset",
    "dataset_hash",
    "load_and_check",
]
