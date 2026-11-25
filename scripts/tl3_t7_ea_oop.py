"""TL3-B · T7: EA v3.2 fuera de periodo en US100 Dukascopy."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_early_closes, nyse_holidays
from tradinglab.ea_lab.nq_adapter import atr_ratio, load_spread_profile, prepare_nq, weekly_lcb
from tradinglab.ea_us100 import load_setfile, params_from_set
from tradinglab.ea_us100_engine import run as run_engine
from tradinglab.tl3 import registry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DUKA = ROOT / "data" / "cache" / "dukascopy" / "US100_M1.parquet"
US100 = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
SETFILE = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
REPORT = ROOT / "TL3_REPORTS" / "ea_oop_dukascopy.md"
START = pd.Timestamp("2012-01-03")
END = pd.Timestamp("2021-08-31")
WARMUP = pd.Timestamp("2011-10-01")
SLIPS = [0.0, 0.5, 1.0, 2.0, 3.0]


def _json_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ny(index):
    idx = pd.DatetimeIndex(index)
    return idx.tz_convert("America/New_York") if idx.tz is not None else idx


def _holidays(start=2011, end=2021):
    values = set(nyse_holidays(start, end))
    values.update(nyse_early_closes(start, end))
    values.update(
        item for item in NYSE_SPECIAL_CLOSURES if start <= item // 10000 <= end
    )
    return {pd.Timestamp(str(item)).normalize() for item in values}


def _coverage(m1: pd.DataFrame, holidays):
    ny = m1.copy()
    ny.index = _ny(ny.index)
    if ny.index.tz is not None:
        ny.index = ny.index.tz_localize(None)
    valid = {}
    for day in sorted(set(ny.index.normalize())):
        if day in holidays or day.day_of_week >= 5:
            continue
        session = ny.loc[day + pd.Timedelta(hours=9, minutes=30) : day + pd.Timedelta(hours=15, minutes=44)]
        night_start = day - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        night = ny.loc[night_start : day + pd.Timedelta(hours=9, minutes=29)]
        valid[day] = len(session) >= 371 and len(night) >= 744
    return valid


def _params(k: float, slip: float | None = None):
    p = params_from_set(load_setfile(SETFILE))
    p["min_sl"] *= k
    p["max_spread"] *= k
    p["be_off"] *= k
    if slip is not None:
        p["slip"] = float(slip)
    return p


def _stats(trades):
    if trades is None or trades.empty:
        return {"n": 0, "exp": None, "sd": None, "pf": None, "dd": None, "win": None}
    r = trades.r.to_numpy(float)
    wins = r[r > 0].sum()
    losses = -r[r <= 0].sum()
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return {
        "n": int(len(r)),
        "exp": float(r.mean()),
        "sd": float(r.std(ddof=1)) if len(r) > 1 else None,
        "pf": float(wins / losses) if losses > 0 else None,
        "dd": float(np.max(peak - equity)),
        "win": float(100.0 * (r > 0).mean()),
    }


def _fmt(value, digits=4):
    return "Sin datos" if value is None else f"{value:.{digits}f}"


def _slip_eq(rows):
    pos = [r for r in rows if r["exp"] is not None and r["exp"] > 0]
    neg = [r for r in rows if r["exp"] is not None and r["exp"] <= 0]
    if not pos or not neg:
        return None
    left = max(pos, key=lambda r: r["slip"])
    right = min(neg, key=lambda r: r["slip"])
    if left["slip"] == right["slip"]:
        return float(left["slip"])
    return float(
        left["slip"]
        + (0 - left["exp"]) * (right["slip"] - left["slip"]) / (right["exp"] - left["exp"])
    )


def main():
    duka = pd.read_parquet(DUKA)
    profile = load_spread_profile(build=True)
    bars = prepare_nq(duka, profile=profile)
    us100 = pd.read_parquet(US100)
    k = atr_ratio(
        us100, bars, start="2022-01-03", end="2022-12-30"
    )
    quality_k = 1.0 if k is None or 0.9 <= k <= 1.1 else float(k)
    holidays = _holidays()
    valid = _coverage(duka, holidays)
    valid_days = {day for day, ok in valid.items() if ok}

    trades = run_engine(bars.loc[WARMUP:], _params(quality_k))
    trades = trades[(trades.t >= START) & (trades.t <= END)].copy()
    trades = trades[trades.t.dt.normalize().isin(valid_days)].copy()

    stats = _stats(trades)
    lcb = weekly_lcb(trades) if not trades.empty else {"lcb95": None}
    verdict = (
        "confirma"
        if stats["n"] >= 300
        and stats["exp"] is not None
        and stats["exp"] >= 0.10
        and lcb["lcb95"] is not None
        and lcb["lcb95"] > 0
        else "no confirma"
    )
    if stats["n"] < 300:
        verdict = "Sin datos (muestra insuficiente)"

    slip_rows = []
    for slip in SLIPS:
        tr = run_engine(bars.loc[WARMUP:], _params(quality_k, slip))
        tr = tr[(tr.t >= START) & (tr.t <= END)]
        tr = tr[tr.t.dt.normalize().isin(valid_days)]
        st = _stats(tr)
        slip_rows.append({"slip": slip, **st})

    yearly = []
    for year, group in trades.groupby(trades.t.dt.year):
        yearly.append({"year": int(year), **_stats(group)})
    sides = []
    for side, group in trades.groupby(np.where(trades.d == 1, "long", "short")):
        sides.append({"side": side, **_stats(group)})

    excluded_holiday = sum(
        1 for day in sorted(set(bars.loc[WARMUP:].index.normalize())) if day in holidays
    )
    lines = [
        "# TL3 · T7 EA v3.2 fuera de periodo US100 Dukascopy",
        "",
        f"Datos: Dukascopy US100 M1 → M5 con `prepare_nq`; ventana de entradas {START.date()} → {END.date()}.",
        f"k = ATR14 M5 Dukascopy / US100.cash 2022: {_fmt(k)} → aplicado {quality_k:.6f}.",
        "Costes: spread por franja 5 min (perfil 2021-2026, anacrónico declarado), slippage 0,5 pt/lado, comisión 0.",
        f"Sesiones válidas por cobertura: {len(valid_days)}; festivos/cierres excluidos: {excluded_holiday}.",
        "Filtro de noticias no modelado (igual que el backtest).",
        "",
        "## Resultado",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones | {stats['n']} |",
        f"| Win rate | {_fmt(stats['win'], 1)} % |",
        f"| Expectativa | {_fmt(stats['exp'])} R |",
        f"| Desviación | {_fmt(stats['sd'])} |",
        f"| PF | {_fmt(stats['pf'])} |",
        f"| DD | {_fmt(stats['dd'])} R |",
        f"| LCB95 semanal | {_fmt(lcb['lcb95'])} R |",
        f"| **Veredicto** | **{verdict}** |",
        "",
        "## Por año",
        "",
        "| Año | Ops | Exp R | Total R | DD R |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in yearly:
        lines.append(
            f"| {row['year']} | {row['n']} | {_fmt(row['exp'])} | "
            f"{_fmt((row['exp'] or 0) * row['n'])} | {_fmt(row['dd'])} |"
        )
    lines += ["", "## Largo/corto", "", "| Lado | Ops | Exp R |", "|---|---:|---:|"]
    for row in sides:
        lines.append(f"| {row['side']} | {row['n']} | {_fmt(row['exp'])} |")
    lines += ["", "## Slippage", "", "| Slip pt/lado | Ops | Exp R | PF |", "|---:|---:|---:|---:|"]
    for row in slip_rows:
        lines.append(f"| {row['slip']:g} | {row['n']} | {_fmt(row['exp'])} | {_fmt(row['pf'])} |")
    lines += [
        "",
        f"`slip_eq` ≈ **{_fmt(_slip_eq(slip_rows), 2)} puntos/lado**.",
        "",
        "Solo una ejecución del criterio. La tabla por año es descriptiva.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    # Registro append-only.
    experiment_id = "exp-t7-" + hashlib.sha256(
        f"{START}-{END}-{quality_k}".encode()
    ).hexdigest()[:12]
    registry.add_experiment(
        experiment_id,
        "H-2026-008",
        git_commit="HEAD",
        config_hash=_json_hash(SETFILE),
        data_manifest_hash=_json_hash(ROOT / "data/tl3/manifest.json"),
        thresholds=registry.thresholds_hash(),
        cost_model_version=2,
        seed=42,
        n_variants=1,
        metrics={"n": stats["n"], "exp": stats["exp"], "lcb95": lcb["lcb95"], "verdict": verdict},
        report_path=str(REPORT),
        status="run",
    )
    registry.add_sample("US100", "M5", str(START.date()), str(END.date()), "H-2026-008", "holdout")
    status = "validated" if verdict == "confirma" else "rejected"
    reason = None if verdict == "confirma" else ("no_power" if stats["n"] < 300 else "holdout_fail")
    with registry.connect() as con:
        row = con.execute("SELECT * FROM hypotheses WHERE hypothesis_id='H-2026-008'").fetchone()
        cols = [c for c in row.keys() if c not in ("hypothesis_id","parent_id","status","rejection_reason","created_at")]
        values = [row[c] for c in cols]
        con.execute(
            f"INSERT INTO hypotheses (hypothesis_id,parent_id,{','.join(cols)},status,rejection_reason,created_at)"
            f" VALUES (?,?,{','.join('?' for _ in cols)},?,?,?)",
            ["H-2026-008b", "H-2026-008", *values, status, reason, row["created_at"]],
        )
        con.commit()


if __name__ == "__main__":
    main()
