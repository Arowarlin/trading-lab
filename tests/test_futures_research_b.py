"""FUT-D2/D3: detectores de Research B, conteo sin desenlaces y evaluador (solo velas sintéticas)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from tradinglab.futures.research_b import (
    Spec,
    count_events,
    detect,
    evaluate,
    newey_west_t,
    outcome,
    seal,
)

MES = Spec(tick=0.25, point_value=5.0, tick_value=1.25, commission_side=0.5)


def day_bars(d: str, base: float, overrides: dict[str, tuple[float, float, float, float]] | None = None,
             start: str = "00:00", end: str = "16:59") -> pd.DataFrame:
    idx = pd.date_range(f"{d} {start}", f"{d} {end}", freq="min", tz="America/New_York")
    df = pd.DataFrame({"open": base, "high": base + 0.25, "low": base - 0.25, "close": base}, index=idx)
    for hhmm, (o, h, lo, c) in (overrides or {}).items():
        df.loc[pd.Timestamp(f"{d} {hhmm}", tz="America/New_York"), ["open", "high", "low", "close"]] = [o, h, lo, c]
    return df


def test_seal_drops_oos2():
    b = pd.concat([day_bars("2023-12-29", 100.0), day_bars("2024-01-02", 100.0)])
    assert seal(b).index.max().year == 2023


def test_rb02_opening_drive_long_and_outcome():
    over = {"09:30": (100.0, 100.5, 95.0, 100.25), "09:34": (100.5, 101.0, 100.25, 101.0),
            "09:35": (101.0, 101.25, 100.75, 101.0), "10:29": (102.0, 102.5, 101.75, 102.5)}
    b = day_bars("2023-03-01", 100.0, over)
    b.loc[(b.index > pd.Timestamp("2023-03-01 09:35", tz="America/New_York"))
          & (b.index < pd.Timestamp("2023-03-01 10:29", tz="America/New_York")), ["open", "high", "low", "close"]] = \
        [101.5, 101.75, 101.25, 101.5]
    (ev,) = detect(b, "RB-02", MES)
    assert (ev.side, ev.entry, ev.stop) == (1, 101.0, 94.75)      # mínimo de 9:30-9:34 = 95 − 1 tick
    r = outcome(ev, b, MES)
    assert r == pytest.approx(((102.5 - 101.0) * 5 - 2 * (0.5 + 1.25)) / (6.25 * 5))


def test_rb02_stop_first_and_no_drive():
    over = {"09:30": (100.0, 100.5, 95.0, 100.25), "09:34": (100.5, 101.0, 100.25, 101.0),
            "09:35": (101.0, 101.25, 100.75, 101.0), "09:40": (100.0, 108.0, 94.0, 101.5)}
    b = day_bars("2023-03-01", 100.0, over)
    (ev,) = detect(b, "RB-02", MES)
    assert outcome(ev, b, MES) == pytest.approx((-6.25 * 5 - 3.5) / 31.25)   # stop y objetivo en la vela: gana el stop
    flat = day_bars("2023-03-02", 100.0)                                   # 9:34 cierra igual que abrió 9:30
    assert detect(flat, "RB-02", MES) == []


def test_rb08_gap_needs_median_range_and_fills_target():
    sessions = [day_bars(d.date().isoformat(), 100.0, {"12:00": (100.0, 104.0, 100.0, 100.0)})
                for d in pd.bdate_range("2023-01-30", "2023-02-28")]          # 21 sesiones: rango RTH 4,25
    gap_day = day_bars("2023-03-01", 104.0, {"09:30": (104.0, 104.25, 103.75, 104.0),
                                             "09:31": (104.0, 104.0, 103.75, 104.0),
                                             "10:00": (101.0, 101.0, 99.5, 99.75)})
    b = pd.concat(sessions + [gap_day])
    evs = [e for e in detect(b, "RB-08", MES) if e.session == date(2023, 3, 1)]
    assert len(evs) == 1 and evs[0].side == -1 and evs[0].target == 100.0 and evs[0].stop == 108.0
    assert outcome(evs[0], b, MES) == pytest.approx((4.0 * 5 - 3.5) / (4.0 * 5))   # objetivo atravesado por 1 tick


def test_count_has_no_outcome_columns():
    over = {"09:30": (100.0, 100.5, 99.75, 100.25), "09:34": (100.5, 101.0, 100.25, 101.0)}
    b = pd.concat([day_bars(f"2023-03-0{d}", 100.0, over) for d in (1, 2, 3)])
    c = count_events(b, "RB-02", MES)
    assert set(c.columns) == {"events", "stop_lt_2_ticks", "cost_filter", "tradable"}
    assert int(c.loc[2023, "events"]) == 3
    assert not {"r", "pnl", "outcome", "exit"} & {col.lower() for col in c.columns}


def test_newey_west_matches_iid_without_autocorrelation():
    x = np.array([1.0, -1.0] * 50) + 0.1
    t0 = newey_west_t(x, lags=0)
    assert t0 == pytest.approx(x.mean() / (x.std(ddof=0) / np.sqrt(x.size)))
    assert newey_west_t(x, lags=5) != t0


def test_evaluate_verdicts_on_synthetic_drift():
    rng = np.random.default_rng(1)
    days = []
    for d in pd.bdate_range("2022-01-03", "2023-12-29")[:300]:
        up = rng.random() < 0.7
        over = {"09:30": (100.0, 100.5, 95.0, 100.25), "09:34": (100.5, 101.0, 100.25, 101.0),
                "09:35": (101.0, 101.25, 100.75, 101.0),
                "10:29": (101.0, 105.0 if up else 101.25, 99.0, 105.0 if up else 99.0)}
        days.append(day_bars(d.date().isoformat(), 100.0, over, start="09:00", end="11:00"))
    res = evaluate(pd.concat(days), "RB-02", MES, t_crit=2.326, split=date(2022, 12, 1))
    assert res["n"] == 300 and res["mean_r"] > 0
    assert res["verdict"].startswith("candidata")
