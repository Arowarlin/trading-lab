"""Tarifas, coste por intento y coste por cuenta financiada (04 §5) — FUT-A5."""

from __future__ import annotations

import math

from .account import MissingRuleError
from .rules import Program


def subscription_charges(end_day: int, period_days: int) -> int:
    """Cargos en los días 0, P, 2P… estrictamente anteriores a ``end_day``: ceil(end_day / P)."""
    if end_day < 1:
        raise ValueError("end_day debe ser >= 1")
    if period_days < 1:
        raise ValueError("period_days debe ser >= 1")
    return math.ceil(end_day / period_days)


def evaluation_cost(program: Program, end_day: int) -> float:
    """Coste de un intento de evaluación que termina el día natural ``end_day``."""
    fee = program.fees.evaluation
    if fee.amount is None or fee.status == "sin_datos":
        raise MissingRuleError("fees.evaluation")
    if fee.type == "subscription":
        if fee.period_days is None:
            raise MissingRuleError("fees.evaluation.period_days")
        return fee.amount * subscription_charges(end_day, fee.period_days)
    return float(fee.amount)


def ev_per_attempt(p_pass: float, attempt_cost: float, activation: float, net_payout_per_funded: float) -> float:
    """EV de un intento independiente: −coste + P(pasar)·(payout neto por financiada − activación)."""
    return -attempt_cost + p_pass * (net_payout_per_funded - activation)


def cost_per_funded(p_pass: float, attempt_cost: float, activation: float) -> float:
    """Coste esperado de conseguir una cuenta financiada: coste / P(pasar) + activación."""
    if p_pass <= 0:
        raise ValueError("p_pass debe ser > 0")
    return attempt_cost / p_pass + activation
