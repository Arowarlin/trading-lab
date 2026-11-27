"""Descarga M1 de Dukascopy por HTTP directo (sin dependencias nuevas).

El feed público sirve un fichero diario por lado (BID/ASK) con 1.440 velas M1
codificadas en LZMA. Cada registro binario ocupa 24 bytes:

    offset_segundos, open, close, low, high, volumen  (big-endian)

Los precios son enteros escalados por el ``point`` del instrumento. Dukascopy
rellena los minutos sin mercado con velas de volumen 0; aquí se descartan para
no fabricar velas en huecos.

La caché es un único ``data/cache/dukascopy/<SYMBOL>_M1.parquet`` en UTC. La
descarga va por meses, reanuda saltando meses ya completos y reescribe el
parquet al cerrar cada mes.

Se usa **HTTP** directo al feed público, sin credenciales y sin proxy. Si el
feed responde 301 a HTTPS, ``httpx`` sigue el redirect; el WAF puede limitar
las ráfagas con 429/503, por eso hay reintentos y una tasa máxima.
"""

from __future__ import annotations

import lzma
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import pandas as pd

from ..config import ROOT

DUKASCOPY_BASE = "http://datafeed.dukascopy.com/datafeed"
DUKASCOPY_DIR = ROOT / "data" / "cache" / "dukascopy"

RECORD = struct.Struct(">IIIIIf")
BASE_COLUMNS = ("open", "high", "low", "close", "volume")
ASK_COLUMNS = ("ask_open", "ask_high", "ask_low", "ask_close", "ask_volume")
COLUMNS = BASE_COLUMNS + ASK_COLUMNS

# nombre canónico -> (instrumento del feed, escala de precio)
INSTRUMENTS = {
    "US100": ("USATECHIDXUSD", 0.001),
    "US500": ("USA500IDXUSD", 0.001),
    "US30": ("USA30IDXUSD", 0.001),
    "XAUUSD": ("XAUUSD", 0.001),
    "EURUSD": ("EURUSD", 0.00001),
    "GBPUSD": ("GBPUSD", 0.00001),
    "USDJPY": ("USDJPY", 0.001),
}
SYMBOLS = tuple(INSTRUMENTS)

# Fechas verificadas contra el feed el 2026-11-21 (primer fichero con datos).
FIRST_AVAILABLE = {
    "US100": "2011-09-18",
    "US500": "2011-09-18",
    "US30": "2013-09-30",
    "XAUUSD": "2003-05-05",
    "EURUSD": "2003-05-04",
    "GBPUSD": "2003-05-04",
    "USDJPY": "2003-05-04",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.dukascopy.com/",
    "Accept": "*/*",
}
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class DukascopyError(RuntimeError):
    pass


class DukascopyDataError(DukascopyError):
    """El feed respondió, pero con velas inválidas (ENG-1 C-13): no es de red."""


class _RateLimiter:
    """Reparte peticiones a una tasa máxima sin serializar las respuestas."""

    def __init__(self, rate_per_s: float) -> None:
        self.interval = 1.0 / float(rate_per_s) if rate_per_s > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            target = max(now, self._next)
            self._next = target + self.interval
        delay = target - now
        if delay > 0:
            time.sleep(delay)


def normalize_symbol(symbol: str) -> str:
    key = str(symbol or "").strip().upper()
    if key not in INSTRUMENTS:
        valid = ", ".join(SYMBOLS)
        raise DukascopyError(f"símbolo no soportado: {symbol!r}; usa uno de: {valid}")
    return key


def instrument_for(symbol: str) -> str:
    return INSTRUMENTS[normalize_symbol(symbol)][0]


def point_for(symbol: str) -> float:
    return INSTRUMENTS[normalize_symbol(symbol)][1]


def first_available(symbol: str) -> str:
    return FIRST_AVAILABLE[normalize_symbol(symbol)]


def cache_path(symbol: str, *, root: Path = ROOT) -> Path:
    key = normalize_symbol(symbol)
    return Path(root) / "data" / "cache" / "dukascopy" / f"{key}_M1.parquet"


def candle_url(instrument: str, day: date, side: str = "BID") -> str:
    side_key = str(side or "BID").strip().upper()
    if side_key not in {"BID", "ASK"}:
        raise DukascopyError(f"lado no soportado: {side}")
    # Dukascopy usa mes 0-based en la ruta.
    return (
        f"{DUKASCOPY_BASE}/{str(instrument).strip()}/"
        f"{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/"
        f"{side_key}_candles_min_1.bi5"
    )


def _empty(side: str = "BID") -> pd.DataFrame:
    columns = BASE_COLUMNS if str(side).upper() == "BID" else ASK_COLUMNS
    return pd.DataFrame(columns=list(columns))


def decode_candles(
    payload: bytes,
    *,
    day: date,
    point: float,
    side: str = "BID",
) -> pd.DataFrame:
    """Decodifica un fichero diario de velas M1 y descarta volumen 0."""
    side_key = str(side or "BID").strip().upper()
    if side_key not in {"BID", "ASK"}:
        raise DukascopyError(f"lado no soportado: {side}")
    if not payload:
        return _empty(side_key)
    try:
        raw = lzma.decompress(payload)
    except lzma.LZMAError as exc:
        raise DukascopyError("fichero .bi5 no es LZMA válido") from exc
    if len(raw) % RECORD.size:
        raise DukascopyError(
            f"tamaño binario inválido: {len(raw)} no es múltiplo de {RECORD.size}"
        )
    scale = float(point)
    if scale <= 0:
        raise DukascopyError("el point debe ser > 0")
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    rows: list[tuple[datetime, float, float, float, float, float]] = []
    invalid = 0
    for offset, open_i, close_i, low_i, high_i, volume in RECORD.iter_unpack(raw):
        if float(volume) <= 0:
            continue
        open_ = float(open_i) * scale
        high = float(high_i) * scale
        low = float(low_i) * scale
        close = float(close_i) * scale
        if (
            open_ <= 0
            or high <= 0
            or low <= 0
            or close <= 0
            or high < low
            or high < max(open_, close)
            or low > min(open_, close)
        ):
            invalid += 1
            continue
        stamp = start + timedelta(seconds=int(offset))
        rows.append((stamp, open_, high, low, close, float(volume)))
    if invalid:
        raise DukascopyDataError(
            f"{invalid} velas OHLC inválidas en {day.isoformat()} ({side_key})"
        )
    if not rows:
        return _empty(side_key)
    base = pd.DataFrame(
        rows, columns=["time", "open", "high", "low", "close", "volume"]
    ).set_index("time")
    if side_key == "ASK":
        base.columns = list(ASK_COLUMNS)
    base.index = pd.DatetimeIndex(base.index, name="time")
    return base.sort_index()


def _fetch_day(
    client: httpx.Client,
    instrument: str,
    day: date,
    side: str,
    point: float,
    *,
    limiter: _RateLimiter | None = None,
    retries: int = 4,
    backoff_s: float = 1.0,
) -> pd.DataFrame:
    url = candle_url(instrument, day, side)
    attempts = max(1, int(retries) + 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            if limiter is not None:
                limiter.wait()
            response = client.get(url)
            if response.status_code == 404:
                return _empty(side)
            if response.status_code in _RETRY_STATUS:
                last_error = DukascopyError(
                    f"Dukascopy HTTP {response.status_code} en {url}"
                )
            elif response.status_code >= 400:
                raise DukascopyError(
                    f"Dukascopy HTTP {response.status_code} en {url}"
                )
            else:
                return decode_candles(
                    response.content,
                    day=day,
                    point=point,
                    side=side,
                )
        except DukascopyError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt >= attempts - 1:
            break
        wait = float(backoff_s) * (2**attempt)
        if isinstance(last_error, DukascopyError) and "429" in str(last_error):
            wait = max(wait, 5.0)
        if wait > 0:
            time.sleep(wait)
    raise DukascopyError(
        f"Dukascopy no disponible para {instrument} {day.isoformat()} "
        f"({side}): {type(last_error).__name__ if last_error else 'sin respuesta'}"
    )


def load_cache(symbol: str, *, root: Path = ROOT) -> pd.DataFrame:
    path = cache_path(symbol, root=root)
    if not path.exists():
        raise DukascopyError(f"Sin datos: no existe {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise DukascopyError(
            f"Sin datos: no se pudo leer {path} ({type(exc).__name__}: {exc})"
        ) from exc
    frame = frame.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    frame.index = index
    frame.index.name = "time"
    frame = frame.sort_index()
    return frame.loc[~frame.index.duplicated(keep="last")]


def _month_start(stamp: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(stamp.year, stamp.month, 1, tz="UTC")


def _next_month(stamp: pd.Timestamp) -> pd.Timestamp:
    return _month_start(stamp) + pd.offsets.MonthBegin(1)


def _parse_start(value: str | None, symbol: str) -> pd.Timestamp:
    text = str(value or first_available(symbol))
    stamp = pd.Timestamp(text)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _parse_end(value: str | None, now: datetime) -> pd.Timestamp:
    if value:
        stamp = pd.Timestamp(str(value))
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        if len(str(value)) <= 10:
            stamp = stamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        return stamp
    current = pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    return current.normalize() - pd.Timedelta(microseconds=1)


def _read_existing(symbol: str, root: Path) -> pd.DataFrame:
    path = cache_path(symbol, root=root)
    if not path.exists():
        return pd.DataFrame(columns=list(COLUMNS))
    return load_cache(symbol, root=root)


def _write_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary)
    temporary.replace(path)


def download(
    symbol: str,
    *,
    start: str | None = None,
    end: str | None = None,
    workers: int = 4,
    rate_per_s: float = 5.0,
    include_ask: bool = True,
    force: bool = False,
    root: Path = ROOT,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    retries: int = 3,
    backoff_s: float = 1.0,
    pause_s: float = 0.0,
) -> dict[str, Any]:
    """Descarga por meses y deja la caché M1 lista para reanudar."""
    key = normalize_symbol(symbol)
    instrument, point = INSTRUMENTS[key]
    start_dt = _parse_start(start, key)
    end_dt = _parse_end(end, now or datetime.now(timezone.utc))
    if end_dt <= start_dt:
        raise DukascopyError("el fin debe ser posterior al inicio")
    if int(workers) < 1:
        raise DukascopyError("workers debe ser >= 1")

    existing = _read_existing(key, root)
    completed: set[str] = set()
    if len(existing):
        last_cached_month = existing.index.max().strftime("%Y-%m")
        for month_key, group in existing.groupby(existing.index.strftime("%Y-%m")):
            # Un mes solo se salta si llegó a la segunda mitad: evita dar por
            # completo un mes cortado por un --to parcial o una caída.
            last_day = group.index.max()
            if int(last_day.day) < 20:
                continue
            # El último mes de la caché es donde se cortó la ejecución anterior:
            # solo está completo si llega a su último día laborable (ENG-1 C-02).
            if str(month_key) == last_cached_month:
                month_first = pd.Timestamp(last_day.year, last_day.month, 1)
                last_weekday = pd.bdate_range(month_first, month_first + pd.offsets.MonthEnd(0))[-1]
                if last_day.date() < last_weekday.date():
                    continue
            completed.add(str(month_key))
    current_month = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    ask_months: set[str] = set()
    if include_ask and len(existing) and "ask_close" in existing.columns:
        with_ask = existing.loc[
            pd.to_numeric(existing["ask_close"], errors="coerce").notna()
        ]
        ask_months = set(with_ask.index.strftime("%Y-%m"))
    limiter = _RateLimiter(rate_per_s)
    own_client = client is None
    http = client or httpx.Client(
        timeout=60.0,
        follow_redirects=True,
        headers=_HEADERS,
    )
    fetched = 0
    skipped = 0
    empty_days = 0
    months: list[dict[str, Any]] = []

    def _pair(day: date) -> tuple[date, pd.DataFrame, pd.DataFrame]:
        bid = _fetch_day(
            http,
            instrument,
            day,
            "BID",
            point,
            limiter=limiter,
            retries=retries,
            backoff_s=backoff_s,
        )
        if bid.empty or not include_ask:
            return day, bid, _empty("ASK")
        try:
            ask = _fetch_day(
                http,
                instrument,
                day,
                "ASK",
                point,
                limiter=limiter,
                retries=retries,
                backoff_s=backoff_s,
            )
        except DukascopyError:
            # El BID es obligatorio; el ASK es opcional ("si está").
            ask = _empty("ASK")
        return day, bid, ask

    try:
        cursor = _month_start(start_dt)
        while cursor <= end_dt:
            month_key = cursor.strftime("%Y-%m")
            month_end = min(end_dt, _next_month(cursor) - pd.Timedelta(nanoseconds=1))
            month_from = max(start_dt, cursor)
            if (
                not force
                and month_key in completed
                and month_key != current_month
                and (not include_ask or month_key in ask_months)
            ):
                skipped += 1
                cursor = _next_month(cursor)
                continue
            days = [
                stamp.date()
                for stamp in pd.date_range(
                    month_from.normalize(), month_end.normalize(), freq="D"
                )
                if stamp.weekday() != 5  # sábado: mercado cerrado
            ]
            bid_frames: list[pd.DataFrame] = []
            ask_frames: list[pd.DataFrame] = []
            failed: list[date] = []
            invalid_days: list[str] = []
            with ThreadPoolExecutor(max_workers=int(workers)) as pool:
                futures = {pool.submit(_pair, day): day for day in days}
                for future in as_completed(futures):
                    day = futures[future]
                    try:
                        _, bid, ask = future.result()
                    except DukascopyDataError as exc:
                        invalid_days.append(str(exc))
                        continue
                    except DukascopyError:
                        failed.append(day)
                        continue
                    if bid.empty:
                        empty_days += 1
                        continue
                    bid_frames.append(bid)
                    if not ask.empty:
                        ask_frames.append(ask)
            # Segundo pase en paralelo para timeouts transitorios del feed.
            if failed:
                retry = list(failed)
                failed = []
                with ThreadPoolExecutor(
                    max_workers=min(4, len(retry))
                ) as pool:
                    futures = {pool.submit(_pair, day): day for day in retry}
                    for future in as_completed(futures):
                        day = futures[future]
                        try:
                            _, bid, ask = future.result()
                        except DukascopyDataError as exc:
                            invalid_days.append(str(exc))
                            continue
                        except DukascopyError:
                            failed.append(day)
                            continue
                        if bid.empty:
                            empty_days += 1
                            continue
                        bid_frames.append(bid)
                        if not ask.empty:
                            ask_frames.append(ask)
            if invalid_days:
                # ENG-1 C-13: reintentar no lo arregla; se dice qué pasa.
                raise DukascopyDataError(
                    f"OHLC inválido en {month_key}: {'; '.join(sorted(invalid_days)[:5])}. "
                    "El feed devolvió datos incoherentes, no es un fallo de red; "
                    "reintentar no lo arregla"
                )
            if failed:
                sample = ", ".join(day.isoformat() for day in failed[:5])
                raise DukascopyError(
                    f"{len(failed)} días sin respuesta en {month_key} "
                    f"({sample}); vuelve a ejecutar para reanudar"
                )
            if not bid_frames:
                months.append(
                    {
                        "month": month_key,
                        "rows": 0,
                        "ask_rows": 0,
                        "empty_days": len(days),
                    }
                )
                if pause_s > 0:
                    time.sleep(float(pause_s))
                cursor = _next_month(cursor)
                continue
            bid = pd.concat(bid_frames).sort_index()
            bid = bid.loc[~bid.index.duplicated(keep="last")]
            bid = bid.loc[
                (bid.index >= month_from) & (bid.index <= month_end)
            ]
            if ask_frames:
                ask = pd.concat(ask_frames).sort_index()
                ask = ask.loc[~ask.index.duplicated(keep="last")]
                bid = bid.join(ask, how="left")
            for column in ASK_COLUMNS:
                if column not in bid.columns:
                    bid[column] = pd.NA
                bid[column] = pd.to_numeric(bid[column], errors="coerce")
            bid = bid.loc[:, list(COLUMNS)]
            if existing is not None and len(existing):
                outside = existing.loc[
                    (existing.index < month_from) | (existing.index > month_end)
                ]
                existing = pd.concat([outside, bid]).sort_index()
                existing = existing.loc[
                    ~existing.index.duplicated(keep="last")
                ]
            else:
                existing = bid
            _write_atomic(existing, cache_path(key, root=root))
            completed.add(month_key)
            fetched += 1
            month_ask = int(pd.to_numeric(bid["ask_close"], errors="coerce").notna().sum())
            months.append(
                {
                    "month": month_key,
                    "rows": int(len(bid)),
                    "ask_rows": month_ask,
                    "empty_days": len(days) - len(bid_frames),
                }
            )
            if progress is not None:
                progress(months[-1])
            if pause_s > 0:
                time.sleep(float(pause_s))
            cursor = _next_month(cursor)
    finally:
        if own_client:
            http.close()

    if existing is None or len(existing) == 0:
        raise DukascopyError(f"Sin datos: no hay velas M1 para {key}")
    output = cache_path(key, root=root)
    total_ask = (
        int(pd.to_numeric(existing["ask_close"], errors="coerce").notna().sum())
        if "ask_close" in existing.columns
        else 0
    )
    return {
        "symbol": key,
        "instrument": instrument,
        "rows": int(len(existing)),
        "ask_rows": int(total_ask),
        "start": existing.index[0].isoformat(),
        "end": existing.index[-1].isoformat(),
        "path": output.as_posix(),
        "months_fetched": int(fetched),
        "months_skipped": int(skipped),
        "months": months,
        "empty_days": int(empty_days),
    }


__all__ = [
    "ASK_COLUMNS",
    "BASE_COLUMNS",
    "COLUMNS",
    "DUKASCOPY_BASE",
    "DUKASCOPY_DIR",
    "DukascopyError",
    "FIRST_AVAILABLE",
    "INSTRUMENTS",
    "SYMBOLS",
    "cache_path",
    "candle_url",
    "decode_candles",
    "download",
    "first_available",
    "instrument_for",
    "load_cache",
    "normalize_symbol",
    "point_for",
]
