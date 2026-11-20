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
MIN_GLOBAL_SERIES = 30


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
    *,
    benchmark_sr: float | None = None,
) -> float | None:
    """Fórmula interna del DSR con todas las entradas por periodo.

    No se exporta como API pública de cálculo: las llamadas deben pasar por
    `dsr_from_returns`, que además valida las unidades. ``benchmark_sr``
    sustituye el SR0 deflactado por un umbral fijo; con 0 se obtiene el PSR
    frente a SR 0 (caso K=1).
    """
    if n_obs < 3:
        return None
    if not math.isfinite(sharpe):
        return None
    nd = NormalDist()
    if benchmark_sr is not None:
        if not math.isfinite(float(benchmark_sr)):
            return None
        sr0 = float(benchmark_sr)
    else:
        if n_trials < 2 or trial_sr_std <= 0:
            return None
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
    *,
    benchmark_sr: float | None = None,
) -> dict:
    """Calcula el DSR v2 a partir de retornos por periodo.

    `trial_srs_per_period` son los Sharpes por periodo de las demás pruebas.
    `periods_per_year` solo añade `annualized_sr` para el informe; no cambia
    el DSR. Un Sharpe por periodo mayor que 1 en valor absoluto se rechaza:
    casi siempre significa que la serie llegó anualizada. Con ``benchmark_sr``
    se calcula el PSR frente a ese umbral (0 = PSR frente a SR 0).
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
        benchmark_sr=benchmark_sr,
    )
    annualized = None
    if periods_per_year is not None:
        if float(periods_per_year) <= 0:
            raise StatsError("periods_per_year debe ser > 0")
        annualized = sr_period * math.sqrt(float(periods_per_year))
    return {
        "dsr": dsr,
        "status": "ok" if dsr is not None else "Sin datos",
        "n_trials": int(n_trials),
        "n_series": int(trial_values.size),
        "sr_period": sr_period,
        "sr0_period": (
            float(benchmark_sr)
            if benchmark_sr is not None
            else (
                trial_std
                * (
                    (1.0 - EULER_GAMMA)
                    * NormalDist().inv_cdf(1.0 - 1.0 / int(n_trials))
                    + EULER_GAMMA
                    * NormalDist().inv_cdf(1.0 - 1.0 / (int(n_trials) * math.e))
                )
                if n_trials >= 2 and trial_std > 0
                else None
            )
        ),
        "skew": skew,
        "kurt": kurt,
        "n_obs": int(values.size),
        "trial_sr_std_period": trial_std,
        "annualized_sr": annualized,
        "periods_per_year": periods_per_year,
        "benchmark_sr_period": (
            None if benchmark_sr is None else float(benchmark_sr)
        ),
        "metric_version": METRIC_VERSION,
    }


def trial_srs(series_list) -> list[float]:
    """Sharpes por periodo de una colección de series de retorno."""
    return [period_sharpe(series) for series in series_list]


def dsr_local_global(
    returns,
    local_srs_per_period,
    global_srs_per_period,
    local_n: int,
    global_n: int,
    periods_per_year: float | None = None,
    min_global_series: int = MIN_GLOBAL_SERIES,
    global_sources: dict | None = None,
    frequency: str | None = None,
) -> dict:
    """Calcula el DSR local y el global con N y dispersión coherentes.

    `local_n` es el número de variantes de la rejilla (o de la pasada actual) y
    su dispersión son esas mismas variantes. `global_n` es el contador global
    de pruebas, pero la dispersión solo se usa si hay al menos
    `min_global_series` series con retorno; si no, el global queda Sin datos.
    """
    local_values = list(local_srs_per_period or [])
    global_values = list(global_srs_per_period or [])
    local = dsr_from_returns(
        returns,
        local_values,
        local_n,
        periods_per_year=periods_per_year,
    )
    local["scope"] = "local"
    if len(global_values) < int(min_global_series):
        global_payload = {
            "dsr": None,
            "status": "Sin datos",
            "reason": (
                f"menos de {int(min_global_series)} series con retorno "
                f"({len(global_values)})"
            ),
            "metric_version": METRIC_VERSION,
            "scope": "global",
            "frequency": frequency,
            "sources": dict(global_sources or {}),
            "n_trials": int(global_n),
            "n_series": len(global_values),
        }
    else:
        global_payload = dsr_from_returns(
            returns,
            global_values,
            global_n,
            periods_per_year=periods_per_year,
        )
        global_payload["scope"] = "global"
        global_payload["frequency"] = frequency
        global_payload["sources"] = dict(global_sources or {})
    return {"local": local, "global": global_payload}


__all__ = [
    "METRIC_VERSION",
    "MIN_GLOBAL_SERIES",
    "StatsError",
    "deflated_sharpe",
    "dsr_from_returns",
    "dsr_local_global",
    "period_sharpe",
    "trial_srs",
]
