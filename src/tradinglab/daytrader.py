"""Carril de day trading de acciones desde JSON externo.

Lee los archivos que escribe el pipeline externo (watchlist, orders y
state/risk.json), importa las señales al diario y pasa las órdenes por los
guards de ``OperatorService``. Por defecto es dry-run: solo ejecuta si el
operador lo pide, ``settings.daytrader.enabled`` es True y la cuenta es paper.

No conoce Alpaca directamente: delega en la capa de ejecución existente a
través de ``OperatorService``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .accounts import load_accounts
from .config import DEFAULT_DB, Settings
from .db import utcnow
from .equities_lane import LaneError, load_lane
from .operator import OperatorService

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-=^]{1,12}$")
VERDICTS = {"PASS", "BLOCK"}
PAPER_PLATFORMS = {"internal", "paper", "alpaca"}
PAPER_STATUSES = {"active", "demo", "paper", "simulated"}
ORDER_FIELDS = (
    "symbol",
    "side",
    "qty",
    "notional",
    "type",
    "time_in_force",
    "limit_price",
    "stop_price",
    "trail_price",
    "trail_percent",
    "extended_hours",
    "client_order_id",
    "order_class",
    "take_profit_limit_price",
    "stop_loss_stop_price",
    "stop_loss_limit_price",
    "advanced_instructions",
)


class DaytraderError(RuntimeError):
    """El carril no puede leer, validar o planificar una orden."""


@dataclass(frozen=True)
class DaytraderSignal:
    symbol: str
    setup: str
    price: float
    as_of: str
    mode: str
    hit_index: int = 0
    raw: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class DaytraderOrder:
    symbol: str
    side: str
    qty: int
    order_type: str
    time_in_force: str
    stop: float
    target: float
    fingerprint: str
    limit_price: float | None = None
    raw: dict = field(default_factory=dict, repr=False, compare=False)


def _resolve_dir(
    directory: str | Path | None,
    settings: Settings | None = None,
) -> Path:
    if directory is None:
        if settings is None:
            raise DaytraderError("falta la carpeta del pipeline daytrader")
        directory = settings.daytrader.dir
    return Path(directory)


def _read_json(path: Path, label: str, *, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise DaytraderError(f"falta {label}: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DaytraderError(f"{label} inválido en {path}: {exc}") from exc


def _positive_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DaytraderError(f"{label} debe ser numérico") from exc
    if not math.isfinite(number) or number <= 0:
        raise DaytraderError(f"{label} debe ser > 0")
    return number


def _integer_qty(value: Any) -> int:
    if isinstance(value, bool):
        raise DaytraderError("qty debe ser entero > 0")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DaytraderError("qty debe ser entero > 0") from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise DaytraderError("qty debe ser entero > 0")
    return int(number)


def _normalise_setups(hit: dict) -> list[str]:
    raw = hit.get("setups")
    if raw is None:
        raw = hit.get("setup")
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise DaytraderError("hit sin setup/setups")
    out: list[str] = []
    for item in items:
        setup = str(item or "").strip()
        if setup and setup not in out:
            out.append(setup)
    if not out:
        raise DaytraderError("hit sin setup/setups")
    return out


def load_watchlist(
    directory: str | Path | None = None,
    settings: Settings | None = None,
) -> list[DaytraderSignal]:
    """Lee y valida watchlist.json; un hit puede traer varios setups."""
    target = _resolve_dir(directory, settings)
    doc = _read_json(target / "watchlist.json", "watchlist.json")
    if not isinstance(doc, dict):
        raise DaytraderError("watchlist.json debe ser un objeto")
    mode = str(doc.get("mode") or "").strip().lower()
    if mode not in {"daily", "orb"}:
        raise DaytraderError("watchlist.json: mode debe ser daily u orb")
    as_of = str(doc.get("as_of") or "").strip()
    if not as_of:
        raise DaytraderError("watchlist.json: falta as_of")
    hits = doc.get("hits")
    if not isinstance(hits, list):
        raise DaytraderError("watchlist.json: hits debe ser una lista")

    out: list[DaytraderSignal] = []
    for hit_index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            raise DaytraderError("watchlist.json: hit inválido")
        symbol = str(hit.get("symbol") or "").strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            raise DaytraderError(f"watchlist.json: símbolo inválido {symbol!r}")
        price = _positive_float(hit.get("price"), f"{symbol}: price")
        for setup in _normalise_setups(hit):
            out.append(
                DaytraderSignal(
                    symbol=symbol,
                    setup=setup,
                    price=price,
                    as_of=as_of,
                    mode=mode,
                    hit_index=hit_index,
                    raw=dict(hit),
                )
            )
    return out


def order_fingerprint(order: dict) -> str:
    """Mismo fingerprint que trader-risk: campos Alpaca exactos, sha256[:16]."""
    core = {
        key: order[key]
        for key in ORDER_FIELDS
        if key in order and order[key] is not None
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_orders(
    directory: str | Path | None = None,
    settings: Settings | None = None,
) -> list[DaytraderOrder]:
    """Lee y valida orders.json; si no existe devuelve una lista vacía."""
    target = _resolve_dir(directory, settings)
    doc = _read_json(target / "orders.json", "orders.json", required=False)
    if doc is None:
        return []
    if isinstance(doc, dict):
        raw_orders = doc.get("orders")
        if not isinstance(raw_orders, list):
            raise DaytraderError("orders.json: falta la lista orders")
    elif isinstance(doc, list):
        raw_orders = doc
    else:
        raise DaytraderError("orders.json debe ser una lista o un objeto con orders")

    out: list[DaytraderOrder] = []
    for raw in raw_orders:
        if not isinstance(raw, dict):
            raise DaytraderError("orders.json: orden inválida")
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            raise DaytraderError(f"orders.json: símbolo inválido {symbol!r}")
        side = str(raw.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise DaytraderError(f"{symbol}: side debe ser buy o sell")
        qty = _integer_qty(raw.get("qty"))
        order_type = str(raw.get("type") or "market").strip().lower()
        if order_type not in {"market", "limit"}:
            raise DaytraderError(f"{symbol}: type debe ser market o limit")
        time_in_force = str(raw.get("time_in_force") or "day").strip().lower()
        if time_in_force not in {"day", "gtc"}:
            raise DaytraderError(f"{symbol}: time_in_force debe ser day o gtc")
        order_class = str(raw.get("order_class") or "").strip().lower()
        if order_class != "bracket":
            raise DaytraderError(f"{symbol}: solo se aceptan órdenes bracket")
        stop = _positive_float(
            raw.get("stop_loss_stop_price"), f"{symbol}: stop_loss_stop_price"
        )
        target_price = _positive_float(
            raw.get("take_profit_limit_price"),
            f"{symbol}: take_profit_limit_price",
        )
        limit_price = None
        if order_type == "limit":
            limit_price = _positive_float(
                raw.get("limit_price"), f"{symbol}: limit_price"
            )
        if side == "buy" and target_price <= stop:
            raise DaytraderError(f"{symbol}: target debe estar por encima del stop")
        if side == "sell" and target_price >= stop:
            raise DaytraderError(f"{symbol}: target debe estar por debajo del stop")
        out.append(
            DaytraderOrder(
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                time_in_force=time_in_force,
                stop=stop,
                target=target_price,
                fingerprint=order_fingerprint(raw),
                limit_price=limit_price,
                raw=dict(raw),
            )
        )
    return out


def load_risk_verdicts(
    directory: str | Path | None = None,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Lee state/risk.json y devuelve fingerprint -> PASS/BLOCK.

    Acepta la forma real de trader-risk (``results`` con ``fingerprint`` y
    ``verdict``) y un mapa directo. Si el archivo falta, devuelve ``{}``: el
    llamador trata todas las órdenes como BLOCK.
    """
    target = _resolve_dir(directory, settings)
    doc = _read_json(target / "state" / "risk.json", "state/risk.json", required=False)
    if doc is None:
        return {}
    if isinstance(doc, dict):
        date = str(doc.get("date") or "").strip()
        if date:
            today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            if date != today:
                return {}
        if isinstance(doc.get("results"), list):
            items = doc["results"]
        else:
            out: dict[str, str] = {}
            for key, value in doc.items():
                verdict = str(value).strip().upper() if isinstance(value, str) else ""
                if verdict in VERDICTS:
                    out[str(key)] = verdict
            return out
    elif isinstance(doc, list):
        items = doc
    else:
        return {}

    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict") or "").strip().upper()
        if verdict not in VERDICTS:
            continue
        fingerprint = item.get("fingerprint")
        if not fingerprint and isinstance(item.get("order"), dict):
            fingerprint = order_fingerprint(item["order"])
        if fingerprint:
            out[str(fingerprint)] = verdict
    return out


def import_signals(
    settings: Settings,
    con,
    directory: str | Path | None = None,
) -> dict:
    """Importa un signal por símbolo+setup sin duplicar por as_of."""
    target = _resolve_dir(directory, settings)
    signals = load_watchlist(target)
    inserted = 0
    duplicate_hits: set[int] = set()
    inserted_hits: set[int] = set()
    for signal in signals:
        reason = f"source=daytrader; setup={signal.setup}; as_of={signal.as_of}"
        # Compatibilidad con la primera versión, que añadía "; mode=...".
        variants = (
            reason,
            f"{reason}; mode=daily",
            f"{reason}; mode=orb",
        )
        exists = con.execute(
            "SELECT 1 FROM signals WHERE ticker = ? AND bot = ? "
            "AND reason IN (?, ?, ?) LIMIT 1",
            (signal.symbol, "daytrader", *variants),
        ).fetchone()
        if exists:
            duplicate_hits.add(signal.hit_index)
            continue
        con.execute(
            "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                utcnow(),
                signal.symbol,
                "daytrader",
                "flat",
                1.0,
                signal.price,
                reason,
            ),
        )
        inserted += 1
        inserted_hits.add(signal.hit_index)
    skipped = len(duplicate_hits - inserted_hits)
    return {
        "dir": str(target),
        "inserted": inserted,
        "skipped": skipped,
        "inserted_hits": len(inserted_hits),
        "total_hits": len({signal.hit_index for signal in signals}),
        "signals": signals,
    }


def _paper_account(settings: Settings):
    account = load_accounts().get(settings.daytrader.account)
    if account is None:
        return False, None
    paper = (
        settings.mode != "live"
        and account.platform in PAPER_PLATFORMS
        and account.status in PAPER_STATUSES
    )
    return paper, account


def _dry_run_reason(execute: bool, enabled: bool, paper: bool) -> str:
    if not execute:
        return "execute=false"
    if not enabled:
        return "daytrader.enabled=false"
    if not paper:
        return "cuenta no paper"
    return "tres condiciones cumplidas"


def plan_orders(
    settings: Settings,
    directory: str | Path | None = None,
    execute: bool = False,
    *,
    service: OperatorService | None = None,
) -> dict:
    """Pasa cada orden PASS por los guards; ejecuta solo con las 3 condiciones."""
    target = _resolve_dir(directory, settings)
    orders_path = target / "orders.json"
    risk_path = target / "state" / "risk.json"
    orders = load_orders(target)
    verdicts = load_risk_verdicts(target)
    prices: dict[str, float] = {}
    try:
        for signal in load_watchlist(target):
            prices.setdefault(signal.symbol, signal.price)
    except DaytraderError:
        pass

    paper, account = _paper_account(settings)
    can_execute = bool(execute and settings.daytrader.enabled and paper)
    service = service or (
        OperatorService(settings, DEFAULT_DB) if orders else None
    )
    results: list[dict] = []
    # El carril de acciones tiene un ticker fijo (decisión del operador). Una
    # orden de otro símbolo se rechaza antes de tocar los guards.
    try:
        lane = load_lane()
        lane_ticker = lane.ticker
        lane_error = ""
    except LaneError as exc:
        lane = None
        lane_ticker = None
        lane_error = str(exc)
    for order in orders:
        external = verdicts.get(order.fingerprint, "BLOCK")
        plan_entry = None
        raw_plan = order.raw.get("plan")
        if isinstance(raw_plan, dict):
            try:
                candidate = float(raw_plan.get("entry"))
                if math.isfinite(candidate) and candidate > 0:
                    plan_entry = candidate
            except (TypeError, ValueError):
                plan_entry = None
        item = {
            "symbol": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "stop": order.stop,
            "target": order.target,
            "price": order.limit_price or plan_entry or prices.get(order.symbol),
            "external_verdict": external,
            "guard_verdict": "NO EVALUADO",
            "action": "rechazada",
            "fingerprint": order.fingerprint,
            "reason": "",
            "order": order.raw,
        }
        if lane is None:
            item["guard_verdict"] = "BLOCK"
            item["action"] = "rechazada"
            item["reason"] = f"sin carril de acciones: {lane_error}"
            results.append(item)
            continue
        if not lane.allows(order.symbol):
            item["guard_verdict"] = "BLOCK"
            item["action"] = "rechazada"
            item["reason"] = (
                f"ticker fuera del carril de acciones ({lane_ticker}): {order.symbol}"
            )
            results.append(item)
            continue

        if external != "PASS":
            if not risk_path.exists():
                item["reason"] = (
                    "state/risk.json no existe: todas las órdenes se tratan como BLOCK"
                )
            elif external == "BLOCK":
                item["reason"] = "veredicto externo BLOCK"
            else:
                item["reason"] = "sin fingerprint PASS en state/risk.json"
            results.append(item)
            continue

        price = order.limit_price or plan_entry or prices.get(order.symbol) or 0.0
        params = {
            "account": settings.daytrader.account,
            "ticker": order.symbol,
            "side": order.side,
            "qty": order.qty,
            "price": price,
            "sl": order.stop,
            "tp": order.target,
        }
        try:
            plan = service._plan_order(params)
            summary = plan["summary"]
            payload = plan["payload"]
            item["guard_verdict"] = "PASS"
            item["guard_reason"] = summary.get("guard")
            item["qty"] = summary.get("qty", order.qty)
            item["stop"] = summary.get("sl", order.stop)
            item["price"] = summary.get("price", price)
            item["target"] = order.target
            item["plan"] = plan
            if can_execute:
                try:
                    item["execution"] = service._execute_order(payload)
                    item["action"] = "ejecutada"
                    item["reason"] = _dry_run_reason(execute, True, paper)
                except Exception as exc:
                    item["guard_verdict"] = "BLOCK"
                    item["action"] = "rechazada"
                    item["reason"] = f"fallo al ejecutar: {exc}"
            else:
                item["action"] = "dry-run"
                item["reason"] = _dry_run_reason(
                    execute, settings.daytrader.enabled, paper
                )
        except Exception as exc:
            item["guard_verdict"] = "BLOCK"
            item["action"] = "rechazada"
            item["reason"] = f"guards del lab: {exc}"
        results.append(item)

    return {
        "dir": str(target),
        "orders_file": orders_path.exists(),
        "risk_file": risk_path.exists(),
        "risk_verdicts": len(verdicts),
        "execute_requested": bool(execute),
        "enabled": bool(settings.daytrader.enabled),
        "account": settings.daytrader.account,
        "paper": bool(paper),
        "can_execute": can_execute,
        "lane_ticker": lane_ticker,
        "orders": results,
    }


__all__ = [
    "DaytraderError",
    "DaytraderOrder",
    "DaytraderSignal",
    "import_signals",
    "load_orders",
    "load_risk_verdicts",
    "load_watchlist",
    "order_fingerprint",
    "plan_orders",
]
