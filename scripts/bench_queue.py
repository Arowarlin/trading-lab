"""Benchmark de la cola con preparación única por worker.

Genera 4 años de barras M5 sintéticas (3 años de IS + OOS-1/OOS-2), 120
estrategias válidas y ejecuta ``jobs.run_queue`` con 12 workers sobre una base
temporal ``discovery.db``. Imprime los jobs/minuto medidos. No usa datos
reales, no escribe en el repo y no se registra como tarea.
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


def _measure(
    db: Path,
    frame: pd.DataFrame,
    strategies: list[dict],
    *,
    campaign_id: str,
    cache_limit_bytes: int | None,
    workers: int,
) -> dict:
    campaigns.register_synthetic(
        frame,
        template="ny_open_vol_filter",
        profile="small",
        segments=SEGMENTS,
        campaign_id=campaign_id,
        db_path=db,
    )
    added = jobs.enqueue(campaign_id, strategies, db_path=db)
    started = time.perf_counter()
    summary = jobs.run_queue(
        campaign_id,
        workers,
        bars=frame,
        db_path=db,
        batch_size=32,
        cache_limit_bytes=cache_limit_bytes,
    )
    elapsed = time.perf_counter() - started
    written = databank.list_strategies(
        campaign_id=campaign_id, limit=None, db_path=db
    )
    evaluations = sum(
        len(databank.list_evaluations(row["id"], db_path=db))
        for row in written
    )
    return {
        "added": added,
        "elapsed": elapsed,
        "summary": summary,
        "strategies": len(written),
        "evaluations": evaluations,
    }


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
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "discovery.db"
        for label, limit, cid in (
            ("sin caché", 0, "bench-before"),
            ("con LRU", None, "bench-after"),
        ):
            measured = _measure(
                db,
                frame,
                strategies,
                campaign_id=cid,
                cache_limit_bytes=limit,
                workers=workers,
            )
            summary = measured["summary"]
            per_minute = (
                summary["done"] / measured["elapsed"] * 60.0
                if measured["elapsed"] > 0
                else 0.0
            )
            rows.append((label, measured, per_minute))
            print(
                f"{label:9s}: {summary['done']} jobs en {measured['elapsed']:.2f} s "
                f"-> {per_minute:.1f} jobs/min · "
                f"cache hits {summary['cache_hits']:,} "
                f"misses {summary['cache_misses']:,} "
                f"bytes {summary['cache_bytes']:,} · "
                f"prep {summary['prep_max_s']:.3f} s"
            )
    before, after = rows[0][2], rows[1][2]
    if before > 0:
        print(f"aceleración medida: {after / before:.2f}×")
    return 0 if all(row[1]["summary"]["failed"] == 0 for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
