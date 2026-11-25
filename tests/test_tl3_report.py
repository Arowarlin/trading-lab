"""T4 · Escalera bruto → neto."""

from __future__ import annotations

import pytest

from tradinglab.tl3.report import ladder


def test_escalera_con_costes_a_mano():
    rows = [
        {"gross": 1.0, "spread": 0.10, "commission": 0.05, "slippage": 0.02, "swap": 0.01},
        {"gross": 2.0, "spread": 0.10, "commission": 0.05, "slippage": 0.02, "swap": 0.01},
        {"gross": 3.0, "spread": 0.10, "commission": 0.05, "slippage": 0.02, "swap": 0.01},
        {"gross": 4.0, "spread": 0.10, "commission": 0.05, "slippage": 0.02, "swap": 0.01},
    ]

    result = ladder(rows, n_boot=500)

    assert result["steps"][0]["mean"] == pytest.approx(2.5)
    assert result["net"]["mean"] == pytest.approx(2.5 - 0.18)
    assert result["net"]["n"] == 4
    assert result["net"]["ci95"] is not None
