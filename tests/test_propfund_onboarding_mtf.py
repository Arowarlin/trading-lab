from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.propfund.costs import CostProfile
from tradinglab.propfund.models import Market
from tradinglab.propfund.onboarding_mtf import (
    assess_cost,
    commission_price,
    median_atr_from_frame,
    operation_cost,
)


def _profile(**kwargs) -> CostProfile:
    base = dict(
        account="CFD-001",
        symbol="EURUSD",
        market=Market.CFD,
        commission_type="per_lot_usd",
        commission_value=2.5,
        commission_side="per_side",
    )
    base.update(kwargs)
    return CostProfile(**base)


def test_comision_por_lote_a_precio() -> None:
    value, error = commission_price(
        _profile(), price=1.10, contract_size=100_000
    )
    assert error is None
    assert value == 2.5 * 2 / 100_000


def test_comision_porcentaje_y_cero() -> None:
    value, error = commission_price(
        _profile(
            commission_type="percent_of_volume",
            commission_value=0.0007,
            symbol="XAUUSD",
        ),
        price=2000.0,
        contract_size=100,
    )
    assert error is None
    assert value == 2000.0 * 0.0007 / 100.0 * 2
    zero, error = commission_price(
        _profile(commission_type="zero", commission_value=0.0),
        price=1.0,
        contract_size=100_000,
    )
    assert zero == 0.0 and error is None


def test_comision_sin_contrato_es_sin_datos() -> None:
    value, error = commission_price(
        _profile(symbol="US100"), price=20_000.0, contract_size=None
    )
    assert value is None
    assert "contract_size" in str(error)


def test_coste_y_cost_r_viable() -> None:
    profile = _profile(spread_p75_price=0.00002)
    cost = operation_cost(
        profile, price=1.10, contract_size=100_000, slippage=0.00005
    )
    assert cost["total"] == 0.00002 + 0.00005 + 0.0001
    verdict = assess_cost(cost, r_typical=0.0017, usable_from="2024-01-01")
    assert verdict["viable"] is True
    assert verdict["cost_r"] == pytest.approx(0.1)
    tight = assess_cost(cost, r_typical=0.001, usable_from="2024-01-01")
    assert tight["viable"] is False
    assert "cost_R" in tight["reason"]


def test_cost_r_fuera_de_usable_from_no_es_viable() -> None:
    profile = _profile(spread_p75_price=0.00002)
    cost = operation_cost(
        profile, price=1.10, contract_size=100_000, slippage=0.00005
    )
    verdict = assess_cost(cost, r_typical=0.01, usable_from=None)
    assert verdict["viable"] is False
    assert verdict["reason"] == "fuera de usable_from"


def test_atr_tipico_sintetico() -> None:
    index = pd.date_range("2024-01-01", periods=100, freq="5min", tz="UTC")
    close = np.full(100, 100.0)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 5.0,
            "low": close - 5.0,
            "close": close,
        },
        index=index,
    )
    value = median_atr_from_frame(frame)
    assert value is not None
    assert 9.9 <= value <= 10.1
    assert median_atr_from_frame(frame, "2025-01-01") is None


def test_cost_r_compartido_onboarding_y_edge_map() -> None:
    from tradinglab.discovery import edge_map
    from tradinglab.propfund.onboarding_mtf import cost_r_for

    r_values = {"US100:H1": {"r": 40.0, "price": 20_000.0}}
    onboarding = cost_r_for("CFD-001", "US100", "H1", r_values=r_values)
    screening = edge_map.template_cost_r(
        "CFD-001", "US100", "H1", r_values=r_values
    )
    assert onboarding["cost_r"] == pytest.approx(screening["cost_r"])
    assert onboarding["viable"] == screening["viable"]
    assert onboarding["swap_credit_r_night"]["long"] > 0.0
    assert onboarding["swap_credit_r_night"]["short"] == 0.0


def test_base_viability_usa_r_cost_de_operaciones() -> None:
    from types import SimpleNamespace

    from tradinglab.discovery import edge_map

    trades = [
        SimpleNamespace(r_cost=0.02),
        SimpleNamespace(r_cost=0.04),
        SimpleNamespace(r_cost=None),
    ]
    assert edge_map._trade_cost_r(trades) == pytest.approx(0.03)
    assert edge_map._trade_cost_r([SimpleNamespace(r_cost=None)]) is None


