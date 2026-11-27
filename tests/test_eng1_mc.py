"""ENG-1 D-05: Monte Carlo de operaciones y bootstrap por bloques (puertas v3)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from tradinglab.discovery import robustness


def _trades(values):
    return [SimpleNamespace(r_net=float(v)) for v in values]


def test_barajar_no_cambia_la_media_y_v3_no_lo_cuenta():
    rng = np.random.default_rng(3)
    values = rng.normal(0.0, 1.0, 120)
    values = values - values.mean() + 0.02  # media positiva (+0,02 R) pero muy incierta
    mc = robustness._mc_trades(_trades(values), paths=500, seed=1)
    assert abs(mc["shuffle_expectancy_p5"] - values.mean()) < 1e-12
    assert mc["resample_expectancy_p5"] < 0.0
    assert robustness._mc_trades_ok(mc, gates_v3=False) is True  # v2: "expectativa > 0"
    assert robustness._mc_trades_ok(mc, gates_v3=True) is False


def test_bootstrap_v3_usa_bloques_mas_largos_con_autocorrelacion():
    rng = np.random.default_rng(4)
    eps = rng.normal(0.0, 1.0, 1000)
    values = np.zeros_like(eps)
    for t in range(1, len(eps)):
        values[t] = 0.6 * values[t - 1] + eps[t]
    daily = pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)))
    old = robustness._bootstrap(daily, paths=200, seed=1)
    new = robustness._bootstrap(daily, paths=200, seed=1, auto_block=True)
    assert old["block_days"] == 5
    assert new["block_days"] > 5
