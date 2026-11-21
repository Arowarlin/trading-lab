"""Perturbation Lab: falsificación relativa a una estrategia concreta.

Compara la estrategia con versiones perturbadas de sí misma (ruido OHLC,
entradas/salidas retrasadas y Monte Carlo de ejecución). Solo usa IS+OOS-1;
nunca OOS-2, nunca crea campañas ni suma al DSR.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..config import DEFAULT_DB
from ..indicators import atr
from ..propfund.costs import load_profile
from . import campaigns, compiler, databank, dsl, fastbt, jobs
from .specs import exit_spec_from_strategy, run_limits_from_strategy

__all__ = [
    "default_slippage",
    "delay_test",
    "execution_mc",
    "load_campaign_inputs",
    "load_spread_histogram",
    "noise_test",
    "perturb_frame",
]


def load_campaign_inputs(
    campaign_id: str,
    *,
    frame: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], jobs.QueueSetup, Any]:
    """Carga IS+OOS-1 de una campaña ``done`` y su coste. Nunca OOS-2."""

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise ValueError(f"campaña no registrada: {campaign_id}")
    is_frame = campaigns.load_segment(
        campaign_id, "is", frame=frame, db_path=db_path
    )
    oos1_frame = campaigns.load_segment(
        campaign_id, "oos1", frame=frame, db_path=db_path
    )
    combined = pd.concat([is_frame, oos1_frame], axis=0, sort=False)
    setup = jobs.QueueSetup.from_campaign(campaign, bars=combined)
    profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
    cost = fastbt.cost_from_profile(profile, use_p75=bool(setup.use_p75))
    return combined, campaign, setup, cost


def load_spread_histogram(
    symbol: str, *, db_path: str | Path | None = None
) -> dict[int, float]:
    """Histograma horario de spread medido; solo lectura de ``broker_spreads``."""

    path = Path(db_path) if db_path else Path(DEFAULT_DB)
    if not path.exists():
        return {}
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT hour_utc, median_bps FROM broker_spreads"
            " WHERE lower(symbol) = lower(?) AND median_bps IS NOT NULL",
            (str(symbol),),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    return {
        int(hour): float(bps)
        for hour, bps in rows
        if hour is not None and bps is not None
    }


def default_slippage(cost: Any) -> float:
    """Slippage máximo por operación (unidades de precio) del perfil."""

    profile = getattr(cost, "profile", None)
    value = getattr(profile, "slippage_price", None)
    return 0.0 if value is None else float(value)


def _archived_strategy(strategy_id: int | None, db_path: str | Path | None) -> bool:
    """True solo si ``strategy_id`` ya existe en ``disc_strategies``."""

    if strategy_id is None:
        return False
    try:
        return (
            databank.get_strategy(int(strategy_id), db_path=db_path) is not None
        )
    except Exception:  # noqa: BLE001 - sin DB no se relaja la validación
        return False


def _prepared(
    model: dsl.Strategy,
    frame: pd.DataFrame,
    cost: Any,
    setup: jobs.QueueSetup,
) -> tuple[fastbt.PreparedBars, fastbt.RunLimits]:
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    trailing = model.exit.trailing or {}
    prepared = fastbt.prepare(
        frame,
        cost,
        atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
        sessions=(limits,),
    )
    return prepared, limits


def _run(
    model: dsl.Strategy,
    frame: pd.DataFrame,
    cost: Any,
    setup: jobs.QueueSetup,
    *,
    signals: compiler.Signals | None = None,
    prepared: fastbt.PreparedBars | None = None,
    limits: fastbt.RunLimits | None = None,
    skip_validation: bool = False,
) -> fastbt.FastResult:
    if prepared is None or limits is None:
        prepared, limits = _prepared(model, frame, cost, setup)
    return fastbt.run(
        signals
        if signals is not None
        else compiler.compile(
            model,
            frame,
            _skip_validation_for_archived=skip_validation,
        ),
        frame,
        exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
    )


def perturb_frame(
    frame: pd.DataFrame, *, scale_atr: float, rng: np.random.Generator
) -> pd.DataFrame:
    """Ruido gaussiano proporcional al ATR14 local y reparación OHLC."""

    out = frame.copy()
    local_atr = np.nan_to_num(
        atr(frame, 14).to_numpy(dtype=float),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    size = len(out)
    for column in ("open", "high", "low", "close"):
        noise = rng.normal(0.0, float(scale_atr), size) * local_atr
        out[column] = out[column].astype(float).to_numpy() + noise
    prices = out[["open", "high", "low", "close"]].clip(lower=1e-9)
    out[["open", "high", "low", "close"]] = prices
    out["high"] = prices.max(axis=1)
    out["low"] = prices.min(axis=1)
    return out


def _expectancy(result: fastbt.FastResult) -> float | None:
    value = result.metrics.get("expectancy_r")
    return None if value is None else float(value)


def _ratio(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or float(base) == 0.0:
        return None
    return float(value) / float(base)


def noise_test(
    strategy: dsl.Strategy | dict,
    frame: pd.DataFrame,
    *,
    paths: int,
    scale_atr: float,
    seed: int,
    cost: Any,
    setup: jobs.QueueSetup,
    strategy_id: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """500 copias con OHLC perturbado; mediana y p10 de expectativa."""

    model = strategy if isinstance(strategy, dsl.Strategy) else dsl.Strategy.model_validate(strategy)
    skip_validation = _archived_strategy(strategy_id, db_path)
    base_result = _run(
        model, frame, cost, setup, skip_validation=skip_validation
    )
    base = _expectancy(base_result)
    values: list[float] = []
    for index in range(int(paths)):
        rng = np.random.default_rng(int(seed) + index)
        perturbed = perturb_frame(frame, scale_atr=float(scale_atr), rng=rng)
        result = _run(
            model,
            perturbed,
            cost,
            setup,
            skip_validation=skip_validation,
        )
        value = _expectancy(result)
        values.append(0.0 if value is None else float(value))
    median = float(np.median(values)) if values else None
    p10 = float(np.percentile(values, 10)) if values else None
    return {
        "base": base,
        "median": median,
        "p10": p10,
        "ratio": _ratio(median, base),
        "positive_frac": (
            float(np.mean(np.asarray(values) > 0.0)) if values else None
        ),
        "paths": int(paths),
        "scale_atr": float(scale_atr),
        "seed": int(seed),
        "valid_paths": len(values),
    }


def _shift_signals(
    signals: compiler.Signals, delay: int
) -> compiler.Signals:
    long_arr = np.zeros_like(signals.long_entry, dtype=bool)
    short_arr = np.zeros_like(signals.short_entry, dtype=bool)
    if delay < len(long_arr):
        long_arr[delay:] = signals.long_entry[:-delay]
        short_arr[delay:] = signals.short_entry[:-delay]
    return compiler.Signals(
        long_entry=long_arr,
        short_entry=short_arr,
        valid_from=int(signals.valid_from) + int(delay),
    )


def _delayed_exit_values(
    trades: list[fastbt.Trade], frame: pd.DataFrame, delay: int
) -> list[float]:
    values: list[float] = []
    last = len(frame) - 1
    for trade in trades:
        if trade.r_net is None:
            continue
        if trade.risk_price is None or float(trade.risk_price) <= 0.0:
            values.append(float(trade.r_net))
            continue
        new_exit = min(last, int(trade.exit_index) + int(delay))
        if new_exit <= int(trade.exit_index):
            values.append(float(trade.r_net))
            continue
        side = 1 if trade.side == "long" else -1
        exit_price = float(frame["close"].iloc[new_exit])
        for index in range(int(trade.exit_index) + 1, new_exit + 1):
            high = float(frame["high"].iloc[index])
            low = float(frame["low"].iloc[index])
            if side == 1:
                if low <= float(trade.stop):
                    exit_price = float(trade.stop)
                    break
                if trade.target is not None and high >= float(trade.target):
                    exit_price = float(trade.target)
                    break
            else:
                if high >= float(trade.stop):
                    exit_price = float(trade.stop)
                    break
                if trade.target is not None and low <= float(trade.target):
                    exit_price = float(trade.target)
                    break
        gross = (
            (exit_price - float(trade.entry_price)) / float(trade.risk_price)
            if side == 1
            else (float(trade.entry_price) - exit_price) / float(trade.risk_price)
        )
        values.append(gross - float(trade.r_cost or 0.0))
    return values


def delay_test(
    strategy: dsl.Strategy | dict,
    frame: pd.DataFrame,
    *,
    entry_delays: tuple[int, ...] | list[int] = (1, 2),
    exit_delays: tuple[int, ...] | list[int] = (1, 2),
    cost: Any,
    setup: jobs.QueueSetup,
    strategy_id: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Entradas/salidas desplazadas +1/+2 barras; salidas iguales o extendidas."""

    model = strategy if isinstance(strategy, dsl.Strategy) else dsl.Strategy.model_validate(strategy)
    skip_validation = _archived_strategy(strategy_id, db_path)
    prepared, limits = _prepared(model, frame, cost, setup)
    signals = compiler.compile(
        model,
        frame,
        _skip_validation_for_archived=skip_validation,
    )
    base_result = _run(
        model,
        frame,
        cost,
        setup,
        signals=signals,
        prepared=prepared,
        limits=limits,
        skip_validation=skip_validation,
    )
    base = _expectancy(base_result)
    entry: dict[str, dict[str, Any]] = {}
    for delay in entry_delays:
        result = _run(
            model,
            frame,
            cost,
            setup,
            signals=_shift_signals(signals, int(delay)),
            prepared=prepared,
            limits=limits,
            skip_validation=skip_validation,
        )
        value = _expectancy(result)
        entry[str(int(delay))] = {
            "expectancy_r": value,
            "ratio": _ratio(value, base),
            "delay_bars": int(delay),
        }
    exit_values: dict[str, dict[str, Any]] = {}
    for delay in exit_delays:
        values = _delayed_exit_values(base_result.trades, frame, int(delay))
        value = float(np.mean(values)) if values else None
        exit_values[str(int(delay))] = {
            "expectancy_r": value,
            "ratio": _ratio(value, base),
            "delay_bars": int(delay),
            "trades": len(values),
        }
    return {"base": base, "entry": entry, "exit": exit_values}


def execution_mc(
    strategy: dsl.Strategy | dict,
    frame: pd.DataFrame,
    *,
    skip_frac: float,
    spread_source: Mapping[int, float] | None,
    slippage_pts: float,
    paths: int,
    seed: int,
    cost: Any,
    setup: jobs.QueueSetup,
    strategy_id: int | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """MC de ejecución: salta operaciones, spread horario y slippage aleatorio."""

    model = strategy if isinstance(strategy, dsl.Strategy) else dsl.Strategy.model_validate(strategy)
    skip_validation = _archived_strategy(strategy_id, db_path)
    base_result = _run(
        model, frame, cost, setup, skip_validation=skip_validation
    )
    base = _expectancy(base_result)
    trades = [
        trade for trade in base_result.trades if trade.r_net is not None
    ]
    if not trades:
        return {
            "base": base,
            "median": None,
            "p10": None,
            "ratio": None,
            "positive_frac": None,
            "paths": int(paths),
            "skip_frac": float(skip_frac),
            "slippage_pts": float(slippage_pts),
            "spread_source": "Sin datos",
            "seed": int(seed),
            "valid_paths": 0,
        }
    r = np.asarray([float(trade.r_net) for trade in trades], dtype=float)
    risk = np.asarray(
        [float(trade.risk_price or 0.0) for trade in trades], dtype=float
    )
    prices = np.asarray(
        [float(trade.entry_price) for trade in trades], dtype=float
    )
    hours = np.asarray([int(trade.entry_time.hour) for trade in trades], dtype=int)
    spread_values = (
        np.asarray([float(value) for value in spread_source.values()], dtype=float)
        if spread_source
        else np.array([], dtype=float)
    )
    current_spread = (
        np.asarray(
            [
                float(spread_source.get(int(hour), np.median(spread_values)))
                for hour in hours
            ],
            dtype=float,
        )
        if spread_source
        else np.zeros(len(trades), dtype=float)
    )
    values: list[float] = []
    skipped: list[int] = []
    safe_risk = np.where(risk > 0.0, risk, 1.0)
    for index in range(int(paths)):
        rng = np.random.default_rng(int(seed) + index)
        keep = rng.random(len(r)) >= float(skip_frac)
        adjusted = r.copy()
        if slippage_pts > 0.0:
            slip = rng.uniform(0.0, float(slippage_pts), len(r))
            adjusted -= slip / safe_risk
        if spread_values.size:
            sampled = rng.choice(spread_values, size=len(r), replace=True)
            adjusted += (
                (sampled - current_spread) / 10_000.0 * prices / safe_risk
            )
        kept = adjusted[keep]
        values.append(float(np.mean(kept)) if len(kept) else 0.0)
        skipped.append(int((~keep).sum()))
    median = float(np.median(values)) if values else None
    p10 = float(np.percentile(values, 10)) if values else None
    return {
        "base": base,
        "median": median,
        "p10": p10,
        "ratio": _ratio(median, base),
        "positive_frac": (
            float(np.mean(np.asarray(values) > 0.0)) if values else None
        ),
        "paths": int(paths),
        "skip_frac": float(skip_frac),
        "slippage_pts": float(slippage_pts),
        "spread_source": "histograma" if spread_source else "Sin datos",
        "seed": int(seed),
        "valid_paths": len(values),
        "skipped_mean": float(np.mean(skipped)) if skipped else None,
    }
