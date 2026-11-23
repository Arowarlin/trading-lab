"""Control contra deriva: entradas aleatorias con el perfil de la estrategia.

Para cada estrategia evaluada en IS se generan ``simulations`` (1000 por
defecto) réplicas con entradas aleatorias sobre las mismas velas y con el mismo
perfil agregado que la estrategia: número de operaciones, proporción de
compras/ventas, tiempo medio en mercado y stop en ATR. La expectativa neta de
la estrategia se sitúa en el percentil de esa distribución. Un percentil bajo
significa que la entrada no aporta nada frente a entrar al azar en la misma
serie y con el mismo riesgo; el umbral por defecto es 90.

La semilla se deriva del id de campaña para que todas las estrategias de una
campaña se comparen contra las mismas secuencias aleatorias (comparación
pareada). El control solo se activa si la campaña lo declara en
``config.controls.test_vs_random_direction``: las campañas anteriores a R8 no
lo tienen y no se recalculan.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from . import fastbt

try:  # pragma: no cover - depende del entorno
    from numba import njit
except ImportError:  # pragma: no cover

    def njit(*args, **kwargs):  # type: ignore[no-redef]
        def wrap(func):
            return func

        return wrap


DEFAULT_SIMULATIONS = 1000
DEFAULT_PERCENTILE_MIN = 90.0


def campaign_seed(campaign_id: str) -> int:
    """Semilla estable a partir del id de campaña."""

    digest = hashlib.sha256(str(campaign_id or "").encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


@njit(cache=True)
def _fill_outcomes(
    open_,
    high,
    low,
    close,
    allowed,
    allowed_entry,
    flat_flag,
    atr,
    entry_bps,
    stop_bps,
    target_bps,
    fut_price,
    stop_kind,
    stop_mult,
    stop_pct,
    stop_fixed,
    target_kind,
    target_rr,
    target_pct,
    target_fixed,
    horizon,
    r_long,
    r_short,
    held_long,
    held_short,
):
    n = len(open_)
    for i in range(1, n):
        if allowed[i] == 0 or allowed_entry[i] == 0:
            continue
        a = 0.0
        if stop_kind == 0:
            a = atr[i - 1]
            if not (a > 0.0):
                continue
        last = i + horizon
        if last > n - 1:
            last = n - 1
        for side in (1, -1):
            entry = open_[i]
            if stop_kind == 0:
                dist = stop_mult * a
            elif stop_kind == 1:
                dist = entry * stop_pct / 100.0
            else:
                dist = (entry - stop_fixed) * side
            if not (dist > 0.0):
                continue
            stop = entry - side * dist
            target = 0.0
            has_target = target_kind != 3
            if has_target:
                if target_kind == 0:
                    target = entry + side * target_rr * dist
                elif target_kind == 1:
                    target = entry + side * entry * target_pct / 100.0
                else:
                    target = target_fixed
                if (side == 1 and target <= entry) or (
                    side == -1 and target >= entry
                ):
                    continue
            exit_j = -1
            price = 0.0
            exit_bps = 0.0
            for j in range(i, last + 1):
                if allowed[j] == 1:
                    if side == 1:
                        if low[j] <= stop:
                            exit_j = j
                            price = stop if stop < open_[j] else open_[j]
                            exit_bps = stop_bps[j]
                            break
                        if has_target and high[j] >= target:
                            exit_j = j
                            price = target if target < high[j] else high[j]
                            exit_bps = target_bps[j]
                            break
                    else:
                        if high[j] >= stop:
                            exit_j = j
                            price = stop if stop > open_[j] else open_[j]
                            exit_bps = stop_bps[j]
                            break
                        if has_target and low[j] <= target:
                            exit_j = j
                            price = target if target > low[j] else low[j]
                            exit_bps = target_bps[j]
                            break
                    if flat_flag[j] == 1:
                        exit_j = j
                        price = close[j]
                        exit_bps = stop_bps[j]
                        break
                if j == last:
                    exit_j = j
                    price = close[j]
                    exit_bps = stop_bps[j]
                    break
            if exit_j < 0:
                continue
            held = exit_j - i
            if side == 1:
                gross = price / entry - 1.0
                r_long[i] = (
                    gross * entry / dist
                    - (entry_bps[i] + exit_bps) / 10_000.0 * entry / dist
                    - 2.0 * fut_price / dist
                )
                held_long[i] = held
            else:
                gross = 1.0 - price / entry
                r_short[i] = (
                    gross * entry / dist
                    - (entry_bps[i] + exit_bps) / 10_000.0 * entry / dist
                    - 2.0 * fut_price / dist
                )
                held_short[i] = held


def outcome_tables(
    bars: pd.DataFrame,
    exit_spec: fastbt.ExitSpec,
    limits: fastbt.RunLimits,
    panel: fastbt.CostPanel,
    prepared: fastbt.PreparedBars | None,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resultado de una entrada aleatoria en cada vela, por lado.

    Devuelve ``r_long, r_short, held_long, held_short, eligible``. Las tablas
    se calculan una vez por estrategia; las 1000 réplicas solo muestrean.
    """

    n = len(bars)
    horizon = max(1, min(int(horizon), n))
    mask = fastbt.session_mask(bars, limits, prepared=prepared)
    atr = fastbt.atr_window(bars, exit_spec.stop_n, prepared=prepared)
    r_long = np.full(n, np.nan, dtype=np.float64)
    r_short = np.full(n, np.nan, dtype=np.float64)
    held_long = np.zeros(n, dtype=np.int64)
    held_short = np.zeros(n, dtype=np.int64)
    _fill_outcomes(
        bars["open"].to_numpy(dtype=float),
        bars["high"].to_numpy(dtype=float),
        bars["low"].to_numpy(dtype=float),
        bars["close"].to_numpy(dtype=float),
        mask.allowed.astype(np.int64),
        mask.allowed_entry.astype(np.int64),
        mask.flat_flag.astype(np.int64),
        atr,
        panel.entry_bps.astype(np.float64),
        panel.stop_bps.astype(np.float64),
        panel.target_bps.astype(np.float64),
        float(panel.fut_price),
        int({"atr": 0, "pct": 1, "fixed": 2}.get(exit_spec.stop, -1)),
        float(exit_spec.stop_mult),
        float(exit_spec.stop_mult),
        float(exit_spec.stop_price or 0.0),
        int({"rr": 0, "pct": 1, "fixed": 2, None: 3}[exit_spec.target]),
        float(exit_spec.target_rr),
        float(exit_spec.target_pct or 0.0),
        float(exit_spec.target_price or 0.0),
        int(horizon),
        r_long,
        r_short,
        held_long,
        held_short,
    )
    eligible = np.flatnonzero(
        mask.allowed_entry
        & np.r_[False, mask.allowed_entry[:-1]]
        & (np.isfinite(r_long) | np.isfinite(r_short))
    ).astype(np.int64)
    return r_long, r_short, held_long, held_short, eligible


def percentile(
    *,
    strategy_expectancy: float | None,
    trades: int,
    long_fraction: float,
    mean_bars: float,
    r_long: np.ndarray,
    r_short: np.ndarray,
    eligible: np.ndarray,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = 0,
    approved: bool = False,
) -> dict[str, Any]:
    """Percentil de la expectativa de la estrategia frente a entradas al azar."""

    from .guard import require_approved

    require_approved("", approved=approved, action="drift_percentile")

    simulations = max(1, int(simulations))
    count = max(0, int(trades))
    if (
        strategy_expectancy is None
        or count <= 0
        or len(eligible) == 0
    ):
        return {
            "percentile": None,
            "simulations": simulations,
            "trades": count,
            "long_fraction": float(long_fraction),
            "mean_bars": float(mean_bars),
            "strategy_expectancy_r": strategy_expectancy,
            "passed": False,
        }
    long_count = int(round(float(long_fraction) * count))
    long_count = min(count, max(0, long_count))
    short_count = count - long_count
    rng = np.random.default_rng(int(seed))
    replace = count > len(eligible)
    means = np.empty(simulations, dtype=np.float64)
    for index in range(simulations):
        picks = rng.choice(eligible, size=count, replace=replace)
        sides = rng.permutation(
            np.concatenate(
                (
                    np.ones(long_count, dtype=np.int8),
                    -np.ones(short_count, dtype=np.int8),
                )
            )
        )
        values = np.where(
            sides > 0,
            r_long[picks],
            r_short[picks],
        )
        finite = np.isfinite(values)
        means[index] = (
            float(values[finite].mean()) if finite.any() else np.nan
        )
    valid = means[np.isfinite(means)]
    if valid.size == 0:
        return {
            "percentile": None,
            "simulations": simulations,
            "trades": count,
            "long_fraction": round(float(long_fraction), 6),
            "mean_bars": round(float(mean_bars), 3),
            "strategy_expectancy_r": round(float(strategy_expectancy), 6),
            "seed": int(seed),
            "passed": False,
        }
    actual = float(strategy_expectancy)
    below = int(np.sum(valid < actual))
    value = 100.0 * below / valid.size
    return {
        "percentile": round(value, 2),
        "simulations": simulations,
        "trades": count,
        "long_fraction": round(float(long_fraction), 6),
        "mean_bars": round(float(mean_bars), 3),
        "strategy_expectancy_r": round(actual, 6),
        "random_expectancy_mean_r": round(float(np.mean(valid)), 6),
        "random_expectancy_median_r": round(float(np.median(valid)), 6),
        "random_percentile_90_r": round(float(np.percentile(valid, 90)), 6),
        "seed": int(seed),
        "passed": value >= DEFAULT_PERCENTILE_MIN,
    }


def evaluate(
    bars: pd.DataFrame,
    exit_spec: fastbt.ExitSpec,
    limits: fastbt.RunLimits,
    full: fastbt.FastResult,
    *,
    cost,
    prepared: fastbt.PreparedBars | None = None,
    campaign_id: str = "",
    simulations: int = DEFAULT_SIMULATIONS,
    percentile_min: float = DEFAULT_PERCENTILE_MIN,
    approved: bool = False,
) -> dict[str, Any]:
    """Calcula el percentil contra deriva de una estrategia ya evaluada.

    El control replica el stop en ATR y el tiempo medio en mercado. No replica
    el objetivo: las entradas aleatorias salen por stop o al vencer el
    horizonte, para que el tiempo en mercado no se acorte por objetivos que la
    estrategia sí tiene.
    """

    from .guard import require_approved

    require_approved(campaign_id, approved=approved, action="drift")

    trades = list(full.trades)
    count = len(trades)
    if count == 0:
        return {
            "percentile": None,
            "simulations": int(simulations),
            "trades": 0,
            "percentile_min": float(percentile_min),
            "passed": False,
            "error": "sin operaciones IS",
        }
    long_fraction = sum(1 for trade in trades if trade.side == "long") / count
    mean_bars = float(np.mean([trade.bars_held for trade in trades]))
    if exit_spec.time_exit_bars:
        horizon = min(int(round(mean_bars)), int(exit_spec.time_exit_bars))
    else:
        horizon = int(round(mean_bars))
    panel = (
        prepared.panel
        if prepared is not None
        else cost.panel(bars)
    )
    control_spec = replace(exit_spec, target=None)
    r_long, r_short, held_long, held_short, eligible = outcome_tables(
        bars, control_spec, limits, panel, prepared, max(1, horizon)
    )
    long_held = held_long[eligible]
    long_held = long_held[long_held > 0]
    short_held = held_short[eligible]
    short_held = short_held[short_held > 0]
    realized = 0.0
    if len(long_held):
        realized += long_fraction * float(np.mean(long_held))
    if len(short_held):
        realized += (1.0 - long_fraction) * float(np.mean(short_held))
    result = percentile(
        strategy_expectancy=(full.metrics or {}).get("expectancy_r"),
        trades=count,
        long_fraction=long_fraction,
        mean_bars=mean_bars,
        r_long=r_long,
        r_short=r_short,
        eligible=eligible,
        simulations=simulations,
        seed=campaign_seed(campaign_id),
        approved=approved,
    )
    result["mean_bars_realized"] = round(realized, 3)
    result["horizon_bars"] = int(max(1, horizon))
    result["percentile_min"] = float(percentile_min)
    result["campaign_id"] = str(campaign_id)
    result["passed"] = bool(
        result["percentile"] is not None
        and float(result["percentile"]) >= float(percentile_min)
    )
    return result


__all__ = [
    "DEFAULT_PERCENTILE_MIN",
    "DEFAULT_SIMULATIONS",
    "campaign_seed",
    "evaluate",
    "outcome_tables",
    "percentile",
]
