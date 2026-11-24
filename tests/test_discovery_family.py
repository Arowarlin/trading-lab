"""T23 · SPA de Hansen por familia."""

from __future__ import annotations

import numpy as np

from tradinglab.discovery import family


def test_spa_nulo_no_rechaza_en_la_mayoria_de_semillas():
    rng = np.random.default_rng(123)
    base = rng.normal(0.0, 1.0, (10, 200))
    rejected = 0
    for seed in range(100):
        result = family.spa_test(
            [row for row in base], block_size=1, reps=100, seed=seed
        )
        if result["p_value"] is not None and result["p_value"] < 0.05:
            rejected += 1
    assert rejected <= 10


def test_spa_con_ventaja_fuerte_rechaza():
    rng = np.random.default_rng(7)
    series = [rng.normal(0.0, 1.0, 300) for _ in range(9)]
    series.append(rng.normal(0.3, 1.0, 300))
    result = family.spa_test(series, block_size=1, reps=500, seed=7)
    assert result["p_value"] < 0.05


def test_family_test_sin_campanas_es_sin_datos(tmp_path):
    result = family.family_test("inexistente", db_path=tmp_path / "nope.db")
    assert result["status"] == "Sin datos"
