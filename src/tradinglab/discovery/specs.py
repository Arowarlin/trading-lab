"""Traducción de estrategias DSL a las specs del motor rápido."""

from __future__ import annotations

from . import fastbt
from .dsl import Strategy


def exit_spec_from_strategy(model: Strategy) -> fastbt.ExitSpec:
    stop = model.exit.stop
    if stop.type == "atr":
        stop_kwargs = {"stop": "atr", "stop_mult": stop.mult, "stop_n": stop.n}
    elif stop.type == "pct":
        percentage = stop.value if stop.value is not None else stop.mult
        stop_kwargs = {"stop": "pct", "stop_mult": float(percentage)}
    else:
        stop_kwargs = {"stop": "fixed", "stop_price": stop.value}
    target = model.exit.target
    if target.type == "rr":
        target_kwargs = {"target": "rr", "target_rr": target.rr}
    elif target.type == "pct":
        percentage = target.value if target.value is not None else target.rr
        target_kwargs = {"target": "pct", "target_pct": float(percentage)}
    else:
        target_kwargs = {"target": "fixed", "target_price": target.value}
    breakeven = model.exit.breakeven or {}
    trailing = model.exit.trailing or {}
    trail_mult = trailing.get("atr_mult", trailing.get("mult"))
    return fastbt.ExitSpec(
        **stop_kwargs,
        **target_kwargs,
        breakeven_at_r=breakeven.get("at_r"),
        trail_atr_mult=trail_mult,
        trail_n=int(trailing.get("n", 14)),
        time_exit_bars=model.exit.time_exit_bars,
        opposite_signal=model.exit.opposite_signal,
    )


def run_limits_from_strategy(
    model: Strategy,
    setup,
    *,
    end_index: int | None = None,
    close_at_end: bool = True,
) -> fastbt.RunLimits:
    session = model.session
    return fastbt.RunLimits(
        session_tz=session.tz or setup.session_tz,
        session_start=session.start,
        session_end=session.end,
        flat_at=session.flat_at,
        weekdays=setup.weekdays,
        max_trades_per_day=model.limits.max_trades_per_day,
        cooldown_bars=model.limits.cooldown_bars,
        close_at_end=close_at_end,
        end_index=end_index,
    )


__all__ = ["exit_spec_from_strategy", "run_limits_from_strategy"]
