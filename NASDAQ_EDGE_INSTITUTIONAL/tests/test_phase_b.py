"""Tests sintéticos de las herramientas de la Fase B (sin datos reales)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location(
    "phase_b", Path(__file__).resolve().parents[1] / "tools" / "phase_b.py"
)
pb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pb)


def test_wilson_known_values():
    w = pb.wilson(50, 100)
    assert w["p"] == 0.5
    assert 0.40 < w["lo"] < 0.41 and 0.59 < w["hi"] < 0.60
    assert pb.wilson(0, 0)["p"] is None


def test_roll_window_covers_roll_and_expiry():
    days = pb.roll_window_days(2015, 2015)
    assert "2015-03-20" in days  # 3er viernes de marzo 2015 (vencimiento)
    assert "2015-03-12" in days  # jueves de roll CME, 8 días antes
    assert "2015-04-15" not in days


def _session(day: str, closes: np.ndarray) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", periods=len(closes), freq="1min", tz=pb.NY)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.25,
            "low": closes - 0.25,
            "close": closes,
            "volume": 100.0,
            "spread": np.nan,
        },
        index=idx,
    )


def test_breakout_continuation_is_detected():
    # 20 sesiones planas para que exista ATR previo y una sesión con ruptura alcista.
    frames = []
    days = pd.bdate_range("2015-04-01", periods=21)
    for d in days[:-1]:
        frames.append(_session(str(d.date()), np.full(390, 100.0)))
    path = np.full(390, 100.0)
    path[:15] = np.linspace(99.0, 101.0, 15)  # OR15 ≈ 98.75 – 101.25
    path[15:60] = np.linspace(101.5, 110.0, 45)  # rompe y recorre > 1×OR
    path[60:] = 110.0
    frames.append(_session(str(days[-1].date()), path))
    df = pd.concat(frames)
    rows = pb.build(df, str(days[-1].date()), set())
    news = pd.DataFrame({"date": [], "event": [], "tier": [], "time_et": []})
    res = pb.stats("NQ", rows, news)
    last = res["breakouts"]["OR15"]["all"]["all"]
    assert last["breaks"] >= 1
    assert last["continuation"]["k"] >= 1
    assert last["false"]["k"] == 0
