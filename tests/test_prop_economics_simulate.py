"""FUT-A6a: bootstrap estacionario, evaluación vectorizada = motor escalar, vectores T1-T7 (04 §6 y §10)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.prop_economics.account import new_evaluation, step_day
from tradinglab.prop_economics.paths import DayPath, TradeSpec, from_trades
from tradinglab.prop_economics.rules import Program, load_program
from tradinglab.prop_economics.simulate import (
    mean_block_length,
    simulate_evaluation,
    stationary_bootstrap_indices,
)

D = date(2026, 11, 30)
PROGRAMS = ROOT / "config" / "prop_economics" / "programs"


def day(marks: list[float], n_trades: int = 1) -> DayPath:
    return DayPath(D, np.asarray(marks, dtype=np.float64), n_trades, (len(marks) - 1,), float(marks[-1]), 0.0)


def variant(name: str, **max_loss) -> Program:
    data = load_program(PROGRAMS / f"{name}.yaml").model_dump(mode="json")
    data["phases"]["evaluation"]["max_loss"].update(max_loss)
    return Program.model_validate(data)


def with_rules(base: Program, **evaluation) -> Program:
    data = base.model_dump(mode="json")
    data["phases"]["evaluation"].update(evaluation)
    return Program.model_validate(data)


# ------------------------------------------------------------------ bootstrap

def test_bootstrap_shape_and_seed():
    a = stationary_bootstrap_indices(10, 50, 100, 3.0, seed=1)
    b = stationary_bootstrap_indices(10, 50, 100, 3.0, seed=1)
    assert a.shape == (100, 50)
    assert np.array_equal(a, b)
    assert a.min() >= 0 and a.max() <= 9


def test_bootstrap_huge_block_is_sequential():
    idx = stationary_bootstrap_indices(7, 40, 30, 1e12, seed=3)
    assert np.array_equal(idx, (idx[:, :1] + np.arange(40)) % 7)


def test_bootstrap_block_one_is_iid():
    idx = stationary_bootstrap_indices(1000, 200, 200, 1.0, seed=5)
    follows = (idx[:, 1:] == (idx[:, :-1] + 1) % 1000).mean()
    assert follows < 0.01        # con bloque 1 cada día es un sorteo nuevo (≈ 1/1000 por azar)


def test_bootstrap_rejects_block_below_one():
    with pytest.raises(ValueError):
        stationary_bootstrap_indices(10, 5, 5, 0.5, seed=1)


def test_mean_block_length_at_least_one():
    assert mean_block_length(np.random.default_rng(0).normal(size=300)) >= 1.0


# ------------------------------------------------------------------ equivalencia con el motor escalar

POOL = [
    day([0, 300, -100, 250]),
    day([0, -400, -1000, 500]),                        # activa la DLL de 1.000 (pause_day)
    day([0, 1500, -700]),                              # rompe en trailing intradía
    day([0.0], n_trades=0),                            # día sin operar
    from_trades(D, [TradeSpec(200, 260, 50, 2.0), TradeSpec(-120, 40, 150, 2.0)]),
    day([0, 900]),
]


@pytest.mark.parametrize("prog", [
    with_rules(variant("synthetic_static"),
               daily_loss={"amount": 1000, "action": "pause_day", "status": "assumed"},
               consistency={"max_best_day_fraction": 0.5, "status": "assumed"}),
    variant("synthetic_trailing"),
    variant("synthetic_static", mode="trailing_intraday", lock_at=0),
    with_rules(variant("synthetic_trailing", check="eod_only"),
               daily_loss={"amount": 1000, "action": "breach", "status": "assumed"},
               min_trading_days={"value": 3, "status": "assumed"},
               max_calendar_days={"value": 25, "status": "assumed"}),
], ids=["static_dll_consistency", "trailing_eod_lock0", "trailing_intraday", "eod_only_dll_breach_timeout"])
def test_vectorized_equals_scalar(prog):
    res = simulate_evaluation(prog, POOL, contracts=2, horizon=60, n_paths=200, seed=7, mean_block=3.0)
    idx = res["idx"]
    codes = {"active": 0, "passed": 1, "failed_mll": 2, "failed_timeout": 3}
    for path in range(idx.shape[0]):
        st = new_evaluation(prog)
        for t in range(idx.shape[1]):
            st = step_day(st, prog, POOL[idx[path, t]], 2)
        assert codes[st.status] == int(res["status"][path])
        assert abs(st.balance - float(res["balance"][path])) < 1e-9


# ------------------------------------------------------------------ vectores T1-T7

def pool_of(wins: int, losses: int, win: float = 500.0, loss: float = 500.0) -> list[DayPath]:
    return [day([0, win])] * wins + [day([0, -loss])] * losses


CASES = [
    ("T1", "synthetic_static", {}, (1, 1, 500.0), 0.4),
    ("T2", "synthetic_static", {}, (11, 9, 500.0), 0.637586),
    ("T3", "synthetic_static", {}, (9, 11, 500.0), 0.191266),
    ("T4", "synthetic_trailing", {}, (1, 1, 500.0), 0.273067),
    ("T5", "synthetic_trailing", {"lock_at": None}, (1, 1, 500.0), 0.262144),
    ("T6", "synthetic_trailing", {}, (11, 9, 500.0), 0.454480),
    ("T7", "synthetic_trailing", {}, (1, 2, 1000.0), 0.277285),
    ("T7_static", "synthetic_static", {}, (1, 2, 1000.0), 0.387582),
]


def _p_pass(name, overrides, pool_spec, n_paths):
    wins, losses, win = pool_spec
    prog = variant(name, **overrides) if overrides else load_program(PROGRAMS / f"{name}.yaml")
    res = simulate_evaluation(prog, pool_of(wins, losses, win), contracts=1, horizon=2000, n_paths=n_paths,
                              seed=2026, mean_block=1.0)
    assert res["p_active_end"] < 1e-3
    return res["p_pass"]


@pytest.mark.parametrize("case_id, name, overrides, pool_spec, expected", CASES, ids=[c[0] for c in CASES])
def test_t_vectors_fast(case_id, name, overrides, pool_spec, expected):
    assert abs(_p_pass(name, overrides, pool_spec, 20_000) - expected) <= 0.014


@pytest.mark.slow
@pytest.mark.parametrize("case_id, name, overrides, pool_spec, expected", CASES, ids=[c[0] for c in CASES])
def test_t_vectors_precise(case_id, name, overrides, pool_spec, expected):
    assert abs(_p_pass(name, overrides, pool_spec, 200_000) - expected) <= 0.004
