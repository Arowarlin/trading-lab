"""T5 · Contrafactual de ai_trader con M1 de MT5 (solo lectura)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from tradinglab.ai_trader import _twin_levels
from tradinglab.config import get_settings
from tradinglab.execution import get_mt5_broker

LAB = Path("data/lab.db")
OUT = Path("TL3_REPORTS/ai_trader_contrafactual.md")
SEED = 7
PATHS = 10_000
START = datetime(2026, 11, 10, tzinfo=timezone.utc)
END = datetime(2026, 11, 26, tzinfo=timezone.utc)


def _bars(raw, offset):
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    frame = pd.DataFrame(raw)
    stamps = pd.to_datetime(frame["time"], unit="s", utc=True) - pd.Timedelta(
        hours=float(offset)
    )
    frame.index = pd.DatetimeIndex(stamps)
    frame = frame.rename(columns={"tick_volume": "tickvol"})
    return frame[["open", "high", "low", "close", "tickvol", "spread"]].sort_index()


def _ny(stamp):
    value = pd.Timestamp(stamp)
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return value.tz_convert("America/New_York")


def _forced(entry_time, style, exit_ts):
    entry_ny = _ny(entry_time)
    if style == "scalping":
        noon = entry_ny.normalize() + pd.Timedelta(hours=12)
        if entry_ny >= noon:
            noon = entry_ny + pd.Timedelta(minutes=60)
        return noon.tz_convert("UTC")
    forced = pd.Timestamp(exit_ts)
    if forced.tzinfo is None:
        forced = forced.tz_localize("UTC")
    if forced <= entry_time:
        forced = entry_time + pd.Timedelta(minutes=60)
    return forced


def _simulate(side, entry, sl_dist, tp_dist, bars, forced, point, spread):
    short = side == "sell"
    risk = float(sl_dist)
    if risk <= 0 or np.isnan(risk):
        return None
    tp_dist = float(tp_dist) if tp_dist and tp_dist > 0 else None
    entry_price = float(bars.iloc[0]["open"])
    for stamp, bar in bars.iterrows():
        if stamp > forced:
            break
        high = float(bar["high"])
        low = float(bar["low"])
        if short:
            if high >= entry_price + risk:
                return (entry_price - (entry_price + risk)) / risk - _cost(
                    spread, point, risk
                )
            if tp_dist is not None and low <= entry_price - tp_dist:
                return (entry_price - (entry_price - tp_dist)) / risk - _cost(
                    spread, point, risk
                )
        else:
            if low <= entry_price - risk:
                return (entry_price - (entry_price - risk)) / risk - _cost(
                    spread, point, risk
                )
            if tp_dist is not None and high >= entry_price + tp_dist:
                return (entry_price - (entry_price + tp_dist)) / risk - _cost(
                    spread, point, risk
                )
    last = float(bars.iloc[-1]["close"])
    raw = (last - entry_price) / risk * (-1 if short else 1)
    return raw - _cost(spread, point, risk)


def _cost(spread_points, point, risk):
    return (float(spread_points) + 1.0) * float(point) / float(risk)


def _bootstrap(values):
    values = np.asarray(values, float)
    if values.size == 0:
        return None
    rng = np.random.default_rng(SEED)
    means = np.array(
        [rng.choice(values, size=values.size, replace=True).mean() for _ in range(PATHS)]
    )
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "ci95": (
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)),
        ),
    }


def main():
    con = sqlite3.connect(f"file:{LAB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    trades = [
        dict(row)
        for row in con.execute(
            "SELECT symbol,side,entry,sl,tp,ts,exit_ts,style,setup,shadow_seed,result_r "
            "FROM ai_trades WHERE result_r IS NOT NULL AND shadow_seed IS NOT NULL"
        )
    ]
    con.close()

    broker = get_mt5_broker(get_settings(), dry_run=True)
    health_before = broker.connect()
    mt5 = broker._require()
    offset = float(broker._server_offset or 0.0)
    bars = {}
    points = {}
    try:
        for symbol in sorted({row["symbol"] for row in trades}):
            info = mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"Sin datos: símbolo {symbol}")
            mt5.symbol_select(symbol, True)
            start_server = (START + timedelta(hours=offset)).replace(tzinfo=None)
            end_server = (END + timedelta(hours=offset)).replace(tzinfo=None)
            raw = mt5.copy_rates_range(
                symbol, mt5.TIMEFRAME_M1, start_server, end_server
            )
            bars[symbol] = _bars(raw, offset)
            points[symbol] = float(info.point)
            print(symbol, len(bars[symbol]), "bars", "point", points[symbol])
        health_after = broker.health()
    finally:
        broker.shutdown()
    if not health_after.get("identity_ok") or int(health_after.get("login") or 0) != int(
        health_before.get("login") or 0
    ):
        raise RuntimeError("MT5 cambió de identidad")

    rows = []
    for row in trades:
        symbol = row["symbol"]
        frame = bars.get(symbol)
        if frame is None or frame.empty:
            continue
        ts = pd.Timestamp(row["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        after = frame[frame.index > ts]
        if after.empty:
            continue
        # La vela siguiente a la entrada.
        next_bar = after.iloc[:1]
        entry_time = next_bar.index[0]
        forced = _forced(entry_time, row["style"], row["exit_ts"])
        window = after[after.index <= forced]
        if window.empty:
            continue
        entry = float(next_bar.iloc[0]["open"])
        sl_dist = abs(float(row["entry"]) - float(row["sl"]))
        tp_dist = (
            abs(float(row["tp"]) - float(row["entry"])) if row["tp"] else None
        )
        side_ai = str(row["side"])
        twin = _twin_levels(
            entry, entry - sl_dist, entry + (tp_dist or sl_dist), seed=int(row["shadow_seed"])
        )
        # Regla de tendencia: sesión NYSE anterior.
        day = _ny(entry_time).normalize()
        prev = day - pd.Timedelta(days=1)
        while prev.day_of_week >= 5:
            prev -= pd.Timedelta(days=1)
        session = frame[
            (frame.index >= prev.tz_convert("UTC") + pd.Timedelta(hours=14, minutes=30))
            & (frame.index <= prev.tz_convert("UTC") + pd.Timedelta(hours=20, minutes=55))
        ]
        trend_side = None
        if len(session) >= 30:
            trend_side = (
                "buy" if float(session.iloc[-1]["close"]) >= float(session.iloc[0]["open"]) else "sell"
            )
        spread = float(next_bar.iloc[0]["spread"])
        result = {
            "symbol": symbol,
            "side": side_ai,
            "ia": _simulate(
                side_ai, entry, sl_dist, tp_dist, window, forced, points[symbol], spread
            ),
            "shadow": _simulate(
                twin["side"], entry, sl_dist, tp_dist, window, forced, points[symbol], spread
            ),
            "trend": (
                _simulate(
                    trend_side, entry, sl_dist, tp_dist, window, forced, points[symbol], spread
                )
                if trend_side
                else None
            ),
            "always": _simulate(
                side_ai, entry, sl_dist, tp_dist, window, forced, points[symbol], spread
            ),
        }
        rows.append(result)

    def delta(key):
        pairs = [
            (row["ia"], row[key])
            for row in rows
            if row["ia"] is not None and row[key] is not None
        ]
        if not pairs:
            return None
        values = [left - right for left, right in pairs]
        return _bootstrap(values)

    summary = {
        "n_trades": len(trades),
        "n_simulated": len(rows),
        "ia": _bootstrap([row["ia"] for row in rows if row["ia"] is not None]),
        "shadow": _bootstrap([row["shadow"] for row in rows if row["shadow"] is not None]),
        "trend": _bootstrap([row["trend"] for row in rows if row["trend"] is not None]),
        "always": _bootstrap([row["always"] for row in rows if row["always"] is not None]),
        "delta_shadow": delta("shadow"),
        "delta_trend": delta("trend"),
        "delta_always": delta("always"),
        "login_before": health_before.get("login"),
        "login_after": health_after.get("login"),
    }
    verdict = "Sin datos"
    trend = summary["delta_trend"]
    if trend is not None:
        if trend["mean"] >= 0.1 and trend["ci95"][0] > 0:
            verdict = "la IA aporta"
        elif trend["ci95"][0] <= 0 <= trend["ci95"][1]:
            verdict = "no concluyente"
        elif trend["ci95"][1] < 0:
            verdict = "no aporta"

    lines = [
        "# TL3 · Contrafactual de `ai_trader` (T5, M1 MT5)",
        "",
        f"Operaciones cerradas leídas: {len(trades)}; simuladas: {len(rows)}.",
        f"Login MT5: {summary['login_before']} antes / {summary['login_after']} después.",
        "Coste: spread de la vela de entrada + 1 punto total de slippage; "
        "gemela recalculada con `shadow_seed`; regla de tendencia con la "
        "sesión NYSE anterior; cierre forzoso 12:00 NY en scalping.",
        "",
        "## Resultados",
        "",
        "| Benchmark | n | Media R | IC95 |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (
        ("ia", "IA (recalculada)"),
        ("shadow", "Gemela aleatoria"),
        ("trend", "Regla de tendencia"),
        ("always", "Siempre tomar"),
    ):
        item = summary[key]
        if item:
            lines.append(
                f"| {label} | {item['n']} | {item['mean']:.4f} | "
                f"[{item['ci95'][0]:.4f}; {item['ci95'][1]:.4f}] |"
            )
        else:
            lines.append(f"| {label} | Sin datos | — | — |")
    lines += [
        "",
        "## Diferencias (IA − benchmark)",
        "",
        "| Benchmark | n | Δ R | IC95 |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (
        ("delta_shadow", "Gemela aleatoria"),
        ("delta_trend", "Regla de tendencia"),
        ("delta_always", "Siempre tomar"),
    ):
        item = summary[key]
        if item:
            lines.append(
                f"| {label} | {item['n']} | {item['mean']:+.4f} | "
                f"[{item['ci95'][0]:+.4f}; {item['ci95'][1]:+.4f}] |"
            )
        else:
            lines.append(f"| {label} | Sin datos | — | — |")
    lines += [
        "",
        "## Desglose por lado y símbolo (Δ frente a la gemela)",
        "",
        "| Corte | n | Δ R |",
        "|---|---:|---:|",
    ]
    for key in ("side", "symbol"):
        groups = {}
        for row in rows:
            if row["ia"] is None or row["shadow"] is None:
                continue
            groups.setdefault(row[key], []).append(row["ia"] - row["shadow"])
        for value, items in groups.items():
            lines.append(f"| {key}={value} | {len(items)} | {np.mean(items):+.4f} |")
    lines += [
        "",
        f"## Veredicto: **{verdict}**",
        "",
        "Regla TL3_AI_TRADER_AUDIT §5: solo aporta si Δ frente a la tendencia "
        "≥ 0,1 R con IC95 > 0. Si el IC95 incluye 0, el veredicto es no "
        "concluyente. No se tocó `ai_trader.py`.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    Path("C:/Users/PC/AppData/Local/Temp/opencode/t5_summary.json").write_text(
        json.dumps(summary, indent=1, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
