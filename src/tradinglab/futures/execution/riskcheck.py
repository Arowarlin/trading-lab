"""``RiskCheck`` R01-R16 (execution_spec.md §4) — FUT-J1. Falla cerrado: lo que no se sabe, no sale."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ...prop_economics.account import lock_level
from ...prop_economics.rules import BLOCKING, Program, is_expired, max_contracts_for
from .intent import ROOTS, OrderIntent, commission_per_side, contract_spec


@dataclass(frozen=True)
class AccountView:
    """Estado de la cuenta que ve el control (del snapshot de la plataforma o del paper)."""

    account_id: str
    equity: float
    peak_eod: float
    peak_intraday: float | None = None
    payout_requested: bool = False
    profit_eod: float = 0.0
    day_pnl: float = 0.0
    open_risk_usd: float = 0.0
    open_micro_eq: float = 0.0


@dataclass(frozen=True)
class CheckContext:
    now: datetime
    firm_category: str                               # automation.category del catálogo de firmas
    policy_risk_usd: float                           # riesgo autorizado por el perfil ORPAE vigente
    last_trade: tuple[float, float] | None = None    # (riesgo, pnl) de la operación anterior de la estrategia/cuenta
    open_keys: frozenset[tuple[str, str, str]] = frozenset()   # (estrategia, cuenta, raíz) con intent o posición
    underlying_micro_eq: dict[str, float] = field(default_factory=dict)   # exposición global por subyacente
    news_events: list[datetime] | None = None        # None = sin calendario
    endpoint_is_live: bool = False


@dataclass
class RiskResult:
    ok: bool
    reasons: list[str]
    warnings: list[str]
    metrics: dict


def _phase(program: Program, phase: str):
    return program.phases.evaluation if phase == "evaluation" else program.phases.funded


def mll_threshold(program: Program, phase: str, acc: AccountView) -> float:
    """Umbral L de 04 §3.1 para el estado del snapshot (K absoluto)."""
    ph = _phase(program, phase)
    ml = ph.max_loss
    s = float(ph.start_balance.value)
    k = lock_level(ml, s)
    base = s - ml.amount
    if ml.mode == "static":
        level = base
    elif ml.mode == "trailing_eod":
        level = max(base, min(acc.peak_eod - ml.amount, k))
    else:
        peak = acc.peak_intraday if acc.peak_intraday is not None else max(acc.peak_eod, acc.equity)
        level = max(base, min(peak - ml.amount, k))
    if acc.payout_requested and ml.lock_after_first_payout and not math.isinf(k):
        level = max(level, k)
    return level


def _clock(value: str) -> tuple[time, ZoneInfo]:
    hhmm, tz = value.split()
    hh, mm = hhmm.split(":")
    return time(int(hh), int(mm)), ZoneInfo(tz)


def _aligned(price: float, tick: float) -> bool:
    return abs(price / tick - round(price / tick)) < 1e-6


def check(intent: OrderIntent, program: Program, acc: AccountView, ctx: CheckContext, cfg: dict) -> RiskResult:
    reasons: list[str] = []
    warnings: list[str] = []
    metrics: dict = {}
    buffer = float(cfg.get("buffer", 0.10))
    ph = _phase(program, intent.phase)
    today: date = ctx.now.date()

    # R01 · R02
    if is_expired(program, today):
        reasons.append("rules_expired")
    if ph is None:
        reasons.append(f"rules_unknown:phases.{intent.phase}")
        return RiskResult(False, reasons, warnings, metrics)
    if ph.max_loss.status in BLOCKING:
        reasons.append("rules_unknown:max_loss")
    flat_rule = getattr(ph, "flat_by", None) or program.phases.evaluation.flat_by
    if flat_rule is None or flat_rule.status in BLOCKING:
        reasons.append("rules_unknown:flat_by")
    contracts_rule = ph.max_contracts
    if (contracts_rule is not None and contracts_rule.status in BLOCKING) or \
            max_contracts_for(program, intent.phase, acc.profit_eod) is None:
        reasons.append("rules_unknown:max_contracts")
    dll = ph.daily_loss if ph.daily_loss is not None and ph.daily_loss.enabled else None
    if dll is not None and (dll.status in BLOCKING or dll.amount is None):
        reasons.append("rules_unknown:daily_loss")
        dll = None
    # R03 · R04
    if intent.origin == "automated":
        if ctx.firm_category in {"prohibited", "unverified"}:
            reasons.append("automation_prohibited")
        elif ctx.firm_category == "conditional" and intent.firm_id not in (cfg.get("firm_conditions_ack") or []):
            reasons.append("automation_conditions_not_acked")
    elif intent.adapter != "ticket" and intent.adapter != "paper":
        reasons.append("semi_manual_requires_ticket")
    if intent.adapter != "paper" and intent.adapter not in (cfg.get("platform_support") or {}).get(intent.firm_id, []):
        reasons.append("platform_unsupported")
    # R13 (unidad, tick, lado)
    if intent.root not in ROOTS or intent.qty < 1 or int(intent.qty) != intent.qty:
        reasons.append("unit_mismatch")
        return RiskResult(False, reasons, warnings, metrics)
    spec = contract_spec(intent.root)
    prices = [intent.entry_price, intent.stop_price] + ([intent.target_price] if intent.target_price is not None else [])
    if not all(_aligned(p, spec.tick_size) for p in prices):
        reasons.append("tick_misaligned")
    long = intent.side == "buy"
    if (long and intent.stop_price >= intent.entry_price) or (not long and intent.stop_price <= intent.entry_price):
        reasons.append("stop_side")
    if intent.target_price is not None and ((long and intent.target_price <= intent.entry_price)
                                            or (not long and intent.target_price >= intent.entry_price)):
        reasons.append("target_side")
    # R15 costes
    commission, _ = commission_per_side(program, intent.root, intent.adapter, cfg)
    if commission is None or math.isnan(intent.risk_usd):
        reasons.append("cost_unknown")
    # R05 contratos (en micro-equivalentes; el programa cuenta en su unidad)
    cap = max_contracts_for(program, intent.phase, acc.profit_eod)
    if cap is not None:
        cap_micro = cap if program.instrument_unit == "micro" else cap * 10
        metrics["max_micro_eq"] = cap_micro
        if acc.open_micro_eq + intent.micro_eq > cap_micro + 1e-9:
            reasons.append("max_contracts")
    # R06 MLL · R07 DLL
    if not math.isnan(intent.risk_usd):
        level = mll_threshold(program, intent.phase, acc)
        room = (acc.equity - level) * (1 - buffer)
        metrics.update(mll_level=level, mll_room=room)
        if acc.open_risk_usd + intent.risk_usd > room + 1e-9:
            reasons.append("mll_room")
        if dll is not None:
            day_loss = max(0.0, -acc.day_pnl)
            if day_loss + acc.open_risk_usd + intent.risk_usd > dll.amount * (1 - buffer) + 1e-9:
                reasons.append("dll_room")
    # R08 hora · R10 overnight
    flat = getattr(ph, "flat_by", None) or program.phases.evaluation.flat_by
    if flat is not None and flat.value is not None:
        flat_t, tz = _clock(str(flat.value))
        local = ctx.now.astimezone(tz)
        flat_dt = datetime.combine(local.date(), flat_t, tz)
        last_entry = flat_dt - timedelta(minutes=int(cfg.get("entry_margin_minutes", 5)))
        firm_last = ((cfg.get("last_entry_by") or {}).get(intent.program_id) or {}).get("value")
        if firm_last:
            ft, ftz = _clock(firm_last)
            last_entry = min(last_entry, datetime.combine(local.date(), ft, ftz))
        metrics["last_entry"] = last_entry.isoformat()
        if ctx.now >= last_entry:
            reasons.append("time_window")
        if intent.exit_by > flat_dt:
            reasons.append("overnight")
    # R09 noticias
    news = program.compliance.get("news_t1") or program.compliance.get("news")
    if news is not None and news.window_minutes and (not news.phases or intent.phase in news.phases):
        if ctx.news_events is None:
            reasons.append("sin_datos_calendario")
        else:
            w = timedelta(minutes=news.window_minutes)
            if any(ev - w <= ctx.now <= ev + w or ctx.now <= ev - w < intent.exit_by for ev in ctx.news_events):
                reasons.append("news_window")
    # R11 · R11b
    if not math.isnan(intent.risk_usd):
        if intent.risk_usd > ctx.policy_risk_usd + 1e-9:
            reasons.append("risk_above_policy")
        if ctx.last_trade is not None and ctx.last_trade[1] < 0 and intent.risk_usd > ctx.last_trade[0] + 1e-9:
            reasons.append("risk_increase_after_loss")
    # R12 exposición
    if (intent.strategy_id, intent.account_id, intent.root) in ctx.open_keys:
        reasons.append("duplicate_exposure")
    limit = ((cfg.get("global_underlying_limit_micro") or {}).get(spec.underlying) or {}).get("value")
    if limit is not None and ctx.underlying_micro_eq.get(spec.underlying, 0.0) + intent.micro_eq > float(limit) + 1e-9:
        reasons.append("global_underlying_limit")
    # R14 consistencia (aviso)
    cons = program.phases.evaluation.consistency if intent.phase == "evaluation" else None
    if cons is not None and intent.target_price is not None:
        gain = abs(intent.target_price - intent.entry_price) * spec.point_value * intent.qty
        required = float(program.phases.evaluation.profit_target.value)
        if acc.day_pnl + gain > cons.max_best_day_fraction * required:
            warnings.append("consistency_risk")
    # R16 live
    if ctx.endpoint_is_live:
        reasons.append("live_blocked")
    return RiskResult(not reasons, reasons, warnings, metrics)
