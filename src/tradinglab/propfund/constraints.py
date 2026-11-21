"""Restricciones de firma comprobables sobre una estrategia del DSL.

El registro (``config/propfund/firms.yaml``) declara ``firm_constraints`` con
las reglas que la firma publica. Este módulo las convierte en un veredicto
determinista:

* ``compatible con <firma>`` si la estrategia no viola ninguna regla declarada.
* ``incompatible con <firma>: ...`` si viola al menos una.
* Las reglas sin dato se listan como ``sin datos`` y no bloquean.

La función es compartida por el onboarding, el mapa de viabilidad y la matriz;
no escribe nada y no conoce cuentas reales.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import Firm, FirmRule, Program, PropAccount, VerificationStatus

CONSTRAINT_KEYS = (
    "news_trading",
    "weekend_holding",
    "overnight_holding",
    "max_trades_per_day",
    "max_lots",
)
CONSTRAINT_LABELS = {
    "news_trading": "Noticias",
    "weekend_holding": "Fin de semana",
    "overnight_holding": "Overnight",
    "max_trades_per_day": "Máx. operaciones/día",
    "max_lots": "Máx. lotes",
}
_TRUE = {"true", "1", "yes", "si", "sí", "allowed", "permitido", "permitida"}
_FALSE = {
    "false",
    "0",
    "no",
    "forbidden",
    "prohibido",
    "prohibida",
    "not_allowed",
}


def _phase_matches(rule: FirmRule, phase: str) -> bool:
    value = str(rule.phase or "all").strip().lower()
    return value in {"", "all", "*", str(phase or "all").strip().lower()}


def constraints_for(
    firm: Firm,
    program: Program | None = None,
    *,
    phase: str = "all",
) -> dict[str, FirmRule]:
    """Reglas aplicables a la fase; el programa sobrescribe a la firma."""

    selected: dict[str, FirmRule] = {}
    for rule in firm.firm_constraints:
        if _phase_matches(rule, phase):
            selected[str(rule.key)] = rule
    if program is not None:
        for rule in program.firm_constraints:
            if _phase_matches(rule, phase):
                selected[str(rule.key)] = rule
    return selected


def _tri_state(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _strategy_dict(strategy: Any) -> dict[str, Any]:
    if isinstance(strategy, Mapping):
        return dict(strategy)
    if hasattr(strategy, "model_dump"):
        return strategy.model_dump(mode="json", exclude_none=False)
    raise TypeError("la estrategia debe ser un dict o un modelo del DSL")


def _minutes(hhmm: Any) -> int | None:
    try:
        hour, minute = str(hhmm).split(":")[:2]
        value = int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value < 24 * 60 else None


def _crosses_midnight(start: Any, end: Any) -> bool:
    left = _minutes(start)
    right = _minutes(end)
    if left is None or right is None:
        return True
    return right <= left


def _has_news_filter(node: Any) -> bool:
    if isinstance(node, Mapping):
        kind = str(node.get("kind") or "").strip().lower()
        ind = str(node.get("ind") or "").strip().lower()
        if kind in {"news", "news_filter", "calendar"}:
            return True
        if ind in {"news", "news_filter", "economic_calendar"}:
            return True
        for key in ("args", "left", "right", "expr"):
            value = node.get(key)
            if isinstance(value, list):
                if any(_has_news_filter(item) for item in value):
                    return True
            elif isinstance(value, Mapping) and _has_news_filter(value):
                return True
    return False


def _unknown(rule: FirmRule | None) -> bool:
    if rule is None or rule.value is None:
        return True
    return rule.status is not VerificationStatus.VERIFIED_OFFICIAL


@dataclass(frozen=True)
class ConstraintCheck:
    firm: str
    program: str | None
    phase: str
    compatible: bool
    label: str
    violations: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    applied: tuple[tuple[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "firm": self.firm,
            "program": self.program,
            "phase": self.phase,
            "compatible": self.compatible,
            "label": self.label,
            "violations": list(self.violations),
            "unknown": list(self.unknown),
            "applied": dict(self.applied),
        }


def check_strategy(
    strategy: Any,
    *,
    firm: Firm,
    program: Program | None = None,
    account: PropAccount | None = None,
    phase: str | None = None,
) -> ConstraintCheck:
    """Comprueba una estrategia contra las restricciones declaradas de la firma."""

    data = _strategy_dict(strategy)
    session = dict(data.get("session") or {})
    limits = dict(data.get("limits") or {})
    effective_phase = str(phase or (account.phase.value if account else "all"))
    rules = constraints_for(firm, program, phase=effective_phase)
    violations: list[str] = []
    unknown: list[str] = []
    applied: list[tuple[str, Any]] = []

    for key in CONSTRAINT_KEYS:
        rule = rules.get(key)
        if rule is not None:
            applied.append((key, rule.value))
        if _unknown(rule):
            unknown.append(key)

    # Noticias: si la firma prohíbe operar noticias, la estrategia necesita un
    # filtro explícito. El DSL actual no tiene bloque de noticias, así que una
    # estrategia sin filtro se marca incompatible (no se supone permiso).
    news = rules.get("news_trading")
    if news is not None and _tri_state(news.value) is False:
        if not _has_news_filter(data):
            violations.append("noticias: sin filtro de noticias y la firma las prohíbe")

    start = session.get("start")
    end = session.get("end")
    flat_at = session.get("flat_at")
    crosses = _crosses_midnight(start, end)
    flat_crosses = flat_at is not None and _crosses_midnight(start, flat_at)

    overnight = rules.get("overnight_holding")
    if overnight is not None and _tri_state(overnight.value) is False:
        if flat_at is None:
            violations.append("overnight: sin flat_at, la posición puede quedar abierta")
        elif crosses or flat_crosses:
            violations.append(
                f"overnight: la sesión {start}-{end} (flat {flat_at}) cruza medianoche"
            )

    weekend = rules.get("weekend_holding")
    weekdays = tuple(
        int(day)
        for day in (data.get("weekdays") or (0, 1, 2, 3, 4))
        if str(day).strip().lstrip("-").isdigit()
    )
    if weekend is not None and _tri_state(weekend.value) is False:
        if flat_at is None:
            violations.append("fin de semana: sin flat_at, la posición puede quedar abierta")
        elif 5 in weekdays or 6 in weekdays:
            violations.append("fin de semana: la estrategia permite operar sábado/domingo")
        elif 4 in weekdays and (crosses or flat_crosses):
            violations.append(
                "fin de semana: la sesión del viernes cruza medianoche"
            )

    max_trades = rules.get("max_trades_per_day")
    if max_trades is not None and max_trades.value is not None:
        try:
            firm_max = int(max_trades.value)
        except (TypeError, ValueError):
            firm_max = None
        if firm_max is not None and firm_max > 0:
            strategy_max = limits.get("max_trades_per_day")
            if strategy_max is None:
                violations.append(
                    f"máx. operaciones/día: la estrategia no declara límite (firma {firm_max})"
                )
            elif int(strategy_max) > firm_max:
                violations.append(
                    f"máx. operaciones/día: {int(strategy_max)} > {firm_max} de la firma"
                )

    max_lots = rules.get("max_lots")
    if max_lots is not None and max_lots.value is not None:
        try:
            firm_lots = float(max_lots.value)
        except (TypeError, ValueError):
            firm_lots = None
        account_lots = account.limits.max_lots if account is not None else None
        if firm_lots is not None and account_lots is not None and float(account_lots) > firm_lots:
            violations.append(
                f"máx. lotes: la cuenta permite {account_lots:g} > {firm_lots:g} de la firma"
            )

    compatible = not violations
    unknown_labels = [CONSTRAINT_LABELS[key] for key in unknown]
    if violations:
        label = f"incompatible con {firm.id}: " + "; ".join(violations)
    elif unknown_labels:
        label = f"compatible con {firm.id} (sin datos: {', '.join(unknown_labels)})"
    else:
        label = f"compatible con {firm.id}"
    return ConstraintCheck(
        firm=firm.id,
        program=program.id if program is not None else None,
        phase=effective_phase,
        compatible=compatible,
        label=label,
        violations=tuple(violations),
        unknown=tuple(unknown),
        applied=tuple(applied),
    )


def constraint_rows(
    firm: Firm,
    program: Program | None = None,
    *,
    phase: str = "all",
) -> list[dict[str, Any]]:
    """Filas legibles para el informe de onboarding."""

    rules = constraints_for(firm, program, phase=phase)
    rows: list[dict[str, Any]] = []
    for key in CONSTRAINT_KEYS:
        rule = rules.get(key)
        value = None if rule is None else rule.value
        if key in {"news_trading", "weekend_holding", "overnight_holding"}:
            tri = _tri_state(value)
            if tri is not None:
                display = "Permitido" if tri else "Prohibido"
            else:
                display = "Sin datos" if value is None else str(value)
        elif isinstance(value, bool):
            display = "Permitido" if value else "Prohibido"
        elif value is None:
            display = "Sin datos"
        else:
            display = str(value)
        status = "verified_official" if not _unknown(rule) else "unverified"
        source = rule.source if rule is not None else None
        rows.append(
            {
                "key": key,
                "label": CONSTRAINT_LABELS[key],
                "value": value,
                "display": display,
                "status": status,
                "source_url": source.url if source is not None else None,
                "consulted_at": source.consulted_at.isoformat() if source is not None else None,
                "note": rule.notes if rule is not None else "",
            }
        )
    return rows


__all__ = [
    "CONSTRAINT_KEYS",
    "CONSTRAINT_LABELS",
    "ConstraintCheck",
    "check_strategy",
    "constraint_rows",
    "constraints_for",
]
