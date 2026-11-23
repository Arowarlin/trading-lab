"""Lectura de resultados de una campaña: solo IS, nunca OOS-2."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


def _resolve_path(payload: Any, path: str) -> Any:
    """Resuelve ``a.b[0].c`` sobre el DSL guardado."""

    current = payload
    for part in re.sub(r"\[(\d+)\]", r".\1", str(path)).split("."):
        if not part:
            continue
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _grid_params(campaign: dict[str, Any], dsl: dict[str, Any]) -> dict[str, Any]:
    config = campaign.get("config") or {}
    dimensions = (config.get("grid") or {}).get("dimensions") or []
    params: dict[str, Any] = {}
    for dimension in dimensions:
        name = dimension.get("name")
        path = dimension.get("path")
        if not name or not path:
            continue
        try:
            params[str(name)] = _resolve_path(dsl, str(path))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return params


def _selection_verdict(
    stored: Any, status: Any, rank: Any
) -> tuple[str, str]:
    text = str(stored or "").strip()
    if text:
        return text, "stored"
    state = str(status or "")
    if state == "finalist":
        return "FINALISTA", "selection"
    if state == "discarded":
        return "DESCARTADO", "selection"
    if state == "evaluated":
        if rank is not None and int(rank) > 0:
            return "NO FINALISTA", "selection"
        return "EVALUADO", "selection"
    return "SIN VEREDICTO", "selection"


def campaign_results(
    campaign_id: str, *, db_path: str | Path = "data/discovery.db"
) -> dict[str, Any]:
    target = Path(db_path)
    if not target.exists():
        raise FileNotFoundError(f"Sin datos: no existe {target}")
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        campaign = con.execute(
            "SELECT id, instrument, timeframe, template, status, n_total,"
            " n_evaluated, n_effective, n_finalists, approved_at, config_json"
            " FROM disc_campaigns WHERE id = ?",
            (str(campaign_id),),
        ).fetchone()
        if campaign is None:
            raise KeyError(f"campaña no registrada: {campaign_id}")
        campaign_data = dict(campaign)
        campaign_data["config"] = json.loads(
            campaign_data.pop("config_json") or "{}"
        )
        rows = []
        for row in con.execute(
            "SELECT s.id, s.dsl_json, s.level, s.status, s.verdict,"
            " s.selection_reason, l.rank, e.metrics_json"
            " FROM disc_strategies s"
            " LEFT JOIN disc_lineage l ON l.strategy_id = s.id"
            " LEFT JOIN disc_evaluations e ON e.strategy_id = s.id"
            " AND e.segment = 'fitness_is'"
            " WHERE s.campaign_id = ? ORDER BY s.id",
            (str(campaign_id),),
        ):
            dsl = json.loads(row["dsl_json"] or "{}")
            metrics = json.loads(row["metrics_json"] or "{}")
            isd = metrics.get("is") or {}
            params = _grid_params(campaign_data, dsl)
            if not params:
                try:
                    params = {
                        "threshold": dsl["long_entry"]["args"][1]["params"][
                            "threshold"
                        ],
                        "stop": dsl["exit"]["stop"]["mult"],
                        "target_rr": dsl["exit"]["target"]["rr"],
                    }
                except (KeyError, IndexError, TypeError):
                    params = {}
            folds = metrics.get("folds") or []
            positive = sum(
                1
                for fold in folds
                if fold.get("expectancy_r") is not None
                and float(fold["expectancy_r"]) > 0
            )
            rank = row["rank"]
            reason = row["selection_reason"]
            if not reason and rank is not None and int(rank) > 0:
                reason = f"rank {rank} > 0 (dominada, fuera del frente)"
            gross = isd.get("gross_expectancy_r")
            costs = isd.get("cost_by_account") or {}
            verdict, verdict_source = _selection_verdict(
                row["verdict"], row["status"], rank
            )
            rows.append(
                {
                    "id": int(row["id"]),
                    "params": params,
                    "trades": isd.get("trades"),
                    "gross_r": gross,
                    "net_r": isd.get("expectancy_r"),
                    "cost_by_account": costs,
                    "profit_factor": isd.get("profit_factor"),
                    "positive_folds": positive,
                    "folds": len(folds),
                    "rank": rank,
                    "level": int(row["level"] or 1),
                    "status": row["status"],
                    "verdict": verdict,
                    "verdict_source": verdict_source,
                    "reason": reason or "",
                }
            )
        return {
            "campaign": {
                **campaign_data,
                "n_finalists": int(campaign_data["n_finalists"] or 0),
            },
            "rows": rows,
            "read_only": True,
        }
    finally:
        con.close()


__all__ = ["campaign_results"]
