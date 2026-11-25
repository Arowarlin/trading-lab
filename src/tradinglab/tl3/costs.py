"""D1 · Conversión única de swap y noches.

Incluye el modelo de coste **v2** para una operación completa: spread,
slippage y comisión por lado, más el swap de las noches que cruce. El coste se
expresa en R dividiendo por la distancia del stop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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


@dataclass(frozen=True)
class CostV2:
    """Componentes del coste de ida y vuelta, en bps del precio de entrada.

    ``spread_bps`` es el cruce de spread de ida y vuelta (se aplica una vez).
    ``slippage_bps`` y ``commission_bps`` son **por lado** y se duplican.
    ``swap_bps`` es el coste de las noches, ya sumado.
    """

    spread_bps: float
    slippage_bps: float
    commission_bps: float
    swap_bps: float = 0.0

    def __post_init__(self) -> None:
        for name in ("spread_bps", "slippage_bps", "commission_bps", "swap_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Sin datos: {name} inválido ({value!r})")
            object.__setattr__(self, name, value)

    @property
    def total_bps(self) -> float:
        return (
            self.spread_bps
            + 2.0 * self.slippage_bps
            + 2.0 * self.commission_bps
            + self.swap_bps
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "spread_bps": self.spread_bps,
            "slippage_bps": self.slippage_bps,
            "commission_bps": self.commission_bps,
            "swap_bps": self.swap_bps,
            "total_bps": self.total_bps,
        }


def cost_r_v2(
    entry_price: float,
    stop_distance: float,
    *,
    spread_bps: float,
    slippage_bps: float,
    commission_bps: float,
    swap_bps: float = 0.0,
) -> dict:
    """Coste de la operación en R con el modelo v2.

    ``stop_distance`` es la distancia en precio entre la entrada y el stop
    (siempre positiva). El resultado incluye el desglose y el coste en R.
    Lanza ``ValueError`` si falta un dato: nunca devuelve un 0 silencioso.
    """

    entry = float(entry_price)
    risk = float(stop_distance)
    if not (entry > 0):
        raise ValueError(f"Sin datos: entry_price inválido ({entry_price!r})")
    if not (risk > 0):
        raise ValueError(f"Sin datos: stop_distance inválido ({stop_distance!r})")
    cost = CostV2(
        spread_bps=float(spread_bps),
        slippage_bps=float(slippage_bps),
        commission_bps=float(commission_bps),
        swap_bps=float(swap_bps),
    )
    cost_price = cost.total_bps / 10_000.0 * entry
    return {
        **cost.as_dict(),
        "entry_price": entry,
        "stop_distance": risk,
        "cost_price": cost_price,
        "cost_r": cost_price / risk,
    }


__all__ = [
    "CostV2",
    "cost_r_v2",
    "nights",
    "swap_bps_per_night",
]
