from __future__ import annotations

import pytest

from tradinglab.metrics import (
    MIN_SAMPLE,
    metrics_warning,
    recovery_factor,
    risk_of_ruin,
    system_quality_number,
)


def test_sqn_formula() -> None:
    returns = [0.01, -0.01, 0.02, 0.0]
    # media=0.005; desv muestral≈0.0129099; sqrt(4)*0.005/desv
    assert system_quality_number(returns) == pytest.approx(0.7745966692, rel=1e-6)
    assert system_quality_number([0.01]) is None
    assert system_quality_number([0.0, 0.0]) is None


def test_recovery_factor() -> None:
    assert recovery_factor(1_000.0, -500.0) == pytest.approx(2.0)
    assert recovery_factor(1_000.0, 0.0) is None
    assert recovery_factor(1_000.0, None) is None


def test_riesgo_de_ruina_supuestos() -> None:
    value, assumptions = risk_of_ruin(0.55, 1.5)
    assert 0.0 < value < 1e-6
    assert "independientes" in assumptions
    assert risk_of_ruin(0.40, 1.0)[0] == pytest.approx(1.0)
    assert risk_of_ruin(None, 1.5)[0] is None
    assert risk_of_ruin(0.55, 0.0)[0] is None


def test_aviso_muestra() -> None:
    assert f"N={MIN_SAMPLE - 1}" in metrics_warning(MIN_SAMPLE - 1)
    assert metrics_warning(MIN_SAMPLE) is None
