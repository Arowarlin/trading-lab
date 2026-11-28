"""FUT-C1: rasgos de order flow con datos sintéticos y cifras exactas (RA_spec §3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.futures.orderflow import (
    diagonal_buy_imbalances,
    footprint,
    minute_bars,
    rolling_refs,
    seal,
    signed,
    stacked,
)


def trades(rows):
    """rows: (hora NY 'YYYY-MM-DD HH:MM:SS', precio, tamaño, lado)."""
    ts = pd.to_datetime([r[0] for r in rows]).tz_localize("America/New_York").tz_convert("UTC")
    return pd.DataFrame({"ts_event": ts, "price": [r[1] for r in rows], "size": [r[2] for r in rows],
                         "side": [r[3] for r in rows]})


T = trades([
    ("2023-03-01 09:29:30", 100.00, 9, "B"),      # pre-apertura: fuera de RTH
    ("2023-03-01 09:30:05", 100.00, 5, "B"),
    ("2023-03-01 09:30:20", 100.25, 3, "A"),
    ("2023-03-01 09:30:40", 100.25, 2, "N"),      # sin lado: se excluye
    ("2023-03-01 09:31:10", 100.50, 4, "B"),
    ("2023-03-02 09:30:00", 101.00, 6, "A"),      # sesión nueva: el CVD se reinicia
    ("2024-01-02 09:30:00", 999.00, 99, "B"),     # OOS-2 sellado
])


def test_seal_drops_oos2_before_anything():
    kept, dropped = seal(T)
    assert dropped == 1 and kept["price"].max() < 999


def test_signed_counts_side_n():
    _, excluded = signed(seal(T)[0])
    assert excluded == 1


def test_minute_bars_delta_and_cvd_reset():
    b = minute_bars(T)
    assert b["delta"].tolist() == [2.0, 4.0, -6.0]          # 5 − 3; 4; −6
    assert b["cvd"].tolist() == [2.0, 6.0, -6.0]            # se reinicia el 2 de marzo
    assert b["volume"].tolist() == [8, 4, 6]
    first = b.iloc[0]
    assert (first["open"], first["high"], first["low"], first["close"]) == (100.0, 100.25, 100.0, 100.25)


def test_footprint_and_stacked_imbalance():
    rows = [("2023-03-01 10:00:00", 100.00, 1, "A"), ("2023-03-01 10:00:01", 100.25, 6, "B"),
            ("2023-03-01 10:00:02", 100.25, 1, "A"), ("2023-03-01 10:00:03", 100.50, 9, "B"),
            ("2023-03-01 10:00:04", 100.75, 12, "B"), ("2023-03-01 10:00:05", 100.50, 2, "A")]
    fp = footprint(trades(rows), 0.25)
    minute = fp.xs(fp.index.get_level_values(0)[0], level=0)
    assert minute.loc[402].tolist() == [9, 2]               # nivel 100,50 = 402 ticks: B 9, S 2
    lv = diagonal_buy_imbalances(minute, ratio=3.0)
    assert lv == [401, 402, 403]                            # 6 ≥ 3·1; 9 ≥ 3·1; 12 ≥ 3·2
    assert stacked(lv, 3) and not stacked([401, 403], 2)


def test_rolling_refs_use_only_the_past():
    idx = pd.date_range("2023-01-02 09:30", periods=30, freq="B").tz_localize("America/New_York")
    rng = np.random.default_rng(0)
    bars = pd.DataFrame({"volume": rng.integers(1, 100, 30).astype(float), "delta": rng.normal(0, 10, 30),
                         "high": 101.0, "low": 100.0}, index=idx)
    ref = rolling_refs(bars, sessions=20)
    assert ref["medV"].iloc[:20].isna().all()
    assert ref["medV"].iloc[20] == pytest.approx(np.median(bars["volume"].iloc[:20]))
    w = bars["delta"].iloc[:20].to_numpy()
    assert ref["s_delta"].iloc[20] == pytest.approx(1.4826 * np.median(np.abs(w - np.median(w))))
    future = bars.copy()
    future.loc[future.index[25:], "volume"] = 10_000.0      # cambiar el futuro no cambia el pasado
    assert rolling_refs(future, sessions=20)["medV"].iloc[:26].equals(ref["medV"].iloc[:26])
