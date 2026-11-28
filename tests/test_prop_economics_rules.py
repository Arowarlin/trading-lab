"""FUT-A1: esquema de programas, caducidad e incógnitas bloqueantes (04_SPEC_PROP_EV.md §8)."""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from pydantic import ValidationError

from tradinglab.config import ROOT
from tradinglab.prop_economics.rules import Program, blocking_unknowns, is_expired, load_program

PROGRAMS = ROOT / "config" / "prop_economics" / "programs"


@pytest.fixture(scope="module")
def topstep() -> Program:
    return load_program(PROGRAMS / "topstep_50k_combine_xfa.yaml")


def test_three_yaml_load():
    for name in ("topstep_50k_combine_xfa", "synthetic_static", "synthetic_trailing"):
        assert load_program(PROGRAMS / f"{name}.yaml").program_id == name


def test_expiry(topstep):
    assert is_expired(topstep, date(2026, 12, 26)) is False
    assert is_expired(topstep, date(2026, 12, 27)) is True


def test_blocking_unknowns_topstep(topstep):
    # FUT-A1b: las comisiones ya están verificadas (tabla TopstepX)
    assert blocking_unknowns(topstep) == [
        "phases.funded.payout.processing_days",
        "phases.funded.scaling_plan",
    ]
    assert (topstep.commissions_per_side["MNQ"].value, topstep.commissions_per_side["NQ"].value) == (0.61, 1.89)


def test_blocking_unknowns_synthetic_static():
    assert blocking_unknowns(load_program(PROGRAMS / "synthetic_static.yaml")) == []


def test_disabled_rule_is_ignored(topstep):
    data = topstep.model_dump(mode="json")
    data["phases"]["evaluation"]["daily_loss"]["status"] = "sin_datos"
    assert "phases.evaluation.daily_loss" not in blocking_unknowns(Program.model_validate(data))
    data["phases"]["evaluation"]["daily_loss"]["enabled"] = True
    assert "phases.evaluation.daily_loss" in blocking_unknowns(Program.model_validate(data))


@pytest.mark.parametrize("mutation", [
    {"mode": "trailing_xyz"},
    {"amount": -1},
])
def test_invalid_max_loss_raises(mutation):
    data = yaml.safe_load((PROGRAMS / "synthetic_static.yaml").read_text(encoding="utf-8"))
    data["phases"]["evaluation"]["max_loss"].update(mutation)
    with pytest.raises(ValidationError):
        Program.model_validate(data)


def test_unknown_field_raises():
    data = yaml.safe_load((PROGRAMS / "synthetic_static.yaml").read_text(encoding="utf-8"))
    data["phases"]["evaluation"]["buffer_min"] = {"value": 1, "status": "assumed"}
    with pytest.raises(ValidationError):
        Program.model_validate(data)
