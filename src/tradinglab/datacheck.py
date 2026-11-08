"""Calidad de la caché de datos. Solo lectura; no descarga ni inventa datos.

El resultado es `ok`, `aviso` o `falla`. `lab research` solo bloquea un activo
cuando el datacheck devuelve `falla`; los avisos se muestran pero no relajan
ningún umbral de propuesta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data.base import safe_ticker
from .instruments import InstrumentError, get_instrument

DATACHECK_VERSION = 1
STATUS_ORDER = {"ok": 0, "aviso": 1, "falla": 2}
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")


@dataclass(frozen=True)
class Check:
    status: str
    reason: str
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "reason": self.reason,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def _status_of(value: str) -> int:
    return STATUS_ORDER.get(value, STATUS_ORDER["falla"])


def _merge_status(statuses: list[str]) -> str:
    if not statuses:
        return "ok"
    return max(statuses, key=_status_of)


def _iso_date(value: Any) -> str | None:
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return None


def _sample_dates(index: pd.Index, mask: pd.Series | pd.Index) -> list[str]:
    try:
        selected = index[mask]
    except Exception:
        return []
    return [str(pd.Timestamp(item).date()) for item in selected[:5]]


def _read_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    meta = Path(path).with_suffix(".meta.json")
    if not meta.exists():
        return {}
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def find_cache(cache_dir: str | Path, symbol: str) -> Path | None:
    """Elige la caché más larga con el fin más reciente para el símbolo."""
    root = Path(cache_dir)
    pattern = f"{safe_ticker(symbol)}__*.parquet"
    files = list(root.glob(pattern))
    if not files:
        return None

    def parts(path: Path) -> tuple[str, str]:
        pieces = path.stem.split("__")
        start = pieces[1] if len(pieces) > 1 else ""
        end = pieces[2] if len(pieces) > 2 else ""
        return start, end

    latest_end = max(parts(path)[1] for path in files)
    candidates = [path for path in files if parts(path)[1] == latest_end]
    return min(candidates, key=lambda path: parts(path)[0])


def _check_cache(path: Path | None, rows: int) -> Check:
    if rows == 0:
        return Check("falla", "Sin datos: el DataFrame está vacío")
    if path is None:
        return Check("ok", f"{rows} barras en memoria (sin cache_path)")
    return Check("ok", f"{rows} barras en {path.name}")


def _check_index(index: pd.Index) -> tuple[Check, Check, Check, pd.DatetimeIndex]:
    try:
        dt = pd.DatetimeIndex(pd.to_datetime(index))
    except Exception:
        bad = Check("falla", "el índice no es una serie temporal válida")
        return bad, bad, bad, pd.DatetimeIndex([])

    duplicates = int(dt.duplicated().sum())
    duplicates_check = (
        Check("ok", "sin timestamps duplicados")
        if duplicates == 0
        else Check("falla", f"{duplicates} timestamps duplicados")
    )
    ordered = bool(dt.is_monotonic_increasing)
    order_check = (
        Check("ok", "barras en orden")
        if ordered
        else Check("falla", "barras fuera de orden")
    )
    tz = getattr(dt, "tz", None)
    if tz is not None:
        tz_check = Check("ok", f"zona horaria declarada: {tz}")
    else:
        tz_check = Check(
            "aviso",
            "el índice es naive; la zona horaria no está declarada en la serie",
        )
    return duplicates_check, order_check, tz_check, dt


def _check_ohlc(df: pd.DataFrame) -> Check:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        return Check("falla", f"faltan columnas: {', '.join(missing)}")

    frame = df.copy()
    for column in REQUIRED_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    values = frame[list(REQUIRED_COLUMNS)].to_numpy(dtype=float)
    non_finite = int((~np.isfinite(values)).sum())
    if non_finite:
        return Check("falla", f"{non_finite} valores NaN/inf en OHLCV")

    open_, high, low, close = (frame[column] for column in PRICE_COLUMNS)
    volume = frame["volume"]
    bad = (
        (high < low)
        | (high < open_)
        | (high < close)
        | (low > open_)
        | (low > close)
        | (open_ <= 0)
        | (close <= 0)
        | (high <= 0)
        | (low <= 0)
    )
    bad_count = int(bad.sum())
    if bad_count:
        return Check(
            "falla",
            f"{bad_count} barras con OHLC inconsistente",
            {"fechas": _sample_dates(frame.index, bad)},
        )
    negative_volume = int((volume < 0).sum())
    if negative_volume:
        return Check("falla", f"{negative_volume} barras con volumen negativo")
    return Check("ok", "OHLC y volumen consistentes")


def _check_calendar(index: pd.DatetimeIndex, timeframe: str) -> Check:
    if timeframe.lower() not in {"1d", "d", "daily"}:
        return Check(
            "aviso",
            f"calendario no configurado para timeframe {timeframe}; solo se valida 1d",
        )
    if len(index) < 2:
        return Check("falla", "Sin datos suficientes para validar el calendario")
    dates = pd.DatetimeIndex(index).normalize()
    expected = pd.bdate_range(dates.min(), dates.max())
    missing = expected.difference(dates)
    gap_pct = len(missing) / max(1, len(expected))
    weekend = int((dates.day_of_week >= 5).sum())
    if gap_pct <= 0.02:
        status = "ok"
    elif gap_pct <= 0.10:
        status = "aviso"
    else:
        status = "falla"
    reason = (
        f"{len(missing)} huecos de calendario ({gap_pct:.1%}) "
        f"y {weekend} barras en fin de semana"
    )
    detail = {"huecos": len(missing), "pct": round(gap_pct, 6), "fin_semana": weekend}
    if len(missing):
        detail["fechas"] = _sample_dates(missing, pd.Series(True, index=missing))
    return Check(status, reason, detail)


def _check_jumps(index: pd.DatetimeIndex, close: pd.Series) -> Check:
    returns = pd.to_numeric(close, errors="coerce").pct_change()
    extreme = returns.abs() > 0.25
    count = int(extreme.fillna(False).sum())
    if count == 0:
        return Check("ok", "sin saltos diarios >25%")
    max_abs = float(returns.abs().max())
    status = "falla" if max_abs >= 0.90 else "aviso"
    detail = {
        "saltos_25": count,
        "max_abs": round(max_abs, 6),
        "fechas": _sample_dates(index, extreme.fillna(False)),
    }
    return Check(status, f"{count} saltos >25%; máximo {max_abs:.1%}", detail)


def _check_adjustment(metadata: dict[str, Any]) -> Check:
    if "adjusted" not in metadata:
        return Check(
            "aviso",
            "ajuste no declarado: no hay metadatos adjusted en la caché",
        )
    if metadata.get("adjusted"):
        source = metadata.get("adjustment") or metadata.get("provider") or "metadatos"
        return Check("ok", f"ajustado declarado ({source})")
    return Check("aviso", "la caché declara datos no ajustados")


def _check_timezone(metadata: dict[str, Any], instrument) -> Check:
    declared = metadata.get("timezone")
    if declared and declared != "date-only":
        return Check("ok", f"zona horaria declarada en metadatos: {declared}")
    if instrument is not None and getattr(instrument, "session_tz", ""):
        return Check(
            "ok",
            f"zona horaria de sesión declarada por catálogo: {instrument.session_tz}",
        )
    return Check("aviso", "zona horaria no declarada")


def _check_bid_ask(df: pd.DataFrame, asset_class: str | None) -> Check:
    present = [column for column in ("bid", "ask", "mid", "spread") if column in df.columns]
    if present:
        return Check("ok", "bid/ask/mid/spread presentes: " + ", ".join(present))
    if asset_class in {"forex", "cfd", "futures"}:
        return Check(
            "aviso",
            f"sin bid/ask/mid/spread en la caché para {asset_class}",
        )
    return Check("ok", "bid/ask no aplica a equity diario")


def _instrument_for(symbol: str):
    try:
        return get_instrument(symbol)
    except InstrumentError:
        return None


def check_frame(
    df: pd.DataFrame,
    symbol: str,
    *,
    timeframe: str = "1d",
    cache_path: str | Path | None = None,
) -> dict[str, Any]:
    """Valida un DataFrame ya cargado. No descarga datos."""
    frame = df.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    instrument = _instrument_for(symbol)
    metadata = _read_metadata(Path(cache_path) if cache_path else None)
    checks: dict[str, Check] = {}

    checks["cache"] = _check_cache(
        Path(cache_path) if cache_path else None,
        len(frame),
    )
    duplicates, order, tz_check, index = _check_index(frame.index)
    checks["duplicados"] = duplicates
    checks["orden"] = order
    # La serie naive puede quedar declarada por metadatos o por el catálogo.
    checks["zona_horaria"] = _check_timezone(metadata, instrument)
    if tz_check.status == "ok":
        checks["zona_horaria"] = tz_check
    checks["ohlc"] = _check_ohlc(frame)
    if checks["ohlc"].status == "ok":
        checks["calendario"] = _check_calendar(index, timeframe)
        checks["saltos"] = _check_jumps(index, frame["close"])
    else:
        checks["calendario"] = Check("falla", "no se evalúa: OHLC inválido")
        checks["saltos"] = Check("falla", "no se evalúa: OHLC inválido")

    checks["ajuste"] = _check_adjustment(metadata)
    checks["bid_ask"] = _check_bid_ask(frame, getattr(instrument, "asset_class", None))

    if timeframe.lower() in {"1d", "d", "daily"} and len(frame) < 260:
        checks["historico"] = Check(
            "falla",
            f"histórico insuficiente para research: {len(frame)} < 260 barras",
        )
    else:
        checks["historico"] = Check("ok", f"{len(frame)} barras")

    statuses = [check.status for check in checks.values()]
    status = _merge_status(statuses)
    reasons = [
        f"{name}: {check.reason}"
        for name, check in checks.items()
        if check.status != "ok"
    ]
    start = _iso_date(index.min()) if len(index) else None
    end = _iso_date(index.max()) if len(index) else None
    return {
        "version": DATACHECK_VERSION,
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "status": status,
        "reasons": reasons,
        "rows": len(frame),
        "start": start,
        "end": end,
        "cache_path": str(cache_path) if cache_path else None,
        "checks": {name: check.to_dict() for name, check in checks.items()},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def check_symbol(
    symbol: str,
    *,
    cache_dir: str | Path,
    timeframe: str = "1d",
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Lee el parquet más reciente del símbolo y lo valida."""
    selected = Path(path) if path is not None else find_cache(cache_dir, symbol)
    if selected is None:
        return {
            "version": DATACHECK_VERSION,
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "status": "falla",
            "reasons": [
                f"cache: Sin datos: no hay parquet para {symbol} en {Path(cache_dir)}"
            ],
            "rows": 0,
            "start": None,
            "end": None,
            "cache_path": None,
            "checks": {
                "cache": {
                    "status": "falla",
                    "reason": f"Sin datos: no hay parquet para {symbol}",
                }
            },
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    try:
        df = pd.read_parquet(selected)
    except Exception as exc:
        return {
            "version": DATACHECK_VERSION,
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "status": "falla",
            "reasons": [f"cache: no se pudo leer el parquet ({type(exc).__name__})"],
            "rows": 0,
            "start": None,
            "end": None,
            "cache_path": str(selected),
            "checks": {
                "cache": {
                    "status": "falla",
                    "reason": f"no se pudo leer: {type(exc).__name__}",
                }
            },
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    return check_frame(
        df,
        symbol,
        timeframe=timeframe,
        cache_path=selected,
    )


__all__ = [
    "DATACHECK_VERSION",
    "check_frame",
    "check_symbol",
    "find_cache",
]
