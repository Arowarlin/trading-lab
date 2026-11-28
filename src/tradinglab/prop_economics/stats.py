"""Calidad estadística de la ventaja: bootstrap estacionario y cota inferior μ_LCB (ORPAE §2.1) — FUT-O1."""

from __future__ import annotations

import numpy as np

from .simulate import mean_block_length, stationary_bootstrap_indices


def bootstrap_means(x: np.ndarray, *, n_boot: int = 5000, mean_block: float | None = None, seed: int = 0) -> np.ndarray:
    """Medias de ``n_boot`` réplicas del bootstrap estacionario (Politis-Romano) de la serie ``x``."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < 2:
        raise ValueError("hacen falta al menos 2 observaciones")
    block = mean_block_length(x) if mean_block is None else mean_block
    idx = stationary_bootstrap_indices(x.size, x.size, n_boot, block, seed)
    return x[idx].mean(axis=1)


def mu_lcb(x: np.ndarray, *, alpha: float = 0.05, n_boot: int = 5000, mean_block: float | None = None,
           seed: int = 0) -> float:
    """Cota inferior unilateral (1 − alpha) de la media: percentil ``alpha`` de las medias bootstrap."""
    return float(np.quantile(bootstrap_means(x, n_boot=n_boot, mean_block=mean_block, seed=seed), alpha))


def mu_interval(x: np.ndarray, *, level: float = 0.95, n_boot: int = 5000, mean_block: float | None = None,
                seed: int = 0) -> tuple[float, float, float]:
    """(media, límite inferior, límite superior) del IC bilateral por percentiles."""
    m = bootstrap_means(x, n_boot=n_boot, mean_block=mean_block, seed=seed)
    a = (1 - level) / 2
    return float(np.mean(x)), float(np.quantile(m, a)), float(np.quantile(m, 1 - a))
