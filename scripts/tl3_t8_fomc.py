"""TL3-B · T8: H2 deriva previa al FOMC (una ejecución)."""

from __future__ import annotations

import math
import re
import sys
from datetime import date, time

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_early_closes, nyse_holidays
from tradinglab.ea_lab.nq_adapter import load_spread_profile
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
SWAP_BPS = 7.33 / 365 * 1e4


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
    values.update(
        item for item in NYSE_SPECIAL_CLOSURES if 2011 <= item // 10000 <= 2026
    )
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
    # Construir desde la caché EA si existe.
    source = ROOT / "data" / "cache" / "ea" / f"{symbol}_CASH_M5_NY.parquet"
    if not source.exists():
        return None
    from tradinglab.ea_lab.nq_adapter import build_spread_profile
    return build_spread_profile(source, target)


def _daily(symbol):
    path = DATA / f"{symbol}_M1.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    frame = frame[["open", "close"]].copy()
    frame.index = pd.DatetimeIndex(frame.index)
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("America/New_York").tz_localize(None)
    result = pd.DataFrame(index=sorted(set(frame.index.date)))
    for clock, key in (
        (time(15, 55), "entry"),
        (time(12, 25), "early"),
        (time(13, 55), "late"),
    ):
        part = frame[frame.index.time == clock]
        if part.empty:
            continue
        column = "open" if key == "entry" else "close"
        result[key] = part.groupby(part.index.date)[column].last()
    return result


def _net(index_frame, profile, point, entry_day, exit_day, late):
    if index_frame is None or entry_day not in index_frame.index or exit_day not in index_frame.index:
        return None
    row_in = index_frame.loc[entry_day]
    row_out = index_frame.loc[exit_day]
    entry = row_in.get("entry")
    exit_ = row_out.get("late" if late else "early")
    if pd.isna(entry) or pd.isna(exit_) or entry <= 0:
        return None
    gross = math.log(float(exit_) / float(entry)) * 1e4
    slots = profile.set_index("slot")["spread"] if profile is not None else None
    if slots is None:
        return None
    spread_entry = float(slots.get(191, slots.median()))
    spread_exit = float(slots.get(167 if late else 149, slots.median()))
    cost = (spread_entry + spread_exit + 1.0) * point / float(entry) * 1e4
    swap = SWAP_BPS * (3.0 if entry_day.weekday() == 4 else 1.0)
    return gross - cost - swap


def _has_bars(index_frame, entry_day, exit_day, late):
    if index_frame is None or entry_day not in index_frame.index or exit_day not in index_frame.index:
        return False
    row_in = index_frame.loc[entry_day]
    row_out = index_frame.loc[exit_day]
    entry = row_in.get("entry")
    exit_ = row_out.get("late" if late else "early")
    return not (pd.isna(entry) or pd.isna(exit_) or entry <= 0)


def _observation(frames, profiles, entry_day, exit_day, late):
    values = [
        _net(frames[symbol], profiles[symbol], POINTS[symbol], entry_day, exit_day, late)
        for symbol in ("US100", "US500", "US30")
    ]
    clean = [value for value in values if value is not None]
    return float(np.mean(clean)) if clean else None


def main():
    events = _events()
    holidays = _holidays()
    frames = {symbol: _daily(symbol) for symbol in ("US100", "US500", "US30")}
    profiles = {symbol: _profile(symbol) for symbol in ("US100", "US500", "US30")}
    valid_events = []
    for day in events:
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        late = day >= date(2016, 1, 1)
        if any(
            _has_bars(frames[symbol], entry_day, day, late)
            for symbol in ("US100", "US500", "US30")
        ):
            valid_events.append(day)

    near = set()
    for day in events:
        for delta in (-1, 0, 1):
            near.add(day + pd.Timedelta(days=delta))
    placebo = {}
    for day in sorted({d for d in frames["US100"].index if isinstance(d, date)}):
        if day in near or day in holidays or day.weekday() >= 5 or day < START or day > END:
            continue
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        value = _observation(frames, profiles, entry_day, day, day >= date(2016, 1, 1))
        if value is not None:
            placebo[day] = value

    n_events = len(valid_events)
    sigma = float(np.std(list(placebo.values()), ddof=1)) if len(placebo) > 1 else None
    mde = 2.49 * sigma / math.sqrt(n_events) if sigma is not None and n_events else None
    lines = [
        "# TL3 · T8 H2 deriva previa al FOMC",
        "",
        f"Eventos programados: {len(events)}; con datos válidos: {n_events}.",
        f"Placebo: {len(placebo)} días; σ = {sigma:.2f} bps; MDE = {mde:.2f} bps; δ = 30 bps." if sigma and mde else "Placebo: Sin datos.",
        "",
    ]
    if mde is None or mde > 30:
        lines += [
            "## Veredicto: **rejected: no_power**",
            "",
            "MDE > 30 bps; no se calcula el retorno de los eventos.",
            "No se reinterpreta ni se cambia la ventana.",
            "",
        ]
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        _register("H-2026-009", n_events, sigma, mde, "rejected", "no_power", lines)
        return

    event_nets = {}
    for day in valid_events:
        entry_day = _prev_session(pd.Timestamp(day), holidays)
        value = _observation(frames, profiles, entry_day, day, day >= date(2016, 1, 1))
        if value is not None:
            event_nets[day] = value

    event_values = np.array(list(event_nets.values()), float)
    placebo_values = np.array(list(placebo.values()), float)
    # Welch unilateral.
    t_value = (event_values.mean() - placebo_values.mean()) / math.sqrt(
        event_values.var(ddof=1) / len(event_values)
        + placebo_values.var(ddof=1) / len(placebo_values)
    )
    rng = np.random.default_rng(42)
    means = np.array(
        [rng.choice(event_values, size=len(event_values), replace=True).mean() for _ in range(10_000)]
    )
    lcb = float(np.percentile(means, 5))
    confirms = t_value >= 1.645 and lcb > 0
    verdict = "confirma" if confirms else "no confirma"
    lines += [
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Eventos | {n_events} |",
        f"| Media neta eventos | {event_values.mean():.2f} bps |",
        f"| Media placebo | {placebo_values.mean():.2f} bps |",
        f"| t Welch unilateral | {t_value:.3f} |",
        f"| LCB95 bootstrap | {lcb:.2f} bps |",
        f"| **Veredicto** | **{verdict}** |",
        "",
        "Costes: spread por franja + 0,5 pt/lado + swap CFD-006 7,33 %/365 por noche (×3 si cruza el día triple).",
        "Filtro de noticias no modelado (igual que el backtest).",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    _register("H-2026-009", n_events, sigma, mde, "validated" if confirms else "rejected", None if confirms else "holdout_fail", lines)


def _register(hypothesis, n_events, sigma, mde, status, reason, lines):
    experiment_id = f"exp-t8-{n_events}-{int(sigma or 0)}"
    registry.add_experiment(
        experiment_id,
        hypothesis,
        git_commit="HEAD",
        config_hash=registry.thresholds_hash(),
        data_manifest_hash=__import__("hashlib").sha256((ROOT / "data/tl3/manifest.json").read_bytes()).hexdigest(),
        thresholds=registry.thresholds_hash(),
        cost_model_version=2,
        seed=42,
        n_variants=1,
        metrics={"n_events": n_events, "sigma_bps": sigma, "mde_bps": mde, "verdict": status},
        report_path=str(REPORT),
        status="run",
    )
    registry.add_sample("US100", "M1", "2011-09-19", "2026-11-25", hypothesis, "holdout")
    with registry.connect() as con:
        row = con.execute("SELECT * FROM hypotheses WHERE hypothesis_id=?", (hypothesis,)).fetchone()
        cols = [c for c in row.keys() if c not in ("hypothesis_id","parent_id","status","rejection_reason","created_at")]
        values = [row[c] for c in cols]
        con.execute(
            f"INSERT INTO hypotheses (hypothesis_id,parent_id,{','.join(cols)},status,rejection_reason,created_at)"
            f" VALUES (?,?,{','.join('?' for _ in cols)},?,?,?)",
            [hypothesis + "b", hypothesis, *values, status, reason, row["created_at"]],
        )
        con.commit()


if __name__ == "__main__":
    main()
