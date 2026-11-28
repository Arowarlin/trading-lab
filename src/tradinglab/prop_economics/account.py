"""Motor escalar de una cuenta: evaluación (FUT-A3) y fase financiada con payouts (FUT-A4).

Fuente de verdad: docs/futures/04_SPEC_PROP_EV.md §3-4. Convención de rotura: E <= L (igualdad incluida).
El bloqueo K (``lock_at``) es un nivel ABSOLUTO (§1): ``start_balance`` -> S; número -> ese número;
``None`` -> sin bloqueo (+inf). El umbral nunca baja. Este motor escalar es la referencia con la que se
compara el motor vectorizado (FUT-A6a).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .paths import DayPath
from .rules import DailyLoss, MaxLoss, Program


class MissingRuleError(ValueError):
    """Una regla necesaria está en ``sin_datos`` y no se ha dado una suposición explícita."""


def lock_level(max_loss: MaxLoss, start_balance: float) -> float:
    if max_loss.lock_at == "start_balance":
        return float(start_balance)
    if max_loss.lock_at is None:
        return math.inf
    return float(max_loss.lock_at)


def _run_marks(balance: float, peak_intraday: float, threshold: float, max_loss: MaxLoss,
               dll: DailyLoss | None, day: DayPath, contracts: int, lock: float
               ) -> tuple[float, bool, float, float]:
    """Recorre las marcas del día. Devuelve (equity de cierre, rotura, pico intradía, umbral)."""
    b = float(balance)
    peak = max(peak_intraday, b)
    thr = threshold
    realtime = max_loss.mode != "trailing_eod" or max_loss.check == "realtime_unrealized"
    dll_on = dll is not None and dll.enabled
    if dll_on and dll.base != "day_start_balance":
        raise NotImplementedError("DLL con base distinta de day_start_balance")
    close = b + contracts * float(day.marks[-1])
    for m in day.marks[1:]:
        e = b + contracts * float(m)
        if max_loss.mode == "trailing_intraday":
            peak = max(peak, e)
            thr = max(thr, min(peak - max_loss.amount, lock))
        if realtime and e <= thr:
            return e, True, peak, thr
        if dll_on and (e - b) <= -dll.amount:
            if dll.action == "breach":
                return e, True, peak, thr
            close = e
            break
    if not realtime and close <= thr:
        return close, True, peak, thr
    return close, False, peak, thr


def _eod_threshold(max_loss: MaxLoss, peak_eod: float, threshold: float, close: float, lock: float
                   ) -> tuple[float, float]:
    if max_loss.mode != "trailing_eod":
        return peak_eod, threshold
    peak_eod = max(peak_eod, close)
    return peak_eod, max(threshold, min(peak_eod - max_loss.amount, lock))


# ---------------------------------------------------------------- evaluación (FUT-A3)

@dataclass(frozen=True)
class AccountState:
    start_balance: float
    balance: float
    peak_eod: float
    peak_intraday: float
    threshold: float
    best_day: float
    trading_days: int
    days: int
    status: str  # "active" | "passed" | "failed_mll" | "failed_timeout"


def new_evaluation(program: Program) -> AccountState:
    ev = program.phases.evaluation
    s = float(ev.start_balance.value)
    return AccountState(s, s, s, s, s - ev.max_loss.amount, 0.0, 0, 0, "active")


def step_day(state: AccountState, program: Program, day: DayPath, contracts: int) -> AccountState:
    """Un día de sesión de la evaluación. Devuelve un estado NUEVO; un estado terminal no cambia."""
    if state.status != "active":
        return state
    ev = program.phases.evaluation
    ml = ev.max_loss
    lock = lock_level(ml, state.start_balance)
    close, breached, peak_i, thr = _run_marks(state.balance, state.peak_intraday, state.threshold, ml,
                                              ev.daily_loss, day, contracts, lock)
    pnl = close - state.balance
    days = state.days + 1
    trading_days = state.trading_days + (1 if day.n_trades > 0 else 0)
    best = max(state.best_day, pnl)
    if breached:
        return replace(state, balance=close, peak_intraday=peak_i, threshold=thr, best_day=best,
                       trading_days=trading_days, days=days, status="failed_mll")
    peak_eod, thr = _eod_threshold(ml, state.peak_eod, thr, close, lock)
    required = float(ev.profit_target.value)
    if ev.consistency is not None:
        if ev.consistency.on_violation != "raise_target":
            raise NotImplementedError("consistency.on_violation distinto de raise_target")
        required = max(required, best / ev.consistency.max_best_day_fraction)
    min_days = int(ev.min_trading_days.value) if ev.min_trading_days and ev.min_trading_days.value else 0
    status = "active"
    if close - state.start_balance >= required and trading_days >= min_days:
        status = "passed"
    elif ev.max_calendar_days is not None and ev.max_calendar_days.value is not None \
            and days >= int(ev.max_calendar_days.value):
        status = "failed_timeout"
    return AccountState(state.start_balance, close, peak_eod, peak_i, thr, best, trading_days, days, status)


# ---------------------------------------------------------------- financiada y payouts (FUT-A4)

@dataclass(frozen=True)
class PayoutRules:
    template: str
    n: int
    min_day_profit: float = 0.0
    c: float | None = None
    min_balance: float = 0.0
    fraction: float = 1.0
    cap: float = math.inf
    buffer_min: float = 0.0
    min_amount: float = 0.0
    split: float = 1.0
    processing_days: int = 0
    lock_after_first_payout: bool = False
    lock_value: float | None = None


def _required_number(value, key: str) -> float:
    if value is None or value.status == "sin_datos" or value.value is None:
        raise MissingRuleError(key)
    return float(value.value)


def payout_rules_from_program(program: Program, *, assume_processing_days: int | None = None) -> PayoutRules:
    funded = program.phases.funded
    if funded is None:
        raise MissingRuleError("phases.funded")
    p = funded.payout
    el = p.eligibility
    if p.processing_days.status == "sin_datos" or p.processing_days.value is None:
        if assume_processing_days is None:
            raise MissingRuleError("processing_days")
        processing = int(assume_processing_days)
    else:
        processing = int(p.processing_days.value)
    ml = funded.max_loss
    start = float(funded.start_balance.value)
    return PayoutRules(
        template=el.template, n=el.n, min_day_profit=float(el.min_day_profit or 0.0), c=el.c,
        min_balance=float(el.min_balance or 0.0),
        fraction=_required_number(p.max_fraction_of_balance, "max_fraction_of_balance"),
        cap=_required_number(p.cap_per_payout, "cap_per_payout"),
        min_amount=_required_number(p.min_amount, "min_amount"),
        split=_required_number(p.split, "split"),
        processing_days=processing,
        lock_after_first_payout=ml.lock_after_first_payout,
        lock_value=None if ml.lock_at is None else lock_level(ml, start),
    )


@dataclass(frozen=True)
class FundedState:
    start_balance: float
    balance: float
    peak_eod: float
    peak_intraday: float
    threshold: float
    days: int
    status: str  # "active" | "failed_mll"
    win_days_since: int
    profit_since: float
    best_since: float
    days_since: int
    n_payouts: int


@dataclass(frozen=True)
class PayoutEvent:
    day_requested: int
    day_received: int
    gross: float
    received: float


def new_funded(program: Program) -> FundedState:
    funded = program.phases.funded
    if funded is None:
        raise MissingRuleError("phases.funded")
    s = float(funded.start_balance.value)
    return FundedState(s, s, s, s, s - funded.max_loss.amount, 0, "active", 0, 0.0, 0.0, 0, 0)


def _eligible(state: FundedState, rules: PayoutRules) -> bool:
    profit = state.balance - state.start_balance
    if rules.template == "winning_days":
        return state.win_days_since >= rules.n
    if rules.template == "trading_days_consistency":
        if rules.c is None:
            raise MissingRuleError("eligibility.c")
        return (state.days_since >= rules.n and state.profit_since > 0
                and state.best_since <= rules.c * state.profit_since)
    if rules.template == "min_balance_and_days":
        return profit >= rules.min_balance and state.days_since >= rules.n
    raise ValueError(f"plantilla desconocida: {rules.template}")


def step_funded_day(state: FundedState, program: Program, rules: PayoutRules, day: DayPath, contracts: int,
                    day_index: int, *, policy: str = "max_asap", policy_arg: float | None = None,
                    payout_fee: float = 0.0) -> tuple[FundedState, PayoutEvent | None]:
    """Un día de la fase financiada; al cierre, pide el payout si es elegible (política del trader)."""
    if state.status != "active":
        return state, None
    funded = program.phases.funded
    ml = funded.max_loss
    lock = lock_level(ml, state.start_balance)
    close, breached, peak_i, thr = _run_marks(state.balance, state.peak_intraday, state.threshold, ml,
                                              funded.daily_loss, day, contracts, lock)
    pnl = close - state.balance
    if breached:
        return replace(state, balance=close, peak_intraday=peak_i, threshold=thr, days=state.days + 1,
                       status="failed_mll"), None
    peak_eod, thr = _eod_threshold(ml, state.peak_eod, thr, close, lock)
    st = replace(state, balance=close, peak_eod=peak_eod, peak_intraday=peak_i, threshold=thr,
                 days=state.days + 1, days_since=state.days_since + 1,
                 profit_since=state.profit_since + pnl, best_since=max(state.best_since, pnl),
                 win_days_since=state.win_days_since + (1 if pnl >= rules.min_day_profit else 0))
    if not _eligible(st, rules):
        return st, None
    profit = st.balance - st.start_balance
    available = min(rules.fraction * profit, rules.cap, profit - rules.buffer_min)
    locked = rules.lock_after_first_payout and rules.lock_value is not None
    thr_after = max(st.threshold, rules.lock_value) if locked else st.threshold
    if policy == "max_asap":
        w = available
    elif policy == "fixed":
        w = min(float(policy_arg), available)
    elif policy == "keep_cushion":
        w = min(available, st.balance - thr_after - float(policy_arg))
    else:
        raise ValueError(f"política desconocida: {policy}")
    if w <= 0 or w < rules.min_amount:
        return st, None
    st = replace(st, balance=st.balance - w, threshold=thr_after, n_payouts=st.n_payouts + 1,
                 win_days_since=0, profit_since=0.0, best_since=0.0, days_since=0)
    event = PayoutEvent(day_index, day_index + rules.processing_days, w, rules.split * w - payout_fee)
    return st, event
