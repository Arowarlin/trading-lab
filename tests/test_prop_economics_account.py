"""FUT-A3: motor escalar de una cuenta en evaluación (04 §3; vectores T8, T10 y T13)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.prop_economics.account import new_evaluation, step_day
from tradinglab.prop_economics.paths import DayPath
from tradinglab.prop_economics.rules import Program

D = date(2026, 11, 30)


def program(mode="static", *, lock_at=None, check="realtime_unrealized", target=3000, dd=2000,
            dll=None, consistency=None, min_days=0, max_days=None) -> Program:
    ev = {
        "start_balance": {"value": 0, "status": "assumed"},
        "profit_target": {"value": target, "status": "assumed"},
        "max_loss": {"mode": mode, "amount": dd, "check": check, "lock_at": lock_at, "status": "assumed"},
        "min_trading_days": {"value": min_days, "status": "assumed"},
    }
    if dll is not None:
        ev["daily_loss"] = {"amount": dll[0], "action": dll[1], "status": "assumed"}
    if consistency is not None:
        ev["consistency"] = {"max_best_day_fraction": consistency, "status": "assumed"}
    if max_days is not None:
        ev["max_calendar_days"] = {"value": max_days, "status": "assumed"}
    return Program.model_validate({
        "schema_version": 1, "program_id": "t", "firm_id": "t", "rules_version": "1", "consulted_at": "2026-11-27",
        "expires_after_days": 30, "instrument_unit": "micro", "phases": {"evaluation": ev},
        "fees": {"evaluation": {"type": "one_time", "amount": 100, "status": "assumed"}},
    })


def day(marks: list[float], n_trades: int = 1) -> DayPath:
    return DayPath(D, np.asarray(marks, dtype=np.float64), n_trades, (len(marks) - 1,), float(marks[-1]), 0.0)


def run(prog: Program, days: list[list[float]], contracts: int = 1):
    st = new_evaluation(prog)
    for m in days:
        st = step_day(st, prog, day(m), contracts)
    return st


def test_new_evaluation():
    st = new_evaluation(program())
    assert (st.balance, st.threshold, st.status) == (0.0, -2000.0, "active")


def test_t8_trailing_intraday_breaks():
    st = run(program("trailing_intraday"), [[0, 1500, -600]])
    assert st.status == "failed_mll"
    assert st.threshold == -500.0


@pytest.mark.parametrize("mode", ["trailing_eod", "static"])
def test_t8_eod_and_static_survive(mode):
    st = run(program(mode), [[0, 1500, -600]])
    assert st.status == "active"
    assert st.balance == -600.0
    assert st.threshold == -2000.0


def test_t10_consistency_raises_target():
    prog = program(consistency=0.5)
    st = run(prog, [[0, 2000], [0, 1100]])
    assert st.status == "active"
    st = step_day(st, prog, day([0, 900]), 1)
    assert st.status == "passed"
    assert st.balance == 4000.0


def test_t13_dll_pause_day():
    st = run(program(dll=(1000, "pause_day")), [[0, -400, -1000, 500]])
    assert st.status == "active"
    assert st.balance == -1000.0


def test_dll_breach_action():
    st = run(program(dll=(1000, "breach")), [[0, -400, -1000, 500]])
    assert st.status == "failed_mll"


def test_static_breaks_on_equality():
    prog = program()
    st = run(prog, [[0, -1000]])
    assert st.status == "active"
    st = step_day(st, prog, day([0, -1000]), 1)
    assert st.status == "failed_mll"


def test_trailing_eod_lock_zero_then_break():
    st = run(program("trailing_eod", lock_at=0), [[0, 2000]])
    assert st.threshold == 0.0
    st = run(program("trailing_eod", lock_at=0), [[0, 2000], [0, -2000]])
    assert st.status == "failed_mll"


def test_eod_only_ignores_intraday_dip():
    st = run(program("trailing_eod", check="eod_only"), [[0, -2500, -100]])
    assert st.status == "active"
    assert st.balance == -100.0
    st = run(program("trailing_eod", check="eod_only"), [[0, -2500, -2000]])
    assert st.status == "failed_mll"


def test_contracts_scale_pnl():
    st = run(program(), [[0, 100, -50]], contracts=3)
    assert st.balance == -150.0


def test_min_days_and_timeout():
    st = run(program(min_days=2), [[0, 3000]])
    assert st.status == "active"
    st = run(program(min_days=2), [[0, 3000], [0, 10]])
    assert st.status == "passed"
    st = run(program(max_days=2), [[0, 10], [0, 10]])
    assert st.status == "failed_timeout"


def test_trading_days_ignore_empty_days():
    prog = program(min_days=2)
    st = new_evaluation(prog)
    st = step_day(st, prog, day([0, 3000]), 1)
    st = step_day(st, prog, DayPath(D, np.asarray([0.0]), 0, (), 0.0, 0.0), 1)
    assert (st.trading_days, st.days, st.status) == (1, 2, "active")


def test_threshold_never_decreases():
    prog = program("trailing_intraday", lock_at=0)
    first = run(prog, [[0, 1500, 500]])
    assert first.threshold == -500.0          # min(1500 - 2000, 0)
    second = step_day(first, prog, day([0, 800, -100]), 1)
    assert second.threshold == -500.0         # el pico sigue en 1500: no sube ni baja
    third = step_day(second, prog, day([0, 2500]), 1)
    assert third.threshold == 0.0             # pico 2900 -> min(900, 0) = 0 (bloqueo)


def test_terminal_state_is_frozen():
    prog = program()
    st = run(prog, [[0, -2000]])
    assert st.status == "failed_mll"
    assert step_day(st, prog, day([0, 5000]), 1) is st
