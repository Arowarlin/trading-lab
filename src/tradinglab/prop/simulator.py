from __future__ import annotations

from math import sqrt

import numpy as np

from .rules import PropRules


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def monte_carlo(
    rules: PropRules,
    daily_returns,
    *,
    n_paths: int = 5_000,
    horizon: int = 60,
    seed: int = 42,
    block_size: int = 1,
) -> dict:
    """Bootstrap de los retornos diarios de una estrategia contra las reglas.

    Aproximación con datos diarios: no modela wicks intradía, así que el riesgo
    de romper el límite diario está ligeramente SUBESTIMADO. Para producción,
    repetir con datos intradía del bróker.
    """
    r = np.asarray(daily_returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        raise ValueError("no hay retornos válidos para simular")
    r = np.clip(r, -0.95, 1.0)

    if n_paths <= 0 or horizon <= 0:
        raise ValueError("n_paths y horizon deben ser > 0")

    block_size = max(1, int(block_size))
    rng = np.random.default_rng(seed)

    initial = float(rules.account_size)
    eff_daily = rules.effective_daily_limit_usd
    eff_max = rules.effective_max_loss_usd
    target = initial + rules.profit_target_usd
    trailing = rules.max_loss_mode != "static"

    equity = np.full(n_paths, initial, dtype=float)
    peak = equity.copy()
    passed_at = np.full(n_paths, -1, dtype=int)
    breach_at = np.full(n_paths, -1, dtype=int)
    max_dd = np.zeros(n_paths, dtype=float)
    running_peak = equity.copy()

    for day in range(horizon):
        if block_size == 1:
            draws = rng.choice(r, size=n_paths, replace=True)
        else:
            starts = rng.integers(0, max(1, r.size - block_size + 1), size=n_paths)
            idx = (starts[:, None] + np.arange(block_size)[None, :]) % r.size
            draws = (1.0 + r[idx]).prod(axis=1) - 1.0

        day_start = equity.copy()
        equity = equity * (1.0 + draws)

        running_peak = np.maximum(running_peak, equity)
        dd = equity / running_peak - 1.0
        max_dd = np.minimum(max_dd, dd)

        # trailing: el pico relevante incluye el cierre de hoy
        if trailing:
            peak = np.maximum(peak, equity)
            max_base = peak
        else:
            max_base = np.full(n_paths, initial)

        daily_floor = day_start - eff_daily
        max_floor = max_base - eff_max
        floor = np.maximum(daily_floor, max_floor)

        breached_now = (breach_at < 0) & (equity <= floor)
        breach_at[breached_now & (passed_at < 0)] = day

        hit_target = (passed_at < 0) & (breach_at < 0) & (equity >= target)
        if rules.profit_target_pct > 0:
            passed_at[hit_target] = day

        if (breach_at >= 0).all():
            break

    passed = passed_at >= 0
    breached = (breach_at >= 0) & ~passed
    timed_out = ~passed & ~breached

    days_to_pass = passed_at[passed] + 1
    pass_count = int(passed.sum())
    breach_count = int(breached.sum())
    timeout_count = int(timed_out.sum())

    lo, hi = _wilson(pass_count, n_paths)

    return {
        "firm": rules.firm,
        "phase": rules.phase,
        "rules": rules.describe(),
        "paths": n_paths,
        "horizon_days": horizon,
        "block_size": block_size,
        "pass_rate": pass_count / n_paths,
        "pass_ci95": (lo, hi),
        "breach_rate": breach_count / n_paths,
        "timeout_rate": timeout_count / n_paths,
        "median_days_to_pass": float(np.median(days_to_pass)) if pass_count else None,
        "p90_days_to_pass": float(np.percentile(days_to_pass, 90)) if pass_count else None,
        "median_max_drawdown": float(np.median(max_dd)),
        "worst_max_drawdown": float(np.min(max_dd)),
        "mean_daily_return": float(r.mean()),
        "daily_volatility": float(r.std(ddof=1)) if r.size > 1 else 0.0,
        "sample_days": int(r.size),
    }


__all__ = ["monte_carlo"]
