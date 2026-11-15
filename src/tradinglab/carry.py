"""Swap/financiación nocturna para los backtests.

Los valores salen de `mt5.symbol_info` o de un override verificado en
`config/costs.yaml`. Si faltan, el modelo queda **provisional** y el motor no
inventa una cifra: aplica carry 0 y lo marca en las métricas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .intraday_costs import AssetCost


@dataclass(frozen=True)
class CostModel:
    swap_long: float | None = None
    swap_short: float | None = None
    swap_unit: str = "percent_annual"
    triple_weekday: int = 2
    point: float = 0.01
    contract_size: float = 1.0
    source: str = "Sin datos"

    @property
    def provisional(self) -> bool:
        return self.swap_long is None or self.swap_short is None

    @property
    def status(self) -> str:
        return "costes provisionales" if self.provisional else "swap incluido"

    def daily_cash(
        self,
        side: str,
        *,
        notional: float,
        shares: float,
        day: date,
    ) -> float:
        """Carry de una noche; negativo = coste, positivo = crédito."""
        if self.provisional:
            return 0.0
        value = self.swap_long if side == "long" else self.swap_short
        if value is None:
            return 0.0
        unit = str(self.swap_unit).strip().lower()
        if unit in {"percent_annual", "percent", "annual_percent"}:
            cash = float(notional) * float(value) / 100.0 / 365.0
        elif unit in {"points", "point"}:
            cash = (
                float(value)
                * float(self.point)
                * float(self.contract_size)
                * abs(float(shares))
            )
        else:
            raise ValueError(f"unidad de swap desconocida: {self.swap_unit!r}")
        multiplier = 3.0 if int(day.weekday()) == int(self.triple_weekday) else 1.0
        return cash * multiplier

    def carry_for_nights(
        self,
        side: str,
        *,
        notional: float,
        shares: float,
        start_day: date,
        end_day: date,
    ) -> float:
        """Suma las noches entre `start_day` (incluido) y `end_day` (excluido)."""
        if end_day <= start_day:
            return 0.0
        total = 0.0
        current = start_day
        while current < end_day:
            # Los brókers no hacen rollover sábado/domingo: el triple del día
            # configurado ya cubre el fin de semana.
            if current.weekday() < 5:
                total += self.daily_cash(
                    side,
                    notional=notional,
                    shares=shares,
                    day=current,
                )
            current += timedelta(days=1)
        return total


def cost_model_from_asset(asset: AssetCost, *, point: float = 0.01) -> CostModel:
    """Convierte los campos de swap de `asset_costs` en un `CostModel`."""
    return CostModel(
        swap_long=asset.swap_long,
        swap_short=asset.swap_short,
        swap_unit=asset.swap_unit,
        triple_weekday=asset.swap_triple_weekday,
        point=point,
        contract_size=float(asset.contract_size or 1.0),
        source=asset.swap_source,
    )


__all__ = ["CostModel", "cost_model_from_asset"]
