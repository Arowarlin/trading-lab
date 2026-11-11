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
        "p5_max_drawdown": float(np.percentile(max_dd, 5)),
        "worst_max_drawdown": float(np.min(max_dd)),
        "mean_daily_return": float(r.mean()),
        "daily_volatility": float(r.std(ddof=1)) if r.size > 1 else 0.0,
        "sample_days": int(r.size),
    }


def multiverse_by_trade(
    rules: PropRules,
    trade_pnls,
    *,
    n_paths: int = 1_000,
    seed: int = 42,
    day_sizes: list[int] | None = None,
    max_points: int = 240,
) -> dict:
    """Reordena operaciones (no días) y evalúa límites de cuenta.

    Cada path es una permutación de los mismos PnL. El límite diario se evalúa
    por operación; si se pasan `day_sizes` (número de operaciones por día
    original), se conserva ese tamaño de día y se evalúa el PnL acumulado del
    bloque. No crea datos: si hay menos de 2 operaciones, falla.
    """
    pnls = np.asarray(list(trade_pnls), dtype=float)
    pnls = pnls[np.isfinite(pnls)]
    if pnls.size < 2:
        raise ValueError("se necesitan al menos 2 operaciones para el multiverse")
    if n_paths <= 0:
        raise ValueError("n_paths debe ser > 0")

    initial = float(rules.account_size)
    daily_limit = float(rules.effective_daily_limit_usd)
    max_limit = float(rules.effective_max_loss_usd)
    sizes = [int(size) for size in (day_sizes or []) if int(size) > 0]
    use_days = bool(sizes) and sum(sizes) == int(pnls.size)
    rng = np.random.default_rng(seed)
    count = int(pnls.size)
    paths = np.empty((n_paths, count + 1), dtype=float)
    paths[:, 0] = initial
    daily_breach = np.zeros(n_paths, dtype=bool)

    for index in range(n_paths):
        shuffled = rng.permutation(pnls)
        paths[index, 1:] = initial + np.cumsum(shuffled)
        if use_days:
            start = 0
            breach = False
            for size in sizes:
                chunk = shuffled[start : start + size]
                start += size
                if float(chunk.sum()) <= -daily_limit:
                    breach = True
                    break
            daily_breach[index] = breach
        else:
            daily_breach[index] = bool((shuffled <= -daily_limit).any())

    peaks = np.maximum.accumulate(paths, axis=1)
    drawdowns = paths / peaks - 1.0
    max_dd = drawdowns.min(axis=1)
    max_dd_usd = (paths - peaks).min(axis=1)
    if rules.max_loss_mode == "static":
        floors = np.full_like(paths, initial - max_limit)
    else:
        floors = peaks - max_limit
    max_breach = (paths <= floors).any(axis=1)
    any_breach = daily_breach | max_breach

    steps = list(range(count + 1))
    if len(steps) > max_points:
        indexes = sorted(
            set(np.linspace(0, count, max_points, dtype=int).tolist())
        )
    else:
        indexes = steps
    curve_pct = paths / initial - 1.0
    curves = {}
    for label, percentile in (("p5", 5), ("p50", 50), ("p95", 95)):
        values = np.percentile(curve_pct[:, indexes], percentile, axis=0)
        curves[label] = [round(float(value), 8) for value in values]

    final = paths[:, -1]
    return {
        "firm": rules.firm,
        "phase": rules.phase,
        "rules": rules.describe(),
        "capital": round(initial, 2),
        "trades": count,
        "paths": int(n_paths),
        "seed": int(seed),
        "daily_limit_usd": round(daily_limit, 2),
        "max_loss_usd": round(max_limit, 2),
        "max_loss_mode": rules.max_loss_mode,
        "daily_basis": "bloques_por_dia" if use_days else "por_operacion",
        "day_sizes": sizes if use_days else [],
        "steps": indexes,
        "curves": curves,
        "prob_breach_daily": float(daily_breach.mean()),
        "prob_breach_max": float(max_breach.mean()),
        "prob_breach_any": float(any_breach.mean()),
        "expected_max_drawdown": float(max_dd.mean()),
        "median_max_drawdown": float(np.median(max_dd)),
        "p5_max_drawdown": float(np.percentile(max_dd, 5)),
        "worst_max_drawdown": float(max_dd.min()),
        "expected_max_drawdown_usd": float(max_dd_usd.mean()),
        "final_equity_p5": float(np.percentile(final, 5)),
        "final_equity_median": float(np.median(final)),
        "final_equity_p95": float(np.percentile(final, 95)),
        "sample_ok": count >= 30,
        "sample_warning": (
            None if count >= 30 else f"muestra insuficiente: N={count} < 30"
        ),
    }


__all__ = ["monte_carlo", "multiverse_by_trade"]
