"""Monte Carlo del motor EV, parte B: un proyecto completo por camino (04 §4-§7.3) — FUT-A6b.

Proyecto = presupuesto de tarifas + una cuenta a la vez: evaluación → activación → financiada → payouts
(cobrados ``processing_days`` sesiones después) → al perder la cuenta, nueva evaluación si hay caja
(presupuesto + cobrado − tarifas). Sin caja → ``ruined``.

Dos implementaciones con la MISMA semántica:
* ``simulate_project_path``: referencia escalar, construida sobre ``account.step_day``/``step_funded_day``.
* ``simulate_project``: vectorizada sobre caminos (numpy). Un test las compara camino a camino.

Convenciones (documentadas en el informe):
* Días de sesión CME desde ``start_date`` (``cme_holidays``); los horizontes son días naturales.
* Suscripción de evaluación: cargo al comprar y cada ``period_days`` naturales mientras siga activa,
  cobrado antes de operar la sesión (04 §5). Las renovaciones se cobran aunque falte caja.
* Una evaluación comprada el día t empieza a operar en t+1. Una cuenta que aprueba el día t opera como
  financiada desde t+1.
* Fuera de v1: varias cuentas a la vez, reset en lugar de compra, transición a Live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from ..discovery.calendars import cme_holidays
from .account import (
    MissingRuleError,
    lock_level,
    new_evaluation,
    new_funded,
    payout_rules_from_program,
    step_day,
    step_funded_day,
)
from .paths import DayPath
from .rules import DailyLoss, MaxLoss, Program, ScalingPlan, max_contracts_for
from .simulate import mean_block_length, stationary_bootstrap_indices

EVAL, FUNDED, RUINED = 0, 1, 2


@dataclass(frozen=True)
class ProjectConfig:
    contracts_eval: int
    contracts_funded: int
    budget: float
    start_date: date
    horizons_days: tuple[int, ...] = (30, 90, 180, 365)
    policy: str = "max_asap"
    policy_arg: float | None = None
    payout_fee: float = 0.0
    assume_processing_days: int | None = None
    assume: tuple[tuple[str, float], ...] = ()   # supuestos explícitos para valores sin_datos (p. ej. cap_per_payout)
    sizing: object | None = None                 # policies.SizingPolicy: contratos según el colchón (FUT-O3)


def session_offsets(start: date, max_days: int) -> np.ndarray:
    """Desfase en días naturales de cada sesión CME (lunes-viernes sin festivos) en [start, start+max_days)."""
    hol = cme_holidays(start.year, start.year + max_days // 365 + 2)
    out = []
    d = start
    while (d - start).days < max_days:
        if d.weekday() < 5 and int(d.strftime("%Y%m%d")) not in hol:
            out.append((d - start).days)
        d += timedelta(days=1)
    return np.asarray(out, dtype=np.int64)


def _fees(program: Program, assume: dict[str, float]) -> tuple[float, str, int | None, float]:
    """Tarifa de evaluación, tipo, periodo y activación. Un valor sin_datos exige un supuesto explícito."""
    fee = program.fees.evaluation
    if fee.amount is None or fee.status == "sin_datos":
        if "fees.evaluation" not in assume:
            raise MissingRuleError("fees.evaluation")
        amount = float(assume["fees.evaluation"])
    else:
        amount = float(fee.amount)
    act = program.fees.activation
    if act is None:
        activation = 0.0
    elif act.amount is None or act.status == "sin_datos":
        if "fees.activation" not in assume:
            raise MissingRuleError("fees.activation")
        activation = float(assume["fees.activation"])
    else:
        activation = float(act.amount)
    if fee.type == "subscription" and fee.period_days is None:
        raise MissingRuleError("fees.evaluation.period_days")
    return amount, fee.type, fee.period_days, activation


# ------------------------------------------------------------------ referencia escalar

def simulate_project_path(program: Program, pool: list[DayPath], idx_row: np.ndarray, cfg: ProjectConfig,
                          offsets: np.ndarray) -> dict:
    rules = payout_rules_from_program(program, assume_processing_days=cfg.assume_processing_days,
                                      assume=dict(cfg.assume))
    fee, fee_type, period, activation = _fees(program, dict(cfg.assume))
    n = len(offsets)
    fees_at = np.zeros(n)
    recv_at = np.zeros(n)
    recv_n_at = np.zeros(n, dtype=np.int64)
    out = {"bought": 1, "passed": 0, "evals_lost": 0, "funded_lost": 0, "requested": 0, "ruin_t": -1, "to_live": 0}
    phase = EVAL
    st = new_evaluation(program)
    fst = None
    eval_start = int(offsets[0])
    charges = 1
    fees_at[0] += fee

    def cash(t: int) -> float:
        return cfg.budget + recv_at[: t + 1].sum() - fees_at[: t + 1].sum()

    def rebuy(t: int) -> None:
        nonlocal phase, st, eval_start, charges
        if cash(t) >= fee:
            fees_at[t] += fee
            out["bought"] += 1
            st = new_evaluation(program)
            phase = EVAL
            eval_start = int(offsets[t + 1]) if t + 1 < n else 10**9
            charges = 1
        else:
            phase = RUINED
            out["ruin_t"] = t

    for t in range(n):
        if phase == RUINED:
            break
        day = pool[int(idx_row[t])]
        if phase == EVAL:
            if fee_type == "subscription":
                while offsets[t] - eval_start >= charges * period:
                    fees_at[t] += fee
                    charges += 1
            cap = max_contracts_for(program, "evaluation", st.balance - st.start_balance)
            ce = cfg.contracts_eval if cfg.sizing is None else cfg.sizing.contracts(st.balance - st.threshold)
            ce = ce if cap is None else min(ce, cap)
            st = step_day(st, program, day, ce)
            if st.status == "passed":
                out["passed"] += 1
                if cash(t) >= activation:
                    fees_at[t] += activation
                    phase = FUNDED
                    fst = new_funded(program)
                else:
                    phase = RUINED
                    out["ruin_t"] = t
            elif st.status != "active":
                out["evals_lost"] += 1
                rebuy(t)
        else:
            cap = max_contracts_for(program, "funded", fst.balance - fst.start_balance)
            cf = cfg.contracts_funded if cfg.sizing is None else cfg.sizing.contracts(fst.balance - fst.threshold)
            cf = cf if cap is None else min(cf, cap)
            fst, ev = step_funded_day(fst, program, rules, day, cf, t, policy=cfg.policy,
                                      policy_arg=cfg.policy_arg, payout_fee=cfg.payout_fee)
            if ev is not None:
                out["requested"] += 1
                if ev.day_received < n:
                    recv_at[ev.day_received] += ev.received
                    recv_n_at[ev.day_received] += 1
            if fst.status == "to_live":
                out["to_live"] += 1
                rebuy(t)
            elif fst.status != "active":
                out["funded_lost"] += 1
                rebuy(t)
    out.update(fees_at=fees_at, recv_at=recv_at, recv_n_at=recv_n_at, phase=phase)
    return out


# ------------------------------------------------------------------ vectorizada

def _vec_marks(m: np.ndarray, b: np.ndarray, peak_i: np.ndarray, thr: np.ndarray, mask: np.ndarray,
               ml: MaxLoss, dll: DailyLoss | None, lock: float):
    """Mismas reglas que ``account._run_marks`` para las filas de ``mask``."""
    peak = np.maximum(peak_i, b)
    th = thr.copy()
    close = b + m[:, -1]
    ended = ~mask
    breach = np.zeros(b.shape[0], dtype=bool)
    realtime = ml.mode != "trailing_eod" or ml.check == "realtime_unrealized"
    for j in range(1, m.shape[1]):
        e = b + m[:, j]
        live = ~ended
        if ml.mode == "trailing_intraday":
            peak = np.where(live, np.maximum(peak, e), peak)
            th = np.where(live, np.maximum(th, np.minimum(peak - ml.amount, lock)), th)
        if realtime:
            hit = live & (e <= th)
            breach |= hit
            close = np.where(hit, e, close)
            ended = ended | hit
            live = ~ended
        if dll is not None:
            d = live & ((e - b) <= -dll.amount)
            close = np.where(d, e, close)
            if dll.action == "breach":
                breach |= d
            ended = ended | d
    if not realtime:
        breach |= mask & ~breach & (close <= th)
    return close, breach, peak, th


def _funded_caps(program: Program, profit: np.ndarray) -> np.ndarray | None:
    """Tope de contratos de la financiada por camino (máximo estático y escalón de escalado)."""
    ph = program.phases.funded
    unit = program.instrument_unit
    cap = None
    if ph.max_contracts is not None and getattr(ph.max_contracts, unit) is not None:
        cap = np.full(profit.shape, int(getattr(ph.max_contracts, unit)))
    if isinstance(ph.scaling_plan, ScalingPlan):
        tiers = sorted(ph.scaling_plan.tiers, key=lambda x: x.min_profit)
        tier_cap = np.full(profit.shape, getattr(tiers[0], unit))
        for tier in tiers:
            if getattr(tier, unit) is not None:
                tier_cap = np.where(profit >= tier.min_profit, getattr(tier, unit), tier_cap)
        cap = tier_cap if cap is None else np.minimum(cap, tier_cap)
    return cap


def _dll(rule: DailyLoss | None) -> DailyLoss | None:
    if rule is None or not rule.enabled:
        return None
    if rule.amount is None:
        raise MissingRuleError("daily_loss.amount")
    if rule.base != "day_start_balance":
        raise NotImplementedError("DLL con base distinta de day_start_balance")
    return rule


def simulate_project(program: Program, pool: list[DayPath], cfg: ProjectConfig, *, n_paths: int, seed: int,
                     mean_block: float | None = None, idx: np.ndarray | None = None) -> dict:
    """Proyecto vectorizado. Devuelve métricas por horizonte (días naturales) y el detalle por camino."""
    if program.phases.funded is None:
        raise MissingRuleError("phases.funded")
    for d in pool:
        d.validate()
    rules = payout_rules_from_program(program, assume_processing_days=cfg.assume_processing_days,
                                      assume=dict(cfg.assume))
    fee, fee_type, period, activation = _fees(program, dict(cfg.assume))
    offsets = session_offsets(cfg.start_date, max(cfg.horizons_days))
    n_days = len(offsets)
    if idx is None:
        if mean_block is None:
            mean_block = mean_block_length(np.asarray([float(d.marks[-1]) for d in pool]))
        idx = stationary_bootstrap_indices(len(pool), n_days, n_paths, mean_block, seed)
    n_paths = idx.shape[0]
    idx = idx[:, :n_days]

    width = max(len(d.marks) for d in pool)
    marks_pool = np.empty((len(pool), width))
    for i, d in enumerate(pool):
        mk = np.asarray(d.marks, dtype=np.float64)
        marks_pool[i, : mk.size] = mk
        marks_pool[i, mk.size:] = mk[-1]
    ntr_pool = np.asarray([d.n_trades for d in pool])

    ev_ph, fu_ph = program.phases.evaluation, program.phases.funded
    e_ml, f_ml = ev_ph.max_loss, fu_ph.max_loss
    e_s, f_s = float(ev_ph.start_balance.value), float(fu_ph.start_balance.value)
    e_lock, f_lock = lock_level(e_ml, e_s), lock_level(f_ml, f_s)
    e_dll, f_dll = _dll(ev_ph.daily_loss), _dll(fu_ph.daily_loss)
    target = float(ev_ph.profit_target.value)
    c = None
    if ev_ph.consistency is not None:
        if ev_ph.consistency.on_violation != "raise_target":
            raise NotImplementedError("consistency.on_violation distinto de raise_target")
        c = ev_ph.consistency.max_best_day_fraction
    min_days = int(ev_ph.min_trading_days.value) if ev_ph.min_trading_days and ev_ph.min_trading_days.value else 0
    max_days = None
    if ev_ph.max_calendar_days is not None and ev_ph.max_calendar_days.value is not None:
        max_days = int(ev_ph.max_calendar_days.value)

    n = n_paths
    phase = np.full(n, EVAL, dtype=np.int8)
    # evaluación
    eb, epe, epi = np.full(n, e_s), np.full(n, e_s), np.full(n, e_s)
    eth = np.full(n, e_s - e_ml.amount)
    ebest = np.zeros(n)
    etd = np.zeros(n, dtype=np.int64)
    edays = np.zeros(n, dtype=np.int64)
    estart = np.full(n, int(offsets[0]), dtype=np.int64)
    echarges = np.ones(n, dtype=np.int64)
    # financiada
    fb, fpe, fpi = np.full(n, f_s), np.full(n, f_s), np.full(n, f_s)
    fth = np.full(n, f_s - f_ml.amount)
    win_since = np.zeros(n, dtype=np.int64)
    profit_since = np.zeros(n)
    best_since = np.zeros(n)
    days_since = np.zeros(n, dtype=np.int64)
    # dinero y contadores
    fees_sum = np.full(n, fee)
    recv_sum = np.zeros(n)
    recv_cnt = np.zeros(n, dtype=np.int64)
    sched_amt = np.zeros((n, n_days))
    sched_cnt = np.zeros((n, n_days), dtype=np.int64)
    bought = np.ones(n, dtype=np.int64)
    passed_n = np.zeros(n, dtype=np.int64)
    evals_lost = np.zeros(n, dtype=np.int64)
    funded_lost = np.zeros(n, dtype=np.int64)
    requested = np.zeros(n, dtype=np.int64)
    to_live_n = np.zeros(n, dtype=np.int64)
    pay_acc = np.zeros(n, dtype=np.int64)
    ruin_t = np.full(n, -1, dtype=np.int64)
    e_cap = max_contracts_for(program, "evaluation", 0.0)
    ce = cfg.contracts_eval if e_cap is None else min(cfg.contracts_eval, e_cap)
    max_out = fees_sum - recv_sum
    locked = rules.lock_after_first_payout and rules.lock_value is not None
    horizon_last = {h: int(np.searchsorted(offsets, h, side="left")) - 1 for h in cfg.horizons_days}
    snaps: dict[int, dict] = {}

    def rebuy(mask: np.ndarray, t: int) -> None:
        nonlocal phase, eb, epe, epi, eth, ebest, etd, edays, estart, echarges, fees_sum, bought, ruin_t
        can = mask & (cfg.budget + recv_sum - fees_sum >= fee)
        stop = mask & ~can
        fees_sum = fees_sum + np.where(can, fee, 0.0)
        bought = bought + can
        phase = np.where(can, EVAL, phase).astype(np.int8)
        phase = np.where(stop, RUINED, phase).astype(np.int8)
        ruin_t = np.where(stop, t, ruin_t)
        for arr, val in ((eb, e_s), (epe, e_s), (epi, e_s), (eth, e_s - e_ml.amount), (ebest, 0.0)):
            arr[can] = val
        etd[can] = 0
        edays[can] = 0
        estart[can] = int(offsets[t + 1]) if t + 1 < n_days else 10**9
        echarges[can] = 1

    for t in range(n_days):
        recv_sum = recv_sum + sched_amt[:, t]
        recv_cnt = recv_cnt + sched_cnt[:, t]
        is_e = phase == EVAL
        is_f = phase == FUNDED
        rows = idx[:, t]
        base = marks_pool[rows]
        # ---- evaluación
        if fee_type == "subscription":
            while True:
                due = is_e & (offsets[t] - estart >= echarges * period)
                if not due.any():
                    break
                fees_sum = fees_sum + np.where(due, fee, 0.0)
                echarges = echarges + due
        if is_e.any():
            if cfg.sizing is None:
                ce_t = np.full(n, ce)
            else:
                ce_t = cfg.sizing.contracts(eb - eth)
                ce_t = ce_t if e_cap is None else np.minimum(ce_t, e_cap)
            close, breach, peak, th = _vec_marks(base * ce_t[:, None], eb, epi, eth, is_e, e_ml, e_dll, e_lock)
            pnl = close - eb
            edays = edays + is_e
            etd = etd + (is_e & (ntr_pool[rows] > 0))
            ebest = np.where(is_e, np.maximum(ebest, pnl), ebest)
            eb = np.where(is_e, close, eb)
            epi = np.where(is_e, peak, epi)
            eth = np.where(is_e, th, eth)
            ok = is_e & ~breach
            if e_ml.mode == "trailing_eod":
                epe = np.where(ok, np.maximum(epe, eb), epe)
                eth = np.where(ok, np.maximum(eth, np.minimum(epe - e_ml.amount, e_lock)), eth)
            required = np.full(n, target) if c is None else np.maximum(target, ebest / c)
            passed = ok & (eb - e_s >= required) & (etd >= min_days)
            timeout = np.zeros(n, dtype=bool)
            if max_days is not None:
                timeout = ok & ~passed & (edays >= max_days)
            failed = (is_e & breach) | timeout
            passed_n = passed_n + passed
            evals_lost = evals_lost + failed
            pay_act = passed & (cfg.budget + recv_sum - fees_sum >= activation)
            fees_sum = fees_sum + np.where(pay_act, activation, 0.0)
            phase = np.where(pay_act, FUNDED, phase).astype(np.int8)
            no_act = passed & ~pay_act
            phase = np.where(no_act, RUINED, phase).astype(np.int8)
            ruin_t = np.where(no_act, t, ruin_t)
            for arr, val in ((fb, f_s), (fpe, f_s), (fpi, f_s), (fth, f_s - f_ml.amount), (profit_since, 0.0),
                             (best_since, 0.0)):
                arr[pay_act] = val
            win_since[pay_act] = 0
            days_since[pay_act] = 0
            pay_acc[pay_act] = 0
            if failed.any():
                rebuy(failed, t)
        # ---- financiada
        if is_f.any():
            caps = _funded_caps(program, fb - f_s)
            want = np.full(n, cfg.contracts_funded) if cfg.sizing is None else cfg.sizing.contracts(fb - fth)
            cf = want if caps is None else np.minimum(want, caps)
            close, breach, peak, th = _vec_marks(base * cf[:, None], fb, fpi, fth, is_f, f_ml, f_dll, f_lock)
            pnl = close - fb
            fb = np.where(is_f, close, fb)
            fpi = np.where(is_f, peak, fpi)
            fth = np.where(is_f, th, fth)
            ok = is_f & ~breach
            if f_ml.mode == "trailing_eod":
                fpe = np.where(ok, np.maximum(fpe, fb), fpe)
                fth = np.where(ok, np.maximum(fth, np.minimum(fpe - f_ml.amount, f_lock)), fth)
            days_since = days_since + ok
            profit_since = profit_since + np.where(ok, pnl, 0.0)
            best_since = np.where(ok, np.maximum(best_since, pnl), best_since)
            win_since = win_since + (ok & (pnl >= rules.min_day_profit))
            live_now = np.zeros(n, dtype=bool)
            if rules.to_live_daily_profit is not None:
                live_now = ok & (pnl >= rules.to_live_daily_profit)
            profit = fb - f_s
            if rules.template == "winning_days":
                elig = win_since >= rules.n
            elif rules.template == "trading_days_consistency":
                elig = (days_since >= rules.n) & (profit_since > 0) & (best_since <= rules.c * profit_since)
            else:
                elig = (profit >= rules.min_balance) & (days_since >= rules.n)
            if rules.net_positive_cycle:
                elig = elig & (profit_since > 0)
            available = np.minimum(np.minimum(rules.fraction * profit, rules.cap), profit - rules.buffer_min)
            thr_after = np.maximum(fth, rules.lock_value) if locked else fth
            if cfg.policy == "max_asap":
                w = available
            elif cfg.policy == "fixed":
                w = np.minimum(float(cfg.policy_arg), available)
            elif cfg.policy == "keep_cushion":
                w = np.minimum(available, fb - thr_after - float(cfg.policy_arg))
            else:
                raise ValueError(f"política desconocida: {cfg.policy}")
            pay = ok & ~live_now & elig & (w > 0) & (w >= rules.min_amount)
            if pay.any():
                received = rules.split * w - cfg.payout_fee
                fb = np.where(pay, fb - w, fb)
                fth = np.where(pay, thr_after, fth)
                requested = requested + pay
                pay_acc = pay_acc + pay
                for arr in (profit_since, best_since):
                    arr[pay] = 0.0
                win_since[pay] = 0
                days_since[pay] = 0
                due_t = t + rules.processing_days
                if due_t == t:
                    recv_sum = recv_sum + np.where(pay, received, 0.0)
                    recv_cnt = recv_cnt + pay
                elif due_t < n_days:
                    sched_amt[:, due_t] += np.where(pay, received, 0.0)
                    sched_cnt[:, due_t] += pay
            if rules.max_payouts is not None:
                live_now = live_now | (pay & (pay_acc >= rules.max_payouts))
            to_live_n = to_live_n + live_now
            lost = is_f & breach
            funded_lost = funded_lost + lost
            if (lost | live_now).any():
                rebuy(lost | live_now, t)
        max_out = np.maximum(max_out, fees_sum - recv_sum)
        for h, last in horizon_last.items():
            if last == t:
                net = recv_sum - fees_sum
                snaps[h] = _metrics(net, recv_cnt, fees_sum, bought, passed_n, evals_lost, funded_lost, requested,
                                    ruin_t, max_out, t)
                snaps[h]["to_live"] = float(to_live_n.mean())

    return {"horizons": snaps, "n_paths": n_paths, "n_sessions": n_days, "idx": idx,
            "per_path": {"fees": fees_sum, "received": recv_sum, "received_n": recv_cnt, "bought": bought,
                         "passed": passed_n, "evals_lost": evals_lost, "funded_lost": funded_lost,
                         "requested": requested, "phase": phase, "ruin_t": ruin_t, "to_live": to_live_n}}


def _metrics(net, recv_cnt, fees, bought, passed, evals_lost, funded_lost, requested, ruin_t, max_out, t) -> dict:
    q = np.percentile(net, [5, 25, 50, 75, 95])
    n = net.size
    sd = float(net.std(ddof=1)) if n > 1 else 0.0
    return {
        "ev": float(net.mean()), "se": sd / math.sqrt(n), "median": float(q[2]),
        "p5": float(q[0]), "p25": float(q[1]), "p75": float(q[3]), "p95": float(q[4]),
        "p_net_pos": float((net > 0).mean()), "p_one_payout_received": float((recv_cnt > 0).mean()),
        "payouts_received": float(recv_cnt.mean()), "payouts_requested": float(requested.mean()),
        "fees": float(fees.mean()), "accounts_bought": float(bought.mean()), "evals_passed": float(passed.mean()),
        "evals_lost": float(evals_lost.mean()), "funded_lost": float(funded_lost.mean()),
        "p_ruin": float(((ruin_t >= 0) & (ruin_t <= t)).mean()),
        "capital_required_p95": float(np.percentile(max_out, 95)),
    }
