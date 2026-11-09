from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

import tradinglab.execution.mt5 as mt5_module
from tradinglab.execution.mt5 import copy_ticks

DTYPE = [("time", "i8"), ("bid", "f8"), ("ask", "f8")]


class FakeMT5:
    COPY_TICKS_ALL = 2

    def __init__(self, raw):
        self.raw = raw
        self.calls: list[tuple] = []

    def copy_ticks_range(self, symbol, desde, hasta, flags):
        self.calls.append((symbol, desde, hasta, flags))
        return self.raw


def _raw(stamps: list[str]) -> np.ndarray:
    return np.array(
        [
            (int(pd.Timestamp(stamp, tz="UTC").timestamp()), 1.1000, 1.1002)
            for stamp in stamps
        ],
        dtype=DTYPE,
    )


def test_copy_ticks_normal_y_orden(monkeypatch):
    fake = FakeMT5(_raw(["2026-11-09 10:00:00", "2026-11-09 09:00:00"]))
    monkeypatch.setattr(mt5_module, "_mt5", lambda: fake)
    desde = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)
    hasta = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)

    frame = copy_ticks("EURUSD", desde, hasta)

    assert list(frame.columns) == ["ts", "bid", "ask"]
    assert frame["ts"].dt.tz is not None
    assert str(frame["ts"].dt.tz) == "UTC"
    assert frame["ts"].is_monotonic_increasing
    assert frame["ts"].iloc[0] == pd.Timestamp("2026-11-09 09:00", tz="UTC")
    assert frame["ts"].iloc[1] == pd.Timestamp("2026-11-09 10:00", tz="UTC")
    assert frame["bid"].tolist() == [1.1, 1.1]
    assert frame["ask"].tolist() == [1.1002, 1.1002]
    assert fake.calls == [("EURUSD", desde, hasta, FakeMT5.COPY_TICKS_ALL)]


def test_copy_ticks_vacio(monkeypatch):
    fake = FakeMT5(np.array([], dtype=DTYPE))
    monkeypatch.setattr(mt5_module, "_mt5", lambda: fake)

    frame = copy_ticks(
        "EURUSD",
        datetime(2026, 11, 9, tzinfo=timezone.utc),
        datetime(2026, 11, 10, tzinfo=timezone.utc),
    )

    assert frame.empty
    assert list(frame.columns) == ["ts", "bid", "ask"]


def test_copy_ticks_none(monkeypatch):
    fake = FakeMT5(None)
    monkeypatch.setattr(mt5_module, "_mt5", lambda: fake)

    frame = copy_ticks(
        "EURUSD",
        datetime(2026, 11, 9, tzinfo=timezone.utc),
        datetime(2026, 11, 10, tzinfo=timezone.utc),
    )

    assert frame.empty
    assert list(frame.columns) == ["ts", "bid", "ask"]
