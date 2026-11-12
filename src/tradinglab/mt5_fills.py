"""Sincroniza los deals de MT5 con la tabla `fills` del Diario.

El forward demo opera en MT5, pero hasta ahora el Diario solo reconstruía
operaciones del paper interno (fills con `order_id`). Este módulo lee el
historial de deals del terminal desde la última lectura, guarda una fila por
deal y deja el cursor en `mt5_fills_sync`. Es idempotente por `deal_id`: si un
ciclo se repite o se solapa, no se duplica nada.

Solo lectura sobre MT5. No envía órdenes ni toca la configuración.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DEFAULT_DB
from .db import connect, init_db, utcnow

FORWARD_BOT_PREFIX = "forward:"
INITIAL_LOOKBACK_DAYS = 30
CURSOR_OVERLAP = timedelta(hours=6)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def sync_mt5_fills(
    broker,
    db_path: str | Path = DEFAULT_DB,
    *,
    magics: dict[int, str] | None = None,
    account: str = "ftmo_demo",
    now: datetime | None = None,
    lookback_days: int = INITIAL_LOOKBACK_DAYS,
) -> dict:
    """Lee los deals nuevos y los escribe en `fills`. Devuelve un resumen.

    `magics` mapea magic → nombre del bot (p. ej. ``forward:us100-trend-d1``).
    Los deals con un magic fuera del mapa se guardan con bot ``manual``.
    """
    moment = _as_utc(now)
    init_db(db_path)
    mapping = {int(key): str(value) for key, value in (magics or {}).items()}

    with connect(db_path) as con:
        row = con.execute(
            "SELECT last_deal_time FROM mt5_fills_sync WHERE account = ?",
            (account,),
        ).fetchone()
    if row is not None:
        try:
            start = datetime.fromisoformat(str(row["last_deal_time"])) - CURSOR_OVERLAP
        except ValueError:
            start = moment - timedelta(days=lookback_days)
    else:
        start = moment - timedelta(days=lookback_days)
    start = _as_utc(start)

    deals = broker.history_deals(start, moment + timedelta(hours=1))

    inserted = 0
    manual = 0
    last_seen = None
    sizes: dict[str, float] = {}

    def _contract_size(symbol: str) -> float:
        if symbol in sizes:
            return sizes[symbol]
        size = 1.0
        try:
            spec = broker.symbol_spec(symbol)
            size = float(spec.get("contract_size") or 1.0)
        except Exception:
            size = 1.0
        sizes[symbol] = size
        return size

    with connect(db_path) as con:
        for deal in deals:
            deal_id = int(deal.get("deal_id") or 0)
            symbol = str(deal.get("symbol") or "").strip().upper()
            side = str(deal.get("side") or "").lower()
            volume = float(deal.get("volume") or 0.0)
            price = float(deal.get("price") or 0.0)
            if deal_id <= 0 or not symbol or side not in {"buy", "sell"}:
                continue
            if volume <= 0 or price <= 0:
                continue
            magic = int(deal.get("magic") or 0)
            bot = mapping.get(magic, "manual")
            if bot == "manual":
                manual += 1
            ts_utc = str(deal.get("ts_utc") or moment.isoformat())
            cursor = con.execute(
                "INSERT OR IGNORE INTO fills"
                "(order_id, ts, qty, price, commission, bot, account, symbol, "
                " side, volume, swap, deal_id, magic, ts_utc, contract_size) "
                "VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ts_utc,
                    volume,
                    price,
                    float(deal.get("commission") or 0.0),
                    bot,
                    account,
                    symbol,
                    side,
                    volume,
                    float(deal.get("swap") or 0.0),
                    deal_id,
                    magic,
                    ts_utc,
                    _contract_size(symbol),
                ),
            )
            inserted += int(cursor.rowcount or 0)
            if last_seen is None or ts_utc > last_seen:
                last_seen = ts_utc
        if last_seen is not None:
            con.execute(
                "INSERT INTO mt5_fills_sync(account, last_deal_time, updated_at) "
                "VALUES(?,?,?) ON CONFLICT(account) DO UPDATE SET "
                "last_deal_time = excluded.last_deal_time, "
                "updated_at = excluded.updated_at",
                (account, last_seen, utcnow()),
            )

    return {
        "account": account,
        "from": start.isoformat(),
        "deals": len(deals),
        "inserted": inserted,
        "manual": manual,
        "last_deal_time": last_seen,
    }


__all__ = ["sync_mt5_fills"]
