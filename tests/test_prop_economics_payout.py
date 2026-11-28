"""FUT-A4: fase financiada y payouts (04 §4; vector T9 y vectores de 05 §4.8)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.account import (
    MissingRuleError,
    PayoutRules,
    new_funded,
    payout_rules_from_program,
    step_funded_day,
)
from tradinglab.prop_economics.paths import DayPath
from tradinglab.prop_economics.rules import Program, load_program

D = date(2026, 11, 30)


def program(*, start=0, lock_at=0, eligibility=None, min_amount=125, processing="sin_datos") -> Program:
    elig = eligibility or {"template": "winning_days", "n": 5, "min_day_profit": 150, "status": "assumed"}
    proc = {"status": "sin_datos"} if processing == "sin_datos" else {"value": processing, "status": "assumed"}
    funded = {
        "start_balance": {"value": start, "status": "assumed"},
        "max_loss": {"mode": "trailing_eod", "amount": 2000, "lock_at": lock_at, "lock_after_first_payout": True,
                     "status": "assumed"},
        "payout": {
            "eligibility": elig,
            "max_fraction_of_balance": {"value": 0.5, "status": "assumed"},
            "cap_per_payout": {"value": 2000, "status": "assumed"},
            "min_amount": {"value": min_amount, "status": "assumed"},
            "split": {"value": 0.9, "status": "assumed"},
            "processing_days": proc,
        },
    }
    return Program.model_validate({
        "schema_version": 1, "program_id": "t", "firm_id": "t", "rules_version": "1", "consulted_at": "2026-11-27",
        "expires_after_days": 30, "instrument_unit": "micro",
        "phases": {"evaluation": {"start_balance": {"value": 0, "status": "assumed"},
                                  "profit_target": {"value": 3000, "status": "assumed"},
                                  "max_loss": {"mode": "static", "amount": 2000, "status": "assumed"}},
                   "funded": funded},
        "fees": {"evaluation": {"type": "one_time", "amount": 100, "status": "assumed"}},
    })


def day(x: float) -> DayPath:
    return DayPath(D, np.asarray([0.0, x]), 1, (1,), float(x), 0.0)


def run(prog: Program, rules: PayoutRules, pnls: list[float], **kw):
    st = new_funded(prog)
    events = []
    for i, x in enumerate(pnls, start=1):
        st, ev = step_funded_day(st, prog, rules, day(x), 1, i, **kw)
        if ev is not None:
            events.append(ev)
    return st, events


def rules_for(prog: Program, **overrides) -> PayoutRules:
    r = payout_rules_from_program(prog, assume_processing_days=0)
    return PayoutRules(**{**r.__dict__, **overrides})


def test_t9_payout_then_breach():
    prog = program()
    r = rules_for(prog, min_amount=1e9)          # sin payout: umbral antes del payout
    st, ev = run(prog, r, [300] * 5)
    assert ev == [] and st.threshold == -500.0
    r = rules_for(prog)
    st, ev = run(prog, r, [300] * 5)
    assert len(ev) == 1
    assert (ev[0].gross, ev[0].received, ev[0].day_requested) == (750.0, 675.0, 5)
    assert (st.balance, st.threshold) == (750.0, 0.0)
    st, _ = step_funded_day(st, prog, r, day(-800), 1, 6)
    assert st.status == "failed_mll"


def test_cap():
    prog = program()
    st, ev = run(prog, rules_for(prog), [1200] * 5)
    assert (ev[0].gross, ev[0].received, st.balance) == (2000.0, 1800.0, 4000.0)


def test_winning_day_filter():
    prog = program()
    st, ev = run(prog, rules_for(prog), [300, 100, 300, 300, 300])
    assert ev == []
    st, ev = run(prog, rules_for(prog), [300, 100, 300, 300, 300, 300])
    assert (ev[0].day_requested, ev[0].gross, ev[0].received) == (6, 800.0, 720.0)


def test_min_amount_500():
    prog = program(min_amount=500)
    _, ev = run(prog, rules_for(prog), [150] * 5)
    assert ev == []
    _, ev = run(prog, rules_for(prog), [150] * 5 + [300])
    assert (ev[0].gross, ev[0].received) == (525.0, 472.5)


def test_trading_days_consistency():
    prog = program(eligibility={"template": "trading_days_consistency", "n": 3, "c": 0.4, "status": "assumed"})
    _, ev = run(prog, rules_for(prog), [100, 100, 100])
    assert (ev[0].day_requested, ev[0].gross, ev[0].received) == (3, 150.0, 135.0)
    _, ev = run(prog, rules_for(prog), [300, 100, 100])
    assert ev == []


def test_min_balance_and_days_with_buffer():
    prog = program(eligibility={"template": "min_balance_and_days", "n": 1, "min_balance": 2100, "status": "assumed"})
    r = rules_for(prog, fraction=1.0, cap=float("inf"), buffer_min=2100.0, min_amount=500.0)
    st, ev = run(prog, r, [2700])
    assert (ev[0].gross, ev[0].received, st.balance) == (600.0, 540.0, 2100.0)


@pytest.mark.parametrize("policy, arg, gross, balance", [
    ("keep_cushion", 500, 750.0, 750.0),
    ("keep_cushion", 1000, 500.0, 1000.0),
    ("fixed", 300, 300.0, 1200.0),
])
def test_policies(policy, arg, gross, balance):
    prog = program()
    st, ev = run(prog, rules_for(prog), [300] * 5, policy=policy, policy_arg=arg)
    assert (ev[0].gross, st.balance) == (gross, balance)
    if policy == "fixed":
        assert ev[0].received == 270.0


def test_processing_days():
    prog = program()
    with pytest.raises(MissingRuleError):
        payout_rules_from_program(prog)
    r = payout_rules_from_program(prog, assume_processing_days=3)
    _, ev = run(prog, r, [300] * 5)
    assert ev[0].day_received == 8


def test_payout_fee():
    prog = program()
    _, ev = run(prog, rules_for(prog), [300] * 5, payout_fee=30.0)
    assert ev[0].received == 645.0


def test_absolute_lock_with_nonzero_start():
    """K es absoluto (04 §1): Lucid Flex empieza en 50.000 y bloquea en 50.100."""
    prog = program(start=50000, lock_at=50100)
    st, ev = run(prog, rules_for(prog), [300] * 5)
    assert ev[0].gross == 750.0
    assert st.threshold == 50100.0
    assert st.balance == 50750.0


def test_topstep_rules_load():
    prog = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")
    r = payout_rules_from_program(prog, assume_processing_days=3)
    assert (r.template, r.n, r.min_day_profit, r.fraction, r.cap, r.min_amount, r.split) == \
        ("winning_days", 5, 150.0, 0.5, 2000.0, 125.0, 0.9)
    assert (r.lock_after_first_payout, r.lock_value) == (True, 0.0)
