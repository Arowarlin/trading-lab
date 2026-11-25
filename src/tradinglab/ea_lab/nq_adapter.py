"""Adaptador NQ M1 → M5 para el motor del EA (NQ-A).

No descarga datos ni ejecuta nada por sí solo: prepara barras M5 alineadas a
Nueva York, asigna el perfil de spread de US100 y filtra operaciones que
cruzan un cambio de contrato. Solo se usa con datos locales.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ..config import ROOT
from ..ea_us100_engine import run as run_engine

CACHE = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
PROFILE = (
    ROOT / "data" / "cache" / "ea" / "us100_spread_profile_ny5m.parquet"
)
SLOTS = 288
BAR_MINUTES = 5


class NqAdapterError(RuntimeError):
    pass


def _ny_naive(index: Any) -> pd.DatetimeIndex:
    values = pd.DatetimeIndex(index)
    if values.tz is not None:
        values = values.tz_convert("America/New_York").tz_localize(None)
    return values


def resample_m5(frame: pd.DataFrame) -> pd.DataFrame:
    """M1 → M5 con OHLC y volumen, alineado a minutos múltiplos de 5."""

    if frame is None or frame.empty:
        raise NqAdapterError("Sin datos: no hay barras M1")
    missing = {"open", "high", "low", "close"} - set(frame.columns)
    if missing:
        raise NqAdapterError(
            "Sin datos: faltan columnas " + ", ".join(sorted(missing))
        )
    volume_column = "volume" if "volume" in frame.columns else "tickvol"
    if volume_column not in frame.columns:
        raise NqAdapterError("Sin datos: falta volume/tickvol")
    data = frame.copy()
    data.index = _ny_naive(data.index)
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="first")]
    aggregated = data.resample(
        f"{BAR_MINUTES}min", label="left", closed="left", origin="epoch"
    ).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            volume_column: "sum",
        }
    )
    aggregated = aggregated.dropna(subset=["open", "high", "low", "close"])
    aggregated["tickvol"] = aggregated[volume_column].astype(float)
    return aggregated


def build_spread_profile(
    cache: str | Path = CACHE,
    output: str | Path = PROFILE,
) -> pd.DataFrame:
    """Mediana del spread de US100 por franja de 5 min en hora de NY."""

    frame = pd.read_parquet(cache)
    if frame.empty or "spread" not in frame.columns:
        raise NqAdapterError("Sin datos: la caché US100 no tiene spread")
    index = _ny_naive(frame.index)
    slot = (index.hour * 60 + index.minute) // BAR_MINUTES
    medians = (
        pd.Series(frame["spread"].to_numpy(float), index=slot)
        .groupby(level=0)
        .median()
    )
    global_median = float(frame["spread"].median())
    values = pd.Series(
        [medians.get(slot, global_median) for slot in range(SLOTS)],
        index=range(SLOTS),
        dtype=float,
    )
    profile = pd.DataFrame({"slot": values.index, "spread": values.values})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    profile.to_parquet(output, index=False)
    return profile


def load_spread_profile(
    path: str | Path = PROFILE,
    *,
    build: bool = False,
) -> pd.DataFrame:
    target = Path(path)
    if not target.exists():
        if build:
            return build_spread_profile(output=target)
        raise NqAdapterError(f"Sin datos: no existe el perfil {target}")
    profile = pd.read_parquet(target)
    if "slot" not in profile.columns or "spread" not in profile.columns:
        raise NqAdapterError("Sin datos: perfil de spread inválido")
    return profile.sort_values("slot").reset_index(drop=True)


def apply_spread(
    frame: pd.DataFrame,
    profile: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Añade ``spread`` a cada barra según su franja de 5 min de NY."""

    data = frame.copy()
    profile = profile if profile is not None else load_spread_profile(build=True)
    values = profile.set_index("slot")["spread"]
    index = _ny_naive(data.index)
    slot = (index.hour * 60 + index.minute) // BAR_MINUTES
    fallback = float(values.median())
    data["spread"] = [
        float(values.get(int(item), fallback)) for item in slot
    ]
    if "tickvol" not in data.columns:
        if "volume" not in data.columns:
            raise NqAdapterError("Sin datos: falta tickvol/volume")
        data["tickvol"] = data["volume"].astype(float)
    return data


def filter_crossing_rolls(
    trades: pd.DataFrame,
    rolls: Iterable[Any] | None,
) -> tuple[pd.DataFrame, int]:
    """Descarta operaciones con un roll estrictamente entre entrada y salida."""

    if trades is None or trades.empty:
        return trades if trades is not None else pd.DataFrame(), 0
    roll_times = [_ny_naive([stamp])[0] for stamp in (rolls or [])]
    if not roll_times:
        return trades, 0
    keep = []
    crossed = 0
    for row in trades.itertuples():
        entry = _ny_naive([row.t])[0]
        exit_ = _ny_naive([row.t_exit])[0]
        if any(entry < stamp < exit_ for stamp in roll_times):
            crossed += 1
            continue
        keep.append(row.Index)
    if crossed:
        return trades.loc[keep].copy(), crossed
    return trades, 0


def prepare_nq(
    m1: pd.DataFrame,
    *,
    profile: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return apply_spread(resample_m5(m1), profile)


def run_nq(
    m1: pd.DataFrame,
    params: dict[str, Any],
    *,
    profile: pd.DataFrame | None = None,
    rolls: Iterable[Any] | None = None,
) -> dict[str, Any]:
    bars = prepare_nq(m1, profile=profile)
    trades = run_engine(bars, params)
    filtered, crossed = filter_crossing_rolls(trades, rolls)
    return {"bars": bars, "trades": filtered, "crossed_rolls": crossed}


def atr14(frame: pd.DataFrame) -> pd.Series:
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    close = frame["close"].to_numpy(float)
    true_range = np.empty(len(frame), dtype=float)
    if len(frame) == 0:
        return pd.Series(dtype=float)
    true_range[0] = high[0] - low[0]
    for index in range(1, len(frame)):
        true_range[index] = max(
            high[index] - low[index],
            abs(high[index] - close[index - 1]),
            abs(low[index] - close[index - 1]),
        )
    values = np.full(len(frame), np.nan, dtype=float)
    if len(frame) >= 14:
        values[13] = true_range[:14].mean()
        for index in range(14, len(frame)):
            values[index] = (values[index - 1] * 13.0 + true_range[index]) / 14.0
    return pd.Series(values, index=frame.index)


def atr_ratio(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
) -> float | None:
    left = atr14(reference)
    right = atr14(candidate)
    if start:
        left = left.loc[pd.Timestamp(start) :]
        right = right.loc[pd.Timestamp(start) :]
    if end:
        left = left.loc[: pd.Timestamp(end)]
        right = right.loc[: pd.Timestamp(end)]
    common = left.index.intersection(right.index)
    if len(common) == 0:
        return None
    left = left.loc[common].dropna()
    right = right.loc[common].dropna()
    index = left.index.intersection(right.index)
    if len(index) == 0:
        return None
    base = float(np.median(left.loc[index]))
    if base <= 0:
        return None
    return float(np.median(right.loc[index]) / base)


@dataclass(frozen=True)
class Validity:
    matched: int
    reference: int
    candidate: int
    matched_pct: float
    correlation: float | None
    valid: bool


def match_validity(
    nq_trades: pd.DataFrame,
    us100_trades: pd.DataFrame,
    *,
    tolerance: pd.Timedelta = pd.Timedelta(minutes=BAR_MINUTES),
) -> Validity:
    """Empareja por lado y barra de entrada ±1 y calcula correlación de R."""

    if nq_trades is None or us100_trades is None:
        raise NqAdapterError("Sin datos: faltan operaciones")
    used: set[int] = set()
    pairs: list[tuple[float, float]] = []
    for candidate in nq_trades.itertuples():
        entry = _ny_naive([candidate.t])[0]
        best = None
        for index, reference in enumerate(us100_trades.itertuples()):
            if index in used or int(reference.d) != int(candidate.d):
                continue
            distance = abs(entry - _ny_naive([reference.t])[0])
            if distance <= tolerance and (
                best is None or distance < best[0]
            ):
                best = (distance, index, reference)
        if best is None:
            continue
        used.add(best[1])
        pairs.append((float(candidate.r), float(best[2].r)))
    reference_count = int(len(us100_trades))
    matched_pct = (
        100.0 * len(pairs) / reference_count if reference_count else 0.0
    )
    correlation = None
    if len(pairs) >= 2:
        left = np.array([item[0] for item in pairs], dtype=float)
        right = np.array([item[1] for item in pairs], dtype=float)
        if left.std() > 0 and right.std() > 0:
            correlation = float(np.corrcoef(left, right)[0, 1])
    valid = bool(
        matched_pct >= 80.0
        and correlation is not None
        and correlation >= 0.7
    )
    return Validity(
        matched=len(pairs),
        reference=reference_count,
        candidate=int(len(nq_trades)),
        matched_pct=matched_pct,
        correlation=correlation,
        valid=valid,
    )


def weekly_lcb(trades: pd.DataFrame, *, paths: int = 10_000, seed: int = 42) -> dict:
    if trades is None or trades.empty:
        return {"mean": None, "lcb95": None, "sd": None, "weeks": 0}
    grouped = trades.assign(
        week=trades["t"].dt.strftime("%G-%V")
    ).groupby("week")["r"].apply(list)
    weeks = [np.asarray(values, dtype=float) for values in grouped]
    rng = np.random.default_rng(seed)
    means = np.empty(paths, dtype=float)
    for index in range(paths):
        picks = rng.integers(0, len(weeks), size=len(weeks))
        values = np.concatenate([weeks[pick] for pick in picks])
        means[index] = values.mean()
    mean = float(trades["r"].mean())
    sd = float(np.std(means, ddof=1))
    return {
        "mean": mean,
        "lcb95": mean - 1.645 * sd,
        "sd": sd,
        "weeks": len(weeks),
    }


__all__ = [
    "BAR_MINUTES",
    "CACHE",
    "NqAdapterError",
    "PROFILE",
    "Validity",
    "apply_spread",
    "atr14",
    "atr_ratio",
    "build_spread_profile",
    "filter_crossing_rolls",
    "load_spread_profile",
    "match_validity",
    "prepare_nq",
    "resample_m5",
    "run_nq",
    "weekly_lcb",
]
