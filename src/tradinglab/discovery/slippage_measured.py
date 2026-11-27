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
from datetime import datetime, timedelta, timezone
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
    origin: str = "tca"

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


MT5_ACCOUNTS = (
    {
        "account": "CFD-001",
        "path": r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe",
        "login": 1515349730,
        "server": "FTMO-Demo",
    },
    {
        "account": "CFD-006",
        "path": r"C:\Program Files\Darwinex MetaTrader 5\terminal64.exe",
        "login": 40000459328,
        "server": "FundingPips-Trial",
    },
)
ORDER_TYPE_NAMES = {
    0: "market",
    1: "market",
    2: "limit",
    3: "limit",
    4: "stop",
    5: "stop",
    6: "stop_limit",
    7: "stop_limit",
}
_BUY_ORDER_TYPES = {0, 2, 4, 6}


def read_mt5_history(
    path: str,
    login: int,
    *,
    days: int = 90,
    server: str | None = None,
) -> dict[str, Any] | None:
    """Adjunta al terminal y lee historial. Solo lectura; ``None`` si no cuadra."""

    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        return None
    if not mt5.initialize(path=path, timeout=60_000):
        return None
    try:
        account = mt5.account_info()
        if account is None or int(account.login) != int(login):
            return None
        if server and str(account.server).strip().lower() != str(server).strip().lower():
            return None
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(days))
        orders = mt5.history_orders_get(start, end + timedelta(days=1)) or []
        deals = mt5.history_deals_get(start, end + timedelta(days=1)) or []
        after = mt5.account_info()
        if after is None or int(after.login) != int(login):
            return None
        return {
            "account": str(login),
            "server": str(account.server),
            "orders": [order._asdict() for order in orders],
            "deals": [deal._asdict() for deal in deals],
        }
    finally:
        mt5.shutdown()


def _cells_from_history(
    history: dict[str, Any], account: str
) -> list[SlippageCell]:
    """Celdas con slippage firmado (positivo = peor) a partir de órdenes/deals."""

    deals_by_order = {
        int(deal.get("order") or 0): deal
        for deal in history.get("deals") or []
        if int(deal.get("order") or 0) > 0
    }
    grouped: dict[tuple[str, str, str, str, str], list[float]] = {}
    for order in history.get("orders") or []:
        raw_type = order.get("type")
        if raw_type is None:
            continue
        order_type = ORDER_TYPE_NAMES.get(int(raw_type))
        if order_type is None:
            continue
        reference = float(order.get("price_open") or 0.0)
        if order_type in {"stop", "stop_limit"}:
            stop_limit = float(order.get("price_stoplimit") or 0.0)
            reference = stop_limit if stop_limit > 0.0 else reference
        deal = deals_by_order.get(int(order.get("ticket") or 0))
        if deal is None or reference <= 0.0:
            continue
        fill = float(deal.get("price") or 0.0)
        if fill <= 0.0:
            continue
        if int(raw_type) in _BUY_ORDER_TYPES:
            slippage = fill - reference
        else:
            slippage = reference - fill
        when = datetime.fromtimestamp(int(deal.get("time") or 0), tz=timezone.utc)
        band = _band(when.hour)
        magic = int(order.get("magic") or 0)
        comment = str(order.get("comment") or "").lower()
        if magic:
            origin = f"ea:{magic}"
        elif "ai" in comment:
            origin = "ai_trader"
        else:
            origin = "manual"
        symbol = str(order.get("symbol") or "Sin datos").upper()
        grouped.setdefault(
            (symbol, account, order_type, band, origin), []
        ).append(slippage)
    cells: list[SlippageCell] = []
    for (symbol, account_id, order_type, band, origin), values in sorted(grouped.items()):
        array = np.asarray(values, dtype=float)
        cells.append(
            SlippageCell(
                symbol=symbol,
                account=account_id,
                order_type=order_type,
                band=band,
                n=len(array),
                median_price=float(np.median(array)),
                p75_price=float(np.percentile(array, 75)),
                origin=origin,
            )
        )
    return cells


def measure_mt5_slippage(
    accounts: tuple[dict[str, Any], ...] = MT5_ACCOUNTS,
    *,
    days: int = 90,
) -> tuple[list[SlippageCell], list[dict[str, Any]]]:
    """Lee los terminales abiertos. Sin terminal/login: Sin datos, sin reintentos."""

    cells: list[SlippageCell] = []
    statuses: list[dict[str, Any]] = []
    for spec in accounts:
        history = read_mt5_history(
            str(spec["path"]),
            int(spec["login"]),
            days=days,
            server=spec.get("server"),
        )
        if history is None:
            statuses.append(
                {
                    "account": spec["account"],
                    "login": spec["login"],
                    "status": "Sin datos",
                    "reason": "terminal no abierto o login distinto",
                }
            )
            continue
        account_cells = _cells_from_history(history, str(spec["account"]))
        cells.extend(account_cells)
        statuses.append(
            {
                "account": spec["account"],
                "login": spec["login"],
                "status": "OK",
                "orders": len(history.get("orders") or []),
                "deals": len(history.get("deals") or []),
                "cells": len(account_cells),
            }
        )
    return cells, statuses


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
        columns = {row[1] for row in con.execute("PRAGMA table_info(tca)")}
        # ENG-1 B-14: el paper graba el slippage supuesto, no uno medido.
        no_paper = " AND COALESCE(t.origin, '') <> 'paper'" if "origin" in columns else ""
        rows = con.execute(
            "SELECT t.id, t.symbol, t.account, t.side, t.order_px, t.fill_px,"
            " t.ts_utc, t.fill_id, o.account_id"
            " FROM tca t LEFT JOIN order_accounts o ON o.order_id = t.fill_id"
            " WHERE t.order_px IS NOT NULL AND t.fill_px IS NOT NULL"
            " AND t.tca_version >= 2" + no_paper
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
                " WHERE tca_version >= 2"
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
    "measure_mt5_slippage",
    "measure_slippage",
    "read_mt5_history",
    "write_proposal",
]
