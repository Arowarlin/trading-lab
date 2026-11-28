"""FUT-M1…M3: estructuras de ratio negativo/positivo sobre el motor real y frontera por tolerancia."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.allocate import evaluate_grid
from tradinglab.prop_economics.policies import SizingPolicy
from tradinglab.prop_economics.project import ProjectConfig
from tradinglab.prop_economics.rules import load_program
from tradinglab.prop_economics.structures import frontier, structure_checks, structure_pool

TOPSTEP = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")
COST = 1.22 + 1.0


def test_structure_hits_the_net_edge():
    pool, s = structure_pool(risk_usd=500.0, rr=0.75, edge_net_usd=40.0, cost_rt_per_contract=COST,
                             n_days=20000, seed=1)
    assert (s["contracts"], s["risk_usd"], s["module"]) == (10, 500.0, "MOD-NR")
    assert s["win_net"] == pytest.approx(375 - 22.2) and s["loss_net"] == pytest.approx(522.2)
    net = np.mean([d.marks[-1] for d in pool])
    assert abs(net - 40.0) < 3 * np.std([d.marks[-1] for d in pool]) / np.sqrt(len(pool))


def test_zero_edge_any_ratio_has_zero_mean():
    for rr in (0.2, 1.0, 3.0):
        _, s = structure_pool(risk_usd=500.0, rr=rr, edge_net_usd=0.0, cost_rt_per_contract=COST, n_days=10, seed=1)
        assert s["p_win"] * s["win_net"] - (1 - s["p_win"]) * s["loss_net"] == pytest.approx(0.0, abs=1e-9)


def test_checks_day_minimum_microscalping_and_cushion():
    _, s = structure_pool(risk_usd=100.0, rr=1.5, edge_net_usd=0.0, cost_rt_per_contract=COST, n_days=5, seed=1)
    why = structure_checks(TOPSTEP, s, firm_id="topstep", median_hold_s=600)
    assert any("día mínimo de 150" in w for w in why)            # 150 − 4,44 < 150: nunca cobra
    _, s = structure_pool(risk_usd=1500.0, rr=0.1, edge_net_usd=0.0, cost_rt_per_contract=COST, n_days=5, seed=1)
    why = structure_checks(TOPSTEP, s, firm_id="lucid", median_hold_s=8, cushion_usd=1000.0)
    assert any("microscalping" in w for w in why) and any("colchón" in w for w in why)


def test_frontier_on_engine_rows():
    rows = []
    cfg = ProjectConfig(contracts_eval=1, contracts_funded=1, budget=1500.0, start_date=date(2027, 1, 4),
                        assume_processing_days=3)
    for risk, rr in ((250.0, 1.5), (500.0, 0.75)):
        pool, s = structure_pool(risk_usd=risk, rr=rr, edge_net_usd=40.0, cost_rt_per_contract=COST,
                                 n_days=400, seed=3)
        pol = SizingPolicy("fixed", s["loss_net"] / s["contracts"], risk_usd=s["loss_net"])
        r = evaluate_grid(TOPSTEP, pool, [pol], cfg, n_paths=300, seed=5, mean_block=1.0)[0]
        r["policy"] = f"{s['module']}_{risk:g}_rr{rr:g}"
        rows.append(r)
    f = frontier(rows, tolerances=(0.0, 1.0))
    assert f[0.0] is None or f[0.0]["ruin24"] == 0.0
    if f[1.0] is not None:
        assert f[1.0]["ev12"] == max(r["ev12"] for r in rows if r["median12"] > 0 and r["p_pos12"] >= 0.6)
