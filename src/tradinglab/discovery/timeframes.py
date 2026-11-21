"""Temporalidades canónicas del Discovery Lab y conversión minutos → velas.

Una sola fuente de verdad para las siete temporalidades, su duración y las
conversiones que antes estaban repartidas por el código. Todo lo temporal de una
estrategia se declara en **minutos**; el motor lo convierte a velas una sola vez
con ``minutes_to_bars`` (redondeo hacia arriba, nunca hacia abajo).
"""

from __future__ import annotations

import math
import re
from zoneinfo import ZoneInfo

import pandas as pd

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TF_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}
_ALIASES = {
    "1M": "M1",
    "5M": "M5",
    "15M": "M15",
    "30M": "M30",
    "1H": "H1",
    "4H": "H4",
    "1D": "D1",
}
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class TimeframeError(ValueError):
    pass


def normalize_timeframe(value: str) -> str:
    """Devuelve la forma canónica (``M5``, ``H1``…) o falla."""

    text = str(value or "").strip().upper()
    text = _ALIASES.get(text, text)
    if text not in TF_MINUTES:
        valid = ", ".join(TIMEFRAMES)
        raise TimeframeError(
            f"timeframe no soportado: {value!r}; usa uno de: {valid}"
        )
    return text


def timeframe_minutes(value: str) -> int:
    return int(TF_MINUTES[normalize_timeframe(value)])


def higher_timeframes(base: str) -> tuple[str, ...]:
    """Temporalidades estrictamente superiores a ``base``."""

    minutes = timeframe_minutes(base)
    return tuple(tf for tf in TIMEFRAMES if TF_MINUTES[tf] > minutes)


def is_higher(base: str, other: str) -> bool:
    return timeframe_minutes(other) > timeframe_minutes(base)


def minutes_to_bars(minutes: int | float, timeframe: str) -> int:
    """Convierte una duración en minutos al número de velas de ``timeframe``.

    ``ceil``: una salida de 30 minutos en H4 ocupa 1 vela, no 0. Una duración
    de 0 minutos son 0 velas (sin límite temporal).
    """

    value = float(minutes)
    if not math.isfinite(value) or value < 0:
        raise TimeframeError(f"minutos inválidos: {minutes!r}")
    if value == 0:
        return 0
    return max(1, int(math.ceil(value / timeframe_minutes(timeframe))))


def _hhmm_minutes(value: str) -> int:
    match = _HHMM.match(str(value or "").strip())
    if match is None:
        raise TimeframeError(f"hora inválida: {value!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


def window_minutes(start: str, end: str) -> int:
    """Minutos de una ventana HH:MM; ``end <= start`` cruza medianoche."""

    begin = _hhmm_minutes(start)
    finish = _hhmm_minutes(end)
    if finish <= begin:
        finish += 24 * 60
    return int(finish - begin)


def bars_in_window(start: str, end: str, timeframe: str) -> int:
    """Velas necesarias para cubrir una ventana de sesión."""

    return max(1, minutes_to_bars(window_minutes(start, end), timeframe))


def bar_delta(timeframe: str) -> pd.Timedelta:
    """Duración de una vela canónica."""

    return pd.Timedelta(minutes=timeframe_minutes(timeframe))


def session_tz(name: str | None, default: str = "America/New_York") -> str:
    """Valida una zona IANA; devuelve ``default`` si no hay valor."""

    value = str(name or default)
    try:
        ZoneInfo(value)
    except Exception as exc:  # noqa: BLE001
        raise TimeframeError(f"zona horaria inválida: {value}") from exc
    return value


__all__ = [
    "TIMEFRAMES",
    "TF_MINUTES",
    "TimeframeError",
    "bar_delta",
    "bars_in_window",
    "higher_timeframes",
    "is_higher",
    "minutes_to_bars",
    "normalize_timeframe",
    "session_tz",
    "timeframe_minutes",
    "window_minutes",
]
