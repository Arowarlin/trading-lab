"""Métricas informativas de operaciones. No cambian criterios de propuesta.

SQN, Recovery Factor y riesgo de ruina se calculan solo si hay muestra
suficiente; con N < 30 se marcan como informativos.
"""

from __future__ import annotations

import math
from pathlib import Path

MIN_SAMPLE = 30
RISK_PER_TRADE = 0.01
RISK_OF_RUIN_ASSUMPTIONS = (
    "operaciones independientes; win rate y payoff constantes; "
    "riesgo fijo del 1% del capital por operación; ruina = perder todo el capital"
)


def system_quality_number(returns: list[float]) -> float | None:
    """SQN de Van Tharp: sqrt(N) * media(R) / desv(R).

    `R` es el retorno por operación. El diario no guarda el riesgo inicial de
    cada trade, así que se usa el retorno porcentual como proxy explícito.
    """
    values = [
        float(value)
        for value in returns
        if value is not None and math.isfinite(float(value))
    ]
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    std = math.sqrt(variance)
    if std <= 0:
        return None
    return math.sqrt(n) * mean / std


def recovery_factor(net_pnl: float, max_drawdown_usd: float | None) -> float | None:
    """Beneficio neto / |max drawdown en USD|. None si no hay drawdown."""
    if max_drawdown_usd is None or max_drawdown_usd == 0:
        return None
    return float(net_pnl) / abs(float(max_drawdown_usd))


def risk_of_ruin(
    win_rate: float | None,
    payoff: float | None,
    *,
    risk_per_trade: float = RISK_PER_TRADE,
) -> tuple[float | None, str]:
    """Aproximación de ruina con fracción fija de capital.

    edge = p - (1-p)/payoff; unidades = 1/f;
    ruina = ((1-edge)/(1+edge))**unidades, con edge > 0. Si edge <= 0, ruina=1.
    Supuestos en `RISK_OF_RUIN_ASSUMPTIONS`.
    """
    if (
        win_rate is None
        or payoff is None
        or payoff <= 0
        or risk_per_trade <= 0
    ):
        return None, RISK_OF_RUIN_ASSUMPTIONS
    p = min(max(float(win_rate), 0.0), 1.0)
    edge = p - (1.0 - p) / float(payoff)
    if edge <= 0:
        return 1.0, RISK_OF_RUIN_ASSUMPTIONS
    units = 1.0 / float(risk_per_trade)
    value = ((1.0 - edge) / (1.0 + edge)) ** units
    return min(max(value, 0.0), 1.0), RISK_OF_RUIN_ASSUMPTIONS


def metrics_warning(n: int) -> str | None:
    if n >= MIN_SAMPLE:
        return None
    return f"aviso: N={n} < {MIN_SAMPLE}; SQN, Recovery y ruina son informativos"


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = min(max(int(round((len(ordered) - 1) * q)), 0), len(ordered) - 1)
    return ordered[index]


def execution_metrics(
    db_path: str | Path,
    *,
    bot: str,
    start_date: str,
) -> dict:
    """Slippage real vs señal y error de tamaño vs orden.

    Se calculó dentro de F13; ahora vive aquí porque lo usan el drift y la
    incubadora de cualquier carril. Solo lee `orders`, `fills` y `signals`.
    """
    from .db import connect, init_db

    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT o.id, o.ts, o.ticker, o.side, o.qty, o.bot, "
            "f.price AS fill_price, f.qty AS fill_qty "
            "FROM orders o JOIN fills f ON f.order_id = o.id "
            "WHERE o.bot = ? AND o.ts >= ? ORDER BY o.id",
            (bot, start_date),
        ).fetchall()
        samples: list[dict] = []
        for row in rows:
            signal = con.execute(
                "SELECT price FROM signals WHERE ticker = ? AND bot = ? AND ts <= ? "
                "ORDER BY id DESC LIMIT 1",
                (row["ticker"], bot, row["ts"]),
            ).fetchone()
            if not signal or not signal["price"] or not row["fill_price"]:
                continue
            sign = 1.0 if row["side"].lower() == "buy" else -1.0
            slippage = (float(row["fill_price"]) / float(signal["price"]) - 1.0) * 10_000 * sign
            samples.append(
                {
                    "ticker": row["ticker"],
                    "slippage_bps": slippage,
                    "size_error": abs(float(row["fill_qty"]) - float(row["qty"])),
                }
            )
    values = [item["slippage_bps"] for item in samples]
    return {
        "fills": len(samples),
        "slippage_p50_bps": _percentile(values, 0.50),
        "slippage_p95_bps": _percentile(values, 0.95),
        "size_error_max": max((item["size_error"] for item in samples), default=0.0),
    }


__all__ = [
    "MIN_SAMPLE",
    "RISK_OF_RUIN_ASSUMPTIONS",
    "RISK_PER_TRADE",
    "execution_metrics",
    "metrics_warning",
    "recovery_factor",
    "risk_of_ruin",
    "system_quality_number",
]
