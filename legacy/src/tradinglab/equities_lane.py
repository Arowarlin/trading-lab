"""Carril de acciones (ORB) en paper: ticker fijo y estado del pipeline.

El scan de acciones **no elige**: el ticker del carril es decisión del
operador y vive en `config/equities_lane.yaml`. Este módulo:

- carga y valida esa configuración (`load_lane`);
- dice si un símbolo pertenece al carril (`symbol_in_lane`);
- resume el estado del pipeline externo (entrada pendiente, watchlist, pesos
  de referencia y si el carril puede ejecutar) (`status`).

Todo es **solo lectura**: este módulo no envía órdenes ni modifica el
pipeline externo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import ROOT

CONFIG_PATH = ROOT / "config" / "equities_lane.yaml"
SYMBOL_RE = r"^[A-Z]{1,6}([.-][A-Z]{1,6})?$"


class LaneError(RuntimeError):
    """La configuración del carril no es utilizable."""


@dataclass(frozen=True)
class Lane:
    """Configuración del carril de acciones."""

    ticker: str
    setup: str = "orb"
    interval: str = "5m"
    opening_range_minutes: int = 15
    account: str = "alpaca_paper"
    only_ticker: bool = True
    entry_start: str = "09:30"
    entry_end: str = "15:30"
    flat_by: str = "15:55"
    max_trades_per_day: int = 3
    max_loss_per_trade_usd: float = 50.0
    notes: str = ""
    source: str = ""

    def allows(self, symbol: str) -> bool:
        """¿El símbolo pertenece al carril?"""
        if not self.only_ticker:
            return True
        return str(symbol or "").strip().upper() == self.ticker


def _int(value: object, label: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise LaneError(f"{label} debe ser un entero: {value!r}") from exc


def _float(value: object, label: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LaneError(f"{label} debe ser numérico: {value!r}") from exc


def load_lane(path: str | Path | None = None) -> Lane:
    """Carga `config/equities_lane.yaml` (sin ticker fijo no hay carril)."""
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        raise LaneError(f"falta la configuración del carril: {target}")
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise LaneError(f"configuración del carril ilegible: {exc}") from exc
    if not isinstance(raw, dict):
        raise LaneError("la configuración del carril debe ser un mapa")
    ticker = str(raw.get("ticker") or "").strip().upper()
    if not ticker:
        raise LaneError("la configuración del carril no tiene ticker")
    return Lane(
        ticker=ticker,
        setup=str(raw.get("setup") or "orb").strip().lower(),
        interval=str(raw.get("interval") or "5m").strip(),
        opening_range_minutes=_int(
            raw.get("opening_range_minutes"), "opening_range_minutes", 15
        ),
        account=str(raw.get("account") or "alpaca_paper").strip(),
        only_ticker=bool(raw.get("only_ticker", True)),
        entry_start=str(raw.get("entry_start") or "09:30").strip(),
        entry_end=str(raw.get("entry_end") or "15:30").strip(),
        flat_by=str(raw.get("flat_by") or "15:55").strip(),
        max_trades_per_day=_int(raw.get("max_trades_per_day"), "max_trades_per_day", 3),
        max_loss_per_trade_usd=_float(
            raw.get("max_loss_per_trade_usd"), "max_loss_per_trade_usd", 50.0
        ),
        notes=str(raw.get("notes") or "").strip(),
        source=str(target),
    )


def symbol_in_lane(symbol: str, lane: Lane | None = None) -> bool:
    """¿El símbolo está en el carril? Sin configuración, no entra nadie."""
    try:
        lane = lane or load_lane()
    except LaneError:
        return False
    return lane.allows(symbol)


def _read_json(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def status(
    *,
    lane: Lane | None = None,
    directory: str | Path | None = None,
    settings=None,
) -> dict:
    """Estado del carril: configuración, pipeline externo y possibility de ejecutar."""
    from .daytrader import _paper_account

    try:
        lane = lane or load_lane()
        lane_error = ""
    except LaneError as exc:
        lane = None
        lane_error = str(exc)

    if settings is None:
        from .config import get_settings

        settings = get_settings()

    target = Path(directory) if directory else Path(settings.daytrader.dir)
    entry = _read_json(target / "entry.json")
    watchlist = _read_json(target / "watchlist.json")
    targets = _read_json(target / "targets.json")
    orders = _read_json(target / "orders.json")

    hits = [
        hit
        for hit in (watchlist.get("hits") or [])
        if isinstance(hit, dict)
        and lane is not None
        and str(hit.get("symbol") or "").strip().upper() == lane.ticker
    ]
    weights = [
        item
        for item in (targets.get("weights") or [])
        if isinstance(item, dict)
        and lane is not None
        and str(item.get("ticker") or "").strip().upper() == lane.ticker
    ]
    raw_orders = orders.get("orders") if isinstance(orders, dict) else orders
    lane_orders = [
        item
        for item in (raw_orders or [])
        if isinstance(item, dict)
        and lane is not None
        and str(item.get("symbol") or "").strip().upper() == lane.ticker
    ]

    paper, account = _paper_account(settings)
    enabled = bool(settings.daytrader.enabled)
    can_execute = bool(enabled and paper)

    return {
        "ticker": lane.ticker if lane else None,
        "setup": lane.setup if lane else None,
        "interval": lane.interval if lane else None,
        "account": lane.account if lane else settings.daytrader.account,
        "only_ticker": lane.only_ticker if lane else None,
        "notes": lane.notes if lane else "",
        "source": lane.source if lane else "",
        "error": lane_error,
        "dir": str(target),
        "daytrader_enabled": enabled,
        "paper": bool(paper),
        "broker_account": account.name if account else None,
        "can_execute": can_execute,
        "entry": {
            "symbol": entry.get("symbol"),
            "setup": entry.get("setup"),
            "status": entry.get("status"),
            "price": entry.get("price"),
            "level": entry.get("level"),
            "date": entry.get("date"),
        },
        "watchlist_hits": len(hits),
        "watchlist_as_of": watchlist.get("as_of"),
        "target_weight": weights[0].get("weight") if weights else None,
        "target_source": targets.get("source"),
        "orders_in_lane": len(lane_orders),
    }


__all__ = [
    "CONFIG_PATH",
    "Lane",
    "LaneError",
    "load_lane",
    "status",
    "symbol_in_lane",
]
