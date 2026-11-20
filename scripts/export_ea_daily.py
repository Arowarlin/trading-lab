"""Exporta la serie diaria de R del EA us100-ftmo1 (solo lectura de datos).

No registra trials, no abre bases de datos y no envía órdenes. Ejecuta el
motor protegido ``ea_us100_engine.run`` sobre la caché M5 real en hora de NY y
guarda ``reports/ea/us100-ftmo1_daily_r.parquet``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from tradinglab.config import ROOT
from tradinglab.ea_us100_engine import run, stats

CACHE = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
REPORT = ROOT / "reports" / "ea" / "us100-ftmo1_v3.json"
DEFAULT_OUT = ROOT / "reports" / "ea" / "us100-ftmo1_daily_r.parquet"


def daily_r_from_trades(trades: pd.DataFrame) -> pd.Series:
    """Suma el R de cada operación por fecha de salida (día natural)."""

    if trades is None or trades.empty or "t_exit" not in trades or "r" not in trades:
        return pd.Series(dtype=float, name="r")
    exits = pd.to_datetime(trades["t_exit"]).dt.normalize()
    values = pd.to_numeric(trades["r"], errors="coerce")
    series = values.groupby(exits).sum().sort_index()
    series.name = "r"
    return series.astype(float)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2021-10-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    if not CACHE.exists():
        raise SystemExit(f"Sin datos: no existe {CACHE}")
    bars = pd.read_parquet(CACHE)
    start = pd.Timestamp(args.start)
    bars = bars[bars.index >= start]
    if args.end:
        bars = bars[bars.index <= pd.Timestamp(args.end)]
    if bars.empty:
        raise SystemExit("Sin datos: el tramo solicitado está vacío")

    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    params = dict(payload.get("params") or {})
    trades = run(bars, p=params)
    summary = stats(trades)
    daily = daily_r_from_trades(trades)

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"date": daily.index, "r": daily.to_numpy(dtype=float)})
    frame.to_parquet(output, index=False)

    print(f"barras: {len(bars)} - {bars.index[0]} -> {bars.index[-1]}")
    print(
        f"operaciones: {summary.get('n', 0)} - expectativa {summary.get('expR')} - "
        f"PF {summary.get('pf')} - total R {summary.get('totR')}"
    )
    print(
        f"dias con R: {len(daily)} - {daily.index[0] if len(daily) else 'Sin datos'} -> "
        f"{daily.index[-1] if len(daily) else 'Sin datos'}"
    )
    print(f"guardado: {output}")


if __name__ == "__main__":
    main()
