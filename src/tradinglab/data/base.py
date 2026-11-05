from __future__ import annotations

from pathlib import Path

import pandas as pd


def safe_ticker(ticker: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in ticker).upper()


def cache_path(cache_dir: str | Path, ticker: str, start: str, end: str) -> Path:
    return Path(cache_dir) / f"{safe_ticker(ticker)}__{start}__{end}.parquet"


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    wanted = ["open", "high", "low", "close", "volume"]
    missing = [c for c in wanted if c not in df.columns]
    if missing:
        raise RuntimeError(f"Faltan columnas {missing}")
    df = df[wanted]
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna()
