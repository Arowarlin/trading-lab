from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import floor
from typing import Literal

AssetClass = Literal["equity", "forex", "futures", "cfd"]


class InstrumentError(ValueError):
    pass


@dataclass(frozen=True)
class Instrument:
    """Especificación de un instrumento.

    `tick_value` es el valor en USD de un tick por 1 contrato/lote.
    En forex es variable (depende del tipo de cambio), así que se deja en None
    y se calcula con `tick_value_usd()`.
    """

    symbol: str
    asset_class: AssetClass
    quote_ccy: str = "USD"
    tick_size: float = 0.01
    contract_size: float = 1.0
    tick_value: float | None = None
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0
    session: str = "24/5"
    session_tz: str = "UTC"
    data_source: str = ""
    series_id: str = ""
    spread: float | None = None
    spread_note: str = ""
    notes: str = ""

    # ------------------------------------------------------------------ básicos

    @property
    def is_fx(self) -> bool:
        return self.asset_class == "forex"

    @property
    def is_futures(self) -> bool:
        return self.asset_class == "futures"

    def pip_size(self) -> float:
        """Tamaño de 1 pip. En FX siempre son 10 ticks (0.0001 o 0.01 en JPY)."""
        if not self.is_fx:
            raise InstrumentError(f"{self.symbol} no es forex: no tiene pips")
        return self.tick_size * 10.0

    def value_per_price_unit(self, price: float | None = None, quote_rate: float | None = None) -> float:
        """USD por cada 1.00 de movimiento del precio, por contrato/lote.

        `quote_rate` = unidades de la divisa cotizada por 1 USD
        (EURUSD -> 1.0, USDJPY -> 150.0, EURJPY -> 150.0).
        """
        if self.tick_value is not None:
            # El bróker manda: trade_tick_value ya viene en USD por lote.
            return self.tick_value / self.tick_size
        if self.is_futures:
            raise InstrumentError(f"{self.symbol}: falta tick_value")
        if self.asset_class == "equity":
            return 1.0

        rate = 1.0
        if self.quote_ccy != "USD":
            if quote_rate is None:
                raise InstrumentError(
                    f"{self.symbol}: necesito quote_rate (unidades de {self.quote_ccy} por 1 USD)"
                )
            if quote_rate <= 0:
                raise InstrumentError("quote_rate debe ser > 0")
            rate = 1.0 / quote_rate
        return self.contract_size * rate

    def tick_value_usd(
        self, price: float | None = None, quote_rate: float | None = None
    ) -> float:
        if self.tick_value is not None:
            return float(self.tick_value)
        return self.value_per_price_unit(price, quote_rate) * self.tick_size

    def notional_per_lot(self, price: float) -> float:
        """Valor nocional en USD de 1 contrato/lote."""
        if price <= 0:
            raise InstrumentError("price debe ser > 0")
        return self.contract_size * price

    def margin_required(self, lots: float, price: float, leverage: float = 100.0) -> float:
        if leverage <= 0:
            raise InstrumentError("leverage debe ser > 0")
        return abs(lots) * self.notional_per_lot(price) / leverage

    # ------------------------------------------------------------------- sizing

    def risk_per_lot(
        self,
        stop_distance: float,
        price: float | None = None,
        quote_rate: float | None = None,
    ) -> float:
        """Pérdida en USD por 1 lote si el precio recorre `stop_distance`."""
        if stop_distance <= 0:
            raise InstrumentError("stop_distance debe ser > 0")
        return stop_distance * self.value_per_price_unit(price, quote_rate)

    def lots_for_risk(
        self,
        risk_usd: float,
        stop_distance: float,
        *,
        price: float | None = None,
        quote_rate: float | None = None,
        cap_lots: float | None = None,
    ) -> float:
        """Tamaño en lotes que arriesga como máximo `risk_usd`.

        Redondea SIEMPRE hacia abajo al step del bróker: nunca arriesgar de más.
        Devuelve 0.0 si ni el lote mínimo cabe en el presupuesto.
        """
        if risk_usd <= 0:
            return 0.0
        per_lot = self.risk_per_lot(stop_distance, price, quote_rate)
        if per_lot <= 0:
            return 0.0

        raw = risk_usd / per_lot
        capped = min(raw, self.max_lot)
        if cap_lots is not None:
            capped = min(capped, cap_lots)
        lots = floor(capped / self.lot_step + 1e-9) * self.lot_step
        lots = round(lots, 8)
        if lots < self.min_lot - 1e-12:
            return 0.0
        return lots

    def round_lots(self, lots: float) -> float:
        """Normaliza un volumen al step del bróker (hacia abajo)."""
        if lots <= 0:
            return 0.0
        lots = min(lots, self.max_lot)
        rounded = floor(lots / self.lot_step + 1e-9) * self.lot_step
        rounded = round(rounded, 8)
        return 0.0 if rounded < self.min_lot - 1e-12 else rounded

    def describe(self) -> str:
        base = (
            f"{self.symbol} [{self.asset_class}] tick={self.tick_size:g} "
            f"contrato={self.contract_size:g} {self.quote_ccy}"
        )
        if self.tick_value is not None:
            base += f" tick_value=${self.tick_value:,.2f}"
        base += f" lote={self.min_lot:g}/{self.lot_step:g}/{self.max_lot:g}"
        base += f" fuente={self.data_source or 'sin datos'}"
        base += f" serie={self.series_id or self.symbol}"
        base += f" sesión={self.session} {self.session_tz}"
        if self.spread is not None:
            base += f" spread={self.spread:g}"
        elif self.spread_note:
            base += f" spread=Sin datos ({self.spread_note})"
        return base

    def tick_ratio(self, price: float | None = None, daily_vol: float | None = None) -> float | None:
        """`tick_size / (precio × volatilidad diaria)`: cuánto pesa un tick.

        Sin precio o sin volatilidad no se puede calcular: `None` (sin datos).
        """
        px = float(price or 0.0)
        vol = float(daily_vol or 0.0)
        if px <= 0 or vol <= 0:
            return None
        return float(self.tick_size) / (px * vol)

    def catalog_row(self) -> dict:
        row = asdict(self)
        row["pip_size"] = self.pip_size() if self.is_fx else None
        return row


# --------------------------------------------------------------------- registro

INSTRUMENTS: dict[str, Instrument] = {}


def register(instrument: Instrument) -> Instrument:
    INSTRUMENTS[instrument.symbol.upper()] = instrument
    return instrument


def get_instrument(symbol: str) -> Instrument:
    key = symbol.upper()
    if key in INSTRUMENTS:
        return INSTRUMENTS[key]
    # Sufijos de bróker: EURUSD.a, EURUSDm, EURUSD.pro
    for known, inst in INSTRUMENTS.items():
        if key.startswith(known):
            return replace(inst, symbol=symbol.upper())
    raise InstrumentError(
        f"Instrumento desconocido: {symbol}. Añádelo con `register()` o revisa el sufijo del bróker."
    )


def list_instruments(asset_class: str | None = None) -> list[Instrument]:
    items = sorted(INSTRUMENTS.values(), key=lambda i: (i.asset_class, i.symbol))
    if asset_class:
        items = [i for i in items if i.asset_class == asset_class]
    return items


def catalog(asset_class: str | None = None) -> list[dict]:
    """Catálogo serializable por clase, con fuente y horario."""
    return [item.catalog_row() for item in list_instruments(asset_class)]


def validate_universe(symbols: list[str]) -> bool:
    """Rechaza mezclar clases de activo en un mismo backtest."""
    if not symbols:
        raise InstrumentError("universo vacío")
    items = [get_instrument(symbol) for symbol in symbols]
    classes = {item.asset_class for item in items}
    if len(classes) > 1:
        detail = ", ".join(
            f"{item.symbol}={item.asset_class}" for item in items
        )
        raise InstrumentError(
            f"no mezclar clases de activo en un mismo backtest: {detail}"
        )
    series = [item.series_id or item.symbol for item in items]
    if len(series) != len(set(series)):
        raise InstrumentError(f"series duplicadas en el universo: {series}")
    return True


def validate_catalog() -> dict:
    """Valida que no haya huecos ni especificaciones imposibles."""
    errors: list[str] = []
    seen: set[str] = set()
    for item in INSTRUMENTS.values():
        if item.symbol in seen:
            errors.append(f"{item.symbol}: símbolo duplicado")
        seen.add(item.symbol)
        if item.asset_class not in {"equity", "forex", "futures", "cfd"}:
            errors.append(f"{item.symbol}: clase inválida {item.asset_class}")
        if not item.data_source:
            errors.append(f"{item.symbol}: falta data_source")
        if not item.session:
            errors.append(f"{item.symbol}: falta session")
        if not item.session_tz:
            errors.append(f"{item.symbol}: falta session_tz")
        if item.tick_size <= 0:
            errors.append(f"{item.symbol}: tick_size <= 0")
        if item.contract_size <= 0:
            errors.append(f"{item.symbol}: contract_size <= 0")
        if item.min_lot <= 0 or item.lot_step <= 0:
            errors.append(f"{item.symbol}: lote mínimo/step <= 0")
        if item.max_lot < item.min_lot:
            errors.append(f"{item.symbol}: max_lot < min_lot")
        if item.asset_class == "futures" and item.tick_value is None:
            errors.append(f"{item.symbol}: futuros sin tick_value")
        if item.asset_class == "cfd" and item.tick_value is None:
            # CFD puede usar tick_value del bróker; si falta, se marca.
            errors.append(f"{item.symbol}: CFD sin tick_value verificado")
    series = [item.series_id or item.symbol for item in INSTRUMENTS.values()]
    if len(series) != len(set(series)):
        errors.append("series_id duplicadas en el catálogo")
    classes = sorted({item.asset_class for item in INSTRUMENTS.values()})
    return {
        "ok": not errors,
        "count": len(INSTRUMENTS),
        "classes": classes,
        "errors": errors,
    }


# --- Forex -------------------------------------------------------------------
# 1 lote = 100.000 unidades de la divisa base.
for _sym, _quote, _tick in [
    ("EURUSD", "USD", 0.00001),
    ("GBPUSD", "USD", 0.00001),
    ("AUDUSD", "USD", 0.00001),
    ("NZDUSD", "USD", 0.00001),
    ("USDCAD", "CAD", 0.00001),
    ("USDCHF", "CHF", 0.00001),
    ("USDJPY", "JPY", 0.001),
    ("EURJPY", "JPY", 0.001),
    ("GBPJPY", "JPY", 0.001),
    ("AUDJPY", "JPY", 0.001),
    ("EURGBP", "GBP", 0.00001),
    ("EURCHF", "CHF", 0.00001),
]:
    register(
        Instrument(
            symbol=_sym,
            asset_class="forex",
            quote_ccy=_quote,
            tick_size=_tick,
            contract_size=100_000,
            min_lot=0.01,
            lot_step=0.01,
            max_lot=100.0,
            session="24/5",
            session_tz="UTC",
            data_source="mt5",
        )
    )

# Metales spot (tratados como forex/CFD)
register(
    Instrument(
        "XAUUSD",
        "cfd",
        quote_ccy="USD",
        tick_size=0.01,
        contract_size=100,
        tick_value=1.0,
        min_lot=0.01,
        lot_step=0.01,
        max_lot=50,
        session="24/5",
        session_tz="UTC",
        data_source="mt5",
        series_id="XAUUSD.SPOT",
        spread=None,
        spread_note="pendiente de verificar con el bróker",
        notes="CFD spot de oro; no mezclar con GC futuros",
    )
)
register(
    Instrument(
        "XAGUSD",
        "cfd",
        quote_ccy="USD",
        tick_size=0.001,
        contract_size=5_000,
        tick_value=5.0,
        min_lot=0.01,
        lot_step=0.01,
        max_lot=50,
        session="24/5",
        session_tz="UTC",
        data_source="mt5",
        series_id="XAGUSD.SPOT",
        spread=None,
        spread_note="pendiente de verificar con el bróker",
        notes="CFD spot de plata",
    )
)

# --- Futuros CME (Micro y completos) -----------------------------------------
_FUTURES = [
    # symbol, tick_size, tick_value, multiplier, max_lot
    ("ES", 0.25, 12.50, 50, 50),
    ("MES", 0.25, 1.25, 5, 200),
    ("NQ", 0.25, 5.00, 20, 50),
    ("MNQ", 0.25, 0.50, 2, 200),
    ("YM", 1.0, 5.00, 5, 50),
    ("MYM", 1.0, 0.50, 0.5, 200),
    ("RTY", 0.10, 5.00, 50, 50),
    ("M2K", 0.10, 0.50, 5, 200),
    ("CL", 0.01, 10.00, 1_000, 50),
    ("MCL", 0.01, 1.00, 100, 200),
    ("GC", 0.10, 10.00, 100, 50),
    ("MGC", 0.10, 1.00, 10, 200),
    ("6E", 0.00005, 6.25, 125_000, 50),
    ("ZN", 0.015625, 15.625, 1_000, 50),
    ("ZB", 0.03125, 31.25, 1_000, 50),
]
for _sym, _tick, _tv, _mult, _max in _FUTURES:
    register(
        Instrument(
            symbol=_sym,
            asset_class="futures",
            quote_ccy="USD",
            tick_size=_tick,
            tick_value=_tv,
            contract_size=_mult,
            min_lot=1,
            lot_step=1,
            max_lot=_max,
            session="24/5 (pausa diaria 17:00-18:00 ET)",
            session_tz="America/New_York",
            data_source="projectx",
            series_id=f"{_sym}.FUT",
            spread=None,
            spread_note="pendiente de verificar con el mercado",
        )
    )

# --- Acciones / ETF ----------------------------------------------------------
for _sym in ["SPY", "QQQ", "IWM", "DIA", "NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "META"]:
    register(
        Instrument(
            symbol=_sym,
            asset_class="equity",
            quote_ccy="USD",
            tick_size=0.01,
            contract_size=1,
            min_lot=1,
            lot_step=1,
            max_lot=1_000_000,
            session="09:30-16:00 America/New_York",
            session_tz="America/New_York",
            data_source="yahoo",
        )
    )


__all__ = [
    "AssetClass",
    "Instrument",
    "InstrumentError",
    "INSTRUMENTS",
    "catalog",
    "register",
    "get_instrument",
    "list_instruments",
    "validate_catalog",
    "validate_universe",
]
