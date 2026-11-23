"""Estrategias sinteticas y trazas de paridad para F12a.

No son campanas ni datos reales: sirven para probar el exportador y dejar
tres pares ``.mq5`` + ``.trace.csv`` que el operador puede comparar en el
Tester cuando quiera. Las barras se generan con semilla fija y no se ejecuta
ninguna campana ni backtest con datos de mercado.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .export_mql5 import ExportResult, export_strategy

__all__ = [
    "SYNTHETIC_STRATEGIES",
    "build_samples",
    "synthetic_bars",
]

_DAYS = 40
_START = "2026-01-05"
_BARS_PER_DAY = 78  # 09:30-16:00 M5


def _strategy(
    *,
    entry_long: dict,
    entry_short: dict | None,
    stop_type: str = "atr",
    stop_mult: float = 1.5,
    stop_n: int = 14,
    target_rr: float | None = 2.0,
    time_exit_minutes: int | None = 240,
    max_trades: int = 2,
    cooldown_minutes: int = 25,
) -> dict:
    exit_spec: dict = {
        "stop": {"type": stop_type, "mult": stop_mult, "n": stop_n},
        "target": None if target_rr is None else {"type": "rr", "rr": target_rr},
        "opposite_signal": False,
    }
    if time_exit_minutes is not None:
        exit_spec["time_exit_minutes"] = time_exit_minutes
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "warmup_minutes": 7200,
        "session": {
            "start": "09:35",
            "end": "15:45",
            "flat_at": "15:55",
            "or_minutes": 15,
        },
        "long_entry": entry_long,
        "short_entry": entry_short,
        "exit": exit_spec,
        "sizing": {"risk_per_trade_r": 1.0},
        "limits": {
            "max_trades_per_day": max_trades,
            "cooldown_minutes": cooldown_minutes,
        },
    }


SYNTHETIC_STRATEGIES: dict[str, dict] = {
    "synthetic_trend": _strategy(
        entry_long={
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "n": 50},
        },
        entry_short={
            "kind": "lt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "n": 50},
        },
        stop_mult=1.5,
        target_rr=2.0,
        time_exit_minutes=240,
        cooldown_minutes=25,
    ),
    "synthetic_reversion": _strategy(
        entry_long={
            "kind": "and",
            "args": [
                {
                    "kind": "lt",
                    "left": {"kind": "indicator", "ind": "bollinger_pct", "n": 20, "params": {"k": 2.0}},
                    "right": {"kind": "const", "value": 0.05},
                },
                {
                    "kind": "lt",
                    "left": {"kind": "indicator", "ind": "rsi", "n": 14},
                    "right": {"kind": "const", "value": 30.0},
                },
            ],
        },
        entry_short=None,
        stop_mult=2.0,
        target_rr=1.5,
        time_exit_minutes=180,
        cooldown_minutes=50,
    ),
    "synthetic_breakout": _strategy(
        entry_long={
            "kind": "and",
            "args": [
                {
                    "kind": "or",
                    "args": [
                        {
                            "kind": "gt",
                            "left": {"kind": "price", "price": "close"},
                            "right": {"kind": "level", "level": "opening_range_high"},
                        },
                        {"kind": "pattern", "pattern": "bos_up", "params": {"left": 3, "right": 3}},
                    ],
                },
                {"kind": "pattern", "pattern": "range_expansion", "n": 20, "params": {"mult": 1.5}},
            ],
        },
        entry_short=None,
        stop_type="pct",
        stop_mult=0.3,
        target_rr=2.0,
        time_exit_minutes=120,
        cooldown_minutes=25,
    ),
}


def synthetic_bars(seed: int = 11) -> pd.DataFrame:
    """Barras M5 sinteticas de 40 dias habiles, 09:30-16:00 NY."""

    rng = np.random.default_rng(int(seed))
    days = pd.bdate_range(_START, periods=_DAYS)
    stamps: list[pd.Timestamp] = []
    for day in days:
        stamps.extend(pd.date_range(day + pd.Timedelta(hours=9, minutes=30), periods=_BARS_PER_DAY, freq="5min"))
    index = pd.DatetimeIndex(stamps).tz_localize("America/New_York").tz_convert("UTC")
    count = len(index)
    returns = rng.normal(0.0, 0.0009, count)
    close = 20000.0 * np.exp(np.cumsum(returns))
    open_ = np.empty(count, dtype=float)
    open_[0] = 20000.0
    open_[1:] = close[:-1]
    wick = np.abs(rng.normal(0.0, 0.0005, count))
    high = np.maximum(open_, close) * (1.0 + wick)
    low = np.minimum(open_, close) * (1.0 - wick)
    volume = rng.integers(100, 1000, count).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tickvol": volume,
        },
        index=pd.DatetimeIndex(index, name="ts"),
    )


def build_samples(out_dir: str | Path) -> dict[str, ExportResult]:
    """Genera los tres .mq5, manifests y trazas de forma determinista."""

    target = Path(out_dir)
    bars = synthetic_bars()
    results: dict[str, ExportResult] = {}
    for name, strategy in SYNTHETIC_STRATEGIES.items():
        results[name] = export_strategy(
            strategy,
            account_id="CFD-001",
            out_dir=target,
            bars=bars,
            write_trace=True,
            stem=name,
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera los 3 samples MQL5 de F12a.")
    parser.add_argument(
        "--out",
        default="tests/fixtures/f12_export/generated",
        help="directorio de salida (por defecto el fixture del repo)",
    )
    args = parser.parse_args(argv)
    results = build_samples(args.out)
    for name, result in sorted(results.items()):
        print(f"{name}: {result.mq5_path.name} sha256={result.sha256} magic={result.magic}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
