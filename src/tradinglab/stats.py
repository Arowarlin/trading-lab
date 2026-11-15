"""Estadística inferencial compartida.

El Deflated Sharpe Ratio (Bailey & López de Prado, 2014) exige que el Sharpe,
su dispersión entre pruebas y ``n_obs`` estén en la **misma unidad temporal**.
Este módulo calcula siempre por periodo. `periods_per_year` solo se usa para
mostrar el Sharpe anualizado en informes; nunca entra en el DSR.
"""

from __future__ import annotations

import math
from statistics import NormalDist, pstdev

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329
METRIC_VERSION = "dsr_v2"


class StatsError(ValueError):
    """Entrada estadística inválida o en unidades incompatibles."""


def _returns_array(returns) -> np.ndarray:
    try:
        values = np.asarray(returns, dtype=float)
    except (TypeError, ValueError) as exc:
        raise StatsError("returns no es una serie numérica") from exc
    if values.ndim != 1:
        raise StatsError("returns debe ser una serie 1-D")
    if values.size == 0:
        raise StatsError("returns está vacío")
    if not np.isfinite(values).all():
        raise StatsError("returns contiene NaN/inf")
    return values


def period_sharpe(returns) -> float:
    """Sharpe por periodo, sin anualizar."""
    values = _returns_array(returns)
    if values.size < 2:
        return 0.0
    std = float(values.std(ddof=1))
    return float(values.mean() / std) if std > 1e-12 else 0.0


def _moments(returns: np.ndarray) -> tuple[float, float]:
    """Asimetría y curtosis **no excesiva** (la normal vale 3)."""
    if returns.size < 3:
        return 0.0, 3.0
    series = pd.Series(returns)
    skew = float(series.skew())
    kurt_excess = float(series.kurt())
    if not math.isfinite(skew):
        skew = 0.0
    if not math.isfinite(kurt_excess):
        kurt_excess = 0.0
    return skew, kurt_excess + 3.0


def deflated_sharpe(
    sharpe: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
    trial_sr_std: float,
    n_trials: int,
) -> float | None:
    """Fórmula interna del DSR con todas las entradas por periodo.

    No se exporta como API pública de cálculo: las llamadas deben pasar por
    `dsr_from_returns`, que además valida las unidades.
    """
    if n_trials < 2 or n_obs < 3 or trial_sr_std <= 0:
        return None
    if not math.isfinite(sharpe):
        return None
    nd = NormalDist()
    sr0 = trial_sr_std * (
        (1.0 - EULER_GAMMA) * nd.inv_cdf(1.0 - 1.0 / n_trials)
        + EULER_GAMMA * nd.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    )
    denom = 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe
    if denom <= 0:
        return None
    z = (sharpe - sr0) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return float(nd.cdf(z))


def dsr_from_returns(
    returns,
    trial_srs_per_period,
    n_trials: int,
    periods_per_year: float | None = None,
) -> dict:
    """Calcula el DSR v2 a partir de retornos por periodo.

    `trial_srs_per_period` son los Sharpes por periodo de las demás pruebas.
    `periods_per_year` solo añade `annualized_sr` para el informe; no cambia
    el DSR. Un Sharpe por periodo mayor que 1 en valor absoluto se rechaza:
    casi siempre significa que la serie llegó anualizada.
    """
    values = _returns_array(returns)
    sr_period = period_sharpe(values)
    if abs(sr_period) > 1.0:
        raise StatsError(
            f"Sharpe por periodo {sr_period:.4f} fuera de rango: "
            "¿la serie llegó anualizada?"
        )

    trial_values = np.asarray(trial_srs_per_period or [], dtype=float)
    if trial_values.ndim != 1:
        raise StatsError("trial_srs_per_period debe ser una lista 1-D")
    if trial_values.size and not np.isfinite(trial_values).all():
        raise StatsError("trial_srs_per_period contiene NaN/inf")
    if trial_values.size and np.any(np.abs(trial_values) > 1.0):
        raise StatsError(
            "trial_srs_per_period tiene un Sharpe por periodo > 1: "
            "las pruebas llegaron anualizadas"
        )

    skew, kurt = _moments(values)
    trial_std = float(pstdev(trial_values)) if trial_values.size > 1 else 0.0
    dsr = deflated_sharpe(
        sr_period,
        int(values.size),
        skew,
        kurt,
        trial_std,
        int(n_trials),
    )
    annualized = None
    if periods_per_year is not None:
        if float(periods_per_year) <= 0:
            raise StatsError("periods_per_year debe ser > 0")
        annualized = sr_period * math.sqrt(float(periods_per_year))
    return {
        "dsr": dsr,
        "sr_period": sr_period,
        "sr0_period": (
            trial_std
            * (
                (1.0 - EULER_GAMMA)
                * NormalDist().inv_cdf(1.0 - 1.0 / int(n_trials))
                + EULER_GAMMA
                * NormalDist().inv_cdf(1.0 - 1.0 / (int(n_trials) * math.e))
            )
            if n_trials >= 2 and trial_std > 0
            else None
        ),
        "skew": skew,
        "kurt": kurt,
        "n_obs": int(values.size),
        "trial_sr_std_period": trial_std,
        "annualized_sr": annualized,
        "periods_per_year": periods_per_year,
        "metric_version": METRIC_VERSION,
    }


__all__ = [
    "METRIC_VERSION",
    "StatsError",
    "deflated_sharpe",
    "dsr_from_returns",
    "period_sharpe",
]
