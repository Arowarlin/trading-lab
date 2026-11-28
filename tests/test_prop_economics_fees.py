"""FUT-A5: tarifas y coste por intento (04 §5; vectores T11 y T12)."""

from __future__ import annotations

import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.account import MissingRuleError
from tradinglab.prop_economics.fees import (
    cost_per_funded,
    ev_per_attempt,
    evaluation_cost,
    subscription_charges,
)
from tradinglab.prop_economics.rules import Program, load_program

PROGRAMS = ROOT / "config" / "prop_economics" / "programs"


@pytest.mark.parametrize("end_day, charges", [(30, 1), (31, 2), (61, 3), (1, 1)])
def test_t11_subscription_charges(end_day, charges):
    assert subscription_charges(end_day, 30) == charges


def test_t11_amounts_with_49():
    topstep = load_program(PROGRAMS / "topstep_50k_combine_xfa.yaml")
    assert [evaluation_cost(topstep, d) for d in (30, 31, 61)] == [49.0, 98.0, 147.0]


def test_subscription_rejects_bad_input():
    with pytest.raises(ValueError):
        subscription_charges(0, 30)
    with pytest.raises(ValueError):
        subscription_charges(10, 0)


def test_one_time_cost():
    assert evaluation_cost(load_program(PROGRAMS / "synthetic_static.yaml"), 400) == 100.0


def test_missing_price_raises():
    data = load_program(PROGRAMS / "synthetic_static.yaml").model_dump(mode="json")
    data["fees"]["evaluation"] = {"type": "one_time", "status": "sin_datos"}
    with pytest.raises(MissingRuleError):
        evaluation_cost(Program.model_validate(data), 10)


def test_t12_ev_and_cost_per_funded():
    assert ev_per_attempt(0.4, 100, 150, 900) == 200.0
    assert cost_per_funded(0.4, 100, 150) == 400.0
    with pytest.raises(ValueError):
        cost_per_funded(0.0, 100, 150)
