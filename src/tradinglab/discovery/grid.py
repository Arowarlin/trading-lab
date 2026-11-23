"""Modo rejilla: todas las combinaciones declaradas por la plantilla.

No hay operadores genéticos. La estructura base es fija y solo cambian los
valores de las dimensiones declaradas en ``grid:``. La simetría largo/corto se
mantiene con ``genetic.mirror_expr``.
"""

from __future__ import annotations

import copy
import itertools
import re
from typing import Any

import yaml

from ..config import ROOT
from . import dsl, genetic

TEMPLATE_DIR = ROOT / "config" / "discovery" / "templates"
_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")
_KINDS = {"path", "volatility", "exit"}


class GridError(ValueError):
    pass


def validate_grid(spec: dict[str, Any], template: str) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise GridError(f"la plantilla {template} no declara grid")
    dimensions = spec.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise GridError("grid.dimensions debe ser una lista no vacía")
    names: set[str] = set()
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            raise GridError("cada dimensión debe ser un objeto")
        name = str(dimension.get("name") or "").strip()
        kind = str(dimension.get("kind") or "path")
        values = dimension.get("values")
        if not name or name in names:
            raise GridError(f"dimensión sin nombre o repetida: {name!r}")
        if kind not in _KINDS:
            raise GridError(f"dimensión {name}: kind desconocido {kind}")
        if not isinstance(values, list) or not values:
            raise GridError(f"dimensión {name}: values vacío")
        if kind == "path" and not str(dimension.get("path") or "").strip():
            raise GridError(f"dimensión {name}: falta path")
        names.add(name)
    if any(str(item.get("kind") or "path") == "exit" for item in dimensions):
        variants = spec.get("exit_variants")
        if not isinstance(variants, dict) or not variants:
            raise GridError("grid.exit_variants falta para la dimensión exit")
        for dimension in dimensions:
            if str(dimension.get("kind") or "path") != "exit":
                continue
            for value in dimension["values"]:
                if str(value) not in variants:
                    raise GridError(f"exit_variants no define {value}")
    return copy.deepcopy(spec)


def load_grid(template: str) -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{template}.yaml"
    if not path.exists():
        raise GridError(f"Sin datos: no existe la plantilla {template}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    spec = payload.get("grid")
    if not isinstance(spec, dict):
        raise GridError(f"la plantilla {template} no declara grid")
    return validate_grid(spec, template)


def grid_size(template: str, *, grid_spec: dict[str, Any] | None = None) -> int:
    spec = validate_grid(grid_spec, template) if grid_spec else load_grid(template)
    size = 1
    for dimension in spec["dimensions"]:
        size *= len(dimension["values"])
    return int(size)


def _tokens(path: str) -> list[Any]:
    tokens: list[Any] = []
    position = 0
    for match in _TOKEN.finditer(path):
        if match.start() != position and path[position : match.start()] not in {"."}:
            raise GridError(f"path inválido: {path}")
        token = match.group(1)
        tokens.append(token if token is not None else int(match.group(2)))
        position = match.end()
        if position < len(path) and path[position] == ".":
            position += 1
    if position != len(path) or not tokens:
        raise GridError(f"path inválido: {path}")
    return tokens


def _set_path(data: Any, path: str, value: Any) -> None:
    tokens = _tokens(path)
    current = data
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                raise GridError(f"path fuera de rango: {path}")
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                raise GridError(f"path inexistente: {path}")
            current = current[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or last >= len(current):
            raise GridError(f"path fuera de rango: {path}")
        current[last] = value
    else:
        if not isinstance(current, dict):
            raise GridError(f"path inválido: {path}")
        current[last] = value


def _apply_volatility(strategy: dict[str, Any], value: str) -> None:
    long_entry = strategy.get("long_entry")
    if not isinstance(long_entry, dict):
        raise GridError("la rejilla de volatilidad necesita long_entry")
    args = long_entry.get("args")
    if not isinstance(args, list):
        raise GridError("la rejilla de volatilidad necesita args")
    args[:] = [
        node
        for node in args
        if not (isinstance(node, dict) and node.get("kind") == "regime")
    ]
    if value == "none":
        return
    if value != "vol_high":
        raise GridError(f"filtro de volatilidad no soportado: {value}")
    args.append(
        {
            "kind": "regime",
            "regime": "vol_high",
            "n": 14,
            "lookback": 100,
            "params": {"pct": 0.8},
        }
    )


def _apply_exit(strategy: dict[str, Any], variant: str, spec: dict[str, Any]) -> None:
    definitions = spec.get("exit_variants") or {}
    definition = definitions.get(str(variant))
    if not isinstance(definition, dict):
        raise GridError(f"exit_variants no define {variant}")
    exit_block = strategy.setdefault("exit", {})
    stop = exit_block.setdefault("stop", {"type": "atr", "n": 14})
    stop["type"] = "atr"
    stop["mult"] = float(definition["stop_mult"])
    stop["n"] = int(definition.get("stop_n", 14))
    if "target_rr" not in definition:
        raise GridError(f"exit_variants {variant} sin target_rr (usa null para sin target)")
    target_rr = definition["target_rr"]
    if target_rr is None:
        exit_block["target"] = None
    else:
        target = exit_block.get("target")
        if not isinstance(target, dict):
            target = {"type": "rr"}
            exit_block["target"] = target
        target["type"] = "rr"
        target["rr"] = float(target_rr)
    if "time_exit_minutes" in definition:
        exit_block.pop("time_exit_bars", None)
        value = definition["time_exit_minutes"]
        if value is None:
            exit_block.pop("time_exit_minutes", None)
        else:
            exit_block["time_exit_minutes"] = int(value)
    else:
        time_exit = definition.get("time_exit_bars")
        exit_block.pop("time_exit_minutes", None)
        if time_exit is None:
            exit_block.pop("time_exit_bars", None)
        else:
            exit_block["time_exit_bars"] = int(time_exit)
    session = strategy.setdefault("session", {})
    session["flat_at"] = str(definition.get("flat_at", "15:55"))


def grid_strategies(
    template: str,
    *,
    instrument: str | None = None,
    timeframe: str | None = None,
    session: dict[str, Any] | None = None,
    grid_spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    spec = (
        validate_grid(grid_spec, template)
        if grid_spec is not None
        else load_grid(template)
    )
    base = genetic.configured_template(
        template,
        instrument=instrument,
        timeframe=timeframe,
        session=session,
    )
    dimensions = spec["dimensions"]
    strategies: list[dict[str, Any]] = []
    for combination in itertools.product(
        *(dimension["values"] for dimension in dimensions)
    ):
        data = copy.deepcopy(base)
        for dimension, value in zip(dimensions, combination):
            kind = str(dimension.get("kind") or "path")
            if kind == "path":
                _set_path(data, str(dimension["path"]), value)
            elif kind == "volatility":
                _apply_volatility(data, str(value))
            elif kind == "exit":
                _apply_exit(data, str(value), spec)
        data["short_entry"] = genetic.mirror_expr(data.get("long_entry"))
        errors = dsl.validate(data)
        if errors:
            raise GridError(
                f"combinación de rejilla inválida "
                f"({dict(zip((d['name'] for d in dimensions), combination))}): "
                + "; ".join(errors)
            )
        strategies.append(data)
    return strategies


__all__ = ["GridError", "grid_size", "grid_strategies", "load_grid", "validate_grid"]
