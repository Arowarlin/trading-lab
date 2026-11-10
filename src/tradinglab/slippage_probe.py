"""Sonda aislada de slippage real en demo.

Solo mide: no activa bots, no usa estrategias y no toca el orquestador. Cada
round-trip envía una orden de mercado y cierra la posición inmediatamente.
"""
from __future__ import annotations

import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .alerts import send as send_alert
from .config import DEFAULT_DB
from .db import connect, init_db

DEFAULT_SPACING_S = 2.0
DEFAULT_MAX_ROUND_TRIPS = 3
DEFAULT_MAX_ROUND_TRIPS_DAY = 6
DEFAULT_POLL_ATTEMPTS = 10
DEFAULT_POLL_S = 0.2
DEFAULT_CLOSE_ATTEMPTS = 3
DEFAULT_CLOSE_RETRY_S = 0.5
REQUOTE_CODE = 10004


class SlippageProbeError(RuntimeError):
    """La sonda no puede ejecutarse o una guarda falló."""


def slippage_bps(side: str, requested: float, filled: float | None) -> float | None:
    """Slippage adverso en bps por lado: positivo = peor precio."""
    if filled is None or requested <= 0:
        return None
    sign = 1.0 if str(side).lower() == "buy" else -1.0
    return float(sign * (float(filled) / float(requested) - 1.0) * 10_000.0)


def _retcode_from_error(exc: Exception) -> int | None:
    match = re.search(r"\[(\d+)\]", str(exc))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _is_requote(exc: Exception, retcode: int | None) -> bool:
    return retcode == REQUOTE_CODE or "requote" in str(exc).lower()


def _record(db_path: str | Path, row: dict[str, Any]) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO broker_slippage"
            "(ts, symbol, side, hour_utc, requested, filled, slippage_bps, "
            "volume, order_type, leg, requote, retcode, error) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["ts"],
                row["symbol"],
                row["side"],
                int(row["hour_utc"]),
                float(row["requested"]),
                None if row.get("filled") is None else float(row["filled"]),
                (
                    None
                    if row.get("slippage_bps") is None
                    else float(row["slippage_bps"])
                ),
                float(row["volume"]),
                row.get("order_type") or "market",
                row.get("leg") or "entry",
                1 if row.get("requote") else 0,
                row.get("retcode"),
                row.get("error"),
            ),
        )


def _entries_today(db_path: str | Path, day: str) -> int:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM broker_slippage "
            "WHERE leg = 'entry' AND substr(ts, 1, 10) = ?",
            (day,),
        ).fetchone()
    return int(row["n"])


def _require_health_true(health: dict, key: str, message: str) -> None:
    if health.get(key) is not True:
        raise SlippageProbeError(message)


def _position_ids(position: dict) -> set[int]:
    ids: set[int] = set()
    for key in ("ticket", "order_id", "deal_id", "position_id", "identifier"):
        value = position.get(key)
        if value is None:
            continue
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _find_position_by_ids(
    broker,
    symbol: str,
    *,
    order_id: int,
    deal_id: int | None,
    side: str,
    volume: float,
    sleep: Callable[[float], None],
) -> dict:
    expected = {int(order_id)}
    if deal_id is not None:
        expected.add(int(deal_id))
    for attempt in range(DEFAULT_POLL_ATTEMPTS):
        positions = broker.positions(symbol=symbol)
        matches = [
            position
            for position in positions
            if _position_ids(position) & expected
        ]
        if len(matches) > 1:
            raise SlippageProbeError(
                f"{symbol}: posición ambigua para order_id={order_id} "
                f"deal_id={deal_id}; no se cierra nada"
            )
        if len(matches) == 1:
            position = matches[0]
            if str(position.get("side") or "").lower() != side:
                raise SlippageProbeError(
                    f"{symbol}: la posición {position.get('ticket')} no coincide "
                    "con el lado de la entrada; no se cierra nada"
                )
            if not math.isclose(
                float(position.get("volume") or 0.0),
                volume,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise SlippageProbeError(
                    f"{symbol}: la posición {position.get('ticket')} no coincide "
                    "con el volumen de la entrada; no se cierra nada"
                )
            return position
        if attempt < DEFAULT_POLL_ATTEMPTS - 1:
            sleep(DEFAULT_POLL_S)
    raise SlippageProbeError(
        f"{symbol}: no se pudo identificar la posición por order_id={order_id} "
        f"deal_id={deal_id}; no se cierra nada"
    )


def _position_is_open(broker, symbol: str, ticket: int) -> bool:
    try:
        positions = broker.positions(symbol=symbol)
    except Exception:
        return True
    return any(int(ticket) in _position_ids(position) for position in positions)


def _close_with_retries(
    broker,
    ticket: int,
    volume: float,
    *,
    sleep: Callable[[float], None],
) -> tuple[dict | None, Exception | None, int]:
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_CLOSE_ATTEMPTS + 1):
        try:
            return broker.close_position(ticket, volume=volume), None, attempt
        except Exception as exc:
            last_error = exc
            if attempt < DEFAULT_CLOSE_ATTEMPTS:
                sleep(DEFAULT_CLOSE_RETRY_S)
    return None, last_error, DEFAULT_CLOSE_ATTEMPTS


def _prepare_probe(
    broker,
    symbol: str,
    *,
    orders: int,
    volume: float | None,
    spacing_s: float,
    max_orders: int,
    max_orders_day: int,
    db_path: str | Path,
    clock: Callable[[], datetime],
) -> dict:
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise SlippageProbeError("símbolo vacío")
    if orders < 1:
        raise SlippageProbeError("orders debe ser >= 1")
    if max_orders < 1 or max_orders_day < 1:
        raise SlippageProbeError("los topes deben ser >= 1")
    if orders > max_orders:
        raise SlippageProbeError(
            f"orders {orders} > tope por ejecución {max_orders}"
        )
    if spacing_s < 0:
        raise SlippageProbeError("spacing no puede ser negativo")

    health = broker.health()
    if health.get("mode") != "demo":
        raise SlippageProbeError(
            f"cuenta no demo: mode={health.get('mode')!r}; no se envía nada"
        )
    _require_health_true(
        health, "identity_ok", "identity_ok != True; no se envía nada"
    )
    _require_health_true(
        health, "connected", "connected != True; no se envía nada"
    )
    _require_health_true(
        health, "trade_allowed", "trade_allowed != True; no se envía nada"
    )

    spec = broker.symbol_spec(symbol)
    volume_min = float(spec.get("volume_min") or 0.0)
    if volume_min <= 0:
        raise SlippageProbeError(f"{symbol}: volume_min inválido")
    if volume is not None:
        if not math.isclose(float(volume), volume_min, rel_tol=1e-9, abs_tol=1e-12):
            raise SlippageProbeError(
                f"{symbol}: esta sonda solo permite el volumen mínimo "
                f"({volume_min:g}); recibido {float(volume):g}"
            )
    selected_volume = volume_min

    init_db(db_path)
    now = clock() or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = now.astimezone(timezone.utc).date().isoformat()
    already = _entries_today(db_path, day)
    if already + orders > max_orders_day:
        raise SlippageProbeError(
            f"tope diario: ya hay {already} entradas hoy y se piden {orders}; "
            f"máximo {max_orders_day}"
        )
    return {
        "symbol": symbol,
        "orders": orders,
        "volume": selected_volume,
        "spec": spec,
        "health": health,
        "spacing_s": spacing_s,
        "max_orders": max_orders,
        "max_orders_day": max_orders_day,
        "day": day,
        "entries_today": already,
        "db_path": str(db_path),
    }


def preview_probe(
    broker,
    symbol: str,
    *,
    orders: int = 2,
    volume: float | None = None,
    spacing_s: float = DEFAULT_SPACING_S,
    max_orders: int = DEFAULT_MAX_ROUND_TRIPS,
    max_orders_day: int = DEFAULT_MAX_ROUND_TRIPS_DAY,
    db_path: str | Path = DEFAULT_DB,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Valida guardas y muestra qué enviaría, sin enviar nada."""
    prepared = _prepare_probe(
        broker,
        symbol,
        orders=orders,
        volume=volume,
        spacing_s=spacing_s,
        max_orders=max_orders,
        max_orders_day=max_orders_day,
        db_path=db_path,
        clock=clock,
    )
    prepared.update(
        {
            "dry_run": True,
            "mode": prepared["health"].get("mode"),
            "identity_ok": prepared["health"].get("identity_ok"),
            "would_send_orders": 2 * orders,
        }
    )
    return prepared


def run_probe(
    broker,
    symbol: str,
    *,
    orders: int = 2,
    volume: float | None = None,
    spacing_s: float = DEFAULT_SPACING_S,
    max_orders: int = DEFAULT_MAX_ROUND_TRIPS,
    max_orders_day: int = DEFAULT_MAX_ROUND_TRIPS_DAY,
    db_path: str | Path = DEFAULT_DB,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Ejecuta N round-trips de volumen mínimo y registra sus fills.

    ``orders`` y los topes cuentan round-trips; cada round-trip son dos órdenes
    de mercado (entrada y cierre). Cualquier guarda falla antes de enviar.
    """
    prepared = _prepare_probe(
        broker,
        symbol,
        orders=orders,
        volume=volume,
        spacing_s=spacing_s,
        max_orders=max_orders,
        max_orders_day=max_orders_day,
        db_path=db_path,
        clock=clock,
    )
    symbol = prepared["symbol"]
    selected_volume = prepared["volume"]

    sent = 0
    filled = 0
    requotes = 0
    errors = 0
    for index in range(orders):
        side = "buy" if index % 2 == 0 else "sell"
        tick = broker.tick(symbol)
        requested = float(tick["ask"] if side == "buy" else tick["bid"])
        stamp = clock().astimezone(timezone.utc)
        order: dict | None = None
        signed_volume = selected_volume if side == "buy" else -selected_volume
        try:
            order = broker.submit_market(
                symbol,
                signed_volume,
                bot="slippage-probe",
                reason="slippage probe",
            )
        except Exception as exc:
            sent += 1
            retcode = _retcode_from_error(exc)
            requote = _is_requote(exc, retcode)
            requotes += 1 if requote else 0
            errors += 0 if requote else 1
            _record(
                db_path,
                {
                    "ts": stamp.isoformat(),
                    "symbol": symbol,
                    "side": side,
                    "hour_utc": stamp.hour,
                    "requested": requested,
                    "filled": None,
                    "slippage_bps": None,
                    "volume": selected_volume,
                    "order_type": "market",
                    "leg": "entry",
                    "requote": requote,
                    "retcode": retcode,
                    "error": str(exc)[:300],
                },
            )
            if not requote:
                raise SlippageProbeError(
                    f"entrada rechazada para {symbol}: {exc}"
                ) from exc
            if index < orders - 1 and spacing_s:
                sleep(spacing_s)
            continue

        sent += 1
        filled_price = float(order["price"])
        retcode = order.get("retcode")
        _record(
            db_path,
            {
                "ts": stamp.isoformat(),
                "symbol": symbol,
                "side": side,
                "hour_utc": stamp.hour,
                "requested": requested,
                "filled": filled_price,
                "slippage_bps": slippage_bps(side, requested, filled_price),
                "volume": selected_volume,
                "order_type": "market",
                "leg": "entry",
                "requote": False,
                "retcode": retcode,
                "error": None,
            },
        )

        order_id = order.get("order_id")
        if order_id is None:
            raise SlippageProbeError(
                f"{symbol}: submit_market no devolvió order_id; no se puede "
                "identificar la posición y no se cierra nada"
            )
        deal_id = order.get("deal_id")
        position = _find_position_by_ids(
            broker,
            symbol,
            order_id=int(order_id),
            deal_id=None if deal_id is None else int(deal_id),
            side=side,
            volume=selected_volume,
            sleep=sleep,
        )
        close_side = "sell" if side == "buy" else "buy"
        close_tick = broker.tick(symbol)
        close_requested = float(
            close_tick["bid"] if close_side == "sell" else close_tick["ask"]
        )
        close_stamp = clock().astimezone(timezone.utc)
        sent += 1
        closed, close_error, attempts = _close_with_retries(
            broker,
            int(position["ticket"]),
            selected_volume,
            sleep=sleep,
        )
        if closed is None:
            retcode = (
                _retcode_from_error(close_error)
                if close_error is not None
                else None
            )
            requote = (
                _is_requote(close_error, retcode)
                if close_error is not None
                else False
            )
            requotes += 1 if requote else 0
            errors += 0 if requote else 1
            error_text = str(close_error)[:300]
            _record(
                db_path,
                {
                    "ts": close_stamp.isoformat(),
                    "symbol": symbol,
                    "side": close_side,
                    "hour_utc": close_stamp.hour,
                    "requested": close_requested,
                    "filled": None,
                    "slippage_bps": None,
                    "volume": selected_volume,
                    "order_type": "market",
                    "leg": "close",
                    "requote": requote,
                    "retcode": retcode,
                    "error": f"close failed after {attempts} attempts: {error_text}",
                },
            )
            if _position_is_open(broker, symbol, int(position["ticket"])):
                message = (
                    f"Posición huérfana en {symbol} ticket={position['ticket']} "
                    f"tras {attempts} intentos de cierre: {error_text}"
                )
                try:
                    send_alert(
                        "slippage_probe_orphan",
                        message,
                        severity="error",
                        db_path=db_path,
                    )
                except Exception:
                    pass
                raise SlippageProbeError(message) from close_error
            raise SlippageProbeError(
                f"{symbol}: el cierre falló tras {attempts} intentos y la "
                f"posición {position['ticket']} ya no está abierta; "
                f"no hay fill de cierre: {error_text}"
            ) from close_error

        close_filled = float(closed["price"])
        _record(
            db_path,
            {
                "ts": close_stamp.isoformat(),
                "symbol": symbol,
                "side": close_side,
                "hour_utc": close_stamp.hour,
                "requested": close_requested,
                "filled": close_filled,
                "slippage_bps": slippage_bps(
                    close_side, close_requested, close_filled
                ),
                "volume": selected_volume,
                "order_type": "market",
                "leg": "close",
                "requote": False,
                "retcode": closed.get("retcode"),
                "error": None,
            },
        )
        filled += 1
        if index < orders - 1 and spacing_s:
            sleep(spacing_s)

    return {
        "symbol": symbol,
        "requested_round_trips": orders,
        "sent_orders": sent,
        "filled_round_trips": filled,
        "requotes": requotes,
        "errors": errors,
        "volume": selected_volume,
        "db_path": str(db_path),
    }


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median_bps": None, "p75_bps": None}
    array = np.asarray(values, dtype=float)
    return {
        "n": int(len(array)),
        "median_bps": float(np.median(array)),
        "p75_bps": float(np.percentile(array, 75)),
    }


def report(
    db_path: str | Path = DEFAULT_DB,
    *,
    symbol: str | None = None,
    order_type: str | None = None,
) -> dict:
    """Mediana y p75 por símbolo, lado, hora UTC y tipo de orden."""
    init_db(db_path)
    clauses = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(str(symbol).strip().upper())
    if order_type:
        clauses.append("order_type = ?")
        params.append(str(order_type).strip().lower())
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT symbol, side, hour_utc, order_type, requested, filled, "
            "slippage_bps, requote FROM broker_slippage"
            f"{where} ORDER BY symbol, ts",
            params,
        ).fetchall()

    filled_rows = [row for row in rows if row["slippage_bps"] is not None]
    requotes = sum(1 for row in rows if int(row["requote"] or 0))

    def grouped(keys: tuple[str, ...]) -> list[dict]:
        buckets: dict[tuple, list[float]] = {}
        counts: dict[tuple, int] = {}
        for row in rows:
            key = tuple(row[column] for column in keys)
            counts[key] = counts.get(key, 0) + (1 if row["requote"] else 0)
            if row["slippage_bps"] is not None:
                buckets.setdefault(key, []).append(float(row["slippage_bps"]))
        out = []
        for key in sorted(buckets):
            item = dict(zip(keys, key))
            item.update(_stats(buckets[key]))
            item["requotes"] = int(counts.get(key, 0))
            out.append(item)
        return out

    return {
        "rows": len(rows),
        "filled_rows": len(filled_rows),
        "requotes": int(requotes),
        "by_symbol": grouped(("symbol",)),
        "by_side": grouped(("symbol", "side")),
        "by_hour": grouped(("symbol", "hour_utc")),
        "by_order_type": grouped(("symbol", "order_type")),
    }


def confirmation_matches(symbol: str, typed: str) -> bool:
    """Confirma que el texto escrito coincide con el símbolo, sin ambigüedad."""
    return str(typed or "").strip().upper() == str(symbol or "").strip().upper()


__all__ = [
    "DEFAULT_CLOSE_ATTEMPTS",
    "DEFAULT_CLOSE_RETRY_S",
    "DEFAULT_MAX_ROUND_TRIPS",
    "DEFAULT_MAX_ROUND_TRIPS_DAY",
    "DEFAULT_SPACING_S",
    "SlippageProbeError",
    "confirmation_matches",
    "preview_probe",
    "report",
    "run_probe",
    "slippage_bps",
]
