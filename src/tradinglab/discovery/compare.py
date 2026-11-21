"""Comparación Dukascopy vs bróker en M5 (solo lectura, sin campañas).

Criterio de aceptación: correlación de rendimientos >= 0,95 y lag 0 (la máxima
correlación ocurre sin desplazamiento). Si no se cumple, la fuente no es apta y
no debe usarse en una campaña.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT
from .data_sources import DataSourceError, load_source
from .fetch_dukascopy import SYMBOLS
from .resample import timeframe_minutes

DEFAULT_START = "2021-10-01"
DEFAULT_TIMEFRAME = "M5"
CORRELATION_MIN = 0.95
LAG_MAX = 5


class CompareError(RuntimeError):
    pass


def _safe_symbol(symbol: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-_." else "_" for char in str(symbol)
    ).upper()


def broker_path(
    symbol: str, timeframe: str = DEFAULT_TIMEFRAME, *, root: Path = ROOT
) -> Path:
    return (
        Path(root)
        / "data"
        / "cache"
        / "discovery"
        / f"{_safe_symbol(symbol)}_{str(timeframe).upper()}.parquet"
    )


def _utc(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work.columns = [str(column).lower() for column in work.columns]
    index = pd.DatetimeIndex(pd.to_datetime(work.index))
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    work.index = index
    work.index.name = "time"
    return work.sort_index()


def _load_broker(
    symbol: str, timeframe: str, root: Path
) -> tuple[pd.DataFrame, Path]:
    path = broker_path(symbol, timeframe, root=root)
    if not path.exists():
        raise CompareError(f"Sin datos: no existe {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise CompareError(
            f"Sin datos: no se pudo leer {path} ({type(exc).__name__}: {exc})"
        ) from exc
    return _utc(frame), path


def _slice(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None
) -> pd.DataFrame:
    mask = frame.index >= start
    if end is not None:
        mask &= frame.index <= end
    return frame.loc[mask]


def compare_symbol(
    symbol: str,
    *,
    start: str = DEFAULT_START,
    end: str | None = None,
    timeframe: str = DEFAULT_TIMEFRAME,
    root: Path = ROOT,
    lag_max: int = LAG_MAX,
) -> dict[str, Any]:
    key = str(symbol).strip().upper()
    tf = str(timeframe).strip().upper()
    start_ts = pd.Timestamp(start, tz="UTC")
    if end:
        end_ts = pd.Timestamp(end, tz="UTC")
        if len(str(end)) <= 10:
            end_ts = end_ts + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    else:
        end_ts = None
    broker, path = _load_broker(key, tf, root)
    try:
        dukascopy = load_source(
            key, tf, source="dukascopy", root=root
        ).frame
    except DataSourceError as exc:
        raise CompareError(str(exc)) from exc
    broker = _slice(broker, start_ts, end_ts)
    dukascopy = _slice(dukascopy, start_ts, end_ts)
    joined = broker[["open", "high", "low", "close"]].join(
        dukascopy[["open", "high", "low", "close"]],
        how="inner",
        suffixes=("_b", "_d"),
    )
    joined = joined.dropna()
    if len(joined) < 2:
        raise CompareError(
            f"Sin datos: solapamiento insuficiente para {key} {tf} "
            f"({len(joined)} velas)"
        )
    returns = joined[["close_b", "close_d"]].pct_change().dropna()
    correlation = (
        float(returns["close_b"].corr(returns["close_d"]))
        if len(returns) > 1
        else None
    )
    best_lag = 0
    best_corr = float("-inf")
    for lag in range(-int(lag_max), int(lag_max) + 1):
        value = returns["close_b"].corr(returns["close_d"].shift(lag))
        if pd.notna(value) and float(value) > best_corr:
            best_corr = float(value)
            best_lag = int(lag)
    mean_diff = float((joined["close_b"] - joined["close_d"]).mean())
    mean_level = float(joined["close_d"].mean())
    mean_diff_bps = mean_diff / mean_level * 10_000.0 if mean_level else None
    median_range = float((joined["high_b"] - joined["low_b"]).median())
    tolerance = max(median_range * 0.10, 1e-12)
    aligned = {
        column: joined[f"{column}_b"] - (joined[f"{column}_d"] + mean_diff)
        for column in ("open", "high", "low", "close")
    }
    matches = pd.Series(True, index=joined.index)
    for values in aligned.values():
        matches &= values.abs() <= tolerance
    match_pct = float(matches.mean() * 100.0)
    lag_ok = best_lag == 0
    corr_ok = correlation is not None and correlation >= CORRELATION_MIN
    verdict = "apta" if corr_ok and lag_ok else "no apta"
    reasons: list[str] = []
    if correlation is None:
        reasons.append("correlación Sin datos")
    elif not corr_ok:
        reasons.append(f"correlación {correlation:.4f} < {CORRELATION_MIN:.2f}")
    if not lag_ok:
        reasons.append(f"lag {best_lag:+d} velas")
    return {
        "symbol": key,
        "timeframe": tf,
        "broker_path": path.as_posix(),
        "start": joined.index[0].isoformat(),
        "end": joined.index[-1].isoformat(),
        "rows": int(len(joined)),
        "correlation": None if correlation is None else round(correlation, 6),
        "lag": int(best_lag),
        "lag_correlation": round(best_corr, 6) if best_corr > float("-inf") else None,
        "mean_diff": mean_diff,
        "mean_diff_bps": None if mean_diff_bps is None else round(mean_diff_bps, 4),
        "match_pct": round(match_pct, 2),
        "tolerance": tolerance,
        "verdict": verdict,
        "reason": "apta" if verdict == "apta" else "; ".join(reasons),
    }


def compare_all(
    symbols: list[str] | tuple[str, ...] | None = None,
    *,
    start: str = DEFAULT_START,
    end: str | None = None,
    timeframe: str = DEFAULT_TIMEFRAME,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    timeframe_minutes(timeframe)
    selected = tuple(symbols) if symbols else SYMBOLS
    rows: list[dict[str, Any]] = []
    for symbol in selected:
        key = str(symbol).strip().upper()
        try:
            rows.append(
                compare_symbol(
                    key,
                    start=start,
                    end=end,
                    timeframe=timeframe,
                    root=root,
                )
            )
        except (CompareError, DataSourceError) as exc:
            rows.append(
                {
                    "symbol": key,
                    "timeframe": str(timeframe).upper(),
                    "broker_path": broker_path(key, timeframe, root=root).as_posix(),
                    "start": None,
                    "end": None,
                    "rows": 0,
                    "correlation": None,
                    "lag": None,
                    "lag_correlation": None,
                    "mean_diff": None,
                    "mean_diff_bps": None,
                    "match_pct": None,
                    "tolerance": None,
                    "verdict": "no apta",
                    "reason": str(exc),
                }
            )
    return rows


__all__ = [
    "CORRELATION_MIN",
    "DEFAULT_START",
    "CompareError",
    "broker_path",
    "compare_all",
    "compare_symbol",
]
