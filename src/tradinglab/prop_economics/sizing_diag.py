"""Kelly, Kelly fraccionario y Optimal f como DIAGNÓSTICO (ORPAE §1; risk/01 §2.2) — FUT-O2.

No dimensionan nada por sí solos: con reglas de prop firm (colchón fijo, día mínimo, tope por retiro) el
tamaño lo decide la simulación del programa (FUT-O4). Kelly sirve para no pasarse: más de 2× Kelly da
crecimiento esperado ≤ 0.
"""

from __future__ import annotations

import numpy as np


def kelly_binary(p: float, win: float, loss: float) -> float:
    """Kelly con dos resultados: ``f* = p − (1 − p)·L/W`` (W y L netos, en R).

    Es la fracción del capital que se PIERDE en una operación perdedora. La fracción por 1 R es
    ``f*/L = p/L − (1 − p)/W`` (la que devuelve ``optimal_f`` como segunda cifra).
    """
    if not 0 < p < 1 or win <= 0 or loss <= 0:
        raise ValueError("p en (0, 1) y W, L > 0")
    return p - (1 - p) * loss / win


def kelly_continuous(mu: float, sigma: float) -> float:
    """Aproximación continua ``f* = μ/σ²``."""
    if sigma <= 0:
        raise ValueError("sigma > 0")
    return mu / sigma**2


def growth_retained(c: float) -> float:
    """Fracción del crecimiento de Kelly que conserva apostar ``c``·Kelly: ``c·(2 − c)``."""
    return c * (2 - c)


def log_growth(f: float, outcomes_r: np.ndarray) -> float:
    """Crecimiento logarítmico medio arriesgando la fracción ``f`` del capital por unidad de R."""
    r = np.asarray(outcomes_r, dtype=np.float64)
    base = 1 + f * r
    if np.any(base <= 0):
        return -np.inf
    return float(np.mean(np.log(base)))


def optimal_f(outcomes_r: np.ndarray, *, grid: int = 2001) -> tuple[float, float]:
    """Optimal f de Vince: maximiza el TWR con resultados escalados por la peor pérdida.

    Devuelve ``(f, fracción_de_riesgo)`` donde la fracción es ``f / |peor pérdida|`` en R.
    """
    r = np.asarray(outcomes_r, dtype=np.float64)
    worst = r.min()
    if worst >= 0:
        raise ValueError("sin pérdidas no hay optimal f")
    fs = np.linspace(0.0, 0.999, grid)
    hpr = 1 + fs[:, None] * (r[None, :] / -worst)
    with np.errstate(divide="ignore", invalid="ignore"):
        twr = np.where((hpr > 0).all(axis=1), np.log(np.clip(hpr, 1e-300, None)).sum(axis=1), -np.inf)
    best = float(fs[int(np.argmax(twr))])
    return best, best / -worst


def kelly_under_uncertainty(p_hat: float, p_lcb: float, win: float, loss: float) -> dict:
    """Kelly con la estimación puntual y con la cota inferior: la diferencia mide el riesgo de sobreapostar."""
    full = kelly_binary(p_hat, win, loss)
    lcb = kelly_binary(p_lcb, win, loss)
    return {"kelly_point": full, "kelly_lcb": max(0.0, lcb), "half_kelly_lcb": max(0.0, lcb) / 2,
            "overbet_ratio": (full / lcb) if lcb > 0 else float("inf")}
