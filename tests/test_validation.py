from __future__ import annotations

import numpy as np
import pytest

from tradinglab.validation import cscv_pbo, returns_matrix


def _noise(t=1600, n=40, seed=1):
    return np.random.default_rng(seed).normal(0, 0.01, size=(t, n))


def test_pure_noise_pbo_is_near_half_on_average():
    # Sin edge, el PBO de una sola muestra es muy ruidoso (0,1-0,7); solo el
    # promedio entre muestras es ~0,5. Se usan combinaciones muestreadas para
    # que el test sea rápido.
    pbos = [
        cscv_pbo(_noise(seed=s), n_slices=16, max_combinations=2000, seed=0).pbo
        for s in range(1, 13)
    ]
    assert 0.3 <= float(np.mean(pbos)) <= 0.65


def test_all_combinations_count():
    res = cscv_pbo(_noise(n=10), n_slices=16)
    assert res.n_combinations == 12870


def test_real_edge_gives_low_pbo():
    r = _noise(seed=2)
    r[:, 7] += 0.002  # una variante con edge persistente (~Sharpe 3)
    res = cscv_pbo(r, n_slices=16)
    assert res.pbo < 0.1
    assert res.verdict() == "ok"


def test_overfit_selection_is_flagged():
    # Cada variante gana solo en un tramo distinto y pierde en el resto:
    # lo que gana IS no se sostiene OOS.
    t, n = 1600, 16
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.01, size=(t, n))
    seg = t // n
    for j in range(n):
        r[j * seg:(j + 1) * seg, j] += 0.01
        mask = np.ones(t, bool)
        mask[j * seg:(j + 1) * seg] = False
        r[mask, j] -= 0.0005
    res = cscv_pbo(r, n_slices=16)
    assert res.pbo > 0.5
    assert res.verdict() == "sobreajustado"


def test_max_combinations_samples_and_is_reproducible():
    r = _noise()
    a = cscv_pbo(r, n_slices=16, max_combinations=500, seed=7)
    b = cscv_pbo(r, n_slices=16, max_combinations=500, seed=7)
    assert a.n_combinations == 500
    assert a.pbo == b.pbo


def test_drops_oldest_remainder_rows():
    res = cscv_pbo(_noise(t=1605), n_slices=16, max_combinations=200)
    assert res.rows_used == 1600


@pytest.mark.parametrize("kwargs", [{"n_slices": 15}, {"n_slices": 2}])
def test_invalid_slices(kwargs):
    with pytest.raises(ValueError):
        cscv_pbo(_noise(), **kwargs)


def test_rejects_short_sample_nan_and_single_variant():
    with pytest.raises(ValueError, match="insuficiente"):
        cscv_pbo(_noise(t=50), n_slices=16)
    bad = _noise()
    bad[3, 3] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        cscv_pbo(bad)
    with pytest.raises(ValueError, match="al menos 2"):
        cscv_pbo(_noise(n=1))


def test_returns_matrix_alignment():
    mat, names = returns_matrix({"a": np.zeros(10), "b": np.ones(10)})
    assert mat.shape == (10, 2) and names == ["a", "b"]
    with pytest.raises(ValueError):
        returns_matrix({"a": np.zeros(10), "b": np.ones(9)})
