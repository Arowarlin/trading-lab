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
