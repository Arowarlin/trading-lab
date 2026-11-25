"""TL3-C · C3: T8 corregido (una ejecución)."""

from __future__ import annotations

import hashlib
import math
import re
import sys
from datetime import date, time

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_early_closes, nyse_holidays
from tradinglab.ea_lab.nq_adapter import build_spread_profile, load_spread_profile
from tradinglab.tl3 import registry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FOMC = ROOT / ".orquestador" / "fomc-fechas.md"
REPORT = ROOT / "TL3_REPORTS" / "h2_pre_fomc.md"
DATA = ROOT / "data" / "cache" / "dukascopy"
PROFILES = {
    "US100": ROOT / "data" / "cache" / "ea" / "us100_spread_profile_ny5m.parquet",
    "US500": ROOT / "data" / "cache" / "ea" / "us500_spread_profile_ny5m.parquet",
    "US30": ROOT / "data" / "cache" / "ea" / "us30_spread_profile_ny5m.parquet",
}
POINTS = {"US100": 0.01, "US500": 0.01, "US30": 0.01}
START = date(2011, 9, 19)
END = date(2026, 11, 25)
SWAP_BPS = 7.33 / 100 / 365 * 1e4


def _events():
    text = FOMC.read_text(encoding="utf-8")
    dates = []
    for line in text.splitlines():
        if not line.startswith("| 20"):
            continue
        for item in re.findall(r"20\d{2}-\d{2}-\d{2}", line):
            day = date.fromisoformat(item)
            if START <= day <= END and day != date(2026, 12, 9):
                dates.append(day)
    return sorted(set(dates))


def _holidays():
    values = set(nyse_holidays(2011, 2026))
    values.update(nyse_early_closes(2011, 2026))
    values.update(item for item in NYSE_SPECIAL_CLOSURES if 2011 <= item // 10000 <= 2026)
    return {date.fromisoformat(f"{item // 10000:04d}-{item // 100 % 100:02d}-{item % 100:02d}") for item in values}


def _prev_session(day, holidays):
    current = day - pd.Timedelta(days=1)
    while current.day_of_week >= 5 or current.date() in holidays:
        current -= pd.Timedelta(days=1)
    return current.date()


def _profile(symbol):
    target = PROFILES[symbol]
    if target.exists():
        return load_spread_profile(target)
    source = ROOT / "data" / "cache" / "ea" / f"{symbol}_CASH_M5_NY.parquet"
    return build_spread_profile(source, target) if source.exists() else None


def _clock_map(frame, target: time, column: str):
    """Barra más cercana a ±2 min; empate → la anterior."""

    minutes = frame.index.hour * 60 + frame.index.minute
    wanted = target.hour * 60 + target.minute
    diff = np.abs(minutes - wanted)
    mask = diff <= 2
    sub = frame.loc[mask, [column]].copy()
    sub["date"] = sub.index.normalize()
    sub["diff"] = diff[mask]
    sub["clock"] = minutes[mask]
    sub = sub.sort_values(["date", "diff", "clock"]).drop_duplicates("date", keep="first")
    return sub.set_index("date")[column]


def _daily(symbol):
    path = DATA / f"{symbol}_M1.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)[["open", "close"]]
    frame.index = pd.DatetimeIndex(frame.index)
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("America/New_York").tz_localize(None)
    result = pd.DataFrame(index=sorted(set(frame.index.date)))
    result["entry"] = _clock_map(frame, time(15, 55), "open")
    result["early"] = _clock_map(frame, time(12, 25), "close")
    result["late"] = _clock_map(frame, time(13, 55), "close")
    return result


def _components(index_frame, profile, point, entry_day, exit_day, late):
    if index_frame is None or entry_day not in index_frame.index or exit_day not in index_frame.index:
        return None
    entry = index_frame.loc[entry_day].get("entry")
    exit_ = index_frame.loc[exit_day].get("late" if late else "early")
    if pd.isna(entry) or pd.isna(exit_) or entry <= 0:
        return None
    slots = profile.set_index("slot")["spread"] if profile is not None else None
    if slots is None:
        return None
    spread_in = float(slots.get(191, slots.median()))
    spread_out = float(slots.get(167 if late else 149, slots.median()))
    gross = math.log(float(exit_) / float(entry)) * 1e4
    spread = (spread_in + spread_out) * point / float(entry) * 1e4
    slippage = 100.0 * point / float(entry) * 1e4
    swap = SWAP_BPS * (3.0 if entry_day.weekday() == 4 else 1.0)
    return {
        "gross": gross,
        "spread": spread,
        "slippage": slippage,
        "swap": swap,
        "net": gross - spread - slippage - swap,
    }


def _observation(frames, profiles, entry_day, exit_day, late):
    rows = [
        _components(frames[symbol], profiles[symbol], POINTS[symbol], entry_day, exit_day, late)
        for symbol in ("US100", "US500", "US30")
    ]
    rows = [row for row in rows if row is not None]
    if not rows:
        return None
    return {key: float(np.mean([row[key] for row in rows])) for key in rows[0]}


def _has_bars(index_frame, entry_day, exit_day, late):
    if index_frame is None or entry_day not in index_frame.index or exit_day not in index_frame.index:
        return False
    entry = index_frame.loc[entry_day].get("entry")
    exit_ = index_frame.loc[exit_day].get("late" if late else "early")
    return not (pd.isna(entry) or pd.isna(exit_) or entry <= 0)


def main():
    events = _events()
    holidays = _holidays()
    frames = {symbol: _daily(symbol) for symbol in ("US100", "US500", "US30")}
    profiles = {symbol: _profile(symbol) for symbol in ("US100", "US500", "US30")}

    valid_events = []
    excluded = {symbol: 0 for symbol in ("US100", "US500", "US30")}
    for day in events:
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        late = day >= date(2016, 1, 1)
        ok = False
        for symbol in ("US100", "US500", "US30"):
            if _has_bars(frames[symbol], entry_day, day, late):
                ok = True
            else:
                excluded[symbol] += 1
        if ok:
            valid_events.append(day)

    near = set()
    for day in events:
        for delta in (-1, 0, 1):
            near.add(day + pd.Timedelta(days=delta))
    placebo = []
    for day in sorted({d for d in frames["US100"].index if isinstance(d, date)}):
        if day in near or day in holidays or day.weekday() >= 5 or day < START or day > END:
            continue
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        value = _observation(frames, profiles, entry_day, day, day >= date(2016, 1, 1))
        if value is not None:
            placebo.append(value)

    n_events = len(valid_events)
    sigma_gross = float(np.std([row["gross"] for row in placebo], ddof=1)) if len(placebo) > 1 else None
    sigma_net = float(np.std([row["net"] for row in placebo], ddof=1)) if len(placebo) > 1 else None
    mde = 2.49 * sigma_gross / math.sqrt(n_events) if sigma_gross is not None and n_events else None
    lines = [
        "# TL3-C · T8 corregido: H2 deriva previa al FOMC",
        "",
        "> La versión de 972d916 es inválida: swap 100× mayor; ver COLA-TL3-C H-a.",
        "",
        f"Eventos programados: {len(events)}; con datos válidos: {n_events}.",
        f"Exclusiones evento×índice: US100 {excluded['US100']}, US500 {excluded['US500']}, US30 {excluded['US30']}.",
        f"Placebo: {len(placebo)} días; σ bruta = {sigma_gross:.2f} bps; σ neta = {sigma_net:.2f} bps; MDE = {mde:.2f} bps; δ = 30 bps.",
        "",
    ]
    if mde is None or mde > 30:
        lines += [
            "## Veredicto: **rejected: no_power**",
            "",
            "MDE > 30 bps; no se calcula el retorno de los eventos.",
            "",
        ]
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        _register(n_events, sigma_gross, sigma_net, mde, "rejected", "no_power", lines)
        return

    event_rows = {}
    for day in valid_events:
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        value = _observation(frames, profiles, entry_day, day, day >= date(2016, 1, 1))
        if value is not None:
            event_rows[day] = value
    event_gross = np.array([row["gross"] for row in event_rows.values()], float)
    event_net = np.array([row["net"] for row in event_rows.values()], float)
    placebo_gross = np.array([row["gross"] for row in placebo], float)
    t_value = (event_gross.mean() - placebo_gross.mean()) / math.sqrt(
        event_gross.var(ddof=1) / len(event_gross)
        + placebo_gross.var(ddof=1) / len(placebo_gross)
    )
    rng = np.random.default_rng(42)
    means = np.array(
        [rng.choice(event_net, size=len(event_net), replace=True).mean() for _ in range(10_000)]
    )
    lcb = float(np.percentile(means, 5))
    confirms = t_value >= 1.645 and lcb > 0
    verdict = "confirma" if confirms else "no confirma"
    lines += [
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Eventos | {n_events} |",
        f"| Bruto eventos | {event_gross.mean():.2f} bps |",
        f"| Bruto placebo | {placebo_gross.mean():.2f} bps |",
        f"| t Welch unilateral (bruto) | {t_value:.3f} |",
        f"| Neto eventos | {event_net.mean():.2f} bps |",
        f"| LCB95 neto (bootstrap) | {lcb:.2f} bps |",
        f"| **Veredicto** | **{verdict}** |",
        "",
        "### Escalera bruta → neta (eventos)",
        "",
        "| Componente | bps |",
        "|---|---:|",
    ]
    for key, label in (
        ("gross", "Bruto"),
        ("spread", "− spread"),
        ("slippage", "− slippage"),
        ("swap", "− swap"),
        ("net", "Neto"),
    ):
        value = float(np.mean([row[key] for row in event_rows.values()]))
        lines.append(f"| {label} | {value:.2f} |")
    lines += [
        "",
        "### Por época",
        "",
        "| Época | n | Bruto bps | Neto bps |",
        "|---|---:|---:|---:|",
    ]
    for label, start in (("≤ 2015", date(2011, 9, 19)), ("≥ 2016", date(2016, 1, 1))):
        subset = [row for day, row in event_rows.items() if (day < date(2016, 1, 1)) == (start < date(2016, 1, 1))]
        if subset:
            lines.append(
                f"| {label} | {len(subset)} | {np.mean([r['gross'] for r in subset]):.2f} | "
                f"{np.mean([r['net'] for r in subset]):.2f} |"
            )
    lines += [
        "",
        "Lectura fijada: «no confirma» descarta un efecto de 30 bps, no uno de ~20 bps; «confirma» es una replicación independiente 2011-2026 en CFD. Referencia: `TL3_REPORTS/literatura_T8_H1.md`.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    _register(n_events, sigma_gross, sigma_net, mde, "validated" if confirms else "rejected", None if confirms else "holdout_fail", lines)


def _register(n_events, sigma_gross, sigma_net, mde, status, reason, lines):
    experiment_id = f"exp-t8-fix-{n_events}-{int(sigma_gross or 0)}"
    registry.add_experiment(
        experiment_id,
        "H-2026-009",
        git_commit="HEAD",
        config_hash=registry.thresholds_hash(),
        data_manifest_hash=hashlib.sha256((ROOT / "data/tl3/manifest.json").read_bytes()).hexdigest(),
        thresholds=registry.thresholds_hash(),
        cost_model_version=2,
        seed=42,
        n_variants=1,
        metrics={"n_events": n_events, "sigma_gross": sigma_gross, "sigma_net": sigma_net, "mde": mde, "verdict": status},
        report_path=str(REPORT),
        status="run",
    )
    for symbol in ("US100", "US500", "US30"):
        registry.add_sample(symbol, "M1", "2011-09-19", "2026-11-25", "H-2026-009", "holdout")
    with registry.connect() as con:
        row = con.execute("SELECT * FROM hypotheses WHERE hypothesis_id='H-2026-009'").fetchone()
        cols = [c for c in row.keys() if c not in ("hypothesis_id","parent_id","status","rejection_reason","created_at")]
        values = [row[c] for c in cols]
        con.execute(
            f"INSERT INTO hypotheses (hypothesis_id,parent_id,{','.join(cols)},status,rejection_reason,created_at)"
            f" VALUES (?,?,{','.join('?' for _ in cols)},?,?,?)",
            ["H-2026-009c", "H-2026-009", *values, status, reason, pd.Timestamp.now('UTC').isoformat()],
        )
        con.commit()


if __name__ == "__main__":
    main()
