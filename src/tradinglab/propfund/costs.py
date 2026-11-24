"""Motores de coste independientes: CFD y Futures.

CFD     → clave ``empresa + programa + cuenta + plataforma + bróker + símbolo``.
          Spread medido (mediana / p75 por hora), comisión por lote o % del
          volumen, swaps y slippage.
Futures → comisión por lado, exchange/clearing/NFA, slippage en ticks.

Reglas:

* Nunca un spread fijo global. El spread sale de la medición de ticks del bróker
  (tabla ``broker_spreads``, ``tradinglab.broker_costs``) o del perfil de la
  cuenta con su fuente y fecha.
* Si falta un componente, la estimación queda ``complete=False`` y enumera lo
  que falta. El router rechaza la operación salvo que el perfil lo permita de
  forma explícita con un valor conservador declarado.
* El modelo de spreads de MT5 nunca se aplica a futuros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from ..config import ROOT
from .instruments import CanonicalInstrument, resolve
from .models import Market

LEGACY_COSTS_PATH = ROOT / "config" / "costs.yaml"
PROPFUND_COSTS_PATH = ROOT / "config" / "propfund" / "costs.yaml"
SWAP_PATH = ROOT / "config" / "propfund" / "swap.yaml"

# Nombre del símbolo en config/costs.yaml (tabla FTMO verificada) por id canónico.
_FTMO_COST_KEYS = {
    "US100": "US100.CASH", "US500": "US500.CASH", "US30": "US30.CASH",
    "US2000": "US2000.CASH", "GER40": "GER40.CASH", "UK100": "UK100.CASH",
    "JP225": "JP225.CASH",
}


@dataclass
class CostProfile:
    account: str
    symbol: str
    market: Market
    commission_type: str | None = None          # per_lot_usd | percent_of_volume | zero | per_contract_usd
    commission_value: float | None = None
    commission_side: str = "per_side"           # per_side | round_turn
    commission_source: str | None = None
    spread_price: float | None = None           # mediana, en unidades de precio
    spread_p75_price: float | None = None
    slippage_price: float | None = None         # CFD: por lado, en precio
    slippage_ticks: float | None = None         # Futures: por lado, en ticks
    exchange_fee_per_side: float | None = None
    clearing_fee_per_side: float | None = None
    nfa_fee_per_side: float | None = None
    swap_long_per_lot: float | None = None
    swap_short_per_lot: float | None = None
    # Datos MT5 en crudo: el modo decide la conversion (points, interest...).
    swap_long: float | None = None
    swap_short: float | None = None
    swap_mode: int | None = None
    swap_rollover3days: int | None = None
    swap_rollover_hour: str | None = None
    swap_rollover_tz: str | None = None
    point: float | None = None
    swap_source: str | None = None
    swap_measured_at: str | None = None
    source: str = ""
    verified: bool = False
    measured_at: str | None = None

    def as_dict(self) -> dict:
        return {k: getattr(self, k) if k != "market" else self.market.value for k in self.__dataclass_fields__}


@dataclass
class CostEstimate:
    total_usd: float
    components: dict[str, float]
    missing: list[str] = field(default_factory=list)
    cost_r: float | None = None
    source: str = ""

    @property
    def complete(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict:
        return {
            "total_usd": round(self.total_usd, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "missing": list(self.missing),
            "complete": self.complete,
            "cost_r": None if self.cost_r is None else round(self.cost_r, 4),
            "source": self.source,
        }


def rollover_units(
    entry_time,
    exit_time,
    *,
    tz: str = "America/New_York",
    hour: int = 17,
    triple_day: int | None = None,
) -> int:
    """Noches de swap entre entrada y salida, con el triple del bróker.

    Cuenta los cierres diarios (por defecto 17:00 NY, que es 00:00 del servidor)
    estrictamente posteriores a la entrada y hasta la salida. Solo lunes a
    viernes; el día triple del servidor se aplica al cierre NY anterior
    (servidor 00:00 = NY 17:00 del día anterior). El fin de semana queda
    cubierto por el triple, como en el rollover estándar.
    """

    start = pd.Timestamp(entry_time)
    end = pd.Timestamp(exit_time)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("entry_time/exit_time deben tener zona horaria")
    if end <= start:
        return 0
    local_start = start.tz_convert(tz)
    local_end = end.tz_convert(tz)
    units = 0
    day = local_start.normalize()
    last = local_end.normalize()
    while day <= last:
        boundary = day + pd.Timedelta(hours=int(hour))
        if start < boundary <= end and boundary.weekday() < 5:
            # 17:00 NY + 7 h = 00:00 del servidor del día siguiente. MT5
            # enumera 0=domingo; Python 0=lunes: (weekday + 2) % 7.
            server_day = (boundary.weekday() + 2) % 7
            units += 3 if triple_day is not None and server_day == int(triple_day) else 1
        day += pd.Timedelta(days=1)
    return int(units)


@dataclass(frozen=True)
class SwapSpec:
    """Swap medido de MT5 y su conversión a R por operación."""

    long: float
    short: float
    mode: int
    triple_day: int | None = None
    point: float | None = None
    rollover_hour: int = 17
    rollover_tz: str = "America/New_York"

    @classmethod
    def from_profile(cls, profile: CostProfile) -> "SwapSpec | None":
        if (
            profile.swap_mode is None
            or profile.swap_long is None
            or profile.swap_short is None
        ):
            return None
        hour = 17
        raw_hour = str(profile.swap_rollover_hour or "17:00")
        try:
            hour = int(raw_hour.split(":")[0])
        except (TypeError, ValueError):
            hour = 17
        return cls(
            long=float(profile.swap_long),
            short=float(profile.swap_short),
            mode=int(profile.swap_mode),
            triple_day=(
                None
                if profile.swap_rollover3days is None
                else int(profile.swap_rollover3days)
            ),
            point=None if profile.point is None else float(profile.point),
            rollover_hour=hour,
            rollover_tz=str(profile.swap_rollover_tz or "America/New_York"),
        )

    def units(self, entry_time, exit_time) -> int:
        return rollover_units(
            entry_time,
            exit_time,
            tz=self.rollover_tz,
            hour=self.rollover_hour,
            triple_day=self.triple_day,
        )

    def total_usd(
        self,
        *,
        side: str,
        price: float,
        contract_size: float,
        lots: float,
        nights: int,
    ) -> float:
        """Swap en USD (negativo = coste) para ``nights`` noches ponderadas."""

        count = int(nights)
        if count == 0:
            return 0.0
        raw = self.long if str(side).lower() == "long" else self.short
        if self.mode == 0:
            return 0.0
        if self.mode == 1:
            if self.point is None:
                raise ValueError("swap mode points sin point")
            return raw * self.point * contract_size * lots * count
        if self.mode == 5:
            return price * contract_size * lots * (raw / 100.0 / 360.0) * count
        raise ValueError(f"swap mode {self.mode} no soportado")

    def per_night_r(
        self,
        *,
        side: str,
        entry_price: float,
        risk_price: float,
        allow_credit: bool = True,
    ) -> float:
        risk = float(risk_price)
        if not (risk > 0.0):
            raise ValueError("risk_price debe ser > 0")
        raw = self.long if str(side).lower() == "long" else self.short
        if self.mode == 0:
            return 0.0
        if self.mode == 1:
            if self.point is None:
                raise ValueError("swap mode points sin point")
            value = float(raw * self.point / risk)
        elif self.mode == 5:
            value = float(entry_price * (raw / 100.0 / 360.0) / risk)
        else:
            raise ValueError(f"swap mode {self.mode} no soportado")
        if not allow_credit and value > 0.0:
            return 0.0
        return value

    def r(
        self,
        *,
        side: str,
        entry_price: float,
        risk_price: float,
        entry_time,
        exit_time,
        allow_credit: bool = True,
    ) -> float:
        """Swap en R (positivo = crédito, negativo = coste), nocturno."""

        units = self.units(entry_time, exit_time)
        if units == 0:
            return 0.0
        return float(
            self.per_night_r(
                side=side,
                entry_price=entry_price,
                risk_price=risk_price,
                allow_credit=allow_credit,
            )
            * units
        )


def _yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def broker_symbol(symbol: str) -> str:
    """Nombre del símbolo en MT5 para un id canónico (US100 → US100.CASH)."""
    item = resolve(symbol)
    return _FTMO_COST_KEYS.get(item.id, item.id)


def _legacy_ftmo_entry(item: CanonicalInstrument, path: Path = LEGACY_COSTS_PATH) -> dict | None:
    """Comisión verificada de FTMO desde config/costs.yaml (solo lectura)."""
    assets = (_yaml(path).get("assets") or {})
    key = broker_symbol(item.id)
    entry = assets.get(key) or assets.get(key.upper())
    if not entry or not entry.get("verified"):
        return None
    return entry


def load_profile(account: str, symbol: str, *, firm: str | None = None,
                 path: Path = PROPFUND_COSTS_PATH,
                 legacy_path: Path = LEGACY_COSTS_PATH) -> CostProfile:
    """Perfil de costes de una cuenta y un símbolo. Lo que falte queda en None."""
    item = resolve(symbol)
    profile = CostProfile(account=account, symbol=item.id, market=item.market)
    accounts = (_yaml(path).get("accounts") or {})
    entry = ((accounts.get(account) or {}).get("symbols") or {}).get(item.id) or {}

    if firm == "ftmo" and item.market is Market.CFD:
        legacy = _legacy_ftmo_entry(item, legacy_path)
        if legacy:
            ctype = legacy.get("commission_type")
            profile.commission_type = ctype
            if ctype == "per_lot_usd":
                profile.commission_value = float(legacy.get("commission_per_lot_usd") or 0)
            elif ctype == "percent_of_volume":
                profile.commission_value = float(legacy.get("commission_percent_per_side") or 0)
            elif ctype == "zero":
                profile.commission_value = 0.0
            profile.commission_side = legacy.get("commission_side", "per_side")
            profile.source = f"config/costs.yaml · {legacy.get('source', '')}".strip()
            profile.verified = True

    for key, value in entry.items():
        if key in profile.__dataclass_fields__ and value is not None:
            setattr(profile, key, value)

    swap_entry = (
        ((_yaml(SWAP_PATH).get("accounts") or {}).get(account) or {})
        .get("symbols", {})
        .get(item.id)
        or {}
    )
    for key in (
        "swap_long",
        "swap_short",
        "swap_mode",
        "swap_rollover3days",
        "swap_rollover_hour",
        "swap_rollover_tz",
        "point",
        "swap_source",
        "swap_measured_at",
    ):
        value = swap_entry.get(key)
        if value is not None:
            setattr(profile, key, value)
    return profile


def _sides(profile: CostProfile) -> float:
    return 1.0 if profile.commission_side == "round_turn" else 2.0


def estimate_cfd(profile: CostProfile, *, lots: float, price: float,
                 contract_size: float | None, risk_usd: float | None = None,
                 nights: int = 0, side: str = "long", use_p75: bool = True) -> CostEstimate:
    """Coste total ida y vuelta de una operación CFD en USD (cotizada en USD)."""
    if profile.market is not Market.CFD:
        raise ValueError("estimate_cfd solo admite CFD; usa estimate_futures para futuros")
    missing: list[str] = []
    comp: dict[str, float] = {}
    size = contract_size
    if size is None:
        missing.append("contract_size")
        size = 0.0

    spread = profile.spread_p75_price if use_p75 and profile.spread_p75_price is not None else profile.spread_price
    if spread is None:
        missing.append("spread")
    else:
        comp["spread"] = spread * size * lots

    if profile.commission_type is None:
        missing.append("commission")
    elif profile.commission_type == "zero":
        comp["commission"] = 0.0
    elif profile.commission_type == "per_lot_usd":
        comp["commission"] = float(profile.commission_value or 0) * lots * _sides(profile)
    elif profile.commission_type == "percent_of_volume":
        volume = lots * size * price
        comp["commission"] = volume * float(profile.commission_value or 0) / 100.0 * _sides(profile)
    else:
        missing.append(f"commission_type:{profile.commission_type}")

    if profile.slippage_price is None:
        missing.append("slippage")
    else:
        comp["slippage"] = profile.slippage_price * size * lots * 2

    if nights:
        spec = SwapSpec.from_profile(profile)
        if spec is not None:
            try:
                comp["swap"] = spec.total_usd(
                    side=side,
                    price=price,
                    contract_size=size,
                    lots=lots,
                    nights=int(nights),
                )
            except ValueError as exc:
                missing.append(f"swap:{exc}")
        else:
            swap = (
                profile.swap_long_per_lot
                if side == "long"
                else profile.swap_short_per_lot
            )
            if swap is None:
                missing.append("swap")
            else:
                comp["swap"] = -float(swap) * lots * nights  # swap negativo = coste

    total = sum(comp.values())
    cost_r = (total / risk_usd) if risk_usd else None
    return CostEstimate(total, comp, missing, cost_r, profile.source)


def estimate_futures(profile: CostProfile, *, contracts: int, risk_usd: float | None = None) -> CostEstimate:
    """Coste ida y vuelta de una operación de futuros en USD."""
    if profile.market is not Market.FUTURES:
        raise ValueError("estimate_futures solo admite futuros (no usar spreads MT5)")
    item = resolve(profile.symbol)
    missing: list[str] = []
    comp: dict[str, float] = {}
    sides = 2.0
    if profile.commission_value is None:
        missing.append("commission")
    else:
        per = float(profile.commission_value)
        comp["commission"] = per * contracts * (1.0 if profile.commission_side == "round_turn" else sides)
    for name in ("exchange_fee_per_side", "clearing_fee_per_side", "nfa_fee_per_side"):
        value = getattr(profile, name)
        if value is None:
            missing.append(name)
        else:
            comp[name.replace("_per_side", "")] = float(value) * contracts * sides
    if profile.slippage_ticks is None:
        missing.append("slippage")
    elif item.tick_value is not None:
        comp["slippage"] = float(profile.slippage_ticks) * item.tick_value * contracts * sides
    total = sum(comp.values())
    cost_r = (total / risk_usd) if risk_usd else None
    return CostEstimate(total, comp, missing, cost_r, profile.source)


__all__ = [
    "CostEstimate",
    "CostProfile",
    "SwapSpec",
    "broker_symbol",
    "estimate_cfd",
    "estimate_futures",
    "load_profile",
    "rollover_units",
]
