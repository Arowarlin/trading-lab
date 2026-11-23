"""Bloqueo de rendimiento antes de register+approve (R9b).

Las funciones que calculan expectativa, PF, percentil de deriva, Monte Carlo o
perturbaciones no deben correr sobre una spec/plantilla que aún no tiene
campaña aprobada. La única excepción es el flag interno de tests, que se activa
desde ``tests/conftest.py``; los tests que verifican el bloqueo lo desactivan.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ALLOW_UNAPPROVED = os.environ.get(
    "TRADINGLAB_ALLOW_UNAPPROVED", ""
).strip().lower() in {"1", "true", "yes", "on"}

_APPROVED_STATES = {
    "registered",
    "running",
    "done",
    "evaluated",
    "promovible",
    "finalist",
}
_BLOCKED_STATES = {"draft", "synthetic", "rejected", "invalid", "superseded"}


class UnapprovedPerformanceError(PermissionError):
    """Se intentó calcular rendimiento sin una campaña aprobada."""


def is_approved(campaign: dict[str, Any] | None) -> bool:
    if not campaign:
        return False
    state = str(campaign.get("status") or "").strip().lower()
    if state in _BLOCKED_STATES or state not in _APPROVED_STATES:
        return False
    return bool(campaign.get("approved_at"))


def require_approved(
    campaign_id: str,
    *,
    approved: bool = False,
    action: str = "rendimiento",
) -> None:
    """Guardia barata para funciones que ya reciben el estado de aprobación."""

    if ALLOW_UNAPPROVED or approved:
        return
    raise UnapprovedPerformanceError(
        f"{action}: campaña {campaign_id or '(sin id)'} sin register+approve. "
        "No se calcula rendimiento antes del pre-registro; si ya se miró, "
        "anótalo con 'lab learning record-informal'."
    )


def require_approved_campaign(
    campaign: dict[str, Any] | None,
    *,
    action: str = "rendimiento",
    allow_synthetic: bool = False,
) -> None:
    if ALLOW_UNAPPROVED:
        return
    state = str((campaign or {}).get("status") or "").strip().lower()
    if allow_synthetic and state == "synthetic":
        return
    if is_approved(campaign):
        return
    identifier = str((campaign or {}).get("id") or "(sin id)")
    raise UnapprovedPerformanceError(
        f"{action}: campaña {identifier} sin register+approve "
        f"(estado {state or 'Sin datos'}). No se calcula rendimiento antes "
        "del pre-registro; si ya se miró, anótalo con "
        "'lab learning record-informal'."
    )


def require_approved_strategy(
    strategy_id: int | None,
    *,
    db_path: str | Path | None = None,
    action: str = "rendimiento",
) -> None:
    if ALLOW_UNAPPROVED:
        return
    if strategy_id is None:
        raise UnapprovedPerformanceError(
            f"{action}: falta strategy_id de una campaña aprobada"
        )
    from . import databank

    strategy = databank.get_strategy(int(strategy_id), db_path=db_path)
    if strategy is None:
        raise UnapprovedPerformanceError(
            f"{action}: estrategia {strategy_id} no registrada"
        )
    campaign = databank.get_campaign(
        str(strategy["campaign_id"]), db_path=db_path
    )
    require_approved_campaign(campaign, action=action)


__all__ = [
    "ALLOW_UNAPPROVED",
    "UnapprovedPerformanceError",
    "is_approved",
    "require_approved",
    "require_approved_campaign",
    "require_approved_strategy",
]
