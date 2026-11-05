from __future__ import annotations

import pandas as pd

from ..indicators import zscore
from .base import StrategyResult, clamp_target


def meanrev_signal(
    df: pd.DataFrame,
    window: int = 20,
    entry_z: float = -2.0,
    exit_z: float = 0.0,
    max_hold: int = 10,
) -> StrategyResult:
    """Reversión a la media long-only sobre z-score del precio.

    Compra cuando el precio cae 2 desviaciones bajo su media de 20 sesiones.
    Vende cuando vuelve a la media o tras `max_hold` sesiones.
    """
    close = df["close"]
    z = zscore(close, window)

    target = pd.Series(0.0, index=close.index)
    holding = False
    days_held = 0

    for i in range(len(z)):
        value = z.iloc[i]
        if pd.isna(value):
            target.iloc[i] = float(holding)
            continue

        if not holding:
            if value <= entry_z:
                holding = True
                days_held = 0
        else:
            days_held += 1
            if value >= exit_z or days_held >= max_hold:
                holding = False

        target.iloc[i] = float(holding)

    return StrategyResult(
        name="meanrev",
        target=clamp_target(target),
        params={"window": window, "entry_z": entry_z, "exit_z": exit_z, "max_hold": max_hold},
    )
