"""Coste v2 y puertas del prerregistro EDGE1 H1 NY impulse."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.tl3.costs import cost_r_v2
from tradinglab.tl3.gates import cost_r_gate, min_trades_gate

ROOT = Path(__file__).resolve().parents[1]


def test_cost_r_v2_suma_spread_y_dos_lados():
    payload = cost_r_v2(
        100.0,
        2.0,
        spread_bps=2.0,
        slippage_bps=1.0,
        commission_bps=0.5,
    )
    assert payload["total_bps"] == pytest.approx(2.0 + 2 * 1.0 + 2 * 0.5)
    assert payload["cost_price"] == pytest.approx(5.0 / 10_000 * 100.0)
    assert payload["cost_r"] == pytest.approx(0.05 / 2.0)


def test_cost_r_v2_rechaza_datos_invalidos():
    with pytest.raises(ValueError, match="entry_price"):
        cost_r_v2(0.0, 1.0, spread_bps=0.0, slippage_bps=0.0, commission_bps=0.0)
    with pytest.raises(ValueError, match="stop_distance"):
        cost_r_v2(100.0, 0.0, spread_bps=0.0, slippage_bps=0.0, commission_bps=0.0)
    with pytest.raises(ValueError, match="spread_bps"):
        cost_r_v2(100.0, 1.0, spread_bps=-1.0, slippage_bps=0.0, commission_bps=0.0)


def test_puertas_de_potencia_y_coste():
    assert min_trades_gate(40)["ok"] is True
    assert min_trades_gate(39)["ok"] is False
    assert min_trades_gate(None)["ok"] is False
    assert cost_r_gate(0.10)["ok"] is True
    assert cost_r_gate(0.1001)["ok"] is False
    assert cost_r_gate(None)["ok"] is False


def test_senal_impulso_y_ruptura():
    spec = importlib.util.spec_from_file_location(
        "edge1_h1_ny_impulse", ROOT / "scripts" / "edge1_h1_ny_impulse.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    prior = pd.DataFrame(
        {
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
        }
    )
    long_signal = pd.Series(
        {"open": 102.0, "high": 105.0, "low": 102.0, "close": 104.0}
    )
    assert module._signal_side(long_signal, prior, 0.5) == "long"

    short_signal = pd.Series(
        {"open": 104.0, "high": 104.0, "low": 100.0, "close": 100.5}
    )
    short_prior = pd.DataFrame(
        {"high": [106.0, 105.0, 104.0], "low": [103.0, 102.0, 101.0]}
    )
    assert module._signal_side(short_signal, short_prior, 0.5) == "short"

    weak_body = pd.Series(
        {"open": 102.0, "high": 105.0, "low": 102.0, "close": 102.2}
    )
    assert module._signal_side(weak_body, prior, 0.5) is None
