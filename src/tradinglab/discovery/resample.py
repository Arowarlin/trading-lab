"""Remuestreo único de M1 a M5/M15/M30/H1/H4/D1 con sesión de Nueva York.

La sesión FX/CFD empieza a las **17:00 America/New_York**. Cada vela origen se
asigna a la sesión que contiene su apertura y, dentro de ella, a una rejilla
anclada en ese instante. Por eso H4 y D1 cortan a las 17:00 NY y los cambios de
hora no desplazan la rejilla de un día a otro.

No se reindexa ni se rellena: si faltan minutos, faltan velas. La etiqueta de
cada vela es su apertura; su cierre es ``etiqueta + timeframe``. Ninguna vela
agregada usa minutos posteriores a ese cierre.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
_TF_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}
_NY = "America/New_York"
_CUT_HOUR = 17


class ResampleError(ValueError):
    pass


def _utc_index(index: pd.Index) -> pd.DatetimeIndex:
    try:
        stamps = pd.DatetimeIndex(pd.to_datetime(index))
    except Exception as exc:  # noqa: BLE001
        raise ResampleError("índice temporal inválido") from exc
    if stamps.tz is None:
        return stamps.tz_localize("UTC")
    return stamps.tz_convert("UTC")


def timeframe_minutes(timeframe: str) -> int:
    key = str(timeframe or "").strip().upper()
    if key not in _TF_MINUTES:
        valid = ", ".join(TIMEFRAMES)
        raise ResampleError(f"timeframe no soportado: {timeframe!r}; usa {valid}")
    return _TF_MINUTES[key]


def session_labels(
    index: pd.Index,
    timeframe: str,
    *,
    tz: str = _NY,
    cut_hour: int = _CUT_HOUR,
) -> pd.DatetimeIndex:
    """Etiqueta de sesión/rejilla (UTC) para cada apertura M1."""
    key = str(timeframe or "").strip().upper()
    minutes = timeframe_minutes(key)
    stamps = _utc_index(index)
    if key == "M1":
        return pd.DatetimeIndex(stamps, name="time")
    zone = ZoneInfo(tz)
    local = stamps.tz_convert(zone)
    naive = local.tz_localize(None)
    day = naive.normalize()
    cutoff = day + pd.Timedelta(hours=int(cut_hour))
    session_day = day.where(naive >= cutoff, day - pd.Timedelta(days=1))
    anchor_naive = session_day + pd.Timedelta(hours=int(cut_hour))
    anchor = anchor_naive.tz_localize(
        zone, ambiguous=False, nonexistent="raise"
    ).tz_convert("UTC")
    if key == "D1":
        return pd.DatetimeIndex(anchor, name="time")
    offset = (stamps - anchor).total_seconds().to_numpy(dtype="float64")
    bucket = np.floor(offset / (minutes * 60.0)).astype("int64")
    labels = anchor + pd.to_timedelta(bucket * minutes, unit="m")
    return pd.DatetimeIndex(labels, name="time")


def _aggregation(frame: pd.DataFrame) -> dict[str, str]:
    rules: dict[str, str] = {}
    for column in frame.columns:
        name = str(column).lower()
        if name in {"open", "ask_open"}:
            rules[column] = "first"
        elif name in {"high", "ask_high"}:
            rules[column] = "max"
        elif name in {"low", "ask_low"}:
            rules[column] = "min"
        elif name in {"close", "ask_close"}:
            rules[column] = "last"
        elif name in {"volume", "tickvol", "ask_volume"}:
            rules[column] = "sum"
        elif name == "spread":
            rules[column] = "mean"
        else:
            rules[column] = "last"
    return rules


def resample_session(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    tz: str = _NY,
    cut_hour: int = _CUT_HOUR,
) -> pd.DataFrame:
    """Agrega M1 a otra temporalidad sin fabricar velas."""
    key = str(timeframe or "").strip().upper()
    timeframe_minutes(key)
    if frame is None or len(frame) == 0:
        return pd.DataFrame() if frame is None else frame.copy()
    work = frame.copy()
    work.columns = [str(column).lower() for column in work.columns]
    missing = [column for column in ("open", "high", "low", "close") if column not in work.columns]
    if missing:
        raise ResampleError(f"faltan columnas OHLC: {', '.join(missing)}")
    index = _utc_index(work.index)
    work.index = index
    work = work.sort_index()
    work = work.loc[~work.index.duplicated(keep="last")]
    if key == "M1":
        work.index.name = "time"
        return work
    labels = session_labels(work.index, key, tz=tz, cut_hour=cut_hour)
    buckets = pd.Series(labels, index=work.index, name="bucket")
    result = work.groupby(buckets, sort=True).agg(_aggregation(work))
    result.index = pd.DatetimeIndex(result.index, name="time")
    return result


__all__ = [
    "ResampleError",
    "TIMEFRAMES",
    "resample_session",
    "session_labels",
    "timeframe_minutes",
]
