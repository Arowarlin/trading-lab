"""Embudo y disciplina: conteos de etapas y bloqueos por guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db


def funnel(db_path: str | Path) -> dict:
    """Conteos por etapa del embudo y tasa de caída."""
    init_db(db_path)
    counts: dict[str, int] = {}
    with connect(db_path) as con:
        def scalar(sql: str) -> int:
            try:
                return int(con.execute(sql).fetchone()[0])
            except Exception:
                return 0

        counts["variantes_probadas"] = scalar("SELECT COUNT(*) FROM strategy_trials")
        counts["pasan_gates"] = scalar(
            "SELECT COUNT(*) FROM strategy_trials WHERE outcome = 'passed'"
        )
        counts["candidato"] = scalar(
            "SELECT COUNT(*) FROM lifecycle_bots WHERE state = 'candidato'"
        )
        counts["incubando"] = scalar(
            "SELECT COUNT(*) FROM lifecycle_bots WHERE state = 'incubando'"
        )
        counts["evaluado"] = scalar(
            "SELECT COUNT(*) FROM lifecycle_bots WHERE state = 'evaluado'"
        )
        counts["promovible"] = scalar(
            "SELECT COUNT(*) FROM lifecycle_bots WHERE state = 'promovible'"
        )
        counts["piloto_activo"] = scalar(
            "SELECT COUNT(*) FROM lifecycle_bots WHERE state = 'promovible' AND evaluated_at IS NOT NULL"
        )
    first = counts.get("variantes_probadas", 0) or 1
    rates = {
        key: (value / first)
        for key, value in counts.items()
        if key != "variantes_probadas"
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
        "rates": rates,
    }


def discipline(db_path: str | Path, *, days: int = 30) -> dict:
    """Órdenes bloqueadas por guard en los últimos días."""
    init_db(db_path)
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    by_guard: dict[str, int] = {}
    with connect(db_path) as con:
        try:
            rows = con.execute(
                "SELECT action, COUNT(*) AS n FROM console_actions "
                "WHERE ts >= ? AND ok = 0 GROUP BY action ORDER BY n DESC",
                (since,),
            ).fetchall()
        except Exception:
            rows = []
        for row in rows:
            by_guard[str(row["action"])] = int(row["n"])
        try:
            pause = con.execute(
                "SELECT COUNT(*) AS n FROM risk_pauses WHERE paused = 1"
            ).fetchone()
            paused = int(pause["n"])
        except Exception:
            paused = 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": int(days),
        "blocked_by_guard": by_guard,
        "total_blocked": sum(by_guard.values()),
        "dias_dentro_del_colchon": paused,
    }


__all__ = ["discipline", "funnel"]
