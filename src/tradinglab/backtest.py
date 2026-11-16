from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import time as dt_time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .carry import CostModel
from .metrics import metrics_warning, recovery_factor, risk_of_ruin, system_quality_number

TRADING_DAYS = 252


def _parse_clock(value: str) -> dt_time:
    try:
        hour, minute = str(value).split(":", 1)
        return dt_time(int(hour), int(minute))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"hora inválida: {value}") from exc


def _session_bounds(session: tuple[str, str] | None) -> tuple[dt_time, dt_time] | None:
    if session is None:
        return None
    if len(session) != 2:
        raise ValueError("session debe ser (inicio, fin)")
    start, end = _parse_clock(session[0]), _parse_clock(session[1])
    if start == end:
        raise ValueError("session no puede tener inicio igual a fin")
    return start, end


def _local_stamp(value, timezone_name: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert(ZoneInfo(timezone_name))


def _inside_session(
    local: pd.Timestamp, bounds: tuple[dt_time, dt_time] | None
) -> bool:
    if bounds is None:
        return True
    start, end = bounds
    clock = local.time()
    if start < end:
        return start <= clock <= end
    return clock >= start or clock <= end


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    metrics: dict
    exposure: float
    trade_pnls: list[float] = field(default_factory=list)
    trade_days: list[str] = field(default_factory=list)
    trade_returns: list[float] = field(default_factory=list)
    costs_status: str = "Sin datos: swap no disponible"
    carry_paid: float = 0.0
    time_in_market: float = 0.0


def run(
    df: pd.DataFrame,
    target: pd.Series,
    starting_cash: float = 100_000.0,
    commission_bps: float = 1.0,
    slippage_bps: float = 5.0,
    max_gross: float = 1.0,
    session: tuple[str, str] | None = None,
    session_tz: str = "UTC",
    flat_dates: Iterable[str] | None = None,
    vol_target: dict | None = None,
    carry: CostModel | None = None,
) -> BacktestResult:
    """Backtest long/short, sin apalancamiento, ejecución en la apertura siguiente.

    `target` va de -1 (corto a plena exposición) a +1 (largo). `max_gross`
    limita la exposición bruta para no simular apalancamiento accidental.
    Costes: comisión y slippage en puntos básicos sobre el nocional.

    `session` opcional (p. ej. ``("09:30", "16:00")``) fuerza objetivo 0 fuera
    de la ventana local; `flat_dates` fuerza objetivo 0 en días completos
    (rollover/vencimiento). Así se evita mantener posiciones fuera de sesión.
    """
    df = df.copy()
    tgt = (
        target.reindex(df.index)
        .astype(float)
        .clip(-abs(max_gross), abs(max_gross))
        .fillna(0.0)
    )
    if vol_target:
        # Objetivo de volatilidad: el factor se estima con datos hasta t-1 y
        # el motor ya aplaza el objetivo una barra más al ejecutar.
        from .vol_target import scale as vol_scale

        factor = vol_scale(
            df["close"].astype(float).pct_change().fillna(0.0),
            target_vol_annual=float(vol_target["target_vol_annual"]),
            halflife_days=int(vol_target.get("halflife_days", 30)),
            max_leverage=float(vol_target.get("max_leverage", 2.0)),
            rebalance=str(vol_target.get("rebalance", "W")),
        )
        tgt = tgt * factor.reindex(df.index).fillna(1.0)
    pos_target = tgt.shift(1).fillna(0.0)
    bounds = _session_bounds(session)
    flat = {str(value) for value in (flat_dates or [])}

    cash = float(starting_cash)
    shares = 0.0  # negativo = corto
    avg_cost = 0.0
    rows: list[dict] = []
    trades: list[dict] = []
    realized: list[float] = []
    realized_days: list[str] = []
    realized_returns: list[float] = []
    effective_exposure: list[float] = []
    last_date = None
    last_close = 0.0
    costs_status = carry.status if carry else "Sin datos: swap no disponible"
    trip_entry_fee = 0.0
    trip_pnl = 0.0
    trip_return = 0.0
    carry_paid = 0.0

    for dt, bar in df.iterrows():
        px_open = float(bar["open"])
        if px_open <= 0 or not np.isfinite(px_open):
            continue
        if (
            last_date is not None
            and dt.date() > last_date
            and shares != 0
            and carry is not None
        ):
            carry_amount = carry.carry_for_nights(
                "long" if shares > 0 else "short",
                notional=abs(shares) * last_close,
                shares=shares,
                start_day=last_date,
                end_day=dt.date(),
            )
            cash += carry_amount
            carry_paid += carry_amount
            trip_pnl += carry_amount

        local = _local_stamp(dt, session_tz)
        force_flat = local.date().isoformat() in flat
        if force_flat or not _inside_session(local, bounds):
            desired = 0.0
        else:
            desired = float(pos_target.loc[dt])
        effective_exposure.append(abs(desired))
        equity_open = cash + shares * px_open
        desired_shares = (desired * equity_open) / px_open
        delta = desired_shares - shares

        # Umbral mínimo para evitar rebalanceos por ruido
        if abs(delta) * px_open > max(equity_open * 0.001, 1.0):
            if delta > 0:
                fill_px = px_open * (1 + slippage_bps / 10_000)
                side = "buy"
            else:
                fill_px = px_open * (1 - slippage_bps / 10_000)
                side = "sell"

            shares_before = shares
            new_shares = shares_before + delta
            if abs(new_shares) < 1e-9:
                new_shares = 0.0
            closing = 0.0
            if shares_before != 0 and (shares_before > 0) != (delta > 0):
                closing = min(abs(delta), abs(shares_before))
            opening = abs(delta) - closing
            close_fee = closing * fill_px * commission_bps / 10_000.0
            open_fee = opening * fill_px * commission_bps / 10_000.0
            fee = close_fee + open_fee
            flip = (
                shares_before != 0
                and new_shares != 0
                and (shares_before > 0) != (new_shares > 0)
            )
            closed_trip = False

            # PnL de la parte cerrada; la comisión de entrada se asigna
            # proporcionalmente a esa parte.
            if closing:
                if shares_before > 0:
                    pnl = (fill_px - avg_cost) * closing
                    trade_return = (
                        (fill_px - avg_cost) / avg_cost if avg_cost > 0 else 0.0
                    )
                else:
                    pnl = (avg_cost - fill_px) * closing
                    trade_return = (
                        (avg_cost - fill_px) / avg_cost if avg_cost > 0 else 0.0
                    )
                fraction = closing / abs(shares_before)
                entry_fee_part = trip_entry_fee * fraction
                trip_entry_fee -= entry_fee_part
                trip_pnl += pnl - entry_fee_part - close_fee
                trip_return += trade_return * fraction
                if new_shares == 0 or flip:
                    realized.append(trip_pnl)
                    realized_returns.append(trip_return)
                    realized_days.append(dt.date().isoformat())
                    closed_trip = True

            if new_shares == 0:
                avg_cost = 0.0
            elif shares_before == 0:
                avg_cost = fill_px
            elif (
                (shares_before > 0) == (new_shares > 0)
                and (shares_before > 0) == (delta > 0)
            ):
                # Aumento en la misma dirección: coste medio ponderado.
                avg_cost = (
                    abs(shares_before) * avg_cost + abs(delta) * fill_px
                ) / abs(new_shares)
            elif flip:
                # Giro: la parte restante abre al precio de ejecución.
                avg_cost = fill_px

            if flip:
                trip_entry_fee = open_fee
                trip_pnl = 0.0
                trip_return = 0.0
            elif closed_trip:
                trip_entry_fee = 0.0
                trip_pnl = 0.0
                trip_return = 0.0
            elif opening:
                trip_entry_fee += open_fee
            shares = new_shares

            cash -= delta * fill_px + fee
            trades.append(
                {
                    "ts": dt,
                    "side": side,
                    "qty": abs(delta),
                    "price": fill_px,
                    "fee": fee,
                }
            )

        equity_close = cash + shares * float(bar["close"])
        rows.append({"ts": dt, "cash": cash, "shares": shares, "equity": equity_close})
        last_date = dt.date()
        last_close = float(bar["close"])

    if not rows:
        raise RuntimeError("Backtest sin barras válidas")

    eq = pd.DataFrame(rows).set_index("ts")["equity"].astype(float)
    rets = eq.pct_change().fillna(0.0)
    exposure = (
        float(np.mean(effective_exposure))
        if effective_exposure
        else float(pos_target.abs().mean())
    )
    metrics = compute_metrics(eq, rets, realized, exposure, realized_returns)
    in_market = sum(
        1 for row in rows if abs(float(row["shares"])) > 1e-12
    ) / len(rows)
    metrics["costs_status"] = costs_status
    metrics["carry_paid"] = carry_paid
    metrics["time_in_market"] = in_market

    return BacktestResult(
        equity=eq,
        returns=rets,
        trades=pd.DataFrame(trades),
        metrics=metrics,
        exposure=exposure,
        trade_pnls=realized,
        trade_days=realized_days,
        trade_returns=realized_returns,
        costs_status=costs_status,
        carry_paid=carry_paid,
        time_in_market=in_market,
    )


def compute_metrics(
    eq: pd.Series,
    rets: pd.Series,
    realized: list[float],
    exposure: float,
    trade_returns: list[float] | None = None,
) -> dict:
    if len(eq) < 2:
        return {}

    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1)
    years = max(len(eq) / TRADING_DAYS, 1 / TRADING_DAYS)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1)
    vol = float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(TRADING_DAYS)) if rets.std(ddof=1) > 0 else 0.0
    drawdown = eq / eq.cummax() - 1
    max_dd = float(drawdown.min())
    max_dd_usd = float((eq - eq.cummax()).min())
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    wins = sum(1 for p in realized if p > 0)
    losses = [p for p in realized if p < 0]
    gains = [p for p in realized if p > 0]
    win_rate = (wins / len(realized)) if realized else 0.0
    payoff = (
        (sum(gains) / len(gains)) / abs(sum(losses) / len(losses))
        if gains and losses
        else None
    )
    expectancy = float(sum(realized) / len(realized)) if realized else 0.0
    sqn = system_quality_number(trade_returns or [])
    recovery = recovery_factor(sum(realized), max_dd_usd)
    ruin, ruin_assumptions = risk_of_ruin(win_rate, payoff)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "max_drawdown_usd": max_dd_usd,
        "calmar": calmar,
        "num_trades": len(realized),
        "win_rate": win_rate,
        "expectancy": expectancy,
        "sqn": sqn,
        "recovery_factor": recovery,
        "risk_of_ruin": ruin,
        "risk_of_ruin_assumptions": ruin_assumptions,
        "metrics_warning": metrics_warning(len(realized)),
        "exposure": exposure,
        "final_equity": float(eq.iloc[-1]),
        "bars": len(eq),
    }
