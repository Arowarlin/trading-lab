"""Cuentas del fondo y límites editables en SQLite.

La identidad de cada cuenta vive en `config/accounts.yaml`. Los límites
editables se guardan en `account_limit_history` y no forman parte del hash de
F13. El límite efectivo es el menor entre el de la firma (prop.yaml, solo
lectura) y el propio.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT
from .db import connect, init_db, utcnow
from .f13 import status as f13_status
from .prop.guard import AccountLimits
from .prop.rules import PropRules, from_yaml

ACCOUNTS_FILE = ROOT / "config" / "accounts.yaml"
LIMIT_FIELDS = (
    "daily_loss_pct",
    "max_drawdown_pct",
    "per_trade_risk_pct",
    "max_open_risk_pct",
    "max_trades_per_day",
)
PCT_FIELDS = {
    "daily_loss_pct",
    "max_drawdown_pct",
    "per_trade_risk_pct",
    "max_open_risk_pct",
}
DEFAULT_LOOSEN_WAIT_DAYS = 1


@dataclass(frozen=True)
class AccountDefinition:
    id: str
    name: str
    type: str
    broker: str
    platform: str
    status: str
    account_size: float
    pocket: str
    firm: str | None
    phase: str | None
    defaults: AccountLimits
    account_daily_stop: float | None = None
    symbol_risk_caps: dict[str, float] = dc_field(default_factory=dict)


def _limits_from_dict(data: dict[str, Any]) -> AccountLimits:
    return AccountLimits(
        daily_loss_pct=float(data.get("daily_loss_pct", 0.05)),
        max_drawdown_pct=float(data.get("max_drawdown_pct", 0.10)),
        per_trade_risk_pct=float(data.get("per_trade_risk_pct", 0.01)),
        max_open_risk_pct=float(data.get("max_open_risk_pct", 0.02)),
        max_trades_per_day=int(data.get("max_trades_per_day", 0)),
    )


def load_accounts(path: str | Path | None = None) -> dict[str, AccountDefinition]:
    path = Path(path) if path else ACCOUNTS_FILE
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for account_id, item in (raw.get("accounts") or {}).items():
        data = item or {}
        daily_stop_raw = data.get("account_daily_stop")
        out[str(account_id)] = AccountDefinition(
            id=str(account_id),
            name=str(data.get("name") or account_id),
            type=str(data.get("type") or "capital_propio"),
            broker=str(data.get("broker") or "paper"),
            platform=str(data.get("platform") or "internal"),
            status=str(data.get("status") or "template"),
            account_size=float(data.get("account_size") or 100_000),
            pocket=str(data.get("pocket") or "swing_equity"),
            firm=data.get("firm"),
            phase=data.get("phase"),
            defaults=_limits_from_dict(data.get("limits") or {}),
            account_daily_stop=(
                float(daily_stop_raw)
                if daily_stop_raw not in (None, "")
                else None
            ),
            symbol_risk_caps={
                str(symbol).strip().upper(): float(value)
                for symbol, value in (data.get("symbol_risk_caps") or {}).items()
            },
        )
    return out


def rules_for_account(account: AccountDefinition) -> PropRules:
    """Reglas base de la cuenta: firma si es fondeo; defaults neutrales si no."""
    if account.type == "fondeo" and account.firm and account.phase:
        return from_yaml(account.firm, account.phase, account.account_size)
    return PropRules(account_size=account.account_size)


def firm_limits(account: AccountDefinition) -> dict[str, float | None]:
    """Límites de la firma; solo lectura desde prop.yaml."""
    if account.type != "fondeo" or not account.firm or not account.phase:
        return {field: None for field in LIMIT_FIELDS}
    rules = from_yaml(account.firm, account.phase, account.account_size)
    return {
        "daily_loss_pct": float(rules.max_daily_loss_pct),
        "max_drawdown_pct": float(rules.max_loss_pct),
        "per_trade_risk_pct": None,
        "max_open_risk_pct": rules.max_open_risk_pct,
        "max_trades_per_day": None,
    }


def init_limits(db_path: str | Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS account_limit_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts TEXT NOT NULL,"
            "account_id TEXT NOT NULL,"
            "field TEXT NOT NULL,"
            "old_value REAL,"
            "new_value REAL NOT NULL,"
            "origin TEXT NOT NULL,"
            "effective_from TEXT NOT NULL,"
            "reason TEXT"
            ")"
        )


def _latest_rows(db_path: str | Path, account_id: str, now: datetime) -> dict[str, dict]:
    path = Path(db_path)
    if not path.exists():
        return {}
    init_limits(path)
    with connect(path) as con:
        rows = con.execute(
            "SELECT * FROM account_limit_history WHERE account_id = ? "
            "AND effective_from <= ? ORDER BY id",
            (account_id, now.astimezone(timezone.utc).isoformat()),
        ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        out[str(row["field"])] = dict(row)
    return out


def own_limits(
    db_path: str | Path,
    account: AccountDefinition,
    *,
    now: datetime | None = None,
) -> AccountLimits:
    current = now or datetime.now(timezone.utc)
    data = {
        "daily_loss_pct": account.defaults.daily_loss_pct,
        "max_drawdown_pct": account.defaults.max_drawdown_pct,
        "per_trade_risk_pct": account.defaults.per_trade_risk_pct,
        "max_open_risk_pct": account.defaults.max_open_risk_pct,
        "max_trades_per_day": account.defaults.max_trades_per_day,
    }
    for field, row in _latest_rows(db_path, account.id, current).items():
        if field in data:
            data[field] = float(row["new_value"])
    return AccountLimits(
        daily_loss_pct=float(data["daily_loss_pct"]),
        max_drawdown_pct=float(data["max_drawdown_pct"]),
        per_trade_risk_pct=float(data["per_trade_risk_pct"]),
        max_open_risk_pct=float(data["max_open_risk_pct"]),
        max_trades_per_day=int(data["max_trades_per_day"]),
    )


def effective_limits(
    db_path: str | Path,
    account: AccountDefinition,
    *,
    now: datetime | None = None,
) -> AccountLimits:
    own = own_limits(db_path, account, now=now)
    firm = firm_limits(account)
    daily_candidates = [own.daily_loss_pct]
    if firm["daily_loss_pct"] is not None:
        daily_candidates.append(float(firm["daily_loss_pct"]))
    if account.account_daily_stop is not None:
        daily_candidates.append(float(account.account_daily_stop))
    return AccountLimits(
        daily_loss_pct=min(daily_candidates),
        max_drawdown_pct=min(own.max_drawdown_pct, firm["max_drawdown_pct"])
        if firm["max_drawdown_pct"] is not None
        else own.max_drawdown_pct,
        per_trade_risk_pct=own.per_trade_risk_pct,
        max_open_risk_pct=min(own.max_open_risk_pct, firm["max_open_risk_pct"])
        if firm["max_open_risk_pct"] is not None
        else own.max_open_risk_pct,
        max_trades_per_day=own.max_trades_per_day,
    )


def _next_business_day(now: datetime, wait_days: int = DEFAULT_LOOSEN_WAIT_DAYS) -> datetime:
    current = now.astimezone(timezone.utc).date()
    remaining = max(1, int(wait_days))
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return datetime.combine(current, time(0, 0), tzinfo=timezone.utc)


def _as_dict(limits: AccountLimits) -> dict[str, float]:
    return {
        "daily_loss_pct": limits.daily_loss_pct,
        "max_drawdown_pct": limits.max_drawdown_pct,
        "per_trade_risk_pct": limits.per_trade_risk_pct,
        "max_open_risk_pct": limits.max_open_risk_pct,
        "max_trades_per_day": float(limits.max_trades_per_day),
    }


def set_limits(
    db_path: str | Path,
    *,
    account_id: str,
    changes: dict[str, float],
    origin: str = "console",
    confirm: bool = False,
    wait_days: int = DEFAULT_LOOSEN_WAIT_DAYS,
    now: datetime | None = None,
    accounts: dict[str, AccountDefinition] | None = None,
) -> dict:
    """Aplica cambios validados. Apretar es inmediato; aflojar espera y exige confirmación."""
    current = now or datetime.now(timezone.utc)
    definitions = accounts if accounts is not None else load_accounts()
    account = definitions.get(account_id)
    if account is None:
        return {"ok": False, "errors": [f"cuenta desconocida: {account_id}"], "changes": []}
    if not changes:
        return {"ok": False, "errors": ["sin cambios"], "changes": []}
    init_limits(db_path)
    own = own_limits(db_path, account, now=current)
    old_values = _as_dict(own)
    firm = firm_limits(account)
    frozen = f13_status(db_path) is not None
    errors: list[str] = []
    actions: list[dict] = []

    for field, raw in changes.items():
        if field not in LIMIT_FIELDS:
            errors.append(f"campo desconocido: {field}")
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{field}: valor no numérico")
            continue
        if not (value == value) or value in (float("inf"), float("-inf")):
            errors.append(f"{field}: valor no finito")
            continue
        if field in PCT_FIELDS and not 0.0 <= value <= 1.0:
            errors.append(f"{field}: debe estar entre 0 y 1")
            continue
        if field == "max_trades_per_day" and (value < 0 or int(value) != value):
            errors.append(f"{field}: debe ser entero >= 0")
            continue
        firm_value = firm.get(field)
        if firm_value is not None and value > float(firm_value) + 1e-12:
            errors.append(
                f"{field}: {value:.4g} supera el límite de la firma {float(firm_value):.4g}"
            )
            continue
        old = old_values[field]
        if abs(value - old) <= 1e-12:
            continue
        loosening = value > old
        if loosening and frozen:
            errors.append(
                f"{field}: F13 congelado/iniciado; solo se permite apretar límites"
            )
            continue
        if loosening and not confirm:
            errors.append(
                f"{field}: aflojar requiere confirmación explícita"
            )
            continue
        effective_from = (
            _next_business_day(current, wait_days)
            if loosening
            else current.astimezone(timezone.utc)
        )
        actions.append(
            {
                "field": field,
                "old": old,
                "new": value,
                "loosening": loosening,
                "effective_from": effective_from.isoformat(),
            }
        )

    if errors:
        return {"ok": False, "errors": errors, "changes": []}

    with connect(db_path) as con:
        for action in actions:
            con.execute(
                "INSERT INTO account_limit_history"
                "(ts, account_id, field, old_value, new_value, origin, effective_from, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    account_id,
                    action["field"],
                    action["old"],
                    action["new"],
                    origin,
                    action["effective_from"],
                    "aflojar" if action["loosening"] else "apretar",
                ),
            )
    return {
        "ok": True,
        "errors": [],
        "account": account_id,
        "changes": actions,
        "pending": any(action["loosening"] for action in actions),
    }


def history(db_path: str | Path, account_id: str, limit: int = 100) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    init_limits(path)
    with connect(path) as con:
        rows = con.execute(
            "SELECT * FROM account_limit_history WHERE account_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (account_id, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


FLOW_KINDS = ("deposit", "withdrawal")


def add_cash_flow(
    db_path: str | Path,
    *,
    account_id: str,
    kind: str,
    amount: float,
    ts: str | None = None,
    note: str = "",
    origin: str = "manual",
    accounts: dict[str, AccountDefinition] | None = None,
) -> dict:
    """Registra un depósito/retiro externo. No modifica límites ni YAML."""
    definitions = accounts if accounts is not None else load_accounts()
    if account_id not in definitions:
        raise ValueError(f"cuenta desconocida: {account_id}")
    if kind not in FLOW_KINDS:
        raise ValueError("kind debe ser deposit o withdrawal")
    try:
        value = float(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("amount debe ser numérico") from exc
    if value <= 0 or value != value or value in (float("inf"), float("-inf")):
        raise ValueError("amount debe ser > 0 y finito")
    stamp = ts or utcnow()
    try:
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("ts inválido: usa ISO 8601") from exc
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO account_cash_flows(ts, account_id, kind, amount, note, origin) "
            "VALUES(?,?,?,?,?,?)",
            (stamp, account_id, kind, value, note[:500], origin[:40]),
        )
    return {
        "account_id": account_id,
        "kind": kind,
        "amount": value,
        "ts": stamp,
        "note": note,
    }


def cash_flows(
    db_path: str | Path, account_id: str | None = None, limit: int = 200
) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    init_db(path)
    with connect(path) as con:
        if account_id:
            rows = con.execute(
                "SELECT * FROM account_cash_flows WHERE account_id = ? "
                "ORDER BY ts DESC, id DESC LIMIT ?",
                (account_id, int(limit)),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM account_cash_flows ORDER BY ts DESC, id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "ACCOUNTS_FILE",
    "AccountDefinition",
    "DEFAULT_LOOSEN_WAIT_DAYS",
    "FLOW_KINDS",
    "LIMIT_FIELDS",
    "PCT_FIELDS",
    "add_cash_flow",
    "cash_flows",
    "effective_limits",
    "firm_limits",
    "history",
    "init_limits",
    "load_accounts",
    "own_limits",
    "set_limits",
]
