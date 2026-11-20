"""Benchmark de la cola con preparación única por worker.

Genera 4 años de barras M5 sintéticas (3 años de IS + OOS-1/OOS-2), 120
estrategias válidas y ejecuta ``jobs.run_queue`` con 12 workers sobre una base
temporal ``discovery.db``. Imprime los jobs/minuto medidos. No usa datos
reales, no escribe en el repo y no se registra como tarea.
"""

from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, dsl, jobs

BARS_PER_YEAR_M5 = 365 * 24 * 12
FRAME_YEARS = 4
TEMPLATE = ROOT / "config" / "discovery" / "templates" / "ny_open_vol_filter.yaml"
SEGMENTS = {
    "is": ["2023-01-02", "2025-12-31"],
    "oos1": ["2026-01-01", "2026-06-30"],
    "oos2": ["2026-07-01", None],
}


def _dataset(bars: int, seed: int = 20261120) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-02", periods=bars, freq="5min", tz="UTC")
    close = 20000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 6.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 6.0, bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def _strategies(count: int) -> list[dict]:
    base = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))["strategy"]
    result = []
    for index in range(count):
        strategy = copy.deepcopy(base)
        pct = round(0.5 + 0.05 * (index % 10), 2)
        stop_mult = round(1.0 + 0.05 * (index // 10), 3)
        strategy["long_entry"]["args"][1]["params"]["pct"] = pct
        strategy["short_entry"]["args"][1]["params"]["pct"] = pct
        strategy["exit"]["stop"]["mult"] = stop_mult
        strategy["exit"]["target"]["rr"] = round(1.5 + 0.05 * (index // 10), 3)
        errors = dsl.validate(strategy)
        if errors:
            raise SystemExit(f"estrategia {index} inválida: {errors}")
        result.append(strategy)
    return result


def main() -> int:
    bars = BARS_PER_YEAR_M5 * FRAME_YEARS
    count = 120
    workers = 12
    frame = _dataset(bars)
    strategies = _strategies(count)
    print("TradingLab · bench cola (preparación por worker)")
    print(
        f"frame: {bars:,} barras M5 ({bars / BARS_PER_YEAR_M5:.2f} años) · "
        f"IS: 3 años · workers: {workers} · jobs: {count}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "discovery.db"
        campaigns.register(
            "US100",
            "M5",
            "ny_open_vol_filter",
            "small",
            segments=SEGMENTS,
            frame=frame,
            campaign_id="bench",
            db_path=db,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "tradinglab.cli",
                "discovery",
                "approve",
                "bench",
                "--approved-by-operator",
                "--db",
                str(db),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        added = jobs.enqueue("bench", strategies, db_path=db)
        started = time.perf_counter()
        summary = jobs.run_queue(
            "bench", workers, bars=frame, db_path=db, batch_size=32
        )
        elapsed = time.perf_counter() - started
        strategies_written = databank.list_strategies(
            campaign_id="bench", limit=None, db_path=db
        )
        evaluations = sum(
            len(databank.list_evaluations(row["id"], db_path=db))
            for row in strategies_written
        )
    jobs_per_minute = summary["done"] / elapsed * 60.0 if elapsed > 0 else 0.0
    print(f"encoladas: {added} · estrategias: {len(strategies_written)} · "
          f"evaluaciones: {evaluations}")
    print(
        f"resultado: done={summary['done']} failed={summary['failed']} "
        f"queued={summary['queued']} running={summary['running']} "
        f"cancelled={summary['cancelled']}"
    )
    print(
        f"preparación por worker (máx): {summary['prep_max_s']:.3f} s · "
        f"motor: {summary['backend']} · prioridad: {summary['priority']}"
    )
    print(
        f"medido: {summary['done']} jobs en {elapsed:.2f} s -> "
        f"{jobs_per_minute:.1f} jobs/min"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
