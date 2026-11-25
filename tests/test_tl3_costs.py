"""D1 · Swap, noches y codificación."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tradinglab.tl3.costs import nights, swap_bps_per_night

ROOT = Path(__file__).resolve().parents[1]


def test_swap_interes_anual():
    assert swap_bps_per_night(7.33, 5) == pytest.approx(2.008, abs=0.001)


def test_swap_puntos_a_mano():
    assert swap_bps_per_night(-100, 1, price=100.0, point=0.01) == pytest.approx(100.0)


def test_modo_desconocido():
    with pytest.raises(ValueError, match="swap_mode"):
        swap_bps_per_night(1.0, 9)


def test_noches_dia_triple():
    assert nights(5) == 3
    assert nights(2) == 1


def test_t8_usa_la_misma_constante():
    spec = importlib.util.spec_from_file_location(
        "tl3_t8_fomc", ROOT / "scripts" / "tl3_t8_fomc.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.SWAP_BPS == pytest.approx(swap_bps_per_night(7.33, 5))
