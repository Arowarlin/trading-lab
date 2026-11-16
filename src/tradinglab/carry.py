"""Swap/financiación nocturna para los backtests.

Los valores salen de `mt5.symbol_info` o de un override verificado en
`config/costs.yaml`. Si faltan, el modelo queda **provisional** y el motor no
inventa una cifra: aplica carry 0 y lo marca en las métricas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .intraday_costs import AssetCost
from .swap_rates import annual_pct_from_points, dff_on, historical_daily_rate


@dataclass(frozen=True)
class CostModel:
    swap_long: float | None = None
    swap_short: float | None = None
    swap_unit: str = "percent_annual"
    triple_weekday: int = 2
    point: float = 0.01
    contract_size: float = 1.0
    source: str = "Sin datos"
    swap_annual_pct_long: float | None = None
    swap_annual_pct_short: float | None = None
    price_at_read: float | None = None
    read_date: date | None = None
    dff: object | None = None
    markup_long: float | None = None
    markup_short: float | None = None
    fixed_days: int = 30

    @property
    def provisional(self) -> bool:
        if self.swap_long is None or self.swap_short is None:
            return True
        if self.read_date is not None:
            return (
                self.dff is None
                or self.markup_long is None
                or self.markup_short is None
            )
        return False

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
        fixed = (
            self.read_date is not None
            and abs((day - self.read_date).days) <= max(0, int(self.fixed_days))
        )
        if fixed or self.read_date is None:
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
        else:
            annual_pct = (
                self.swap_annual_pct_long
                if side == "long"
                else self.swap_annual_pct_short
            )
            markup = self.markup_long if side == "long" else self.markup_short
            rate = historical_daily_rate(
                dff_on(self.dff, self.read_date) if self.read_date else None,
                markup,
                day,
                self.dff,
            )
            if annual_pct is None or rate is None:
                return 0.0
            cash = float(notional) * rate / 365.0
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


def cost_model_from_asset(
    asset: AssetCost, *, point: float = 0.01, dff=None
) -> CostModel:
    """Convierte los campos de swap de `asset_costs` en un `CostModel`."""
    read_date = None
    if asset.swap_read_at:
        try:
            read_date = date.fromisoformat(str(asset.swap_read_at)[:10])
        except ValueError:
            read_date = None
    point_value = float(asset.swap_point or point or 0.01)
    contract = float(asset.contract_size or 1.0)
    annual_long = asset.swap_annual_pct_long
    annual_short = asset.swap_annual_pct_short
    if annual_long is None and asset.swap_long is not None and asset.swap_price_at_read:
        annual_long = annual_pct_from_points(
            asset.swap_long,
            point=point_value,
            contract_size=contract,
            price=float(asset.swap_price_at_read),
        )
    if annual_short is None and asset.swap_short is not None and asset.swap_price_at_read:
        annual_short = annual_pct_from_points(
            asset.swap_short,
            point=point_value,
            contract_size=contract,
            price=float(asset.swap_price_at_read),
        )
    dff_today = dff_on(dff, read_date) if read_date else None
    return CostModel(
        swap_long=asset.swap_long,
        swap_short=asset.swap_short,
        swap_unit=asset.swap_unit,
        triple_weekday=asset.swap_triple_weekday,
        point=point_value,
        contract_size=contract,
        source=asset.swap_source,
        swap_annual_pct_long=annual_long,
        swap_annual_pct_short=annual_short,
        price_at_read=asset.swap_price_at_read,
        read_date=read_date,
        dff=dff,
        markup_long=(
            annual_long - dff_today
            if annual_long is not None and dff_today is not None
            else None
        ),
        markup_short=(
            annual_short - dff_today
            if annual_short is not None and dff_today is not None
            else None
        ),
    )


__all__ = ["CostModel", "cost_model_from_asset"]
