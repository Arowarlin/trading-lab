"""Traducción de estrategias DSL a las specs del motor rápido."""

from __future__ import annotations

from . import fastbt
from .dsl import Strategy
from .timeframes import minutes_to_bars


def time_exit_bars(model: Strategy) -> int | None:
    """Barras de salida temporal: minutos nuevos o compatibilidad archivada."""

    if model.exit.time_exit_minutes is not None:
        return max(
            1,
            minutes_to_bars(model.exit.time_exit_minutes, model.timeframe),
        )
    return model.exit.time_exit_bars


def cooldown_bars(model: Strategy) -> int:
    if model.limits.cooldown_minutes is not None:
        return minutes_to_bars(model.limits.cooldown_minutes, model.timeframe)
    return int(model.limits.cooldown_bars or 0)


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
    if target is None:
        target_kwargs = {"target": None}
    elif target.type == "rr":
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
        time_exit_bars=time_exit_bars(model),
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
        flat_mode=session.flat_mode,
        weekday_mode=session.weekday_mode,
        weekdays=setup.weekdays,
        max_trades_per_day=model.limits.max_trades_per_day,
        cooldown_bars=cooldown_bars(model),
        allow_next_day_entry=model.timeframe == "D1",
        close_at_end=close_at_end,
        end_index=end_index,
        cost_model_version=int(getattr(setup, "cost_model_version", 1) or 1),
    )


__all__ = [
    "cooldown_bars",
    "exit_spec_from_strategy",
    "run_limits_from_strategy",
    "time_exit_bars",
]
