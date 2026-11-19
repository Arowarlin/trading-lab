"""Universo normalizado CFD / Futures con alias y exposición equivalente.

* Un mismo instrumento tiene nombres distintos según la firma o el bróker
  (``US100.cash``, ``NAS100``, ``USTEC``...). Todos se resuelven a un id
  canónico; nunca se asume que dos nombres distintos son dos mercados.
* CFD y futuros **no se mezclan**: ``US100`` (CFD) y ``NQ`` (futuro) son
  instrumentos distintos con especificaciones y costes propios, pero comparten
  el *subyacente* ``NASDAQ100``. El gestor de riesgo global agrega por
  subyacente para ver la exposición real.
* Las especificaciones de futuros se toman de ``tradinglab.instruments``
  (catálogo existente). ``SI`` no existía y se declara aquí sin tocar ese módulo.
* Las especificaciones de CFD (tamaño de contrato, valor del tick) dependen del
  bróker: se leen de MT5 (``symbol_info``) y aquí solo queda ``None`` si no se
  conocen. No se inventan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..instruments import InstrumentError, get_instrument
from .models import CfdCategory, FuturesCategory, Market

ACCEPTED_SOURCE_FUTURES = "CME Group · especificaciones de contrato (catálogo tradinglab.instruments)"


@dataclass(frozen=True)
class CanonicalInstrument:
    id: str
    market: Market
    category: str
    underlying: str
    description: str
    aliases: tuple[str, ...] = ()
    # Futuros: multiplicador USD por punto, tick y valor del tick (fuente CME).
    multiplier: float | None = None
    tick_size: float | None = None
    tick_value: float | None = None
    exchange: str | None = None
    # CFD: tamaño de contrato si el catálogo existente lo tiene; si no, None.
    contract_size: float | None = None
    spec_source: str = ""
    currencies: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "market": self.market.value,
            "category": self.category,
            "underlying": self.underlying,
            "description": self.description,
            "aliases": list(self.aliases),
            "multiplier": self.multiplier,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "exchange": self.exchange,
            "contract_size": self.contract_size,
            "spec_source": self.spec_source or "Sin datos: leer del bróker (MT5 symbol_info)",
        }


def _fx(pair: str, *aliases: str) -> CanonicalInstrument:
    contract = None
    try:
        contract = get_instrument(pair).contract_size
    except InstrumentError:
        contract = None
    return CanonicalInstrument(
        id=pair,
        market=Market.CFD,
        category=CfdCategory.FOREX.value,
        underlying=f"FX:{pair}",
        description=f"Forex {pair[:3]}/{pair[3:]}",
        aliases=(pair, *aliases),
        contract_size=contract,
        spec_source="catálogo tradinglab.instruments; confirmar con MT5" if contract else "",
        currencies=(pair[:3], pair[3:]),
    )


def _cfd_index(cid: str, underlying: str, desc: str, *aliases: str) -> CanonicalInstrument:
    return CanonicalInstrument(
        id=cid,
        market=Market.CFD,
        category=CfdCategory.INDEX.value,
        underlying=underlying,
        description=desc,
        aliases=(cid, *aliases),
    )


def _future(sym: str, underlying: str, desc: str, category: FuturesCategory, exchange: str,
            *, multiplier: float | None = None, tick: float | None = None,
            tick_value: float | None = None) -> CanonicalInstrument:
    if multiplier is None:
        spec = get_instrument(sym)
        multiplier, tick, tick_value = spec.contract_size, spec.tick_size, spec.tick_value
    return CanonicalInstrument(
        id=sym,
        market=Market.FUTURES,
        category=category.value,
        underlying=underlying,
        description=desc,
        aliases=(sym,),
        multiplier=multiplier,
        tick_size=tick,
        tick_value=tick_value,
        exchange=exchange,
        spec_source=ACCEPTED_SOURCE_FUTURES,
    )


_CATALOG: list[CanonicalInstrument] = [
    # --- CFD Forex
    _fx("EURUSD"), _fx("GBPUSD"), _fx("USDJPY"), _fx("AUDUSD"), _fx("USDCAD"),
    _fx("USDCHF"), _fx("NZDUSD"), _fx("EURJPY"), _fx("GBPJPY"),
    # --- CFD Índices
    _cfd_index("US100", "NASDAQ100", "Nasdaq 100 CFD", "US100.cash", "NAS100", "USTEC", "NDX100", "NAS100.cash"),
    _cfd_index("US500", "SP500", "S&P 500 CFD", "US500.cash", "SPX500", "SP500", "US500"),
    _cfd_index("US30", "DOW30", "Dow Jones 30 CFD", "US30.cash", "DJ30", "WS30", "DOW30"),
    _cfd_index("US2000", "RUSSELL2000", "Russell 2000 CFD", "US2000.cash", "RUSSELL2000", "US2000"),
    _cfd_index("GER40", "DAX40", "DAX 40 CFD", "GER40.cash", "DAX40", "DE40", "GER30"),
    _cfd_index("UK100", "FTSE100", "FTSE 100 CFD", "UK100.cash", "FTSE100"),
    _cfd_index("JP225", "NIKKEI225", "Nikkei 225 CFD", "JP225.cash", "JPN225", "NIKKEI225"),
    # --- CFD Metales
    CanonicalInstrument(
        id="XAUUSD", market=Market.CFD, category=CfdCategory.METAL.value, underlying="GOLD",
        description="Oro spot CFD", aliases=("XAUUSD", "GOLD", "XAUUSD.a"),
        contract_size=get_instrument("XAUUSD").contract_size,
        spec_source="catálogo tradinglab.instruments; confirmar con MT5", currencies=("XAU", "USD"),
    ),
    CanonicalInstrument(
        id="XAGUSD", market=Market.CFD, category=CfdCategory.METAL.value, underlying="SILVER",
        description="Plata spot CFD", aliases=("XAGUSD", "SILVER"),
        contract_size=get_instrument("XAGUSD").contract_size,
        spec_source="catálogo tradinglab.instruments; confirmar con MT5", currencies=("XAG", "USD"),
    ),
    # --- Futuros índices (CME / CBOT)
    _future("NQ", "NASDAQ100", "E-mini Nasdaq-100", FuturesCategory.INDEX, "CME"),
    _future("MNQ", "NASDAQ100", "Micro E-mini Nasdaq-100", FuturesCategory.INDEX, "CME"),
    _future("ES", "SP500", "E-mini S&P 500", FuturesCategory.INDEX, "CME"),
    _future("MES", "SP500", "Micro E-mini S&P 500", FuturesCategory.INDEX, "CME"),
    _future("YM", "DOW30", "E-mini Dow ($5)", FuturesCategory.INDEX, "CBOT"),
    _future("MYM", "DOW30", "Micro E-mini Dow", FuturesCategory.INDEX, "CBOT"),
    _future("RTY", "RUSSELL2000", "E-mini Russell 2000", FuturesCategory.INDEX, "CME"),
    _future("M2K", "RUSSELL2000", "Micro E-mini Russell 2000", FuturesCategory.INDEX, "CME"),
    # --- Futuros metales (COMEX)
    _future("GC", "GOLD", "Gold Futures (100 oz)", FuturesCategory.METAL, "COMEX"),
    _future("MGC", "GOLD", "Micro Gold Futures (10 oz)", FuturesCategory.METAL, "COMEX"),
    _future("SI", "SILVER", "Silver Futures (5.000 oz)", FuturesCategory.METAL, "COMEX",
            multiplier=5_000, tick=0.005, tick_value=25.0),
]

CATALOG: dict[str, CanonicalInstrument] = {item.id: item for item in _CATALOG}
_ALIASES: dict[str, str] = {
    alias.upper(): item.id for item in _CATALOG for alias in item.aliases
}

#: Clases de activo que el Prop Fund nunca opera (acciones y ETF).
EXCLUDED_ASSET_CLASSES = frozenset({"equity", "etf", "stock"})


def resolve(symbol: str) -> CanonicalInstrument:
    """Alias del bróker → instrumento canónico. Lanza KeyError si no está en el universo."""
    key = symbol.strip().upper()
    if key in _ALIASES:
        return CATALOG[_ALIASES[key]]
    # Sufijos de bróker (EURUSD.a, EURUSDm, US100.cash.r)
    for alias, cid in sorted(_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if key.startswith(alias) and CATALOG[cid].market is Market.CFD:
            return CATALOG[cid]
    # Contratos con vencimiento: NQZ6, MNQH27, GCZ2026
    for cid, item in sorted(CATALOG.items(), key=lambda kv: -len(kv[0])):
        if item.market is Market.FUTURES and key.startswith(cid):
            rest = key[len(cid):]
            if rest and rest[0] in "FGHJKMNQUVXZ" and rest[1:].isdigit():
                return item
    raise KeyError(f"{symbol}: fuera del universo Prop Fund (CFD Forex/Índices/Metales o Futures)")


def is_in_universe(symbol: str) -> bool:
    try:
        resolve(symbol)
    except KeyError:
        return False
    return True


def universe(market: Market | None = None) -> list[CanonicalInstrument]:
    return [item for item in _CATALOG if market is None or item.market is market]


def same_underlying(a: str, b: str) -> bool:
    return resolve(a).underlying == resolve(b).underlying


def micro_equivalent(symbol: str) -> float | None:
    """Cuántos contratos micro equivalen a 1 contrato de este futuro (NQ → 10 MNQ)."""
    item = resolve(symbol)
    if item.market is not Market.FUTURES or item.multiplier is None:
        return None
    smallest = min(
        (c.multiplier for c in CATALOG.values()
         if c.market is Market.FUTURES and c.underlying == item.underlying and c.multiplier),
        default=item.multiplier,
    )
    return item.multiplier / smallest


def notional_usd(symbol: str, quantity: float, price: float,
                 *, contract_size: float | None = None) -> float | None:
    """Exposición nocional en USD (signo = dirección). None si falta la especificación.

    * Futuros: ``cantidad × multiplicador × precio``.
    * CFD: ``lotes × tamaño_contrato × precio`` (convertido a USD si la cotizada no es USD).
      ``contract_size`` debe venir del bróker; si no, se usa el catálogo y, si
      tampoco existe, se devuelve None (el riesgo global lo marca "Sin datos").
    """
    item = resolve(symbol)
    if item.market is Market.FUTURES:
        if item.multiplier is None:
            return None
        return quantity * item.multiplier * price
    size = contract_size if contract_size is not None else item.contract_size
    if size is None:
        return None
    if item.category == CfdCategory.FOREX.value:
        base, quote = item.currencies
        if base == "USD":
            return quantity * size  # nocional ya en USD
        if quote == "USD":
            return quantity * size * price
        return None  # cruces: requiere el tipo USD de la base
    return quantity * size * price


__all__ = [
    "CATALOG",
    "CanonicalInstrument",
    "EXCLUDED_ASSET_CLASSES",
    "is_in_universe",
    "micro_equivalent",
    "notional_usd",
    "resolve",
    "same_underlying",
    "universe",
]
