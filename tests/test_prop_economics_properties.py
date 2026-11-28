"""FUT-A9: propiedades del motor (04 §10, T14) con hypothesis."""

from __future__ import annotations

from datetime import date

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from tradinglab.prop_economics.account import (
    PayoutRules,
    new_evaluation,
    new_funded,
    step_day,
    step_funded_day,
)
from tradinglab.prop_economics.fees import subscription_charges
from tradinglab.prop_economics.paths import DayPath
from tradinglab.prop_economics.rules import Program

D = date(2027, 2, 1)

marks_st = st.lists(st.floats(-3000, 3000, allow_nan=False, allow_infinity=False), min_size=1, max_size=6)
days_st = st.lists(marks_st, min_size=1, max_size=25)
mode_st = st.sampled_from(["static", "trailing_eod", "trailing_intraday"])
lock_st = st.one_of(st.none(), st.sampled_from([0.0, 100.0, "start_balance"]))
dll_st = st.one_of(st.none(), st.tuples(st.sampled_from([500.0, 1000.0]), st.sampled_from(["pause_day", "breach"])))


def program(mode, lock_at, dll) -> Program:
    ev = {"start_balance": {"value": 0, "status": "assumed"},
          "profit_target": {"value": 1e9, "status": "assumed"},
          "max_loss": {"mode": mode, "amount": 2000, "lock_at": lock_at, "status": "assumed"}}
    if dll is not None:
        ev["daily_loss"] = {"amount": dll[0], "action": dll[1], "status": "assumed"}
    funded = {"start_balance": {"value": 0, "status": "assumed"},
              "max_loss": {"mode": mode, "amount": 2000, "lock_at": lock_at, "lock_after_first_payout": True,
                           "status": "assumed"},
              "payout": {"eligibility": {"template": "winning_days", "n": 2, "min_day_profit": 50, "status": "assumed"},
                         "max_fraction_of_balance": {"value": 0.5, "status": "assumed"},
                         "cap_per_payout": {"value": 2000, "status": "assumed"},
                         "min_amount": {"value": 100, "status": "assumed"},
                         "split": {"value": 0.9, "status": "assumed"},
                         "processing_days": {"value": 0, "status": "assumed"}}}
    if dll is not None:
        funded["daily_loss"] = {"amount": dll[0], "action": dll[1], "status": "assumed"}
    return Program.model_validate({
        "schema_version": 1, "program_id": "p", "firm_id": "p", "rules_version": "1", "consulted_at": "2026-11-28",
        "expires_after_days": 30, "instrument_unit": "micro",
        "phases": {"evaluation": ev, "funded": funded},
        "fees": {"evaluation": {"type": "one_time", "amount": 100, "status": "assumed"}}})


def mk(marks: list[float]) -> DayPath:
    arr = np.asarray([0.0, *marks], dtype=np.float64)
    return DayPath(D, arr, 1, (arr.size - 1,), float(arr[-1]), 0.0)


@settings(max_examples=500, deadline=None)
@given(mode_st, lock_st, dll_st, days_st, st.integers(1, 3))
def test_evaluation_threshold_never_decreases_and_balance_moves_by_close(mode, lock_at, dll, days, k):
    prog = program(mode, lock_at, dll)
    s = new_evaluation(prog)
    for marks in days:
        prev = s
        s = step_day(s, prog, mk(marks), k)
        assert s.threshold >= prev.threshold - 1e-9
        if s.status == "active":
            moved = s.balance - prev.balance
            full = k * marks[-1]
            if dll is None:
                assert abs(moved - full) < 1e-6
            else:   # con DLL el día puede cerrar antes (pausa) en una marca intermedia
                assert any(abs(moved - k * m) < 1e-6 for m in marks)
        if s.status != "active":
            break


@settings(max_examples=500, deadline=None)
@given(mode_st, lock_st, dll_st, days_st, st.integers(1, 3))
def test_funded_payouts_bounded_and_threshold_monotone(mode, lock_at, dll, days, k):
    prog = program(mode, lock_at, dll)
    lock_value = None if lock_at is None else (0.0 if lock_at == "start_balance" else float(lock_at))
    rules = PayoutRules(template="winning_days", n=2, min_day_profit=50.0, fraction=0.5, cap=2000.0,
                        min_amount=100.0, split=0.9, lock_after_first_payout=True, lock_value=lock_value)
    s = new_funded(prog)
    for t, marks in enumerate(days):
        prev = s
        s, ev = step_funded_day(s, prog, rules, mk(marks), k, t)
        assert s.threshold >= prev.threshold - 1e-9
        if ev is not None:
            assert 0 < ev.received <= ev.gross
            assert ev.gross >= rules.min_amount
            assert ev.gross <= rules.cap
        if s.status != "active":
            break


@settings(max_examples=500, deadline=None)
@given(st.integers(1, 3000), st.integers(1, 60))
def test_subscription_charges_nonnegative_and_monotone(end_day, period):
    c = subscription_charges(end_day, period)
    assert c >= 1
    assert subscription_charges(end_day + 1, period) >= c
