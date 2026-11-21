"""Sesiones que cruzan medianoche: niveles, flat y preflight de Asia."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from tradinglab.discovery import campaigns, engine
from tradinglab.discovery import indicators_ext as ext

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}


def _asia_frame() -> pd.DataFrame:
    index = pd.date_range(
        "2024-01-10 23:00", "2024-01-12 08:00", freq="5min", tz="UTC"
    )
    first = index < pd.Timestamp("2024-01-11 08:00", tz="UTC")
    high = np.where(first, 110.0, 210.0)
    low = np.where(first, 90.0, 190.0)
    return pd.DataFrame(
        {
            "open": (high + low) / 2.0,
            "high": high,
            "low": low,
            "close": (high + low) / 2.0,
        },
        index=index,
    )


def test_niveles_de_sesion_cruzan_medianoche() -> None:
    frame = _asia_frame()
    high = ext.prev_session_level(
        frame,
        tz="America/New_York",
        start="18:00",
        end="03:00",
        which="high",
    )
    low = ext.prev_session_level(
        frame,
        tz="America/New_York",
        start="18:00",
        end="03:00",
        which="low",
    )
    opening_high = ext.opening_range(
        frame,
        tz="America/New_York",
        start="18:00",
        end="03:00",
        minutes=15,
        which="high",
    )
    evening = pd.Timestamp("2024-01-11 23:30", tz="UTC")  # 18:30 NY
    after_midnight = pd.Timestamp("2024-01-12 06:00", tz="UTC")  # 01:00 NY

    assert high.loc[evening] == 110.0
    assert low.loc[evening] == 90.0
    assert high.loc[after_midnight] == 110.0
    assert low.loc[after_midnight] == 90.0
    assert opening_high.loc[evening] == 210.0
    assert opening_high.loc[after_midnight] == 210.0


def test_asia_range_reversion_pasa_preflight(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        campaigns,
        "_quality",
        lambda *_args, **_kwargs: (
            SimpleNamespace(
                status="ok",
                issues=[],
                granularity={"useful_start": "2023-01-01"},
                segments={},
            ),
            "2023-01-01",
        ),
    )
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=20261124)
    campaigns.register_synthetic(
        frame,
        instrument="US100",
        template="asia_range_reversion",
        profile="small",
        segments=SEGMENTS,
        seed=20261124,
        campaign_id="asia-preflight",
        db_path=db,
    )
    report = engine.preflight("asia-preflight", db_path=db)

    assert report["generated"] == report["population"] == 40
    assert report["valid"] == 40
    assert report["rejected"] == 0
