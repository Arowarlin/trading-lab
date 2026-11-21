from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import indicators_ext as ext
from tradinglab.discovery.blocks import BLOCKS
from tradinglab.discovery.compiler import compile

CONTEXT = {
    "tz": "America/New_York",
    "start": "09:35",
    "end": "16:00",
    "or_minutes": 15,
}


def _frame(periods: int = 1200) -> pd.DataFrame:
    index = pd.date_range("2026-11-09 00:00", periods=periods, freq="5min", tz="UTC")
    rng = np.random.default_rng(11)
    close = 100 + np.cumsum(rng.normal(0, 0.2, len(index)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0, 0.2, len(index))
    low = np.minimum(open_, close) - rng.uniform(0, 0.2, len(index))
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tickvol": rng.uniform(100.0, 1000.0, len(index)),
        },
        index=index,
    )


def _alter_future(frame: pd.DataFrame, cutoff: int, seed: int) -> pd.DataFrame:
    altered = frame.copy()
    future = altered.index > altered.index[cutoff]
    count = int(future.sum())
    rng = np.random.default_rng(seed)
    last = float(altered["close"].iloc[cutoff])
    close = last + rng.normal(0, 1.0, count)
    open_ = np.r_[last, close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.0, 0.5, count)
    low = np.minimum(open_, close) - rng.uniform(0.0, 0.5, count)
    altered.loc[future, "open"] = open_
    altered.loc[future, "high"] = high
    altered.loc[future, "low"] = low
    altered.loc[future, "close"] = close
    altered.loc[future, "tickvol"] = rng.uniform(100.0, 1000.0, count)
    return altered


@pytest.mark.parametrize("name", sorted(BLOCKS))
def test_bloque_sin_lookahead(name: str) -> None:
    spec = BLOCKS[name]
    params = {key: param.default for key, param in spec.params.items()}
    frame = _frame()
    cutoff = 800
    left = spec.compute(frame, params, CONTEXT)
    altered = _alter_future(frame, cutoff, seed=1000 + len(name))
    right = spec.compute(altered, params, CONTEXT)
    pd.testing.assert_series_equal(
        left.iloc[: cutoff + 1],
        right.iloc[: cutoff + 1],
        check_exact=True,
        check_names=False,
    )


def test_session_return_nan_hasta_cerrar_end() -> None:
    index = pd.date_range(
        "2024-01-02 09:30", periods=78, freq="5min", tz="America/New_York"
    ).tz_convert("UTC")
    close = np.full(len(index), 100.0)
    close[6] = 101.0
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
        },
        index=index,
    )
    values = BLOCKS["session_return"].compute(
        frame, {"start": 570, "end": 600}, CONTEXT
    )

    assert np.isnan(values.iloc[5])  # 09:55
    assert np.isnan(values.iloc[6])  # 10:00: la vela aún no ha cerrado
    assert values.iloc[7] == pytest.approx(0.01)  # 10:05, ya cerrada
    assert values.iloc[7:].nunique(dropna=False) == 1


def test_vwap_sin_lookahead() -> None:
    frame = _frame()
    cutoff = 800
    left = ext.vwap_session(frame, tz=CONTEXT["tz"], start=CONTEXT["start"], end=CONTEXT["end"])
    right = ext.vwap_session(
        _alter_future(frame, cutoff, seed=7),
        tz=CONTEXT["tz"],
        start=CONTEXT["start"],
        end=CONTEXT["end"],
    )
    pd.testing.assert_series_equal(left.iloc[: cutoff + 1], right.iloc[: cutoff + 1], check_exact=True)


def test_niveles_de_sesion_sin_lookahead() -> None:
    frame = _frame()
    cutoff = 800
    altered = _alter_future(frame, cutoff, seed=8)
    for indicator in (
        lambda data: ext.prev_session_level(
            data, tz=CONTEXT["tz"], start=CONTEXT["start"], end=CONTEXT["end"], which="high"
        ),
        lambda data: ext.opening_range(
            data,
            tz=CONTEXT["tz"],
            start=CONTEXT["start"],
            end=CONTEXT["end"],
            minutes=CONTEXT["or_minutes"],
            which="high",
        ),
        lambda data: ext.prev_day_level(data, tz=CONTEXT["tz"], which="high"),
    ):
        left = indicator(frame)
        right = indicator(altered)
        pd.testing.assert_series_equal(
            left.iloc[: cutoff + 1],
            right.iloc[: cutoff + 1],
            check_exact=True,
        )


def _session_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-11-09 18:00",
            "2026-11-09 18:05",
            "2026-11-09 18:10",
            "2026-11-09 18:20",
            "2026-11-10 01:00",
            "2026-11-10 01:05",
            "2026-11-10 12:00",
            "2026-11-10 18:00",
            "2026-11-10 18:05",
            "2026-11-10 18:10",
            "2026-11-10 18:20",
            "2026-11-11 01:00",
        ],
        tz="America/New_York",
    )
    high = [105, 106, 108, 120, 130, 135, 999, 205, 206, 208, 220, 230]
    low = [95, 96, 92, 90, 100, 105, 998, 195, 196, 192, 190, 200]
    close = [100, 100, 100, 100, 200, 200, 999, 300, 300, 300, 300, 400]
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "tickvol": 1.0,
        },
        index=index,
    )


def _vwap_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-11-09 18:00",
            "2026-11-09 18:05",
            "2026-11-10 01:00",
            "2026-11-10 01:05",
            "2026-11-10 12:00",
            "2026-11-10 18:00",
            "2026-11-10 18:05",
            "2026-11-11 01:00",
        ],
        tz="America/New_York",
    )
    close = [100.0, 100.0, 200.0, 200.0, 999.0, 300.0, 300.0, 400.0]
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "tickvol": 1.0,
        },
        index=index,
    )


def test_vwap_y_niveles_cruzan_medianoche() -> None:
    vwap = ext.vwap_session(_vwap_frame(), tz="America/New_York", start="18:00", end="03:00")
    assert vwap.loc["2026-11-10 01:00"] == pytest.approx((100 + 100 + 200) / 3)
    assert vwap.loc["2026-11-10 01:05"] == pytest.approx((100 + 100 + 200 + 200) / 4)
    assert vwap.loc["2026-11-10 18:00"] == pytest.approx(300)
    assert vwap.loc["2026-11-11 01:00"] == pytest.approx((300 + 300 + 400) / 3)
    assert np.isnan(vwap.loc["2026-11-10 12:00"])

    frame = _session_frame()
    previous_high = ext.prev_session_level(
        frame, tz="America/New_York", start="18:00", end="03:00", which="high"
    )
    previous_low = ext.prev_session_level(
        frame, tz="America/New_York", start="18:00", end="03:00", which="low"
    )
    assert previous_high.loc["2026-11-10 18:05"] == pytest.approx(135)
    assert previous_high.loc["2026-11-11 01:00"] == pytest.approx(135)
    assert previous_low.loc["2026-11-10 18:05"] == pytest.approx(90)
    assert np.isnan(previous_high.loc["2026-11-09 18:05"])

    opening_high = ext.opening_range(
        frame,
        tz="America/New_York",
        start="18:00",
        end="03:00",
        minutes=15,
        which="high",
    )
    opening_low = ext.opening_range(
        frame,
        tz="America/New_York",
        start="18:00",
        end="03:00",
        minutes=15,
        which="low",
    )
    assert np.isnan(opening_high.loc["2026-11-09 18:10"])
    assert opening_high.loc["2026-11-09 18:20"] == pytest.approx(108)
    assert opening_high.loc["2026-11-10 01:00"] == pytest.approx(108)
    assert opening_low.loc["2026-11-10 01:00"] == pytest.approx(92)
    assert opening_high.loc["2026-11-10 18:20"] == pytest.approx(208)
    assert opening_high.loc["2026-11-11 01:00"] == pytest.approx(208)


def _htf_frame() -> pd.DataFrame:
    index = pd.date_range("2026-11-16 09:00", "2026-11-16 11:05", freq="5min", tz="UTC")
    close = np.where(index < pd.Timestamp("2026-11-16 10:00", tz="UTC"), 50.0, 150.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "tickvol": 1.0,
        },
        index=index,
    )


def test_htf_usa_la_vela_cerrada() -> None:
    strategy = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "04:00", "end": "08:00", "flat_at": "09:00", "or_minutes": 15},
        "long_entry": {
            "kind": "htf",
            "tf": "H1",
            "expr": {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 100},
            },
        },
        "short_entry": None,
        "exit": {"stop": {"type": "atr", "mult": 1.5, "n": 14}, "target": {"type": "rr", "rr": 2.0}},
    }
    frame = _htf_frame()
    signals = compile(strategy, frame)
    positions = {stamp: index for index, stamp in enumerate(frame.index)}
    assert signals.long_entry[positions[pd.Timestamp("2026-11-16 09:55", tz="UTC")]] is np.False_
    assert signals.long_entry[positions[pd.Timestamp("2026-11-16 10:00", tz="UTC")]] is np.False_
    assert signals.long_entry[positions[pd.Timestamp("2026-11-16 10:05", tz="UTC")]] is np.False_
    assert signals.long_entry[positions[pd.Timestamp("2026-11-16 11:00", tz="UTC")]] is np.True_
    assert signals.long_entry[positions[pd.Timestamp("2026-11-16 11:05", tz="UTC")]] is np.True_
