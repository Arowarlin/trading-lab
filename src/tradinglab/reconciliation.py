"""Reconciliación diaria broker vs SQLite.

Cualquier diferencia no explicada genera una fila en `reconciliation` y una
alerta. No corrige posiciones automáticamente: primero se investiga.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .alerts import send as send_alert
from .db import connect, init_db, utcnow


@dataclass(frozen=True)
class ReconciliationResult:
    source: str
    broker_equity: float | None
    db_equity: float | None
    diff_equity: float | None
    broker_positions: int
    db_positions: int
    diff_positions: int
    status: str
    details: str


def _tolerance(equity: float | None) -> float:
    # $1 o 0.1% del equity, lo que sea mayor.
    return max(1.0, abs(equity or 0.0) * 0.001)


def reconcile(broker, db_path: str | Path, *, source: str | None = None) -> ReconciliationResult:
    init_db(db_path)
    snap = broker.snapshot({})
    broker_equity = float(snap.get("equity") or 0.0)
    broker_positions = {
        str(p["ticker"]).upper(): float(p["qty"])
        for p in (snap.get("positions") or [])
        if abs(float(p["qty"])) > 1e-9
    }

    with connect(db_path) as con:
        rows = con.execute("SELECT ticker, qty FROM positions").fetchall()
        db_positions = {str(r["ticker"]).upper(): float(r["qty"]) for r in rows if abs(float(r["qty"])) > 1e-9}
        equity_row = con.execute("SELECT equity FROM equity ORDER BY id DESC LIMIT 1").fetchone()
        db_equity = float(equity_row["equity"]) if equity_row else None

    diff_equity = broker_equity - db_equity if db_equity is not None else None
    all_tickers = set(broker_positions) | set(db_positions)
    diff_positions = sum(
        1
        for ticker in all_tickers
        if abs(broker_positions.get(ticker, 0.0) - db_positions.get(ticker, 0.0)) > 1e-6
    )
    details: list[str] = []
    if diff_positions:
        details.append(f"{diff_positions} posiciones distintas")
    if diff_equity is not None and abs(diff_equity) > _tolerance(db_equity):
        details.append(f"equity broker={broker_equity:,.2f} db={db_equity:,.2f}")
    if db_equity is None:
        details.append("DB sin snapshots de equity")

    status = "ok" if not details else "mismatch"
    result = ReconciliationResult(
        source=source or "broker",
        broker_equity=broker_equity,
        db_equity=db_equity,
        diff_equity=diff_equity,
        broker_positions=len(broker_positions),
        db_positions=len(db_positions),
        diff_positions=diff_positions,
        status=status,
        details="; ".join(details),
    )

    with connect(db_path) as con:
        con.execute(
            "INSERT INTO reconciliation"
            "(ts, source, broker_equity, db_equity, diff_equity, broker_positions, "
            "db_positions, diff_positions, status, details) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                result.source,
                result.broker_equity,
                result.db_equity,
                result.diff_equity,
                result.broker_positions,
                result.db_positions,
                result.diff_positions,
                result.status,
                result.details,
            ),
        )

    if status != "ok":
        send_alert(
            "reconciliation_mismatch",
            f"{result.source}: {result.details}",
            severity="error",
            db_path=db_path,
        )
    return result


def last_reconciliation(db_path: str | Path) -> dict | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM reconciliation ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


__all__ = ["ReconciliationResult", "last_reconciliation", "reconcile"]
