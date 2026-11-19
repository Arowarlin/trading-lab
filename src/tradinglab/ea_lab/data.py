"""Datos M5 de US500.cash en solo lectura y validación de la caché propia."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..broker_costs import load_spreads
from ..config import Settings
from ..nyse_calendar import is_full_holiday
from .atr import ny_naive_index
from .candidate import SYMBOL, US500_CACHE, WINDOW_END, WINDOW_START

EXPECTED_POINT = 0.01
BARS_PER_RTH_DAY = 78  # 09:30–15:55, 78 velas M5
MAX_SPREAD_AGE_DAYS = 7


class DataError(RuntimeError):
    pass


@dataclass
class DataBundle:
    frame: pd.DataFrame
    spec: dict | None
    cache_path: Path
    source: str
    downloaded_at: str | None = None


def _settings_broker():
    from ..propfund.snapshots import AttachOnlyBroker

    settings = Settings.load()
    login = settings.mt5.login
    server = settings.mt5.server
    if login is None or not str(server or "").strip():
        raise DataError(
            "Sin datos: define MT5_LOGIN y MT5_SERVER para verificar la cuenta del terminal"
        )
    broker = AttachOnlyBroker(
        expected_login=int(login),
        expected_server=str(server).strip(),
        path=settings.mt5.terminal_path,
        timeout_ms=5000,
        server_utc_offset_hours=settings.mt5.server_utc_offset_hours,
    )
    broker.connect()
    return broker


def _normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    out = ny_naive_index(frame)
    if "volume" in out.columns and "tickvol" not in out.columns:
        out = out.rename(columns={"volume": "tickvol"})
    for column in ("tickvol", "spread"):
        if column not in out.columns:
            out[column] = 0.0
    columns = ["open", "high", "low", "close", "tickvol", "spread"]
    return out[[column for column in columns if column in out.columns]].astype(float)


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def load_m5_us500(
    *,
    refresh: bool = False,
    cache_path: Path = US500_CACHE,
    broker=None,
    count: int = 400_000,
) -> DataBundle:
    """Lee US500.cash M5 del terminal o de su caché propia (nunca la del US100)."""
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

    owned = broker is None
    broker = broker or _settings_broker()
    try:
        spec = broker.symbol_spec(SYMBOL) or {}
        raw = broker.rates(SYMBOL, "M5", count)
    finally:
        if owned:
            # AttachOnlyBroker no llama a shutdown: la conexión IPC se libera
            # al terminar el proceso y el terminal compartido no se toca.
            pass
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


def load_us100_cache(path: Path | None = None) -> pd.DataFrame:
    from .candidate import US100_CACHE

    target = Path(path) if path else US100_CACHE
    if not target.exists():
        raise DataError(f"Sin datos: falta la caché del US100 en {target}")
    frame = pd.read_parquet(target)
    frame.index = pd.DatetimeIndex(frame.index)
    return _normalize_bars(frame)


def measured_spread(
    symbol: str = SYMBOL,
    *,
    db_path=None,
    max_age_days: int = MAX_SPREAD_AGE_DAYS,
    now: datetime | None = None,
) -> dict:
    """Spread medido en ``broker_spreads`` (source=broker) y su antigüedad."""
    frame = (
        load_spreads(symbol=symbol, source="broker")
        if db_path is None
        else load_spreads(db_path, symbol=symbol, source="broker")
    )
    if frame is None or frame.empty:
        raise DataError(
            f"Sin datos: no hay spread medido de {symbol}. Ejecuta antes: "
            f"lab ticks broker-spread {symbol} --days 7"
        )
    to_ts = pd.to_datetime(frame["to_ts"], errors="coerce", utc=True).max()
    if pd.isna(to_ts):
        raise DataError("Sin datos: broker_spreads no tiene to_ts válido")
    moment = now or datetime.now(UTC)
    age = moment - to_ts.to_pydatetime()
    if age > timedelta(days=int(max_age_days)):
        raise DataError(
            f"Sin datos: la medición de {symbol} tiene {age.days} días "
            f"(máximo {max_age_days}). Ejecuta: lab ticks broker-spread {symbol} --days 7"
        )
    return {
        "symbol": symbol,
        "source": "broker",
        "rows": int(len(frame)),
        "median_bps": round(float(frame["median_bps"].median()), 6),
        "p75_bps": round(float(frame["p75_bps"].median()), 6),
        "hours": sorted(int(hour) for hour in frame["hour_utc"].unique()),
        "from_ts": str(frame["from_ts"].min()),
        "to_ts": str(to_ts.isoformat()),
        "age_hours": round(age.total_seconds() / 3600, 2),
        "max_age_days": int(max_age_days),
    }


def apply_spread_floor(
    frame: pd.DataFrame,
    measured: dict,
    *,
    point_size: float = EXPECTED_POINT,
    spread_rows: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Aplica ``max(spread_barra, cierre × bps / 10000)`` por hora UTC.

    El motor cobra ``spread × 0,01``; se mantiene la columna en puntos para no
    cambiar el motor. Las horas sin medición conservan el spread del bróker.
    """
    if point_size <= 0:
        raise DataError("point_size inválido")
    local = ny_naive_index(frame)
    rows = spread_rows
    if rows is None:
        rows = load_spreads(symbol=measured["symbol"], source="broker")
    if rows is None or rows.empty:
        raise DataError("Sin datos: broker_spreads desapareció entre la lectura y el uso")
    by_hour = (
        rows.assign(hour=pd.to_numeric(rows["hour_utc"], errors="coerce"))
        .groupby("hour")["median_bps"]
        .median()
    )
    utc = local.index.tz_localize("America/New_York").tz_convert("UTC")
    hours = pd.Index(utc.hour)
    bps = pd.Series(by_hour.reindex(hours).to_numpy(), index=local.index, dtype=float)
    measured_points = pd.to_numeric(local["close"], errors="coerce") * bps / 10_000.0 / point_size
    bar_points = pd.to_numeric(local["spread"], errors="coerce").fillna(0.0)
    floored = np.maximum(bar_points.to_numpy(), measured_points.fillna(-np.inf).to_numpy())
    out = local.copy()
    out["spread"] = floored
    covered = int(bps.notna().sum())
    covered_hours = sorted({int(hour) for hour, value in zip(hours, bps) if not pd.isna(value)})
    return out, {
        "hours_covered": covered_hours,
        "bars_with_measured_floor": covered,
        "bars_total": int(len(out)),
        "bar_median_points": round(float(bar_points.median()), 6) if len(bar_points) else None,
        "floored_median_points": round(float(np.median(floored)), 6) if len(floored) else None,
    }


def _rth(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.between_time("09:30", "15:59")


def validate_bars(
    frame: pd.DataFrame,
    spec: dict | None,
    *,
    start: str = WINDOW_START,
    end: str = WINDOW_END,
) -> dict:
    """Duplicados, huecos, zona horaria, cobertura y comprobación del punto."""
    local = ny_naive_index(frame)
    if local.empty:
        raise DataError("Sin datos: la serie M5 está vacía")
    window = local.loc[start:end]
    if window.empty:
        raise DataError(f"Sin datos: no hay velas en la ventana {start} → {end}")
    rth = _rth(window)
    duplicates = int(local.index.duplicated().sum())
    invalid = int(
        (
            window[["open", "high", "low", "close"]].isna().any(axis=1)
            | (window[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (window["high"] < window["low"])
        ).sum()
    )
    outside = int(len(window) - len(rth))

    days = pd.DatetimeIndex(sorted(set(rth.index.normalize())))
    per_day = rth.groupby(rth.index.normalize()).size()
    missing_by_day = (BARS_PER_RTH_DAY - per_day).clip(lower=0)
    holiday_flags = {day: is_full_holiday(day.date()) for day in days}
    holiday_days = [str(day.date()) for day in days if holiday_flags[day] and per_day.get(day, 0) > 0]
    early_close_days = [
        str(day.date())
        for day in days
        if not holiday_flags[day] and 30 <= int(missing_by_day.get(day, 0)) < 50
    ]
    years: dict[str, dict] = {}
    for year in sorted(set(window.index.year)):
        chunk = window[window.index.year == year]
        rth_year = rth[rth.index.year == year]
        years[str(year)] = {
            "bars": int(len(chunk)),
            "rth_bars": int(len(rth_year)),
            "days": int(chunk.index.normalize().nunique()),
            "missing_rth_bars": int(missing_by_day[missing_by_day.index.year == year].sum()),
        }

    gaps: list[dict] = []
    max_gap = 0.0
    for day, group in rth.groupby(rth.index.normalize()):
        if holiday_flags.get(day, False):
            continue
        stamps = group.index
        if len(stamps) < 2:
            continue
        delta = stamps.to_series().diff().dt.total_seconds().div(60)
        worst = float(delta.max())
        if worst > 5:
            gaps.append({"day": str(day.date()), "max_gap_min": worst, "bars": int(len(stamps))})
        max_gap = max(max_gap, worst)
    gaps.sort(key=lambda item: item["max_gap_min"], reverse=True)

    trading_missing = int(
        sum(int(value) for day, value in missing_by_day.items() if not holiday_flags.get(day, False))
    )
    trading_days = sum(1 for day in days if not holiday_flags[day])
    missing_pct = (
        round(trading_missing / (trading_days * BARS_PER_RTH_DAY) * 100, 3)
        if trading_days else None
    )

    point = float((spec or {}).get("point") or 0.0)
    digits = int((spec or {}).get("digits") or 0)
    point_ok = abs(point - EXPECTED_POINT) < 1e-12
    first_time = str(rth.index.min().time()) if len(rth) else None
    last_time = str(rth.index.max().time()) if len(rth) else None
    coverage_ok = (
        local.index.min() <= pd.Timestamp(start)
        and local.index.max() >= pd.Timestamp(f"{end} 23:59")
    )
    return {
        "rows": int(len(local)),
        "window_rows": int(len(window)),
        "rth_rows": int(len(rth)),
        "start": str(local.index.min()),
        "end": str(local.index.max()),
        "window_start": str(window.index.min()),
        "window_end": str(window.index.max()),
        "duplicates": duplicates,
        "invalid_bars": invalid,
        "bars_outside_rth": outside,
        "rth_days": int(len(days)),
        "missing_rth_bars": int(missing_by_day.sum()),
        "missing_rth_bars_pct": round(
            float(missing_by_day.sum()) / (len(days) * BARS_PER_RTH_DAY) * 100, 3
        ) if days.size else None,
        "missing_rth_bars_trading_days": trading_missing,
        "missing_rth_bars_pct_trading_days": missing_pct,
        "trading_days": int(trading_days),
        "early_close_days": early_close_days,
        "holiday_days_with_data": holiday_days,
        "max_intraday_gap_min": round(max_gap, 2),
        "worst_gaps": gaps[:10],
        "first_rth_time": first_time,
        "last_rth_time": last_time,
        "years": years,
        "spec": {
            "point": point or None,
            "digits": digits or None,
            "tick_size": (spec or {}).get("tick_size"),
            "contract_size": (spec or {}).get("contract_size"),
            "point_ok": point_ok,
        },
        "coverage_ok": bool(coverage_ok),
        "years_min_300_rth": all(item["rth_bars"] >= 300 for item in years.values()),
    }


def build_data_report(
    bundle: DataBundle,
    us100: pd.DataFrame,
    measured: dict,
    ratio: dict,
    *,
    window_start: str = WINDOW_START,
    window_end: str = WINDOW_END,
) -> dict:
    quality = validate_bars(bundle.frame, bundle.spec, start=window_start, end=window_end)
    prepared, floor = apply_spread_floor(bundle.frame, measured)
    bar_spread = pd.to_numeric(
        _rth(prepared.loc[window_start:window_end])["spread"], errors="coerce"
    )
    return {
        "candidate": "us500-nyopen",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": bundle.source,
        "downloaded_at": bundle.downloaded_at,
        "cache": str(bundle.cache_path),
        "window": {"start": window_start, "end": window_end, "tz": "America/New_York"},
        "quality": quality,
        "spread": {
            "measured": measured,
            "floor": floor,
            "rth_bar_median_points": round(float(bar_spread.median()), 6) if len(bar_spread) else None,
            "rth_bar_p75_points": round(float(bar_spread.quantile(0.75)), 6) if len(bar_spread) else None,
            "rth_bar_median_price": round(float(bar_spread.median()) * EXPECTED_POINT, 6)
            if len(bar_spread) else None,
        },
        "atr": ratio,
        "us100_rows": int(len(us100)),
    }


__all__ = [
    "BARS_PER_RTH_DAY",
    "DataBundle",
    "DataError",
    "EXPECTED_POINT",
    "apply_spread_floor",
    "build_data_report",
    "load_m5_us500",
    "load_us100_cache",
    "measured_spread",
    "validate_bars",
]
