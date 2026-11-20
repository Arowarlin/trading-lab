"""Benchmark de la cola con preparación única por worker.

Genera 3 años de barras M5 sintéticas y 120 estrategias válidas (variantes de
la plantilla NY), ejecuta ``jobs.run_queue`` con 12 workers y una base temporal
``discovery.db`` e imprime los jobs/minuto medidos. No usa datos reales, no
escribe en el repo y no se registra como tarea.
"""

from __future__ import annotations

import copy
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tradinglab.config import ROOT
from tradinglab.discovery import databank, dsl, jobs

BARS_PER_YEAR_M5 = 365 * 24 * 12
TEMPLATE = ROOT / "config" / "discovery" / "templates" / "ny_open_vol_filter.yaml"


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
    bars = BARS_PER_YEAR_M5 * 3
    count = 120
    workers = 12
    frame = _dataset(bars)
    strategies = _strategies(count)
    print("TradingLab · bench cola (preparación por worker)")
    print(
        f"barras/backtest: {bars:,} ({bars / BARS_PER_YEAR_M5:.2f} años M5) · "
        f"workers: {workers} · jobs: {count}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "discovery.db"
        databank.add_campaign(
            "bench",
            {"instrument": "US100", "timeframe": "M5"},
            instrument="US100",
            timeframe="M5",
            db_path=db,
        )
        added = jobs.enqueue("bench", strategies, db_path=db)
        setup = jobs.QueueSetup(bars=frame, template="ny_open_vol_filter")
        started = time.perf_counter()
        summary = jobs.run_queue(
            "bench", workers, setup=setup, db_path=db, batch_size=32
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
