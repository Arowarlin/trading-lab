"""Escenarios de ventaja y ventaja mínima rentable μ* (04 §7.1-7.2) — FUT-A7.

Todo se mide por operación y por contrato. Los escenarios desplazan el P&L de cada operación
(``paths.shift``) y, si procede, suben los costes (``add_cost``). μ* se busca por bisección en δ con
números aleatorios comunes (la misma matriz de índices para todos los δ).
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from .paths import DayPath, shift
from .project import ProjectConfig, session_offsets, simulate_project
from .rules import Program
from .simulate import mean_block_length, stationary_bootstrap_indices

SCENARIOS = ("optimista", "base", "conservador", "estres_severo", "sin_ventaja")


def pool_stats(pool: list[DayPath]) -> dict:
    """Medias por operación y contrato: neta, bruta, coste y riesgo (None si no hay riesgo declarado)."""
    n = sum(d.n_trades for d in pool)
    if n == 0:
        raise ValueError("el pool no tiene operaciones")
    net = sum(float(d.marks[-1]) for d in pool)
    gross = sum(d.gross_pnl for d in pool)
    cost = sum(d.cost for d in pool)
    risks = [d.risk_usd for d in pool if d.n_trades > 0 and d.risk_usd is not None]
    return {"n_trades": n, "mean_net": net / n, "mean_gross": gross / n, "mean_cost": cost / n,
            "mean_risk": (sum(risks) / len(risks)) if risks else None}


def add_cost(day: DayPath, per_trade: float) -> DayPath:
    """Sube el coste de cada operación en ``per_trade``: el P&L neto baja y el bruto no cambia."""
    moved = shift(day, -per_trade)
    return replace(moved, gross_pnl=day.gross_pnl, cost=day.cost + day.n_trades * per_trade)


def lcb95_mean_net(pool: list[DayPath], *, n_boot: int = 2000, mean_block: float | None = None,
                   seed: int = 0) -> float:
    """Cota inferior unilateral al 95 % de la media neta por operación (bootstrap estacionario por días)."""
    net = np.asarray([float(d.marks[-1]) for d in pool])
    ntr = np.asarray([d.n_trades for d in pool], dtype=float)
    if ntr.sum() == 0:
        raise ValueError("el pool no tiene operaciones")
    if mean_block is None:
        mean_block = mean_block_length(net)
    idx = stationary_bootstrap_indices(len(pool), len(pool), n_boot, mean_block, seed)
    tot_n = ntr[idx].sum(axis=1)
    means = np.where(tot_n > 0, net[idx].sum(axis=1) / np.maximum(tot_n, 1), np.nan)
    return float(np.nanpercentile(means, 5))


def scenario_pool(pool: list[DayPath], name: str, *, lcb95: float | None = None, tick_value: float | None = None,
                  haircut: float = 0.5) -> tuple[list[DayPath], float]:
    """Devuelve (pool desplazado, δ por operación) del escenario ``name`` (04 §7.1)."""
    st = pool_stats(pool)
    mean_cost = st["mean_cost"]
    if name == "optimista":
        return list(pool), 0.0
    if name == "base":
        delta = -haircut * st["mean_net"] if st["mean_net"] > 0 else 0.0
        return [shift(d, delta) for d in pool], delta
    if name == "conservador":
        if lcb95 is None:
            raise ValueError("el escenario conservador necesita lcb95")
        delta = lcb95 - st["mean_net"]
        return [add_cost(shift(d, delta), 0.25 * mean_cost) for d in pool], delta
    if name == "estres_severo":
        if tick_value is None:
            raise ValueError("el estrés severo necesita tick_value (+1 tick por lado)")
        delta = -st["mean_gross"]
        return [add_cost(shift(d, delta), 0.5 * mean_cost + 2 * tick_value) for d in pool], delta
    if name == "sin_ventaja":
        delta = -st["mean_gross"]
        return [shift(d, delta) for d in pool], delta
    raise ValueError(f"escenario desconocido: {name}")


def ev_at_delta(program: Program, pool: list[DayPath], cfg: ProjectConfig, delta: float, *, horizon_days: int,
                idx: np.ndarray) -> tuple[float, float]:
    res = simulate_project(program, [shift(d, delta) for d in pool], cfg, n_paths=idx.shape[0], seed=0, idx=idx)
    h = res["horizons"][horizon_days]
    return h["ev"], h["se"]


def min_profitable_edge(program: Program, pool: list[DayPath], cfg: ProjectConfig, *, horizon_days: int = 365,
                        n_paths: int = 4000, seed: int = 0, mean_block: float | None = None,
                        lo: float | None = None, hi: float | None = None, tol: float = 0.5,
                        max_iter: int = 40) -> dict:
    """μ* = mean_net + δ* con EV_H(δ*) = 0, por bisección con números aleatorios comunes (04 §7.2)."""
    cfg = replace(cfg, horizons_days=(horizon_days,))
    st = pool_stats(pool)
    if mean_block is None:
        mean_block = mean_block_length(np.asarray([float(d.marks[-1]) for d in pool]))
    n_days = len(session_offsets(cfg.start_date, horizon_days))
    idx = stationary_bootstrap_indices(len(pool), n_days, n_paths, mean_block, seed)
    span = max(abs(st["mean_gross"]), st["mean_cost"], 1.0)
    lo = -st["mean_net"] - 10 * span if lo is None else lo
    hi = -st["mean_net"] + 10 * span if hi is None else hi
    ev_lo, _ = ev_at_delta(program, pool, cfg, lo, horizon_days=horizon_days, idx=idx)
    ev_hi, _ = ev_at_delta(program, pool, cfg, hi, horizon_days=horizon_days, idx=idx)
    if not (ev_lo < 0 < ev_hi):
        return {"delta_star": None, "mu_star_usd": None, "mu_star_r": None, "bracket": (lo, hi),
                "ev_bracket": (ev_lo, ev_hi), "monotone": None, "grid": [], "note": "sin cambio de signo en el intervalo"}
    a, b = lo, hi
    for _ in range(max_iter):
        if b - a <= tol:
            break
        mid = 0.5 * (a + b)
        ev_mid, _ = ev_at_delta(program, pool, cfg, mid, horizon_days=horizon_days, idx=idx)
        if ev_mid < 0:
            a = mid
        else:
            b = mid
    delta_star = 0.5 * (a + b)
    grid = []
    for x in np.linspace(lo, hi, 9):
        ev, se = ev_at_delta(program, pool, cfg, float(x), horizon_days=horizon_days, idx=idx)
        grid.append((float(x), ev, se))
    monotone = all(grid[k + 1][1] >= grid[k][1] - 2 * max(grid[k][2], grid[k + 1][2]) for k in range(8))
    mu_star = st["mean_net"] + delta_star
    mu_r = mu_star / st["mean_risk"] if st["mean_risk"] else None
    return {"delta_star": delta_star, "mu_star_usd": mu_star, "mu_star_r": mu_r, "bracket": (lo, hi),
            "ev_bracket": (ev_lo, ev_hi), "monotone": monotone, "grid": grid,
            "se_at_star": None if not grid else min(g[2] for g in grid), "n_paths": n_paths,
            "note": None if not math.isnan(mu_star) else "μ* no finito"}
