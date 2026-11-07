"""Pausa de aperturas por racha o pérdida diaria (solo aprieta).

Los umbrales viven en SQLite (`account_risk_config` + historial), fuera del
hash de F13. La pausa se latcha hasta reanudación explícita; cerrar/reducir
nunca se bloquea. Con F13 congelado/iniciado solo se permite apretar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .accounts import AccountDefinition, load_accounts
from .db import connect, init_db, utcnow
from .f13 import status as f13_status

DEFAULT_MAX_CONSECUTIVE_LOSSES = 3
DEFAULT_DAILY_LOSS_PCT = 0.02
FIELDS = ("max_consecutive_losses", "daily_loss_pct")

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_risk_config (
    account_id TEXT PRIMARY KEY,
    max_consecutive_losses INTEGER NOT NULL,
    daily_loss_pct REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_risk_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    origin TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS account_pause_state (
    account_id TEXT PRIMARY KEY,
    paused INTEGER NOT NULL,
    reason TEXT,
    trigger_type TEXT,
    triggered_at TEXT,
    reset_at TEXT,
    updated_at TEXT NOT NULL,
    actor TEXT
);
"""


class RiskPauseError(ValueError):
    pass


@dataclass(frozen=True)
class RiskConfig:
    account_id: str
    max_consecutive_losses: int
    daily_loss_pct: float


def init_riskpause(db_path: str | Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.executescript(SCHEMA)


def _frozen(db_path: str | Path) -> bool:
    return f13_status(db_path) is not None


def config(db_path: str | Path, account_id: str) -> RiskConfig:
    init_riskpause(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM account_risk_config WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    if row:
        return RiskConfig(
            account_id=str(row["account_id"]),
            max_consecutive_losses=int(row["max_consecutive_losses"]),
            daily_loss_pct=float(row["daily_loss_pct"]),
        )
    return RiskConfig(
        account_id=account_id,
        max_consecutive_losses=DEFAULT_MAX_CONSECUTIVE_LOSSES,
        daily_loss_pct=DEFAULT_DAILY_LOSS_PCT,
    )


def _state(db_path: str | Path, account_id: str) -> dict | None:
    init_riskpause(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM account_pause_state WHERE account_id = ?",
            (account_id,),
        ).fetchone()
    return dict(row) if row else None


def _parse_ts(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _today(tz: str, now: datetime | None) -> str:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(zone).date().isoformat()


def _load_trades(db_path: str | Path, tz: str):
    from .journal import load_closed_trades
    from .orchestrator import load_bots

    specs = load_bots()
    trades, _ = load_closed_trades(
        db_path,
        tz=tz,
        bots={
            spec.id: {"account": spec.account, "profile": spec.profile}
            for spec in specs
        },
    )
    return trades


def _stats(
    trades: list[Any],
    account: AccountDefinition,
    cfg: RiskConfig,
    today: str,
) -> dict:
    ordered = sorted(trades, key=lambda trade: (trade.exit_ts, trade.exit_fill_id))
    streak = 0
    for trade in reversed(ordered):
        if float(trade.pnl) < 0:
            streak += 1
        else:
            break
    day_pnl = sum(float(trade.pnl) for trade in ordered if trade.day == today)
    daily_loss = max(0.0, -day_pnl)
    daily_limit = max(0.0, float(cfg.daily_loss_pct) * float(account.account_size))
    return {
        "consecutive_losses": streak,
        "max_consecutive_losses": cfg.max_consecutive_losses,
        "daily_loss_usd": round(daily_loss, 2),
        "daily_limit_usd": round(daily_limit, 2),
        "daily_loss_pct": cfg.daily_loss_pct,
        "today": today,
    }


def pause_status(
    db_path: str | Path,
    account_id: str,
    *,
    trades: list[Any] | None = None,
    tz: str = "UTC",
    now: datetime | None = None,
    persist: bool = True,
) -> dict:
    """Estado de pausa; puede disparar y persistir el latch."""
    accounts = load_accounts()
    account = accounts.get(account_id)
    if account is None:
        raise RiskPauseError(f"cuenta desconocida: {account_id}")
    cfg = config(db_path, account_id)
    state = _state(db_path, account_id)
    if state and state["paused"]:
        return {
            "paused": True,
            "reason": state["reason"],
            "trigger_type": state["trigger_type"],
            "triggered_at": state["triggered_at"],
            "reset_at": state["reset_at"],
            "max_consecutive_losses": cfg.max_consecutive_losses,
            "daily_loss_pct": cfg.daily_loss_pct,
            "consecutive_losses": None,
            "daily_loss_usd": None,
            "daily_limit_usd": None,
            "today": _today(tz, now),
        }
    if trades is None:
        trades = [
            trade
            for trade in _load_trades(db_path, tz)
            if trade.account == account_id
        ]
    else:
        trades = [trade for trade in trades if trade.account == account_id]
    if state and state.get("reset_at"):
        since = _parse_ts(state["reset_at"])
        trades = [
            trade for trade in trades if _parse_ts(trade.exit_ts) > since
        ]
    stats = _stats(trades, account, cfg, _today(tz, now))
    reasons = []
    trigger = None
    if (
        cfg.max_consecutive_losses > 0
        and stats["consecutive_losses"] >= cfg.max_consecutive_losses
    ):
        reasons.append(
            f"racha perdedora {stats['consecutive_losses']} >= "
            f"{cfg.max_consecutive_losses}"
        )
        trigger = "streak"
    if stats["daily_loss_usd"] >= stats["daily_limit_usd"] > 0:
        reasons.append(
            f"pérdida diaria {stats['daily_loss_usd']:.2f} >= "
            f"{stats['daily_limit_usd']:.2f}"
        )
        trigger = trigger or "daily_loss"
    paused = trigger is not None
    if paused and persist:
        init_riskpause(db_path)
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO account_pause_state"
                "(account_id, paused, reason, trigger_type, triggered_at, reset_at, updated_at, actor) "
                "VALUES(?,?,?,?,?,NULL,?,?) ON CONFLICT(account_id) DO UPDATE SET "
                "paused=1, reason=excluded.reason, trigger_type=excluded.trigger_type, "
                "triggered_at=excluded.triggered_at, reset_at=NULL, "
                "updated_at=excluded.updated_at, actor=excluded.actor",
                (
                    account_id,
                    1,
                    "; ".join(reasons),
                    trigger,
                    utcnow(),
                    utcnow(),
                    "auto",
                ),
            )
            con.execute(
                "INSERT INTO account_risk_history"
                "(ts, account_id, field, old_value, new_value, origin, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    account_id,
                    "paused",
                    0,
                    1,
                    "auto",
                    "; ".join(reasons),
                ),
            )
    return {
        "paused": paused,
        "reason": "; ".join(reasons) if reasons else "sin pausa",
        "trigger_type": trigger,
        "triggered_at": utcnow() if paused and persist else None,
        "reset_at": None,
        "max_consecutive_losses": cfg.max_consecutive_losses,
        "daily_loss_pct": cfg.daily_loss_pct,
        **stats,
    }


def resume(
    db_path: str | Path,
    account_id: str,
    *,
    confirm: bool,
    actor: str = "console",
) -> dict:
    if not confirm:
        raise RiskPauseError("reanudar exige confirmación explícita")
    if _frozen(db_path):
        raise RiskPauseError(
            "F13 está congelado/iniciado: solo se permite apretar; no reanudar"
        )
    state = _state(db_path, account_id)
    if not state or not state["paused"]:
        raise RiskPauseError(f"{account_id} no está en pausa")
    init_riskpause(db_path)
    with connect(db_path) as con:
        con.execute(
            "UPDATE account_pause_state SET paused=0, reset_at=?, updated_at=?, actor=? "
            "WHERE account_id = ?",
            (utcnow(), utcnow(), actor, account_id),
        )
        con.execute(
            "INSERT INTO account_risk_history"
            "(ts, account_id, field, old_value, new_value, origin, reason) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                utcnow(),
                account_id,
                "paused",
                1,
                0,
                actor,
                "reanudación confirmada",
            ),
        )
    return {"account_id": account_id, "paused": False, "reset_at": utcnow()}


def set_thresholds(
    db_path: str | Path,
    account_id: str,
    *,
    changes: dict,
    origin: str = "cli",
    confirm: bool = False,
    reason: str = "",
) -> dict:
    if account_id not in load_accounts():
        raise RiskPauseError(f"cuenta desconocida: {account_id}")
    current = config(db_path, account_id)
    old = {
        "max_consecutive_losses": current.max_consecutive_losses,
        "daily_loss_pct": current.daily_loss_pct,
    }
    actions = []
    for field, raw in changes.items():
        if field not in FIELDS:
            raise RiskPauseError(f"campo desconocido: {field}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise RiskPauseError(f"{field}: valor no numérico") from exc
        if field == "max_consecutive_losses":
            if value < 1 or int(value) != value:
                raise RiskPauseError(
                    "max_consecutive_losses debe ser entero >= 1"
                )
            new_value: float = int(value)
        else:
            if not 0 < value <= 1:
                raise RiskPauseError("daily_loss_pct debe estar en (0, 1]")
            new_value = value
        if abs(new_value - old[field]) <= 1e-12:
            continue
        loosening = new_value > old[field]
        if loosening and _frozen(db_path):
            raise RiskPauseError(
                f"{field}: F13 congelado/iniciado; solo se permite apretar"
            )
        if loosening and not confirm:
            raise RiskPauseError(
                f"{field}: aflojar requiere confirmación explícita"
            )
        actions.append(
            {"field": field, "old": old[field], "new": new_value, "loosening": loosening}
        )
    if not actions:
        return {"ok": True, "changes": [], "config": old}
    init_riskpause(db_path)
    new_values = dict(old)
    for action in actions:
        new_values[action["field"]] = action["new"]
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO account_risk_config"
            "(account_id, max_consecutive_losses, daily_loss_pct, updated_at, updated_by) "
            "VALUES(?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
            "max_consecutive_losses=excluded.max_consecutive_losses, "
            "daily_loss_pct=excluded.daily_loss_pct, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by",
            (
                account_id,
                int(new_values["max_consecutive_losses"]),
                float(new_values["daily_loss_pct"]),
                utcnow(),
                origin,
            ),
        )
        for action in actions:
            con.execute(
                "INSERT INTO account_risk_history"
                "(ts, account_id, field, old_value, new_value, origin, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    account_id,
                    action["field"],
                    action["old"],
                    action["new"],
                    origin,
                    reason,
                ),
            )
    return {"ok": True, "changes": actions, "config": new_values}


__all__ = [
    "DEFAULT_DAILY_LOSS_PCT",
    "DEFAULT_MAX_CONSECUTIVE_LOSSES",
    "FIELDS",
    "RiskConfig",
    "RiskPauseError",
    "config",
    "init_riskpause",
    "pause_status",
    "resume",
    "set_thresholds",
]
