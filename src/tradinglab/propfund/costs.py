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

import yaml

from ..config import ROOT
from .instruments import CanonicalInstrument, resolve
from .models import Market

LEGACY_COSTS_PATH = ROOT / "config" / "costs.yaml"
PROPFUND_COSTS_PATH = ROOT / "config" / "propfund" / "costs.yaml"

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
        swap = profile.swap_long_per_lot if side == "long" else profile.swap_short_per_lot
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
    "broker_symbol",
    "estimate_cfd",
    "estimate_futures",
    "load_profile",
]
