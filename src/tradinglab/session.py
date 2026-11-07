"""Filtros de sesión: fin de semana, viernes y rollover.

Todas las horas son UTC. El cierre de posiciones nunca se bloquea; los
llamadores solo consultan `blocked` para aperturas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone

from .prop.rules import PropRules


@dataclass(frozen=True)
class SessionBlock:
    blocked: bool
    reason: str
    kind: str = ""
    data_ok: bool = True


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hour, minute = value.strip().split(":")
        return time(int(hour), int(minute), tzinfo=timezone.utc)
    except Exception:
        return default


def _minutes_diff(a: time, b: time) -> int:
    """Diferencia circular en minutos entre dos horas UTC."""
    left = a.hour * 60 + a.minute
    right = b.hour * 60 + b.minute
    diff = abs(left - right)
    return min(diff, 1440 - diff)


def session_block(
    rules: PropRules,
    now: datetime | None = None,
    *,
    asset_class: str = "equity",
) -> SessionBlock:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    weekday = now.weekday()  # 0=lunes, 4=viernes, 5=sábado, 6=domingo

    if not rules.weekend_holding:
        friday_close = _parse_hhmm(rules.friday_close_utc, time(20, 0, tzinfo=timezone.utc))
        if weekday == 4 and now.timetz().replace(tzinfo=timezone.utc) >= friday_close:
            return SessionBlock(
                True,
                f"viernes después de {rules.friday_close_utc} UTC: no mantener fin de semana",
                "friday",
            )
        if weekday >= 5:
            return SessionBlock(
                True,
                "fin de semana con weekend_holding=false",
                "weekend",
            )

    if asset_class.lower() in {"futures", "cfd"} and rules.rollover_blackout_min > 0:
        rollover = _parse_hhmm(rules.rollover_utc, time(21, 0, tzinfo=timezone.utc))
        if _minutes_diff(now.timetz().replace(tzinfo=timezone.utc), rollover) <= rules.rollover_blackout_min:
            return SessionBlock(
                True,
                f"rollover {rules.rollover_utc} UTC ± {rules.rollover_blackout_min} min",
                "rollover",
            )

    return SessionBlock(False, "sesión permitida")


__all__ = ["SessionBlock", "session_block"]
