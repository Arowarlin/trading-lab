"""Ticks de Dukascopy: descarga, decodificación y métricas de spread.

Solo lectura de datos públicos. No envía órdenes ni se conecta a un bróker.
Los archivos `.bi5` están comprimidos con LZMA y cada registro binario tiene
20 bytes: offset en ms, ask, bid, volumen ask y volumen bid (big-endian).
"""
from __future__ import annotations

import lzma
import struct
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from ..config import ROOT

DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
TICK_COLUMNS = ("ts", "bid", "ask", "bid_volume", "ask_volume")
POINT_SIZES = {
    "EURUSD": 1e-5,
    "GBPUSD": 1e-5,
    "USDJPY": 1e-3,
    "XAUUSD": 1e-3,
}
RECORD = struct.Struct(">IIIff")
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class TickError(RuntimeError):
    pass


def point_size(symbol: str, point: float | None = None) -> float:
    if point is not None:
        if point <= 0:
            raise TickError("el point debe ser > 0")
        return float(point)
    value = POINT_SIZES.get(str(symbol).upper())
    if value is None:
        raise TickError(
            f"sin point para {symbol}; indícalo con --point (p. ej. 0.00001)"
        )
    return value


def hour_url(symbol: str, day: date, hour: int) -> str:
    if not 0 <= int(hour) <= 23:
        raise TickError(f"hora inválida: {hour}")
    # Dukascopy usa mes 0-based en la ruta.
    return (
        f"{DUKASCOPY_BASE}/{str(symbol).upper()}/"
        f"{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/{int(hour):02d}h_ticks.bi5"
    )


def decode_bi5(
    payload: bytes,
    *,
    symbol: str,
    day: date,
    hour: int,
    point: float | None = None,
) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame(columns=TICK_COLUMNS + ("spread", "spread_bps"))
    try:
        raw = lzma.decompress(payload)
    except lzma.LZMAError as exc:
        raise TickError("archivo .bi5 no es LZMA válido") from exc
    if len(raw) % RECORD.size:
        raise TickError(
            f"tamaño binario inválido: {len(raw)} no es múltiplo de {RECORD.size}"
        )
    scale = point_size(symbol, point)
    start = datetime(day.year, day.month, day.day, int(hour), tzinfo=timezone.utc)
    rows = []
    for offset, ask_i, bid_i, ask_volume, bid_volume in RECORD.iter_unpack(raw):
        ask = float(ask_i) * scale
        bid = float(bid_i) * scale
        rows.append(
            {
                "ts": start + timedelta(milliseconds=int(offset)),
                "bid": bid,
                "ask": ask,
                "bid_volume": float(bid_volume),
                "ask_volume": float(ask_volume),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=TICK_COLUMNS + ("spread", "spread_bps"))
    frame = frame.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    frame["spread"] = frame["ask"] - frame["bid"]
    mid = (frame["ask"] + frame["bid"]) / 2.0
    frame["spread_bps"] = (frame["spread"] / mid.replace(0, pd.NA)) * 10_000
    return frame


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUSES
    return isinstance(exc, (httpx.TransportError, TimeoutError))


def fetch_hour(
    symbol: str,
    day: date,
    hour: int,
    *,
    point: float | None = None,
    client: httpx.Client | None = None,
    retries: int = 2,
    backoff_s: float = 1.0,
) -> pd.DataFrame:
    own = client is None
    http = client or httpx.Client(timeout=20, follow_redirects=True)
    url = hour_url(symbol, day, hour)
    attempts = max(1, int(retries) + 1)
    try:
        for attempt in range(attempts):
            try:
                response = http.get(url)
                if response.status_code == 404:
                    return pd.DataFrame(
                        columns=TICK_COLUMNS + ("spread", "spread_bps")
                    )
                response.raise_for_status()
                return decode_bi5(
                    response.content,
                    symbol=symbol,
                    day=day,
                    hour=hour,
                    point=point,
                )
            except Exception as exc:
                if attempt >= attempts - 1 or not _retryable(exc):
                    if isinstance(exc, TickError):
                        raise
                    if isinstance(exc, httpx.HTTPStatusError):
                        raise TickError(
                            f"Dukascopy HTTP {exc.response.status_code} en {url}"
                        ) from exc
                    raise TickError(
                        f"Dukascopy no disponible: {type(exc).__name__}"
                    ) from exc
                wait = float(backoff_s) * (2**attempt)
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code == 429
                ):
                    wait = max(wait, 5.0)
                if wait > 0:
                    import time

                    time.sleep(wait)
        raise TickError("sin intentos")  # pragma: no cover
    finally:
        if own:
            http.close()


def fetch_day(
    symbol: str,
    day: date,
    *,
    hours: list[int] | None = None,
    point: float | None = None,
    client: httpx.Client | None = None,
    retries: int = 2,
    min_interval_s: float = 0.5,
) -> pd.DataFrame:
    selected = list(range(24)) if hours is None else [int(hour) for hour in hours]
    frames = []
    for index, hour in enumerate(selected):
        if index and min_interval_s > 0:
            import time

            time.sleep(float(min_interval_s))
        frame = fetch_hour(
            symbol,
            day,
            hour,
            point=point,
            client=client,
            retries=retries,
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=TICK_COLUMNS + ("spread", "spread_bps"))
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def save_ticks(
    frame: pd.DataFrame,
    symbol: str,
    day: date,
    *,
    out_dir: str | Path | None = None,
) -> Path:
    if frame.empty:
        raise TickError("no hay ticks para guardar")
    target = Path(out_dir) if out_dir else ROOT / "data" / "cache" / "ticks"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{str(symbol).upper()}_{day:%Y%m%d}.parquet"
    frame.to_parquet(path, index=False)
    return path


def hourly_spread_bps(
    frame_or_path: pd.DataFrame | str | Path,
) -> pd.Series:
    """Mediana de spread bps por hora UTC, para alimentar el coste intradía."""
    frame = (
        pd.read_parquet(frame_or_path)
        if isinstance(frame_or_path, (str, Path))
        else frame_or_path
    )
    if frame.empty or "spread_bps" not in frame.columns:
        raise TickError("parquet de ticks sin columna spread_bps")
    stamps = pd.to_datetime(frame["ts"], utc=True)
    values = pd.to_numeric(frame["spread_bps"], errors="coerce")
    valid = values.notna()
    if not valid.any():
        raise TickError("parquet de ticks sin spread válido")
    hourly = values[valid].groupby(stamps[valid].dt.hour).median()
    return hourly.sort_index()


def summarize_ticks(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {
            "ticks": 0,
            "start": None,
            "end": None,
            "median_spread": None,
            "p95_spread": None,
            "median_spread_bps": None,
        }
    return {
        "ticks": int(len(frame)),
        "start": str(frame["ts"].iloc[0]),
        "end": str(frame["ts"].iloc[-1]),
        "median_spread": float(frame["spread"].median()),
        "p95_spread": float(frame["spread"].quantile(0.95)),
        "median_spread_bps": float(frame["spread_bps"].median()),
    }


def parse_hours(value: str) -> list[int]:
    hours: set[int] = set()
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                first, last = int(start), int(end)
            except ValueError as exc:
                raise TickError(f"rango de horas inválido: {part}") from exc
            if first > last:
                raise TickError(f"rango de horas invertido: {part}")
            hours.update(range(first, last + 1))
        else:
            try:
                hours.add(int(part))
            except ValueError as exc:
                raise TickError(f"hora inválida: {part}") from exc
    if not hours or min(hours) < 0 or max(hours) > 23:
        raise TickError("las horas deben estar entre 0 y 23")
    return sorted(hours)


__all__ = [
    "DUKASCOPY_BASE",
    "POINT_SIZES",
    "TICK_COLUMNS",
    "TickError",
    "decode_bi5",
    "fetch_day",
    "fetch_hour",
    "hour_url",
    "hourly_spread_bps",
    "parse_hours",
    "point_size",
    "save_ticks",
    "summarize_ticks",
]
