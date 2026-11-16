"""Riesgo abierto agregado por símbolo, grupo y total.

El riesgo se mide desde el precio de entrada hasta el SL actual:
``distancia × volumen × valor_por_precio``. Una posición sin SL se marca como
bloqueo total y se cuenta como el límite total de la cuenta. Solo se cuentan
los magics del laboratorio y los ``managed_magics`` de los EAs de la cuenta.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .accounts import AccountDefinition
from .config import ROOT

AI_CONFIG = ROOT / "config" / "ai_trader.yaml"
DEFAULT_DB = ROOT / "data" / "lab.db"


def canonical_symbol(symbol: str) -> str:
    """US100.cash -> US100; EURUSD -> EURUSD; XAUUSD -> XAUUSD."""
    text = str(symbol or "").strip().upper()
    for separator in (".", "_", "-", " "):
        if separator in text:
            text = text.split(separator, 1)[0]
    return text


def account_magics(account_id: str) -> list[int]:
    """Magics que el laboratorio y sus EAs pueden tener en esa cuenta."""
    out: set[int] = set()
    out.update(ea_magics(account_id))
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


def ea_magics(account_id: str) -> list[int]:
    """Magics gestionados por EAs externos registrados en mt5_eas.yaml."""
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
    return sorted(out)


def risk_group(account: AccountDefinition | None, symbol: str) -> str:
    """Grupo de riesgo: índices US, metales, pares USD o el propio símbolo."""
    base = canonical_symbol(symbol)
    caps = getattr(account, "risk_caps", None)
    groups = getattr(caps, "groups", {}) or {}
    for name, members in groups.items():
        for member in members:
            member_base = canonical_symbol(member)
            if base == member_base or base.startswith(member_base):
                return str(name)
    if base.startswith("XAU") or base.startswith("XAG"):
        return "metales"
    if "USD" in base:
        return "usd"
    return f"symbol:{base}"


def _risk_base(account: AccountDefinition | None, balance: float | None) -> float:
    if balance is not None and float(balance) > 0:
        return float(balance)
    if account is not None and float(account.account_size) > 0:
        return float(account.account_size)
    return 0.0


def position_has_sl(position: dict) -> bool:
    entry = float(
        position.get("price_open")
        or position.get("avg_price")
        or position.get("entry")
        or 0.0
    )
    stop = float(
        position.get("sl")
        or position.get("stop")
        or position.get("stop_loss")
        or 0.0
    )
    return entry > 0 and stop > 0


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
    stop = float(
        position.get("sl")
        or position.get("stop")
        or position.get("stop_loss")
        or 0.0
    )
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
    """Riesgo abierto por símbolo de los magics permitidos."""
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


def _cap_candidate(pct: float, usd: float, source: str) -> dict:
    return {"pct": float(pct), "usd": float(usd), "source": source}


def _effective_cap(candidates: list[dict]) -> dict:
    """El mínimo de todos los topes aplicables; lista las fuentes que empatan."""
    usable = [item for item in candidates if item.get("usd") is not None]
    if not usable:
        return {"pct": None, "usd": None, "source": ""}
    low = min(float(item["usd"]) for item in usable)
    binding = [
        item for item in usable if abs(float(item["usd"]) - low) <= 1e-9
    ]
    source = " / ".join(
        f"{item['source']} {float(item['pct']):.2%}" for item in binding
    )
    return {"pct": float(binding[0]["pct"]), "usd": low, "source": source}


def effective_symbol_cap(
    account: AccountDefinition | None,
    symbol: str,
    *,
    balance: float | None = None,
    ai_pct: float | None = None,
) -> dict:
    """Mínimo entre el tope explícito existente, el 2 % nuevo y ai_trader."""
    if account is None:
        return _effective_cap([])
    base = _risk_base(account, balance)
    target = canonical_symbol(symbol)
    candidates: list[dict] = []
    for key, value in (account.symbol_risk_caps or {}).items():
        if canonical_symbol(key) == target:
            candidates.append(
                _cap_candidate(
                    value,
                    float(account.account_size) * float(value),
                    "accounts.yaml symbol_risk_caps",
                )
            )
            break
    caps = getattr(account, "risk_caps", None)
    if caps is not None and caps.symbol_pct is not None:
        candidates.append(
            _cap_candidate(
                caps.symbol_pct,
                base * float(caps.symbol_pct),
                "accounts.yaml account_risk_caps",
            )
        )
    if ai_pct is not None:
        candidates.append(
            _cap_candidate(ai_pct, base * float(ai_pct), "ai_trader.yaml")
        )
    return _effective_cap(candidates)


def effective_group_cap(
    account: AccountDefinition | None,
    group: str,
    *,
    balance: float | None = None,
) -> dict:
    """Tope del grupo; ``symbol:XXX`` no tiene tope de grupo adicional."""
    if account is None or str(group).startswith("symbol:"):
        return _effective_cap([])
    caps = getattr(account, "risk_caps", None)
    if caps is None or caps.group_pct is None:
        return _effective_cap([])
    base = _risk_base(account, balance)
    return _effective_cap(
        [
            _cap_candidate(
                caps.group_pct,
                base * float(caps.group_pct),
                "accounts.yaml account_risk_caps",
            )
        ]
    )


def effective_total_cap(
    account: AccountDefinition | None,
    *,
    balance: float | None = None,
    prop_pct: float | None = None,
    ai_pct: float | None = None,
) -> dict:
    """Mínimo entre prop.yaml, accounts.yaml, ai_trader.yaml y el 4 % nuevo."""
    if account is None:
        return _effective_cap([])
    base = _risk_base(account, balance)
    candidates: list[dict] = []
    if prop_pct is not None:
        candidates.append(
            _cap_candidate(
                prop_pct,
                float(account.account_size) * float(prop_pct),
                "prop.yaml",
            )
        )
    if account.defaults.max_open_risk_pct:
        candidates.append(
            _cap_candidate(
                account.defaults.max_open_risk_pct,
                float(account.account_size) * float(account.defaults.max_open_risk_pct),
                "accounts.yaml",
            )
        )
    if ai_pct is not None:
        candidates.append(
            _cap_candidate(ai_pct, base * float(ai_pct), "ai_trader.yaml")
        )
    caps = getattr(account, "risk_caps", None)
    if caps is not None and caps.total_pct is not None:
        candidates.append(
            _cap_candidate(
                caps.total_pct,
                base * float(caps.total_pct),
                "accounts.yaml account_risk_caps",
            )
        )
    return _effective_cap(candidates)


def symbol_cap_usd(
    account: AccountDefinition | None,
    symbol: str,
    balance: float | None = None,
) -> float | None:
    return effective_symbol_cap(account, symbol, balance=balance).get("usd")


def group_cap_usd(
    account: AccountDefinition | None,
    group: str,
    balance: float | None = None,
) -> float | None:
    return effective_group_cap(account, group, balance=balance).get("usd")


def total_cap_usd(
    account: AccountDefinition | None,
    balance: float | None = None,
) -> float | None:
    return effective_total_cap(account, balance=balance).get("usd")


def risk_snapshot(
    positions: list[dict],
    broker,
    *,
    account_id: str,
    account: AccountDefinition | None,
    balance: float | None = None,
) -> dict:
    """Riesgo agregado por símbolo, grupo y total para una cuenta.

    Incluye los magics del laboratorio y los EAs de ``mt5_eas.yaml``. Una
    posición sin SL se cuenta como el límite total y se marca en
    ``missing_sl``; el guard la bloquea aunque el resto esté dentro.
    """
    allowed = set(account_magics(account_id))
    ea = set(ea_magics(account_id))
    lab = allowed - ea
    base = _risk_base(account, balance)
    total_cap = total_cap_usd(account, base)
    by_symbol: dict[str, float] = {}
    by_group: dict[str, float] = {}
    ea_by_symbol: dict[str, float] = {}
    ea_by_group: dict[str, float] = {}
    total = 0.0
    ea_total = 0.0
    lab_total = 0.0
    missing: list[dict] = []

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
        group = risk_group(account, symbol)
        has_sl = position_has_sl(position)
        if has_sl:
            risk = position_risk_usd(position, broker)
        else:
            risk = total_cap if total_cap is not None else position_risk_usd(position, broker)
            missing.append(
                {
                    "ticket": position.get("ticket"),
                    "symbol": symbol,
                    "magic": magic,
                    "volume": round(abs(float(position.get("volume") or 0.0)), 4),
                    "risk_usd": round(float(risk), 2),
                }
            )
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + risk
        by_group[group] = by_group.get(group, 0.0) + risk
        total += risk
        if magic in ea:
            ea_total += risk
            ea_by_symbol[symbol] = ea_by_symbol.get(symbol, 0.0) + risk
            ea_by_group[group] = ea_by_group.get(group, 0.0) + risk
        elif magic in lab:
            lab_total += risk

    ea_over: list[dict] = []
    for symbol, risk in sorted(ea_by_symbol.items()):
        cap = symbol_cap_usd(account, symbol, base)
        if cap is not None and risk > cap + 1e-9:
            ea_over.append(
                {"kind": "symbol", "name": symbol, "risk_usd": round(risk, 2), "cap_usd": round(cap, 2)}
            )
    for group, risk in sorted(ea_by_group.items()):
        cap = group_cap_usd(account, group, base)
        if cap is not None and risk > cap + 1e-9:
            ea_over.append(
                {"kind": "group", "name": group, "risk_usd": round(risk, 2), "cap_usd": round(cap, 2)}
            )
    if total_cap is not None and ea_total > total_cap + 1e-9:
        ea_over.append(
            {"kind": "total", "name": "total", "risk_usd": round(ea_total, 2), "cap_usd": round(total_cap, 2)}
        )

    symbol_caps = {
        symbol: (
            round(cap, 2) if (cap := symbol_cap_usd(account, symbol, base)) is not None else None
        )
        for symbol in by_symbol
    }
    group_caps = {
        group: (
            round(cap, 2) if (cap := group_cap_usd(account, group, base)) is not None else None
        )
        for group in by_group
    }
    return {
        "account": account_id,
        "balance_usd": round(base, 2),
        "total_usd": round(total, 2),
        "total_cap_usd": round(total_cap, 2) if total_cap is not None else None,
        "by_symbol": {key: round(value, 2) for key, value in sorted(by_symbol.items())},
        "by_group": {key: round(value, 2) for key, value in sorted(by_group.items())},
        "symbol_caps": symbol_caps,
        "group_caps": group_caps,
        "missing_sl": missing,
        "ea_total_usd": round(ea_total, 2),
        "lab_total_usd": round(lab_total, 2),
        "ea_over": ea_over,
        "ea_magics": sorted(ea),
        "lab_magics": sorted(lab),
    }


def alert_risk_events(
    account_id: str,
    risk: dict,
    *,
    db_path: str | Path = DEFAULT_DB,
    now: datetime | None = None,
) -> None:
    """Alerta critical por SL ausente y warning si el EA solo supera un tope."""
    try:
        from .alerts import send_once
    except Exception:
        return
    day = (now or datetime.now(timezone.utc)).date().isoformat()
    for item in risk.get("missing_sl") or []:
        event = f"missing_sl:{account_id}:{item.get('symbol')}:{day}"
        try:
            send_once(
                event,
                f"{account_id}: posición {item.get('symbol')} sin SL; "
                "riesgo abierto bloqueado",
                severity="critical",
                db_path=db_path,
                now=now,
            )
        except Exception:
            pass
    for item in risk.get("ea_over") or []:
        event = f"ea_risk_cap:{account_id}:{item.get('kind')}:{item.get('name')}:{day}"
        try:
            send_once(
                event,
                f"{account_id}: EA supera límite {item.get('kind')} "
                f"{item.get('name')} ({item.get('risk_usd'):,.2f} > "
                f"{item.get('cap_usd'):,.2f}); aperturas del lab bloqueadas",
                severity="warning",
                db_path=db_path,
                now=now,
            )
        except Exception:
            pass


def open_risk_report(
    db_path: str | Path,
    account: AccountDefinition,
    *,
    broker,
    balance: float | None = None,
    prop_pct: float | None = None,
    ai_pct: float | None = None,
) -> dict:
    positions = broker.positions() or []
    risk = risk_snapshot(
        positions,
        broker,
        account_id=account.id,
        account=account,
        balance=balance,
    )
    symbols = {}
    for symbol, open_risk in sorted(risk["by_symbol"].items()):
        effective = effective_symbol_cap(
            account, symbol, balance=balance, ai_pct=ai_pct
        )
        cap = effective.get("usd")
        symbols[symbol] = {
            "open_risk_usd": round(open_risk, 2),
            "cap_usd": round(cap, 2) if cap is not None else None,
            "cap_pct": effective.get("pct"),
            "source": effective.get("source") or "",
            "used_pct": round(open_risk / cap, 6) if cap else None,
            "remaining_usd": round(max(0.0, cap - open_risk), 2) if cap is not None else None,
        }
    groups = {}
    for group, open_risk in sorted(risk["by_group"].items()):
        effective = effective_group_cap(account, group, balance=balance)
        cap = effective.get("usd")
        groups[group] = {
            "open_risk_usd": round(open_risk, 2),
            "cap_usd": round(cap, 2) if cap is not None else None,
            "cap_pct": effective.get("pct"),
            "source": effective.get("source") or "",
            "used_pct": round(open_risk / cap, 6) if cap else None,
            "remaining_usd": round(max(0.0, cap - open_risk), 2) if cap is not None else None,
        }
    effective_total = effective_total_cap(
        account, balance=balance, prop_pct=prop_pct, ai_pct=ai_pct
    )
    total_cap = effective_total.get("usd")
    total = {
        "open_risk_usd": round(risk["total_usd"], 2),
        "cap_usd": round(total_cap, 2) if total_cap is not None else None,
        "cap_pct": effective_total.get("pct"),
        "source": effective_total.get("source") or "",
        "used_pct": round(risk["total_usd"] / total_cap, 6) if total_cap else None,
        "remaining_usd": round(max(0.0, total_cap - risk["total_usd"]), 2)
        if total_cap is not None
        else None,
    }
    return {
        "account": account.id,
        "balance_usd": risk["balance_usd"],
        "magics": account_magics(account.id),
        "ea_magics": risk["ea_magics"],
        "lab_magics": risk["lab_magics"],
        "symbols": symbols,
        "groups": groups,
        "total": total,
        "missing_sl": risk["missing_sl"],
        "ea_over": risk["ea_over"],
        "ea_total_usd": risk["ea_total_usd"],
        "lab_total_usd": risk["lab_total_usd"],
    }


__all__ = [
    "account_magics",
    "alert_risk_events",
    "canonical_symbol",
    "ea_magics",
    "effective_group_cap",
    "effective_symbol_cap",
    "effective_total_cap",
    "group_cap_usd",
    "open_risk_by_symbol",
    "open_risk_report",
    "position_has_sl",
    "position_risk_usd",
    "risk_group",
    "risk_snapshot",
    "symbol_cap_usd",
    "total_cap_usd",
]
