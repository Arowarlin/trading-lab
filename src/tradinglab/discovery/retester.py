"""Retester de una estrategia congelada: costes ×1,5/×2 y slippage +1/+2.

Solo IS+OOS-1. La evaluación en otros instrumentos se marca ``transfer`` y es
informativa: nunca cuenta como validación.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from . import compiler, dsl, fastbt
from .specs import exit_spec_from_strategy, run_limits_from_strategy


def _scenario_panel(
    panel: fastbt.CostPanel,
    cost: Any,
    bars: pd.DataFrame,
    *,
    factor: float = 1.0,
    slippage_points: float = 0.0,
) -> fastbt.CostPanel:
    entry = panel.entry_bps.astype(float) * factor
    stop = panel.stop_bps.astype(float) * factor
    target = panel.target_bps.astype(float) * factor
    spread = panel.spread_bps.astype(float) * factor
    slip = panel.slip_bps.astype(float) * factor
    comm = panel.comm_bps.astype(float) * factor
    fut = float(panel.fut_price) * factor
    if slippage_points:
        prices = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
        if getattr(cost, "market", "cfd") == "futures":
            fut += float(slippage_points)
        else:
            adder = float(slippage_points) / prices * 10_000.0
            entry = entry + adder
            stop = stop + adder
            target = target + adder
            slip = slip + adder
    return fastbt.CostPanel(
        spread_bps=spread,
        slip_bps=slip,
        comm_bps=comm,
        fut_price=fut,
        # La v1 conserva exactamente el panel escalado de siempre; la v2 usa
        # los componentes (el objetivo no paga slippage).
        legacy_entry_bps=entry,
        legacy_stop_bps=stop,
        legacy_target_bps=target,
    )


def _run(
    model: dsl.Strategy,
    bars: pd.DataFrame,
    cost,
    setup,
    prepared: fastbt.PreparedBars,
    panel: fastbt.CostPanel,
    cache=None,
) -> dict[str, Any]:
    signals = compiler.compile(model, bars, cache=cache)
    scenario = replace(prepared, panel=panel)
    result = fastbt.run(
        signals,
        bars,
        exit_spec_from_strategy(model),
        cost,
        run_limits_from_strategy(model, setup, close_at_end=True),
        prepared=scenario,
    )
    return {
        "expectancy_r": result.metrics.get("expectancy_r"),
        "profit_factor": result.metrics.get("profit_factor"),
        "max_dd_r": result.metrics.get("max_dd_r"),
        "trades": int(result.metrics.get("trades") or 0),
        "returns": result.daily_r.to_numpy(dtype=float).tolist(),
        "return_dates": [stamp.isoformat() for stamp in result.daily_r.index],
    }


def retest(
    strategy: dsl.Strategy | dict,
    is_frame: pd.DataFrame,
    oos1_frame: pd.DataFrame,
    cost,
    setup,
    *,
    prepared: fastbt.PreparedBars | None = None,
    cache=None,
) -> dict[str, Any]:
    """Costes base/×1,5/×2 y slippage +1/+2 sobre IS+OOS-1."""

    model = (
        strategy
        if isinstance(strategy, dsl.Strategy)
        else dsl.Strategy.model_validate(strategy)
    )
    bars = (
        prepared.bars
        if prepared is not None
        else pd.concat([is_frame, oos1_frame], axis=0, sort=False)
    )
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    trailing = model.exit.trailing or {}
    trail_n = int(trailing.get("n", 14))
    base_prepared = prepared or fastbt.prepare(
        bars,
        cost,
        atr_windows=(model.exit.stop.n, trail_n),
        sessions=(limits,),
    )
    panel = cost.panel(bars)
    scenarios = {
        "base": (1.0, 0.0),
        "cost_x1_5": (1.5, 0.0),
        "cost_x2": (2.0, 0.0),
        "slippage_plus_1": (1.0, 1.0 * float(setup.point)),
        "slippage_plus_2": (1.0, 2.0 * float(setup.point)),
    }
    results = {}
    for name, (factor, points) in scenarios.items():
        scenario_panel = _scenario_panel(
            panel,
            cost,
            bars,
            factor=factor,
            slippage_points=points,
        )
        results[name] = _run(
            model,
            bars,
            cost,
            setup,
            base_prepared,
            scenario_panel,
            cache=cache,
        )
    base_expectancy = results["base"].get("expectancy_r")
    stress = results["cost_x1_5"].get("expectancy_r")
    slip2 = results["slippage_plus_2"].get("expectancy_r")
    return {
        **results,
        "stress_cost_x1_5_ok": (
            base_expectancy is not None
            and stress is not None
            and float(stress) > 0.0
        ),
        "slippage_plus_2_ok": (
            base_expectancy is not None
            and slip2 is not None
            and float(slip2) > 0.0
        ),
        "transfer": {},
        "note": "estrategia congelada; transfer no cuenta como validación",
    }


def transfer(
    strategy: dsl.Strategy | dict,
    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
    costs: dict[str, Any],
    setups: dict[str, Any],
    *,
    cache=None,
) -> dict[str, Any]:
    """Evaluación informativa en otros instrumentos (marcada transfer)."""

    model = (
        strategy
        if isinstance(strategy, dsl.Strategy)
        else dsl.Strategy.model_validate(strategy)
    )
    out: dict[str, Any] = {}
    for symbol, (is_frame, oos1_frame) in frames.items():
        bars = pd.concat([is_frame, oos1_frame], axis=0, sort=False)
        setup = setups[symbol]
        limits = run_limits_from_strategy(model, setup, close_at_end=True)
        trailing = model.exit.trailing or {}
        trail_n = int(trailing.get("n", 14))
        prepared = fastbt.prepare(
            bars,
            costs[symbol],
            atr_windows=(model.exit.stop.n, trail_n),
            sessions=(limits,),
        )
        panel = costs[symbol].panel(bars)
        out[symbol] = {
            **_run(model, bars, costs[symbol], setup, prepared, panel, cache=cache),
            "transfer": True,
            "counts_as_validation": False,
        }
    return out


__all__ = ["retest", "transfer"]
