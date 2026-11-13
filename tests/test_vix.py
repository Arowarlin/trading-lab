from __future__ import annotations

import pandas as pd

from tradinglab.data.vix import compute_structure, latest_structure, save_cached


def test_ratio_vix_y_flag():
    index = pd.to_datetime(["2026-11-10", "2026-11-11"], utc=True)
    frame = compute_structure(
        pd.Series([20.0, 30.0], index=index),
        pd.Series([25.0, 25.0], index=index),
    )
    assert frame.iloc[0]["ratio"] == 0.8
    assert frame.iloc[0]["structure"] == "contango"
    assert bool(frame.iloc[0]["vix_backwardation"]) is False
    assert frame.iloc[1]["ratio"] == 1.2
    assert frame.iloc[1]["structure"] == "backwardation"
    assert bool(frame.iloc[1]["vix_backwardation"]) is True


def test_latest_structure_respeta_fecha(tmp_path):
    path = tmp_path / "vix.json"
    save_cached([
        {"date": "2026-11-10", "vix": 20, "vix3m": 25, "ratio": 0.8,
         "structure": "contango", "vix_backwardation": False},
        {"date": "2026-11-12", "vix": 30, "vix3m": 25, "ratio": 1.2,
         "structure": "backwardation", "vix_backwardation": True},
    ], path)
    result = latest_structure(pd.Timestamp("2026-11-11", tz="UTC"), path)
    assert result["latest"]["date"] == "2026-11-10"
