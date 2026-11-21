"""Preflight de viabilidad de una campaña, sin PnL ni expectativa.

Calcula solo lo que decide si una rejilla o una población inicial puede llegar
a evaluarse: operaciones IS, operaciones por pliegue, mediana de ``cost_R`` y
tiempo medio en mercado. No calcula expectativa, no escribe en ``disc_*``, no
suma al DSR y no abre OOS-1/OOS-2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from . import campaigns, compiler, databank, dsl, fastbt, fitness, jobs, specs
from .config import load_engine_config
from .engine import candidate_strategies

MIN_FEASIBLE_PCT = 50.0


@dataclass
class FeasibilityRow:
    index: int
    strategy_hash: str
    label: str
    trades_is: int
    fold_trades: list[int]
    cost_r: float | None
    mean_bars: float
    mean_minutes: float
    feasible: bool
    reasons: list[str]


def _walk(node: Any):
    if not isinstance(node, dict):
        return
    yield node
    for item in node.get("args") or []:
        yield from _walk(item)
    for key in ("left", "right", "expr"):
        if isinstance(node.get(key), dict):
            yield from _walk(node[key])


def _label(strategy: dict[str, Any]) -> str:
    entry = strategy.get("long_entry") or {}
    parts: list[str] = []
    for node in _walk(entry):
        if node.get("kind") not in {"gt", "lt", "ge", "le"}:
            continue
        left = node.get("left") or {}
        right = node.get("right") or {}
        if left.get("kind") == "indicator" and left.get("ind") == "session_return":
            params = left.get("params") or {}
            parts.append(f"u={right.get('value')}")
            parts.append(f"fin={params.get('end')}")
        elif left.get("kind") == "indicator":
            parts.append(f"{left.get('ind')}>{right.get('value')}")
    if entry.get("kind") == "and":
        for node in entry.get("args") or []:
            if node.get("kind") == "time_between":
                parts.append(f"entrada={node.get('start')}")
            elif node.get("kind") in {"regime", "pattern"}:
                parts.append(f"filtro={node.get('regime') or node.get('pattern')}")
    stop = ((strategy.get("exit") or {}).get("stop") or {}).get("mult")
    if stop is not None:
        parts.append(f"stop={stop}")
    return " ".join(dict.fromkeys(part for part in parts if part)) or "individuo"


def _context(campaign_id: str, db_path):
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    setup = jobs.QueueSetup.from_campaign(campaign)
    bars = campaigns.load_segment(campaign_id, "is", db_path=db_path)
    from ..propfund.costs import load_profile

    try:
        profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
        cost = fastbt.cost_from_profile(profile, use_p75=setup.use_p75)
    except Exception as exc:  # noqa: BLE001 - coste ausente se informa como Sin datos
        raise campaigns.CampaignError(f"Sin datos: coste {exc}") from exc
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
    )
    prepared = fastbt.prepare(
        bars,
        cost,
        atr_windows=(setup.stop_n, setup.trail_n),
        sessions=(limits,),
    )
    return campaign, setup, bars, cost, prepared


def check(campaign_id: str, *, db_path=None) -> dict[str, Any]:
    """Devuelve la viabilidad de cada combinación/individuo inicial."""

    campaign, setup, bars, cost, prepared = _context(campaign_id, db_path)
    strategies, population, mode, template, seed = candidate_strategies(campaign)
    config = load_engine_config()
    folds = int(config.validation.folds)
    min_trades_is = int(config.validation.min_trades_is)
    min_trades_fold = int(config.validation.min_trades_fold)
    max_cost_r = float(config.fitness.cost_r_max)
    rows: list[FeasibilityRow] = []
    for index, strategy in enumerate(strategies):
        trades_is = 0
        fold_trades: list[int] = []
        cost_r: float | None = None
        mean_bars = 0.0
        reasons: list[str] = []
        gate = jobs.strategy_gate(strategy, setup)
        if gate:
            reasons.append(gate)
        else:
            try:
                model = dsl.Strategy.model_validate(strategy)
                signals = compiler.compile(model, bars)
                exit_spec = specs.exit_spec_from_strategy(model)
                base_limits = specs.run_limits_from_strategy(
                    model, setup, close_at_end=True
                )
                full = fastbt.run(
                    signals,
                    bars,
                    exit_spec,
                    cost,
                    base_limits,
                    prepared=prepared,
                )
                trades = list(full.trades)
                trades_is = len(trades)
                costs = [
                    float(trade.r_cost)
                    for trade in trades
                    if trade.r_cost is not None
                ]
                cost_r = float(np.median(costs)) if costs else None
                if trades:
                    mean_bars = float(np.mean([trade.bars_held for trade in trades]))
                for start, end in fitness.fold_bounds(len(bars), folds):
                    fold_signals = fastbt.Signals(
                        signals.long_entry,
                        signals.short_entry,
                        max(int(start), int(signals.valid_from)),
                    )
                    fold_limits = specs.run_limits_from_strategy(
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
                    fold_trades.append(len(fold_result.trades))
                max_bars = max(
                    float(fitness._session_bars(model) * 2),
                    float(model.exit.time_exit_bars or 0),
                )
                if trades_is < min_trades_is:
                    reasons.append(f"trades IS {trades_is} < {min_trades_is}")
                for fold_index, count in enumerate(fold_trades, 1):
                    if count < min_trades_fold:
                        reasons.append(
                            f"pliegue {fold_index} trades {count} < {min_trades_fold}"
                        )
                if cost_r is None:
                    reasons.append("coste_R Sin datos")
                elif cost_r > max_cost_r:
                    reasons.append(f"coste_R {cost_r:.4f} > {max_cost_r:.4f}")
                if mean_bars > max_bars:
                    reasons.append(
                        f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}"
                    )
            except Exception as exc:  # noqa: BLE001 - se informa la fila, no se aborta
                reasons.append(f"{type(exc).__name__}: {exc}")
        rows.append(
            FeasibilityRow(
                index=index,
                strategy_hash=dsl.strategy_hash(strategy),
                label=_label(strategy),
                trades_is=trades_is,
                fold_trades=fold_trades,
                cost_r=cost_r,
                mean_bars=mean_bars,
                mean_minutes=mean_bars * 5.0,
                feasible=not reasons,
                reasons=reasons,
            )
        )
    n_checked = len(rows)
    n_feasible = sum(1 for row in rows if row.feasible)
    feasible_pct = 100.0 * n_feasible / n_checked if n_checked else 0.0
    return {
        "campaign_id": campaign_id,
        "status": campaign.get("status"),
        "mode": mode,
        "template": template,
        "seed": seed,
        "population": population,
        "n_checked": n_checked,
        "n_feasible": n_feasible,
        "feasible_pct": feasible_pct,
        "passes": feasible_pct >= MIN_FEASIBLE_PCT,
        "rows": [asdict(row) for row in rows],
    }


__all__ = ["FeasibilityRow", "MIN_FEASIBLE_PCT", "check"]
