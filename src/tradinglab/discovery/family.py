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


def _aligned(
    series: Iterable[Iterable[float]],
    dates: Iterable[Iterable[Any] | None] | None = None,
) -> np.ndarray | None:
    """Matriz (observaciones x series).

    Con fechas (ENG-1 D-04): se alinean por día, con 0 los días sin operación de
    cada serie. Sin fechas: comportamiento anterior (recorte a la más corta),
    solo para compatibilidad.
    """

    values = [np.asarray([float(v) for v in item], dtype=float) for item in series]
    date_lists = list(dates) if dates is not None else [None] * len(values)
    if date_lists and all(d is not None and len(list(d)) == len(v) for d, v in zip(date_lists, values)):
        import pandas as pd

        frames = {}
        for index, (vals, days) in enumerate(zip(values, date_lists)):
            stamps = pd.DatetimeIndex(pd.to_datetime(list(days))).normalize()
            serie = pd.Series(vals, index=stamps)
            frames[index] = serie[np.isfinite(serie.to_numpy())].groupby(level=0).sum()
        frames = {k: v for k, v in frames.items() if len(v) > 1}
        if not frames:
            return None
        joined = pd.concat(frames, axis=1, sort=True)
        calendar = pd.bdate_range(joined.index.min(), joined.index.max()).union(joined.index)
        joined = joined.reindex(calendar).fillna(0.0)
        return joined.to_numpy(dtype=float) if len(joined) >= 2 else None
    arrays = [array[np.isfinite(array)] for array in values if len(array) > 1]
    if not arrays:
        return None
    length = min(len(array) for array in arrays)
    if length < 2:
        return None
    return np.column_stack([array[:length] for array in arrays])


def spa_test(
    series: Iterable[Iterable[float]],
    *,
    dates: Iterable[Iterable[Any] | None] | None = None,
    block_size: int = 1,
    reps: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    """p-valor SPA de Hansen (2005), studentizado, con bootstrap estacionario.

    H0: ninguna serie tiene media positiva (referencia = 0). ENG-1 D-04: antes
    no se studentizaba, el bloque salía casi siempre 1 y las series se
    emparejaban por posición. Ahora se usa ``arch.bootstrap.SPA`` (p consistente),
    el bloque es el mayor entre ``block_size`` (duración media de las
    operaciones) y la longitud óptima estimada, y las series se alinean por
    fecha cuando hay fechas.
    """

    matrix = _aligned(series, dates)
    minimum = max(1, int(block_size))
    if matrix is None:
        return {"status": "Sin datos", "p_value": None, "n_series": 0, "block_size": minimum}
    from arch.bootstrap import SPA, optimal_block_length

    observations, models = matrix.shape
    try:
        automatic = float(optimal_block_length(matrix.mean(axis=1))["stationary"].iloc[0])
    except Exception:  # noqa: BLE001 - sin estimación, se usa el mínimo
        automatic = 1.0
    block = int(min(max(minimum, math.ceil(automatic)), max(1, observations // 2)))
    spa = SPA(
        np.zeros(observations),
        -matrix,
        block_size=block,
        reps=int(reps),
        bootstrap="stationary",
        studentize=True,
        seed=int(seed),
    )
    spa.compute()
    p_value = float(spa.pvalues["consistent"])
    return {
        "status": "ok",
        "p_value": p_value,
        "p_values": {key: float(value) for key, value in spa.pvalues.items()},
        "n_series": int(models),
        "observations": int(observations),
        "block_size": block,
        "block_size_min": minimum,
        "block_size_auto": automatic,
        "reps": int(reps),
        "method": "hansen_spa_studentized",
        "aligned_by_date": dates is not None,
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
                    "dates": metrics.get("return_dates"),
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
    dates = [item.get("dates") for item in selected]
    result = spa_test(
        [item["returns"] for item in selected],
        dates=dates if all(d and len(d) == len(i["returns"]) for d, i in zip(dates, selected)) else None,
        block_size=block_size,
        reps=reps,
        seed=seed,
    )
    result["family"] = str(family)
    result["campaigns"] = [item["campaign_id"] for item in selected]
    return result


__all__ = ["family_test", "spa_test"]
