"""Control por familia con SPA de Hansen (T23).

Aplica el test SPA a las series diarias de R de las primarias v2 de una
familia, con bootstrap estacionario de bloque igual a la duración media de las
operaciones (en días, mínimo 1). Solo lectura de `discovery.db`.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from . import databank, results
from .timeframes import timeframe_minutes


def _aligned(series: Iterable[Iterable[float]]) -> np.ndarray | None:
    arrays = [
        np.asarray([float(value) for value in values], dtype=float)
        for values in series
    ]
    arrays = [array[np.isfinite(array)] for array in arrays if len(array) > 1]
    if not arrays:
        return None
    length = min(len(array) for array in arrays)
    if length < 2:
        return None
    return np.column_stack([array[:length] for array in arrays])


def spa_test(
    series: Iterable[Iterable[float]],
    *,
    block_size: int = 1,
    reps: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    """p-valor SPA (Hansen) con bootstrap estacionario."""

    matrix = _aligned(series)
    if matrix is None:
        return {
            "status": "Sin datos",
            "p_value": None,
            "n_series": 0,
            "block_size": max(1, int(block_size)),
        }
    from arch.bootstrap import StationaryBootstrap

    observations, models = matrix.shape
    means = matrix.mean(axis=0)
    statistic = float(np.max(math.sqrt(observations) * means))
    boot = StationaryBootstrap(
        max(1, int(block_size)), np.arange(observations), seed=int(seed)
    )
    exceed = 0
    for data in boot.bootstrap(int(reps)):
        indices = np.asarray(data[0][0], dtype=int).reshape(-1)
        sampled = matrix[indices].mean(axis=0)
        boot_stat = float(
            np.max(math.sqrt(observations) * (sampled - means))
        )
        if boot_stat >= statistic:
            exceed += 1
    p_value = (exceed + 1.0) / (int(reps) + 1.0)
    return {
        "status": "ok",
        "p_value": float(p_value),
        "n_series": int(models),
        "observations": int(observations),
        "block_size": max(1, int(block_size)),
        "statistic": statistic,
        "reps": int(reps),
    }


def family_test(
    family: str,
    *,
    db_path: str | Path | None = None,
    reps: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    """Series de las primarias v2 de la familia; Sin datos si no hay ninguna."""

    target = Path(db_path or databank.DEFAULT_DISCOVERY_DB)
    if not target.exists():
        return {
            "status": "Sin datos",
            "family": str(family),
            "reason": "no existe discovery.db",
            "p_value": None,
            "n_series": 0,
        }
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, timeframe, config_json FROM disc_campaigns"
            " WHERE approved_at IS NOT NULL"
            " AND COALESCE(status, '') != 'superseded'"
        ).fetchall()
        selected: list[dict[str, Any]] = []
        for row in rows:
            try:
                config = json.loads(row["config_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if (
                str(config.get("family") or "") != str(family)
                or int(config.get("protocol_version") or 1) < 2
                or not config.get("primary")
            ):
                continue
            campaign = {
                "id": row["id"],
                "timeframe": row["timeframe"],
                "config": config,
            }
            strategies = con.execute(
                "SELECT id, dsl_json FROM disc_strategies WHERE campaign_id = ?",
                (row["id"],),
            ).fetchall()
            primary_id = None
            for strategy in strategies:
                try:
                    dsl = json.loads(strategy["dsl_json"] or "{}")
                except (TypeError, ValueError):
                    continue
                params = results._grid_params(campaign, dsl)
                from .plateau import matches

                if matches(params, config.get("primary")):
                    primary_id = int(strategy["id"])
                    break
            if primary_id is None:
                continue
            evaluation = con.execute(
                "SELECT returns_blob, metrics_json FROM disc_evaluations"
                " WHERE strategy_id = ? AND segment IN ('fitness_is', 'oos1')"
                " ORDER BY id DESC LIMIT 1",
                (primary_id,),
            ).fetchone()
            if evaluation is None:
                continue
            values = databank.decode_returns(evaluation["returns_blob"])
            if len(values) < 2:
                continue
            metrics = {}
            try:
                metrics = json.loads(evaluation["metrics_json"] or "{}")
            except (TypeError, ValueError):
                pass
            minutes = timeframe_minutes(str(row["timeframe"] or "M5"))
            mean_bars = metrics.get("mean_bars") or 0.0
            holding_days = (
                float(mean_bars) * float(minutes) / 1440.0
                if mean_bars
                else 1.0
            )
            selected.append(
                {
                    "campaign_id": str(row["id"]),
                    "returns": values,
                    "holding_days": holding_days,
                }
            )
    finally:
        con.close()
    if not selected:
        return {
            "status": "Sin datos",
            "family": str(family),
            "reason": "no hay primarias v2 de la familia",
            "p_value": None,
            "n_series": 0,
        }
    block_size = max(
        1,
        int(
            round(
                sum(item["holding_days"] for item in selected)
                / len(selected)
            )
        ),
    )
    result = spa_test(
        [item["returns"] for item in selected],
        block_size=block_size,
        reps=reps,
        seed=seed,
    )
    result["family"] = str(family)
    result["campaigns"] = [item["campaign_id"] for item in selected]
    return result


__all__ = ["family_test", "spa_test"]
