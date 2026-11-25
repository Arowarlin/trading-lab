"""Datos M5 propios de US100 y spread por ventana de sesión (Fase 2).

No ejecuta backtests: descarga/valida velas, aplica el suelo de spread medido y
compara las ventanas de entrada de Londres y Asia con la de Nueva York.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import session_engine
from .atr import ny_naive_index, wilder_atr
from .data import (
    EXPECTED_POINT,
    DataBundle,
    DataError,
    _normalize_bars,
    _settings_broker,
    apply_spread_floor,
    validate_bars,
)
from .sessions import (
    OWN_CACHE,
    WINDOW_END,
    WINDOW_START,
)

SYMBOL = "US100.cash"


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def load_m5_us100_own(
    *,
    refresh: bool = False,
    cache_path: Path = OWN_CACHE,
    broker=None,
    count: int = 400_000,
) -> DataBundle:
    """Lee US100.cash M5 del terminal o de su caché propia (nunca la del EA)."""
    cache_path = Path(cache_path)
    meta_path = _meta_path(cache_path)
    if cache_path.exists() and not refresh:
        frame = pd.read_parquet(cache_path)
        frame.index = pd.DatetimeIndex(frame.index)
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        return DataBundle(
            frame=_normalize_bars(frame),
            spec=meta.get("spec"),
            cache_path=cache_path,
            source=str(meta.get("source") or "cache"),
            downloaded_at=meta.get("downloaded_at"),
        )

    broker = broker or _settings_broker()
    spec = broker.symbol_spec(SYMBOL) or {}
    raw = broker.rates(SYMBOL, "M5", count)
    frame = _normalize_bars(raw)
    downloaded_at = datetime.now(UTC).isoformat(timespec="seconds")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path)
    meta_path.write_text(
        json.dumps(
            {"source": "mt5-attach-only", "downloaded_at": downloaded_at, "spec": spec},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return DataBundle(
        frame=frame,
        spec=spec,
        cache_path=cache_path,
        source="mt5-attach-only",
        downloaded_at=downloaded_at,
    )


def session_clock(frame: pd.DataFrame, anchors: dict) -> tuple[np.ndarray, pd.DatetimeIndex]:
    """Minutos locales y fechas locales de la ventana pre-registrada."""
    _utc, minutes, _day, local = session_engine._local_index(frame.index, anchors["tz"])
    return minutes, pd.DatetimeIndex(local)


def _window_mask(minutes: np.ndarray, anchors: dict) -> np.ndarray:
    resolved = session_engine.resolve_session({}, session=anchors)
    start = resolved["trade_start_min"]
    end = resolved["trade_end_min"]
    return np.array([session_engine.in_sess(int(m), start, end) for m in minutes], dtype=bool)


def session_spread(
    frame: pd.DataFrame,
    measured: dict,
    anchors: dict,
    label: str,
    *,
    spread_rows: pd.DataFrame | None = None,
    start: str = WINDOW_START,
    end: str = WINDOW_END,
) -> dict:
    """Spread bruto y con suelo en la ventana de entradas de una sesión."""
    local_frame = ny_naive_index(frame).loc[start:end]
    prepared, floor = apply_spread_floor(local_frame, measured, spread_rows=spread_rows)
    minutes, local = session_clock(prepared, anchors)
    mask = _window_mask(minutes, anchors)
    if not mask.any():
        raise DataError(f"Sin datos: la ventana de {label} no tiene velas")
    window = prepared.loc[mask]
    raw = local_frame.loc[window.index]
    floored = pd.to_numeric(window["spread"], errors="coerce")
    raw_points = pd.to_numeric(raw["spread"], errors="coerce")
    hours = np.array([stamp.hour for stamp in local[mask]], dtype=int)
    hourly = []
    for hour in sorted(set(hours.tolist())):
        chunk = floored[hours == hour]
        hourly.append(
            {
                "hour_local": int(hour),
                "bars": int(len(chunk)),
                "median_points": round(float(chunk.median()), 4),
                "p75_points": round(float(chunk.quantile(0.75)), 4),
            }
        )
    days = pd.DatetimeIndex(local[mask]).normalize().unique()
    resolved = session_engine.resolve_session({}, session=anchors)
    start_min = resolved["trade_start_min"]
    end_min = resolved["trade_end_min"]
    return {
        "label": label,
        "tz": anchors["tz"],
        "window": f"{start_min // 60:02d}:{start_min % 60:02d}–"
                  f"{end_min // 60:02d}:{end_min % 60:02d}",
        "bars": int(len(window)),
        "days": int(len(days)),
        "first_local": str(pd.DatetimeIndex(local[mask]).min()),
        "last_local": str(pd.DatetimeIndex(local[mask]).max()),
        "bars_per_day_median": round(float(
            pd.Series(1, index=window.index).groupby(
                pd.DatetimeIndex(window.index).normalize()
            ).sum().median()
        ), 2),
        "median_points": round(float(floored.median()), 4),
        "p75_points": round(float(floored.quantile(0.75)), 4),
        "median_price": round(float(floored.median()) * EXPECTED_POINT, 4),
        "raw_median_points": round(float(raw_points.median()), 4),
        "floor": floor,
        "hourly": hourly,
    }


def _weekday_coverage(days: int, start: str = WINDOW_START, end: str = WINDOW_END) -> dict:
    expected = len(pd.bdate_range(start, end))
    return {
        "days_with_data": int(days),
        "weekdays_in_window": int(expected),
        "coverage_pct": round(days / expected * 100, 2) if expected else None,
    }


def session_atr(
    frame: pd.DataFrame,
    anchors: dict,
    *,
    length: int = 14,
    start: str = WINDOW_START,
    end: str = WINDOW_END,
) -> dict:
    """ATR Wilder 14 mediano dentro de la ventana de entradas (no backtest)."""
    local = ny_naive_index(frame)
    atr = wilder_atr(local, length)
    minutes, _ = session_clock(local.loc[start:end], anchors)
    mask = _window_mask(minutes, anchors)
    values = atr.loc[start:end][mask].dropna()
    if values.empty:
        raise DataError(f"Sin datos: ATR vacío en la ventana de {anchors['tz']}")
    return {
        "atr_len": int(length),
        "bars": int(len(values)),
        "median_atr": round(float(values.median()), 6),
    }


def build_session_data_report(
    bundle: DataBundle,
    measured: dict,
    *,
    candidate: str,
    anchors: dict,
    session_stats: dict,
    ny_stats: dict,
    atr_stats: dict,
    ny_atr: dict,
) -> dict:
    quality = validate_bars(bundle.frame, bundle.spec, start=WINDOW_START, end=WINDOW_END)
    coverage = _weekday_coverage(session_stats["days"])
    ny_median = float(ny_stats["median_points"])
    session_median = float(session_stats["median_points"])
    comparison = {
        "ny_median_points": round(ny_median, 4),
        "session_median_points": round(session_median, 4),
        "difference_points": round(session_median - ny_median, 4),
        "ratio_vs_ny": round(session_median / ny_median, 4) if ny_median > 0 else None,
    }
    session_rel = (
        float(session_stats["median_price"]) / float(atr_stats["median_atr"])
        if atr_stats["median_atr"] > 0 else None
    )
    ny_rel = (
        float(ny_stats["median_price"]) / float(ny_atr["median_atr"])
        if ny_atr["median_atr"] > 0 else None
    )
    viability = {
        "session": {
            "median_atr": atr_stats["median_atr"],
            "atr_bars": atr_stats["bars"],
            "spread_price": session_stats["median_price"],
            "spread_over_atr": round(session_rel, 6) if session_rel is not None else None,
        },
        "ny": {
            "median_atr": ny_atr["median_atr"],
            "atr_bars": ny_atr["bars"],
            "spread_price": ny_stats["median_price"],
            "spread_over_atr": round(ny_rel, 6) if ny_rel is not None else None,
        },
        "ratio_vs_ny": (
            round(session_rel / ny_rel, 4)
            if session_rel is not None and ny_rel not in (None, 0) else None
        ),
    }
    data_ok = all(
        [
            quality["duplicates"] == 0,
            quality["invalid_bars"] == 0,
            quality["spec"]["point_ok"],
            quality["coverage_ok"],
            quality["years_min_300_rth"],
            str(quality["first_rth_time"]).startswith("09:30"),
            str(quality["last_rth_time"]).startswith("15:55"),
            session_stats["bars"] > 0,
            comparison["ratio_vs_ny"] is not None,
            atr_stats["bars"] > 0,
            viability["ratio_vs_ny"] is not None,
        ]
    )
    return {
        "candidate": candidate,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": bundle.source,
        "downloaded_at": bundle.downloaded_at,
        "cache": str(bundle.cache_path),
        "window": {"start": WINDOW_START, "end": WINDOW_END, "tz": "America/New_York"},
        "anchors": anchors,
        "quality": quality,
        "spread": {
            "measured": measured,
            "session": session_stats,
            "ny": ny_stats,
            "comparison": comparison,
            "coverage": coverage,
        },
        "viability": viability,
        "data_ok": bool(data_ok),
    }


__all__ = [
    "SYMBOL",
    "build_session_data_report",
    "load_m5_us100_own",
    "session_atr",
    "session_clock",
    "session_spread",
]
