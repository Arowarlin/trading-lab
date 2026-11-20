"""Análisis de meseta ±1 paso de una estrategia congelada (solo IS).

No crea estrategias: evalúa copias temporales de los parámetros y devuelve la
matriz para el mapa de calor. Optuna/reoptimización queda fuera del MVP.
"""

from __future__ import annotations

import copy
from typing import Any

import pandas as pd

from . import compiler, dsl, fastbt
from .blocks import get_block
from .specs import exit_spec_from_strategy, run_limits_from_strategy

EXIT_STEPS = {
    "stop.mult": 0.1,
    "stop.value": 0.1,
    "target.rr": 0.1,
    "target.value": 0.1,
    "time_exit_bars": 12,
    "session.start": 5,
    "session.end": 5,
}


def _walk(node: Any, path: str = ""):
    if not isinstance(node, dict):
        return
    yield node, path
    for index, child in enumerate(node.get("args") or []):
        yield from _walk(child, f"{path}.args[{index}]")
    for key in ("left", "right", "expr"):
        child = node.get(key)
        if isinstance(child, dict):
            yield from _walk(child, f"{path}.{key}")


def _entry_nodes(strategy: dict[str, Any]):
    for name in ("long_entry", "short_entry"):
        root = strategy.get(name)
        if isinstance(root, dict):
            yield name, root


def _set_path(strategy: dict[str, Any], path: str, value: float) -> bool:
    tokens: list[Any] = []
    for chunk in path.replace("]", "").split("."):
        if not chunk:
            continue
        if "[" in chunk:
            name, index = chunk.split("[")
            tokens.append(name)
            tokens.append(int(index))
        else:
            tokens.append(chunk)
    current: Any = strategy
    for token in tokens[:-1]:
        current = current[token]
    current[tokens[-1]] = value
    return True


def _get_path(strategy: dict[str, Any], path: str) -> float | None:
    tokens: list[Any] = []
    for chunk in path.replace("]", "").split("."):
        if not chunk:
            continue
        if "[" in chunk:
            name, index = chunk.split("[")
            tokens.append(name)
            tokens.append(int(index))
        else:
            tokens.append(chunk)
    current: Any = strategy
    for token in tokens:
        current = current[token]
    try:
        return float(current)
    except (TypeError, ValueError):
        return None


def _parameters(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for which, root in _entry_nodes(strategy):
        for node, path in _walk(root, which):
            name = node.get("ind") or node.get("pattern") or node.get("regime")
            if not name:
                continue
            try:
                spec = get_block(name)
            except KeyError:
                continue
            for key, param in spec.params.items():
                if key == "n":
                    node_path = f"{path}.n"
                elif key == "lookback":
                    node_path = f"{path}.lookback"
                else:
                    node_path = f"{path}.params.{key}"
                current = _get_path(strategy, node_path)
                if current is None and key in {"n", "lookback"}:
                    current = float(param.default)
                if current is None:
                    continue
                parameters.append(
                    {
                        "name": f"{path}.{key}",
                        "path": node_path,
                        "step": float(param.step),
                        "low": float(param.low),
                        "high": float(param.high),
                        "integer": bool(param.integer),
                    }
                )
    exit_block = strategy.get("exit") or {}
    stop_block = exit_block.get("stop") or {}
    target_block = exit_block.get("target") or {}
    stop_type = str(stop_block.get("type") or "atr")
    target_type = str(target_block.get("type") or "rr")
    exit_parameters = []
    if stop_type == "atr":
        exit_parameters.append(("stop.mult", EXIT_STEPS["stop.mult"]))
    elif stop_block.get("value") is not None:
        exit_parameters.append(("stop.value", EXIT_STEPS["stop.value"]))
    if target_type == "rr":
        exit_parameters.append(("target.rr", EXIT_STEPS["target.rr"]))
    elif target_block.get("value") is not None:
        exit_parameters.append(("target.value", EXIT_STEPS["target.value"]))
    if exit_block.get("time_exit_bars") is not None:
        exit_parameters.append(
            ("time_exit_bars", float(EXIT_STEPS["time_exit_bars"]))
        )
    for key, step in exit_parameters:
        path = f"exit.{key}"
        current = _get_path(strategy, path)
        if current is None:
            continue
        parameters.append(
            {
                "name": key,
                "path": path,
                "step": step,
                "low": 0.0,
                "high": 10_000.0,
                "integer": key == "time_exit_bars",
            }
        )
    for key in ("session.start", "session.end"):
        raw = _get_path(strategy, key)
        if raw is None:
            # Las horas son "HH:MM" y no pasan por _get_path numérico.
            field = key.split(".", 1)[1]
            text = str((strategy.get("session") or {}).get(field) or "")
            if ":" in text:
                hour, minute = (int(part) for part in text.split(":"))
                raw = float(hour * 60 + minute)
        if raw is None:
            continue
        parameters.append(
            {
                "name": key,
                "path": key,
                "step": float(EXIT_STEPS[key]),
                "low": 0.0,
                "high": 24 * 60.0,
                "integer": True,
            }
        )
    return parameters


def _set_value(
    strategy: dict[str, Any], parameter: dict[str, Any], value: float
) -> None:
    if parameter["path"].startswith("session."):
        total = int(round(value))
        key = parameter["path"].split(".", 1)[1]
        strategy.setdefault("session", {})[key] = (
            f"{total // 60:02d}:{total % 60:02d}"
        )
        return
    if parameter["integer"]:
        value = float(int(round(value)))
    _set_path(strategy, parameter["path"], value)


def _metrics(
    strategy: dict[str, Any],
    bars: pd.DataFrame,
    cost,
    setup,
    prepared,
    *,
    cache,
) -> dict[str, Any]:
    model = dsl.Strategy.model_validate(strategy)
    signals = compiler.compile(model, bars, cache=cache)
    result = fastbt.run(
        signals,
        bars,
        exit_spec_from_strategy(model),
        cost,
        run_limits_from_strategy(model, setup),
        prepared=prepared,
    )
    return {
        "expectancy_r": result.metrics.get("expectancy_r"),
        "profit_factor": result.metrics.get("profit_factor"),
        "max_dd_r": result.metrics.get("max_dd_r"),
        "trades": int(result.metrics.get("trades") or 0),
    }


def plateau(
    strategy: dsl.Strategy | dict,
    bars: pd.DataFrame,
    cost,
    setup,
    prepared,
    *,
    cache=None,
) -> dict[str, Any]:
    """Matriz de estabilidad ±1 paso; no modifica la estrategia ni la guarda."""

    base = (
        strategy.model_dump(mode="json", exclude_none=True)
        if isinstance(strategy, dsl.Strategy)
        else copy.deepcopy(strategy)
    )
    parameters = _parameters(base)
    base_metrics = _metrics(base, bars, cost, setup, prepared, cache=cache)
    rows: list[dict[str, Any]] = []
    for parameter in parameters:
        current = _get_path(base, parameter["path"])
        if current is None and parameter["path"].startswith("session."):
            key = parameter["path"].split(".", 1)[1]
            text = str((base.get("session") or {}).get(key) or "")
            hour, minute = (int(part) for part in text.split(":"))
            current = float(hour * 60 + minute)
        if current is None:
            continue
        row = {
            "name": parameter["name"],
            "base": float(current),
            "minus": None,
            "plus": None,
            "metrics": {"base": base_metrics, "minus": None, "plus": None},
        }
        for label, delta in (("minus", -parameter["step"]), ("plus", parameter["step"])):
            value = float(current) + delta
            if value < parameter["low"] or value > parameter["high"]:
                continue
            if parameter["path"] == "time_exit_bars" and value < 1:
                continue
            variant = copy.deepcopy(base)
            _set_value(variant, parameter, value)
            if dsl.validate(variant):
                continue
            row[label] = value
            row["metrics"][label] = _metrics(
                variant, bars, cost, setup, prepared, cache=cache
            )
        rows.append(row)
    return {
        "base": base_metrics,
        "parameters": rows,
        "rows": len(rows),
        "note": "análisis de meseta; no crea estrategias ni reoptimiza",
    }


__all__ = ["plateau"]
