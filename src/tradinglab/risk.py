from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import RiskSettings


@dataclass
class RiskCheck:
    approved: bool
    qty: int
    reason: str


def size_position(
    equity: float,
    price: float,
    atr_value: float,
    cfg: RiskSettings,
    max_pct: float | None = None,
) -> int:
    """Tamaño por riesgo (1% del equity / distancia al stop) con tope por concentración."""
    if equity <= 0 or price <= 0:
        return 0

    pct = min(cfg.max_position_pct, max_pct) if max_pct else cfg.max_position_pct
    cap_value = equity * pct
    risk_budget = equity * cfg.per_trade_risk_pct
    risk_per_share = max(atr_value * cfg.atr_stop_mult, price * 0.005)

    qty_by_risk = risk_budget / risk_per_share
    qty_by_cap = cap_value / price
    return int(max(0.0, min(qty_by_risk, qty_by_cap)))


def check_order(
    *,
    equity: float,
    cash: float,
    price: float,
    qty: int,
    current_positions: int,
    gross_exposure: float,
    cfg: RiskSettings,
) -> RiskCheck:
    if qty <= 0:
        return RiskCheck(False, 0, "cantidad cero")

    notional = qty * price
    if notional > cash:
        return RiskCheck(False, 0, "efectivo insuficiente")

    if notional > equity * cfg.max_position_pct + 1e-6:
        allowed = int(equity * cfg.max_position_pct / price)
        return RiskCheck(allowed > 0, allowed, "recortado por max_position_pct")

    if current_positions >= cfg.max_positions:
        return RiskCheck(False, 0, "máximo de posiciones alcanzado")

    if gross_exposure + notional > equity * cfg.max_gross_exposure:
        return RiskCheck(False, 0, "exposición bruta máxima alcanzada")

    return RiskCheck(True, qty, "ok")


def kill_switch(equity_series: pd.Series, cfg: RiskSettings) -> tuple[bool, str]:
    if equity_series is None or len(equity_series) < 2:
        return False, "sin historial suficiente"

    today = float(equity_series.iloc[-1])
    yesterday = float(equity_series.iloc[-2])
    if yesterday > 0:
        daily = today / yesterday - 1
        if daily <= -cfg.daily_loss_limit_pct:
            return True, f"límite de pérdida diaria alcanzado ({daily:.2%})"

    peak = float(equity_series.cummax().iloc[-1])
    if peak > 0:
        drawdown = today / peak - 1
        if drawdown <= -cfg.max_drawdown_pct:
            return True, f"drawdown máximo alcanzado ({drawdown:.2%})"

    return False, "ok"
