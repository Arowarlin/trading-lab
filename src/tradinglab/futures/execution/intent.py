"""``OrderIntent``: una orden propuesta que todavía no ha salido (execution_spec.md §2-3) — FUT-J1."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from ...config import ROOT
from ...prop_economics.rules import Program
from ...propfund.instruments import micro_equivalent, resolve

EXECUTION_CONFIG = ROOT / "config" / "futures" / "execution.yaml"
ROOTS = ("MNQ", "NQ", "MES", "ES", "MGC", "GC")


def load_execution_config(path: str | Path = EXECUTION_CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ContractSpec:
    root: str
    point_value: float
    tick_size: float
    tick_value: float
    micro_eq: float
    underlying: str


def contract_spec(root: str) -> ContractSpec:
    if root not in ROOTS:
        raise ValueError(f"raíz no admitida: {root}")
    item = resolve(root)
    return ContractSpec(root, float(item.multiplier), float(item.tick_size), float(item.tick_value),
                        float(micro_equivalent(root)), str(item.underlying))


@dataclass(frozen=True)
class OrderIntent:
    strategy_id: str
    hypothesis_id: str
    account_id: str
    firm_id: str
    program_id: str
    phase: str                      # "evaluation" | "funded"
    root: str
    contract: str
    side: str                       # "buy" | "sell"
    qty: int
    entry_type: str                 # "market" | "limit" | "stop"
    entry_price: float              # para market, el precio de referencia que se pasa al control
    stop_price: float
    target_price: float | None
    exit_by: datetime
    origin: str                     # "automated" | "semi_manual"
    adapter: str                    # "paper" | "projectx" | "nt8" | "ticket"
    risk_usd: float
    cost_usd: float
    cost_assumed: bool
    signal_hash: str
    created_at: datetime
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = True

    @property
    def micro_eq(self) -> float:
        return self.qty * contract_spec(self.root).micro_eq


def commission_per_side(program: Program, root: str, adapter: str, cfg: dict) -> tuple[float | None, bool]:
    """(comisión por lado, supuesta). Sin dato verificado: en paper la del laboratorio; si no, None."""
    value = program.commissions_per_side.get(root)
    if value is not None and value.status not in {"sin_datos"} and value.value is not None:
        return float(value.value), False
    if adapter == "paper":
        lab = (cfg.get("lab_commission_per_side") or {}).get(root)
        if lab is not None:
            return float(lab["value"]), True
    return None, True


def build_intent(*, program: Program, cfg: dict, strategy_id: str, hypothesis_id: str, account_id: str,
                 phase: str, root: str, contract: str, side: str, qty: int, entry_type: str, entry_price: float,
                 stop_price: float, target_price: float | None, exit_by: datetime, origin: str, adapter: str,
                 signal_hash: str, created_at: datetime) -> OrderIntent:
    """Calcula riesgo y coste (§3) y devuelve el intent. Nunca lo envía."""
    if created_at.tzinfo is None or exit_by.tzinfo is None:
        raise ValueError("las horas deben llevar zona")
    spec = contract_spec(root)
    commission, assumed = commission_per_side(program, root, adapter, cfg)
    slip_ticks = int(cfg.get("default_slippage_ticks", 1))
    cost_c = None if commission is None else 2 * commission + 2 * slip_ticks * spec.tick_value
    risk = None if cost_c is None else qty * abs(entry_price - stop_price) * spec.point_value + qty * cost_c
    return OrderIntent(
        strategy_id=strategy_id, hypothesis_id=hypothesis_id, account_id=account_id, firm_id=program.firm_id,
        program_id=program.program_id, phase=phase, root=root, contract=contract, side=side, qty=qty,
        entry_type=entry_type, entry_price=entry_price, stop_price=stop_price, target_price=target_price,
        exit_by=exit_by, origin=origin, adapter=adapter,
        risk_usd=float("nan") if risk is None else round(risk, 10),
        cost_usd=float("nan") if cost_c is None else round(qty * cost_c, 10),
        cost_assumed=assumed, signal_hash=signal_hash, created_at=created_at)
