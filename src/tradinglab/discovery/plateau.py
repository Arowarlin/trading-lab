"""Especificación primaria y meseta (T21).

La decisión usa solo la primaria; la rejilla solo comprueba que hay una
meseta: fracción de puntos con expectativa neta > 0, mínimo 0,6.
"""

from __future__ import annotations

from typing import Any, Iterable

MIN_PLATEAU = 0.6


def fraction(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return sum(1 for value in clean if value > 0.0) / len(clean)


def summary(values: Iterable[float | None]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None]
    value = fraction(clean)
    return {
        "plateau_n": len(clean),
        "plateau_pct": value,
        "plateau_ok": bool(value is not None and value >= MIN_PLATEAU),
        "plateau_min": MIN_PLATEAU,
    }


def matches(params: dict[str, Any], primary: dict[str, Any] | None) -> bool:
    if not primary:
        return False
    for key, expected in primary.items():
        if key not in params:
            return False
        actual = params[key]
        try:
            if abs(float(actual) - float(expected)) > 1e-9:
                return False
        except (TypeError, ValueError):
            if str(actual) != str(expected):
                return False
    return True


def primary_hash(
    campaign: dict[str, Any],
    individuals: Iterable[Any],
) -> str | None:
    """``strategy_hash`` del individuo que coincide con la primaria."""

    from . import results

    primary = (campaign.get("config") or {}).get("primary")
    if not primary:
        return None
    for item in individuals:
        params = results._grid_params(campaign, item.strategy)
        if matches(params, primary):
            return str(item.strategy_hash)
    return None


__all__ = [
    "MIN_PLATEAU",
    "fraction",
    "matches",
    "primary_hash",
    "summary",
]
