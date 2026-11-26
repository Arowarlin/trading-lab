"""TCA: coste de ejecución real frente al supuesto del backtest.

Cada fill deja una fila en `tca` con el precio de referencia, el precio de
ejecución, el slippage medido, el coste esperado (el del modelo de costes) y el
coste realizado. Sobre esas filas se calcula una **EWMA de 20 fills** del
slippage y del coste realizado, por bot y símbolo.

Estados con los mismos umbrales que `drift.py`:

- `ok`: slippage p50 dentro de lo supuesto + 5 bps
- `vigilar`: p50 supera el supuesto + 5 bps
- `deriva`: p50 > 10 bps o p95 > 25 bps

Con menos de 5 fills: **sin datos**. La alerta `tca_drift` se envía **solo al
pasar a `deriva`**, nunca en cada consulta.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .db import connect, init_db

HALFLIFE = 20
MIN_FILLS = 5
MAX_P50_BPS = 10.0
MAX_P95_BPS = 25.0
TCA_VERSION = 2
STATUS_ORDER = {"sin datos": 0, "ok": 1, "vigilar": 2, "deriva": 3}


def record_fill(
    db_path: str | Path,
    *,
    fill_id: int | None = None,
    bot: str | None = None,
    account: str | None = None,
    symbol: str,
    side: str | None = None,
    signal_px: float | None = None,
    order_px: float | None = None,
    fill_px: float | None = None,
    slippage_bps: float | None = None,
    latency_ms: float | None = None,
    expected_cost_bps: float | None = None,
    realized_cost_bps: float | None = None,
    bid: float | None = None,
    ask: float | None = None,
    requested_price: float | None = None,
    order_type: str | None = None,
    origin: str | None = None,
) -> int | None:
    """Registra un fill. Nunca rompe la orden si falla el registro."""
    try:
        init_db(db_path)
        with connect(db_path) as con:
            cursor = con.execute(
                "INSERT INTO tca"
                "(fill_id, bot, account, symbol, side, signal_px, order_px, fill_px, "
                "slippage_bps, latency_ms, expected_cost_bps, realized_cost_bps, "
                "bid, ask, requested_price, order_type, origin, tca_version, ts_utc) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    None if fill_id is None else int(fill_id),
                    None if bot is None else str(bot),
                    None if account is None else str(account),
                    str(symbol).upper(),
                    None if side is None else str(side),
                    None if signal_px is None else float(signal_px),
                    None if order_px is None else float(order_px),
                    None if fill_px is None else float(fill_px),
                    None if slippage_bps is None else float(slippage_bps),
                    None if latency_ms is None else float(latency_ms),
                    None if expected_cost_bps is None else float(expected_cost_bps),
                    None if realized_cost_bps is None else float(realized_cost_bps),
                    None if bid is None else float(bid),
                    None if ask is None else float(ask),
                    None if requested_price is None else float(requested_price),
                    None if order_type is None else str(order_type),
                    None if origin is None else str(origin),
                    int(TCA_VERSION),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            return int(cursor.lastrowid)
    except Exception:
        return None


def slippage_bps(signal_px: float | None, fill_px: float | None, side: str | None) -> float | None:
    """Slippage en bps con el signo de la operación (positivo = peor que lo previsto)."""
    if not signal_px or not fill_px:
        return None
    raw = (float(fill_px) - float(signal_px)) / float(signal_px) * 10_000.0
    return -raw if str(side or "buy").lower() == "sell" else raw


def ewma_last(values: list[float], halflife: int = HALFLIFE) -> float | None:
    """Último valor de una EWMA de los `values` (los más recientes pesan más)."""
    clean = [float(value) for value in values if value is not None and math.isfinite(value)]
    if not clean:
        return None
    alpha = 1.0 - 0.5 ** (1.0 / max(1, int(halflife)))
    result = clean[0]
    for value in clean[1:]:
        result = alpha * value + (1 - alpha) * result
    return float(result)


def classify(
    fills: int,
    p50_bps: float | None,
    p95_bps: float | None,
    *,
    expected_bps: float,
    min_fills: int = MIN_FILLS,
) -> tuple[str, list[str]]:
    """Estado con los umbrales de drift.py."""
    if fills < min_fills or p50_bps is None:
        return "sin datos", [f"fills={fills} < {min_fills}"]
    reasons: list[str] = []
    if p50_bps > MAX_P50_BPS or (p95_bps is not None and p95_bps > MAX_P95_BPS):
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps / p95="
            f"{p95_bps if p95_bps is not None else float('nan'):.1f}bps "
            f"supera maximos {MAX_P50_BPS:.0f}/{MAX_P95_BPS:.0f}"
        )
        return "deriva", reasons
    if p50_bps > expected_bps + 5.0:
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps > supuesto {expected_bps:.1f}bps + 5"
        )
        return "vigilar", reasons
    reasons.append(f"slippage p50={p50_bps:.1f}bps vs supuesto {expected_bps:.1f}bps")
    return "ok", reasons


def _percentile(values: list[float], pct: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * pct
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[int(position)]
    return clean[lower] + (clean[upper] - clean[lower]) * (position - lower)


def build_tca(
    db_path: str | Path,
    *,
    min_fills: int = MIN_FILLS,
    expected_bps: float | None = None,
    alert: bool = True,
) -> dict:
    """Estado de TCA por bot y símbolo."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM tca WHERE tca_version >= 2 ORDER BY id"
        ).fetchall()
        orders = con.execute(
            "SELECT bot, COUNT(*) AS n FROM orders WHERE status = 'filled' GROUP BY bot"
        ).fetchall()

    orders_by_bot = {
        str(row["bot"] or "-"): int(row["n"]) for row in orders if row["bot"]
    }

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (str(row["bot"] or "-"), str(row["symbol"] or "-"))
        grouped.setdefault(key, []).append(dict(row))

    out: list[dict] = []
    for (bot, symbol), items in sorted(grouped.items()):
        slips = [
            float(item["slippage_bps"])
            for item in items
            if item.get("slippage_bps") is not None
        ]
        costs = [
            float(item["realized_cost_bps"])
            for item in items
            if item.get("realized_cost_bps") is not None
        ]
        latencies = [
            float(item["latency_ms"])
            for item in items
            if item.get("latency_ms") is not None
        ]
        expected = (
            float(expected_bps)
            if expected_bps is not None
            else (
                statistics.fmean(
                    [
                        float(item["expected_cost_bps"])
                        for item in items
                        if item.get("expected_cost_bps") is not None
                    ]
                )
                if any(item.get("expected_cost_bps") is not None for item in items)
                else 0.0
            )
        )
        p50 = _percentile(slips, 0.50)
        p95 = _percentile(slips, 0.95)
        status, reasons = classify(
            len(slips), p50, p95, expected_bps=expected, min_fills=min_fills
        )
        total_orders = orders_by_bot.get(bot, 0)
        out.append(
            {
                "bot": bot,
                "symbol": symbol,
                "fills": len(items),
                "orders": total_orders,
                "fill_rate": (len(items) / total_orders) if total_orders else None,
                "slippage_p50_bps": p50,
                "slippage_p95_bps": p95,
                "slippage_ewma_bps": ewma_last(slips),
                "cost_ewma_bps": ewma_last(costs),
                "median_latency_ms": statistics.median(latencies) if latencies else None,
                "expected_cost_bps": expected,
                "status": status,
                "reasons": reasons,
            }
        )

    counts: dict[str, int] = {}
    for row in out:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    worst = max(
        (row["status"] for row in out),
        key=lambda status: STATUS_ORDER.get(status, 0),
        default="sin datos",
    )
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": out,
        "counts": counts,
        "status": worst,
        "min_fills": int(min_fills),
    }
    if alert:
        state["alerts"] = _alert_transitions(db_path, out)
    return state


def _alert_transitions(db_path: str | Path, rows: list[dict]) -> list[dict]:
    """Alerta `tca_drift` solo al pasar a `deriva`."""
    from .alerts import send as send_alert

    sent: list[dict] = []
    try:
        init_db(db_path)
        with connect(db_path) as con:
            previous = {
                (str(row["bot"]), str(row["symbol"])): str(row["status"])
                for row in con.execute(
                    "SELECT bot, symbol, status FROM tca_state"
                ).fetchall()
            }
            for row in rows:
                key = (row["bot"], row["symbol"])
                before = previous.get(key)
                if row["status"] == "deriva" and before != "deriva":
                    message = (
                        f"TCA {row['bot']}/{row['symbol']}: {row['reasons'][0]}"
                    )
                    try:
                        send_alert("tca_drift", message, severity="warning")
                    except Exception:
                        pass
                    sent.append({"bot": row["bot"], "symbol": row["symbol"], "message": message})
                con.execute(
                    "INSERT INTO tca_state(bot, symbol, status, updated_at) "
                    "VALUES(?,?,?,?)",
                    (
                        row["bot"],
                        row["symbol"],
                        row["status"],
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )
    except Exception:
        return sent
    return sent


def attach_to_drift(rows: list[dict], db_path: str | Path) -> list[dict]:
    """Añade a cada fila de deriva la EWMA de TCA del bot (si hay fills)."""
    try:
        state = build_tca(db_path, alert=False)
    except Exception:
        return rows
    by_bot: dict[str, dict] = {}
    for row in state["rows"]:
        by_bot.setdefault(str(row["bot"]), row)
    for row in rows:
        item = by_bot.get(str(row.get("bot")))
        if not item:
            continue
        row["tca_status"] = item["status"]
        row["tca_slippage_ewma_bps"] = item["slippage_ewma_bps"]
        row["tca_fills"] = item["fills"]
    return rows


__all__ = [
    "HALFLIFE",
    "MIN_FILLS",
    "STATUS_ORDER",
    "TCA_VERSION",
    "attach_to_drift",
    "build_tca",
    "classify",
    "ewma_last",
    "record_fill",
    "slippage_bps",
]
