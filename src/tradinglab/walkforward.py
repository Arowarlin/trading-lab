"""Walk-forward y evaluación por regímenes para `lab research`.

API pública:
- `walk_forward(returns, train_len=504, test_len=126)`: recorre la matriz
  (T, N) en ventanas contiguas, elige la mejor variante en train y mide su
  comportamiento en test. Devuelve `WalkForwardResult`.
- `regime_report(returns, years=(2018, 2020, 2022))`: estadísticas de una
  serie con índice `DatetimeIndex` por régimen.
- `regime_gate(report)`: aprueba solo si todos los regímenes requeridos tienen
  datos suficientes y retorno positivo. Un régimen sin datos NO aprueba.

No depende de nada externo salvo numpy/pandas (ya presentes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ANNUALIZATION = 252
REQUIRED_REGIMES = (2018, 2020, 2022)


def _sharpe(returns: np.ndarray, periods: int = ANNUALIZATION) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    std = float(np.std(r, ddof=1))
    if not np.isfinite(std) or std <= 1e-12:
        return 0.0
    mean = float(np.mean(r))
    if not np.isfinite(mean):
        return 0.0
    return mean / std * float(np.sqrt(periods))


def _rank_pct(values: np.ndarray, idx: int) -> float:
    """Percentil 0..1 de `values[idx]` con empates promediados."""
    n = len(values)
    if n <= 1:
        return 1.0
    v = values[idx]
    less = int(np.sum(values < v))
    equal = int(np.sum(values == v))
    avg_rank = less + (equal + 1) / 2.0  # rango 1-based
    return float((avg_rank - 1.0) / (n - 1.0))


@dataclass
class WalkForwardResult:
    stitched_sharpe: float
    frac_positive: float
    efficiency: float
    median_rank_pct: float
    stability: float
    n_folds: int
    n_variants: int
    train_len: int
    test_len: int
    fold_details: list[dict] = field(default_factory=list)
    oos_returns: np.ndarray = field(repr=False, default_factory=lambda: np.empty(0))

    def to_dict(self) -> dict:
        return {
            "stitched_sharpe": self.stitched_sharpe,
            "frac_positive": self.frac_positive,
            "efficiency": self.efficiency,
            "median_rank_pct": self.median_rank_pct,
            "stability": self.stability,
            "n_folds": self.n_folds,
            "n_variants": self.n_variants,
            "train_len": self.train_len,
            "test_len": self.test_len,
        }

    def verdict(
        self,
        *,
        min_stitched_sharpe: float = 0.0,
        min_frac_positive: float = 0.5,
        min_efficiency: float = 0.3,
        min_rank_pct: float = 0.5,
        min_stability: float = 0.3,
        min_folds: int = 3,
    ) -> str:
        """Devuelve `ok` o `fallido`.

        `fallido` incluye muestra insuficiente y cualquier umbral no superado.
        Los umbrales son deliberadamente fijos; no se relajan para fabricar
        propuestas.
        """
        if self.n_folds < min_folds:
            return "fallido"
        if self.stitched_sharpe <= min_stitched_sharpe:
            return "fallido"
        if self.frac_positive < min_frac_positive:
            return "fallido"
        if self.efficiency < min_efficiency:
            return "fallido"
        if self.median_rank_pct < min_rank_pct:
            return "fallido"
        if self.stability < min_stability:
            return "fallido"
        return "ok"


def walk_forward(
    returns: np.ndarray,
    train_len: int = 504,
    test_len: int = 126,
) -> WalkForwardResult:
    """Walk-forward con ventana deslizante y selección de la mejor variante.

    `returns` es una matriz (T, N) de retornos por periodo. En cada fold se
    elige la variante con mayor Sharpe en train y se concatenan sus retornos
    de test. La eficiencia es la mediana de Sharpe(OOS)/Sharpe(IS) por fold;
    la estabilidad es la fracción de folds consecutivos que eligen la misma
    variante.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2:
        raise ValueError("returns debe ser 2-D (T, N)")
    if not np.isfinite(r).all():
        raise ValueError("returns contiene NaN/inf; limpia o rellena antes")
    t, n = r.shape
    if n < 1:
        raise ValueError("walk_forward necesita al menos 1 variante")
    if train_len < 2 or test_len < 1:
        raise ValueError("train_len debe ser >= 2 y test_len >= 1")
    if t < train_len + test_len:
        raise ValueError(
            f"muestra insuficiente: {t} filas para train={train_len} + test={test_len}"
        )

    fold_details: list[dict] = []
    oos_chunks: list[np.ndarray] = []
    efficiencies: list[float] = []
    rank_pcts: list[float] = []
    oos_sharpes: list[float] = []
    selected: list[int] = []

    start = 0
    while start + train_len + test_len <= t:
        train = r[start : start + train_len]
        test = r[start + train_len : start + train_len + test_len]
        is_perf = np.array([_sharpe(train[:, j]) for j in range(n)])
        oos_perf = np.array([_sharpe(test[:, j]) for j in range(n)])
        best = int(np.argmax(is_perf))
        oos = test[:, best]
        oos_sharpe = float(oos_perf[best])
        is_sharpe = float(is_perf[best])
        rank_pct = _rank_pct(oos_perf, best)
        efficiency = oos_sharpe / is_sharpe if is_sharpe > 1e-12 else 0.0

        oos_chunks.append(oos)
        efficiencies.append(float(efficiency))
        rank_pcts.append(rank_pct)
        oos_sharpes.append(oos_sharpe)
        selected.append(best)
        fold_details.append(
            {
                "fold": len(fold_details) + 1,
                "train_start": start,
                "test_start": start + train_len,
                "test_end": start + train_len + test_len,
                "selected": best,
                "is_sharpe": is_sharpe,
                "oos_sharpe": oos_sharpe,
                "efficiency": float(efficiency),
                "rank_pct": rank_pct,
            }
        )
        start += test_len

    stitched = np.concatenate(oos_chunks) if oos_chunks else np.empty(0)
    frac_positive = float(np.mean(np.asarray(oos_sharpes) > 0.0)) if oos_sharpes else 0.0
    median_efficiency = float(np.median(efficiencies)) if efficiencies else 0.0
    median_rank = float(np.median(rank_pcts)) if rank_pcts else 0.0
    if len(selected) > 1:
        stability = float(np.mean(np.asarray(selected[:-1]) == np.asarray(selected[1:])))
    else:
        stability = 1.0 if selected else 0.0

    return WalkForwardResult(
        stitched_sharpe=_sharpe(stitched),
        frac_positive=frac_positive,
        efficiency=median_efficiency,
        median_rank_pct=median_rank,
        stability=stability,
        n_folds=len(fold_details),
        n_variants=n,
        train_len=train_len,
        test_len=test_len,
        fold_details=fold_details,
        oos_returns=stitched,
    )


def _year_stats(returns: np.ndarray) -> dict:
    r = np.asarray(returns, dtype=float)
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    return {
        "n": int(r.size),
        "total_return": float(equity[-1] - 1.0) if r.size else 0.0,
        "sharpe": _sharpe(r),
        "max_drawdown": float(np.min(drawdown)) if r.size else 0.0,
        "positive": bool(r.size and equity[-1] > 1.0),
    }


@dataclass
class RegimeReport:
    years: dict[int, dict]
    missing: list[int]
    min_obs: int = 20

    def to_dict(self) -> dict:
        return {
            "years": {str(year): stats for year, stats in sorted(self.years.items())},
            "missing": list(self.missing),
            "min_obs": self.min_obs,
        }


@dataclass
class RegimeGateResult:
    passed: bool
    reasons: list[str]
    missing: list[int]
    report: RegimeReport = field(repr=False)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "missing": list(self.missing),
        }


def regime_report(
    returns: pd.Series,
    years: tuple[int, ...] = REQUIRED_REGIMES,
    min_obs: int = 20,
) -> RegimeReport:
    """Estadísticas por año de una serie de retornos con índice de fechas."""
    if not isinstance(returns.index, pd.DatetimeIndex):
        return RegimeReport(years={}, missing=list(years), min_obs=min_obs)

    series = pd.to_numeric(returns, errors="coerce")
    series = series.replace([np.inf, -np.inf], np.nan).dropna()
    stats: dict[int, dict] = {}
    missing: list[int] = []
    for year in years:
        chunk = series[series.index.year == year]
        if len(chunk) < min_obs:
            missing.append(year)
            continue
        stats[int(year)] = _year_stats(chunk.to_numpy(dtype=float))
    return RegimeReport(years=stats, missing=missing, min_obs=min_obs)


def regime_gate(report: RegimeReport, *, min_return: float = 0.0) -> RegimeGateResult:
    """Aprueba solo si todos los regímenes tienen datos y retorno positivo."""
    reasons: list[str] = []
    if not report.years and not report.missing:
        reasons.append("sin regímenes evaluados")
    for year in report.missing:
        reasons.append(f"sin datos suficientes en {year} (mínimo {report.min_obs})")
    for year, stats in sorted(report.years.items()):
        if float(stats.get("total_return", 0.0)) <= min_return:
            reasons.append(
                f"{year} con retorno {float(stats.get('total_return', 0.0)):.2%} "
                f"≤ {min_return:.2%}"
            )
    return RegimeGateResult(
        passed=not reasons,
        reasons=reasons,
        missing=list(report.missing),
        report=report,
    )


__all__ = [
    "ANNUALIZATION",
    "REQUIRED_REGIMES",
    "WalkForwardResult",
    "walk_forward",
    "RegimeReport",
    "RegimeGateResult",
    "regime_report",
    "regime_gate",
]
