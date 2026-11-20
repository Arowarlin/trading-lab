"""Benchmark de ``discovery.fastbt`` con datos sintéticos.

Mide backtests/minuto de punta a punta (12 workers por defecto) sobre tres
años de barras M5 generadas en el propio script. No lee datos reales, no
escribe archivos y no se registra como tarea programada.

Uso:
    .\\.venv\\Scripts\\python.exe scripts\\bench_fastbt.py
    .\\.venv\\Scripts\\python.exe scripts\\bench_fastbt.py --quick
"""

from __future__ import annotations

import argparse
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor

BACKEND_ENV = "TRADINGLAB_FASTBT_BACKEND"
BARS_PER_YEAR_M5 = 365 * 24 * 12


def _dataset(bars: int, seed: int):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-02", periods=bars, freq="5min", tz="UTC")
    steps = rng.normal(0.0, 0.0004, bars)
    close = 100.0 * np.exp(np.cumsum(steps))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.0003, bars))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.0003, bars))
    frame = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )
    signal = np.zeros(bars, dtype=bool)
    starts = np.arange(200, bars - 200, 97)
    signal[starts] = True
    return frame, signal


def _worker(task: tuple[str, int, int, int]) -> tuple[int, float, list[float], str]:
    backend, bars, runs, seed = task
    os.environ[BACKEND_ENV] = backend
    import numpy as np

    from tradinglab.discovery import fastbt

    frame, signal = _dataset(bars, seed)
    signals = fastbt.Signals(signal, np.zeros(bars, dtype=bool))
    spec = fastbt.ExitSpec(
        stop="atr",
        stop_mult=1.5,
        stop_n=14,
        target="rr",
        target_rr=2.0,
        breakeven_at_r=1.0,
        time_exit_bars=48,
    )
    cost = fastbt.cfd_costs_from_bps(
        commission_bps=0.5, slippage_bps=1.0, spread_bps=3.0
    )
    limits = fastbt.RunLimits(
        session_tz="UTC",
        weekdays=tuple(range(7)),
        max_trades_per_day=3,
        cooldown_bars=5,
    )
    fastbt.set_backend(backend)
    fastbt.run(signals, frame, spec, cost, limits)  # calienta numba
    times: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        fastbt.run(signals, frame, spec, cost, limits)
        times.append(time.perf_counter() - started)
    return runs, sum(times), times, fastbt.backend()


def _measure(
    backend: str,
    *,
    bars: int,
    workers: int,
    runs_per_worker: int,
    seed: int,
) -> dict[str, float | str]:
    tasks = [
        (backend, bars, runs_per_worker, seed + index)
        for index in range(workers)
    ]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_worker, tasks))
    wall = time.perf_counter() - started
    total_runs = sum(item[0] for item in results)
    all_times = [value for item in results for value in item[2]]
    return {
        "backend": results[0][3] if results else backend,
        "runs": float(total_runs),
        "wall": wall,
        "loop": max((item[1] for item in results), default=0.0),
        "per_minute": total_runs / wall * 60.0 if wall > 0 else 0.0,
        "loop_per_minute": (
            total_runs / max((item[1] for item in results), default=1.0) * 60.0
        ),
        "median_ms": statistics.median(all_times) * 1000.0 if all_times else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de discovery.fastbt")
    parser.add_argument(
        "--bars",
        type=int,
        default=BARS_PER_YEAR_M5 * 3,
        help="barras M5 por backtest (por defecto 3 años)",
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--runs", type=int, default=5, help="backtests por worker")
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument("--quick", action="store_true", help="20k barras y 1 run")
    args = parser.parse_args()
    bars = 20_000 if args.quick else args.bars
    runs = 1 if args.quick else args.runs

    import importlib.util

    have_numba = importlib.util.find_spec("numba") is not None

    print("TradingLab · bench fastbt")
    print(
        f"barras/backtest: {bars:,} ({bars / BARS_PER_YEAR_M5:.2f} años M5) · "
        f"workers: {args.workers} · runs/worker: {runs}"
    )

    numba_row = None
    if have_numba:
        numba_row = _measure(
            "numba",
            bars=bars,
            workers=args.workers,
            runs_per_worker=runs,
            seed=args.seed,
        )
    python_row = _measure(
        "python",
        bars=bars,
        workers=args.workers,
        runs_per_worker=runs,
        seed=args.seed,
    )

    if numba_row is None:
        print("numba    : no disponible en este Python; solo fallback")
    else:
        print(
            f"numba    : {int(numba_row['runs'])} runs · bucle "
            f"{numba_row['loop']:.2f} s -> {numba_row['loop_per_minute']:.1f} "
            f"backtests/min · pared {numba_row['wall']:.2f} s -> "
            f"{numba_row['per_minute']:.1f}/min con arranque "
            f"(mediana {numba_row['median_ms']:.1f} ms/run)"
        )
    print(
        f"python   : {int(python_row['runs'])} runs · bucle "
        f"{python_row['loop']:.2f} s -> {python_row['loop_per_minute']:.1f} "
        f"backtests/min · pared {python_row['wall']:.2f} s -> "
        f"{python_row['per_minute']:.1f}/min con arranque "
        f"(mediana {python_row['median_ms']:.1f} ms/run)"
    )
    if numba_row is not None and python_row["loop_per_minute"] > 0:
        print(
            f"aceleración medida (bucle): "
            f"{numba_row['loop_per_minute'] / python_row['loop_per_minute']:.2f}×"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
