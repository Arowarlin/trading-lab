"""FUT-O3 (políticas de tamaño en el motor) y FUT-O4 (rejilla, selección y escalera de evidencia)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tradinglab.config import ROOT
from tradinglab.prop_economics.allocate import evaluate_grid, ladder_step, select
from tradinglab.prop_economics.policies import SizingPolicy
from tradinglab.prop_economics.pools import synthetic_pool
from tradinglab.prop_economics.project import (
    ProjectConfig,
    session_offsets,
    simulate_project,
    simulate_project_path,
)
from tradinglab.prop_economics.rules import load_program
from tradinglab.prop_economics.simulate import stationary_bootstrap_indices

PROGRAMS = ROOT / "config" / "prop_economics" / "programs"
START = date(2027, 2, 1)
RPC = 50.0 + 2.22   # 1 MNQ con stop de 25 puntos y costes de Topstep


# ------------------------------------------------------------------ FUT-O3

def test_fixed_policy_contracts():
    p = SizingPolicy("fixed", RPC, risk_usd=500.0)
    assert p.contracts(1234.0) == 9                  # suelo(500 / 52,22)
    assert p.contracts(np.array([0.0, 5000.0])).tolist() == [9, 9]


def test_cushion_policy_contracts_and_minimum():
    p = SizingPolicy("cushion", RPC, kappa=0.25, r_max=1000.0)
    assert p.contracts(2000.0) == 9                  # min(1000, 500) / 52,22 → 9
    assert p.contracts(8000.0) == 19                 # tope r_max = 1.000
    assert p.contracts(10.0) == 1                    # mínimo 1 micro mientras la cuenta viva
    assert p.contracts(-50.0) == 1


@settings(max_examples=500, deadline=None)
@given(st.floats(0, 5000), st.floats(0, 5000), st.floats(0.05, 1.0), st.floats(100, 3000))
def test_policy_is_anti_martingale(c1, loss, kappa, r_max):
    p = SizingPolicy("cushion", RPC, kappa=kappa, r_max=r_max)
    assert p.contracts(c1 - loss) <= p.contracts(c1)        # menos colchón tras perder → nunca más tamaño
    assert p.contracts(c1) * RPC <= max(r_max, RPC) + 1e-9   # nunca más riesgo que el autorizado (o 1 micro)


def test_invalid_policies():
    with pytest.raises(ValueError):
        SizingPolicy("martingale", RPC)
    with pytest.raises(ValueError):
        SizingPolicy("fixed", RPC)


@pytest.mark.parametrize("name, assume, policy", [
    ("topstep_50k_combine_xfa", (), SizingPolicy("cushion", RPC, kappa=0.3, r_max=900.0)),
    ("lucid_flex_50k", (("fees.evaluation", 125.0),), SizingPolicy("cushion", RPC, kappa=0.5, r_max=1500.0)),
    ("topstep_50k_combine_xfa", (), SizingPolicy("fixed", RPC, risk_usd=500.0)),
])
def test_sizing_vectorized_equals_scalar(name, assume, policy):
    prog = load_program(PROGRAMS / f"{name}.yaml")
    pool = synthetic_pool(mu_gross_r=0.15, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=300, seed=5)
    cfg = ProjectConfig(contracts_eval=1, contracts_funded=1, budget=1500.0, start_date=START, horizons_days=(240,),
                        assume_processing_days=3, assume=assume, sizing=policy)
    offsets = session_offsets(START, 240)
    idx = stationary_bootstrap_indices(len(pool), len(offsets), 80, 1.0, seed=9)
    pp = simulate_project(prog, pool, cfg, n_paths=80, seed=0, idx=idx)["per_path"]
    assert (pp["passed"] > 0).any()
    for p in range(idx.shape[0]):
        ref = simulate_project_path(prog, pool, idx[p], cfg, offsets)
        assert abs(ref["fees_at"].sum() - pp["fees"][p]) < 1e-9
        assert abs(ref["recv_at"].sum() - pp["received"][p]) < 1e-9
        for key in ("bought", "passed", "funded_lost", "requested", "ruin_t", "to_live"):
            assert ref[key] == pp[key][p], (key, p)


# ------------------------------------------------------------------ FUT-O4

def _row(policy, ev12, median12, ruin24, p_pos12, cap=1000.0):
    return {"policy": policy, "ev12": ev12, "median12": median12, "ruin24": ruin24, "p_pos12": p_pos12,
            "cap_p95": cap}


def test_select_respects_constraints_and_ties():
    rows = [_row("A", 5000, -10, 0.05, 0.7),        # mediana < 0
            _row("B", 4000, 900, 0.20, 0.8),        # ruina > 10 %
            _row("C", 3000, 800, 0.08, 0.55),       # P(neto>0) < 60 %
            _row("D", 2500, 700, 0.09, 0.65, cap=1500),
            _row("E", 2500, 600, 0.02, 0.70, cap=900)]
    assert select(rows)["policy"] == "E"            # empate en EV → menor capital requerido
    assert select(rows, ruin_max=0.25)["policy"] == "B"
    assert select(rows[:3]) is None                 # nada cumple → no comprar


@pytest.mark.parametrize("lcb, expected", [(-0.01, "no comprar evaluaciones"), (0.0, "no comprar evaluaciones"),
                                           (0.02, "no comprar todavía"), (0.03, "no comprar todavía"),
                                           (0.08, "D: 500"), (0.15, "D: 500"), (0.25, "E: riesgo")])
def test_evidence_ladder(lcb, expected):
    assert ladder_step(lcb).startswith(expected)


def test_grid_uses_common_random_numbers_and_orders_by_edge():
    prog = load_program(PROGRAMS / "topstep_50k_combine_xfa.yaml")
    pool = synthetic_pool(mu_gross_r=0.15, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=300, seed=7)
    cfg = ProjectConfig(contracts_eval=1, contracts_funded=1, budget=1500.0, start_date=START,
                        assume_processing_days=3)
    pols = [SizingPolicy("fixed", RPC, risk_usd=250.0), SizingPolicy("fixed", RPC, risk_usd=500.0)]
    rows = evaluate_grid(prog, pool, pols, cfg, n_paths=300, seed=3, mean_block=1.0)
    assert [r["policy"] for r in rows] == ["fixed_250", "fixed_500"]
    worse = evaluate_grid(prog, pool, pols, cfg, n_paths=300, seed=3, mean_block=1.0, delta=-15.0)
    for a, b in zip(rows, worse):                     # misma secuencia de días: menos ventaja → menos EV
        assert b["ev12"] < a["ev12"]
