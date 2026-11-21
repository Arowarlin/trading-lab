"""Espejo del AST por tipo de bloque.

Cada ``BlockSpec`` declara cómo se refleja en el corto:

* ``signed``: el bloque está centrado en cero; se invierte el operador y se
  niega la constante (``gt(x, u)`` -> ``lt(x, -u)``).
* ``bounded``: el bloque vive en una escala acotada con centro declarado; se
  invierte el operador y se refleja la constante (``c' = 2*centro - c``).
* ``price``: precio, nivel, media o patrón direccional; se invierte el operador
  y se intercambian ``high<->low``, niveles y patrones ``up<->down``.
* ``none``: filtro o régimen sin dirección; la condición se copia idéntica.

``between`` refleja y reordena sus dos extremos para ``signed`` y ``bounded``.
``cross_up``/``cross_down`` siguen la misma regla que ``gt``/``lt``.
"""

from __future__ import annotations

import copy
from typing import Any

from .blocks import BlockSpec, get_block

COMPARE = {"gt", "lt", "ge", "le"}
CROSS = {"cross_up", "cross_down"}
LOGICAL = {"and", "or", "not"}
OPPOSITE = {
    "gt": "lt",
    "lt": "gt",
    "ge": "le",
    "le": "ge",
    "cross_up": "cross_down",
    "cross_down": "cross_up",
}
MIRROR_LEVEL = {
    "opening_range_high": "opening_range_low",
    "opening_range_low": "opening_range_high",
    "prev_day_high": "prev_day_low",
    "prev_day_low": "prev_day_high",
    "prev_session_high": "prev_session_low",
    "prev_session_low": "prev_session_high",
    "donchian_high": "donchian_low",
    "donchian_low": "donchian_high",
}
MIRROR_PRICE = {"high": "low", "low": "high"}
MIRROR_PATTERN = {
    "bos_up": "bos_down",
    "bos_down": "bos_up",
    "choch_up": "choch_down",
    "choch_down": "choch_up",
}
MIRROR_INDICATOR = {
    "swing_high": "swing_low",
    "swing_low": "swing_high",
}


def _block(node: Any) -> BlockSpec | None:
    if not isinstance(node, dict):
        return None
    kind = node.get("kind")
    name = None
    if kind == "indicator":
        name = node.get("ind")
    elif kind == "pattern":
        name = node.get("pattern")
    elif kind == "regime":
        name = node.get("regime")
    if not name:
        return None
    try:
        return get_block(str(name))
    except KeyError:
        return None


def _node_type(node: Any) -> tuple[str, float | None] | None:
    """Tipo de espejo del nodo, o ``None`` si no es un bloque comparable."""

    if not isinstance(node, dict):
        return None
    if node.get("kind") in {"price", "level"}:
        return ("price", None)
    spec = _block(node)
    if spec is not None:
        return (spec.mirror, spec.center)
    return None


def _comparison_type(node: dict) -> tuple[str, float | None]:
    for side in ("left", "right"):
        found = _node_type(node.get(side))
        if found is not None:
            return found
    # Comparaciones entre constantes: el operador se invierte como precio.
    return ("price", None)


def _reflect_value(value: float, mirror: str, center: float | None) -> float:
    if mirror == "signed":
        return -float(value)
    if mirror == "bounded":
        if center is None:  # pragma: no cover - BlockSpec lo impide
            raise ValueError("mirror bounded sin centro")
        return round(2.0 * float(center) - float(value), 12)
    return float(value)


def _reflect_operand(node: dict, mirror: str, center: float | None) -> None:
    if mirror in {"signed", "bounded"}:
        for side in ("left", "right"):
            child = node.get(side)
            if isinstance(child, dict) and child.get("kind") == "const":
                child["value"] = _reflect_value(
                    float(child.get("value", 0.0)), mirror, center
                )


def mirror_expr(expr: Any) -> Any:
    """Devuelve el espejo del AST según el tipo de cada bloque."""

    if not isinstance(expr, dict):
        return copy.deepcopy(expr)
    data = copy.deepcopy(expr)
    kind = data.get("kind")

    if kind in LOGICAL:
        data["args"] = [mirror_expr(item) for item in data.get("args") or []]
        return data

    if kind in COMPARE or kind in CROSS:
        mirror, center = _comparison_type(data)
        if mirror == "none":
            return data
        data["kind"] = OPPOSITE[str(kind)]
        for side in ("left", "right"):
            child = data.get(side)
            if isinstance(child, dict):
                data[side] = mirror_expr(child)
        _reflect_operand(data, mirror, center)
        return data

    if kind == "between":
        found = _node_type(data.get("left")) or ("price", None)
        mirror, center = found
        if isinstance(data.get("left"), dict):
            data["left"] = mirror_expr(data["left"])
        low = float(data.get("low", 0.0))
        high = float(data.get("high", 0.0))
        if mirror in {"signed", "bounded"}:
            data["low"], data["high"] = (
                _reflect_value(high, mirror, center),
                _reflect_value(low, mirror, center),
            )
        return data

    if kind in {"held_for", "within_bars"}:
        data["args"] = [mirror_expr(item) for item in data.get("args") or []]
        return data

    if kind == "htf":
        if isinstance(data.get("expr"), dict):
            data["expr"] = mirror_expr(data["expr"])
        return data

    if kind == "price":
        if data.get("price") in MIRROR_PRICE:
            data["price"] = MIRROR_PRICE[data["price"]]
        return data

    if kind == "level":
        if data.get("level") in MIRROR_LEVEL:
            data["level"] = MIRROR_LEVEL[data["level"]]
        return data

    if kind == "pattern":
        spec = _block(data)
        if spec is not None and spec.mirror == "price":
            if data.get("pattern") in MIRROR_PATTERN:
                data["pattern"] = MIRROR_PATTERN[data["pattern"]]
        return data

    if kind == "indicator":
        spec = _block(data)
        if spec is not None and spec.mirror == "price":
            if data.get("src") in MIRROR_PRICE:
                data["src"] = MIRROR_PRICE[data["src"]]
            if data.get("ind") in MIRROR_INDICATOR:
                data["ind"] = MIRROR_INDICATOR[data["ind"]]
        return data

    if kind in {"regime", "const"} or kind is None:
        return data

    # Nodos compuestos no clasificados: se copian recursivamente.
    if "args" in data:
        data["args"] = [mirror_expr(item) for item in data.get("args") or []]
    for key in ("left", "right", "expr"):
        if isinstance(data.get(key), dict):
            data[key] = mirror_expr(data[key])
    return data


def _first_diff(expected: Any, actual: Any, path: str = "") -> str:
    if type(expected) is not type(actual):
        return f"{path or 'raíz'}: {expected!r} != {actual!r}"
    if isinstance(expected, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            child_path = f"{path}.{key}" if path else str(key)
            if key not in expected:
                return f"{child_path}: sobra en short_entry"
            if key not in actual:
                return f"{child_path}: falta en short_entry"
            if expected[key] != actual[key]:
                return _first_diff(expected[key], actual[key], child_path)
        return path or "raíz"
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path or 'raíz'}: longitud {len(expected)} != {len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual)):
            if left != right:
                return _first_diff(left, right, f"{path}[{index}]")
        return path or "raíz"
    return f"{path or 'raíz'}: {expected!r} != {actual!r}"


def mirror_errors(long_entry: Any, short_entry: Any) -> list[str]:
    """Errores de coherencia del corto; vacío si es el espejo exacto."""

    if not long_entry or not short_entry:
        return []
    expected = mirror_expr(long_entry)
    if expected == short_entry:
        return []
    return [
        "short_entry no es el espejo de long_entry según el tipo de bloque: "
        "short_entry."
        + _first_diff(expected, short_entry)
    ]


__all__ = ["mirror_errors", "mirror_expr"]
