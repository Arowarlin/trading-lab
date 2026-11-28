"""FUT-A7: escenarios de ventaja (04 §7.1) y ventaja mínima rentable μ* (04 §7.2)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.paths import DayPath, TradeSpec, from_trades
from tradinglab.prop_economics.project import ProjectConfig, session_offsets
from tradinglab.prop_economics.rules import load_program
from tradinglab.prop_economics.scenarios import (
    add_cost,
    ev_at_delta,
    lcb95_mean_net,
    min_profitable_edge,
    pool_stats,
    scenario_pool,
)
from tradinglab.prop_economics.simulate import stationary_bootstrap_indices

D = date(2027, 2, 1)


def two_trade_day() -> DayPath:
    return from_trades(D, [TradeSpec(100, 150, 40, 2.5), TradeSpec(-50, 20, 60, 2.5)], risk_usd=50.0)


def one(x: float, cost: float = 2.0, risk: float = 50.0) -> DayPath:
    return from_trades(D, [TradeSpec(x, max(x, 0.0), max(-x, 0.0), cost)], risk_usd=risk)


def test_pool_stats_exact():
    st = pool_stats([two_trade_day(), one(30), DayPath(D, np.asarray([0.0]), 0, (), 0.0, 0.0)])
    assert st["n_trades"] == 3
    assert st["mean_net"] == pytest.approx((50 + 30) / 3)
    assert st["mean_gross"] == pytest.approx((55 + 32) / 3)
    assert st["mean_cost"] == pytest.approx(7 / 3)
    assert st["mean_risk"] == 50.0


def test_add_cost_exact():
    day = add_cost(two_trade_day(), 1.5)
    assert day.marks.tolist() == [0, 150, -40, 98.5, 118.5, 38.5, 47.0]
    assert (day.gross_pnl, day.cost) == (55.0, 8.0)
    day.validate()


def test_scenarios_shift_and_costs():
    pool = [one(100), one(-40)]                  # mean_net 30, mean_gross 32, mean_cost 2
    assert scenario_pool(pool, "optimista")[1] == 0.0
    base, d = scenario_pool(pool, "base")
    assert d == -15.0 and pool_stats(base)["mean_net"] == pytest.approx(15.0)
    cons, d = scenario_pool(pool, "conservador", lcb95=10.0)
    assert d == -20.0
    assert pool_stats(cons)["mean_net"] == pytest.approx(10.0 - 0.5)       # costes ×1,25
    sev, d = scenario_pool(pool, "estres_severo", tick_value=0.5)
    assert d == -32.0
    assert pool_stats(sev)["mean_net"] == pytest.approx(-2.0 - 1.0 - 1.0)   # bruto 0, costes ×1,5, +1 tick/lado
    nul, d = scenario_pool(pool, "sin_ventaja")
    assert pool_stats(nul)["mean_net"] == pytest.approx(-2.0)
    with pytest.raises(ValueError):
        scenario_pool(pool, "conservador")
    with pytest.raises(ValueError):
        scenario_pool(pool, "estres_severo")


def test_lcb95_below_mean_and_exact_on_constant_pool():
    rng = np.random.default_rng(3)
    pool = [one(float(x)) for x in rng.normal(20, 80, 300).round(2)]
    lcb = lcb95_mean_net(pool, n_boot=1000, seed=1)
    assert lcb < pool_stats(pool)["mean_net"]
    const = [one(25.0)] * 50
    assert lcb95_mean_net(const, n_boot=200, seed=1) == pytest.approx(25.0)


def _program():
    return load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")


def test_mu_star_brackets_zero_ev():
    rng = np.random.default_rng(5)
    # pool de 1 MNQ: stop 25 pt (50 USD), objetivo 1,5 R; resultados aleatorios con media neta ~0
    outcomes = rng.choice([75.0 - 2.22, -50.0 - 2.22], size=250, p=[0.4, 0.6])
    pool = [one(float(x), cost=2.22) for x in outcomes]
    cfg = ProjectConfig(contracts_eval=10, contracts_funded=10, budget=1500.0, start_date=D,
                        assume_processing_days=3)
    res = min_profitable_edge(_program(), pool, cfg, horizon_days=180, n_paths=1500, seed=7, mean_block=1.0,
                              lo=-30.0, hi=40.0, tol=0.5)
    assert res["delta_star"] is not None
    assert res["monotone"] is True
    idx = stationary_bootstrap_indices(len(pool), len(session_offsets(D, 180)), 1500, 1.0, 7)
    c180 = ProjectConfig(**{**cfg.__dict__, "horizons_days": (180,)})
    ev_below, _ = ev_at_delta(_program(), pool, c180, res["delta_star"] - 3.0, horizon_days=180, idx=idx)
    ev_above, _ = ev_at_delta(_program(), pool, c180, res["delta_star"] + 3.0, horizon_days=180, idx=idx)
    assert ev_below < 0 < ev_above
    assert res["mu_star_r"] == pytest.approx(res["mu_star_usd"] / 50.0)


def test_mu_star_reports_no_sign_change():
    pool = [one(40.0)] * 20
    cfg = ProjectConfig(contracts_eval=10, contracts_funded=10, budget=1500.0, start_date=D,
                        assume_processing_days=3)
    res = min_profitable_edge(_program(), pool, cfg, horizon_days=90, n_paths=200, seed=1, mean_block=1.0,
                              lo=0.0, hi=5.0)
    assert res["delta_star"] is None and "sin cambio de signo" in res["note"]
