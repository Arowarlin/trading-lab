"""ATR de Wilder, mediana RTH y cociente de reescalado US500/US100."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .candidate import WINDOW_END, WINDOW_START


class AtrError(ValueError):
    pass


def ny_naive_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Índice en hora de Nueva York sin tz, como la caché del US100."""
    out = frame.copy()
    index = pd.DatetimeIndex(out.index)
    if index.tz is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    out.index = index
    return out.sort_index()


def true_ranges(frame: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    ranges.iloc[0] = high.iloc[0] - low.iloc[0] if len(ranges) else np.nan
    return ranges


def wilder_atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    """Misma definición que ``ea_us100_engine``: media simple inicial y RMA."""
    if length <= 0:
        raise AtrError("length debe ser > 0")
    tr = true_ranges(frame)
    atr = pd.Series(np.nan, index=frame.index, dtype=float)
    if len(tr) < length:
        return atr
    atr.iloc[length - 1] = float(tr.iloc[:length].mean())
    for index in range(length, len(tr)):
        atr.iloc[index] = (atr.iloc[index - 1] * (length - 1) + tr.iloc[index]) / length
    return atr


def median_rth_atr(
    frame: pd.DataFrame,
    atr: pd.Series,
    *,
    start: str = WINDOW_START,
    end: str = WINDOW_END,
) -> tuple[float, int]:
    """Mediana del ATR en velas RTH (09:30–15:59 NY) dentro de la ventana."""
    local = ny_naive_index(frame)
    values = atr.copy()
    values.index = local.index
    window = values.loc[start:end].between_time("09:30", "15:59").dropna()
    if window.empty:
        raise AtrError(f"sin ATR RTH en la ventana {start} → {end}")
    return float(window.median()), int(window.shape[0])


def atr_ratio(
    us500: pd.DataFrame,
    us100: pd.DataFrame,
    *,
    start: str = WINDOW_START,
    end: str = WINDOW_END,
    length: int = 14,
) -> dict:
    """Cociente congelado ``mediana_atr(US500) / mediana_atr(US100)``."""
    us500_local = ny_naive_index(us500)
    us100_local = ny_naive_index(us100)
    atr500 = wilder_atr(us500_local, length)
    atr100 = wilder_atr(us100_local, length)
    median500, bars500 = median_rth_atr(us500_local, atr500, start=start, end=end)
    median100, bars100 = median_rth_atr(us100_local, atr100, start=start, end=end)
    if median500 <= 0 or median100 <= 0:
        raise AtrError("ATR mediano no positivo; no se puede reescalar")
    return {
        "method": "median_rth_atr14_ratio",
        "atr_len": int(length),
        "rth": "09:30-15:59",
        "window_start": start,
        "window_end": end,
        "us500_median_atr": round(median500, 8),
        "us100_median_atr": round(median100, 8),
        "us500_bars": bars500,
        "us100_bars": bars100,
        "ratio": round(median500 / median100, 8),
    }


__all__ = [
    "AtrError",
    "atr_ratio",
    "median_rth_atr",
    "ny_naive_index",
    "true_ranges",
    "wilder_atr",
]
