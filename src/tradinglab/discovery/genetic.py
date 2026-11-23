"""Operadores genéticos sobre el AST del DSL.

Todos los operadores devuelven un ``dict`` válido (``dsl.validate`` vacío) o
``None``. El motor decide si el resultado es nuevo; aquí no se tocan datos ni
el databank.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Iterator

import yaml

from ..config import ROOT
from . import dsl
from .blocks import BLOCKS, get_block
from .mirror import mirror_expr
from .timeframes import normalize_timeframe

BOOL_KINDS = {"and", "or", "not", "gt", "lt", "ge", "le", "between", "cross_up", "cross_down",
              "held_for", "within_bars", "time_between", "weekday_in", "pattern", "regime", "htf"}
TEMPLATE_DIR = ROOT / "config" / "discovery" / "templates"


def template_strategy(name: str) -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Sin datos: no existe la plantilla {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    strategy = data.get("strategy")
    if not isinstance(strategy, dict):
        raise ValueError(f"plantilla {name} sin bloque strategy")
    return copy.deepcopy(strategy)


def configured_template(
    name: str,
    *,
    instrument: str | None = None,
    timeframe: str | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plantilla real adaptada al instrumento, timeframe y sesión de la campaña.

    Las plantillas YAML fijan ``instrument: US100``; una campaña sobre un
    símbolo real (``US100.CASH``) debe generar AST con SU instrumento, porque
    el worker rechaza cualquier estrategia que no coincida con la campaña.
    """

    strategy = template_strategy(name)
    if instrument is not None:
        strategy["instrument"] = str(instrument).strip().upper()
    if timeframe is not None:
        strategy["timeframe"] = str(timeframe).strip().upper()
    if session:
        merged = dict(strategy.get("session") or {})
        merged.update(
            {key: value for key, value in dict(session).items() if value is not None}
        )
        strategy["session"] = merged
    return strategy


def template_timeframes(name: str) -> tuple[str, ...]:
    """Temporalidades compatibles declaradas por la plantilla."""

    path = TEMPLATE_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Sin datos: no existe la plantilla {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("valid_timeframes") or data.get("timeframes")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"la plantilla {name} no declara timeframes")
    result: list[str] = []
    for item in raw:
        key = normalize_timeframe(str(item))
        if key not in result:
            result.append(key)
    return tuple(result)


def template_symmetric(name: str) -> bool:
    """Lee el flag ``symmetric`` de la plantilla (clave de nivel superior)."""

    path = TEMPLATE_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Sin datos: no existe la plantilla {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return bool(data.get("symmetric", False))


def _enforce_symmetry(strategy: dict[str, Any]) -> None:
    long_entry = strategy.get("long_entry")
    strategy["short_entry"] = (
        mirror_expr(long_entry) if isinstance(long_entry, dict) else None
    )


def _valid(strategy: dict[str, Any]) -> bool:
    return not dsl.validate(strategy)


def _iter_nodes(
    node: Any, parent: Any = None, slot: Any = None
) -> Iterator[tuple[dict, Any, Any]]:
    if not isinstance(node, dict):
        return
    yield node, parent, slot
    for index, child in enumerate(node.get("args") or []):
        yield from _iter_nodes(child, node["args"], index)
    for key in ("left", "right", "expr"):
        child = node.get(key)
        if isinstance(child, dict):
            yield from _iter_nodes(child, node, key)


def _roots(strategy: dict[str, Any]):
    for name in ("long_entry", "short_entry"):
        root = strategy.get(name)
        if isinstance(root, dict):
            yield name, root


def _side_roots(strategy: dict[str, Any], symmetric: bool = False):
    for name, root in _roots(strategy):
        if symmetric and name != "long_entry":
            continue
        yield name, root


def _bool_roots(strategy: dict[str, Any], symmetric: bool = False):
    for name, root in _side_roots(strategy, symmetric):
        for node, parent, slot in _iter_nodes(root):
            if node.get("kind") in BOOL_KINDS:
                yield name, node, parent, slot


def _replace(
    strategy: dict[str, Any],
    name: str,
    parent: Any,
    slot: Any,
    replacement: dict[str, Any],
) -> None:
    if parent is None:
        strategy[name] = replacement
    else:
        parent[slot] = replacement


def _choose_param(
    node: dict[str, Any], rng: random.Random
) -> tuple[str, float, float] | None:
    name = node.get("ind") or node.get("pattern") or node.get("regime")
    if not name or name not in BLOCKS:
        return None
    spec = get_block(name)
    candidates = []
    for key, param in spec.params.items():
        current = node.get("params", {}).get(key, param.default)
        if key == "n" and node.get("n") is not None:
            current = node["n"]
        if key == "lookback" and node.get("lookback") is not None:
            current = node["lookback"]
        try:
            current_value = float(current)
        except (TypeError, ValueError):
            continue
        candidates.append((key, param, current_value))
    if not candidates:
        return None
    key, param, current = rng.choice(candidates)
    steps = max(1, int(round((param.high - param.low) / param.step)))
    values = [
        param.low + step * param.step
        for step in range(steps + 1)
        if param.low + step * param.step <= param.high + 1e-9
    ]
    values = [round(value, 6) for value in values if abs(value - current) > 1e-9]
    if not values:
        return None
    value = rng.choice(values)
    return key, value, current


def _set_param(node: dict[str, Any], key: str, value: float) -> None:
    if key == "n":
        node["n"] = int(value)
        return
    if key == "lookback":
        node["lookback"] = int(value)
        return
    params = dict(node.get("params") or {})
    params[key] = value
    node["params"] = params


def mutate_param(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    nodes = [
        node
        for _name, root in _side_roots(data, symmetric)
        for node, _parent, _slot in _iter_nodes(root)
    ]
    candidates = [
        node
        for node in nodes
        if node.get("kind") in {"indicator", "pattern", "regime"}
    ]
    rng.shuffle(candidates)
    for node in candidates:
        picked = _choose_param(node, rng)
        if picked is None:
            continue
        key, value, _current = picked
        _set_param(node, key, value)
        if symmetric:
            _enforce_symmetry(data)
        if _valid(data):
            return data
    return None


def mutate_block(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    nodes = [
        node
        for _name, root in _side_roots(data, symmetric)
        for node, _parent, _slot in _iter_nodes(root)
    ]
    indicators = [node for node in nodes if node.get("kind") == "indicator"]
    rng.shuffle(indicators)
    for node in indicators:
        current = node.get("ind")
        if current not in BLOCKS:
            continue
        output = get_block(current).output
        options = [
            name
            for name, spec in BLOCKS.items()
            if spec.output == output and name != current
        ]
        if not options:
            continue
        node["ind"] = rng.choice(options)
        node["params"] = {}
        node.pop("n", None)
        node.pop("lookback", None)
        if symmetric:
            _enforce_symmetry(data)
        if _valid(data):
            return data
    return None


def mutate_threshold(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    comparisons = [
        node
        for _name, node, _parent, _slot in _bool_roots(data, symmetric)
        if node.get("kind") in {"gt", "lt", "ge", "le", "between"}
    ]
    rng.shuffle(comparisons)
    for node in comparisons:
        if node.get("kind") == "between":
            current = float(node.get("value") or 0.0)
            step = max(abs(current) * 0.05, 0.01)
            node["value"] = current + rng.choice([-step, step])
            node["low"] = float(node["value"]) - step
            node["high"] = float(node["value"]) + step
        else:
            side = None
            if (node.get("right") or {}).get("kind") == "const":
                side = "right"
            elif (node.get("left") or {}).get("kind") == "const":
                side = "left"
            if side is None:
                continue
            current = float(node[side].get("value") or 0.0)
            step = max(abs(current) * 0.05, 0.01)
            node[side]["value"] = current + rng.choice([-step, step])
        if symmetric:
            _enforce_symmetry(data)
        if _valid(data):
            return data
    return None


def _bool_node(rng: random.Random) -> dict:
    choices = [
        {
            "kind": "gt",
            "left": {"kind": "indicator", "ind": "rsi", "n": 14},
            "right": {"kind": "const", "value": rng.choice([50.0, 55.0, 60.0])},
        },
        {
            "kind": "lt",
            "left": {"kind": "indicator", "ind": "rsi", "n": 14},
            "right": {"kind": "const", "value": rng.choice([35.0, 40.0, 45.0])},
        },
        {
            "kind": "cross_up",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "level", "level": "opening_range_high"},
        },
        {
            "kind": "cross_down",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "level", "level": "opening_range_low"},
        },
        {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 50},
        },
        {
            "kind": "lt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 50},
        },
        {
            "kind": "regime",
            "regime": "vol_high",
            "n": 14,
            "lookback": 100,
            "params": {"pct": rng.choice([0.7, 0.8, 0.9])},
        },
    ]
    return copy.deepcopy(rng.choice(choices))


def mutate_logic(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    logical = [
        (name, node, parent, slot)
        for name, node, parent, slot in _bool_roots(data, symmetric)
        if node.get("kind") in {"and", "or", "not"}
    ]
    if not logical:
        return None
    name, node, parent, slot = rng.choice(logical)
    action = rng.choice(["flip", "not", "add", "remove"])
    if action == "flip" and node.get("kind") in {"and", "or"} and len(node.get("args") or []) >= 2:
        node["kind"] = "or" if node["kind"] == "and" else "and"
    elif action == "not":
        args = node.get("args") or []
        if node.get("kind") == "not" and len(args) == 1:
            _replace(data, name, parent, slot, copy.deepcopy(args[0]))
        elif node.get("kind") in {"and", "or"} and args:
            index = rng.randrange(len(args))
            args[index] = {"kind": "not", "args": [args[index]]}
    elif action == "add" and node.get("kind") in {"and", "or"}:
        args = node.setdefault("args", [])
        args.append(_bool_node(rng))
    elif action == "remove" and node.get("kind") in {"and", "or"} and len(node.get("args") or []) > 2:
        node["args"].pop(rng.randrange(len(node["args"])))
    else:
        return None
    if symmetric:
        _enforce_symmetry(data)
    return data if _valid(data) else None


def mutate_exit(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    exit_block = data.setdefault("exit", {})
    action = rng.choice(
        ["stop", "target", "breakeven", "trailing", "time", "opposite"]
    )
    if action == "stop":
        exit_block["stop"] = {
            "type": "atr",
            "mult": round(rng.uniform(1.0, 5.0), 2),
            "n": rng.choice([10, 14, 20, 30]),
        }
    elif action == "target":
        exit_block["target"] = {
            "type": "rr",
            "rr": round(rng.uniform(1.0, 4.0), 2),
        }
    elif action == "breakeven":
        exit_block["breakeven"] = (
            None if exit_block.get("breakeven") else {"at_r": round(rng.uniform(0.5, 1.5), 2)}
        )
    elif action == "trailing":
        exit_block["trailing"] = (
            None
            if exit_block.get("trailing")
            else {
                "atr_mult": round(rng.uniform(0.5, 2.5), 2),
                "n": rng.choice([10, 14, 20]),
            }
        )
    elif action == "time":
        exit_block.pop("time_exit_bars", None)
        exit_block["time_exit_minutes"] = rng.choice([60, 120, 180, 240, 360, 480])
    else:
        exit_block["opposite_signal"] = not bool(exit_block.get("opposite_signal"))
    if symmetric:
        _enforce_symmetry(data)
    return data if _valid(data) else None


def mutate_session(
    strategy: dict[str, Any], rng: random.Random, *, symmetric: bool = False
) -> dict | None:
    data = copy.deepcopy(strategy)
    session = data.setdefault("session", {})
    start_h, start_m = (int(part) for part in str(session.get("start", "09:35")).split(":"))
    end_h, end_m = (int(part) for part in str(session.get("end", "11:30")).split(":"))
    minutes_start = start_h * 60 + start_m + rng.choice([-15, -5, 5, 15])
    minutes_end = end_h * 60 + end_m + rng.choice([-15, -5, 5, 15])
    if minutes_start < 9 * 60 + 30 or minutes_end > 15 * 60:
        return None
    if minutes_end <= minutes_start:
        return None
    session["start"] = f"{minutes_start // 60:02d}:{minutes_start % 60:02d}"
    session["end"] = f"{minutes_end // 60:02d}:{minutes_end % 60:02d}"
    if symmetric:
        _enforce_symmetry(data)
    return data if _valid(data) else None


def crossover_subtree(
    left: dict[str, Any],
    right: dict[str, Any],
    rng: random.Random,
    *,
    symmetric: bool = False,
) -> dict | None:
    data = copy.deepcopy(left)
    left_nodes = list(_bool_roots(data, symmetric))
    right_nodes = list(_bool_roots(right, symmetric))
    if not left_nodes or not right_nodes:
        return None
    kinds = {node.get("kind") for _n, node, _p, _s in right_nodes}
    candidates = [
        (name, node, parent, slot)
        for name, node, parent, slot in left_nodes
        if node.get("kind") in kinds
    ]
    if not candidates:
        return None
    name, _node, parent, slot = rng.choice(candidates)
    _rname, replacement, _rp, _rs = rng.choice(
        [item for item in right_nodes if item[1].get("kind") == _node.get("kind")]
    )
    _replace(data, name, parent, slot, copy.deepcopy(replacement))
    if symmetric:
        _enforce_symmetry(data)
    return data if _valid(data) else None


def crossover_exit(
    left: dict[str, Any],
    right: dict[str, Any],
    rng: random.Random,
    *,
    symmetric: bool = False,
) -> dict | None:
    data = copy.deepcopy(left)
    data["exit"] = copy.deepcopy(right.get("exit") or data.get("exit"))
    if symmetric:
        _enforce_symmetry(data)
    return data if _valid(data) else None


MUTATIONS = (
    mutate_param,
    mutate_block,
    mutate_threshold,
    mutate_logic,
    mutate_exit,
    mutate_session,
)


def tournament_offspring(
    left: dict[str, Any],
    right: dict[str, Any] | None,
    rng: random.Random,
    *,
    symmetric: bool = False,
) -> tuple[dict | None, str]:
    """Aplica un operador aleatorio y devuelve (hijo, nombre)."""

    if right is not None and rng.random() < 0.6:
        if rng.random() < 0.5:
            return (
                crossover_subtree(left, right, rng, symmetric=symmetric),
                "crossover_subtree",
            )
        return (
            crossover_exit(left, right, rng, symmetric=symmetric),
            "crossover_exit",
        )
    operator = rng.choice(MUTATIONS)
    return operator(left, rng, symmetric=symmetric), operator.__name__


def random_strategy(
    rng: random.Random,
    template: str = "ny_open_vol_filter",
    *,
    attempts: int = 25,
    instrument: str | None = None,
    timeframe: str | None = None,
    session: dict[str, Any] | None = None,
    symmetric: bool | None = None,
) -> dict | None:
    if symmetric is None:
        symmetric = template_symmetric(template)
    model = configured_template(
        template,
        instrument=instrument,
        timeframe=timeframe,
        session=session,
    )
    if symmetric:
        _enforce_symmetry(model)
    for _ in range(attempts):
        data = copy.deepcopy(model)
        for _step in range(rng.randint(1, 3)):
            data = rng.choice(MUTATIONS)(data, rng, symmetric=symmetric) or data
        data["exit"] = {
            "stop": {
                "type": "atr",
                "mult": round(rng.uniform(2.0, 5.0), 2),
                "n": rng.choice([14, 20]),
            },
            "target": {"type": "rr", "rr": round(rng.uniform(1.0, 3.0), 2)},
            "time_exit_minutes": rng.choice([120, 240, 360]),
        }
        if symmetric:
            _enforce_symmetry(data)
        if _valid(data):
            return data
    for _ in range(attempts):
        conditions = [_bool_node(rng) for _ in range(rng.choice([1, 2, 3]))]
        entry = conditions[0] if len(conditions) == 1 else {
            "kind": rng.choice(["and", "or"]),
            "args": conditions,
        }
        data = copy.deepcopy(model)
        data["long_entry"] = entry
        data["short_entry"] = None
        data["exit"] = {
            "stop": {
                "type": "atr",
                "mult": round(rng.uniform(2.0, 5.0), 2),
                "n": 14,
            },
            "target": {"type": "rr", "rr": round(rng.uniform(1.0, 3.0), 2)},
            "time_exit_minutes": rng.choice([120, 240, 360]),
        }
        if symmetric:
            _enforce_symmetry(data)
        if _valid(data):
            return data
    return None


def diff_strategies(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Diff compacto por rutas para la genealogía."""

    changes: dict[str, Any] = {}

    def walk(a: Any, b: Any, path: str) -> None:
        if len(changes) >= 20:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key), b.get(key), f"{path}.{key}" if path else str(key))
            return
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                changes[path] = [len(a), len(b)]
                return
            for index, (left_item, right_item) in enumerate(zip(a, b)):
                walk(left_item, right_item, f"{path}[{index}]")
            return
        if a != b:
            changes[path] = [a, b]

    walk(left, right, "")
    return changes


__all__ = [
    "MUTATIONS",
    "configured_template",
    "crossover_exit",
    "crossover_subtree",
    "diff_strategies",
    "mirror_expr",
    "mutate_block",
    "mutate_exit",
    "mutate_logic",
    "mutate_param",
    "mutate_session",
    "mutate_threshold",
    "random_strategy",
    "template_strategy",
    "template_symmetric",
    "template_timeframes",
    "tournament_offspring",
]
