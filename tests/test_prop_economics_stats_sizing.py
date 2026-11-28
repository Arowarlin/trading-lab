"""FUT-O1 (μ_LCB por bootstrap estacionario) y FUT-O2 (Kelly y Optimal f como diagnóstico)."""

from __future__ import annotations

import numpy as np
import pytest

from tradinglab.prop_economics.sizing_diag import (
    growth_retained,
    kelly_binary,
    kelly_continuous,
    kelly_under_uncertainty,
    log_growth,
    optimal_f,
)
from tradinglab.prop_economics.stats import mu_interval, mu_lcb


def _ar1(n: int, phi: float, mean: float, rng) -> np.ndarray:
    e = rng.normal(0, 1, n)
    x = np.empty(n)
    x[0] = e[0] / np.sqrt(1 - phi**2)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x + mean


@pytest.mark.slow
def test_o1_coverage_ar1():
    rng = np.random.default_rng(42)
    hits = 0
    reps = 300
    for k in range(reps):
        x = _ar1(400, 0.5, 0.1, rng)
        _, lo, hi = mu_interval(x, level=0.95, n_boot=400, seed=k)
        hits += lo <= 0.1 <= hi
    assert 0.88 <= hits / reps <= 0.99


def test_o1_lcb_below_mean_and_deterministic():
    x = np.random.default_rng(1).normal(0.2, 1.0, 300)
    a = mu_lcb(x, n_boot=800, seed=3)
    assert a < x.mean()
    assert a == mu_lcb(x, n_boot=800, seed=3)
    with pytest.raises(ValueError):
        mu_lcb(np.array([1.0]))


def test_o2_kelly_binary_value():
    assert kelly_binary(0.452, 1.45, 1.05) == pytest.approx(0.0552, abs=1e-4)


def test_o2_kelly_identities():
    assert kelly_continuous(0.08, 1.2) == pytest.approx(0.08 / 1.44)
    assert growth_retained(0.5) == pytest.approx(0.75)
    assert growth_retained(0.25) == pytest.approx(0.4375)
    assert growth_retained(2.0) == pytest.approx(0.0)        # 2× Kelly: crecimiento nulo


def test_o2_optimal_f_on_binary_matches_kelly_scaled():
    # resultados ±: +1,45 R con p y −1,05 R con 1−p en proporciones exactas
    r = np.array([1.45] * 452 + [-1.05] * 548)
    f, risk_frac = optimal_f(r)
    # optimal_f da la fracción por 1 R; Kelly binario da la fracción que se PIERDE en una perdedora (1,05 R)
    assert risk_frac == pytest.approx(0.452 / 1.05 - 0.548 / 1.45, abs=5e-4)          # óptimo analítico por R
    assert risk_frac * 1.05 == pytest.approx(kelly_binary(0.452, 1.45, 1.05), abs=5e-4)
    assert log_growth(risk_frac, r) > log_growth(2.2 * risk_frac, r)


def test_o2_uncertainty_shows_overbetting():
    d = kelly_under_uncertainty(0.452, 0.43, 1.45, 1.05)
    assert d["kelly_point"] == pytest.approx(0.0552, abs=1e-4)
    assert d["kelly_lcb"] == pytest.approx(0.0, abs=1e-12) or d["kelly_lcb"] < d["kelly_point"]
    assert d["overbet_ratio"] > 1
