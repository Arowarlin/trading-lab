from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    metrics: dict
    exposure: float


def run(
    df: pd.DataFrame,
    target: pd.Series,
    starting_cash: float = 100_000.0,
    commission_bps: float = 1.0,
    slippage_bps: float = 5.0,
) -> BacktestResult:
    """Backtest long-only, sin apalancamiento, ejecución en la apertura siguiente.

    Costes: comisión y slippage en puntos básicos sobre el nocional.
    """
    df = df.copy()
    tgt = target.reindex(df.index).astype(float).clip(0.0, 1.0).fillna(0.0)
    pos_target = tgt.shift(1).fillna(0.0)

    cash = float(starting_cash)
    shares = 0.0
    avg_cost = 0.0
    rows: list[dict] = []
    trades: list[dict] = []
    realized: list[float] = []

    for dt, bar in df.iterrows():
        px_open = float(bar["open"])
        if px_open <= 0 or not np.isfinite(px_open):
            continue

        desired = float(pos_target.loc[dt])
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

            notional = abs(delta) * fill_px
            fee = notional * commission_bps / 10_000

            if delta > 0:
                total_cost = avg_cost * shares + delta * fill_px
                shares += delta
                avg_cost = total_cost / shares if shares > 0 else 0.0
            else:
                sold = -delta
                realized.append((fill_px - avg_cost) * sold - fee)
                shares += delta
                if shares <= 1e-9:
                    shares = 0.0
                    avg_cost = 0.0

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

    if not rows:
        raise RuntimeError("Backtest sin barras válidas")

    eq = pd.DataFrame(rows).set_index("ts")["equity"].astype(float)
    rets = eq.pct_change().fillna(0.0)
    metrics = compute_metrics(eq, rets, realized, float(pos_target.mean()))

    return BacktestResult(
        equity=eq,
        returns=rets,
        trades=pd.DataFrame(trades),
        metrics=metrics,
        exposure=float(pos_target.mean()),
    )


def compute_metrics(
    eq: pd.Series,
    rets: pd.Series,
    realized: list[float],
    exposure: float,
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
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    wins = sum(1 for p in realized if p > 0)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "num_trades": len(realized),
        "win_rate": (wins / len(realized)) if realized else 0.0,
        "exposure": exposure,
        "final_equity": float(eq.iloc[-1]),
        "bars": len(eq),
    }
