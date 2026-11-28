"""FUT-C3: evaluador de Research A con cotizaciones y trades sintéticos (cifras exactas)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from tradinglab.futures.research_a_eval import cr1_t, evaluate, simulate, verdict

NY = "America/New_York"


def quotes_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """``rows``: (hora NY, bid, ask, bid_size, ask_size)."""
    ts = pd.to_datetime([r[0] for r in rows]).tz_localize(NY).tz_convert("UTC")
    return pd.DataFrame({"ts_event": ts, "bid": [r[1] for r in rows], "ask": [r[2] for r in rows],
                         "bid_size": [r[3] for r in rows], "ask_size": [r[4] for r in rows]})


def trades_frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """``rows``: (hora NY, precio, tamaño)."""
    ts = pd.to_datetime([r[0] for r in rows]).tz_localize(NY).tz_convert("UTC")
    return pd.DataFrame({"ts_event": ts, "price": [r[1] for r in rows], "size": [r[2] for r in rows]})


def event(*, d: str = "2023-03-01", hhmm: str = "10:00", side: int = 1, stop: float = 99.0) -> dict:
    return {"minute": pd.Timestamp(f"{d} {hhmm}", tz=NY), "side": side, "stop": stop}


def bars_day(d: str, base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(f"{d} 09:30", f"{d} 15:59", freq="min", tz=NY)
    return pd.DataFrame({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base,
                         "volume": 100.0, "delta": 0.0}, index=idx)


def a_signal_day(d: str) -> pd.DataFrame:
    b = bars_day(d)
    b.loc[pd.Timestamp(f"{d} 10:00", tz=NY), ["open", "high", "low", "close", "volume", "delta"]] = \
        [100.0, 100.5, 95.0, 100.25, 250, -40]
    b["cvd"] = b["delta"].cumsum()
    return b


def refs_like(bars: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"medV": 100.0, "medRng": 1.0, "s_delta": 10.0}, index=bars.index)


def test_entry_fills_at_the_ask_after_latency():
    q = quotes_frame([("2023-03-01 10:01:00.400", 99.75, 100.0, 5, 5),
                      ("2023-03-01 10:01:00.500", 99.75, 100.25, 5, 5),
                      ("2023-03-01 10:16:00.500", 100.0, 100.25, 5, 5)])
    t = trades_frame([("2023-03-01 10:10:00", 100.0, 1)])
    res = simulate(event(stop=99.0), q, t)
    assert res["entry"] == 100.25
    assert res["entry_time"] == pd.Timestamp("2023-03-01 10:01:00.500", tz=NY)
    assert (res["exit_kind"], res["exit"]) == ("time", 100.0)
    assert res["hold_s"] == 900.0
    assert simulate(event(), quotes_frame([("2023-03-01 10:00:00", 99.75, 100.0, 5, 5)]), t) is None


def test_stop_triggers_on_a_trade_and_fills_at_the_bid():
    q = quotes_frame([("2023-03-01 10:01:00.500", 99.75, 100.0, 5, 5),
                      ("2023-03-01 10:03:00.200", 99.9, 100.15, 5, 5),
                      ("2023-03-01 10:03:00.500", 98.5, 98.75, 5, 5),
                      ("2023-03-01 10:16:00.500", 100.0, 100.25, 5, 5)])
    t = trades_frame([("2023-03-01 10:03:00.000", 98.75, 1)])
    res = simulate(event(stop=99.0), q, t)
    assert (res["exit_kind"], res["exit"]) == ("stop", 98.5)      # la cotización previa a t+L se ignora
    assert res["r_net"] == pytest.approx(((98.5 - 100.0) * 2 - 1.5) / (1.0 * 2))


def test_target_needs_a_one_tick_crossing():
    q = quotes_frame([("2023-03-01 10:01:00.500", 99.75, 100.0, 5, 5),
                      ("2023-03-01 10:16:00.500", 100.5, 100.75, 5, 5)])
    touched = simulate(event(stop=99.0), q, trades_frame([("2023-03-01 10:05:00", 101.5, 1)]))
    assert (touched["exit_kind"], touched["exit"]) == ("time", 100.5)     # objetivo 101,5 sin atravesar
    crossed = simulate(event(stop=99.0), q, trades_frame([("2023-03-01 10:05:00", 101.75, 1)]))
    assert (crossed["exit_kind"], crossed["exit"]) == ("target", 101.5)
    assert crossed["r_net"] == pytest.approx(((101.5 - 100.0) * 2 - 1.5) / (1.0 * 2))


def test_stop_wins_in_the_same_second():
    q = quotes_frame([("2023-03-01 10:01:00.500", 99.75, 100.0, 5, 5),
                      ("2023-03-01 10:05:01.300", 98.5, 98.75, 5, 5)])
    t = trades_frame([("2023-03-01 10:05:00.200", 101.75, 1), ("2023-03-01 10:05:00.800", 98.75, 1)])
    res = simulate(event(stop=99.0), q, t)
    assert (res["exit_kind"], res["exit"]) == ("stop", 98.5)


def test_short_entry_at_the_bid_and_stop_at_the_ask():
    q = quotes_frame([("2023-03-01 10:01:00.500", 99.75, 100.0, 5, 5),
                      ("2023-03-01 10:04:00.500", 100.9, 101.25, 5, 5)])
    t = trades_frame([("2023-03-01 10:04:00.000", 100.5, 1)])
    res = simulate(event(side=-1, stop=100.5), q, t)
    assert res["entry"] == 99.75
    assert (res["exit_kind"], res["exit"]) == ("stop", 101.25)
    assert res["r_net"] == pytest.approx((-1 * (101.25 - 99.75) * 2 - 1.5) / (0.75 * 2))


def test_entry_goes_one_tick_worse_without_size_at_the_best_level():
    q = quotes_frame([("2023-03-01 10:01:00.500", 99.75, 100.0, 5, 0),
                      ("2023-03-01 10:16:00.500", 100.0, 100.25, 5, 5)])
    t = trades_frame([("2023-03-01 10:10:00", 100.0, 1)])
    assert simulate(event(stop=99.0), q, t)["entry"] == 100.25


def test_cr1_t_of_a_known_series():
    x = np.array([2.0, 2.0, 0.0, 0.0])
    sessions = np.array(["2023-01-03", "2023-01-03", "2023-01-04", "2023-01-04"])
    assert cr1_t(x, sessions) == pytest.approx(1.0)
    assert np.isnan(cr1_t(np.array([1.0]), np.array(["2023-01-03"])))
    assert cr1_t(np.array([1.0, 1.0]), np.array(["a", "b"])) == float("inf")


def test_verdict_follows_the_section_7_order():
    kw = dict(n=10, mean_r=0.05, t_cr1=3.0, t_crit=2.394, mean_r_1tick=0.01, mean_r_latency=0.01,
              mean_first=0.05, mean_second=0.05)
    assert verdict(**kw) == "candidata, no monetizable todavía en prop"
    assert verdict(**{**kw, "mean_r": 0.10}) == "candidata"
    assert verdict(**{**kw, "t_cr1": 1.0}) == "rechazada"
    assert verdict(**{**kw, "mean_r_1tick": -0.01}) == "rechazada por costes"
    assert verdict(**{**kw, "mean_r_latency": -0.01}) == "rechazada por latencia"
    assert verdict(**{**kw, "mean_second": -0.05}) == "inconclusa"
    assert verdict(**{**kw, "n": 1, "t_cr1": float("nan")}) == "Sin datos"


def test_evaluate_uses_detect_and_reports_the_criteria():
    days = ["2023-03-01", "2023-03-02"]
    bars = pd.concat([a_signal_day(d) for d in days])
    quotes = quotes_frame([(f"{d} {hhmm}", bid, ask, 5, 5) for d in days
                           for hhmm, bid, ask in (("10:01:00.500", 99.75, 100.0),
                                                  ("10:01:01.000", 99.75, 100.0),
                                                  ("10:16:00.500", 100.0, 100.25))])
    trades = trades_frame([(f"{d} 10:05:00", 108.5, 1) for d in days])
    res = evaluate(bars, refs_like(bars), None, "A", quotes, trades, t_crit=2.394, split=date(2023, 3, 2))
    assert res["n"] == 2 and res["dropped"] == 0
    assert res["mean_r"] == pytest.approx(((107.875 - 100.0) * 2 - 1.5) / (5.25 * 2))
    assert res["t_cr1"] == float("inf") and res["median_hold_s"] == 239.5
    assert res["median_hold_s"] >= 30.0 and "hold_note" not in res
    assert res["verdict"] == "candidata"
