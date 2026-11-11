from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from .base import cache_path, normalize


def _record_freshness(
    ticker: str,
    timeframe: str,
    frame: "pd.DataFrame",
    path: Path,
    source: str,
) -> None:
    """Deja constancia de la frescura; nunca rompe la descarga."""
    try:
        from ..freshness import record

        last = None
        if len(frame):
            last = frame.index[-1]
            if hasattr(last, "to_pydatetime"):
                last = last.to_pydatetime()
        fetched = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        record(
            ticker,
            timeframe,
            last_bar_utc=last,
            fetched_at_utc=fetched,
            source=source,
        )
    except Exception:
        return


def fetch(ticker: str, start: str, end: str, cache_dir: str | Path, refresh: bool = False) -> pd.DataFrame:
    """Descarga OHLCV diario ajustado. Cachea en parquet."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, ticker, start, end)
    if path.exists() and not refresh:
        cached = pd.read_parquet(path)
        _record_freshness(ticker, "1d", cached, path, "yahoo")
        return cached

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        raise RuntimeError(f"Sin datos para {ticker} ({start} -> {end})")

    df = normalize(df)
    if df.empty:
        raise RuntimeError(f"Datos vacíos para {ticker} tras normalizar")
    df.to_parquet(path)
    metadata = {
        "provider": "yahoo",
        "ticker": ticker,
        "start": start,
        "end": end,
        "adjusted": True,
        "adjustment": "auto_adjust=True",
        "timezone": "date-only",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.with_suffix(".meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _record_freshness(ticker, "1d", df, path, "yahoo")
    return df
