"""NQ-A · Prueba fuera de periodo del EA con NQ (preregistro).

No descarga datos. Lee un parquet M1 de NQ ya descargado y la caché de
US100.cash. En `--synthetic` genera datos falsos y no toca NQ real.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from tradinglab.config import ROOT
from tradinglab.ea_lab.nq_adapter import (
    apply_spread,
    atr_ratio,
    filter_crossing_rolls,
    load_spread_profile,
    match_validity,
    prepare_nq,
    resample_m5,
    weekly_lcb,
)
from tradinglab.ea_us100 import load_setfile, params_from_set
from tradinglab.ea_us100_engine import run as run_engine

DEFAULT_SETFILE = (
    ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
)
DEFAULT_US100 = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
DEFAULT_REPORT = ROOT / "reports" / "ea" / "us100-ftmo1-nq-2010-2017.md"
VALID_START = pd.Timestamp("2018-01-02")
VALID_END = pd.Timestamp("2018-12-31")
TEST_START = pd.Timestamp("2010-06-06")
TEST_END = pd.Timestamp("2017-12-27")


def _params(path: Path, k: float) -> dict:
    values = load_setfile(path)
    params = params_from_set(values)
    params["min_sl"] = params["min_sl"] * k
    params["max_spread"] = params["max_spread"] * k
    params["be_off"] = params["be_off"] * k
    return params


def _run(frame: pd.DataFrame, params: dict) -> pd.DataFrame:
    trades = run_engine(frame, params)
    return trades if trades is not None else pd.DataFrame()


def _within(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    if trades is None or trades.empty:
        return trades
    return trades[(trades["t"] >= start) & (trades["t"] <= end)].copy()


def _stats(trades: pd.DataFrame) -> dict:
    if trades is None or trades.empty:
        return {"n": 0, "exp": None, "sd": None, "pf": None, "dd": None}
    values = trades["r"].to_numpy(float)
    wins = values[values > 0].sum()
    losses = -values[values <= 0].sum()
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return {
        "n": int(len(values)),
        "exp": float(values.mean()),
        "sd": float(values.std(ddof=1)) if len(values) > 1 else None,
        "pf": float(wins / losses) if losses > 0 else None,
        "dd": float(np.max(peak - equity)) if len(equity) else 0.0,
    }


def _yearly(trades: pd.DataFrame):
    rows = []
    for year, group in trades.groupby(trades["t"].dt.year):
        values = group["r"].to_numpy(float)
        rows.append(
            {
                "year": int(year),
                "n": int(len(values)),
                "exp": float(values.mean()),
                "total": float(values.sum()),
            }
        )
    return rows


def _fmt(value, digits=4):
    if value is None:
        return "Sin datos"
    return f"{value:.{digits}f}"


def _synthetic_frames():
    def make(year: int, seed: int):
        start = pd.Timestamp(f"{year}-01-02 09:30")
        end = pd.Timestamp(f"{year}-12-30 16:00")
        index = pd.date_range(start, end, freq="min")
        keep = (index.day_of_week < 5) & (
            ((index.hour * 60 + index.minute) >= 570)
            & ((index.hour * 60 + index.minute) <= 960)
        )
        index = index[keep]
        rng = np.random.default_rng(seed)
        trend = np.linspace(0, 8, len(index))
        close = 100.0 + trend + np.cumsum(rng.normal(0, 0.08, len(index)))
        open_ = np.r_[close[0], close[:-1]]
        frame = pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) + 0.2,
                "low": np.minimum(open_, close) - 0.2,
                "close": close,
                "volume": 10.0,
            },
            index=index,
        )
        return frame

    nq_m1 = pd.concat([make(2018, 7), make(2016, 11)])
    nq_m5 = resample_m5(nq_m1)
    profile = load_spread_profile(build=True)
    us100 = apply_spread(nq_m5.copy(), profile)
    return nq_m1, us100


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m1", type=Path, help="Parquet M1 de NQ")
    parser.add_argument("--us100", type=Path, default=DEFAULT_US100)
    parser.add_argument("--setfile", type=Path, default=DEFAULT_SETFILE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--rolls", type=Path, help="JSON de rolls (opcional)")
    args = parser.parse_args(argv)

    if args.synthetic:
        nq_m1, us100 = _synthetic_frames()
        valid_start, valid_end = VALID_START, VALID_END
        test_start, test_end = pd.Timestamp("2016-01-04"), pd.Timestamp("2016-12-30")
        label = "SINTÉTICO (no es la prueba real)"
    else:
        if args.m1 is None or not args.m1.exists():
            print("Sin datos: falta --m1", file=sys.stderr)
            return 2
        nq_m1 = pd.read_parquet(args.m1)
        us100 = pd.read_parquet(args.us100)
        valid_start, valid_end = VALID_START, VALID_END
        test_start, test_end = TEST_START, TEST_END
        label = str(args.m1)

    profile = load_spread_profile(build=True)
    nq_bars = prepare_nq(nq_m1, profile=profile)
    us100 = us100.copy()
    us100.index = pd.DatetimeIndex(us100.index)
    if "spread" not in us100.columns:
        us100 = apply_spread(us100, profile)

    ratio = atr_ratio(
        us100,
        nq_bars,
        start=str(valid_start.date()),
        end=str(valid_end.date()),
    )
    k = 1.0 if ratio is None or 0.9 <= ratio <= 1.1 else float(ratio)
    params_nq = _params(args.setfile, k)
    params_us100 = _params(args.setfile, 1.0)

    nq_all = _run(nq_bars, params_nq)
    us100_all = _run(us100, params_us100)
    rolls = None
    if args.rolls and args.rolls.exists():
        import json

        payload = json.loads(args.rolls.read_text(encoding="utf-8"))
        rolls = [
            pd.Timestamp(item) if not isinstance(item, dict) else pd.Timestamp(item["when"])
            for item in payload
        ]
    nq_all, crossed = filter_crossing_rolls(nq_all, rolls)

    nq_valid = _within(nq_all, valid_start, valid_end)
    us100_valid = _within(us100_all, valid_start, valid_end)
    validity = match_validity(nq_valid, us100_valid)

    lines = [
        "# EA us100-ftmo1 · NQ fuera de periodo",
        "",
        f"Datos: {label}",
        f"Periodo de validez: {valid_start.date()} → {valid_end.date()}",
        f"Periodo de prueba: {test_start.date()} → {test_end.date()}",
        "",
        "## Escalado",
        "",
        f"- ATR14 M5 NQ / US100 en 2018: {_fmt(ratio)}",
        f"- k aplicado a `min_sl`, `max_spread`, `be_off`: {k:.6f}",
        "- `slip=0,5` y parámetros en ATR/%/horas/R no se escalan.",
        f"- Operaciones descartadas por roll: {crossed}",
        "",
        "## Validez 2018",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones NQ | {validity.candidate} |",
        f"| Operaciones US100 | {validity.reference} |",
        f"| Emparejadas | {validity.matched} ({validity.matched_pct:.1f} %) |",
        f"| Correlación de R | {_fmt(validity.correlation)} |",
        f"| ¿Válida? | {'Sí' if validity.valid else 'No'} |",
        "",
    ]

    if not validity.valid:
        lines += [
            "## Resultado",
            "",
            "**NO VÁLIDA (Sin datos).** No se cumple el mínimo de 80 % de",
            "operaciones emparejadas y correlación ≥ 0,7. No se mira",
            "2010-2017.",
            "",
        ]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 0

    nq_test = _within(nq_all, test_start, test_end)
    stats = _stats(nq_test)
    lcb = weekly_lcb(nq_test) if nq_test is not None and not nq_test.empty else {
        "lcb95": None
    }
    verdict = (
        "confirma"
        if stats["n"] >= 300
        and stats["exp"] is not None
        and stats["exp"] >= 0.10
        and lcb["lcb95"] is not None
        and lcb["lcb95"] > 0
        else "no confirma"
    )
    lines += [
        f"## Prueba {test_start.date()} → {test_end.date()}",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones | {stats['n']} |",
        f"| Expectativa | {_fmt(stats['exp'])} R |",
        f"| Desviación | {_fmt(stats['sd'])} |",
        f"| PF | {_fmt(stats['pf'])} |",
        f"| DD | {_fmt(stats['dd'])} R |",
        f"| LCB95 | {_fmt(lcb['lcb95'])} R |",
        "| Criterio | n ≥ 300, exp ≥ 0,10, LCB95 > 0 |",
        f"| **Veredicto** | **{verdict}** |",
        "",
        "### Por año",
        "",
        "| Año | Ops | Exp R | Total R |",
        "|---|---:|---:|---:|",
    ]
    for row in _yearly(nq_test):
        lines.append(
            f"| {row['year']} | {row['n']} | {_fmt(row['exp'])} | {_fmt(row['total'])} |"
        )
    lines.append("")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
