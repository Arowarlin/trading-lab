"""NQ-B · Enmienda A: puente Dukascopy, validez NQ y prueba 2010-2017.

No descarga datos. Lee NQ M1, la referencia Dukascopy US100 M1 y la caché
US100.cash. En `--synthetic` genera datos falsos y no toca NQ real.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery.calendars import (
    NYSE_SPECIAL_CLOSURES,
    nyse_early_closes,
    nyse_holidays,
)
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SETFILE = (
    ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
)
DEFAULT_US100 = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
DEFAULT_REPORT = ROOT / "reports" / "ea" / "us100-ftmo1-nq-2010-2017.md"
DEFAULT_REFERENCE = ROOT / "data" / "cache" / "dukascopy" / "US100_M1.parquet"
DEFAULT_NQ = ROOT / "data" / "cache" / "databento" / "US100_M1.parquet"
VALID_START = pd.Timestamp("2018-01-02")
VALID_END = pd.Timestamp("2018-12-31")
BRIDGE_START = pd.Timestamp("2022-01-03")
BRIDGE_END = pd.Timestamp("2022-12-30")
TEST_START = pd.Timestamp("2010-06-06")
TEST_END = pd.Timestamp("2017-12-27")
SLIPS = [0.0, 0.5, 1.0, 2.0, 3.0]


class NqRunError(RuntimeError):
    pass


def _params(path: Path, k: float = 1.0, slip: float | None = None) -> dict:
    values = load_setfile(path)
    params = params_from_set(values)
    params["min_sl"] *= k
    params["max_spread"] *= k
    params["be_off"] *= k
    if slip is not None:
        params["slip"] = float(slip)
    return params


def _run(frame: pd.DataFrame, params: dict) -> pd.DataFrame:
    trades = run_engine(frame, params)
    return trades if trades is not None else pd.DataFrame()


def _within(trades: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    if trades is None or trades.empty:
        return trades
    return trades[(trades["t"] >= start) & (trades["t"] <= end)].copy()


def _granularity_error(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> str | None:
    if frame is None or frame.empty:
        return "Sin datos: granularidad"
    window = frame.loc[start:end]
    if len(window) < 2:
        return "Sin datos: granularidad"
    deltas = pd.Series(window.index).diff().dropna()
    if deltas.empty or deltas.median() > pd.Timedelta(minutes=10):
        return "Sin datos: granularidad"
    return None


def _first_session_after(day: pd.Timestamp) -> pd.Timestamp:
    return pd.bdate_range(day + pd.Timedelta(days=1), periods=1)[0].normalize()


def holiday_sessions(start_year: int, end_year: int) -> list[pd.Timestamp]:
    """Festivos NYSE, cierres especiales y cierres tempranos del rango."""

    values = set(nyse_holidays(start_year, end_year))
    values.update(nyse_early_closes(start_year, end_year))
    values.update(
        item
        for item in NYSE_SPECIAL_CLOSURES
        if start_year <= item // 10000 <= end_year
    )
    return sorted({pd.Timestamp(str(item)) for item in values})


def load_roll_sessions(path: Path | None) -> tuple[list[pd.Timestamp], str]:
    if path is None or not path.exists():
        return [], "Sin datos: sin --roll-dates"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw = payload.get("rolls") or payload.get("dates") or []
        explicit = payload.get("excluded_sessions") or []
        source = str(payload.get("source") or "")
    else:
        raw = payload
        explicit = []
        source = ""
    if explicit:
        sessions = [pd.Timestamp(item).normalize() for item in explicit]
    else:
        rolls = [pd.Timestamp(item).normalize() for item in raw]
        sessions = [_first_session_after(item) for item in rolls]
    return sorted(set(sessions)), source


def exclude_roll_sessions(
    trades: pd.DataFrame,
    sessions: list[pd.Timestamp],
) -> tuple[pd.DataFrame, dict[int, int]]:
    if trades is None or trades.empty or not sessions:
        return trades if trades is not None else pd.DataFrame(), {}
    allowed = set(sessions)
    mask = trades["t"].dt.normalize().isin(allowed)
    excluded = trades[mask]
    counts = (
        excluded.assign(year=excluded["t"].dt.year)
        .groupby("year")
        .size()
        .astype(int)
        .to_dict()
    )
    return trades[~mask].copy(), counts


def _stats(trades: pd.DataFrame) -> dict:
    if trades is None or trades.empty:
        return {"n": 0, "exp": None, "sd": None, "pf": None, "dd": None, "win": None}
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
        "win": float(100.0 * (values > 0).mean()),
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


def _slip_eq(rows):
    positive = [row for row in rows if row["exp"] is not None and row["exp"] > 0]
    negative = [row for row in rows if row["exp"] is not None and row["exp"] <= 0]
    if not positive or not negative:
        return None
    left = max(positive, key=lambda row: row["slip"])
    right = min(negative, key=lambda row: row["slip"])
    if right["slip"] == left["slip"]:
        return float(left["slip"])
    return float(
        left["slip"]
        + (0.0 - left["exp"])
        * (right["slip"] - left["slip"])
        / (right["exp"] - left["exp"])
    )


def _slippage(
    bars: pd.DataFrame,
    setfile: Path,
    k: float,
    sessions: list[pd.Timestamp],
    holidays: list[pd.Timestamp],
    start: pd.Timestamp,
    end: pd.Timestamp,
):
    rows = []
    for slip in SLIPS:
        trades = _run(bars, _params(setfile, k, slip))
        trades, _ = exclude_roll_sessions(trades, sessions)
        trades, _ = exclude_roll_sessions(trades, holidays)
        window = _within(trades, start, end)
        stats = _stats(window)
        rows.append({"slip": slip, **stats})
    return rows


def _bridge(
    reference: pd.DataFrame,
    us100: pd.DataFrame,
    setfile: Path,
) -> dict:
    error = _granularity_error(us100, BRIDGE_START, BRIDGE_END)
    if error:
        return {"error": error}
    ref_trades = _within(
        _run(reference, _params(setfile, 1.0)), BRIDGE_START, BRIDGE_END
    )
    us_trades = _within(
        _run(us100, _params(setfile, 1.0)), BRIDGE_START, BRIDGE_END
    )
    validity = match_validity(ref_trades, us_trades)
    return {
        "error": None,
        "reference": validity.reference,
        "candidate": validity.candidate,
        "matched": validity.matched,
        "matched_pct": validity.matched_pct,
        "correlation": validity.correlation,
        "valid": validity.valid,
    }


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
        return pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) + 0.2,
                "low": np.minimum(open_, close) - 0.2,
                "close": close,
                "volume": 10.0,
            },
            index=index,
        )

    nq_m1 = pd.concat([make(2018, 7), make(2022, 13), make(2016, 11)])
    reference_m1 = nq_m1.copy()
    profile = load_spread_profile(build=True)
    reference = apply_spread(resample_m5(reference_m1), profile)
    us100 = apply_spread(resample_m5(reference_m1.copy()), profile)
    return nq_m1, reference_m1, reference, us100


def _write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m1", type=Path, default=DEFAULT_NQ)
    parser.add_argument("--reference-m1", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--us100", type=Path, default=DEFAULT_US100)
    parser.add_argument("--setfile", type=Path, default=DEFAULT_SETFILE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--roll-dates", type=Path)
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args(argv)

    if args.synthetic:
        nq_m1, reference_m1, reference, us100 = _synthetic_frames()
        valid_start, valid_end = VALID_START, VALID_END
        test_start, test_end = pd.Timestamp("2016-01-04"), pd.Timestamp("2016-12-30")
        label = "SINTÉTICO (no es la prueba real)"
    else:
        if not args.m1.exists() or not args.reference_m1.exists():
            print("Sin datos: falta --m1 o --reference-m1", file=sys.stderr)
            return 2
        nq_m1 = pd.read_parquet(args.m1)
        reference_m1 = pd.read_parquet(args.reference_m1)
        us100 = pd.read_parquet(args.us100)
        valid_start, valid_end = VALID_START, VALID_END
        test_start, test_end = TEST_START, TEST_END
        label = str(args.m1)

    profile = load_spread_profile(build=True)
    nq_bars = prepare_nq(nq_m1, profile=profile)
    reference_bars = prepare_nq(reference_m1, profile=profile)
    us100 = us100.copy()
    us100.index = pd.DatetimeIndex(us100.index)
    if "spread" not in us100.columns:
        us100 = apply_spread(us100, profile)

    # k: NQ frente a la referencia Dukascopy, nunca frente a la caché del EA.
    ratio = atr_ratio(
        reference_bars,
        nq_bars,
        start=str(valid_start.date()),
        end=str(valid_end.date()),
    )
    k = 1.0 if ratio is None or 0.9 <= ratio <= 1.1 else float(ratio)
    sessions, roll_source = load_roll_sessions(args.roll_dates)

    if args.bridge:
        bridge = _bridge(reference_bars, us100, args.setfile)
        lines = [
            "# NQ-B · A-1 puente Dukascopy vs US100.cash (2022)",
            "",
            f"Datos de referencia: {args.reference_m1 if not args.synthetic else label}",
            "La caché del EA solo se usa como referencia del puente.",
            "",
        ]
        if bridge["error"]:
            lines += [f"**{bridge['error']}**", ""]
            _write_report(args.report, lines)
            print("\n".join(lines))
            return 2
        lines += [
            "| Métrica | Valor |",
            "|---|---:|",
            f"| Operaciones Dukascopy | {bridge['candidate']} |",
            f"| Operaciones US100.cash | {bridge['reference']} |",
            f"| Emparejadas | {bridge['matched']} ({bridge['matched_pct']:.1f} %) |",
            f"| Correlación de R | {_fmt(bridge['correlation'])} |",
            f"| ¿Válida? | {'Sí' if bridge['valid'] else 'No'} |",
            "",
            "Solo paridad: no se calculan expectativa, PF ni R totales de 2022.",
            "",
        ]
        _write_report(args.report, lines)
        print("\n".join(lines))
        return 0

    nq_all = _run(nq_bars, _params(args.setfile, k))
    ref_all = _run(reference_bars, _params(args.setfile, 1.0))
    holidays = holiday_sessions(2010, 2018)
    nq_all, nq_roll_excluded = exclude_roll_sessions(nq_all, sessions)
    ref_all, ref_roll_excluded = exclude_roll_sessions(ref_all, sessions)
    nq_all, nq_holiday_excluded = exclude_roll_sessions(nq_all, holidays)
    ref_all, ref_holiday_excluded = exclude_roll_sessions(ref_all, holidays)
    nq_all, crossed = filter_crossing_rolls(nq_all, [])

    nq_valid = _within(nq_all, valid_start, valid_end)
    ref_valid = _within(ref_all, valid_start, valid_end)
    validity = match_validity(nq_valid, ref_valid)

    lines = [
        "# EA us100-ftmo1 · NQ.c.0 (futuro CME, Databento GLBX.MDP3)",
        "",
        f"Datos NQ: {label}",
        "Referencia: Dukascopy US100 M1 procesado con `prepare_nq`.",
        f"Periodo de validez A-2: {valid_start.date()} → {valid_end.date()}",
        f"Periodo de prueba B3: {test_start.date()} → {test_end.date()}",
        "",
        "## Escalado",
        "",
        f"- ATR14 M5 NQ / referencia Dukascopy en 2018: {_fmt(ratio)}",
        f"- k aplicado a `min_sl`, `max_spread`, `be_off`: {k:.6f}",
        "- `slip=0,5` y parámetros en ATR/%/horas/R no se escalan.",
        f"- Rolls: {roll_source or 'Sin datos'}; sesiones excluidas: {len(sessions)}",
        "",
        "## A-2 · Validez NQ 2018",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones NQ | {validity.candidate} |",
        f"| Operaciones referencia | {validity.reference} |",
        f"| Emparejadas | {validity.matched} ({validity.matched_pct:.1f} %) |",
        f"| Correlación de R | {_fmt(validity.correlation)} |",
        f"| ¿Válida? | {'Sí' if validity.valid else 'No'} |",
        "",
        "### Exclusiones A-2",
        "",
        f"- Sesiones de roll: {len(sessions)}; festivos/cierres NYSE: {len(holidays)}",
        f"- NQ rolls: {sum(nq_roll_excluded.values())}; por año: {nq_roll_excluded}",
        f"- NQ festivos/cierres: {sum(nq_holiday_excluded.values())}; por año: {nq_holiday_excluded}",
        f"- Referencia rolls: {sum(ref_roll_excluded.values())}; por año: {ref_roll_excluded}",
        f"- Referencia festivos/cierres: {sum(ref_holiday_excluded.values())}; por año: {ref_holiday_excluded}",
        "",
    ]

    if not validity.valid:
        lines += [
            "## Resultado",
            "",
            "**Prueba no válida (Sin datos).** No se cumple el mínimo de 80 %",
            "de operaciones emparejadas y correlación ≥ 0,7. No se abre",
            "2010-2017.",
            "",
        ]
        _write_report(args.report, lines)
        print("\n".join(lines))
        return 0

    nq_test = _within(nq_all, test_start, test_end)
    stats = _stats(nq_test)
    lcb = weekly_lcb(nq_test)
    slip_rows = _slippage(
        nq_bars, args.setfile, k, sessions, holidays, test_start, test_end
    )
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
        f"## B3 · Prueba {test_start.date()} → {test_end.date()}",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones | {stats['n']} |",
        f"| Win rate | {_fmt(stats['win'], 1)} % |",
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
    lines += [
        "",
        "### Slippage",
        "",
        "| Slip (pt/lado) | Ops | Exp R | PF |",
        "|---:|---:|---:|---:|",
    ]
    for row in slip_rows:
        lines.append(
            f"| {row['slip']:g} | {row['n']} | {_fmt(row['exp'])} | {_fmt(row['pf'])} |"
        )
    lines += [
        "",
        f"`slip_eq` ≈ **{_fmt(_slip_eq(slip_rows), 2)} puntos/lado**.",
        "",
        "### Operaciones excluidas",
        "",
        f"- Rolls NQ: {sum(nq_roll_excluded.values())}; por año: {nq_roll_excluded}",
        f"- Rolls referencia: {sum(ref_roll_excluded.values())}; por año: {ref_roll_excluded}",
        f"- Festivos/cierres NQ: {sum(nq_holiday_excluded.values())}; por año: {nq_holiday_excluded}",
        f"- Festivos/cierres referencia: {sum(ref_holiday_excluded.values())}; por año: {ref_holiday_excluded}",
        f"- Cruces de roll: {crossed} (debería ser 0).",
        "- El filtro de noticias (`InpNewsFilter`) no está modelado en el motor,",
        "  igual que en las 478 operaciones del backtest.",
        "",
        "A-1 y A-2 son controles de paridad; no suman pruebas.",
        "",
    ]
    _write_report(args.report, lines)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
