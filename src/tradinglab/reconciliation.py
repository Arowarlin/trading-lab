"""Reconciliación diaria broker vs SQLite.

Cualquier diferencia no explicada genera una fila en `reconciliation` y una
alerta. No corrige posiciones automáticamente: primero se investiga.
"""

from __future__ import annotations

from collections import defaultdict
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


def expected_positions(
    db_path: str | Path,
    *,
    account_id: str,
    bot: str | None = None,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """Posiciones esperadas por símbolo y por bot, a partir de `fills`.

    `fills.account` es la frontera entre cuentas. Para Alpaca se escribe en el
    momento del fill; así F13 (QQQ) y el daytrader (AAPL) se pueden reconciliar
    por separado aunque compartan la misma cuenta del bróker.
    """
    init_db(db_path)
    query = (
        "SELECT bot, symbol, side, qty FROM fills "
        "WHERE account = ? AND symbol IS NOT NULL "
        "AND side IN ('buy','sell')"
    )
    params: list[object] = [account_id]
    if bot:
        query += " AND bot = ?"
        params.append(bot)
    with connect(db_path) as con:
        rows = con.execute(query, tuple(params)).fetchall()

    net: dict[str, float] = defaultdict(float)
    by_bot: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        symbol = str(row["symbol"]).upper()
        qty = abs(float(row["qty"] or 0.0))
        sign = 1.0 if str(row["side"]).lower() == "buy" else -1.0
        net[symbol] += sign * qty
        label = str(row["bot"] or "manual")
        by_bot[label][symbol] += sign * qty
    clean = {symbol: qty for symbol, qty in net.items() if abs(qty) > 1e-9}
    clean_by_bot = {
        label: {
            symbol: qty
            for symbol, qty in symbols.items()
            if abs(qty) > 1e-9
        }
        for label, symbols in by_bot.items()
    }
    return clean, clean_by_bot


def reconcile_account(
    broker,
    db_path: str | Path,
    *,
    account_id: str,
    source: str | None = None,
) -> ReconciliationResult:
    """Reconcilia una cuenta de bróker separando las posiciones por bot.

    A diferencia de `reconcile`, la equity no se compara: es de toda la cuenta
    y no se puede atribuir a un bot. Lo que se exige es que cada símbolo del
    bróker tenga exactamente los fills registrados para esa cuenta.
    """
    init_db(db_path)
    sync_error = ""
    sync = getattr(broker, "sync_fills", None)
    if callable(sync):
        try:
            sync()
        except Exception as exc:
            sync_error = str(exc)[:200]

    snap = broker.snapshot({})
    broker_equity = float(snap.get("equity") or 0.0)
    broker_positions = {
        str(p["ticker"]).upper(): float(p["qty"])
        for p in (snap.get("positions") or [])
        if abs(float(p["qty"])) > 1e-9
    }
    expected, by_bot = expected_positions(db_path, account_id=account_id)

    tickers = set(broker_positions) | set(expected)
    diffs = [
        ticker
        for ticker in sorted(tickers)
        if abs(broker_positions.get(ticker, 0.0) - expected.get(ticker, 0.0)) > 1e-6
    ]

    details: list[str] = []
    if diffs:
        details.append(f"{len(diffs)} posiciones distintas")
        for ticker in diffs:
            details.append(
                f"{ticker} broker={broker_positions.get(ticker, 0.0):g} "
                f"db={expected.get(ticker, 0.0):g}"
            )
    if by_bot:
        parts = []
        for label in sorted(by_bot):
            positions = ", ".join(
                f"{symbol}={qty:g}" for symbol, qty in sorted(by_bot[label].items())
            )
            parts.append(f"{label}: {positions}")
        details.append("por bot: " + "; ".join(parts))
    if sync_error:
        details.append(f"sync fills: {sync_error}")
    if not details:
        details.append("sin diferencias")

    status = "ok" if not diffs and not sync_error else "mismatch"
    result = ReconciliationResult(
        source=source or f"account:{account_id}",
        broker_equity=broker_equity,
        db_equity=None,
        diff_equity=None,
        broker_positions=len(broker_positions),
        db_positions=len(expected),
        diff_positions=len(diffs),
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


__all__ = [
    "ReconciliationResult",
    "expected_positions",
    "last_reconciliation",
    "reconcile",
    "reconcile_account",
]
