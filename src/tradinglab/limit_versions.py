"""Versionado de límites de cuenta, rollback y capital máximo por bot.

SQLite e historial; no toca YAML ni activa nada. El rollback respeta las reglas
de F13 y de aflojamiento de `set_limits` (un aflojamiento aplica al siguiente
día hábil).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .accounts import (
    LIMIT_FIELDS,
    effective_limits,
    load_accounts,
    own_limits,
    set_limits,
)
from .db import connect, init_db, utcnow
from .f13 import status as f13_status

DEFAULT_MAX_CAPITAL = 0.0


class LimitVersionError(ValueError):
    pass


def _snapshot_hash(account_id: str, version: int, limits: dict) -> str:
    raw = json.dumps(
        {"account": account_id, "version": version, "limits": limits},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def snapshot_limits(
    db_path: str | Path,
    account_id: str,
    *,
    created_by: str = "cli",
    reason: str = "",
) -> dict:
    """Congela una versión numerada de los límites propios/efectivos."""
    accounts = load_accounts()
    account = accounts.get(account_id)
    if account is None:
        raise LimitVersionError(f"cuenta desconocida: {account_id}")
    init_db(db_path)
    own = asdict(own_limits(db_path, account))
    effective = asdict(effective_limits(db_path, account))
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM account_limit_versions "
            "WHERE account_id=?",
            (account_id,),
        ).fetchone()
        version = int(row["v"]) + 1
        digest = _snapshot_hash(account_id, version, own)
        con.execute(
            "INSERT INTO account_limit_versions"
            "(ts, account_id, version, limits, effective, hash, created_by, reason) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                account_id,
                version,
                json.dumps(own, sort_keys=True),
                json.dumps(effective, sort_keys=True),
                digest,
                created_by[:100],
                reason[:500],
            ),
        )
    return {
        "account_id": account_id,
        "version": version,
        "hash": digest,
        "limits": own,
        "effective": effective,
    }


def list_versions(db_path: str | Path, account_id: str) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM account_limit_versions WHERE account_id=? "
            "ORDER BY version DESC",
            (account_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        for key in ("limits", "effective"):
            try:
                item[key] = json.loads(item[key])
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out


def get_version(db_path: str | Path, account_id: str, version: int) -> dict:
    rows = list_versions(db_path, account_id)
    for row in rows:
        if int(row["version"]) == int(version):
            return row
    raise LimitVersionError(f"versión {version} no encontrada para {account_id}")


def rollback_version(
    db_path: str | Path,
    account_id: str,
    version: int,
    *,
    confirm: bool,
    by: str = "humano",
    now: datetime | None = None,
) -> dict:
    if not confirm:
        raise LimitVersionError("rollback exige confirmación explícita")
    account = load_accounts().get(account_id)
    if account is None:
        raise LimitVersionError(f"cuenta desconocida: {account_id}")
    target = get_version(db_path, account_id, version)
    current = asdict(own_limits(db_path, account, now=now))
    changes = {}
    for field in LIMIT_FIELDS:
        value = float(target["limits"][field])
        if abs(value - float(current[field])) > 1e-12:
            changes[field] = value
    if not changes:
        return {"ok": True, "changes": [], "account_id": account_id, "version": version}
    frozen = f13_status(db_path) is not None
    if frozen:
        for field, value in changes.items():
            if value > float(current[field]) + 1e-12:
                raise LimitVersionError(
                    f"{field}: F13 congelado/iniciado; el rollback intenta aflojar"
                )
    result = set_limits(
        db_path,
        account_id=account_id,
        changes=changes,
        origin="rollback",
        confirm=True,
        now=now,
        accounts=load_accounts(),
    )
    if not result["ok"]:
        raise LimitVersionError("; ".join(result["errors"]))
    return {
        "ok": True,
        "account_id": account_id,
        "version": version,
        "changes": result["changes"],
        "frozen": frozen,
    }


def set_bot_capital(
    db_path: str | Path,
    bot: str,
    max_capital_usd: float,
    *,
    by: str = "humano",
    reason: str = "",
) -> dict:
    try:
        value = float(max_capital_usd)
    except (TypeError, ValueError) as exc:
        raise LimitVersionError("max_capital_usd debe ser numérico") from exc
    if value <= 0 or value != value or value in (float("inf"), float("-inf")):
        raise LimitVersionError("max_capital_usd debe ser > 0 y finito")
    from .orchestrator import load_bots

    if not any(spec.id == bot for spec in load_bots()):
        raise LimitVersionError(f"bot desconocido: {bot}")
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT max_capital_usd FROM bot_capital_limits WHERE bot=?",
            (bot,),
        ).fetchone()
        old = float(row["max_capital_usd"]) if row else None
        con.execute(
            "INSERT INTO bot_capital_limits(bot, max_capital_usd, updated_at, updated_by) "
            "VALUES(?,?,?,?) ON CONFLICT(bot) DO UPDATE SET "
            "max_capital_usd=excluded.max_capital_usd, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by",
            (bot, value, utcnow(), by[:100]),
        )
        con.execute(
            "INSERT INTO bot_capital_history"
            "(ts, bot, old_value, new_value, updated_by, reason) VALUES(?,?,?,?,?,?)",
            (utcnow(), bot, old, value, by[:100], reason[:500]),
        )
    return {"bot": bot, "old": old, "max_capital_usd": value}


def bot_capital(db_path: str | Path, bot: str) -> float | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT max_capital_usd FROM bot_capital_limits WHERE bot=?", (bot,)
        ).fetchone()
    return float(row["max_capital_usd"]) if row else None


def list_bot_capital(db_path: str | Path) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM bot_capital_limits ORDER BY bot"
        ).fetchall()
    return [dict(row) for row in rows]


def cap_quantity(desired: int, price: float, max_capital_usd: float | None) -> int:
    """Recorta shares/contratos para no superar el capital máximo del bot."""
    if max_capital_usd is None or max_capital_usd <= 0 or price <= 0:
        return int(desired)
    allowed = int(max_capital_usd // price)
    return max(0, min(int(desired), allowed))


__all__ = [
    "DEFAULT_MAX_CAPITAL",
    "LimitVersionError",
    "bot_capital",
    "cap_quantity",
    "get_version",
    "list_bot_capital",
    "list_versions",
    "rollback_version",
    "set_bot_capital",
    "snapshot_limits",
]
