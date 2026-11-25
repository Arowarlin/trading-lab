"""D1 · Conversión única de swap y noches."""

from __future__ import annotations

from datetime import date, datetime


def swap_bps_per_night(
    rate: float,
    mode: int,
    *,
    price: float | None = None,
    point: float | None = None,
) -> float:
    """Convierte un swap de MT5 a bps por noche."""

    mode = int(mode)
    rate = float(rate)
    if mode == 5:
        return abs(rate) / 100.0 / 365.0 * 1e4
    if mode == 1:
        if price is None or point is None or float(price) <= 0:
            raise ValueError("Sin datos: mode 1 exige price y point")
        return abs(rate) * float(point) / float(price) * 1e4
    raise ValueError("Sin datos: swap_mode no soportado")


def nights(entry_date: date | datetime | str, rollover3days: int = 5) -> int:
    """3 si la noche cruza el día triple (convención MT5 0=domingo).

    Recibe una fecha, no un weekday. La conversión desde la convención de
    Python (0=lunes … 6=domingo) se hace aquí.
    """

    if isinstance(entry_date, int):
        raise TypeError("nights() recibe una fecha, no un weekday")
    if isinstance(entry_date, str):
        entry_date = date.fromisoformat(entry_date)
    mt5_weekday = (int(entry_date.weekday()) + 1) % 7
    return 3 if mt5_weekday == int(rollover3days) else 1


__all__ = ["nights", "swap_bps_per_night"]
