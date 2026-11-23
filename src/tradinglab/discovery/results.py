"""Lectura de resultados de una campaña (R2k/C1): solo IS, nunca OOS-2."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


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
            " n_evaluated, n_effective, n_finalists, approved_at"
            " FROM disc_campaigns WHERE id = ?",
            (str(campaign_id),),
        ).fetchone()
        if campaign is None:
            raise KeyError(f"campaña no registrada: {campaign_id}")
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
            params: dict[str, Any] = {}
            try:
                params = {
                    "threshold": dsl["long_entry"]["args"][1]["params"]["threshold"],
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
                    "verdict": row["verdict"],
                    "reason": reason or "",
                }
            )
        return {
            "campaign": {
                **dict(campaign),
                "n_finalists": int(campaign["n_finalists"] or 0),
            },
            "rows": rows,
            "read_only": True,
        }
    finally:
        con.close()


__all__ = ["campaign_results"]
