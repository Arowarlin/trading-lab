"""Descarga M5 por cuenta desde el terminal MT5 adjunto (solo lectura).

Reglas:
* ``AttachOnlyBroker``: no llama a ``login`` ni a ``shutdown``.
* Verifica ``account_info`` antes y después; si el login cambia, aborta sin
  escribir.
* Solo ``symbol_select`` (Market Watch) y ``copy_rates_range``; los bloques
  trimestrales evitan el límite de barras del gráfico.
* Escribe únicamente ``data/cache/discovery/<SYMBOL>_M5.parquet`` en UTC.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..config import ROOT
from ..execution.mt5_offsets import infer_bar_offsets
from ..propfund.instruments import resolve
from ..propfund.market import broker_symbol as market_broker_symbol
from ..propfund.registry import load_registry
from ..propfund.snapshots import default_broker_factory

DISCOVERY_DIR = ROOT / "data" / "cache" / "discovery"
_TF_ATTR = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


class FetchError(RuntimeError):
    pass


def _safe_symbol(symbol: str) -> str:
    return "".join(
        c if c.isalnum() or c in "-_." else "_" for c in str(symbol)
    ).upper()


def canonical_symbol(symbol: str) -> str:
    try:
        return resolve(symbol).id
    except KeyError as exc:
        raise FetchError(str(exc)) from exc


def broker_symbol_for(symbol: str, account: Any) -> str:
    item = resolve(symbol)
    mapped = (getattr(account, "broker_symbols", {}) or {}).get(item.id)
    return str(mapped or market_broker_symbol(item.id))


def discovery_path(
    symbol: str, timeframe: str = "M5", *, root: Path = ROOT
) -> Path:
    return (
        root
        / "data"
        / "cache"
        / "discovery"
        / f"{_safe_symbol(canonical_symbol(symbol))}_{str(timeframe).upper()}.parquet"
    )


def _account_info(mt5: Any) -> Any:
    info = getattr(mt5, "account_info", None)
    if info is None:
        raise FetchError("Sin datos: el módulo MT5 no expone account_info")
    return info()


def _check_login(account: Any, expected_login: int) -> None:
    if account is None:
        raise FetchError("Sin datos: MT5 no tiene cuenta iniciada")
    login = int(getattr(account, "login", 0) or 0)
    if login != int(expected_login):
        raise FetchError(
            f"login esperado {int(expected_login)}, conectado {login}; "
            "no se escribe nada"
        )


def _timeframe(mt5: Any, timeframe: str) -> Any:
    key = str(timeframe).upper()
    attr = _TF_ATTR.get(key)
    if attr is None:
        raise FetchError(f"timeframe no soportado: {timeframe}")
    value = getattr(mt5, attr, None)
    if value is None:
        raise FetchError(f"Sin datos: MT5 no expone {attr}")
    return value


def _blocks(start: datetime, end: datetime, block_days: int):
    cursor = start
    step = timedelta(days=max(1, int(block_days)))
    while cursor < end:
        block_end = min(end, cursor + step)
        yield cursor, block_end
        cursor = block_end


def _server_frame(raw: Any) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    frame = pd.DataFrame(raw)
    if "time" not in frame.columns:
        raise FetchError("Sin datos: copy_rates_range no devolvió la columna time")
    frame = frame.copy()
    frame["time"] = pd.to_datetime(
        frame["time"], unit="s", utc=True
    )
    return frame


def download(
    symbol: str,
    *,
    account: str = "CFD-001",
    timeframe: str = "M5",
    start: str = "2021-09-01",
    end: str | None = None,
    block_days: int = 90,
    pause_s: float = 0.5,
    root: Path = ROOT,
    broker_factory: Callable[[Any], Any] | None = None,
    offset_hours: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Descarga por bloques y guarda en ``data/cache/discovery``."""

    identifier = canonical_symbol(symbol)
    registry = load_registry()
    account_obj = registry.accounts.get(str(account))
    if account_obj is None:
        raise FetchError(f"Sin datos: cuenta no registrada: {account}")
    factory = broker_factory or default_broker_factory
    broker = factory(account_obj)
    broker.connect()
    mt5 = broker._require()  # solo lectura; AttachOnlyBroker no hace shutdown

    expected_login = int(getattr(broker, "expected_login", getattr(account_obj, "login", 0) or 0))
    _check_login(_account_info(mt5), expected_login)

    broker_name = broker_symbol_for(identifier, account_obj)
    selected = getattr(mt5, "symbol_select", None)
    if selected is None:
        raise FetchError("Sin datos: el módulo MT5 no expone symbol_select")
    if not selected(broker_name, True):
        raise FetchError(f"symbol_select falló para {broker_name}")

    start_dt = pd.Timestamp(start, tz="UTC")
    end_dt = (
        pd.Timestamp(end, tz="UTC")
        if end
        else pd.Timestamp(now or datetime.now(timezone.utc))
    )
    if end_dt <= start_dt:
        raise FetchError("el fin debe ser posterior al inicio")

    tf = _timeframe(mt5, timeframe)
    raw_frames: list[pd.DataFrame] = []
    margin = timedelta(days=2)
    for block_start, block_end in _blocks(
        start_dt.to_pydatetime(), end_dt.to_pydatetime(), block_days
    ):
        server_from = (block_start - margin).replace(tzinfo=None)
        server_to = (block_end + margin).replace(tzinfo=None)
        raw = mt5.copy_rates_range(broker_name, tf, server_from, server_to)
        frame = _server_frame(raw)
        if not frame.empty:
            raw_frames.append(frame)
        if pause_s > 0:
            time.sleep(float(pause_s))
    if not raw_frames:
        raise FetchError(f"Sin datos: no hay barras para {broker_name}")

    # Segunda comprobación de identidad: si el terminal cambió de cuenta,
    # no se escribe nada.
    _check_login(_account_info(mt5), expected_login)

    combined = pd.concat(raw_frames, ignore_index=True)
    server_time = pd.DatetimeIndex(combined["time"])
    if offset_hours is None:
        try:
            offsets = infer_bar_offsets(server_time, timeframe)
        except Exception as exc:  # noqa: BLE001
            raise FetchError(
                f"No se pudo inferir el offset del servidor: {exc}"
            ) from exc
        utc_index = server_time - pd.to_timedelta(
            offsets.to_numpy(dtype=float), unit="h"
        )
    else:
        utc_index = server_time - pd.to_timedelta(
            float(offset_hours), unit="h"
        )
    combined.index = utc_index
    combined.index.name = "time"
    if "tick_volume" in combined.columns:
        combined = combined.rename(columns={"tick_volume": "tickvol"})
    columns = [
        column
        for column in ("open", "high", "low", "close", "tickvol", "spread")
        if column in combined.columns
    ]
    missing = {"open", "high", "low", "close"} - set(columns)
    if missing:
        raise FetchError(
            f"Sin datos: faltan columnas {', '.join(sorted(missing))}"
        )
    combined = combined.loc[:, columns].sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    combined = combined.loc[
        (combined.index >= start_dt) & (combined.index <= end_dt)
    ]
    if combined.empty:
        raise FetchError(f"Sin datos: el rango quedó vacío para {broker_name}")
    numeric = combined[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    invalid = (
        numeric.isna().any(axis=1)
        | (numeric["high"] < numeric["low"])
        | (numeric["high"] < numeric[["open", "close"]].max(axis=1))
        | (numeric["low"] > numeric[["open", "close"]].min(axis=1))
        | (numeric <= 0).any(axis=1)
    )
    if bool(invalid.any()):
        raise FetchError(
            f"Sin datos: {int(invalid.sum())} velas OHLC inválidas en {broker_name}"
        )

    output = discovery_path(identifier, timeframe, root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    combined.to_parquet(temporary)
    temporary.replace(output)
    return {
        "symbol": identifier,
        "broker_symbol": broker_name,
        "account": str(account),
        "timeframe": str(timeframe).upper(),
        "rows": int(len(combined)),
        "start": combined.index[0].isoformat(),
        "end": combined.index[-1].isoformat(),
        "path": output.as_posix(),
    }


__all__ = [
    "FetchError",
    "broker_symbol_for",
    "canonical_symbol",
    "discovery_path",
    "download",
]
