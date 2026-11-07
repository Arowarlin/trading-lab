"""Diario de operaciones cerradas reconstruido desde `lab.db` (solo lectura).

No crea tablas ni escribe nada. Empareja `fills` con `orders` y consume lotes
FIFO por `(bot, ticker)`. Los brokers que solo registran órdenes y no dejan
fills se muestran como "sin datos": nunca se inventan precios de entrada/salida.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .accounts import AccountDefinition, load_accounts, rules_for_account
from .orchestrator import load_bots

MIN_SAMPLE = 30
GROUPS = ("bot", "account", "profile", "ticker", "day", "hour")
SIN_DATOS = "sin datos"


@dataclass(frozen=True)
class ClosedTrade:
    bot: str
    account: str | None
    profile: str | None
    ticker: str
    qty: float
    entry_price: float
    exit_price: float
    entry_ts: str
    exit_ts: str
    pnl: float
    fees: float
    return_pct: float
    holding_hours: float | None
    day: str
    hour: int
    entry_order_id: int
    exit_order_id: int
    exit_fill_id: int


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _parse_ts(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _distribution(values: list[float]) -> dict:
    if not values:
        return {
            "n": 0,
            "min": None,
            "p5": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "max": None,
            "mean": None,
            "stdev": None,
            "histogram": [],
        }
    mean = sum(values) / len(values)
    variance = (
        sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        if len(values) > 1
        else 0.0
    )
    ordered = sorted(values)
    low, high = ordered[0], ordered[-1]
    bins = 10
    width = (high - low) / bins if high > low else 1.0
    counts = [0] * bins
    for value in values:
        index = 0 if high <= low else min(bins - 1, int((value - low) / width))
        counts[max(0, index)] += 1
    histogram = []
    for index in range(bins):
        lower = low + width * index
        upper = lower + width
        histogram.append(
            {
                "low": round(lower, 6),
                "high": round(upper, 6),
                "count": counts[index],
            }
        )
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "p5": round(_quantile(values, 0.05), 6),
        "p25": round(_quantile(values, 0.25), 6),
        "median": round(_quantile(values, 0.50), 6),
        "p75": round(_quantile(values, 0.75), 6),
        "p95": round(_quantile(values, 0.95), 6),
        "max": round(max(values), 6),
        "mean": round(mean, 6),
        "stdev": round(math.sqrt(variance), 6),
        "histogram": histogram,
    }


def _read_fills(db_path: str | Path) -> tuple[list[sqlite3.Row], dict]:
    path = Path(db_path)
    diagnostics: dict[str, Any] = {
        "source": "lab.db:fills+orders",
        "read_only": True,
        "fills_total": 0,
        "joined_fills": 0,
        "unmatched_sell_qty": 0.0,
        "open_lots_qty": 0.0,
        "error": None,
    }
    if not path.exists():
        diagnostics["error"] = "lab.db no existe"
        return [], diagnostics
    try:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3
        )
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        diagnostics["error"] = str(exc)[:300]
        return [], diagnostics
    try:
        total = connection.execute("SELECT COUNT(*) AS n FROM fills").fetchone()["n"]
        rows = connection.execute(
            "SELECT f.id AS fill_id, f.ts AS fill_ts, f.qty AS fill_qty, "
            "f.price AS fill_price, f.commission AS commission, "
            "o.id AS order_id, o.ts AS order_ts, o.ticker, o.side, o.bot "
            "FROM fills f JOIN orders o ON o.id = f.order_id "
            "ORDER BY f.ts, f.id"
        ).fetchall()
        diagnostics["fills_total"] = int(total)
        diagnostics["joined_fills"] = len(rows)
        return rows, diagnostics
    except sqlite3.Error as exc:
        diagnostics["error"] = f"sin tabla fills/orders: {exc}"[:300]
        return [], diagnostics
    finally:
        connection.close()


def load_closed_trades(
    db_path: str | Path,
    *,
    tz: str = "America/New_York",
    bots: dict[str, dict] | None = None,
) -> tuple[list[ClosedTrade], dict]:
    """Reconstruye operaciones cerradas. Nunca escribe en la base."""
    rows, diagnostics = _read_fills(db_path)
    zone = _zone(tz)
    bot_map = bots or {}
    lots: dict[tuple[str, str], list[dict]] = {}
    trades: list[ClosedTrade] = []

    for row in rows:
        ticker = str(row["ticker"] or "").upper()
        bot_id = str(row["bot"] or SIN_DATOS)
        side = str(row["side"] or "").lower()
        qty = abs(float(row["fill_qty"] or 0.0))
        price = float(row["fill_price"] or 0.0)
        commission = float(row["commission"] or 0.0)
        if not ticker or qty <= 0 or price <= 0:
            continue
        key = (bot_id, ticker)
        if side == "buy":
            lots.setdefault(key, []).append(
                {
                    "qty": qty,
                    "remaining": qty,
                    "price": price,
                    "fee_per_unit": commission / qty,
                    "ts": str(row["fill_ts"]),
                    "order_id": int(row["order_id"]),
                }
            )
            continue
        if side != "sell":
            continue

        remaining = qty
        consumed_qty = 0.0
        cost_basis = 0.0
        buy_fees = 0.0
        entry_ts: str | None = None
        entry_order_id: int | None = None
        queue = lots.setdefault(key, [])
        while remaining > 1e-12 and queue:
            lot = queue[0]
            take = min(remaining, float(lot["remaining"]))
            consumed_qty += take
            cost_basis += take * float(lot["price"])
            buy_fees += take * float(lot["fee_per_unit"])
            if entry_ts is None or str(lot["ts"]) < entry_ts:
                entry_ts = str(lot["ts"])
                entry_order_id = int(lot["order_id"])
            lot["remaining"] = float(lot["remaining"]) - take
            remaining -= take
            if lot["remaining"] <= 1e-12:
                queue.pop(0)
        if consumed_qty <= 1e-12:
            diagnostics["unmatched_sell_qty"] += qty
            continue

        matched_ratio = consumed_qty / qty
        sell_fee = commission * matched_ratio
        entry_price = cost_basis / consumed_qty
        pnl = consumed_qty * (price - entry_price) - sell_fee - buy_fees
        exit_stamp = _parse_ts(str(row["fill_ts"]))
        entry_stamp = _parse_ts(entry_ts or str(row["fill_ts"]))
        exit_local = exit_stamp.astimezone(zone)
        holding_hours = max(
            0.0, (exit_stamp - entry_stamp).total_seconds() / 3600.0
        )
        mapping = bot_map.get(bot_id) or {}
        trades.append(
            ClosedTrade(
                bot=bot_id,
                account=mapping.get("account"),
                profile=mapping.get("profile"),
                ticker=ticker,
                qty=round(consumed_qty, 8),
                entry_price=round(entry_price, 8),
                exit_price=round(price, 8),
                entry_ts=entry_stamp.astimezone(zone).isoformat(),
                exit_ts=exit_local.isoformat(),
                pnl=round(pnl, 6),
                fees=round(sell_fee + buy_fees, 6),
                return_pct=(
                    round(pnl / (entry_price * consumed_qty), 8)
                    if entry_price > 0 and consumed_qty > 0
                    else 0.0
                ),
                holding_hours=round(holding_hours, 3),
                day=exit_local.date().isoformat(),
                hour=exit_local.hour,
                entry_order_id=int(entry_order_id or row["order_id"]),
                exit_order_id=int(row["order_id"]),
                exit_fill_id=int(row["fill_id"]),
            )
        )

    diagnostics["closed_trades"] = len(trades)
    diagnostics["open_lots_qty"] = round(
        sum(float(lot["remaining"]) for queue in lots.values() for lot in queue), 8
    )
    diagnostics["unmatched_sell_qty"] = round(
        diagnostics["unmatched_sell_qty"], 8
    )
    unknown_accounts = sorted({t.bot for t in trades if t.account is None})
    diagnostics["bots_sin_cuenta"] = unknown_accounts
    # La atribución de cuenta sale de config/bots.yaml; no se deduce del bróker.
    trades.sort(key=lambda trade: (trade.exit_ts, trade.exit_fill_id))
    return trades, diagnostics


def filter_trades(
    trades: list[ClosedTrade],
    *,
    bot: str | None = None,
    account: str | None = None,
    profile: str | None = None,
    ticker: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[ClosedTrade]:
    for value, name in ((since, "since"), (until, "until")):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} inválido: usa YYYY-MM-DD") from exc

    def matches(value: str | None, wanted: str | None) -> bool:
        if not wanted:
            return True
        if wanted == SIN_DATOS:
            return value is None
        return value == wanted

    out = []
    for trade in trades:
        if not matches(trade.bot, bot):
            continue
        if not matches(trade.account, account):
            continue
        if not matches(trade.profile, profile):
            continue
        if not matches(trade.ticker, ticker.upper() if ticker else None):
            continue
        if since and trade.day < since:
            continue
        if until and trade.day > until:
            continue
        out.append(trade)
    return out


def _capital_for(
    trades: list[ClosedTrade], accounts: dict[str, AccountDefinition]
) -> tuple[float | None, list[str], list[str]]:
    account_ids = sorted({trade.account for trade in trades if trade.account})
    missing = sorted({trade.bot for trade in trades if trade.account is None})
    unknown = [account_id for account_id in account_ids if account_id not in accounts]
    if not account_ids or missing or unknown:
        return None, account_ids, sorted(set(missing) | set(unknown))
    capital = sum(float(accounts[account_id].account_size) for account_id in account_ids)
    return (capital if capital > 0 else None), account_ids, []


def _consistency_pct(
    account_ids: list[str], accounts: dict[str, AccountDefinition]
) -> tuple[float | None, str | None]:
    values = set()
    for account_id in account_ids:
        account = accounts.get(account_id)
        if account is None:
            continue
        rules = rules_for_account(account)
        values.add(rules.consistency_pct)
    if len(values) == 1:
        value = next(iter(values))
        if value is not None:
            return float(value), None
        return None, "sin regla de consistencia configurada"
    return None, "reglas de consistencia distintas entre cuentas"


def _concentration(
    trades: list[ClosedTrade], *, consistency_pct: float | None
) -> dict:
    net = sum(trade.pnl for trade in trades)
    gross_profit = sum(trade.pnl for trade in trades if trade.pnl > 0)
    ordered = sorted((trade.pnl for trade in trades), reverse=True)
    top3 = sum(ordered[:3])
    daily: dict[str, float] = {}
    for trade in trades:
        daily[trade.day] = daily.get(trade.day, 0.0) + trade.pnl
    best_day = max(daily.values()) if daily else None
    top3_share = (top3 / net) if net > 0 else None
    top3_gross_share = (sum(value for value in ordered[:3] if value > 0) / gross_profit) if gross_profit > 0 else None
    best_day_share = (best_day / net) if net > 0 and best_day is not None else None
    consistency_ok = (
        best_day_share <= consistency_pct
        if best_day_share is not None and consistency_pct is not None
        else None
    )
    return {
        "net_profit": round(net, 6),
        "gross_profit": round(gross_profit, 6),
        "top3_pnl": round(top3, 6),
        "top3_share": round(top3_share, 6) if top3_share is not None else None,
        "top3_gross_share": (
            round(top3_gross_share, 6) if top3_gross_share is not None else None
        ),
        "best_day": max(daily, key=daily.get) if daily else None,
        "best_day_pnl": round(best_day, 6) if best_day is not None else None,
        "best_day_share": (
            round(best_day_share, 6) if best_day_share is not None else None
        ),
        "consistency_pct": consistency_pct,
        "consistency_ok": consistency_ok,
        "days": len(daily),
    }


def _daily_metrics(
    trades: list[ClosedTrade], capital: float | None
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    daily: dict[str, float] = {}
    for trade in trades:
        daily[trade.day] = daily.get(trade.day, 0.0) + trade.pnl
    if not daily:
        return None, None, None, None, None
    days = sorted(daily)
    if capital is None or capital <= 0 or len(days) < 2:
        return None, None, None, None, None
    returns = []
    equity = capital
    equity_points = [capital]
    for day in days:
        pnl = daily[day]
        returns.append(pnl / equity if equity > 0 else 0.0)
        equity += pnl
        equity_points.append(equity)
    mean = sum(returns) / len(returns)
    variance = (
        sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        if len(returns) > 1
        else 0.0
    )
    stdev = math.sqrt(variance)
    sharpe = (mean / stdev * math.sqrt(252)) if stdev > 0 else None
    downside = [min(0.0, value) for value in returns]
    downside_dev = math.sqrt(sum(value * value for value in downside) / len(downside))
    sortino = (mean / downside_dev * math.sqrt(252)) if downside_dev > 0 else None
    peak = equity_points[0]
    max_dd = 0.0
    max_dd_usd = 0.0
    for point in equity_points:
        peak = max(peak, point)
        drawdown = point / peak - 1.0 if peak > 0 else 0.0
        max_dd = min(max_dd, drawdown)
        max_dd_usd = min(max_dd_usd, point - peak)
    first = date.fromisoformat(days[0])
    last = date.fromisoformat(days[-1])
    span_days = max(1.0, (last - first).days + 1)
    years = max(span_days / 365.25, 1.0 / 252.0)
    final = equity_points[-1]
    cagr = (final / capital) ** (1.0 / years) - 1.0 if final > 0 else None
    calmar = (cagr / abs(max_dd)) if cagr is not None and max_dd < 0 else None
    return sharpe, sortino, calmar, max_dd, max_dd_usd


def summarize(
    trades: list[ClosedTrade],
    accounts: dict[str, AccountDefinition],
) -> dict:
    if not trades:
        return {
            "n": 0,
            "net_pnl": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "expectancy_pct": None,
            "avg_win": None,
            "avg_loss": None,
            "payoff": None,
            "best_trade": None,
            "worst_trade": None,
            "total_return": None,
            "capital": None,
            "max_drawdown": None,
            "max_drawdown_usd": None,
            "sharpe": None,
            "sortino": None,
            "calmar": None,
            "avg_holding_hours": None,
            "first_day": None,
            "last_day": None,
            "distribution": _distribution([]),
            "concentration": _concentration([], consistency_pct=None),
            "consistency_pct": None,
            "consistency_note": "sin datos",
            "sample_ok": False,
            "sample_warning": f"sin datos: N=0 < {MIN_SAMPLE}",
            "capital_accounts": [],
            "capital_missing": [],
        }

    pnls = [trade.pnl for trade in trades]
    returns = [trade.return_pct for trade in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    net = sum(pnls)
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    capital, capital_accounts, capital_missing = _capital_for(trades, accounts)
    consistency_pct, consistency_note = _consistency_pct(capital_accounts, accounts)
    sharpe, sortino, calmar, max_dd, max_dd_usd = _daily_metrics(trades, capital)
    distribution = _distribution(returns)
    ordered_days = sorted({trade.day for trade in trades})
    return {
        "n": len(trades),
        "net_pnl": round(net, 6),
        "gross_profit": round(gross_profit, 6),
        "gross_loss": round(gross_loss, 6),
        "win_rate": round(len(wins) / len(trades), 6),
        "profit_factor": (
            round(gross_profit / abs(gross_loss), 6)
            if gross_loss < 0
            else None
        ),
        "profit_factor_note": (
            None if gross_loss < 0 else "sin operaciones perdedoras"
        ),
        "expectancy": round(net / len(trades), 6),
        "expectancy_pct": round(sum(returns) / len(returns), 8),
        "avg_win": round(gross_profit / len(wins), 6) if wins else None,
        "avg_loss": round(gross_loss / len(losses), 6) if losses else None,
        "payoff": (
            round((gross_profit / len(wins)) / abs(gross_loss / len(losses)), 6)
            if wins and losses
            else None
        ),
        "best_trade": round(max(pnls), 6),
        "worst_trade": round(min(pnls), 6),
        "total_return": round(net / capital, 8) if capital else None,
        "capital": round(capital, 2) if capital else None,
        "max_drawdown": round(max_dd, 8) if max_dd is not None else None,
        "max_drawdown_usd": (
            round(max_dd_usd, 2) if max_dd_usd is not None else None
        ),
        "sharpe": round(sharpe, 6) if sharpe is not None else None,
        "sortino": round(sortino, 6) if sortino is not None else None,
        "calmar": round(calmar, 6) if calmar is not None else None,
        "avg_holding_hours": round(
            sum(trade.holding_hours or 0.0 for trade in trades) / len(trades), 3
        ),
        "first_day": ordered_days[0] if ordered_days else None,
        "last_day": ordered_days[-1] if ordered_days else None,
        "distribution": distribution,
        "concentration": _concentration(
            trades, consistency_pct=consistency_pct
        ),
        "consistency_pct": consistency_pct,
        "consistency_note": consistency_note,
        "sample_ok": len(trades) >= MIN_SAMPLE,
        "sample_warning": (
            None
            if len(trades) >= MIN_SAMPLE
            else f"muestra insuficiente: N={len(trades)} < {MIN_SAMPLE}"
        ),
        "capital_accounts": capital_accounts,
        "capital_missing": capital_missing,
    }


def _group_key(trade: ClosedTrade, field: str) -> str:
    value = getattr(trade, field)
    return SIN_DATOS if value is None else str(value)


def group_summaries(
    trades: list[ClosedTrade],
    field: str,
    accounts: dict[str, AccountDefinition],
) -> list[dict]:
    if field not in GROUPS:
        raise ValueError(f"group_by inválido: {field}")
    grouped: dict[str, list[ClosedTrade]] = {}
    for trade in trades:
        grouped.setdefault(_group_key(trade, field), []).append(trade)
    rows = []
    for key, group in grouped.items():
        summary = summarize(group, accounts)
        rows.append({"key": key, **summary})
    if field in ("day", "hour"):
        rows.sort(key=lambda row: row["key"])
    else:
        rows.sort(key=lambda row: row["net_pnl"], reverse=True)
    return rows


def build_journal(
    db_path: str | Path,
    *,
    tz: str = "America/New_York",
    bot: str | None = None,
    account: str | None = None,
    profile: str | None = None,
    ticker: str | None = None,
    since: str | None = None,
    until: str | None = None,
    group_by: str = "bot",
    limit: int = 200,
) -> dict:
    """Payload del diario. Solo lectura; si falta un dato se marca sin datos."""
    if group_by not in GROUPS:
        raise ValueError(f"group_by inválido: usa {', '.join(GROUPS)}")
    limit = max(1, int(limit))
    accounts = load_accounts()
    bots = {
        spec.id: {"account": spec.account, "profile": spec.profile}
        for spec in load_bots()
    }
    all_trades, diagnostics = load_closed_trades(
        db_path, tz=tz, bots=bots
    )
    filtered = filter_trades(
        all_trades,
        bot=bot,
        account=account,
        profile=profile,
        ticker=ticker,
        since=since,
        until=until,
    )
    summary = summarize(filtered, accounts)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(db_path),
        "read_only": True,
        "filters": {
            "bot": bot,
            "account": account,
            "profile": profile,
            "ticker": ticker,
            "since": since,
            "until": until,
            "group_by": group_by,
        },
        "filters_available": {
            "bots": sorted({trade.bot for trade in all_trades}),
            "accounts": sorted(
                {trade.account for trade in all_trades if trade.account}
            )
            + ([SIN_DATOS] if any(trade.account is None for trade in all_trades) else []),
            "profiles": sorted(
                {trade.profile for trade in all_trades if trade.profile}
            )
            + ([SIN_DATOS] if any(trade.profile is None for trade in all_trades) else []),
            "tickers": sorted({trade.ticker for trade in all_trades}),
        },
        "diagnostics": diagnostics,
        "summary": summary,
        "groups": group_summaries(filtered, group_by, accounts),
        "by_account": group_summaries(filtered, "account", accounts),
        "by_bot": group_summaries(filtered, "bot", accounts),
        "trades": [asdict(trade) for trade in reversed(filtered[-limit:])],
        "total_trades": len(filtered),
    }


__all__ = [
    "ClosedTrade",
    "GROUPS",
    "MIN_SAMPLE",
    "SIN_DATOS",
    "build_journal",
    "filter_trades",
    "group_summaries",
    "load_closed_trades",
    "summarize",
]
