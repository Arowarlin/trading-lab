"""Datos de mercado CFD/futuros en **solo lectura** para agentes y briefing.

* Se adjunta al terminal MT5 ya abierto (``AttachOnlyBroker``): no pasa
  credenciales, no arranca el terminal y **nunca** llama a métodos de órdenes.
* Si MT5 no está abierto o la cuenta no es la esperada, devuelve ``Sin datos``.
* El universo activo es el del Prop Fund: US100, US500, GER40, XAUUSD, EURUSD,
  GBPUSD y USDJPY. Los futuros (NQ, MNQ, GC, MGC) quedan declarados pero
  devuelven ``Sin datos`` hasta tener proveedor intradía.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..execution.mt5 import MT5Error
from .instruments import resolve

CFD_UNIVERSE: tuple[str, ...] = (
    "US100",
    "US500",
    "GER40",
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
)

FUTURES_UNIVERSE: tuple[str, ...] = ("NQ", "MNQ", "GC", "MGC")

ACTIVE_UNIVERSE: tuple[str, ...] = CFD_UNIVERSE

_SESSIONS = (
    # (nombre, hora UTC de inicio, hora UTC de fin)
    ("asia", 0, 7),
    ("london", 7, 12),
    ("ny", 12, 21),
)


@dataclass(frozen=True)
class Session:
    name: str
    label: str
    tz: str

    def as_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "tz": self.tz}


def session_now(now: datetime | None = None) -> Session:
    """Sesión de mercado aproximada a partir de UTC (sin inventar horarios)."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    hour = moment.astimezone(UTC).hour
    for name, start, end in _SESSIONS:
        if start <= hour < end:
            if name == "asia":
                return Session("asia", "Asia", "Asia/Tokyo")
            if name == "london":
                return Session("london", "Londres", "Europe/London")
            return Session("ny", "Nueva York", "America/New_York")
    return Session("fuera", "Fuera de sesión", "UTC")


def briefing_slot(now: datetime | None = None) -> str:
    """``pre_london``, ``pre_ny`` o ``fuera`` para el briefing."""
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    london = moment.astimezone(ZoneInfo("Europe/London"))
    ny = moment.astimezone(ZoneInfo("America/New_York"))
    if london.weekday() < 5 and (london.hour, london.minute) < (7, 30):
        return "pre_london"
    if ny.weekday() < 5 and (ny.hour, ny.minute) < (9, 0) and ny.hour >= 7:
        return "pre_ny"
    return "fuera"


def broker_symbol(instrument_id: str) -> str:
    """Alias de bróker más probable para un id canónico del Prop Fund."""
    item = resolve(instrument_id)
    for alias in item.aliases:
        if alias.upper() == item.id:
            continue
        if alias.upper().endswith(".CASH"):
            return alias
    return item.id


def read_only_broker(*, settings: Settings | None = None):
    """``AttachOnlyBroker`` con la identidad MT5 configurada. Sin órdenes."""
    from .snapshots import AttachOnlyBroker

    settings = settings or Settings.load()
    login = settings.mt5.login
    server = str(settings.mt5.server or "").strip()
    if login is None or not server:
        raise MT5Error("Sin datos: define MT5_LOGIN y MT5_SERVER")
    return AttachOnlyBroker(
        expected_login=int(login),
        expected_server=server,
        path=settings.mt5.terminal_path,
        timeout_ms=5000,
        server_utc_offset_hours=settings.mt5.server_utc_offset_hours,
    )


def _quote_with(broker, instrument_id: str) -> dict:
    symbol = broker_symbol(instrument_id)
    tick = broker.tick(symbol)
    bid = tick.get("bid")
    ask = tick.get("ask")
    price = tick.get("last") or ((bid + ask) / 2 if bid and ask else None)
    spread = (ask - bid) if bid is not None and ask is not None else None
    item = resolve(instrument_id)
    return {
        "instrument": item.id,
        "symbol": symbol,
        "market": item.market.value,
        "underlying": item.underlying,
        "bid": bid,
        "ask": ask,
        "price": price,
        "spread_price": spread,
        "time": tick.get("time"),
        "source": "mt5",
        "read_only": True,
        "status": "ok" if price is not None else "Sin datos",
    }


def quote(instrument_id: str, *, broker=None, settings: Settings | None = None) -> dict:
    """Una cotización. Nunca lanza: cualquier fallo es ``Sin datos``."""
    try:
        owned = broker is None
        broker = broker or read_only_broker(settings=settings)
        if owned:
            broker.connect()
        return _quote_with(broker, instrument_id)
    except Exception as exc:
        return {
            "instrument": str(instrument_id).upper(),
            "status": "Sin datos",
            "source": "mt5",
            "read_only": True,
            "error": str(exc)[:240],
        }


def quotes(
    instrument_ids: tuple[str, ...] | list[str] | None = None,
    *,
    broker=None,
    settings: Settings | None = None,
) -> list[dict]:
    """Cotizaciones del universo CFD. Un solo attach para toda la lista."""
    ids = instrument_ids or ACTIVE_UNIVERSE
    items = []
    try:
        owned = broker is None
        broker = broker or read_only_broker(settings=settings)
        if owned:
            broker.connect()
    except Exception as exc:
        return [
            {
                "instrument": str(item).upper(),
                "status": "Sin datos",
                "source": "mt5",
                "read_only": True,
                "error": str(exc)[:240],
            }
            for item in ids
        ]
    for instrument_id in ids:
        try:
            items.append(_quote_with(broker, instrument_id))
        except Exception as exc:
            items.append(
                {
                    "instrument": str(instrument_id).upper(),
                    "status": "Sin datos",
                    "source": "mt5",
                    "read_only": True,
                    "error": str(exc)[:240],
                }
            )
    return items


def rates(
    instrument_id: str,
    *,
    timeframe: str = "D1",
    count: int = 260,
    broker=None,
    settings: Settings | None = None,
):
    """Barras OHLC en solo lectura (``pandas.DataFrame``) o ``None``."""
    try:
        owned = broker is None
        broker = broker or read_only_broker(settings=settings)
        if owned:
            broker.connect()
        return broker.rates(broker_symbol(instrument_id), timeframe=timeframe, count=count)
    except Exception:
        return None


def market_snapshot(
    instrument_ids: tuple[str, ...] | list[str] | None = None,
    *,
    broker=None,
    settings: Settings | None = None,
) -> dict:
    """Cotización + tendencia D1 de todo el universo, con un solo attach."""
    ids = instrument_ids or ACTIVE_UNIVERSE
    rows: list[dict] = []
    try:
        owned = broker is None
        broker = broker or read_only_broker(settings=settings)
        if owned:
            broker.connect()
    except Exception as exc:
        return {
            "status": "Sin datos",
            "source": "mt5",
            "read_only": True,
            "rows": [],
            "error": str(exc)[:240],
        }

    for instrument_id in ids:
        row = {
            "instrument": str(instrument_id).upper(),
            "symbol": str(instrument_id).upper(),
            "status": "Sin datos",
            "read_only": True,
        }
        try:
            quote_row = _quote_with(broker, instrument_id)
            row.update(quote_row)
            frame = broker.rates(broker_symbol(instrument_id), timeframe="D1", count=260)
            if frame is not None and len(frame) >= 21:
                close = frame["close"].astype(float)
                last = float(close.iloc[-1])

                def ret(days: int) -> float | None:
                    return float(last / close.iloc[-1 - days] - 1.0) if len(close) > days else None

                sma20 = float(close.iloc[-20:].mean())
                sma50 = float(close.iloc[-50:].mean()) if len(close) >= 50 else None
                trend = "up" if last > sma20 and (sma50 is None or sma20 > sma50) else (
                    "down" if last < sma20 and (sma50 is None or sma20 < sma50) else "mixed"
                )
                row.update(
                    {
                        "close": last,
                        "return_1d": ret(1),
                        "return_5d": ret(5),
                        "return_20d": ret(20),
                        "trend": trend,
                        "spark": [float(value) for value in close.iloc[-60:]],
                        "as_of": str(frame.index[-1]),
                    }
                )
        except Exception as exc:
            row["error"] = str(exc)[:200]
        rows.append(row)
    return {
        "status": "ok",
        "source": "mt5",
        "read_only": True,
        "rows": rows,
        "count": len(rows),
        "session": session_now().as_dict(),
    }


def universe(*, include_futures: bool = True) -> dict:
    rows = []
    for instrument_id in ACTIVE_UNIVERSE:
        item = resolve(instrument_id)
        rows.append(
            {
                "id": item.id,
                "market": item.market.value,
                "category": item.category,
                "underlying": item.underlying,
                "aliases": list(item.aliases),
                "data": "mt5",
            }
        )
    if include_futures:
        for instrument_id in FUTURES_UNIVERSE:
            try:
                item = resolve(instrument_id)
            except KeyError:
                continue
            rows.append(
                {
                    "id": item.id,
                    "market": item.market.value,
                    "category": item.category,
                    "underlying": item.underlying,
                    "aliases": list(item.aliases),
                    "data": "Sin datos: proveedor intradía pendiente",
                }
            )
    return {
        "cfd": list(CFD_UNIVERSE),
        "futures": list(FUTURES_UNIVERSE),
        "instruments": rows,
        "read_only": True,
    }


__all__ = [
    "ACTIVE_UNIVERSE",
    "CFD_UNIVERSE",
    "FUTURES_UNIVERSE",
    "Session",
    "briefing_slot",
    "broker_symbol",
    "market_snapshot",
    "quote",
    "quotes",
    "rates",
    "read_only_broker",
    "session_now",
    "universe",
]
