"""Monte Carlo del motor EV, parte A: bootstrap estacionario y evaluación vectorizada (04 §3 y §6) — FUT-A6a.

La evaluación vectorizada aplica EXACTAMENTE las reglas de ``account.step_day`` (motor escalar de
referencia); un test compara los dos camino a camino.
"""

from __future__ import annotations

import math

import numpy as np
from arch.bootstrap import optimal_block_length

from .account import lock_level
from .paths import DayPath
from .rules import Program

ACTIVE, PASSED, FAILED_MLL, FAILED_TIMEOUT = 0, 1, 2, 3


def stationary_bootstrap_indices(n_pool: int, horizon: int, n_paths: int, mean_block: float, seed: int
                                 ) -> np.ndarray:
    """Índices (n_paths, horizon) del bootstrap estacionario de Politis-Romano con bloque medio ``mean_block``."""
    if mean_block < 1:
        raise ValueError("mean_block debe ser >= 1")
    if n_pool < 1 or horizon < 1 or n_paths < 1:
        raise ValueError("n_pool, horizon y n_paths deben ser >= 1")
    rng = np.random.Generator(np.random.PCG64(seed))
    idx = np.empty((n_paths, horizon), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n_pool, n_paths)
    p_new = 1.0 / mean_block
    for t in range(1, horizon):
        new = rng.random(n_paths) < p_new
        idx[:, t] = np.where(new, rng.integers(0, n_pool, n_paths), (idx[:, t - 1] + 1) % n_pool)
    return idx


def mean_block_length(daily_pnl: np.ndarray) -> float:
    x = np.asarray(daily_pnl, dtype=np.float64)
    if x.size < 3 or float(np.std(x)) == 0.0:
        return 1.0   # serie constante o demasiado corta: no hay dependencia que estimar
    return max(1.0, float(optimal_block_length(x)["stationary"].iloc[0]))


def _pool_matrix(pool: list[DayPath]) -> tuple[np.ndarray, np.ndarray]:
    width = max(len(d.marks) for d in pool)
    marks = np.empty((len(pool), width), dtype=np.float64)
    for i, d in enumerate(pool):
        m = np.asarray(d.marks, dtype=np.float64)
        marks[i, : m.size] = m
        marks[i, m.size:] = m[-1]   # repetir la última marca no cambia ninguna regla
    n_trades = np.asarray([d.n_trades for d in pool], dtype=np.int64)
    return marks, n_trades


def simulate_evaluation(program: Program, pool: list[DayPath], *, contracts: int, horizon: int, n_paths: int,
                        seed: int, mean_block: float | None = None, idx: np.ndarray | None = None) -> dict:
    """Evaluación de ``n_paths`` cuentas sobre días remuestreados del pool. Devuelve probabilidades y estados."""
    if not pool:
        raise ValueError("pool vacío")
    for d in pool:
        d.validate()
    if idx is None:
        if mean_block is None:
            mean_block = mean_block_length(np.asarray([float(d.marks[-1]) for d in pool]))
        idx = stationary_bootstrap_indices(len(pool), horizon, n_paths, mean_block, seed)
    n_paths, horizon = idx.shape
    ev = program.phases.evaluation
    ml = ev.max_loss
    s = float(ev.start_balance.value)
    dd = ml.amount
    lock = lock_level(ml, s)
    realtime = ml.mode != "trailing_eod" or ml.check == "realtime_unrealized"
    dll = ev.daily_loss if ev.daily_loss is not None and ev.daily_loss.enabled else None
    if dll is not None and dll.base != "day_start_balance":
        raise NotImplementedError("DLL con base distinta de day_start_balance")
    target = float(ev.profit_target.value)
    c = None
    if ev.consistency is not None:
        if ev.consistency.on_violation != "raise_target":
            raise NotImplementedError("consistency.on_violation distinto de raise_target")
        c = ev.consistency.max_best_day_fraction
    min_days = int(ev.min_trading_days.value) if ev.min_trading_days and ev.min_trading_days.value else 0
    max_days = None
    if ev.max_calendar_days is not None and ev.max_calendar_days.value is not None:
        max_days = int(ev.max_calendar_days.value)

    marks_pool, ntr_pool = _pool_matrix(pool)
    width = marks_pool.shape[1]
    balance = np.full(n_paths, s)
    peak_eod = np.full(n_paths, s)
    peak_i = np.full(n_paths, s)
    thr = np.full(n_paths, s - dd)
    best = np.zeros(n_paths)
    tdays = np.zeros(n_paths, dtype=np.int64)
    days = np.zeros(n_paths, dtype=np.int64)
    status = np.zeros(n_paths, dtype=np.int8)
    pass_day = np.full(n_paths, -1, dtype=np.int64)
    for t in range(horizon):
        active = status == ACTIVE
        if not active.any():
            break
        rows = idx[:, t]
        m = marks_pool[rows] * contracts
        b = balance
        peak = np.maximum(peak_i, b)
        th = thr.copy()
        close = b + m[:, -1]
        ended = ~active
        breach = np.zeros(n_paths, dtype=bool)
        for j in range(1, width):
            e = b + m[:, j]
            live = ~ended
            if ml.mode == "trailing_intraday":
                peak = np.where(live, np.maximum(peak, e), peak)
                th = np.where(live, np.maximum(th, np.minimum(peak - dd, lock)), th)
            if realtime:
                hit = live & (e <= th)
                breach |= hit
                close = np.where(hit, e, close)
                ended = ended | hit
                live = ~ended
            if dll is not None:
                d = live & ((e - b) <= -dll.amount)
                close = np.where(d, e, close)
                if dll.action == "breach":
                    breach |= d
                ended = ended | d
        if not realtime:
            breach |= active & ~breach & (close <= th)
        pnl = close - b
        days = days + active
        tdays = tdays + (active & (ntr_pool[rows] > 0))
        best = np.where(active, np.maximum(best, pnl), best)
        balance = np.where(active, close, balance)
        peak_i = np.where(active, peak, peak_i)
        thr = np.where(active, th, thr)
        status = np.where(active & breach, FAILED_MLL, status).astype(np.int8)
        ok = active & ~breach
        if ml.mode == "trailing_eod":
            peak_eod = np.where(ok, np.maximum(peak_eod, balance), peak_eod)
            thr = np.where(ok, np.maximum(thr, np.minimum(peak_eod - dd, lock)), thr)
        required = np.full(n_paths, target) if c is None else np.maximum(target, best / c)
        passed = ok & (balance - s >= required) & (tdays >= min_days)
        status = np.where(passed, PASSED, status).astype(np.int8)
        pass_day = np.where(passed, t + 1, pass_day)
        if max_days is not None:
            status = np.where(ok & ~passed & (days >= max_days), FAILED_TIMEOUT, status).astype(np.int8)

    p_pass = float(np.mean(status == PASSED))
    passed_days = pass_day[pass_day > 0]
    return {
        "p_pass": p_pass,
        "p_fail_mll": float(np.mean(status == FAILED_MLL)),
        "p_timeout": float(np.mean(status == FAILED_TIMEOUT)),
        "p_active_end": float(np.mean(status == ACTIVE)),
        "se_p_pass": math.sqrt(p_pass * (1 - p_pass) / n_paths),
        "median_days_to_pass": float(np.median(passed_days)) if passed_days.size else None,
        "idx": idx,
        "status": status,
        "balance": balance,
    }
