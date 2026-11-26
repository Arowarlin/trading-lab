"""Fitness multiobjetivo sobre IS con walk-forward anclado de 4 pliegues.

El GA solo ve IS. Cada pliegue se evalúa con estado nuevo (sin posición,
cooldown ni contador diario heredados): la estrategia está congelada y cada
operación pertenece al pliegue de su entrada. El objetivo 5 usa la sensibilidad
+1 punto del motor de métricas.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import compiler, dsl, fastbt, metrics
from .config import load_engine_config
from .specs import exit_spec_from_strategy, run_limits_from_strategy, time_exit_bars
from .timeframes import bars_in_window, timeframe_minutes

TIMEFRAME_MINUTES = {
    tf: timeframe_minutes(tf)
    for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
}


def _walk(expr: dsl.Expr | None):
    if expr is None:
        return
    yield expr
    for item in expr.args:
        yield from _walk(item)
    yield from _walk(expr.left)
    yield from _walk(expr.right)
    yield from _walk(expr.expr)


def complexity(strategy: dsl.Strategy) -> int:
    nodes = dsl.count_nodes(strategy)
    params = 0
    for expr in list(_walk(strategy.long_entry)) + list(_walk(strategy.short_entry)):
        params += len(expr.params)
        params += 1 if expr.n is not None else 0
        params += 1 if expr.lookback is not None else 0
    return int(nodes + params + 2)


def _session_bars(strategy: dsl.Strategy) -> int:
    return bars_in_window(
        strategy.session.start,
        strategy.session.end,
        strategy.timeframe,
    )


def max_holding_bars(strategy: dsl.Strategy) -> float:
    """Cota estructural del tiempo en mercado permitido por la plantilla."""

    limit = max(
        float(_session_bars(strategy) * 2),
        float(time_exit_bars(strategy) or 0),
    )
    entry = strategy.long_entry
    if entry is not None and entry.kind == "month_turn":
        # La salida es un día del mes siguiente, no un número fijo de velas:
        # el hueco puede incluir fin de semana y festivos. No es un umbral de
        # optimización, solo la cota estructural de la ventana N + M.
        limit = max(limit, float((entry.n or 1) + (entry.m or 2) + 5))
    return limit


def fold_bounds(length: int, folds: int) -> list[tuple[int, int]]:
    if folds < 1:
        raise ValueError("folds debe ser >= 1")
    if length < folds + 1:
        raise ValueError("Sin datos: no hay barras para los pliegues")
    edges = [int(k * length / (folds + 1)) for k in range(folds + 2)]
    bounds = []
    for k in range(1, folds + 1):
        start = edges[k]
        end = edges[k + 1] - 1
        if end < start:
            raise ValueError("Sin datos: pliegue vacío")
        bounds.append((start, end))
    return bounds


def _fold_row(
    result: fastbt.FastResult,
    start: int,
    end: int,
    bars: pd.DataFrame,
    *,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = metrics if metrics is not None else result.metrics
    return {
        "start_index": int(start),
        "end_index": int(end),
        "start": bars.index[start].isoformat(),
        "end": bars.index[end].isoformat(),
        "trades": int(data.get("trades") or 0),
        "expectancy_r": data.get("expectancy_r"),
        "profit_factor": data.get("profit_factor"),
        "max_dd_r": data.get("max_dd_r"),
    }


def _median(values: Iterable[float | None]) -> float:
    clean = [float(value) for value in values if value is not None]
    return float(np.median(clean)) if clean else 0.0


def evaluate(
    strategy: dsl.Strategy | dict,
    bars: pd.DataFrame,
    cost,
    setup,
    prepared,
    *,
    cache=None,
    cost_r_max: float | None = None,
    cost_book=None,
    campaign_id: str = "",
    drift_simulations: int = 0,
    drift_percentile_min: float = 90.0,
    approved: bool = False,
) -> dict[str, Any]:
    """Evalúa una estrategia congelada en IS y devuelve el vector de fitness."""

    from .guard import require_approved

    require_approved(campaign_id, approved=approved, action="fitness")

    model = (
        strategy
        if isinstance(strategy, dsl.Strategy)
        else dsl.Strategy.model_validate(strategy)
    )
    config = load_engine_config()
    validation = config.validation.for_timeframe(model.timeframe)
    folds = int(validation.folds)
    max_cost_r = (
        float(config.fitness.cost_r_max) if cost_r_max is None else float(cost_r_max)
    )
    signals = compiler.compile(model, bars, cache=cache)
    exit_spec = exit_spec_from_strategy(model)
    base_limits = run_limits_from_strategy(model, setup, close_at_end=True)
    full = fastbt.run(
        signals,
        bars,
        exit_spec,
        cost,
        base_limits,
        prepared=prepared,
    )
    applied = None
    full_metrics = full.metrics
    full_daily = full.daily_r
    cost_info: dict[str, Any] = {}
    if cost_book is not None:
        from .costs import apply_result

        applied, full_metrics = apply_result(
            cost_book,
            full,
            session_tz=base_limits.session_tz,
            point=float(setup.point),
            max_cost_r=max_cost_r,
        )
        full_daily = applied.daily_r
        cost_info = {
            "cost_by_account": full_metrics.get("cost_by_account"),
            "worst_account": full_metrics.get("worst_account"),
            "worst_share": full_metrics.get("worst_share"),
            "best_account": full_metrics.get("best_account"),
            "best_share": full_metrics.get("best_share"),
            "selected_account": full_metrics.get("selected_account"),
            "selected_share": full_metrics.get("selected_share"),
            "cost_viable_by_account": full_metrics.get("cost_viable_by_account"),
            "cost_accounts": full_metrics.get("cost_accounts"),
            "cost_mode": full_metrics.get("cost_mode"),
            "slippage_assumption": full_metrics.get("slippage_assumption"),
        }

    fold_rows: list[dict[str, Any]] = []
    for start, end in fold_bounds(len(bars), folds):
        fold_signals = fastbt.Signals(
            signals.long_entry,
            signals.short_entry,
            max(int(start), int(signals.valid_from)),
            exit_index=signals.exit_index,
        )
        fold_limits = run_limits_from_strategy(
            model, setup, end_index=end, close_at_end=True
        )
        fold_result = fastbt.run(
            fold_signals,
            bars,
            exit_spec,
            cost,
            fold_limits,
            prepared=prepared,
        )
        if cost_book is not None:
            from .costs import apply_result

            _fold_applied, fold_metrics = apply_result(
                cost_book,
                fold_result,
                session_tz=fold_limits.session_tz,
                point=float(setup.point),
            )
            fold_rows.append(
                _fold_row(fold_result, start, end, bars, metrics=fold_metrics)
            )
        else:
            fold_rows.append(_fold_row(fold_result, start, end, bars))

    fold_expectancy = [row["expectancy_r"] for row in fold_rows]
    median_expectancy = _median(fold_expectancy)
    positive = [value for value in fold_expectancy if value is not None and value > 0]
    positive_fraction = len(positive) / len(fold_rows) if fold_rows else 0.0
    clean = [float(value) for value in fold_expectancy if value is not None]
    dispersion = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    stability = float(positive_fraction - 0.25 * min(dispersion, 2.0))
    worst_dd = max(
        (abs(float(row["max_dd_r"] or 0.0)) for row in fold_rows), default=0.0
    )
    node_count = complexity(model)

    trades = applied.trades if applied is not None else full.trades
    cost_values = [float(trade.r_cost) for trade in trades if trade.r_cost is not None]
    cost_r = (
        float(np.median(cost_values))
        if cost_values
        else full_metrics.get("cost_r")
    )
    base_expectancy = full_metrics.get("expectancy_r")
    plus, _delta = metrics.cost_sensitivity(
        trades, float(setup.point)
    )
    cost_drop = (
        max(0.0, float(base_expectancy) - float(plus))
        if base_expectancy is not None and plus is not None
        else 0.0
    )

    violations: list[str] = []
    if len(trades) < int(validation.min_trades_is):
        violations.append(
            f"trades IS {len(trades)} < {validation.min_trades_is}"
        )
    for row in fold_rows:
        if int(row["trades"]) < int(validation.min_trades_fold):
            violations.append(
                f"pliegue {row['start']} trades {row['trades']} < "
                f"{validation.min_trades_fold}"
            )
    concentration = full_metrics.get("concentration")
    if concentration is None or float(concentration) > 0.20:
        violations.append(f"concentración {concentration} > 0,20")
    if cost_r is None:
        violations.append("coste_R Sin datos")
    elif cost_r > max_cost_r:
        violations.append(f"coste_R {cost_r:.4f} > {max_cost_r:.4f}")
    mean_bars = (
        float(np.mean([trade.bars_held for trade in trades])) if trades else 0.0
    )
    max_bars = max_holding_bars(model)
    if mean_bars > max_bars:
        violations.append(f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}")

    fitness = [
        float(median_expectancy),
        float(stability),
        -float(worst_dd),
        -float(node_count),
        -float(cost_drop),
    ]
    raw_expectancy = full_metrics.get("gross_expectancy_r")
    raws = {
        "expectancy_r": median_expectancy,
        "positive_fraction": positive_fraction,
        "dispersion": dispersion,
        "stability": stability,
        "worst_dd_r": worst_dd,
        "complexity": node_count,
        "cost_r": cost_r,
        "cost_drop": cost_drop,
        "mean_bars": mean_bars,
        "concentration": concentration,
        "raw_expectancy_r": raw_expectancy,
        "raw_total_r": full_metrics.get("gross_total_r"),
    }
    metrics_payload = {
        "fitness": fitness,
        "raw": raws,
        "raw_expectancy_r": raw_expectancy,
        "raw_total_r": full_metrics.get("gross_total_r"),
        "folds": fold_rows,
        "violations": violations,
        "cost_r": cost_r,
        "complexity": node_count,
        "is": dict(full_metrics),
    }
    drift_info: dict[str, Any] | None = None
    if int(drift_simulations) > 0:
        try:
            from . import drift as drift_control

            drift_info = drift_control.evaluate(
                bars,
                exit_spec,
                base_limits,
                full,
                cost=cost,
                prepared=prepared,
                campaign_id=campaign_id,
                simulations=int(drift_simulations),
                percentile_min=float(drift_percentile_min),
                approved=approved,
            )
        except Exception as exc:  # noqa: BLE001 - el control no tumba el job
            drift_info = {
                "percentile": None,
                "simulations": int(drift_simulations),
                "percentile_min": float(drift_percentile_min),
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        metrics_payload["drift"] = drift_info
    metrics_payload.update(cost_info)
    return {
        "strategy_hash": dsl.strategy_hash(model),
        "fitness": fitness,
        "feasible": not violations,
        "violations": violations,
        "cost_r": cost_r,
        "complexity": node_count,
        "folds": fold_rows,
        "daily_returns": full_daily,
        "trades_count": len(trades),
        "metrics": metrics_payload,
        "drift": drift_info,
    }


def _greedy_clusters(corr: np.ndarray, threshold: float) -> int:
    clusters: list[list[int]] = []
    for index in range(len(corr)):
        best = None
        best_value = -2.0
        for cluster_index, members in enumerate(clusters):
            value = float(np.mean([corr[index, member] for member in members]))
            if value > best_value:
                best_value = value
                best = cluster_index
        if best is not None and best_value >= threshold:
            clusters[best].append(index)
        else:
            clusters.append([index])
    return len(clusters)


def effective_trials(
    series: Iterable[pd.Series | Iterable[float]],
    *,
    threshold: float = 0.7,
) -> int:
    """Clústeres de retornos diarios (average linkage jerárquico)."""

    clean = []
    for index, values in enumerate(series):
        if isinstance(values, pd.Series):
            if len(values) >= 2:
                clean.append(values.rename(index))
        else:
            array = np.asarray(list(values), dtype=float)
            if array.size >= 2:
                clean.append(pd.Series(array, name=index))
    if len(clean) < 2:
        return len(clean)
    frame = pd.concat(clean, axis=1, sort=False).fillna(0.0)
    corr = frame.corr().fillna(0.0).to_numpy(dtype=float).copy()
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)
    try:
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform

        distance = np.clip(1.0 - corr, 0.0, 2.0)
        np.fill_diagonal(distance, 0.0)
        condensed = squareform(distance, checks=False)
        tree = linkage(condensed, method="average")
        labels = fcluster(tree, t=1.0 - float(threshold), criterion="distance")
        return int(len(set(labels.tolist())))
    except ImportError:  # pragma: no cover - scipy ya está instalado
        return int(_greedy_clusters(corr, float(threshold)))


__all__ = [
    "complexity",
    "effective_trials",
    "evaluate",
    "fold_bounds",
]
