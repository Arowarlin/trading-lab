"""Stop diario de la cuenta compartida por todos los carriles.

La pérdida del día se mide sobre la equity real de MT5 (realizada + flotante) y
se compara con ``account_daily_stop`` de ``config/accounts.yaml``. No abre nada:
solo devuelve el veredicto que PropGuard, el forward y el carril IA consultan.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .accounts import effective_limits, load_accounts, rules_for_account
from .alerts import send as send_alert
from .db import connect, init_db
from .prop.guard import AccountSnapshot, PropGuard, evaluate_account
from .symbol_risk import account_magics


class AccountDailyError(RuntimeError):
    pass


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _equity_series(broker):
    try:
        series = broker.equity_series()
    except TypeError:
        series = broker.equity_series(180)
    if series is None or len(series) == 0:
        raise AccountDailyError("equity sin datos")
    frame = pd.Series(series).astype(float)
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.date_range(
            end=pd.Timestamp.now(tz="UTC"), periods=len(frame), freq="min",
        )
    elif frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.sort_index()


def _ea_context(account_id: str) -> tuple[set[int], set[str]]:
    try:
        from .ea_registry import load_eas

        eas = [ea for ea in load_eas() if ea.account == account_id]
    except Exception:
        return set(), set()
    magics = {int(ea.magic) for ea in eas}
    for ea in eas:
        magics.update(int(item) for item in ea.managed_magics)
    return magics, {ea.bot_id for ea in eas}


def _ea_realized_today(
    db_path: str | Path, bot_ids: set[str], now: datetime
) -> float:
    if not bot_ids:
        return 0.0
    try:
        from .journal import load_closed_trades

        trades, _ = load_closed_trades(db_path, tz="UTC", bots=None)
        today = now.astimezone(timezone.utc).date().isoformat()
        return float(
            sum(
                trade.pnl
                for trade in trades
                if trade.bot in bot_ids and str(trade.exit_ts)[:10] == today
            )
        )
    except Exception:
        return 0.0


def _record_stop_once(
    db_path: str | Path,
    *,
    account_id: str,
    day: str,
    payload: dict,
) -> bool:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT params FROM console_actions WHERE action = 'account_stop' "
            "AND ts >= ?",
            (f"{day}T00:00:00",),
        ).fetchall()
    for row in rows:
        try:
            data = json.loads(row["params"] or "{}")
        except (TypeError, ValueError):
            continue
        if data.get("account") == account_id and data.get("day") == day:
            return False
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="account_stop",
            params={"account": account_id, "day": day, **payload},
            result=str(payload.get("reason") or "stop de cuenta"),
            ok=False,
            actor="account_daily",
            detail=json.dumps(payload, ensure_ascii=False, sort_keys=True)[:900],
        )
    except Exception:
        pass
    return True


def account_daily_report(
    db_path: str | Path,
    account_id: str = "ftmo_demo",
    *,
    broker,
    now: datetime | None = None,
    closing: bool = False,
    alert: bool = True,
) -> dict:
    """Estado del stop diario de cuenta; incluye flotante de todos los magics."""
    accounts = load_accounts()
    account = accounts.get(account_id)
    if account is None:
        raise AccountDailyError(f"cuenta desconocida: {account_id}")
    rules = rules_for_account(account)
    limits = effective_limits(db_path, account, now=now)
    positions = broker.positions() or []
    health = broker.health()
    ea_magics, ea_bots = _ea_context(account_id)
    try:
        curve = _equity_series(broker)
    except Exception:
        curve = pd.Series(
            [float(health.get("equity") or 0.0)],
            index=pd.DatetimeIndex([pd.Timestamp.now(tz="UTC")]),
        )
    try:
        state = PropGuard.state_from_equity(
            rules,
            curve,
            initial_balance=rules.account_size,
            open_positions=len(positions),
        )
    except Exception as exc:
        raise AccountDailyError(f"equity no disponible: {exc}") from exc
    equity = float(health.get("equity") or state.equity or 0.0)
    if equity <= 0:
        raise AccountDailyError("equity inválido")
    snapshot = AccountSnapshot(
        equity=equity,
        day_start_equity=state.day_start_equity,
        initial_balance=rules.account_size,
        peak_equity=state.peak_equity or equity,
        realized_pnl_today=state.closed_pnl_today,
        open_positions=len(positions),
        open_risk_usd=0.0,
    )
    report = evaluate_account(
        rules,
        snapshot,
        limits=limits,
        proposed_risk_usd=0.0,
        closing=closing,
    )
    daily_stop_pct = float(limits.daily_loss_pct)
    daily_stop_usd = float(rules.account_size) * daily_stop_pct
    pnl_today = float(equity - state.day_start_equity)
    floating_by_magic: dict[int, float] = {}
    for position in positions:
        magic = int(position.get("magic") or 0)
        floating_by_magic[magic] = floating_by_magic.get(magic, 0.0) + float(
            position.get("profit") or 0.0
        ) + float(position.get("swap") or 0.0) + float(
            position.get("commission") or 0.0
        )
    lab_magics = set(account_magics(account_id)) - ea_magics
    ea_floating = sum(floating_by_magic.get(magic, 0.0) for magic in ea_magics)
    lab_floating = sum(floating_by_magic.get(magic, 0.0) for magic in lab_magics)
    moment = _as_utc(now)
    ea_realized = _ea_realized_today(db_path, ea_bots, moment)
    pnl_without_ea = pnl_today - ea_floating - ea_realized
    stop_cause = "ninguna"
    alerted = False
    if not report.allowed:
        if pnl_without_ea > -daily_stop_usd and pnl_today <= -daily_stop_usd:
            stop_cause = "ea"
        elif ea_floating < 0 or ea_realized < 0:
            stop_cause = "shared"
        else:
            stop_cause = "lab"
        day = moment.date().isoformat()
        payload = {
            "account": account_id,
            "day": day,
            "cause": stop_cause,
            "reason": report.reason,
            "pnl_today": round(pnl_today, 2),
            "ea_floating": round(ea_floating, 2),
            "ea_realized": round(ea_realized, 2),
            "lab_floating": round(lab_floating, 2),
        }
        alerted = _record_stop_once(
            db_path, account_id=account_id, day=day, payload=payload
        )
        if alerted and alert:
            message = (
                f"stop de cuenta {account_id} ({stop_cause}): {report.reason}; "
                f"EA flotante {ea_floating:+,.2f} / realizado {ea_realized:+,.2f}"
            )
            try:
                send_alert(
                    f"account_stop:{account_id}",
                    message,
                    severity="critical",
                    db_path=db_path,
                )
            except Exception:
                pass
    return {
        "account": account_id,
        "allowed": bool(report.allowed),
        "closing": bool(closing),
        "reason": report.reason,
        "severity": report.severity,
        "daily_stop_pct": round(daily_stop_pct, 6),
        "daily_stop_usd": round(daily_stop_usd, 2),
        "equity": round(equity, 2),
        "day_start_equity": round(float(state.day_start_equity), 2),
        "pnl_today": round(pnl_today, 2),
        "loss_used_usd": round(max(0.0, -pnl_today), 2),
        "used_pct": round(max(0.0, -pnl_today) / daily_stop_usd, 6)
        if daily_stop_usd > 0 else None,
        "remaining_usd": round(max(0.0, report.remaining_usd), 2),
        "open_positions": len(positions),
        "floating_by_magic": {
            str(magic): round(value, 2)
            for magic, value in sorted(floating_by_magic.items())
        },
        "magics": sorted(floating_by_magic),
        "ea_magics": sorted(ea_magics),
        "lab_magics": sorted(lab_magics),
        "ea_floating_usd": round(ea_floating, 2),
        "lab_floating_usd": round(lab_floating, 2),
        "ea_realized_today": round(ea_realized, 2),
        "stop_cause": stop_cause,
        "alerted": alerted,
        "generated_at": moment.isoformat(),
    }


__all__ = ["AccountDailyError", "account_daily_report"]
