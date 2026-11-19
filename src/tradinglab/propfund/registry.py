"""Carga y valida ``config/propfund`` (firmas, cuentas, estrategias, asignaciones)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import ROOT
from .instruments import is_in_universe, resolve
from .models import (
    Firm,
    PropAccount,
    Strategy,
    StrategyAssignment,
    StrategyLane,
)

CONFIG_DIR = ROOT / "config" / "propfund"


class RegistryError(ValueError):
    pass


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RegistryError(f"{path.name}: se esperaba un mapa YAML")
    return data


@dataclass
class Registry:
    firms: dict[str, Firm] = field(default_factory=dict)
    accounts: dict[str, PropAccount] = field(default_factory=dict)
    strategies: dict[str, Strategy] = field(default_factory=dict)
    assignments: dict[str, StrategyAssignment] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------- consultas
    def firm_of(self, account_id: str) -> Firm:
        return self.firms[self.accounts[account_id].firm]

    def accounts_of(self, firm_id: str) -> list[PropAccount]:
        return [a for a in self.accounts.values() if a.firm == firm_id]

    def assignments_of(self, strategy_id: str) -> list[StrategyAssignment]:
        return [a for a in self.assignments.values() if a.strategy == strategy_id]

    def affected_accounts(self, firm_id: str, program_id: str | None = None) -> list[str]:
        """Cuentas afectadas por un cambio de reglas de una firma/programa."""
        return sorted(
            a.id for a in self.accounts.values()
            if a.firm == firm_id and (program_id is None or a.program == program_id)
        )


def load_registry(config_dir: Path = CONFIG_DIR) -> Registry:
    reg = Registry()
    for raw in _load(config_dir / "firms.yaml").get("firms") or []:
        firm = Firm.model_validate(raw)
        if firm.id in reg.firms:
            raise RegistryError(f"firma duplicada: {firm.id}")
        reg.firms[firm.id] = firm
    for raw in _load(config_dir / "accounts.yaml").get("accounts") or []:
        acc = PropAccount.model_validate(raw)
        if acc.id in reg.accounts:
            raise RegistryError(f"cuenta duplicada: {acc.id}")
        reg.accounts[acc.id] = acc
    for raw in _load(config_dir / "strategies.yaml").get("strategies") or []:
        st = Strategy.model_validate(raw)
        reg.strategies[st.id] = st
    for raw in _load(config_dir / "assignments.yaml").get("assignments") or []:
        asg = StrategyAssignment.model_validate(raw)
        reg.assignments[asg.id] = asg
    validate(reg)
    return reg


def validate(reg: Registry) -> None:
    """Coherencia cruzada. Errores duros → RegistryError; dudas → warnings."""
    errors: list[str] = []
    for acc in reg.accounts.values():
        firm = reg.firms.get(acc.firm)
        if firm is None:
            errors.append(f"{acc.id}: firma desconocida {acc.firm}")
            continue
        if firm.market is not acc.market:
            errors.append(f"{acc.id}: mercado {acc.market} distinto del de {firm.id} ({firm.market})")
        if firm.program(acc.program) is None:
            errors.append(f"{acc.id}: programa {acc.program} no existe en {firm.id}")
        for sym in acc.allowed_instruments:
            if not is_in_universe(sym):
                errors.append(f"{acc.id}: {sym} fuera del universo (acciones/ETF excluidos)")
            elif resolve(sym).market is not acc.market:
                errors.append(f"{acc.id}: {sym} es {resolve(sym).market}, la cuenta es {acc.market}")
        if acc.connection_state.value.startswith("LIVE"):
            errors.append(f"{acc.id}: estado LIVE no se declara en archivo; requiere autorización humana")
        if acc.protected and not firm.protected:
            reg.warnings.append(f"{acc.id}: cuenta protegida en una firma no protegida")

    for st in reg.strategies.values():
        for sym in st.instruments:
            if not is_in_universe(sym):
                errors.append(f"estrategia {st.id}: {sym} fuera del universo")
            elif resolve(sym).market is not st.market:
                errors.append(f"estrategia {st.id}: {sym} no es {st.market}")
        if st.lane is StrategyLane.PROTECTED_FTMO and not st.protected:
            errors.append(f"estrategia {st.id}: carril protegido sin protected: true")

    for asg in reg.assignments.values():
        st = reg.strategies.get(asg.strategy)
        acc = reg.accounts.get(asg.account)
        if st is None or acc is None:
            errors.append(f"{asg.id}: estrategia o cuenta inexistente")
            continue
        if st.protected:
            errors.append(f"{asg.id}: {st.id} es protegida; no se asigna desde el Prop Fund")
        if st.market is not acc.market:
            errors.append(f"{asg.id}: {st.id} ({st.market}) en cuenta {acc.market}: motores no se mezclan")
        for sym in asg.instruments:
            if sym not in st.instruments:
                errors.append(f"{asg.id}: {sym} no está en la estrategia {st.id}")
            if sym not in acc.allowed_instruments:
                errors.append(f"{asg.id}: {sym} no está permitido en {acc.id}")

    # Exclusividad de firma (Tradeify): una estrategia asignada a esa firma no
    # puede estar asignada a otra firma.
    for st_id in {a.strategy for a in reg.assignments.values()}:
        firms = {reg.accounts[a.account].firm for a in reg.assignments_of(st_id) if a.account in reg.accounts}
        for firm_id in firms:
            policy = reg.firms[firm_id].automation
            if policy.exclusive_to_firm and len(firms) > 1:
                reg.warnings.append(
                    f"{st_id}: asignada a {firm_id} (bot exclusivo) y a otras firmas {sorted(firms - {firm_id})}; "
                    "el router bloqueará la ejecución automática"
                )
    if errors:
        raise RegistryError("; ".join(errors))


__all__ = ["CONFIG_DIR", "Registry", "RegistryError", "load_registry", "validate"]
