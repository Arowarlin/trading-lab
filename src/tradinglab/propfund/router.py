"""Strategy Router: una señal → una decisión independiente por cuenta.

    Señal → Elegibilidad → Compliance → Riesgo → Coste → Solicitud → Reconciliación

* Nunca un copiador ciego: cada cuenta se valida por separado y puede terminar
  en un estado distinto.
* Las firmas que prohíben la automatización (o cuya política no está
  verificada) reciben ``ALERT_ONLY``: investigación/señal/alerta, nunca orden.
* La salida máxima es ``READY_DRY_RUN``: una solicitud de ejecución en
  PAPER/DEMO, con clave de idempotencia. Este módulo **no envía órdenes**; el
  adaptador de ejecución (Fase 4) es quien la consume tras autorización.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import floor
from pathlib import Path

from ..config import ROOT
from .costs import CostProfile, estimate_cfd, estimate_futures, load_profile
from .instruments import resolve
from .models import AccountPhase, Market, StrategyAssignment
from .registry import Registry
from .risk import AccountSnapshot, GlobalLimits, PositionView, check_account, check_global

DECISIONS_LOG = ROOT / "logs" / "propfund" / "decisions.jsonl"


class Decision(StrEnum):
    REJECTED_ELIGIBILITY = "REJECTED_ELIGIBILITY"
    ALERT_ONLY = "ALERT_ONLY"
    REJECTED_COMPLIANCE = "REJECTED_COMPLIANCE"
    REJECTED_SIZING = "REJECTED_SIZING"
    REJECTED_RISK = "REJECTED_RISK"
    REJECTED_COST = "REJECTED_COST"
    READY_DRY_RUN = "READY_DRY_RUN"


@dataclass(frozen=True)
class Signal:
    strategy: str
    symbol: str
    side: str            # long | short
    entry: float
    stop: float
    ts: str = ""

    def __post_init__(self) -> None:
        if self.side not in {"long", "short"}:
            raise ValueError("side debe ser long o short")
        if (self.side == "long" and self.stop >= self.entry) or (self.side == "short" and self.stop <= self.entry):
            raise ValueError("el stop debe estar del lado contrario a la entrada")


@dataclass
class AccountDecision:
    assignment: str
    account: str
    firm: str
    decision: Decision
    steps: list[dict] = field(default_factory=list)
    quantity: float = 0.0
    risk_usd: float = 0.0
    cost: dict | None = None
    request: dict | None = None

    def step(self, name: str, ok: bool, reasons: list[str] | None = None, **extra) -> None:
        self.steps.append({"step": name, "ok": ok, "reasons": reasons or [], **extra})

    def as_dict(self) -> dict:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


_PHASE_ALIASES = {
    AccountPhase.EVALUATION: {"evaluation", "challenge", "combine"},
    AccountPhase.VERIFICATION: {"verification", "evaluation"},
    AccountPhase.FUNDED: {"funded", "express_funded"},
    AccountPhase.LIVE: {"live"},
}


def _phase_allowed(phase: AccountPhase, allowed: list[str]) -> bool:
    if not allowed:
        return True
    return bool(_PHASE_ALIASES[phase] & {p.lower() for p in allowed})


def _size(signal: Signal, risk_usd: float, *, contract_size: float | None) -> tuple[float, str | None]:
    item = resolve(signal.symbol)
    dist = abs(signal.entry - signal.stop)
    if item.market is Market.FUTURES:
        ticks = dist / item.tick_size
        per_contract = ticks * item.tick_value
        qty = floor(risk_usd / per_contract) if per_contract > 0 else 0
        return float(qty), None if qty >= 1 else "el riesgo no alcanza para 1 contrato"
    size = contract_size if contract_size is not None else item.contract_size
    if size is None:
        return 0.0, "Sin datos: tamaño de contrato del bróker"
    lots = floor((risk_usd / (dist * size)) * 100) / 100
    return lots, None if lots >= 0.01 else "el riesgo no alcanza para 0.01 lotes"


def _replication_ok(reg: Registry, asg: StrategyAssignment) -> list[str]:
    if not asg.replication_group:
        return []
    peers = [a for a in reg.assignments.values() if a.replication_group == asg.replication_group]
    reasons: list[str] = []
    for peer in peers:
        firm = reg.firm_of(peer.account)
        if firm.automation.copy_trading not in {"allowed", "own_accounts"}:
            reasons.append(f"{firm.name} no permite copiar operaciones entre cuentas")
        if firm.automation.exclusive_to_firm and len({reg.accounts[p.account].firm for p in peers}) > 1:
            reasons.append(f"{firm.name} exige bot exclusivo: no se replica a otras firmas")
    return sorted(set(reasons))


def route(
    signal: Signal,
    reg: Registry,
    *,
    snapshots: dict[str, AccountSnapshot],
    positions: list[PositionView] | None = None,
    contract_sizes: dict[str, float] | None = None,
    cost_profiles: dict[str, CostProfile] | None = None,
    include_disabled: bool = False,
    global_limits: GlobalLimits | None = None,
) -> list[AccountDecision]:
    """Evalúa la señal contra cada asignación de su estrategia."""
    positions = list(positions or [])
    contract_sizes = contract_sizes or {}
    cost_profiles = cost_profiles or {}
    strategy = reg.strategies.get(signal.strategy)
    item = resolve(signal.symbol)
    out: list[AccountDecision] = []

    for asg in reg.assignments_of(signal.strategy):
        acc = reg.accounts.get(asg.account)
        firm = reg.firms.get(acc.firm) if acc else None
        dec = AccountDecision(asg.id, asg.account, firm.id if firm else "?", Decision.REJECTED_ELIGIBILITY)
        out.append(dec)

        # 1 · Elegibilidad -----------------------------------------------------
        reasons: list[str] = []
        if strategy is None or acc is None or firm is None:
            reasons.append("estrategia, cuenta o firma inexistente")
        else:
            if strategy.protected:
                reasons.append("estrategia protegida: la ejecuta su propio motor")
            if not asg.enabled and not include_disabled:
                reasons.append("asignación deshabilitada")
            if acc.template:
                reasons.append("cuenta plantilla: no es una cuenta real")
            if not acc.connection_state.can_route:
                reasons.append(f"conexión {acc.connection_state.value}: solo PAPER/DEMO enrutan")
            if item.id not in asg.instruments or item.id not in acc.allowed_instruments:
                reasons.append(f"{item.id} no permitido en la asignación/cuenta")
            if item.market is not acc.market:
                reasons.append("motor distinto: CFD y Futures no se mezclan")
        dec.step("eligibility", not reasons, reasons)
        if reasons:
            continue

        # 2 · Compliance -------------------------------------------------------
        policy = firm.automation_for(acc.program)
        reasons = []
        if not policy.permission.allows_auto_orders:
            dec.step("compliance", False, [f"automatización {policy.permission.value} en {firm.name}"])
            dec.decision = Decision.ALERT_ONLY
            continue
        if not policy.status.is_verified:
            dec.step("compliance", False, [f"política de {firm.name} sin verificar en fuente oficial"])
            dec.decision = Decision.ALERT_ONLY
            continue
        if not acc.automation_acknowledged:
            reasons.append("el operador no confirmó las condiciones de automatización de la firma")
        if not _phase_allowed(acc.phase, policy.allowed_phases):
            reasons.append(f"fase {acc.phase.value} sin automatización permitida")
        if policy.exclusive_to_firm:
            other = {reg.accounts[a.account].firm for a in reg.assignments_of(signal.strategy)} - {firm.id}
            if other:
                reasons.append(f"{firm.name} exige bot exclusivo y la estrategia está en {sorted(other)}")
        reasons += _replication_ok(reg, asg)
        dec.step("compliance", not reasons, reasons, conditions=policy.conditions)
        if reasons:
            dec.decision = Decision.REJECTED_COMPLIANCE
            continue

        # 3 · Tamaño ----------------------------------------------------------
        snap = snapshots.get(acc.id)
        equity = snap.equity if snap else acc.nominal_size
        risk_usd = equity * acc.risk.per_trade_risk_pct * asg.risk_per_trade_r
        qty, err = _size(signal, risk_usd, contract_size=contract_sizes.get(acc.id))
        dec.step("sizing", err is None, [err] if err else [], quantity=qty, risk_budget_usd=round(risk_usd, 2))
        if err:
            dec.decision = Decision.REJECTED_SIZING
            continue
        # Riesgo real tras redondear la cantidad hacia abajo.
        dist = abs(signal.entry - signal.stop)
        if item.market is Market.FUTURES:
            real_risk = qty * dist / item.tick_size * item.tick_value
        else:
            real_risk = qty * dist * (contract_sizes.get(acc.id) or item.contract_size or 0)
        dec.quantity, dec.risk_usd = qty, round(real_risk, 2)

        # 4 · Riesgo cuenta + global ---------------------------------------------
        acc_check = check_account(acc, snap, new_risk_usd=real_risk)
        signed = qty if signal.side == "long" else -qty
        glob_check = check_global(
            positions, account=acc.id, firm=firm.id, strategy=signal.strategy, symbol=item.id,
            quantity=signed, price=signal.entry, risk_usd=real_risk,
            contract_size=contract_sizes.get(acc.id), limits=global_limits,
        )
        dec.step("risk_account", acc_check.ok, acc_check.reasons, metrics=acc_check.metrics)
        dec.step("risk_global", glob_check.ok, glob_check.reasons)
        if not (acc_check.ok and glob_check.ok):
            dec.decision = Decision.REJECTED_RISK
            continue

        # 5 · Coste --------------------------------------------------------------
        profile = cost_profiles.get(acc.id) or load_profile(acc.id, item.id, firm=firm.id)
        if item.market is Market.FUTURES:
            est = estimate_futures(profile, contracts=int(qty), risk_usd=real_risk)
        else:
            est = estimate_cfd(profile, lots=qty, price=signal.entry,
                               contract_size=contract_sizes.get(acc.id) or item.contract_size,
                               risk_usd=real_risk)
        dec.cost = est.as_dict()
        reasons = []
        if not est.complete:
            reasons.append(f"Sin datos de coste: {', '.join(est.missing)}")
        elif est.cost_r is not None and est.cost_r > acc.risk.max_cost_r:
            reasons.append(f"coste {est.cost_r:.2f}R > máximo {acc.risk.max_cost_r:.2f}R")
        dec.step("cost", not reasons, reasons)
        if reasons:
            dec.decision = Decision.REJECTED_COST
            continue

        # 6 · Solicitud (dry-run) ----------------------------------------------------
        payload = {
            "account": acc.id, "provider": acc.execution_provider, "symbol": item.id,
            "side": signal.side, "quantity": qty, "entry": signal.entry, "stop": signal.stop,
            "strategy": signal.strategy, "assignment": asg.id, "ts": signal.ts,
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        dec.request = {**payload, "mode": acc.connection_state.value, "dry_run": True, "idempotency_key": key}
        dec.step("execution_request", True)
        dec.decision = Decision.READY_DRY_RUN
    return out


def log_decisions(signal: Signal, decisions: list[AccountDecision], path: Path = DECISIONS_LOG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for dec in decisions:
            fh.write(json.dumps({
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                "signal": asdict(signal),
                **dec.as_dict(),
            }, ensure_ascii=False) + "\n")
    return path


__all__ = ["AccountDecision", "DECISIONS_LOG", "Decision", "Signal", "log_decisions", "route"]
