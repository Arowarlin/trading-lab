"""FUT-A10: programas de MFF Rapid 50K y Lucid Flex 50K con el esquema ampliado y su efecto en el motor."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.account import (
    MissingRuleError,
    new_funded,
    payout_rules_from_program,
    step_funded_day,
)
from tradinglab.prop_economics.paths import DayPath
from tradinglab.prop_economics.project import (
    ProjectConfig,
    session_offsets,
    simulate_project,
    simulate_project_path,
)
from tradinglab.prop_economics.rules import blocking_unknowns, load_program, max_contracts_for
from tradinglab.prop_economics.simulate import stationary_bootstrap_indices

PROGRAMS = ROOT / "config" / "prop_economics" / "programs"
START = date(2027, 2, 1)
D = START
LUCID_ASSUME = (("fees.evaluation", 125.0),)
MFF_ASSUME = (("max_fraction_of_balance", 1.0), ("cap_per_payout", math.inf))


@pytest.fixture(scope="module")
def lucid():
    return load_program(PROGRAMS / "lucid_flex_50k.yaml")


@pytest.fixture(scope="module")
def mff():
    return load_program(PROGRAMS / "myfundedfutures_rapid_50k.yaml")


def day(x: float) -> DayPath:
    return DayPath(D, np.asarray([0.0, x]), 1, (1,), float(x), 0.0)


def test_blocking_unknowns_exact(lucid, mff):
    assert blocking_unknowns(lucid) == [
        "fees.consistency_addon", "fees.data_platform_monthly", "fees.evaluation", "fees.reset",
        "phases.funded.inactivity_close_days", "phases.funded.max_accounts",
        "phases.funded.payout.max_fraction_of_balance",
    ]
    assert blocking_unknowns(mff) == [
        "fees.reset", "phases.funded.max_contracts", "phases.funded.max_loss",
        "phases.funded.payout.cap_per_payout", "phases.funded.payout.max_fraction_of_balance",
        "phases.funded.payout.processing_days", "phases.funded.scaling_plan",
    ]


def test_contract_caps(lucid, mff):
    assert max_contracts_for(lucid, "evaluation", 0.0) == 40
    assert [max_contracts_for(lucid, "funded", p) for p in (-50.0, 999.0, 1000.0, 1999.0, 2000.0)] == [20, 20, 30, 30, 40]
    assert max_contracts_for(mff, "funded", 5000.0) == 50


def test_lucid_payout_rules(lucid):
    r = payout_rules_from_program(lucid)
    assert (r.template, r.n, r.min_day_profit, r.fraction, r.cap, r.min_amount, r.split) == \
        ("winning_days", 5, 150.0, 0.5, 2000.0, 500.0, 0.9)
    assert (r.processing_days, r.net_positive_cycle, r.max_payouts, r.buffer_min, r.lock_value) == \
        (2, True, 5, 0.0, 50100.0)


def test_mff_rules_need_explicit_assumptions(mff):
    with pytest.raises(MissingRuleError):
        payout_rules_from_program(mff)
    r = payout_rules_from_program(mff, assume=dict(MFF_ASSUME))
    assert (r.template, r.min_balance, r.n, r.buffer_min, r.min_amount, r.to_live_daily_profit, r.lock_value) == \
        ("min_balance_and_days", 2100.0, 1, 2100.0, 500.0, 10000.0, 100.0)


def test_mff_daily_profit_moves_account_to_live(mff):
    r = payout_rules_from_program(mff, assume=dict(MFF_ASSUME))
    st, ev = step_funded_day(new_funded(mff), mff, r, day(10_000.0), 1, 1)
    assert (st.status, ev) == ("to_live", None)


def test_net_positive_cycle_blocks_payout(lucid):
    r = payout_rules_from_program(lucid)
    st = new_funded(lucid)
    # −1.100 y luego 5 días de +200: 5 días ≥ 150 pero el ciclo neto es −100 → sin payout y sin rotura
    for i, x in enumerate([-1100, 200, 200, 200, 200, 200], start=1):
        st, ev = step_funded_day(st, lucid, r, day(x), 1, i)
        assert ev is None
    assert (st.status, st.win_days_since, st.profit_since) == ("active", 5, -100.0)
    without = payout_rules_from_program(lucid).__class__(**{**r.__dict__, "net_positive_cycle": False,
                                                              "min_amount": 0.0})
    st2 = new_funded(lucid)
    for i, x in enumerate([-1100, 200, 200, 200, 200, 200], start=1):
        st2, ev2 = step_funded_day(st2, lucid, without, day(x), 1, i)
    assert st2.status == "active"   # sin la regla, la elegibilidad no se bloquea por el ciclo (el importe es ≤ 0)


def test_lucid_deterministic_scaling_and_payouts(lucid):
    cfg = ProjectConfig(contracts_eval=10, contracts_funded=30, budget=1500.0, start_date=START,
                        horizons_days=(60,), assume=LUCID_ASSUME)
    offsets = session_offsets(START, 60)
    idx = np.zeros((1, len(offsets)), dtype=np.int64)
    ref = simulate_project_path(lucid, [day(15.0)], idx[0], cfg, offsets)
    assert ref["passed"] == 1
    assert ref["recv_at"][26] == pytest.approx(742.5)      # 1.er payout: 825 pedidos el día 24, cobro +2
    assert ref["recv_at"][31] == pytest.approx(1316.25)    # 2.º payout: 1.462,50 pedidos el día 29
    res = simulate_project(lucid, [day(15.0)], cfg, n_paths=1, seed=0, idx=idx)
    assert res["per_path"]["received"][0] == pytest.approx(ref["recv_at"].sum())


POOL = [
    DayPath(D, np.asarray([0, 70, -20, 45.0]), 1, (3,), 45.0, 0.0),
    DayPath(D, np.asarray([0, -30, -90, 20.0]), 1, (3,), 20.0, 0.0),
    DayPath(D, np.asarray([0, 120, -60.0]), 1, (2,), -60.0, 0.0),
    DayPath(D, np.asarray([0.0]), 0, (), 0.0, 0.0),
    DayPath(D, np.asarray([0, 90.0]), 1, (1,), 90.0, 0.0),
    DayPath(D, np.asarray([0, -110.0]), 1, (1,), -110.0, 0.0),
    DayPath(D, np.asarray([0, 60.0]), 1, (1,), 60.0, 0.0),
]


@pytest.mark.parametrize("name, assume, contracts", [
    ("lucid_flex_50k", LUCID_ASSUME, (10, 30)),
    ("myfundedfutures_rapid_50k", MFF_ASSUME, (10, 10)),
])
def test_vectorized_equals_scalar_real_programs(name, assume, contracts):
    prog = load_program(PROGRAMS / f"{name}.yaml")
    cfg = ProjectConfig(contracts_eval=contracts[0], contracts_funded=contracts[1], budget=1500.0, start_date=START,
                        horizons_days=(240,), assume=assume)
    offsets = session_offsets(START, 240)
    idx = stationary_bootstrap_indices(len(POOL), len(offsets), 120, 2.0, seed=21)
    res = simulate_project(prog, POOL, cfg, n_paths=120, seed=0, idx=idx)
    pp = res["per_path"]
    assert (pp["passed"] > 0).any() and (pp["requested"] > 0).any()
    for p in range(idx.shape[0]):
        ref = simulate_project_path(prog, POOL, idx[p], cfg, offsets)
        assert abs(ref["fees_at"].sum() - pp["fees"][p]) < 1e-9
        assert abs(ref["recv_at"].sum() - pp["received"][p]) < 1e-9
        for key in ("bought", "passed", "evals_lost", "funded_lost", "requested", "ruin_t", "to_live"):
            assert ref[key] == pp[key][p], (key, p)
