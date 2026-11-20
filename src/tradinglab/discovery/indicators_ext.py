"""Indicadores extendidos del Discovery Lab (pandas, sin look-ahead).

Todo se calcula con barras cerradas. El índice debe ser **tz-aware**: nunca se
asume UTC. Los pivotes se confirman con ``right`` barras y se desplazan
``right`` posiciones; los niveles de sesión y el VWAP se reinician al inicio de
la sesión local, incluida una sesión que cruza la medianoche.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import atr, ema, rsi, sma, zscore

__all__ = [
    "adx",
    "atr_pct_rank",
    "bollinger",
    "bos_down",
    "bos_up",
    "cci",
    "choch_down",
    "choch_up",
    "donchian",
    "donchian_level",
    "keltner",
    "macd",
    "opening_range",
    "prev_day_level",
    "prev_session_level",
    "range_compression",
    "realized_vol",
    "stochastic",
    "swing_high",
    "swing_low",
    "vwap_session",
]


def _series(frame: pd.DataFrame | pd.Series) -> pd.Series:
    return frame.astype(float) if isinstance(frame, pd.Series) else frame["close"].astype(float)


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.Series:
    _require_aware_series(series)
    if fast >= slow:
        raise ValueError("macd: fast debe ser menor que slow")
    return ema(series, fast) - ema(series, slow)


def adx(frame: pd.DataFrame, n: int = 14) -> pd.Series:
    _require_aware_index(frame.index)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr_n = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus = plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr_n.replace(0, np.nan)
    minus = minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr_n.replace(0, np.nan)
    dx = ((plus - minus).abs() / (plus + minus).replace(0, np.nan)) * 100.0
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def bollinger(series: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    _require_aware_series(series)
    mid = sma(series, n)
    std = series.rolling(n, min_periods=n).std()
    return pd.DataFrame({"mid": mid, "upper": mid + k * std, "lower": mid - k * std})


def stochastic(frame: pd.DataFrame, n: int = 14) -> pd.Series:
    _require_aware_index(frame.index)
    high = frame["high"].astype(float).rolling(n, min_periods=n).max()
    low = frame["low"].astype(float).rolling(n, min_periods=n).min()
    close = frame["close"].astype(float)
    return (close - low) / (high - low).replace(0, np.nan) * 100.0


def cci(frame: pd.DataFrame, n: int = 20) -> pd.Series:
    _require_aware_index(frame.index)
    typical = (frame["high"] + frame["low"] + frame["close"]).astype(float) / 3.0
    mean = typical.rolling(n, min_periods=n).mean()
    deviation = typical.rolling(n, min_periods=n).apply(
        lambda values: float(np.mean(np.abs(values - np.mean(values)))), raw=True
    )
    return (typical - mean) / (0.015 * deviation.replace(0, np.nan))


def donchian(frame: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    _require_aware_index(frame.index)
    upper = frame["high"].astype(float).rolling(n, min_periods=n).max()
    lower = frame["low"].astype(float).rolling(n, min_periods=n).min()
    return pd.DataFrame({"upper": upper, "lower": lower, "mid": (upper + lower) / 2.0})


def donchian_level(frame: pd.DataFrame, n: int = 20, which: str = "high") -> pd.Series:
    bands = donchian(frame, n)
    return (bands["upper"] if which == "high" else bands["lower"]).shift(1)


def keltner(frame: pd.DataFrame, n: int = 20, mult: float = 2.0) -> pd.DataFrame:
    _require_aware_index(frame.index)
    mid = ema(frame["close"].astype(float), n)
    band = atr(frame, n) * mult
    return pd.DataFrame({"mid": mid, "upper": mid + band, "lower": mid - band})


def _require_aware_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Exige un índice con zona horaria; nunca asume UTC."""
    if not isinstance(index, pd.DatetimeIndex):
        try:
            index = pd.DatetimeIndex(index)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "el índice debe ser un DatetimeIndex con zona horaria (tz-aware); "
                "no se asume UTC. Usa discovery.data_sources.load_source()."
            ) from exc
    if index.tz is None:
        raise ValueError(
            "el índice debe tener zona horaria (tz-aware); no se asume UTC. "
            "Usa discovery.data_sources.load_source()."
        )
    return index


def _require_aware_series(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex) or series.index.tz is None:
        raise ValueError(
            "el índice debe ser un DatetimeIndex con zona horaria (tz-aware); "
            "no se asume UTC."
        )
    return series


def _local_index(index: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    aware = _require_aware_index(index)
    return aware.tz_convert(tz)


def _hm(value: str) -> int:
    text = str(value).strip()
    if len(text) != 5 or text[2] != ":":
        raise ValueError(f"hora inválida: {value!r}; usa HH:MM")
    hour, minute = int(text[:2]), int(text[3:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"hora inválida: {value!r}")
    return hour * 60 + minute


def _session_keys(
    index: pd.DatetimeIndex,
    tz: str,
    start: str,
    end: str,
) -> tuple[pd.DatetimeIndex, pd.Series, pd.Series]:
    """Devuelve (índice local, máscara de sesión, clave de la sesión).

    La clave es la fecha local en la que empezó la sesión. Si la sesión cruza
    la medianoche, las barras posteriores a las 00:00 conservan la clave del
    día anterior; las barras fuera de la sesión quedan con ``NaT``.
    """
    local = _local_index(index, tz)
    start_min = _hm(start)
    end_min = _hm(end)
    if start_min == end_min:
        raise ValueError("la sesión no puede empezar y terminar a la misma hora")
    minutes = local.hour * 60 + local.minute
    if start_min < end_min:
        mask = (minutes >= start_min) & (minutes < end_min)
    else:
        mask = (minutes >= start_min) | (minutes < end_min)
    mask_series = pd.Series(mask, index=index)
    key = pd.Series(local.normalize(), index=index)
    if start_min > end_min:
        before_midnight = pd.Series(minutes < end_min, index=index)
        key = key.where(~before_midnight, key - pd.Timedelta(days=1))
    key = key.where(mask_series)
    return local, mask_series, key


def _session_mask(
    index: pd.DatetimeIndex,
    tz: str,
    start: str,
    end: str,
) -> tuple[pd.DatetimeIndex, pd.Series]:
    local, mask, _key = _session_keys(index, tz, start, end)
    return local, mask


def vwap_session(
    frame: pd.DataFrame,
    *,
    tz: str = "America/New_York",
    start: str = "09:35",
    end: str = "16:00",
) -> pd.Series:
    """VWAP de la sesión local; se reinicia en ``start`` y sigue tras medianoche."""
    _local, mask, key = _session_keys(frame.index, tz, start, end)
    typical = (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0
    if "volume" in frame.columns:
        volume = frame["volume"].astype(float)
    elif "tickvol" in frame.columns:
        volume = frame["tickvol"].astype(float)
    else:
        volume = pd.Series(1.0, index=frame.index)
    volume = volume.fillna(1.0).clip(lower=0.0)
    volume = volume.where(volume > 0, 1.0)
    sub = pd.DataFrame({"tp": typical, "vol": volume, "key": key}, index=frame.index).loc[mask]
    sub["pv"] = sub["tp"] * sub["vol"]
    sub["cum_pv"] = sub.groupby("key")["pv"].cumsum()
    sub["cum_vol"] = sub.groupby("key")["vol"].cumsum()
    value = sub["cum_pv"] / sub["cum_vol"].replace(0, np.nan)
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    out.loc[value.index] = value.to_numpy()
    return out


def realized_vol(series: pd.Series, n: int = 20) -> pd.Series:
    _require_aware_series(series)
    return series.pct_change().rolling(n, min_periods=n).std()


def atr_pct_rank(frame: pd.DataFrame, n: int = 14, lookback: int = 100) -> pd.Series:
    _require_aware_index(frame.index)
    percent = atr(frame, n) / frame["close"].astype(float)
    return percent.rolling(lookback, min_periods=max(10, lookback // 2)).rank(pct=True)


def range_compression(frame: pd.DataFrame, n: int = 20) -> pd.Series:
    _require_aware_index(frame.index)
    rng = frame["high"].astype(float) - frame["low"].astype(float)
    return rng / atr(frame, n).replace(0, np.nan)


def _pivot(values: pd.Series, left: int, right: int, mode: str) -> pd.Series:
    array = values.to_numpy(dtype=float)
    out = np.full(len(array), np.nan)
    for index in range(left, len(array) - right):
        window = array[index - left : index + right + 1]
        if mode == "high" and array[index] >= np.nanmax(window):
            out[index + right] = array[index]
        elif mode == "low" and array[index] <= np.nanmin(window):
            out[index + right] = array[index]
    return pd.Series(out, index=values.index)


def swing_high(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    _require_aware_index(frame.index)
    return _pivot(frame["high"].astype(float), left, right, "high")


def swing_low(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    _require_aware_index(frame.index)
    return _pivot(frame["low"].astype(float), left, right, "low")


def _filled(series: pd.Series) -> pd.Series:
    return series.ffill()


def bos_up(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    level = _filled(swing_high(frame, left, right))
    return frame["close"].astype(float) > level


def bos_down(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    level = _filled(swing_low(frame, left, right))
    return frame["close"].astype(float) < level


def choch_up(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    return bos_up(frame, left, right) & ~bos_up(frame, left, right).shift(1, fill_value=False)


def choch_down(frame: pd.DataFrame, left: int = 5, right: int = 5) -> pd.Series:
    return bos_down(frame, left, right) & ~bos_down(frame, left, right).shift(1, fill_value=False)


def _session_ranges(frame: pd.DataFrame, tz: str, start: str, end: str) -> pd.DataFrame:
    _local, mask, key = _session_keys(frame.index, tz, start, end)
    sub = frame.loc[mask].copy()
    sub["_key"] = key.loc[mask]
    grouped = sub.groupby("_key")
    return pd.DataFrame({"high": grouped["high"].max(), "low": grouped["low"].min()})


def prev_session_level(
    frame: pd.DataFrame,
    *,
    tz: str = "America/New_York",
    start: str = "09:35",
    end: str = "16:00",
    which: str = "high",
) -> pd.Series:
    ranges = _session_ranges(frame, tz, start, end)
    _local, mask, key = _session_keys(frame.index, tz, start, end)
    previous = ranges.sort_index()[which].shift(1)
    mapping = {stamp: value for stamp, value in previous.items()}
    result = key.where(mask).map(mapping)
    return pd.Series(result, index=frame.index, dtype=float).where(mask)


def prev_day_level(
    frame: pd.DataFrame,
    *,
    tz: str = "America/New_York",
    which: str = "high",
) -> pd.Series:
    local = _local_index(frame.index, tz)
    key = pd.Series(local.normalize(), index=frame.index)
    grouped = frame.assign(_key=key).groupby("_key")
    values = grouped[which].max().shift(1)
    mapping = {stamp: value for stamp, value in values.items()}
    result = key.map(mapping)
    return pd.Series(result, index=frame.index, dtype=float)


def opening_range(
    frame: pd.DataFrame,
    *,
    tz: str = "America/New_York",
    start: str = "09:35",
    end: str = "23:59",
    minutes: int = 15,
    which: str = "high",
) -> pd.Series:
    """Máximo/mínimo de los primeros ``minutes`` de la sesión local.

    El valor solo está disponible cuando el rango ya cerró y pertenece a la
    sesión que empezó en ``start``, aunque cruce la medianoche.
    """
    local, mask, key = _session_keys(frame.index, tz, start, end)
    start_min = _hm(start)
    minutes_of_day = local.hour * 60 + local.minute
    relative = (minutes_of_day - start_min) % 1440
    window = int(minutes)
    inside = mask & (relative < window)
    sub = frame.loc[inside].copy()
    sub["_key"] = key.loc[inside]
    aggregation = "max" if which == "high" else "min"
    values = sub.groupby("_key")[which].agg(aggregation)
    mapping = {stamp: value for stamp, value in values.items()}
    result = key.where(mask).map(mapping)
    after = mask & (relative >= window)
    return pd.Series(result, index=frame.index, dtype=float).where(after)


__all__ += ["sma", "ema", "atr", "rsi", "zscore"]
