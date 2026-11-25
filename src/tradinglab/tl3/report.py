"""T4 · Escalera bruto → neto por componente."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

MDE_RULE = 2.49
STEPS = ("gross", "spread", "commission", "slippage", "swap")


def _summary(values: np.ndarray, *, n_boot: int, seed: int) -> dict[str, Any]:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"n": 0, "mean": None, "ci95": None, "mde": None}
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(n_boot, values.size), replace=True).mean(axis=1)
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "ci95": (
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)),
        ),
        "mde": MDE_RULE * float(values.std(ddof=1)) / np.sqrt(values.size)
        if values.size > 1
        else None,
    }


def ladder(
    trades: Iterable[dict[str, Any]] | pd.DataFrame,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    frame = pd.DataFrame(list(trades)) if not isinstance(trades, pd.DataFrame) else trades.copy()
    missing = [column for column in STEPS if column not in frame.columns]
    if missing:
        raise ValueError("faltan columnas: " + ", ".join(missing))
    net = frame["gross"].astype(float)
    rows = [{"step": "gross", **_summary(net.to_numpy(float), n_boot=n_boot, seed=seed)}]
    for step in STEPS[1:]:
        net = net - frame[step].astype(float)
        rows.append(
            {
                "step": f"-{step}",
                **_summary(net.to_numpy(float), n_boot=n_boot, seed=seed),
            }
        )
    return {"steps": rows, "net": rows[-1]}


__all__ = ["STEPS", "ladder"]
