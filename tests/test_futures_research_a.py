"""FUT-C2: detectores de Research A y conteo sin desenlaces (velas sintéticas construidas a mano)."""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.futures.research_a import (
    COST_STOP_POINTS,
    count_events,
    detect,
    med_l,
    s_c,
)

NY = "America/New_York"
HIST = [d.date().isoformat() for d in pd.bdate_range("2023-01-02", periods=20)]
HIST_DELTA = {d: (1.0 if i % 2 == 0 else 2.0) for i, d in enumerate(HIST)}
DAY = "2023-02-01"


def bars_day(d: str, *, base: float = 100.0, rng: float = 0.5, volume: float = 100.0,
             delta: float = 0.0, start: str = "09:30", end: str = "15:59") -> pd.DataFrame:
    idx = pd.date_range(f"{d} {start}", f"{d} {end}", freq="min", tz=NY)
    df = pd.DataFrame({"open": base, "high": base + rng, "low": base - rng, "close": base,
                       "volume": volume, "delta": delta}, index=idx)
    df["cvd"] = df["delta"].cumsum()
    return df


def put(df: pd.DataFrame, hhmm: str, o: float, h: float, low: float, c: float, v: float,
        d: float) -> pd.DataFrame:
    """Fija una vela; hay que recalcular el CVD con ``closed``."""
    ts = pd.Timestamp(f"{df.index[0].date().isoformat()} {hhmm}", tz=NY)
    df.loc[ts, ["open", "high", "low", "close", "volume", "delta"]] = [o, h, low, c, v, d]
    return df


def closed(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["cvd"] = out.groupby(out.index.date)["delta"].cumsum()
    return out


def refs_like(bars: pd.DataFrame, *, medV: float = 100.0, medRng: float = 1.0,
              s_delta: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame({"medV": medV, "medRng": medRng, "s_delta": s_delta}, index=bars.index)


def ts(d: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{d} {hhmm}", tz=NY)


def footprint(d: str, hhmm: str, rows: list[tuple[int, float, float]]) -> pd.DataFrame:
    """``rows``: (nivel en ticks, buy, sell)."""
    minute = ts(d, hhmm)
    idx = pd.MultiIndex.from_tuples([(minute, lv) for lv, _, _ in rows], names=["minute", "level"])
    return pd.DataFrame({"buy": [b for _, b, _ in rows], "sell": [s for _, _, s in rows]}, index=idx)


HIST_FP = [footprint(d, "10:30", [(400, 5, 5), (401, 5, 5), (402, 5, 5), (403, 5, 5)]) for d in HIST]
HIST_BARS = pd.concat([bars_day(d, delta=HIST_DELTA[d]) for d in HIST])


def test_a_absorption_long_short_and_volume_filter():
    long_day = closed(put(bars_day("2023-03-01"), "10:00", 100.0, 100.5, 99.5, 100.25, 250, -40))
    (ev,) = detect(long_day, refs_like(long_day), None, "A")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-01", "10:00"), 1, 99.25)

    short_day = closed(put(bars_day("2023-03-02"), "11:00", 100.0, 100.5, 99.5, 99.75, 250, 40))
    (ev,) = detect(short_day, refs_like(short_day), None, "A")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-02", "11:00"), -1, 100.75)

    thin = closed(put(bars_day("2023-03-03"), "10:00", 100.0, 100.5, 99.5, 100.25, 150, -40))
    assert detect(thin, refs_like(thin), None, "A") == []


def test_e_failed_breakout_short_long_and_confirmation():
    b = closed(put(bars_day("2023-03-01"), "10:30", 100.25, 101.5, 100.0, 101.25, 100, -10))
    (ev,) = detect(b, refs_like(b), None, "E")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-01", "10:30"), -1, 101.75)

    up = closed(put(bars_day("2023-03-02"), "10:30", 100.25, 101.5, 100.0, 101.25, 100, 10))
    assert detect(up, refs_like(up), None, "E") == []          # la ruptura trae compra agresora: no es E

    lo = closed(put(bars_day("2023-03-03"), "10:30", 99.75, 100.0, 98.5, 98.75, 100, 10))
    (ev,) = detect(lo, refs_like(lo), None, "E")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-03", "10:30"), 1, 98.25)


def test_h_confirmed_breakout_long_short_and_z_threshold():
    b = closed(put(bars_day("2023-03-01"), "10:30", 100.0, 101.5, 99.75, 101.25, 100, 25))
    (ev,) = detect(b, refs_like(b), None, "H")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-01", "10:30"), 1, 99.5)

    weak = closed(put(bars_day("2023-03-02"), "10:30", 100.0, 101.5, 99.75, 101.25, 100, 15))
    assert detect(weak, refs_like(weak), None, "H") == []      # z = 1,5 < 2

    s = closed(put(bars_day("2023-03-03"), "10:30", 100.0, 100.25, 98.5, 98.75, 100, -25))
    (ev,) = detect(s, refs_like(s), None, "H")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-03", "10:30"), -1, 100.5)


def test_c_delta_divergence_uses_the_20_session_scale():
    down = closed(put(bars_day(DAY), "10:30", 100.0, 101.5, 99.75, 100.5, 100, -25))
    both = pd.concat([HIST_BARS, down])
    (ev,) = detect(both, refs_like(both), None, "C")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts(DAY, "10:30"), -1, 101.75)
    assert s_c(both).loc[ts(DAY, "10:30")] == pytest.approx(1.4826 * 15.0)

    mild = closed(put(bars_day(DAY), "10:30", 100.0, 101.5, 99.75, 100.5, 100, -20))
    no = pd.concat([HIST_BARS, mild])
    assert detect(no, refs_like(no), None, "C") == []          # −20 no supera sC = 22,239

    up = closed(put(bars_day(DAY), "10:30", 100.0, 100.25, 98.5, 99.5, 100, 25))
    hi = pd.concat([HIST_BARS, up])
    (ev,) = detect(hi, refs_like(hi), None, "C")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts(DAY, "10:30"), 1, 98.25)


def test_d_stacked_imbalance_long_short_and_two_levels():
    b = closed(put(bars_day(DAY), "10:30", 100.0, 100.25, 99.75, 100.25, 100, 0))
    long_fp = pd.concat(HIST_FP + [footprint(DAY, "10:30", [(400, 12, 1), (401, 12, 1), (402, 12, 1)])])
    (ev,) = detect(b, refs_like(b), long_fp, "D")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts(DAY, "10:30"), 1, 99.75)

    s = closed(put(bars_day(DAY), "10:30", 100.0, 100.25, 99.75, 99.75, 100, 0))
    short_fp = pd.concat(HIST_FP + [footprint(DAY, "10:30", [(400, 1, 12), (401, 1, 12), (402, 1, 12)])])
    (ev,) = detect(s, refs_like(s), short_fp, "D")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts(DAY, "10:30"), -1, 100.75)

    two = pd.concat(HIST_FP + [footprint(DAY, "10:30", [(400, 12, 1), (401, 12, 1)])])
    assert detect(b, refs_like(b), two, "D") == []
    with pytest.raises(ValueError, match="Sin datos: footprints"):
        detect(b, refs_like(b), None, "D")
    assert ("D", 2023) in count_events(b, refs_like(b), long_fp).index


def test_i_volume_expansion_follows_the_delta_sign():
    b = closed(put(bars_day("2023-03-01"), "10:00", 99.75, 101.75, 99.75, 100.75, 300, 50))
    (ev,) = detect(b, refs_like(b), None, "I")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-01", "10:00"), 1, 99.5)

    s = closed(put(bars_day("2023-03-02"), "10:00", 101.0, 101.0, 98.75, 99.25, 300, -50))
    (ev,) = detect(s, refs_like(s), None, "I")
    assert (ev["minute"], ev["side"], ev["stop"]) == (ts("2023-03-02", "10:00"), -1, 101.25)

    thin = closed(put(bars_day("2023-03-03"), "10:00", 99.75, 101.75, 99.75, 100.75, 250, 50))
    assert detect(thin, refs_like(thin), None, "I") == []      # 250 < 3·medV


def test_fifteen_minute_gap_and_three_events_per_session():
    b = bars_day("2023-03-01")
    for hhmm in ("10:00", "10:10", "10:20"):
        put(b, hhmm, 100.0, 100.5, 99.5, 100.25, 250, -40)
    b = closed(b)
    assert [e["minute"].strftime("%H:%M") for e in detect(b, refs_like(b), None, "A")] == ["10:00", "10:20"]

    c = bars_day("2023-03-02")
    for hhmm in ("10:00", "10:15", "10:30", "10:45"):
        put(c, hhmm, 100.0, 100.5, 99.5, 100.25, 250, -40)
    c = closed(c)
    assert [e["minute"].strftime("%H:%M") for e in detect(c, refs_like(c), None, "A")] == \
        ["10:00", "10:15", "10:30"]


def test_signal_window_is_0945_to_1530():
    b = bars_day("2023-03-01")
    put(b, "09:44", 100.0, 100.5, 99.5, 100.25, 250, -40)
    put(b, "15:31", 100.0, 100.5, 99.5, 100.25, 250, -40)
    b = closed(b)
    assert detect(b, refs_like(b), None, "A") == []


def test_oos2_rows_are_discarded_before_any_calculation():
    oos = closed(put(bars_day("2024-01-02"), "10:00", 100.0, 100.5, 99.5, 100.25, 250, -40))
    assert detect(oos, refs_like(oos), None, "A") == []
    kept = closed(put(bars_day("2023-12-29"), "10:00", 100.0, 100.5, 99.5, 100.25, 250, -40))
    both = pd.concat([kept, oos])
    c = count_events(both, refs_like(both))
    assert c.index.get_level_values("year").max() == 2023


def test_med_l_uses_only_the_previous_twenty_sessions():
    fp = pd.concat([footprint(d, "10:30", [(400, 5, 5)]) for d in HIST]
                   + [footprint(DAY, "10:30", [(400, 90, 90)])])
    m = med_l(fp)
    assert pd.Timestamp(HIST[19]).date() not in m.index          # 19 sesiones: todavía sin medL
    assert m.loc[pd.Timestamp(DAY).date()] == 10.0               # 20 previas de 10; la de 90 es futuro


def test_count_events_columns_and_cost_filter():
    cheap = closed(put(bars_day("2023-03-01"), "10:00", 100.0, 100.5, 99.9, 100.1, 250, -40))
    wide = closed(put(bars_day("2023-03-02"), "10:00", 100.0, 100.5, 95.0, 100.1, 250, -40))
    b = pd.concat([cheap, wide])
    c = count_events(b, refs_like(b))
    assert COST_STOP_POINTS == 4.2
    assert set(c.columns) == {"events", "cost_filter", "tradable"}
    assert list(c.index.names) == ["hypothesis", "year"]
    assert int(c.loc[("A", 2023), "events"]) == 2
    assert int(c.loc[("A", 2023), "cost_filter"]) == 1
    assert int(c.loc[("A", 2023), "tradable"]) == 1
    assert not {"r", "r_net", "pnl", "outcome", "exit", "target"} & {col.lower() for col in c.columns}


def test_count_events_skips_d_without_footprints():
    b = closed(put(bars_day(DAY), "10:30", 100.0, 100.25, 99.75, 100.25, 100, 0))
    assert "D" not in count_events(b, refs_like(b)).index.get_level_values("hypothesis")
