"""Presupuesto semanal de alertas por canal y tipo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db

DEFAULT_WEEKLY_BUDGET = 40


def weekly_budget(db_path: str | Path, *, budget: int | None = None) -> dict:
    """Uso de alertas de la última semana frente al presupuesto."""
    init_db(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows: list[dict] = []
    with connect(db_path) as con:
        try:
            raw = con.execute(
                "SELECT event, channel, COUNT(*) AS n FROM alerts "
                "WHERE ts >= ? GROUP BY event, channel ORDER BY n DESC",
                (since,),
            ).fetchall()
        except Exception:
            raw = []
        for row in raw:
            rows.append(
                {
                    "event": str(row["event"]),
                    "channel": str(row["channel"] or "-"),
                    "n": int(row["n"]),
                }
            )
        try:
            stored = con.execute(
                "SELECT COUNT(*) AS n FROM alert_budget WHERE ts >= ?", (since,)
            ).fetchone()
            total = int(stored["n"])
        except Exception:
            total = sum(item["n"] for item in rows)
    limit = int(budget) if budget is not None else DEFAULT_WEEKLY_BUDGET
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "since": since,
        "budget": limit,
        "used": total,
        "remaining": max(0, limit - total),
        "exceeded": total > limit,
        "rows": rows,
    }


__all__ = ["DEFAULT_WEEKLY_BUDGET", "weekly_budget"]
