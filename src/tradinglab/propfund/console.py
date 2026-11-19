"""Payload de solo lectura para la consola web (vista «Prop Fund»)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ..config import ROOT
from . import protected
from .instruments import universe
from .models import Market, VerificationStatus
from .registry import CONFIG_DIR, RegistryError, load_registry


def _rule_rows(firm) -> list[dict]:
    rows = []
    for program in firm.programs:
        for rule in program.rules:
            rows.append({
                "program": program.id,
                "key": rule.key,
                "value": rule.value,
                "unit": rule.unit,
                "phase": rule.phase,
                "status": rule.status.value,
                "source": rule.source.url if rule.source else None,
            })
    return rows


def payload(
    root: Path = ROOT,
    config_dir: Path | None = None,
    *,
    include_exposure: bool = False,
    exposure: dict | None = None,
) -> dict:
    if config_dir is None:
        config_dir = root / "config" / "propfund" if root != ROOT else CONFIG_DIR
    try:
        reg = load_registry(config_dir)
    except (RegistryError, ValueError) as exc:  # pydantic.ValidationError hereda de ValueError
        return {"ok": False, "error": str(exc)}

    firms = []
    for firm in sorted(reg.firms.values(), key=lambda f: (f.market.value, f.priority)):
        accounts = reg.accounts_of(firm.id)
        pol = firm.automation
        firms.append({
            "id": firm.id,
            "name": firm.name,
            "market": firm.market.value,
            "priority": firm.priority,
            "enabled": firm.enabled,
            "protected": firm.protected,
            "website": firm.website,
            "platforms": firm.platforms,
            "providers": firm.execution_providers,
            "rules_version": firm.rules_version,
            "automation": {
                "permission": pol.permission.value,
                "status": pol.status.value,
                "auto_orders": pol.permission.allows_auto_orders and pol.status is VerificationStatus.VERIFIED_OFFICIAL,
                "conditions": pol.conditions,
                "copy_trading": pol.copy_trading,
                "vps_allowed": pol.vps_allowed,
                "exclusive_to_firm": pol.exclusive_to_firm,
                "sources": [s.url for s in pol.sources],
            },
            "programs": [{"id": p.id, "name": p.name, "phases": [ph.value for ph in p.phases],
                          "sizes": p.sizes} for p in firm.programs],
            "rules": _rule_rows(firm),
            "accounts": [a.id for a in accounts],
        })

    accounts = []
    for acc in reg.accounts.values():
        firm = reg.firms[acc.firm]
        accounts.append({
            "id": acc.id,
            "firm": firm.name,
            "firm_id": firm.id,
            "program": acc.program,
            "market": acc.market.value,
            "phase": acc.phase.value,
            "size": acc.nominal_size,
            "platform": acc.platform,
            "provider": acc.execution_provider,
            "state": acc.connection_state.value,
            "template": acc.template,
            "protected": acc.protected,
            "legacy": acc.legacy_account,
            "instruments": acc.allowed_instruments,
            "limits": acc.limits.model_dump(),
            "risk": acc.risk.model_dump(),
            "automation_ack": acc.automation_acknowledged,
            "strategies": sorted({a.strategy for a in reg.assignments.values() if a.account == acc.id}),
            "notes": acc.notes.strip(),
        })

    strategies = [{
        "id": s.id, "name": s.name, "lane": s.lane.value, "market": s.market.value,
        "instruments": s.instruments, "timeframe": s.timeframe, "status": s.status,
        "protected": s.protected, "engine": s.engine, "params_ref": s.params_ref,
        "assignments": [a.id for a in reg.assignments_of(s.id)],
    } for s in reg.strategies.values()]

    assignments = [{
        "id": a.id, "strategy": a.strategy, "account": a.account,
        "firm": reg.accounts[a.account].firm, "instruments": a.instruments,
        "enabled": a.enabled, "replication_group": a.replication_group, "notes": a.notes,
    } for a in reg.assignments.values()]

    instruments = [item.as_dict() for item in universe()]
    states = Counter(a["state"] for a in accounts)
    integrity = protected.verify(root)
    if exposure is None and include_exposure:
        from .snapshots import collect_exposure

        exposure = collect_exposure(root=root, config_dir=config_dir)
    data = {
        "ok": True,
        "summary": {
            "firms": len(firms),
            "firms_cfd": sum(1 for f in firms if f["market"] == Market.CFD.value),
            "firms_futures": sum(1 for f in firms if f["market"] == Market.FUTURES.value),
            "accounts": len(accounts),
            "accounts_real": sum(1 for a in accounts if not a["template"]),
            "accounts_template": sum(1 for a in accounts if a["template"]),
            "auto_firms": sum(1 for f in firms if f["automation"]["auto_orders"]),
            "strategies": len(strategies),
            "strategies_protected": sum(1 for s in strategies if s["protected"]),
            "assignments": len(assignments),
            "assignments_enabled": sum(1 for a in assignments if a["enabled"]),
            "states": dict(states),
            "mode": "PAPER/DEMO",
        },
        "firms": firms,
        "accounts": accounts,
        "strategies": strategies,
        "assignments": assignments,
        "instruments": instruments,
        "protection": integrity,
        "warnings": reg.warnings,
    }
    if exposure is not None:
        data["exposure"] = exposure
    return data


__all__ = ["payload"]
