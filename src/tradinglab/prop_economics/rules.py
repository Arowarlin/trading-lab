"""Esquema de programas de prop firms (04_SPEC_PROP_EV.md §8) — FUT-A1.

Cada valor numérico lleva ``status``. ``blocking_unknowns`` lista lo que sigue en ``sin_datos`` o
``discrepancia``; ``is_expired`` aplica la caducidad de las reglas (ADR-F09).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Status = Literal["verified", "verified_repo", "discrepancia", "sin_datos", "assumed"]
BLOCKING = frozenset({"sin_datos", "discrepancia"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Model):
    url: str
    consulted_at: date


class Value(_Model):
    value: float | int | str | None = None
    alt: float | None = None
    status: Status
    note: str | None = None


class MaxLoss(_Model):
    mode: Literal["static", "trailing_eod", "trailing_intraday"]
    amount: float = Field(gt=0)
    check: Literal["realtime_unrealized", "eod_only"] = "realtime_unrealized"
    lock_at: float | Literal["start_balance"] | None = None
    lock_after_first_payout: bool = False
    status: Status
    note: str | None = None


class DailyLoss(_Model):
    amount: float | None = Field(default=None, gt=0)   # None solo si la regla no está activa o es sin_datos
    action: Literal["pause_day", "breach"]
    enabled: bool = True
    optional: bool = False
    base: Literal["day_start_balance", "higher_of_balance_or_equity"] = "day_start_balance"
    status: Status
    note: str | None = None


class Consistency(_Model):
    max_best_day_fraction: float = Field(gt=0, le=1)
    basis: Literal["total_profit"] = "total_profit"
    on_violation: Literal["raise_target", "fail"] = "raise_target"
    status: Status
    note: str | None = None


class MaxContracts(_Model):
    mini: int | None = None
    micro: int | None = None
    status: Status
    note: str | None = None


class Eligibility(_Model):
    template: Literal["winning_days", "trading_days_consistency", "min_balance_and_days"]
    n: int = Field(ge=0)
    min_day_profit: float | None = None
    c: float | None = None
    min_balance: float | None = None
    net_positive_cycle: bool = False
    status: Status
    note: str | None = None


class MaxPayouts(_Model):
    value: int = Field(gt=0)
    then: Literal["to_live"] = "to_live"
    status: Status
    note: str | None = None


class ToLive(_Model):
    trigger: Literal["daily_net_profit_ge"]
    value: float = Field(gt=0)
    status: Status
    note: str | None = None


class Tier(_Model):
    min_profit: float
    mini: int | None = None
    micro: int | None = None


class ScalingPlan(_Model):
    status: Status
    basis: Literal["profit_eod"] = "profit_eod"
    tiers: list[Tier]
    note: str | None = None


class ComplianceRule(_Model):
    allowed: bool | None = None
    window_minutes: int | None = None
    phases: list[str] | None = None
    action: Literal["breach", "skip_day"] | None = None
    category: str | None = None
    source_doc: str | None = None
    status: Status
    note: str | None = None


class Payout(_Model):
    eligibility: Eligibility
    max_fraction_of_balance: Value
    cap_per_payout: Value
    min_amount: Value
    split: Value
    processing_days: Value
    buffer_min: Value | None = None
    fraction_basis: Literal["profit", "balance"] = "profit"
    max_payouts: MaxPayouts | None = None
    to_live: ToLive | None = None


class EvaluationPhase(_Model):
    start_balance: Value
    profit_target: Value
    max_loss: MaxLoss
    daily_loss: DailyLoss | None = None
    consistency: Consistency | None = None
    min_trading_days: Value | None = None
    max_contracts: MaxContracts | None = None
    flat_by: Value | None = None
    max_calendar_days: Value | None = None


class FundedPhase(_Model):
    start_balance: Value
    max_loss: MaxLoss
    daily_loss: DailyLoss | None = None
    max_contracts: MaxContracts | None = None
    consistency: Value | None = None                   # solo documenta "ninguna" en la financiada
    scaling_plan: ScalingPlan | Value | None = None
    max_accounts: Value | None = None
    inactivity_close_days: Value | None = None
    payout: Payout


class Phases(_Model):
    evaluation: EvaluationPhase
    funded: FundedPhase | None = None


class Fee(_Model):
    amount: float | None = Field(default=None, ge=0)
    status: Status
    note: str | None = None


class EvaluationFee(_Model):
    type: Literal["subscription", "one_time"]
    amount: float | None = Field(default=None, ge=0)
    alt: float | None = Field(default=None, ge=0)      # precio alternativo (p. ej. promoción)
    period_days: int | None = Field(default=None, gt=0)
    status: Status
    note: str | None = None


class Fees(_Model):
    evaluation: EvaluationFee
    activation: Fee | None = None
    reset: Fee | None = None
    data_platform_monthly: Fee | None = None
    consistency_addon: Fee | None = None


class Program(_Model):
    schema_version: Literal[1]
    program_id: str
    firm_id: str
    rules_version: str
    consulted_at: date
    expires_after_days: int = Field(gt=0)
    instrument_unit: Literal["micro", "mini"]
    phases: Phases
    fees: Fees
    commissions_per_side: dict[str, Value] = Field(default_factory=dict)
    compliance: dict[str, ComplianceRule] = Field(default_factory=dict)
    sources: list[Source] = Field(default_factory=list)


def max_contracts_for(program: Program, phase: str, profit: float) -> int | None:
    """Contratos máximos (en la unidad del programa) para la fase y el beneficio EOD; None si no hay límite."""
    ph = program.phases.evaluation if phase == "evaluation" else program.phases.funded
    unit = program.instrument_unit
    caps: list[int] = []
    if ph is not None and ph.max_contracts is not None:
        v = getattr(ph.max_contracts, unit)
        if v is not None:
            caps.append(int(v))
    if phase == "funded" and ph is not None and isinstance(ph.scaling_plan, ScalingPlan):
        tiers = sorted(ph.scaling_plan.tiers, key=lambda x: x.min_profit)
        cap = getattr(tiers[0], unit)
        for tier in tiers:
            if profit >= tier.min_profit and getattr(tier, unit) is not None:
                cap = getattr(tier, unit)
        if cap is not None:
            caps.append(int(cap))
    return min(caps) if caps else None


def load_program(path: str | Path) -> Program:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Program.model_validate(data)


def is_expired(program: Program, today: date) -> bool:
    """Caducado si ``today >= consulted_at + expires_after_days`` días."""
    return today >= program.consulted_at + timedelta(days=program.expires_after_days)


def _walk(obj: object, prefix: str, out: list[str]) -> None:
    if isinstance(obj, BaseModel):
        if getattr(obj, "enabled", True) is False:
            return
        status = getattr(obj, "status", None)
        if status in BLOCKING:
            out.append(prefix)
        for name in type(obj).model_fields:
            _walk(getattr(obj, name), f"{prefix}.{name}" if prefix else name, out)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _walk(value, f"{prefix}.{key}" if prefix else str(key), out)


def blocking_unknowns(program: Program) -> list[str]:
    """Claves con puntos de todo valor ``sin_datos`` o ``discrepancia`` (reglas desactivadas excluidas)."""
    out: list[str] = []
    _walk(program, "", out)
    return sorted(out)
