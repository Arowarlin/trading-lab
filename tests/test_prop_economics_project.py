"""FUT-A6b: proyecto completo por camino (evaluación → financiada → payouts → recompra), vectorizado = escalar."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.paths import DayPath, TradeSpec, from_trades
from tradinglab.prop_economics.project import (
    ProjectConfig,
    session_offsets,
    simulate_project,
    simulate_project_path,
)
from tradinglab.prop_economics.rules import Program, load_program
from tradinglab.prop_economics.simulate import stationary_bootstrap_indices

D = date(2027, 2, 1)
START = date(2027, 2, 1)   # lunes; sin festivos CME del índice hasta el Viernes Santo (2027-03-26)


def day(marks: list[float], n_trades: int = 1) -> DayPath:
    return DayPath(D, np.asarray(marks, dtype=np.float64), n_trades, (len(marks) - 1,), float(marks[-1]), 0.0)


def synthetic(*, fee=None, processing=0, eligibility=None, funded_dll=None, eval_extra=None) -> Program:
    fee = fee or {"type": "one_time", "amount": 100, "status": "assumed"}
    proc = {"status": "sin_datos"} if processing is None else {"value": processing, "status": "assumed"}
    funded = {
        "start_balance": {"value": 0, "status": "assumed"},
        "max_loss": {"mode": "trailing_eod", "amount": 2000, "lock_at": 0, "lock_after_first_payout": True,
                     "status": "assumed"},
        "payout": {
            "eligibility": eligibility or {"template": "winning_days", "n": 5, "min_day_profit": 150,
                                           "status": "assumed"},
            "max_fraction_of_balance": {"value": 0.5, "status": "assumed"},
            "cap_per_payout": {"value": 2000, "status": "assumed"},
            "min_amount": {"value": 125, "status": "assumed"},
            "split": {"value": 0.9, "status": "assumed"},
            "processing_days": proc,
        },
    }
    if funded_dll:
        funded["daily_loss"] = funded_dll
    evaluation = {"start_balance": {"value": 0, "status": "assumed"},
                  "profit_target": {"value": 3000, "status": "assumed"},
                  "max_loss": {"mode": "static", "amount": 2000, "status": "assumed"},
                  "min_trading_days": {"value": 2, "status": "assumed"}}
    evaluation.update(eval_extra or {})
    return Program.model_validate({
        "schema_version": 1, "program_id": "syn", "firm_id": "syn", "rules_version": "1",
        "consulted_at": "2026-11-28", "expires_after_days": 3650, "instrument_unit": "micro",
        "phases": {"evaluation": evaluation, "funded": funded},
        "fees": {"evaluation": fee, "activation": {"amount": 150, "status": "assumed"}},
    })


def cfg(**kw) -> ProjectConfig:
    base = dict(contracts_eval=1, contracts_funded=1, budget=1500.0, start_date=START, horizons_days=(30, 90))
    base.update(kw)
    return ProjectConfig(**base)


# ------------------------------------------------------------------ deterministas

def test_session_offsets_feb_2027():
    off = session_offsets(START, 30)
    assert len(off) == 22 and off[0] == 0 and off[-1] == 29


def test_deterministic_always_winning_day():
    res = simulate_project(synthetic(), [day([0, 1000])], cfg(), n_paths=4, seed=1, mean_block=1.0)
    h30 = res["horizons"][30]
    assert h30["ev"] == pytest.approx(5150.0)
    assert h30["payouts_received"] == 3.0
    assert h30["fees"] == 250.0
    assert (h30["p_net_pos"], h30["p_ruin"], h30["accounts_bought"]) == (1.0, 0.0, 1.0)


def test_processing_delay_moves_payout_out_of_horizon():
    res = simulate_project(synthetic(processing=5), [day([0, 1000])], cfg(), n_paths=2, seed=1, mean_block=1.0)
    h30 = res["horizons"][30]
    assert h30["payouts_received"] == 2.0
    assert h30["payouts_requested"] == 3.0
    assert h30["ev"] == pytest.approx(2 * 1800 - 250)


def test_subscription_renewals():
    prog = synthetic(fee={"type": "subscription", "amount": 49, "period_days": 30, "status": "assumed"})
    res = simulate_project(prog, [day([0, 0])], cfg(), n_paths=2, seed=1, mean_block=1.0)
    assert res["horizons"][30]["fees"] == 49.0
    assert res["horizons"][90]["fees"] == 147.0


def test_ruin_when_budget_cannot_rebuy():
    res = simulate_project(synthetic(), [day([0, -2500])], cfg(budget=150.0), n_paths=3, seed=1, mean_block=1.0)
    h30 = res["horizons"][30]
    assert (h30["p_ruin"], h30["fees"], h30["ev"], h30["accounts_bought"]) == (1.0, 100.0, -100.0, 1.0)


def test_rebuy_until_budget_exhausted():
    # cada evaluación rompe el primer día: 1.000 de presupuesto / 100 por intento = 10 compras y ruina el día 9
    res = simulate_project(synthetic(), [day([0, -2500])], cfg(budget=1000.0), n_paths=2, seed=1, mean_block=1.0)
    pp = res["per_path"]
    assert pp["bought"].tolist() == [10, 10]
    assert pp["ruin_t"].tolist() == [9, 9]


def test_missing_processing_days_raises():
    from tradinglab.prop_economics.account import MissingRuleError
    with pytest.raises(MissingRuleError):
        simulate_project(synthetic(processing=None), [day([0, 1000])], cfg(), n_paths=2, seed=1, mean_block=1.0)


# ------------------------------------------------------------------ equivalencia con la referencia escalar

POOL = [
    day([0, 700, -200, 450]),
    day([0, -300, -900, 200]),
    day([0, 1200, -600]),
    day([0.0], n_trades=0),
    from_trades(D, [TradeSpec(350, 500, 120, 2.0), TradeSpec(-180, 90, 260, 2.0)]),
    day([0, 900]),
    day([0, -1100]),
]

POOL_UP = [   # deriva positiva y días parecidos: la plantilla de consistencia llega a pagar
    day([0, 300, 150]),
    day([0, 200]),
    day([0, 250, -50, 220]),
    day([0, -150]),
    day([0, -850, 100]),                               # dispara la DLL de 800 (pause_day) en la financiada
    day([0, 180]),
]

PROGRAMS = {
    "topstep": load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml"),
    "syn_consistency_dll": synthetic(
        eligibility={"template": "trading_days_consistency", "n": 3, "c": 0.4, "status": "assumed"},
        funded_dll={"amount": 800, "action": "pause_day", "status": "assumed"},
        eval_extra={"consistency": {"max_best_day_fraction": 0.5, "status": "assumed"}}),
    "syn_min_balance": synthetic(
        eligibility={"template": "min_balance_and_days", "n": 2, "min_balance": 1500, "status": "assumed"},
        processing=2),
}


@pytest.mark.parametrize("name, pool_name, kw", [
    ("topstep", "POOL", dict(assume_processing_days=3, contracts_eval=2, contracts_funded=2)),
    ("syn_consistency_dll", "POOL_UP", dict(policy="fixed", policy_arg=400.0, payout_fee=30.0)),
    ("syn_min_balance", "POOL", dict(policy="keep_cushion", policy_arg=800.0, budget=400.0)),
])
def test_vectorized_equals_scalar(name, pool_name, kw):
    prog = PROGRAMS[name]
    pool = globals()[pool_name]
    c = cfg(horizons_days=(120,), **kw)
    offsets = session_offsets(START, 120)
    idx = stationary_bootstrap_indices(len(pool), len(offsets), 150, 2.5, seed=11)
    res = simulate_project(prog, pool, c, n_paths=150, seed=0, idx=idx)
    pp = res["per_path"]
    assert (pp["requested"] > 0).any() and (pp["passed"] > 0).any()   # el caso ejerce los payouts
    for p in range(idx.shape[0]):
        ref = simulate_project_path(prog, pool, idx[p], c, offsets)
        assert abs(ref["fees_at"].sum() - pp["fees"][p]) < 1e-9
        assert abs(ref["recv_at"].sum() - pp["received"][p]) < 1e-9
        assert ref["recv_n_at"].sum() == pp["received_n"][p]
        for key in ("bought", "passed", "evals_lost", "funded_lost", "requested", "ruin_t"):
            assert ref[key] == pp[key][p], (key, p)
        assert ref["phase"] == pp["phase"][p]
    assert res["horizons"][120]["accounts_bought"] >= 1.0
