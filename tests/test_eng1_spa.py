"""ENG-1 D-04: SPA de Hansen studentizado, bloque automático y alineación por fecha.

Con ruido autocorrelacionado (AR(1), phi = 0,3) la versión anterior rechazaba
H0 ~29 % de las veces (Worker D); un test al 5 % debe rechazar ~5 %.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.discovery import family


def _ar1(rng, n, models, phi=0.3):
    eps = rng.normal(0.0, 1.0, (n, models))
    out = np.zeros_like(eps)
    for t in range(1, n):
        out[t] = phi * out[t - 1] + eps[t]
    return out


def test_tamano_correcto_con_autocorrelacion():
    rejected = 0
    trials = 60
    for seed in range(trials):
        rng = np.random.default_rng(1000 + seed)
        data = _ar1(rng, 400, 10)
        result = family.spa_test([data[:, j] for j in range(10)], reps=200, seed=seed)
        rejected += result["p_value"] < 0.05
    assert rejected <= 9  # <= 15 % (esperado ~5 %); la versión anterior daba ~29 %


def test_detecta_una_ventaja_clara():
    rng = np.random.default_rng(7)
    data = _ar1(rng, 600, 9)
    edge = rng.normal(0.25, 1.0, 600)
    result = family.spa_test([data[:, j] for j in range(9)] + [edge], reps=500, seed=7)
    assert result["p_value"] < 0.05
    assert result["method"] == "hansen_spa_studentized"


def test_alinea_por_fecha_y_no_por_posicion():
    days = pd.bdate_range("2024-01-01", periods=30)
    a = [1.0] * 30
    b = [2.0] * 10  # solo los 10 últimos días
    matrix = family._aligned([a, b], [list(days), list(days[-10:])])
    assert matrix.shape == (30, 2)
    assert matrix[:20, 1].tolist() == [0.0] * 20 and matrix[20:, 1].tolist() == [2.0] * 10
