"""FUT-O5: cuentas correladas frente a independientes (mismo EV, distinta dispersión)."""

from __future__ import annotations

from datetime import date

import numpy as np

from tradinglab.config import ROOT
from tradinglab.prop_economics.pools import synthetic_pool
from tradinglab.prop_economics.portfolio import simulate_portfolio
from tradinglab.prop_economics.project import ProjectConfig, session_offsets, simulate_project
from tradinglab.prop_economics.rules import load_program
from tradinglab.prop_economics.simulate import stationary_bootstrap_indices

PROG = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")
POOL = synthetic_pool(mu_gross_r=0.15, rr=1.5, risk_usd=50.0, cost_rt=2.22, n_days=300, seed=11)
CFG = ProjectConfig(contracts_eval=10, contracts_funded=10, budget=1500.0, start_date=date(2027, 2, 1),
                    horizons_days=(365,), assume_processing_days=3)


def test_correlated_is_k_times_one_account_with_split_budget():
    two = simulate_portfolio(PROG, POOL, CFG, k=2, correlated=True, n_paths=400, seed=4, mean_block=1.0)
    idx = stationary_bootstrap_indices(len(POOL), len(session_offsets(CFG.start_date, 365)), 400, 1.0, 4)
    one = simulate_project(PROG, POOL, ProjectConfig(**{**CFG.__dict__, "budget": 750.0}), n_paths=400, seed=4, idx=idx)
    assert np.allclose(two["net_paths"][365], 2 * one["net_paths"][365])


def test_independent_has_same_ev_and_less_dispersion():
    corr = simulate_portfolio(PROG, POOL, CFG, k=3, correlated=True, n_paths=1500, seed=8, mean_block=1.0)["horizons"][365]
    ind = simulate_portfolio(PROG, POOL, CFG, k=3, correlated=False, n_paths=1500, seed=8, mean_block=1.0)["horizons"][365]
    assert abs(corr["ev"] - ind["ev"]) < 4 * np.hypot(corr["se"], ind["se"])
    assert ind["sd"] < corr["sd"]
    assert ind["p5"] >= corr["p5"]
