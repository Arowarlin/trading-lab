"""TL3-C · C3: tests sintéticos de las correcciones de T8."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tl3_t8_fomc", ROOT / "scripts" / "tl3_t8_fomc.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _profile(value: float = 90.0) -> pd.DataFrame:
    return pd.DataFrame({"slot": range(288), "spread": [value] * 288})


def test_swap_bps_es_interes_anual():
    assert MODULE.SWAP_BPS == 7.33 / 100 / 365 * 1e4
    assert MODULE.SWAP_BPS < 3.0


def test_componentes_incluyen_100_puntos_de_slippage():
    frame = pd.DataFrame(
        {"entry": [100.0, 101.0], "late": [np.nan, 102.0], "early": [np.nan, np.nan]},
        index=[pd.Timestamp("2026-01-15").date(), pd.Timestamp("2026-01-16").date()],
    )
    row = MODULE._components(
        frame,
        _profile(),
        0.01,
        pd.Timestamp("2026-01-15").date(),
        pd.Timestamp("2026-01-16").date(),
        True,
    )
    assert row is not None
    expected_gross = math.log(102 / 100) * 1e4
    expected_slippage = 100.0 * 0.01 / 100.0 * 1e4
    assert row["gross"] == expected_gross
    assert row["slippage"] == expected_slippage
    assert row["spread"] == 180.0 * 0.01 / 100.0 * 1e4


def test_clock_map_toma_la_barra_mas_cercana_y_empate_anterior():
    index = pd.to_datetime(
        ["2026-01-15 15:53", "2026-01-15 15:55", "2026-01-15 15:57"]
    )
    frame = pd.DataFrame({"open": [1.0, 2.0, 3.0]}, index=index)
    nearest = MODULE._clock_map(frame, MODULE.time(15, 55), "open")
    assert nearest.iloc[0] == 2.0

    index2 = pd.to_datetime(["2026-01-15 15:53", "2026-01-15 15:55"])
    frame2 = pd.DataFrame({"open": [1.0, 2.0]}, index=index2)
    tie = MODULE._clock_map(frame2, MODULE.time(15, 54), "open")
    assert tie.iloc[0] == 1.0


def test_has_bars_detecta_faltantes():
    frame = pd.DataFrame(
        {"entry": [100.0], "late": [101.0]},
        index=[pd.Timestamp("2026-01-15").date()],
    )
    assert MODULE._has_bars(
        frame,
        pd.Timestamp("2026-01-15").date(),
        pd.Timestamp("2026-01-16").date(),
        True,
    ) is False
