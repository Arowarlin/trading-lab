"""Fechas de trading y timestamps con zona explícita.

- ``market_today()`` es la fecha del día de trading en Nueva York.
- ``utc_now()`` es el instante UTC para logs, nombres de archivo y auditoría.

Los resets de fondeo no se tocan: siguen usando su ``reset_tz`` (FTMO, Praga).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def market_today(now: datetime | None = None):
    """Fecha de Nueva York; si `now` es naive, se interpreta como UTC."""
    moment = now or utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MARKET_TZ).date()


__all__ = ["MARKET_TZ", "market_today", "utc_now"]
