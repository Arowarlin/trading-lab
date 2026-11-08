"""Métricas informativas de operaciones. No cambian criterios de propuesta.

SQN, Recovery Factor y riesgo de ruina se calculan solo si hay muestra
suficiente; con N < 30 se marcan como informativos.
"""

from __future__ import annotations

import math

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


__all__ = [
    "MIN_SAMPLE",
    "RISK_OF_RUIN_ASSUMPTIONS",
    "RISK_PER_TRADE",
    "metrics_warning",
    "recovery_factor",
    "risk_of_ruin",
    "system_quality_number",
]
