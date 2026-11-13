"""Stop diario de la cuenta compartida por todos los carriles.

La pérdida del día se mide sobre la equity real de MT5 (realizada + flotante) y
se compara con ``account_daily_stop`` de ``config/accounts.yaml``. No abre nada:
solo devuelve el veredicto que PropGuard, el forward y el carril IA consultan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .accounts import effective_limits, load_accounts, rules_for_account
from .prop.guard import AccountSnapshot, PropGuard, evaluate_account


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


def account_daily_report(
    db_path: str | Path,
    account_id: str = "ftmo_demo",
    *,
    broker,
    now: datetime | None = None,
    closing: bool = False,
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
        "generated_at": _as_utc(now).isoformat(),
    }


__all__ = ["AccountDailyError", "account_daily_report"]
