"""Monitor de preparación de F13 y decisiones. Solo lectura."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import Settings
from .db import connect, init_db
from .llm import schema_summary

MIN_DECISIONS = 30


def readiness(
    db_path: str | Path,
    *,
    settings: Settings | None = None,
    today: date | None = None,
) -> dict:
    settings = settings or Settings()
    day = today or datetime.now(timezone.utc).date()
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT mode, COUNT(*) AS n, "
            "SUM(CASE WHEN return_20d IS NOT NULL THEN 1 ELSE 0 END) AS with_20d "
            "FROM decision_outcomes GROUP BY mode ORDER BY mode"
        ).fetchall()
        total = sum(int(row["n"]) for row in rows)
        with_20d = sum(int(row["with_20d"] or 0) for row in rows)
        events = con.execute(
            "SELECT event, ts_utc, importance FROM macro_events "
            "WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc LIMIT 10",
            (
                datetime.now(timezone.utc).isoformat(),
                (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
            ),
        ).fetchall()
        f13 = con.execute("SELECT * FROM f13_config WHERE id = 1").fetchone()
    f13_data = dict(f13) if f13 else None
    days_in_paper = None
    if f13_data and f13_data.get("start_date"):
        try:
            days_in_paper = max(
                0, (day - date.fromisoformat(str(f13_data["start_date"]))).days
            )
        except ValueError:
            days_in_paper = None
    return {
        "date": day.isoformat(),
        "mode": settings.mode,
        "f13": f13_data,
        "days_in_paper": days_in_paper,
        "decisions": {
            "total": total,
            "with_20d": with_20d,
            "pending": max(0, total - with_20d),
            "needed": max(0, MIN_DECISIONS - with_20d),
            "by_mode": [dict(row) for row in rows],
        },
        "calendar": [dict(row) for row in events],
        "llm_schema": schema_summary(db_path),
    }


__all__ = ["MIN_DECISIONS", "readiness"]
