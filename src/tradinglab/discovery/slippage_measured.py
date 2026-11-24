"""Slippage medido desde fills y TCA (T12).

Solo lectura sobre ``lab.db``. Calcula la mediana y el p75 de
``|fill − precio solicitado|`` por símbolo, cuenta, tipo de orden y franja de
4 horas, con su ``n``. Con ``n ≥ 30`` propone ``source: measured``; con menos,
mantiene el supuesto actual y lo marca.

Nunca sobrescribe ``config/propfund/costs.yaml``: escribe una propuesta en
``config/propfund/costs.measured.yaml``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..config import DEFAULT_DB, ROOT

MIN_FILLS = 30
COSTS_PATH = ROOT / "config" / "propfund" / "costs.yaml"
PROPOSAL_PATH = ROOT / "config" / "propfund" / "costs.measured.yaml"


@dataclass(frozen=True)
class SlippageCell:
    symbol: str
    account: str
    order_type: str
    band: str
    n: int
    median_price: float | None
    p75_price: float | None

    @property
    def status(self) -> str:
        return "measured" if self.n >= MIN_FILLS else "Sin datos"


def _band(hour: int) -> str:
    start = (int(hour) // 4) * 4
    return f"{start:02d}-{start + 4:02d}"


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _order_lookup(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT id, ts, ticker, order_type FROM orders"
        " WHERE status = 'filled' AND order_type IS NOT NULL"
    ).fetchall()
    return [dict(row) for row in rows]


def _match_order(
    orders: list[dict[str, Any]],
    *,
    symbol: str,
    when: datetime | None,
) -> dict[str, Any] | None:
    if when is None:
        return None
    best = None
    best_delta = 121.0
    for row in orders:
        if str(row.get("ticker") or "").upper() != symbol.upper():
            continue
        other = _parse_ts(row.get("ts"))
        if other is None:
            continue
        delta = abs((other - when).total_seconds())
        if delta < best_delta:
            best = row
            best_delta = delta
    return best


def _account_lookup(con: sqlite3.Connection) -> dict[int, str]:
    rows = con.execute(
        "SELECT order_id, account_id FROM order_accounts"
    ).fetchall()
    return {int(row["order_id"]): str(row["account_id"]) for row in rows}


def measure_slippage(
    db_path: str | Path = DEFAULT_DB,
    *,
    min_fills: int = MIN_FILLS,
) -> list[SlippageCell]:
    """Celdas símbolo × cuenta × tipo × franja de 4 h con mediana y p75."""

    path = Path(db_path)
    if not path.exists():
        return []
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        orders = _order_lookup(con)
        rows = con.execute(
            "SELECT t.id, t.symbol, t.account, t.side, t.order_px, t.fill_px,"
            " t.ts_utc, t.fill_id, o.account_id"
            " FROM tca t LEFT JOIN order_accounts o ON o.order_id = t.fill_id"
            " WHERE t.order_px IS NOT NULL AND t.fill_px IS NOT NULL"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()

    grouped: dict[tuple[str, str, str, str], list[float]] = {}
    for row in rows:
        order_px = row["order_px"]
        fill_px = row["fill_px"]
        if order_px is None or fill_px is None:
            continue
        symbol = str(row["symbol"] or "Sin datos").upper()
        when = _parse_ts(row["ts_utc"])
        matched = _match_order(orders, symbol=symbol, when=when)
        order_type = (
            str(matched.get("order_type") or "market") if matched else "market"
        )
        account = (
            str(row["account_id"])
            if row["account_id"]
            else str(row["account"] or "Sin datos")
        )
        band = _band(when.hour) if when is not None else "Sin datos"
        value = abs(float(fill_px) - float(order_px))
        grouped.setdefault((symbol, account, order_type, band), []).append(value)

    cells: list[SlippageCell] = []
    for (symbol, account, order_type, band), values in sorted(grouped.items()):
        array = np.asarray(values, dtype=float)
        cells.append(
            SlippageCell(
                symbol=symbol,
                account=account,
                order_type=order_type,
                band=band,
                n=len(array),
                median_price=float(np.median(array)),
                p75_price=float(np.percentile(array, 75)),
            )
        )
    return cells


def fills_inventory(db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    """Inventario de las tablas de fills; solo lectura."""

    path = Path(db_path)
    if not path.exists():
        return {"error": "Sin datos: no existe lab.db"}
    uri = f"file:{path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        tables = {}
        for table in ("fills", "tca", "orders"):
            try:
                tables[table] = int(
                    con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                )
            except sqlite3.Error:
                tables[table] = 0
        by_fill = [
            dict(row)
            for row in con.execute(
                "SELECT account, symbol, side, COUNT(*) AS n FROM fills"
                " GROUP BY account, symbol, side ORDER BY n DESC"
            )
        ]
        by_tca = [
            dict(row)
            for row in con.execute(
                "SELECT bot, symbol, side, COUNT(*) AS n FROM tca"
                " GROUP BY bot, symbol, side ORDER BY n DESC"
            )
        ]
        by_type = [
            dict(row)
            for row in con.execute(
                "SELECT order_type, COUNT(*) AS n FROM orders"
                " GROUP BY order_type ORDER BY n DESC"
            )
        ]
    except sqlite3.Error as exc:
        return {"error": f"Sin datos: {exc}"}
    finally:
        con.close()
    return {
        "tables": tables,
        "fills": by_fill,
        "tca": by_tca,
        "orders_by_type": by_type,
    }


def build_proposal(
    cells: list[SlippageCell],
    *,
    costs_path: str | Path = COSTS_PATH,
    measured_at: datetime | None = None,
    min_fills: int = MIN_FILLS,
) -> dict[str, Any]:
    """Construye la propuesta sin tocar ``costs.yaml``."""

    current = yaml.safe_load(Path(costs_path).read_text(encoding="utf-8")) or {}
    moment = (measured_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    proposal_accounts: dict[str, Any] = {}
    for account, block in (current.get("accounts") or {}).items():
        symbols: dict[str, Any] = {}
        for symbol, item in (block.get("symbols") or {}).items():
            symbol_cells = [
                cell
                for cell in cells
                if cell.symbol == symbol.upper()
            ]
            total = sum(cell.n for cell in symbol_cells)
            measured = total >= int(min_fills)
            if measured:
                weighted = sum(
                    (cell.median_price or 0.0) * cell.n for cell in symbol_cells
                )
                value = weighted / total if total else None
                source = "measured"
                date = moment
                n = total
                median = value
                p75 = max(
                    (cell.p75_price or 0.0) for cell in symbol_cells
                )
            else:
                value = item.get("slippage_price")
                source = "assumption"
                date = None
                n = total
                median = None
                p75 = None
            symbols[symbol] = {
                "slippage_price": value,
                "source": source,
                "measured_at": date,
                "n": n,
                "median_price": median,
                "p75_price": p75,
            }
        proposal_accounts[account] = {"symbols": symbols}
    return {
        "version": 1,
        "generated_at": moment,
        "note": (
            "Propuesta de slippage medido. No se aplica sola: el operador "
            "decide. Las celdas con n < 30 conservan el supuesto actual."
        ),
        "accounts": proposal_accounts,
        "cells": [asdict(cell) | {"status": cell.status} for cell in cells],
    }


def write_proposal(
    proposal: dict[str, Any],
    *,
    path: str | Path = PROPOSAL_PATH,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(proposal, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return target


__all__ = [
    "COSTS_PATH",
    "MIN_FILLS",
    "PROPOSAL_PATH",
    "SlippageCell",
    "build_proposal",
    "fills_inventory",
    "measure_slippage",
    "write_proposal",
]
