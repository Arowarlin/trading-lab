from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategyResult:
    """Resultado de una estrategia.

    `target` es la exposición deseada (0.0 a 1.0) **decidida al cierre** de cada barra.
    El motor de ejecución la aplica en la apertura de la barra siguiente.
    """

    name: str
    target: pd.Series
    params: dict = field(default_factory=dict)


def clamp_target(series: pd.Series) -> pd.Series:
    return series.astype(float).clip(0.0, 1.0).fillna(0.0)


def exposure_multiplier(
    flags: dict[str, bool] | None,
    table: dict[str, float] | None = None,
) -> float:
    """Multiplicador de exposición según los condicionadores activos.

    `table` mapea flag → multiplicador (por defecto 1,0 para todos). El
    multiplicador total es el producto de los flags activos. Si no hay tabla,
    nada cambia.
    """
    if not flags:
        return 1.0
    factors = table or {}
    total = 1.0
    for flag, active in flags.items():
        if not active:
            continue
        try:
            total *= float(factors.get(flag, 1.0))
        except (TypeError, ValueError):
            continue
    return float(total)
