"""Validación de sobreajuste: PBO vía CSCV (Bailey, Borwein, López de Prado, Zhu).

Entrada: matriz de retornos periódicos (T filas = fechas, N columnas = variantes
de estrategia/parámetros probadas en el mismo barrido de `lab research`).

PBO = probabilidad de que la variante que gana en la muestra (IS) quede por
debajo de la mediana fuera de muestra (OOS). Cerca de 0 es bueno; cerca de 0,5
o más indica que elegir la mejor es esencialmente azar.

Solo depende de numpy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

ANNUALIZATION = 252


@dataclass
class PBOResult:
    pbo: float                      # P(logit <= 0)
    n_variants: int
    n_slices: int
    n_combinations: int
    rows_used: int
    median_logit: float
    prob_oos_loss: float            # P(OOS de la ganadora IS < 0)
    degradation_slope: float        # pendiente OOS ~ IS de la ganadora (1 = sin degradación)
    logits: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))

    def to_dict(self) -> dict:
        return {
            "pbo": self.pbo,
            "n_variants": self.n_variants,
            "n_slices": self.n_slices,
            "n_combinations": self.n_combinations,
            "rows_used": self.rows_used,
            "median_logit": self.median_logit,
            "prob_oos_loss": self.prob_oos_loss,
            "degradation_slope": self.degradation_slope,
        }

    def verdict(self, max_pbo: float = 0.30) -> str:
        if self.pbo <= max_pbo:
            return "ok"
        return "sobreajustado"


def _sharpe_from_sums(s: np.ndarray, ss: np.ndarray, n: int) -> np.ndarray:
    """Sharpe anualizado por variante a partir de suma y suma de cuadrados."""
    mean = s / n
    var = (ss - n * mean**2) / max(n - 1, 1)
    std = np.sqrt(np.maximum(var, 0.0))
    out = np.zeros_like(mean)
    ok = std > 1e-12
    out[ok] = mean[ok] / std[ok] * np.sqrt(ANNUALIZATION)
    return out


def _avg_rank(values: np.ndarray, target_idx: int) -> float:
    """Rango medio (1-based) de values[target_idx] con empates promediados."""
    v = values[target_idx]
    less = np.sum(values < v)
    equal = np.sum(values == v)
    return less + (equal + 1) / 2.0


def cscv_pbo(
    returns: np.ndarray,
    n_slices: int = 16,
    max_combinations: int | None = None,
    seed: int = 0,
) -> PBOResult:
    """Calcula PBO con Combinatorially Symmetric Cross-Validation.

    returns: array (T, N) de retornos por periodo (una columna por variante).
    n_slices: número de bloques temporales contiguos (par). 16 -> 12.870
        combinaciones; es rápido porque se usan sumas por bloque.
    max_combinations: si se indica y hay más combinaciones, se muestrean al azar.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2:
        raise ValueError("returns debe ser 2-D (T, N)")
    if not np.isfinite(r).all():
        raise ValueError("returns contiene NaN/inf; limpia o rellena antes")
    t, n = r.shape
    if n < 2:
        raise ValueError("PBO necesita al menos 2 variantes")
    if n_slices < 4 or n_slices % 2:
        raise ValueError("n_slices debe ser par y >= 4")
    per = t // n_slices
    if per < 5:
        raise ValueError(
            f"muestra insuficiente: {t} filas para {n_slices} bloques "
            f"(mínimo 5 filas por bloque)"
        )
    rows = per * n_slices
    r = r[t - rows:]  # descarta el resto más antiguo, conserva lo reciente
    blocks = r.reshape(n_slices, per, n)
    s = blocks.sum(axis=1)               # (S, N)
    ss = (blocks**2).sum(axis=1)         # (S, N)

    half = n_slices // 2
    all_combos = list(combinations(range(n_slices), half))
    if max_combinations and len(all_combos) > max_combinations:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(all_combos), size=max_combinations, replace=False)
        combos = [all_combos[i] for i in idx]
    else:
        combos = all_combos

    logits = np.empty(len(combos))
    is_best_perf = np.empty(len(combos))
    oos_best_perf = np.empty(len(combos))
    n_rows_half = per * half

    for k, combo in enumerate(combos):
        is_mask = np.zeros(n_slices, dtype=bool)
        is_mask[list(combo)] = True
        oos_mask = ~is_mask
        is_perf = _sharpe_from_sums(s[is_mask].sum(0), ss[is_mask].sum(0), n_rows_half)
        oos_perf = _sharpe_from_sums(s[oos_mask].sum(0), ss[oos_mask].sum(0), n_rows_half)
        best = int(np.argmax(is_perf))
        omega = _avg_rank(oos_perf, best) / (n + 1)
        logits[k] = np.log(omega / (1.0 - omega))
        is_best_perf[k] = is_perf[best]
        oos_best_perf[k] = oos_perf[best]

    pbo = float(np.mean(logits <= 0.0))
    if np.ptp(is_best_perf) > 1e-12:
        slope = float(np.polyfit(is_best_perf, oos_best_perf, 1)[0])
    else:
        slope = float("nan")
    return PBOResult(
        pbo=pbo,
        n_variants=n,
        n_slices=n_slices,
        n_combinations=len(combos),
        rows_used=rows,
        median_logit=float(np.median(logits)),
        prob_oos_loss=float(np.mean(oos_best_perf < 0.0)),
        degradation_slope=slope,
        logits=logits,
    )


def returns_matrix(series_by_variant: dict[str, "np.ndarray"]) -> tuple[np.ndarray, list[str]]:
    """Alinea series de retornos (misma longitud/fechas) en una matriz (T, N).

    Pensado para `research.py`: pasa el retorno diario neto de cada variante
    ya calculado por el backtester. Todas deben cubrir las mismas fechas.
    """
    names = list(series_by_variant)
    lengths = {len(v) for v in series_by_variant.values()}
    if len(lengths) != 1:
        raise ValueError(f"las series tienen longitudes distintas: {sorted(lengths)}")
    mat = np.column_stack([np.asarray(series_by_variant[k], float) for k in names])
    return mat, names


__all__ = ["ANNUALIZATION", "PBOResult", "cscv_pbo", "returns_matrix"]
