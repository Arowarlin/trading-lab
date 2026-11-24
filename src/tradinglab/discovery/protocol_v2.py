"""Protocolo v2: LCB de desarrollo y holdout único con consistencia (T22)."""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
from scipy.stats import t as t_dist

T_HOLDOUT = 1.6448536269514722


def _clean(values: Iterable[float]) -> np.ndarray:
    array = np.asarray([float(value) for value in values], dtype=float)
    return array[np.isfinite(array)]


def lcb_dev(values: Iterable[float], *, confidence: float = 0.95) -> dict[str, Any]:
    """Cota inferior de la media en desarrollo: x̄ − t·s/√n."""

    array = _clean(values)
    n = int(len(array))
    if n < 2:
        return {"n": n, "mean": None, "sd": None, "lcb": None, "t": None}
    mean = float(array.mean())
    sd = float(array.std(ddof=1))
    critical = float(t_dist.ppf(confidence, n - 1))
    standard_error = sd / math.sqrt(n)
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "t": critical,
        "se": standard_error,
        "lcb": mean - critical * standard_error,
    }


def holdout_decision(
    values: Iterable[float],
    lcb_development: float,
) -> dict[str, Any]:
    """t_h ≥ 1,645 y x̄_h ≥ LCB_dev − 2·s_h/√n_h."""

    array = _clean(values)
    n = int(len(array))
    if n < 2:
        return {
            "approved": False,
            "n": n,
            "mean": None,
            "sd": None,
            "t": None,
            "threshold": None,
            "reason": "Sin datos: n holdout < 2",
        }
    mean = float(array.mean())
    sd = float(array.std(ddof=1))
    standard_error = sd / math.sqrt(n)
    t_value = mean / standard_error if standard_error > 0.0 else 0.0
    threshold = float(lcb_development) - 2.0 * standard_error
    approved = bool(
        t_value >= T_HOLDOUT and mean >= threshold
    )
    return {
        "approved": approved,
        "n": n,
        "mean": mean,
        "sd": sd,
        "se": standard_error,
        "t": float(t_value),
        "threshold": threshold,
        "t_min": T_HOLDOUT,
        "reason": (
            "holdout ok"
            if approved
            else (
                f"t={t_value:.3f} < {T_HOLDOUT:.3f}"
                if t_value < T_HOLDOUT
                else f"media {mean:.4f} < LCB_dev − 2se ({threshold:.4f})"
            )
        ),
    }


__all__ = ["T_HOLDOUT", "holdout_decision", "lcb_dev"]
