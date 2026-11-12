"""Carril IA discrecional (solo demo): snapshot, propuesta, ejecución y medición.

El LLM elige estrategia, símbolo, timeframe y dirección; los niveles y el lote
los calcula el código. Cada operación real tiene una gemela sombra aleatoria.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from .ai_setups import (
    ALLOWED,
    STRATEGY_TIMEFRAME,
    TIMEFRAMES,
    SetupError,
    plan,
    validate,
)
from .audit import append_hashed
from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .db import connect, init_db, utcnow
from .indicators import atr, ema
from .intraday_costs import asset_costs
from .prop.guard import PropGuard
from .prop.rules import from_yaml
from .trailing import next_stop

CONFIG_PATH = ROOT / "config" / "ai_trader.yaml"
PRAGUE = ZoneInfo("Europe/Prague")
NEW_YORK = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")


class AiTraderError(ValueError):
    pass


def load_config(path: str | Path | None = None) -> dict:
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        raise AiTraderError(f"falta {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AiTraderError("configuración ai_trader inválida")
    out = {
        "account": str(data.get("account") or ""),
        "magic": int(data.get("magic") or 0),
        "universe": [str(item) for item in (data.get("universe") or [])],
        "risk_per_trade": float(data.get("risk_per_trade") or 0.0),
        "max_trades_per_day": int(data.get("max_trades_per_day") or 0),
        "max_open_per_symbol": int(data.get("max_open_per_symbol") or 1),
        "max_open_total": int(data.get("max_open_total") or 1),
        "daily_stop": float(data.get("daily_stop") or 0.0),
        "playbook_version": int(data.get("playbook_version") or 1),
        "enabled": bool(data.get("enabled", False)),
        "allowed": data.get("allowed") or ALLOWED,
        "timeframes": [str(item) for item in (data.get("timeframes") or TIMEFRAMES)],
        "source": str(target),
    }
    if out["account"] != "ftmo_demo":
        raise AiTraderError("el carril solo permite account=ftmo_demo")
    if not out["universe"]:
        raise AiTraderError("universo vacío")
    if out["magic"] <= 0:
        raise AiTraderError("magic inválido")
    if not 0 < out["risk_per_trade"] <= 0.01:
        raise AiTraderError("risk_per_trade debe estar en (0, 1%]")
    if not 1 <= out["max_trades_per_day"] <= 10:
        raise AiTraderError("max_trades_per_day fuera de rango")
    if out["max_open_total"] < 1:
        raise AiTraderError("max_open_total debe ser >= 1")
    if not 0 < out["daily_stop"] <= 0.05:
        raise AiTraderError("daily_stop debe estar en (0, 5%]")
    for tf in out["timeframes"]:
        if tf not in TIMEFRAMES:
            raise AiTraderError(f"timeframe no permitido: {tf}")
    return out


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _sma(series: pd.Series, n: int) -> float:
    value = series.rolling(n).mean().iloc[-1]
    return float(value) if pd.notna(value) else float("nan")


def _rsi(series: pd.Series, n: int) -> float:
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    if down.iloc[-1] == 0:
        return 100.0
    rs = up.iloc[-1] / down.iloc[-1]
    return float(100 - 100 / (1 + rs))


def _daily(h4: pd.DataFrame) -> pd.DataFrame:
    return (
        h4.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )


def _session(now: datetime) -> str:
    hour = _as_utc(now).hour
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 13:
        return "Londres"
    if 13 <= hour < 21:
        return "Nueva York"
    return "Fuera de sesión"


def _quote_rate(broker, instrument) -> float:
    quote = str(getattr(instrument, "quote_ccy", "USD") or "USD").upper()
    if quote == "USD":
        return 1.0
    symbol = str(getattr(instrument, "symbol", "") or "").upper()
    try:
        if symbol.startswith("USD"):
            return float(broker.tick(symbol)["bid"])
        if quote in {"JPY", "CHF", "CAD"}:
            return float(broker.tick(f"USD{quote}")["bid"])
        return 1.0 / float(broker.tick(f"{quote}USD")["bid"])
    except Exception as exc:
        raise AiTraderError(f"cambio {quote}/USD no disponible: {exc}") from exc


def _lane_positions(broker, magic: int) -> list[dict]:
    return [dict(p) for p in (broker.positions() or []) if int(p.get("magic") or 0) == int(magic)]


def _day_start() -> datetime:
    now = datetime.now(PRAGUE)
    local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def _lane_pnl_today(db_path: str | Path, magic: int) -> float:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS pnl FROM ai_trades "
            "WHERE magic = ? AND status='closed' AND exit_ts >= ?",
            (magic, _day_start().isoformat()),
        ).fetchone()
    return float(row["pnl"] or 0.0)


def _trades_today(db_path: str | Path, magic: int) -> int:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM ai_trades WHERE magic=? AND ts>=? "
            "AND status IN ('open','closed')",
            (magic, _day_start().isoformat()),
        ).fetchone()
    return int(row["n"])


def _cell_status(db_path: str | Path, strategy: str, symbol: str, timeframe: str) -> str:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT status FROM ai_cell_state WHERE strategy=? AND symbol=? AND timeframe=?",
            (strategy, symbol, timeframe),
        ).fetchone()
    return str(row["status"]) if row else "active"


def _commission_bps(symbol: str, price: float) -> float | None:
    try:
        cost = asset_costs(symbol)
        return float(cost.commission_bps(pd.Series([price])).iloc[0])
    except Exception:
        return None


def _cost_ratio(symbol: str, price: float, spread: float, stop_distance: float) -> float | None:
    commission = _commission_bps(symbol, price)
    if commission is None or stop_distance <= 0:
        return None
    cost_price = spread + price * (commission + 1.0) / 10_000.0
    return cost_price / stop_distance


def _vwap(bars: pd.DataFrame) -> tuple[float, float]:
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    if "tick_volume" in bars.columns:
        volume = bars["tick_volume"].clip(lower=0)
    elif "real_volume" in bars.columns:
        volume = bars["real_volume"].clip(lower=0)
    else:
        volume = pd.Series(1.0, index=bars.index)
    total = float(volume.sum())
    if total <= 0:
        return float(typical.iloc[-1]), 0.0
    vwap = float((typical * volume).sum() / total)
    var = float((volume * (typical - vwap) ** 2).sum() / total)
    return vwap, math.sqrt(max(var, 0.0))


def snapshot_symbol(broker, symbol: str, config: dict, db_path: str | Path = DEFAULT_DB) -> dict:
    key = str(symbol).upper()
    h4 = broker.rates(symbol, "H4", 3000)
    h1 = broker.rates(symbol, "H1", 800)
    m15 = broker.rates(symbol, "M15", 800)
    for frame in (h4, h1, m15):
        frame.drop(frame.index[frame.index.duplicated()], inplace=True)
        frame.sort_index(inplace=True)
    if len(h4) < 300 or len(h1) < 60 or len(m15) < 60:
        raise AiTraderError(f"{symbol}: Sin datos suficientes")
    d1 = _daily(h4)
    today = pd.Timestamp.now(tz="UTC").normalize()
    d1 = d1[d1.index < today]
    if len(d1) < 55:
        raise AiTraderError(f"{symbol}: Sin datos D1")
    tick = broker.tick(symbol)
    price = (float(tick["bid"]) + float(tick["ask"])) / 2.0
    spread = float(tick["ask"]) - float(tick["bid"])

    m15_atr = float(atr(m15).iloc[-1])
    h1_atr = float(atr(h1).iloc[-1])
    d1_atr = float(atr(d1).iloc[-1])
    vwap, sigma = _vwap(m15[m15.index >= pd.Timestamp.now(tz="UTC").normalize()])
    et_now = datetime.now(NEW_YORK)
    et_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    orb = m15[(m15.index >= et_open.astimezone(timezone.utc)) & (m15.index < (et_open + timedelta(hours=1)).astimezone(timezone.utc))]
    orb_valid = len(orb) >= 4
    orb_high = float(orb["high"].max()) if orb_valid else float("nan")
    orb_low = float(orb["low"].min()) if orb_valid else float("nan")

    mid = _sma(h1["close"], 20)
    sd = float(h1["close"].rolling(20).std(ddof=0).iloc[-1])
    bb_upper, bb_lower = mid + 2 * sd, mid - 2 * sd
    width = (bb_upper - bb_lower) / mid if mid else float("nan")
    mean20 = h1["close"].rolling(20).mean()
    sd20 = h1["close"].rolling(20).std(ddof=0)
    width_series = 4 * sd20 / mean20
    squeeze = bool(pd.notna(width) and width <= float(width_series.tail(120).min()))

    london_start = datetime.now(LONDON).replace(hour=0, minute=0, second=0, microsecond=0)
    asian = h1[(h1.index >= london_start.astimezone(timezone.utc)) & (h1.index < (london_start + timedelta(hours=7)).astimezone(timezone.utc))]
    asian_valid = len(asian) >= 4
    asian_high = float(asian["high"].max()) if asian_valid else float("nan")
    asian_low = float(asian["low"].min()) if asian_valid else float("nan")

    prev = d1.iloc[-1]
    prev_high, prev_low = float(prev["high"]), float(prev["low"])
    prev_mid = (prev_high + prev_low) / 2
    last_h1 = h1.iloc[-1]
    sweep_high = bool(float(last_h1["high"]) > prev_high and float(last_h1["close"]) < prev_high)
    sweep_low = bool(float(last_h1["low"]) < prev_low and float(last_h1["close"]) > prev_low)

    dc20_high = float(d1["high"].rolling(20).max().iloc[-1])
    dc20_low = float(d1["low"].rolling(20).min().iloc[-1])
    dc55_high = float(d1["high"].rolling(55).max().iloc[-1])
    dc55_low = float(d1["low"].rolling(55).min().iloc[-1])
    mother = d1.iloc[-2]
    inside = bool(float(prev["high"]) <= float(mother["high"]) and float(prev["low"]) >= float(mother["low"]))

    costs = {}
    for tf, atr_value in (("M15", m15_atr), ("H1", h1_atr), ("D1", d1_atr)):
        ratio = _cost_ratio(symbol, price, spread, atr_value)
        costs[tf] = round(ratio, 4) if ratio is not None else "Sin datos"

    lane = _lane_positions(broker, config["magic"])
    equity = float(broker.health().get("equity") or 0.0)
    pnl = _lane_pnl_today(db_path, config["magic"])
    return {
        "symbol": symbol,
        "is_index": "US100" in key,
        "price": round(price, 8),
        "spread": round(spread, 8),
        "session": _session(datetime.now(timezone.utc)),
        "cost_r": costs,
        "m15": {
            "atr": round(m15_atr, 8),
            "ema9": round(float(ema(m15["close"], 9).iloc[-1]), 8),
            "ema21": round(float(ema(m15["close"], 21).iloc[-1]), 8),
            "ema50": round(float(ema(m15["close"], 50).iloc[-1]), 8),
            "vwap": round(vwap, 8),
            "vwap_sigma": round(sigma, 8),
            "orb_high": round(orb_high, 8) if orb_valid else "Sin datos",
            "orb_low": round(orb_low, 8) if orb_valid else "Sin datos",
            "orb_valid": orb_valid,
            "close": round(float(m15["close"].iloc[-1]), 8),
        },
        "h1": {
            "atr": round(h1_atr, 8),
            "ema9": round(float(ema(h1["close"], 9).iloc[-1]), 8),
            "ema21": round(float(ema(h1["close"], 21).iloc[-1]), 8),
            "ema50": round(float(ema(h1["close"], 50).iloc[-1]), 8),
            "bb_upper": round(bb_upper, 8),
            "bb_mid": round(mid, 8),
            "bb_lower": round(bb_lower, 8),
            "bb_width": round(width, 6),
            "bb_squeeze": squeeze,
            "asian_high": round(asian_high, 8) if asian_valid else "Sin datos",
            "asian_low": round(asian_low, 8) if asian_valid else "Sin datos",
            "asian_valid": asian_valid,
            "prev_high": round(prev_high, 8),
            "prev_low": round(prev_low, 8),
            "prev_mid": round(prev_mid, 8),
            "sweep_high": sweep_high,
            "sweep_low": sweep_low,
            "open": round(float(last_h1["open"]), 8),
            "high": round(float(last_h1["high"]), 8),
            "low": round(float(last_h1["low"]), 8),
            "close": round(float(last_h1["close"]), 8),
        },
        "d1": {
            "atr": round(d1_atr, 8),
            "sma5": round(_sma(d1["close"], 5), 8),
            "sma20": round(_sma(d1["close"], 20), 8),
            "sma200": round(_sma(d1["close"], 200), 8),
            "rsi2": round(_rsi(d1["close"], 2), 2),
            "dc20_high": round(dc20_high, 8),
            "dc20_low": round(dc20_low, 8),
            "dc55_high": round(dc55_high, 8),
            "dc55_low": round(dc55_low, 8),
            "prev_high": round(prev_high, 8),
            "prev_low": round(prev_low, 8),
            "prev_close": round(float(prev["close"]), 8),
            "mother_high": round(float(mother["high"]), 8),
            "mother_low": round(float(mother["low"]), 8),
            "inside_bar": inside,
        },
        "lane_open": len(lane),
        "lane_open_symbol": sum(1 for p in lane if str(p.get("symbol", "")).upper() == key),
        "trades_today": _trades_today(db_path, config["magic"]),
        "daily_stop_remaining": round(equity * config["daily_stop"] - max(0.0, -pnl), 2),
        "equity": round(equity, 2),
        "magic": config["magic"],
        "playbook_version": config["playbook_version"],
    }


def snapshot(broker, symbols: list[str] | None = None, config: dict | None = None, db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    wanted = [str(item) for item in (symbols or cfg["universe"])]
    payload = {sym: snapshot_symbol(broker, sym, cfg, db_path) for sym in wanted}
    return {"generated_at": utcnow(), "playbook_version": cfg["playbook_version"], "symbols": payload}


def _snapshot_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_payload(payload: dict, config: dict) -> dict:
    if not isinstance(payload, dict):
        raise AiTraderError("propuesta inválida")
    symbol = str(payload.get("symbol") or "").strip()
    universe = {str(item).lower(): str(item) for item in config["universe"]}
    if symbol.lower() not in universe:
        raise AiTraderError(f"símbolo fuera del universo: {symbol}")
    strategy = str(payload.get("strategy") or payload.get("setup") or "").strip()
    if strategy not in STRATEGY_TIMEFRAME:
        raise AiTraderError(f"estrategia desconocida: {strategy}")
    timeframe = str(payload.get("timeframe") or STRATEGY_TIMEFRAME[strategy]).strip().upper()
    if timeframe not in config["timeframes"]:
        raise AiTraderError(f"timeframe no permitido: {timeframe}")
    if STRATEGY_TIMEFRAME[strategy] != timeframe:
        raise AiTraderError(f"{strategy} usa {STRATEGY_TIMEFRAME[strategy]}, no {timeframe}")
    side = str(payload.get("side") or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise AiTraderError("side debe ser buy o sell")
    thesis = str(payload.get("thesis") or "").strip()
    if not thesis or len(thesis) > 300:
        raise AiTraderError("thesis obligatoria y <= 300 caracteres")
    try:
        confidence = int(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AiTraderError("confidence debe ser entero 1-5") from exc
    if not 1 <= confidence <= 5:
        raise AiTraderError("confidence debe estar entre 1 y 5")
    return {
        "symbol": universe[symbol.lower()],
        "strategy": strategy,
        "timeframe": timeframe,
        "side": side,
        "thesis": thesis,
        "confidence": confidence,
    }


def _volume_for_risk(broker, symbol: str, stop_distance: float, risk_usd: float) -> tuple[float, float, float]:
    instrument = broker.instrument(symbol)
    spec = broker.symbol_spec(symbol)
    rate = _quote_rate(broker, instrument)
    risk_per_lot = float(instrument.risk_per_lot(stop_distance, quote_rate=rate))
    if risk_per_lot <= 0:
        raise AiTraderError("riesgo por lote no disponible")
    step = float(spec.get("volume_step") or 0.01)
    minimum = float(spec.get("volume_min") or step)
    maximum = float(spec.get("volume_max") or 0.0)
    lots = math.floor((risk_usd / risk_per_lot) / step + 1e-9) * step
    lots = round(lots, 8)
    if maximum and lots > maximum:
        lots = maximum
    if lots <= 0 or lots < minimum:
        raise AiTraderError(
            f"volumen {lots:.4f} < mínimo {minimum}: stop demasiado ancho "
            f"(riesgo mínimo {minimum * risk_per_lot:.2f} > {risk_usd:.2f})"
        )
    return lots, lots * risk_per_lot, risk_per_lot


def propose(payload: dict, *, broker, config: dict | None = None, settings: Settings | None = None, db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    settings = settings or get_settings()
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    health = broker.health()
    if str(health.get("mode")) != "demo":
        raise AiTraderError("solo demo: la cuenta no es demo")
    item = _validate_payload(payload, cfg)
    assigned = (cfg["allowed"].get(item["symbol"].upper()) or {}).get(item["strategy"])
    if assigned != item["timeframe"]:
        raise AiTraderError(f"{item['strategy']} no asignada a {item['symbol']} ({assigned})")
    if _cell_status(db_path, item["strategy"], item["symbol"], item["timeframe"]) == "paused":
        raise AiTraderError("celda pausada por el scoreboard; requiere reactivación del operador")
    lane = _lane_positions(broker, cfg["magic"])
    if len(lane) >= cfg["max_open_total"]:
        raise AiTraderError(f"máximo de posiciones del carril alcanzado ({cfg['max_open_total']})")
    same = [p for p in lane if str(p.get("symbol", "")).upper() == item["symbol"].upper()]
    if len(same) >= cfg["max_open_per_symbol"]:
        raise AiTraderError(f"{item['symbol']}: ya hay una posición del carril abierta")
    if _trades_today(db_path, cfg["magic"]) >= cfg["max_trades_per_day"]:
        raise AiTraderError("máximo de operaciones del carril alcanzado hoy")
    equity = float(health.get("equity") or 0.0)
    pnl_today = _lane_pnl_today(db_path, cfg["magic"])
    if pnl_today <= -equity * cfg["daily_stop"]:
        raise AiTraderError("stop diario del carril tocado: no se abre hasta el reset de FTMO")

    snap = snapshot_symbol(broker, item["symbol"], cfg, db_path)
    ok, reason = validate(item["strategy"], item["side"], snap)
    if not ok:
        raise AiTraderError(f"setup no válido: {reason}")
    try:
        level = plan(item["strategy"], item["side"], snap)
    except SetupError as exc:
        raise AiTraderError(f"setup no válido: {exc}") from exc
    tick = broker.tick(item["symbol"])
    entry = float(tick["ask"] if item["side"] == "buy" else tick["bid"])
    dist = abs(entry - level.sl)
    sl = level.sl
    tp = level.tp
    if dist <= 0:
        raise AiTraderError("distancia de stop no positiva")
    price = float(snap["price"])
    spec = broker.symbol_spec(item["symbol"])
    min_sl = max(3 * float(snap["spread"]), float(spec.get("stops_level") or 0) * float(spec.get("point") or 0))
    if dist < min_sl - 1e-12:
        raise AiTraderError(f"SL {dist:.5f} < mínimo {min_sl:.5f} (3×spread o stops_level)")
    cost_ratio = _cost_ratio(item["symbol"], price, float(snap["spread"]), dist)
    if cost_ratio is None:
        raise AiTraderError("coste/R Sin datos: comisión no verificada")
    if cost_ratio > 0.10:
        raise AiTraderError(f"coste/R {cost_ratio:.3f} > 0.10")
    risk_usd = equity * cfg["risk_per_trade"]
    lots, real_risk, risk_per_lot = _volume_for_risk(broker, item["symbol"], dist, risk_usd)

    rules = from_yaml("ftmo", settings.prop.phase, account_size=float(settings.prop.account_size))
    guard = PropGuard(rules)
    try:
        state = PropGuard.state_from_equity(rules, broker.equity_series(), initial_balance=rules.account_size, open_positions=len(broker.positions()))
        report = guard.evaluate(state, proposed_lots=lots, risk_per_lot=risk_per_lot, open_risk_usd=0.0, new_position=True)
    except Exception as exc:
        raise AiTraderError(f"PropGuard no disponible: {exc}") from exc
    if not report.allowed:
        raise AiTraderError(f"PropGuard: {report.reason}")

    pid = uuid.uuid4().hex
    now = utcnow()
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_trades"
            "(proposal_id, ts, symbol, setup, side, timeframe, thesis, confidence, "
            " snapshot_hash, playbook_version, entry, sl, tp, volume, risk_usd, "
            " cost_ratio, magic, status, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, now, item["symbol"], item["strategy"], item["side"], item["timeframe"],
                item["thesis"], item["confidence"], _snapshot_hash(snap),
                cfg["playbook_version"], round(entry, 8), round(sl, 8),
                round(tp, 8) if tp is not None else None, lots, round(real_risk, 2),
                round(cost_ratio, 4), cfg["magic"], "proposed", now, now,
            ),
        )
    return {
        "id": pid,
        "status": "proposed",
        "strategy": item["strategy"],
        "snapshot": snap,
        "order": {
            "symbol": item["symbol"],
            "strategy": item["strategy"],
            "timeframe": item["timeframe"],
            "side": item["side"],
            "volume": lots,
            "entry": round(entry, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8) if tp is not None else None,
            "risk_usd": round(real_risk, 2),
            "risk_pct": round(real_risk / equity * 100, 3),
            "rr": level.rr,
            "cost_ratio": round(cost_ratio, 4),
            "magic": cfg["magic"],
        },
    }


def execute(proposal_id: str, *, broker, config: dict | None = None, db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM ai_trades WHERE proposal_id=?", (proposal_id,)).fetchone()
    if row is None:
        raise AiTraderError(f"propuesta no encontrada: {proposal_id}")
    if row["status"] != "proposed":
        raise AiTraderError(f"propuesta en estado {row['status']}, no proposed")
    side = str(row["side"])
    tick = broker.tick(row["symbol"])
    current = float(tick["ask"] if side == "buy" else tick["bid"])
    stop = abs(float(row["entry"]) - float(row["sl"]))
    if stop > 0 and abs(current - float(row["entry"])) > 0.25 * stop:
        raise AiTraderError("el precio se movió > 0,25R desde la propuesta; vuelve a proponer")
    signed = float(row["volume"]) if side == "buy" else -float(row["volume"])
    order = broker.submit_market(
        row["symbol"], signed, sl=float(row["sl"]),
        tp=float(row["tp"]) if row["tp"] is not None else None,
        bot="ai:discrecional", reason=str(row["thesis"])[:400],
        magic=cfg["magic"], dry_run=False,
    )
    now = utcnow()
    seed = int(hashlib.sha256(proposal_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    shadow_side = rng.choice(["buy", "sell"])
    entry = float(row["entry"])
    sl_dist = abs(entry - float(row["sl"]))
    tp_dist = abs(float(row["tp"]) - entry) if row["tp"] is not None else sl_dist
    shadow_sl = entry - sl_dist if shadow_side == "buy" else entry + sl_dist
    shadow_tp = entry + tp_dist if shadow_side == "buy" else entry - tp_dist
    with connect(db_path) as con:
        con.execute(
            "UPDATE ai_trades SET status='open', ticket=?, entry=?, shadow_side=?, "
            "shadow_entry=?, shadow_sl=?, shadow_tp=?, shadow_status='open', "
            "shadow_seed=?, updated_at=? WHERE proposal_id=?",
            (int(order.get("order_id") or 0), round(entry, 8), shadow_side, round(entry, 8),
             round(shadow_sl, 8), round(shadow_tp, 8), seed, now, proposal_id),
        )
        append_hashed(con, "console_actions", {
            "ts": now, "action": "ai_trader_execute",
            "params": json.dumps({"proposal_id": proposal_id, "symbol": row["symbol"],
                                  "strategy": row["strategy"], "timeframe": row["timeframe"],
                                  "side": side, "volume": float(row["volume"])},
                                 ensure_ascii=False, sort_keys=True),
            "result": "executed", "ok": 1, "actor": "opencode",
            "detail": str(row["thesis"])[:400],
        })
    return {"id": proposal_id, "status": "open", "order": order}


def _shadow_sim(row: dict, bars: pd.DataFrame) -> dict:
    side = str(row.get("shadow_side") or "")
    entry = float(row.get("shadow_entry") or row.get("entry") or 0)
    sl = float(row.get("shadow_sl") or row.get("sl") or 0)
    tp = float(row.get("shadow_tp") or row.get("tp") or 0)
    if not side or bars is None or len(bars) < 2 or not tp:
        return {"status": "Sin datos", "r": None}
    short = side == "sell"
    risk = abs(entry - sl)
    if risk <= 0:
        return {"status": "Sin datos", "r": None}
    atr_series = atr(bars)
    best = entry
    for ts, bar in bars.iterrows():
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if short:
            best = min(best, low)
            if high >= sl:
                return {"status": "closed", "r": round((entry - sl) / risk, 4)}
            if low <= tp:
                return {"status": "closed", "r": round((entry - tp) / risk, 4)}
            profit_r = (entry - close) / risk
        else:
            best = max(best, high)
            if low <= sl:
                return {"status": "closed", "r": round((sl - entry) / risk, 4)}
            if high >= tp:
                return {"status": "closed", "r": round((tp - entry) / risk, 4)}
            profit_r = (close - entry) / risk
        new_sl = next_stop(side=side, entry=entry, best=best, atr_value=float(atr_series.loc[ts]),
                           current_sl=sl, profit_r=profit_r, digits=8)
        if new_sl is not None:
            sl = new_sl
    last = float(bars["close"].iloc[-1])
    r = (entry - last) / risk if short else (last - entry) / risk
    return {"status": "open", "r": round(r, 4)}


def manage(*, broker, config: dict | None = None, db_path: str | Path = DEFAULT_DB) -> list[dict]:
    cfg = config or load_config()
    magic = cfg["magic"]
    now = datetime.now(timezone.utc)
    init_db(db_path)
    with connect(db_path) as con:
        rows = {int(r["ticket"]): dict(r) for r in con.execute(
            "SELECT * FROM ai_trades WHERE status='open' AND ticket IS NOT NULL").fetchall()}
    out = []
    for position in _lane_positions(broker, magic):
        ticket = int(position["ticket"])
        row = rows.get(ticket) or {}
        setup = str(row.get("setup") or "")
        timeframe = str(row.get("timeframe") or "H1")
        bars = broker.rates(position["symbol"], timeframe, 500)
        opened = pd.Timestamp(position["time"])
        if opened.tzinfo is None:
            opened = opened.tz_localize("UTC")
        since = bars[bars.index >= opened]
        short = str(position["side"]).lower() == "sell"
        entry = float(position["price_open"])
        sl = float(position["sl"] or 0)
        if sl <= 0:
            continue
        best = float(since["low"].min()) if short and len(since) else (
            float(since["high"].max()) if len(since) else entry)
        tick = broker.tick(position["symbol"])
        price = float(tick["ask"] if short else tick["bid"])
        best = min(best, price) if short else max(best, price)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        profit_r = (entry - price) / risk if short else (price - entry) / risk
        spec = broker.symbol_spec(position["symbol"])
        if setup == "donchian_turtle":
            d1 = _daily(broker.rates(position["symbol"], "H4", 800))
            d1 = d1[d1.index < pd.Timestamp.now(tz="UTC").normalize()]
            channel = float(d1["low"].tail(10).min()) if short is False else float(d1["high"].tail(10).max())
            candidate = channel if not short else channel
            if profit_r >= 0.5:
                candidate = max(candidate, entry) if not short else min(candidate, entry)
        else:
            candidate = next_stop(
                side=position["side"], entry=entry, best=best,
                atr_value=float(atr(bars).iloc[-1]),
                current_sl=sl, profit_r=profit_r,
                digits=int(spec.get("digits") or 2),
                min_distance=float(spec.get("stops_level") or 0) * float(spec.get("point") or 0),
            )
        moved = None
        if candidate is not None and ((short and candidate < sl) or (not short and candidate > sl)):
            try:
                broker.modify_position(ticket, sl=round(candidate, int(spec.get("digits") or 2)))
                moved = round(candidate, int(spec.get("digits") or 2))
            except Exception:
                moved = None
        out.append({"ticket": ticket, "symbol": position["symbol"], "side": position["side"],
                    "setup": setup, "timeframe": timeframe, "profit_r": round(profit_r, 4),
                    "sl": sl, "new_sl": moved})
    sync_closed(broker, magic=magic, db_path=db_path, now=now)
    return out


def sync_closed(broker, *, magic: int, db_path: str | Path = DEFAULT_DB, now: datetime | None = None) -> int:
    moment = _as_utc(now)
    open_tickets = {int(p["ticket"]) for p in (broker.positions() or [])}
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM ai_trades WHERE status='open' AND ticket IS NOT NULL").fetchall()]
    closed = 0
    for row in rows:
        ticket = int(row["ticket"])
        if ticket in open_tickets:
            continue
        try:
            deals = broker.history_deals(datetime.fromisoformat(str(row["ts"])) - timedelta(hours=2), moment + timedelta(hours=1))
        except Exception:
            continue
        rel = [d for d in deals if int(d.get("position_id") or 0) == ticket and int(d.get("magic") or 0) == magic]
        if not rel:
            continue
        pnl = sum(float(d.get("profit") or 0) + float(d.get("swap") or 0) + float(d.get("commission") or 0) for d in rel)
        risk = float(row.get("risk_usd") or 0)
        with connect(db_path) as con:
            con.execute(
                "UPDATE ai_trades SET status='closed', exit_price=?, exit_ts=?, pnl=?, r_multiple=?, updated_at=? WHERE proposal_id=?",
                (float(rel[-1].get("price") or 0), str(rel[-1].get("ts_utc") or moment.isoformat()),
                 round(pnl, 2), round(pnl / risk, 4) if risk else None, utcnow(), row["proposal_id"]),
            )
        closed += 1
    return closed


def _pause_cells(cells: list[dict], db_path: str | Path) -> None:
    init_db(db_path)
    for cell in cells:
        if cell["n"] < 30 or cell["expectancy_r"] is None or cell["shadow_expectancy_r"] is None:
            continue
        if cell["expectancy_r"] < cell["shadow_expectancy_r"]:
            with connect(db_path) as con:
                con.execute(
                    "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, reason, updated_at) "
                    "VALUES(?,?,?,'paused',?,?) ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
                    "status='paused', reason=excluded.reason, updated_at=excluded.updated_at",
                    (cell["strategy"], cell["symbol"], cell["timeframe"],
                     f"expectativa {cell['expectancy_r']:.3f}R < sombra {cell['shadow_expectancy_r']:.3f}R",
                     utcnow()),
                )


def resume_cell(strategy: str, symbol: str, timeframe: str, db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, reason, updated_at) "
            "VALUES(?,?,?,'active',?,?) ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
            "status='active', reason=excluded.reason, updated_at=excluded.updated_at",
            (strategy, symbol, timeframe, "reactivada por el operador", utcnow()),
        )
    return {"strategy": strategy, "symbol": symbol, "timeframe": timeframe, "status": "active"}


def scoreboard(*, broker, config: dict | None = None, db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM ai_trades ORDER BY ts").fetchall()]
    positions = {int(p["ticket"]): p for p in (broker.positions() or [])}
    out = []
    for row in rows:
        real_r = None
        if row["status"] == "closed" and row.get("r_multiple") is not None:
            real_r = float(row["r_multiple"])
        elif row.get("ticket") and int(row["ticket"]) in positions:
            pos = positions[int(row["ticket"])]
            entry = float(row["entry"])
            risk = abs(entry - float(row["sl"]))
            if risk > 0:
                price = float(pos["price_current"])
                real_r = (entry - price) / risk if row["side"] == "sell" else (price - entry) / risk
        shadow = {"status": "Sin datos", "r": None}
        try:
            if row.get("shadow_entry"):
                bars = broker.rates(row["symbol"], str(row.get("timeframe") or "H1"), 800)
                since = bars[bars.index >= pd.Timestamp(row["ts"])]
                shadow = _shadow_sim(row, since)
        except Exception:
            pass
        out.append({"id": row["proposal_id"], "ts": row["ts"], "symbol": row["symbol"],
                    "strategy": row["setup"], "timeframe": row.get("timeframe") or "Sin datos",
                    "side": row["side"], "status": row["status"],
                    "r": round(real_r, 4) if real_r is not None else None,
                    "shadow_r": shadow["r"], "cost_ratio": row.get("cost_ratio")})
    groups: dict[tuple, list] = {}
    for row in out:
        groups.setdefault((row["strategy"], row["symbol"], row["timeframe"]), []).append(row)
    cells = []
    for (strategy, symbol, timeframe), items in sorted(groups.items()):
        rs = [float(i["r"]) for i in items if i["r"] is not None]
        sr = [float(i["shadow_r"]) for i in items if i["shadow_r"] is not None]
        costs = [float(i["cost_ratio"]) for i in items if i["cost_ratio"] is not None]
        cells.append({
            "strategy": strategy, "symbol": symbol, "timeframe": timeframe,
            "n": len(items),
            "hit": round(sum(1 for r in rs if r > 0) / len(rs), 3) if rs else None,
            "avg_r": round(sum(rs) / len(rs), 4) if rs else None,
            "expectancy_r": round(sum(rs) / len(rs), 4) if rs else None,
            "shadow_expectancy_r": round(sum(sr) / len(sr), 4) if sr else None,
            "cost_ratio_avg": round(sum(costs) / len(costs), 4) if costs else None,
            "insufficient": len(items) < 30,
            "cell_status": _cell_status(db_path, strategy, symbol, timeframe),
        })
    _pause_cells(cells, db_path)
    for cell in cells:
        cell["cell_status"] = _cell_status(db_path, cell["strategy"], cell["symbol"], cell["timeframe"])
    return {"trades": out, "cells": cells, "n": len(out)}


def log_no_trade(reason: str, *, symbols: list[str] | None = None, db_path: str | Path = DEFAULT_DB) -> dict:
    text = str(reason or "").strip()
    if not text or len(text) > 500:
        raise AiTraderError("motivo obligatorio y <= 500 caracteres")
    init_db(db_path)
    with connect(db_path) as con:
        append_hashed(con, "console_actions", {
            "ts": utcnow(), "action": "ai_trader_no_trade",
            "params": json.dumps({"symbols": symbols or []}, ensure_ascii=False),
            "result": "no_trade", "ok": 1, "actor": "opencode", "detail": text,
        })
    return {"ok": True, "reason": text}


def panel(db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT proposal_id, ts, symbol, setup, side, timeframe, thesis, confidence, "
            "entry, sl, tp, volume, risk_usd, status, pnl, r_multiple, shadow_side, "
            "shadow_r, cost_ratio FROM ai_trades ORDER BY ts DESC LIMIT 100").fetchall()]
        lessons = [dict(r) for r in con.execute(
            "SELECT id, hypothesis, status FROM lessons WHERE status='proposed' "
            "AND kind='lesson' ORDER BY id DESC LIMIT 10").fetchall()]
        cells = [dict(r) for r in con.execute(
            "SELECT strategy, symbol, timeframe, status, reason FROM ai_cell_state "
            "WHERE status='paused' ORDER BY updated_at DESC").fetchall()]
    opened = [r for r in rows if r["status"] == "open"]
    closed = [r for r in rows if r["status"] == "closed"]
    real = [float(r["r_multiple"]) for r in closed if r["r_multiple"] is not None]
    shadow = [float(r["shadow_r"]) for r in closed if r["shadow_r"] is not None]
    return {"open": opened, "closed": {"n": len(closed),
            "avg_r": round(sum(real) / len(real), 4) if real else None,
            "shadow_avg_r": round(sum(shadow) / len(shadow), 4) if shadow else None},
            "lessons": lessons, "paused": cells, "n": len(rows)}


def review(*, config: dict | None = None, settings: Settings | None = None,
           db_path: str | Path = DEFAULT_DB, days: int = 7) -> dict:
    cfg = config or load_config()
    settings = settings or get_settings()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM ai_trades WHERE status='closed' AND ts>=? ORDER BY ts",
            (since,)).fetchall()]
    report_dir = ROOT / "reports" / "ai_trader"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"review_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    rs = [float(r["r_multiple"]) for r in rows if r["r_multiple"] is not None]
    lines = ["# IA discrecional · revisión semanal",
             f"- Ventana: últimos {days} días · cerradas: {len(rows)}",
             f"- Playbook: v{cfg['playbook_version']}",
             f"- R medio: {sum(rs)/len(rs):+.3f}" if rs else "- R medio: Sin datos",
             f"- PnL: {sum(float(r.get('pnl') or 0) for r in rows):+.2f} USD", "",
             "| id | símbolo | estrategia | tf | lado | R | PnL |", "|---|---|---|---|---|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['proposal_id'][:8]} | {row['symbol']} | {row['setup']} | "
                     f"{row.get('timeframe') or '-'} | {row['side']} | "
                     f"{float(row.get('r_multiple') or 0):+.2f} | {float(row.get('pnl') or 0):+.2f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lessons = []
    if len(rs) >= 5:
        from .learning import create_lesson

        def avg(items): return sum(items) / len(items) if items else 0.0

        conditions = []
        for strategy in sorted({str(r["setup"]) for r in rows}):
            with_ = [float(r["r_multiple"]) for r in rows if r["setup"] == strategy and r["r_multiple"] is not None]
            without = [float(r["r_multiple"]) for r in rows if r["setup"] != strategy and r["r_multiple"] is not None]
            if len(with_) >= 5:
                conditions.append((f"estrategia={strategy}", with_, without))
        for name, with_, without in conditions[:3]:
            diff = avg(with_) - avg(without)
            if abs(diff) < 0.2:
                continue
            lesson = create_lesson(db_path,
                hypothesis=f"En IA discrecional, {name} muestra R medio {avg(with_):+.2f} frente a {avg(without):+.2f} del resto.",
                evidence=json.dumps({"n_with": len(with_), "avg_r_with": round(avg(with_), 4),
                                     "n_without": len(without), "avg_r_without": round(avg(without), 4),
                                     "overall": round(avg(rs), 4)}, ensure_ascii=False, sort_keys=True),
                author="qwen", kind="lesson", settings=settings)
            lessons.append(lesson)
    return {"path": str(path), "lessons": lessons, "n": len(rows)}


def approve_lesson(lesson_id: int, *, config_path: str | Path = CONFIG_PATH,
                   db_path: str | Path = DEFAULT_DB, settings: Settings | None = None) -> dict:
    from .learning import approve

    lesson = approve(db_path, lesson_id, by="operador", settings=settings)
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["playbook_version"] = int(data.get("playbook_version") or 1) + 1
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"lesson": lesson, "playbook_version": data["playbook_version"]}
