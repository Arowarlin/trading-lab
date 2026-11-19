from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab import ea_us100_engine as old_engine
from tradinglab.config import ROOT
from tradinglab.ea_lab import session_engine
from tradinglab.ea_lab.sessions import (
    ASIA_ANCHORS,
    CANDIDATES,
    EA_CACHE,
    LONDON_ANCHORS,
    NYSE_ANCHORS,
    anchors_for,
    pre_registration_hash,
)


def _synthetic(days: int = 40, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows, index = [], []
    price = 20000.0
    for day in range(days):
        start = pd.Timestamp("2026-08-03") + pd.Timedelta(days=day)
        for step in range(288):
            change = float(rng.normal(0, 8))
            open_ = price
            close = price + change
            high = max(open_, close) + abs(float(rng.normal(0, 3)))
            low = min(open_, close) - abs(float(rng.normal(0, 3)))
            rows.append(
                {
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "tickvol": float(rng.integers(1000, 9000)),
                    "spread": 80.0,
                }
            )
            index.append(start + pd.Timedelta(minutes=5 * step))
            price = close
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))


def _params() -> dict:
    params = dict(old_engine.DEF)
    params["ny_offset_h"] = 0
    return params


def _assert_same(left: pd.DataFrame, right: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(
        left.reset_index(drop=True), right.reset_index(drop=True), check_dtype=True
    )


def test_equivalencia_ny_sintetica():
    frame = _synthetic()
    params = _params()
    expected = old_engine.run(frame, params)
    actual = session_engine.run(frame, params, session=NYSE_ANCHORS)
    assert len(actual) == len(expected) > 0
    _assert_same(expected, actual)


def test_equivalencia_ny_real():
    if not EA_CACHE.exists():
        pytest.skip("sin caché local del US100")
    frame = pd.read_parquet(EA_CACHE)
    frame.index = pd.DatetimeIndex(frame.index)
    params = _params()
    expected = old_engine.run(frame, params)
    actual = session_engine.run(frame, params, session=NYSE_ANCHORS)
    assert len(actual) == len(expected) > 0
    _assert_same(expected, actual)


def test_anchores_pre_registrados():
    assert anchors_for("us100-london") == LONDON_ANCHORS
    assert anchors_for("us100-asia") == ASIA_ANCHORS
    assert LONDON_ANCHORS["trade_start"] == "08:05"
    assert LONDON_ANCHORS["flat_at"] == "14:15"
    assert ASIA_ANCHORS["trade_start"] == "09:05"
    assert ASIA_ANCHORS["flat_at"] == "15:15"


def test_sesion_nocturna_asia_cruza_medianoche():
    # 16:00 Nueva York → 09:00 Tokio del día siguiente (horario de invierno).
    stamps = pd.DatetimeIndex(
        [
            "2026-11-19T20:00:00Z",  # 15:00 NY, antes del cierre
            "2026-11-19T21:00:00Z",  # 16:00 NY = 06:00 Tokio
            "2026-11-19T23:59:00Z",  # 18:59 NY = 08:59 Tokio
            "2026-11-20T00:00:00Z",  # 19:00 NY = 09:00 Tokio (fin exclusivo)
            "2026-11-20T01:00:00Z",  # 20:00 NY = 10:00 Tokio
        ]
    )
    mask = session_engine._on_mask(
        stamps,
        np.zeros(len(stamps), dtype=np.int32),
        tz="Asia/Tokyo",
        on_start_tz="America/New_York",
        on_start_min=16 * 60,
        on_end_tz="Asia/Tokyo",
        on_end_min=9 * 60,
    )
    assert list(mask) == [False, True, True, False, False]


def test_sesion_nocturna_londres_mismo_huso():
    stamps = pd.DatetimeIndex(
        ["2026-11-19T00:30:00Z", "2026-11-19T06:59:00Z", "2026-11-19T07:00:00Z"]
    )
    mask = session_engine._on_mask(
        stamps,
        np.zeros(len(stamps), dtype=np.int32),
        tz="Europe/London",
        on_start_tz="Europe/London",
        on_start_min=0,
        on_end_tz="Europe/London",
        on_end_min=7 * 60,
    )
    assert list(mask) == [True, True, False]


def test_documentos_incluyen_el_hash():
    for candidate in ("us100-london", "us100-asia"):
        doc = (ROOT / CANDIDATES[candidate]["doc"]).read_text(encoding="utf-8")
        assert pre_registration_hash(candidate) in doc
