"""Riesgo abierto por símbolo de todos los carriles y EAs registrados.

El riesgo se mide desde el precio de entrada hasta el SL actual:
``distancia × volumen × valor_por_precio``. Sin SL se usa un 2 % del nocional
como estimación conservadora, igual que el forward. Solo se cuentan los magics
del laboratorio y los managed_magics de los EAs de la cuenta.
"""

from __future__ import annotations

from pathlib import Path

from .accounts import AccountDefinition
from .config import ROOT

AI_CONFIG = ROOT / "config" / "ai_trader.yaml"


def account_magics(account_id: str) -> list[int]:
    """Magics que el laboratorio y sus EAs pueden tener en esa cuenta."""
    out: set[int] = set()
    try:
        from .ea_registry import load_eas

        for ea in load_eas():
            if ea.account != account_id:
                continue
            out.add(int(ea.magic))
            out.update(int(item) for item in ea.managed_magics)
    except Exception:
        pass
    try:
        from .forward_intraday import load_forward_bots

        for bot in load_forward_bots():
            if bot.account == account_id:
                out.add(int(bot.magic))
    except Exception:
        pass
    try:
        from .ai_trader import load_config as load_ai_config

        cfg = load_ai_config()
        if str(cfg.get("account") or "") == account_id:
            for item in (cfg.get("styles") or {}).values():
                magic = item.get("magic")
                if magic is not None:
                    out.add(int(magic))
    except Exception:
        pass
    return sorted(out)


def position_risk_usd(position: dict, broker) -> float:
    """Pérdida estimada hasta el SL de una posición, en USD de la cuenta."""
    symbol = str(position.get("symbol") or position.get("ticker") or "")
    volume = abs(float(position.get("volume") or position.get("qty") or 0.0))
    if not symbol or volume <= 0:
        return 0.0
    entry = float(
        position.get("price_open")
        or position.get("avg_price")
        or position.get("entry")
        or 0.0
    )
    stop = float(position.get("sl") or position.get("stop") or 0.0)
    try:
        spec = broker.symbol_spec(symbol)
    except Exception:
        spec = {}
    tick_size = float(spec.get("tick_size") or spec.get("point") or 0.0)
    tick_value = float(spec.get("tick_value") or 0.0)
    contract = float(spec.get("contract_size") or 1.0)
    if stop > 0 and entry > 0:
        if tick_size > 0 and tick_value > 0:
            value_per_price = tick_value / tick_size
            return abs(entry - stop) * volume * value_per_price
        return abs(entry - stop) * volume * contract
    price = float(
        position.get("price_current")
        or position.get("last")
        or entry
        or 0.0
    )
    if price <= 0:
        return 0.0
    return volume * contract * price * 0.02


def open_risk_by_symbol(
    positions: list[dict],
    broker,
    *,
    account_id: str,
) -> dict[str, float]:
    allowed = set(account_magics(account_id))
    if not allowed:
        return {}
    out: dict[str, float] = {}
    for position in positions or []:
        try:
            magic = int(position.get("magic") or 0)
        except (TypeError, ValueError):
            magic = 0
        if magic not in allowed:
            continue
        symbol = str(position.get("symbol") or position.get("ticker") or "").upper()
        if not symbol:
            continue
        out[symbol] = out.get(symbol, 0.0) + position_risk_usd(position, broker)
    return {symbol: round(value, 2) for symbol, value in out.items()}


def symbol_cap_usd(account: AccountDefinition | None, symbol: str) -> float | None:
    if account is None:
        return None
    target = str(symbol or "").strip().upper()
    for key, value in (account.symbol_risk_caps or {}).items():
        if str(key).strip().upper() == target:
            return float(account.account_size) * float(value)
    return None


def open_risk_report(
    db_path: str | Path,
    account: AccountDefinition,
    *,
    broker,
) -> dict:
    positions = broker.positions() or []
    by_symbol = open_risk_by_symbol(positions, broker, account_id=account.id)
    symbols = {}
    for symbol, risk in sorted(by_symbol.items()):
        cap = symbol_cap_usd(account, symbol)
        symbols[symbol] = {
            "open_risk_usd": round(risk, 2),
            "cap_usd": round(cap, 2) if cap is not None else None,
            "used_pct": round(risk / cap, 6) if cap else None,
            "remaining_usd": round(max(0.0, cap - risk), 2) if cap is not None else None,
        }
    return {
        "account": account.id,
        "magics": account_magics(account.id),
        "symbols": symbols,
    }


__all__ = [
    "account_magics",
    "open_risk_by_symbol",
    "open_risk_report",
    "position_risk_usd",
    "symbol_cap_usd",
]
