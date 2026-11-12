"""Carril IA discrecional (solo demo): snapshot, propuesta, ejecución y medición.

Tres estilos (scalping, intraday y swing) con magic, riesgo, stop diario y
universo propios. El LLM elige estilo, estrategia, símbolo, timeframe y
dirección; los niveles y el lote los calcula el código. Cada orden lleva el
magic del estilo y el carril se mide contra una gemela sombra aleatoria.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import yaml

from .ai_setups import (
    STRATEGY_TIMEFRAME,
    TIMEFRAMES,
    SetupError,
    plan,
    supports,
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
REQUIRED_STYLES = ("scalping", "intraday", "swing")
TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}
TF_SECTION = {"M1": "m1", "M5": "m5", "M15": "m15",
              "H1": "h1", "H4": "h4", "D1": "d1"}
DECISIONS = ("take", "skip", "no_setup")
SOURCES = ("forward", "replay")


class AiTraderError(ValueError):
    pass


class _Reject(AiTraderError):
    """Rechazo con la decisión que debe quedar registrada."""

    def __init__(self, message: str, *, decision: str = "skip",
                 setup_valid: int = 1, snapshot: dict | None = None) -> None:
        super().__init__(message)
        self.decision = decision
        self.setup_valid = int(setup_valid)
        self.snapshot = snapshot


# ------------------------------------------------------------------- config


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_allowed(raw: dict | None) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for symbol, strategies in (raw or {}).items():
        if not isinstance(strategies, dict):
            raise AiTraderError(f"allowed.{symbol} debe ser un objeto")
        entry: dict[str, list[str]] = {}
        for strategy, value in strategies.items():
            if isinstance(value, (list, tuple)):
                frames = [str(item).upper() for item in value]
            else:
                frames = [str(value).upper()]
            entry[str(strategy)] = frames
        out[str(symbol).upper()] = entry
    return out


def _parse_session(raw) -> dict | None:
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise AiTraderError("session debe ser un objeto start/end/tz")
    start = str(raw.get("start") or "").strip()
    end = str(raw.get("end") or "").strip()
    zone = str(raw.get("tz") or "America/New_York").strip()
    try:
        dtime.fromisoformat(start)
        dtime.fromisoformat(end)
        ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise AiTraderError(f"session inválida ({start}-{end} {zone}): {exc}") from exc
    return {"start": start, "end": end, "tz": zone}


def _legacy_style(data: dict) -> dict:
    """Config antigua de un solo carril: se envuelve como un estilo."""
    return {
        "enabled": bool(data.get("enabled", False)),
        "magic": int(data.get("magic") or 0),
        "timeframes": [str(item).upper() for item in (data.get("timeframes") or ["M15", "H1", "D1"])],
        "risk_per_trade": float(data.get("risk_per_trade") or 0.0),
        "daily_stop": float(data.get("daily_stop") or 0.0),
        "max_trades_per_day": int(data.get("max_trades_per_day") or 0),
        "max_cost_r": 0.10,
        "slippage_points": 1.0,
        "universe": [str(item) for item in (data.get("universe") or [])],
        "session": None,
        "max_open_risk": None,
        "allowed": _parse_allowed(data.get("allowed") or {}),
    }


def load_config(path: str | Path | None = None) -> dict:
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        raise AiTraderError(f"falta {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AiTraderError("configuración ai_trader inválida")

    global_raw = data.get("global") or {}
    if not isinstance(global_raw, dict):
        raise AiTraderError("global debe ser un objeto")
    account = str(data.get("account") or global_raw.get("account") or "").strip()
    if account != "ftmo_demo":
        raise AiTraderError("el carril solo permite account=ftmo_demo")
    universe = [str(item) for item in (global_raw.get("universe") or data.get("universe") or [])]
    if not universe:
        raise AiTraderError("universo global vacío")
    canonical = {item.lower(): item for item in universe}

    raw_styles = data.get("styles")
    legacy = False
    if not isinstance(raw_styles, dict) or not raw_styles:
        raw_styles = {"legacy": _legacy_style(data)}
        legacy = True
    required = set() if legacy else set(REQUIRED_STYLES)
    if not required.issubset(raw_styles):
        missing = ", ".join(sorted(required - set(raw_styles)))
        raise AiTraderError(f"faltan estilos en la configuración: {missing}")

    styles: dict[str, dict] = {}
    for name, raw in raw_styles.items():
        if not isinstance(raw, dict):
            raise AiTraderError(f"estilo {name} inválido")
        magic = int(raw.get("magic") or 0)
        if magic <= 0:
            raise AiTraderError(f"{name}: magic inválido")
        frames = [str(item).upper() for item in (raw.get("timeframes") or [])]
        if not frames:
            raise AiTraderError(f"{name}: timeframes vacío")
        for tf in frames:
            if tf not in TIMEFRAMES:
                raise AiTraderError(f"{name}: timeframe no permitido: {tf}")
        risk = float(raw.get("risk_per_trade") or 0.0)
        if not 0 < risk <= 0.02:
            raise AiTraderError(f"{name}: risk_per_trade debe estar en (0, 2%]")
        daily = float(raw.get("daily_stop") or 0.0)
        if not 0 < daily <= 0.05:
            raise AiTraderError(f"{name}: daily_stop debe estar en (0, 5%]")
        trades = raw.get("max_trades_per_day")
        max_trades = None if trades in (None, "") else int(trades)
        if max_trades is not None and not 1 <= max_trades <= 100:
            raise AiTraderError(f"{name}: max_trades_per_day fuera de rango")
        max_cost = _float_or_none(raw.get("max_cost_r"))
        if max_cost is not None and not 0 < max_cost <= 1:
            raise AiTraderError(f"{name}: max_cost_r fuera de rango")
        max_open_risk = _float_or_none(raw.get("max_open_risk"))
        if max_open_risk is not None and not 0 < max_open_risk <= 0.10:
            raise AiTraderError(f"{name}: max_open_risk fuera de rango")
        style_universe = [str(item) for item in (raw.get("universe") or universe)]
        for symbol in style_universe:
            if symbol.lower() not in canonical:
                raise AiTraderError(f"{name}: símbolo fuera del universo global: {symbol}")
        allowed = _parse_allowed(raw.get("allowed") or {})
        for symbol, strategies in allowed.items():
            if symbol.lower() not in canonical:
                raise AiTraderError(f"{name}: allowed con símbolo desconocido: {symbol}")
            if symbol not in {item.upper() for item in style_universe}:
                raise AiTraderError(f"{name}: allowed fuera de su universo: {symbol}")
            for strategy, assigned in strategies.items():
                if strategy not in STRATEGY_TIMEFRAME:
                    raise AiTraderError(f"{name}: estrategia desconocida en allowed: {strategy}")
                for tf in assigned:
                    if tf not in frames:
                        raise AiTraderError(f"{name}: {strategy} usa {tf}, fuera de {frames}")
                    if not supports(strategy, tf):
                        raise AiTraderError(f"{name}: {strategy} no soporta {tf}")
        styles[str(name)] = {
            "name": str(name),
            "enabled": bool(raw.get("enabled", True)),
            "magic": magic,
            "timeframes": frames,
            "risk_per_trade": risk,
            "daily_stop": daily,
            "max_trades_per_day": max_trades,
            "max_cost_r": max_cost,
            "slippage_points": float(raw.get("slippage_points", 1.0)),
            "universe": style_universe,
            "session": _parse_session(raw.get("session")),
            "max_open_risk": max_open_risk,
            "allowed": allowed,
        }

    magics = [int(item["magic"]) for item in styles.values()]
    if len(set(magics)) != len(magics):
        raise AiTraderError("cada estilo debe tener un magic distinto")

    daily_stop = float(global_raw.get("daily_stop") or data.get("daily_stop") or 0.0)
    if not 0 < daily_stop <= 0.10:
        raise AiTraderError("daily_stop global debe estar en (0, 10%]")
    max_open_total = int(global_raw.get("max_open_total") or data.get("max_open_total") or 0)
    if max_open_total < 1:
        raise AiTraderError("max_open_total debe ser >= 1")
    per_symbol = int(
        global_raw.get("max_open_per_symbol_per_style")
        or data.get("max_open_per_symbol")
        or 1
    )
    if per_symbol < 1:
        raise AiTraderError("max_open_per_symbol_per_style debe ser >= 1")
    playbook = int(
        global_raw.get("playbook_version")
        or data.get("playbook_version")
        or 1
    )
    if playbook < 1:
        raise AiTraderError("playbook_version debe ser >= 1")

    allowed_flat: dict[str, dict[str, str]] = {}
    for style in styles.values():
        for symbol, strategies in style["allowed"].items():
            target = allowed_flat.setdefault(symbol, {})
            for strategy, frames in strategies.items():
                target.setdefault(strategy, frames[0])

    out = {
        "version": int(data.get("version") or 2),
        "account": account,
        "enabled": bool(data.get("enabled", False)),
        "global": {
            "account": account,
            "daily_stop": daily_stop,
            "max_open_total": max_open_total,
            "max_open_per_symbol_per_style": per_symbol,
            "universe": universe,
            "playbook_version": playbook,
        },
        "styles": styles,
        "magics": sorted(magics),
        "magic": styles["scalping"]["magic"] if "scalping" in styles else magics[0],
        "universe": universe,
        "daily_stop": daily_stop,
        "max_open_total": max_open_total,
        "max_open_per_symbol": per_symbol,
        "playbook_version": playbook,
        "timeframes": sorted({tf for item in styles.values() for tf in item["timeframes"]}),
        "allowed": allowed_flat,
        "source": str(target),
    }
    return out


def style_config(config: dict, style: str) -> dict:
    item = config["styles"].get(str(style))
    if item is None:
        raise AiTraderError(f"estilo desconocido: {style}")
    return item


def lane_magic_map(config: dict | None = None) -> dict[int, str]:
    cfg = config or load_config()
    return {int(item["magic"]): f"ai:{name}" for name, item in cfg["styles"].items()}


def style_for_magic(config: dict, magic: int) -> str | None:
    for name, item in config["styles"].items():
        if int(item["magic"]) == int(magic):
            return name
    return None


def daily_stop_check(config: dict) -> dict:
    total = sum(float(item["daily_stop"]) for item in config["styles"].values())
    limit = float(config["global"]["daily_stop"])
    warn = total > limit + 1e-12
    detail = (
        f"suma de estilos {total:.2%} vs global {limit:.2%} "
        f"({len(config['styles'])} estilos)"
    )
    if warn:
        detail += " · un estilo puede consumir el stop global"
    return {"sum": total, "global": limit, "warn": warn, "detail": detail}


# --------------------------------------------------------------- utilidades


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


def _prop_rules(settings: Settings | None = None):
    settings = settings or get_settings()
    return from_yaml(
        settings.prop.firm or "ftmo",
        settings.prop.phase,
        account_size=float(settings.prop.account_size),
    )


def _reset_start(settings: Settings | None = None) -> datetime:
    """Inicio del día según el reset de FTMO (``prop/rules.py``)."""
    try:
        rules = _prop_rules(settings)
        zone_name = rules.reset_tz or "Europe/Prague"
        raw_time = rules.reset_time or "00:00"
    except Exception:
        zone_name = (settings.prop.reset_tz if settings else None) or "Europe/Prague"
        raw_time = "00:00"
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = PRAGUE
    try:
        hour, minute = (int(part) for part in raw_time.split(":", 1))
    except ValueError:
        hour, minute = 0, 0
    now = datetime.now(zone)
    local = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local > now:
        local -= timedelta(days=1)
    return local.astimezone(timezone.utc)


def _day_start(settings: Settings | None = None) -> datetime:
    return _reset_start(settings)


def _reset_date(settings: Settings | None = None) -> str:
    return _reset_start(settings).date().isoformat()


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


def _floating_today(positions: list[dict], magic: int,
                    settings: Settings | None = None) -> float:
    """Flotante de posiciones abiertas hoy; las antiguas ya contaron su día."""
    start = _day_start(settings)
    total = 0.0
    for position in positions:
        if int(position.get("magic") or 0) != int(magic):
            continue
        stamp = position.get("time")
        if isinstance(stamp, datetime) and _as_utc(stamp) < start:
            continue
        total += float(position.get("profit") or 0.0)
    return total


def _all_lane_positions(broker, config: dict) -> list[dict]:
    wanted = {int(item) for item in config["magics"]}
    return [dict(p) for p in (broker.positions() or []) if int(p.get("magic") or 0) in wanted]


def _lane_pnl_today(
    db_path: str | Path, magic: int, settings: Settings | None = None
) -> float:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS pnl FROM ai_trades "
            "WHERE magic = ? AND status='closed' AND exit_ts >= ?",
            (magic, _day_start(settings).isoformat()),
        ).fetchone()
    return float(row["pnl"] or 0.0)


def _trades_today(
    db_path: str | Path, magic: int, settings: Settings | None = None
) -> int:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM ai_trades WHERE magic=? AND ts>=? "
            "AND status IN ('open','closed')",
            (magic, _day_start(settings).isoformat()),
        ).fetchone()
    return int(row["n"])


def _open_risk(db_path: str | Path, magic: int) -> float:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(SUM(risk_usd), 0) AS risk FROM ai_trades "
            "WHERE magic=? AND status='open'",
            (magic,),
        ).fetchone()
    return float(row["risk"] or 0.0)


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


def _cost_ratio(
    symbol: str,
    price: float,
    spread: float,
    stop_distance: float,
    *,
    slippage_points: float = 0.0,
    point: float | None = None,
    slippage_bps: float | None = None,
) -> float | None:
    """Coste/R en precio: spread + comisión FTMO + slippage del estilo.

    Con ``point`` se usa el slippage en puntos del símbolo (el carril nuevo).
    Sin ``point`` se conserva el supuesto antiguo de 1 bp por lado.
    """
    commission = _commission_bps(symbol, price)
    if commission is None or stop_distance <= 0:
        return None
    if point is not None:
        slippage_price = max(0.0, float(slippage_points)) * float(point)
    else:
        basis = 1.0 if slippage_bps is None else float(slippage_bps)
        slippage_price = price * basis / 10_000.0
    cost_price = spread + price * commission / 10_000.0 + slippage_price
    return cost_price / stop_distance


def _vwap(bars: pd.DataFrame) -> tuple[float, float]:
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    volume = None
    for column in ("tick_volume", "volume", "real_volume"):
        if column in bars.columns:
            volume = bars[column].clip(lower=0)
            break
    if volume is None:
        volume = pd.Series(1.0, index=bars.index)
    total = float(volume.sum())
    if total <= 0:
        return float(typical.iloc[-1]), 0.0
    vwap = float((typical * volume).sum() / total)
    var = float((volume * (typical - vwap) ** 2).sum() / total)
    return vwap, math.sqrt(max(var, 0.0))


def _round_or_none(value: float | None, digits: int = 8):
    if value is None:
        return "Sin datos"
    if not math.isfinite(float(value)):
        return "Sin datos"
    return round(float(value), digits)


def _block_from_bars(bars: pd.DataFrame, timeframe: str, d1: pd.DataFrame,
                     price: float, now: datetime) -> dict:
    """Indicadores comunes de un timeframe. No inventa: si falta, Sin datos.

    Solo usa barras cerradas hasta ``now``: truncar el histórico a esa hora
    produce exactamente el mismo bloque (sin lookahead).
    """
    if bars is None or len(bars) < 55:
        raise AiTraderError(f"Sin datos {timeframe}")
    moment = _as_utc(now)
    bars = bars[bars.index <= moment]
    if len(bars) < 55:
        raise AiTraderError(f"Sin datos {timeframe}")
    if d1 is not None:
        # Solo días completos: el día en curso aún no ha cerrado.
        d1 = d1[d1.index < pd.Timestamp(moment).normalize()]
    if d1 is None or len(d1) < 1:
        raise AiTraderError(f"Sin datos {timeframe} D1")
    minutes = TF_MINUTES.get(timeframe, 15)
    atr_value = float(atr(bars).iloc[-1])
    mid = _sma(bars["close"], 20)
    sd = float(bars["close"].rolling(20).std(ddof=0).iloc[-1])
    bb_upper, bb_lower = mid + 2 * sd, mid - 2 * sd
    width = (bb_upper - bb_lower) / mid if mid else float("nan")
    mean20 = bars["close"].rolling(20).mean()
    sd20 = bars["close"].rolling(20).std(ddof=0)
    width_series = 4 * sd20 / mean20
    squeeze = bool(pd.notna(width) and width <= float(width_series.tail(120).min()))

    # VWAP de la sesión de Nueva York (desde la apertura 09:30 NY).
    ny_open = moment.astimezone(NEW_YORK).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    session_bars = bars[bars.index >= ny_open.astimezone(timezone.utc)]
    if len(session_bars) == 0:
        session_bars = bars.tail(1)
    vwap, sigma = _vwap(session_bars)

    et_now = moment.astimezone(NEW_YORK)
    et_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    expected_orb = max(1, 60 // minutes)
    orb = bars[(bars.index >= et_open.astimezone(timezone.utc))
               & (bars.index < (et_open + timedelta(hours=1)).astimezone(timezone.utc))]
    orb_complete = moment >= (et_open + timedelta(hours=1)).astimezone(timezone.utc)
    orb_valid = orb_complete and len(orb) >= expected_orb
    orb_high = float(orb["high"].max()) if orb_valid else float("nan")
    orb_low = float(orb["low"].min()) if orb_valid else float("nan")

    london_start = moment.astimezone(LONDON).replace(hour=0, minute=0, second=0, microsecond=0)
    expected_asian = max(1, 420 // minutes)
    asian = bars[(bars.index >= london_start.astimezone(timezone.utc))
                 & (bars.index < (london_start + timedelta(hours=7)).astimezone(timezone.utc))]
    asian_complete = moment >= (london_start + timedelta(hours=7)).astimezone(timezone.utc)
    asian_valid = asian_complete and len(asian) >= expected_asian
    asian_high = float(asian["high"].max()) if asian_valid else float("nan")
    asian_low = float(asian["low"].min()) if asian_valid else float("nan")

    prev = d1.iloc[-1]
    prev_high, prev_low = float(prev["high"]), float(prev["low"])
    prev_mid = (prev_high + prev_low) / 2
    last = bars.iloc[-1]
    sweep_high = bool(float(last["high"]) > prev_high and float(last["close"]) < prev_high)
    sweep_low = bool(float(last["low"]) < prev_low and float(last["close"]) > prev_low)

    block = {
        "atr": _round_or_none(atr_value),
        "sma20": _round_or_none(mid),
        "ema9": _round_or_none(float(ema(bars["close"], 9).iloc[-1])),
        "ema21": _round_or_none(float(ema(bars["close"], 21).iloc[-1])),
        "ema50": _round_or_none(float(ema(bars["close"], 50).iloc[-1])),
        "bb_upper": _round_or_none(bb_upper),
        "bb_mid": _round_or_none(mid),
        "bb_lower": _round_or_none(bb_lower),
        "bb_width": _round_or_none(width, 6),
        "bb_squeeze": squeeze,
        "vwap": _round_or_none(vwap),
        "vwap_sigma": _round_or_none(sigma),
        "orb_high": _round_or_none(orb_high if orb_valid else None),
        "orb_low": _round_or_none(orb_low if orb_valid else None),
        "orb_valid": orb_valid,
        "asian_high": _round_or_none(asian_high if asian_valid else None),
        "asian_low": _round_or_none(asian_low if asian_valid else None),
        "asian_valid": asian_valid,
        "prev_high": round(prev_high, 8),
        "prev_low": round(prev_low, 8),
        "prev_mid": round(prev_mid, 8),
        "sweep_high": sweep_high,
        "sweep_low": sweep_low,
        "open": round(float(last["open"]), 8),
        "high": round(float(last["high"]), 8),
        "low": round(float(last["low"]), 8),
        "close": round(float(last["close"]), 8),
    }
    if timeframe in {"H4", "D1"} and len(bars) >= 3:
        prev_bar, mother = bars.iloc[-2], bars.iloc[-3]
        block.update({
            "mother_high": round(float(mother["high"]), 8),
            "mother_low": round(float(mother["low"]), 8),
            "inside_bar": bool(
                float(prev_bar["high"]) <= float(mother["high"])
                and float(prev_bar["low"]) >= float(mother["low"])
            ),
        })
    if timeframe == "D1":
        block.update({
            "sma5": _round_or_none(_sma(d1["close"], 5)),
            "sma20": _round_or_none(_sma(d1["close"], 20)),
            "sma200": _round_or_none(_sma(d1["close"], 200)),
            "rsi2": round(_rsi(d1["close"], 2), 2),
            "dc20_high": round(float(d1["high"].rolling(20).max().iloc[-1]), 8),
            "dc20_low": round(float(d1["low"].rolling(20).min().iloc[-1]), 8),
            "dc55_high": round(float(d1["high"].rolling(55).max().iloc[-1]), 8),
            "dc55_low": round(float(d1["low"].rolling(55).min().iloc[-1]), 8),
            "prev_close": round(float(prev["close"]), 8),
        })
    return block


def _daily_block(d1: pd.DataFrame) -> dict:
    prev = d1.iloc[-1]
    mother = d1.iloc[-2]
    price = float(prev["close"])
    return {
        "atr": _round_or_none(float(atr(d1).iloc[-1])),
        "sma5": _round_or_none(_sma(d1["close"], 5)),
        "sma20": _round_or_none(_sma(d1["close"], 20)),
        "sma200": _round_or_none(_sma(d1["close"], 200)),
        "rsi2": round(_rsi(d1["close"], 2), 2),
        "dc20_high": round(float(d1["high"].rolling(20).max().iloc[-1]), 8),
        "dc20_low": round(float(d1["low"].rolling(20).min().iloc[-1]), 8),
        "dc55_high": round(float(d1["high"].rolling(55).max().iloc[-1]), 8),
        "dc55_low": round(float(d1["low"].rolling(55).min().iloc[-1]), 8),
        "prev_high": round(float(prev["high"]), 8),
        "prev_low": round(float(prev["low"]), 8),
        "prev_close": round(float(prev["close"]), 8),
        "mother_high": round(float(mother["high"]), 8),
        "mother_low": round(float(mother["low"]), 8),
        "inside_bar": bool(
            float(prev["high"]) <= float(mother["high"])
            and float(prev["low"]) >= float(mother["low"])
        ),
        "open": round(float(prev["open"]), 8),
        "high": round(float(prev["high"]), 8),
        "low": round(float(prev["low"]), 8),
        "close": round(price, 8),
        "vwap": round(price, 8),
        "vwap_sigma": 0.0,
        "ema9": _round_or_none(float(ema(d1["close"], 9).iloc[-1])),
        "ema21": _round_or_none(float(ema(d1["close"], 21).iloc[-1])),
        "ema50": _round_or_none(float(ema(d1["close"], 50).iloc[-1])),
        "bb_upper": "Sin datos",
        "bb_mid": "Sin datos",
        "bb_lower": "Sin datos",
        "bb_width": "Sin datos",
        "bb_squeeze": False,
        "orb_high": "Sin datos",
        "orb_low": "Sin datos",
        "orb_valid": False,
        "asian_high": "Sin datos",
        "asian_low": "Sin datos",
        "asian_valid": False,
        "prev_mid": round((float(prev["high"]) + float(prev["low"])) / 2, 8),
        "sweep_high": False,
        "sweep_low": False,
    }


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.drop(frame.index[frame.index.duplicated()])
    return frame.sort_index()


def _safe_rates(broker, symbol: str, timeframe: str, count: int) -> pd.DataFrame | None:
    """Velas del bróker; si el offset no se puede confirmar, Sin datos."""
    try:
        frame = broker.rates(symbol, timeframe, count)
    except Exception:
        return None
    if frame is None or len(frame) == 0:
        return None
    return _clean(frame)


def _empty_block(reason: str) -> dict:
    return {
        "error": reason,
        "atr": "Sin datos", "sma20": "Sin datos",
        "ema9": "Sin datos", "ema21": "Sin datos",
        "ema50": "Sin datos", "bb_upper": "Sin datos", "bb_mid": "Sin datos",
        "bb_lower": "Sin datos", "bb_width": "Sin datos", "bb_squeeze": False,
        "vwap": "Sin datos", "vwap_sigma": "Sin datos",
        "orb_high": "Sin datos", "orb_low": "Sin datos", "orb_valid": False,
        "asian_high": "Sin datos", "asian_low": "Sin datos", "asian_valid": False,
        "prev_high": "Sin datos", "prev_low": "Sin datos", "prev_mid": "Sin datos",
        "sweep_high": False, "sweep_low": False,
        "open": "Sin datos", "high": "Sin datos", "low": "Sin datos",
        "close": "Sin datos",
    }


def session_open(style: dict, now: datetime | None = None) -> bool | None:
    """True/False si el estilo tiene ventana; None si opera 24 h."""
    window = style.get("session")
    if not window:
        return None
    zone = ZoneInfo(window["tz"])
    local = _as_utc(now).astimezone(zone)
    start = dtime.fromisoformat(window["start"])
    end = dtime.fromisoformat(window["end"])
    current = local.time()
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def snapshot_symbol(broker, symbol: str, config: dict,
                    db_path: str | Path = DEFAULT_DB,
                    style: str | None = None) -> dict:
    key = str(symbol).upper()
    counts = {"M1": 20_000, "M5": 6_000, "M15": 2_000, "H1": 1_000, "H4": 3_000}
    frames = {
        tf: _safe_rates(broker, symbol, tf, count)
        for tf, count in counts.items()
    }
    tick = broker.tick(symbol)
    price = (float(tick["bid"]) + float(tick["ask"])) / 2.0
    spread = float(tick["ask"]) - float(tick["bid"])
    now = datetime.now(timezone.utc)

    d1 = None
    if frames["H4"] is not None and len(frames["H4"]) >= 300:
        raw_daily = _daily(frames["H4"])
        today = pd.Timestamp.now(tz="UTC").normalize()
        raw_daily = raw_daily[raw_daily.index < today]
        if len(raw_daily) >= 55:
            d1 = raw_daily

    blocks = {}
    for tf, bars in frames.items():
        if bars is None or len(bars) < 55:
            blocks[tf] = _empty_block(f"{symbol} {tf}")
            continue
        if d1 is None:
            blocks[tf] = _empty_block(f"{symbol} D1")
            continue
        blocks[tf] = _block_from_bars(bars, tf, d1, price, now)
    blocks["D1"] = _daily_block(d1) if d1 is not None else _empty_block(f"{symbol} D1")

    spec = broker.symbol_spec(symbol)
    point = float(spec.get("point") or 0.0)
    slip = 1.0
    if style and style in config["styles"]:
        slip = float(config["styles"][style]["slippage_points"])
    costs = {}
    for tf in TIMEFRAMES:
        raw_atr = blocks[tf].get("atr")
        try:
            atr_value = float(raw_atr)
        except (TypeError, ValueError):
            atr_value = 0.0
        ratio = _cost_ratio(
            symbol, price, spread, atr_value,
            slippage_points=slip, point=point,
        ) if point and atr_value > 0 else None
        costs[tf] = round(ratio, 4) if ratio is not None else "Sin datos"

    positions = _all_lane_positions(broker, config)
    equity = float(broker.health().get("equity") or 0.0)
    style_payload = {}
    total_today = 0
    for name, item in config["styles"].items():
        lane = [p for p in positions if int(p.get("magic") or 0) == int(item["magic"])]
        same = [p for p in lane if str(p.get("symbol", "")).upper() == key]
        pnl = _lane_pnl_today(db_path, item["magic"])
        pnl += _floating_today(lane, item["magic"])
        today_trades = _trades_today(db_path, item["magic"])
        total_today += today_trades
        limit = equity * item["daily_stop"]
        style_payload[name] = {
            "magic": item["magic"],
            "risk_per_trade": item["risk_per_trade"],
            "daily_stop": item["daily_stop"],
            "max_trades_per_day": item["max_trades_per_day"],
            "max_cost_r": item["max_cost_r"],
            "timeframes": item["timeframes"],
            "session_open": session_open(item),
            "lane_open": len(lane),
            "lane_open_symbol": len(same),
            "trades_today": today_trades,
            "pnl_today": round(pnl, 2),
            "daily_stop_remaining": round(limit - max(0.0, -pnl), 2),
            "daily_stop_hit": bool(pnl <= -limit + 1e-9),
            "cost_r": {tf: costs.get(tf) for tf in item["timeframes"]},
        }

    style_pnl = sum(float(item["pnl_today"]) for item in style_payload.values())
    global_limit = equity * config["global"]["daily_stop"]
    payload = {
        "symbol": symbol,
        "is_index": "US100" in key,
        "price": round(price, 8),
        "spread": round(spread, 8),
        "point": point,
        "now": now.isoformat(),
        "session": _session(now),
        "cost_r": costs,
        "styles": style_payload,
        "active_style": style,
        "lane_open": len(positions),
        "lane_open_symbol": sum(1 for p in positions if str(p.get("symbol", "")).upper() == key),
        "trades_today": total_today,
        "daily_stop_remaining": round(global_limit - max(0.0, -style_pnl), 2),
        "daily_stop_hit": bool(style_pnl <= -global_limit + 1e-9),
        "equity": round(equity, 2),
        "magic": config.get("magic"),
        "magics": config["magics"],
        "playbook_version": config["playbook_version"],
    }
    for tf, block in blocks.items():
        payload[TF_SECTION[tf]] = block
    return payload


def snapshot(broker, symbols: list[str] | None = None,
             config: dict | None = None,
             db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    wanted = [str(item) for item in (symbols or cfg["universe"])]
    payload = {sym: snapshot_symbol(broker, sym, cfg, db_path) for sym in wanted}
    return {
        "generated_at": utcnow(),
        "account": cfg["account"],
        "playbook_version": cfg["playbook_version"],
        "magics": cfg["magics"],
        "global": cfg["global"],
        "styles": {
            name: {
                "magic": item["magic"],
                "risk_per_trade": item["risk_per_trade"],
                "daily_stop": item["daily_stop"],
                "max_trades_per_day": item["max_trades_per_day"],
                "max_cost_r": item["max_cost_r"],
                "universe": item["universe"],
                "timeframes": item["timeframes"],
                "session": item["session"],
                "session_open": session_open(item),
            }
            for name, item in cfg["styles"].items()
        },
        "symbols": payload,
    }


# --------------------------------------------------------- snapshot por estilo

# Campos que necesita cada estrategia en su timeframe. El snapshot compacto
# solo manda lo que la estrategia asignada usa; el resto se queda fuera.
STRATEGY_FIELDS = {
    "orb_ny": ("atr", "orb_high", "orb_low", "orb_valid"),
    "vwap_reversion": ("atr", "vwap", "vwap_sigma"),
    "bollinger_squeeze": (
        "atr", "bb_upper", "bb_mid", "bb_lower", "bb_width", "bb_squeeze", "close",
    ),
    "liquidity_sweep": (
        "atr", "prev_high", "prev_low", "prev_mid", "sweep_high", "sweep_low",
        "high", "low", "close",
    ),
    "london_breakout": ("atr", "asian_high", "asian_low", "asian_valid"),
    "ema_pullback": (
        "atr", "ema9", "ema21", "ema50", "high", "low", "open", "close",
    ),
    "rsi2_connors": ("atr", "sma5", "sma200", "rsi2", "close"),
    "donchian_turtle": (
        "atr", "dc20_high", "dc20_low", "dc55_high", "dc55_low", "close",
    ),
    "inside_bar": ("atr", "mother_high", "mother_low", "inside_bar", "close"),
    "trend_pullback": ("atr", "sma20", "high", "low", "close"),
}

# Secciones adicionales que una estrategia mira fuera de su timeframe.
STRATEGY_EXTRA = {
    "trend_pullback": {"d1": ("close", "sma200")},
}


def _compact(value, digits: int = 5):
    if value in (None, "", "Sin datos"):
        return "Sin datos"
    if isinstance(value, bool):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number):
        return "Sin datos"
    return round(number, digits)


def _block_value(block: dict, key: str):
    value = (block or {}).get(key)
    if value in (None, "", "Sin datos"):
        return "Sin datos"
    return _compact(value)


def _trend_label(block: dict, *, d1: bool = False) -> str:
    try:
        if d1:
            close = float(block["close"])
            sma200 = float(block["sma200"])
        else:
            e9, e21, e50 = (float(block[key]) for key in ("ema9", "ema21", "ema50"))
    except (KeyError, TypeError, ValueError):
        return "Sin datos"
    if d1:
        return "up" if close > sma200 else ("down" if close < sma200 else "flat")
    if e9 > e21 > e50:
        return "up"
    if e9 < e21 < e50:
        return "down"
    return "flat"


def _style_data(snap: dict, strategies: dict[str, list[str]]) -> dict:
    """Datos mínimos por símbolo para las estrategias asignadas al estilo."""
    data: dict = {}
    for strategy, frames in strategies.items():
        for tf in frames:
            section = TF_SECTION.get(tf)
            if section is None:
                continue
            block = snap.get(section) or {}
            bucket = data.setdefault(section, {})
            for field in STRATEGY_FIELDS.get(strategy, ()):  # type: ignore[arg-type]
                bucket[field] = _block_value(block, field)
            for extra_section, fields in STRATEGY_EXTRA.get(strategy, {}).items():
                extra_block = snap.get(extra_section) or {}
                extra_bucket = data.setdefault(extra_section, {})
                for field in fields:
                    extra_bucket[field] = _block_value(extra_block, field)
    data["trend_d1"] = _trend_label(snap.get("d1") or {}, d1=True)
    data["trend_h4"] = _trend_label(snap.get("h4") or {})
    if "d1" in data:
        data["d1"].setdefault("sma200", _block_value(snap.get("d1") or {}, "sma200"))
    return data


def _style_setups(snap: dict, strategies: dict[str, list[str]]) -> list[dict]:
    """Setups válidos ahora, calculados por el código (nunca por el LLM)."""
    out: list[dict] = []
    for strategy, frames in strategies.items():
        for tf in frames:
            for side in ("buy", "sell"):
                try:
                    ok, _reason = validate(strategy, side, snap, tf)
                    if not ok:
                        continue
                    level = plan(strategy, side, snap, tf)
                except (SetupError, KeyError, TypeError, ValueError):
                    continue
                out.append(
                    {
                        "strategy": strategy,
                        "timeframe": tf,
                        "side": side,
                        "entry": _compact(level.entry),
                        "sl": _compact(level.sl),
                        "tp": _compact(level.tp) if level.tp is not None else None,
                        "rr": _compact(level.rr, 3) if level.rr is not None else None,
                    }
                )
    return out


def _events_24h(db_path: str | Path, now: datetime) -> list[dict] | str:
    start = _as_utc(now)
    end = start + timedelta(hours=24)
    try:
        init_db(db_path)
        with connect(db_path) as con:
            rows = con.execute(
                "SELECT event, ts_utc, importance FROM macro_events "
                "WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc LIMIT 12",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
    except Exception:
        return "Sin datos"
    return [
        {
            "event": str(row["event"]),
            "ts_utc": str(row["ts_utc"]),
            "importance": str(row["importance"] or "medium"),
        }
        for row in rows
    ]


def snapshot_style(broker, style: str, symbols: list[str] | None = None,
                   config: dict | None = None,
                   db_path: str | Path = DEFAULT_DB) -> dict:
    """Snapshot compacto (<= 3.000 tokens) de un estilo."""
    cfg = config or load_config()
    item = style_config(cfg, style)
    init_db(db_path)
    assigned = item["allowed"]
    if symbols:
        wanted = [str(symbol) for symbol in symbols]
    elif assigned:
        wanted = sorted(assigned)
    else:
        wanted = list(item["universe"])
    canonical = {str(symbol).lower(): str(symbol) for symbol in cfg["universe"]}

    now = datetime.now(timezone.utc)
    positions = _all_lane_positions(broker, cfg)
    lane = [
        position for position in positions
        if int(position.get("magic") or 0) == int(item["magic"])
    ]
    pnl = _lane_pnl_today(db_path, item["magic"]) + _floating_today(lane, item["magic"])
    equity = float(broker.health().get("equity") or 0.0)
    limit = equity * float(item["daily_stop"])
    open_risk = _open_risk(db_path, item["magic"])
    max_open_risk = item["max_open_risk"]
    trades_today = _trades_today(db_path, item["magic"])

    payload: dict = {
        "generated_at": utcnow(),
        "style": style,
        "magic": item["magic"],
        "playbook_version": cfg["playbook_version"],
        "session_open": session_open(item),
        "budget": {
            "equity": round(equity, 2),
            "risk_per_trade": item["risk_per_trade"],
            "risk_usd": round(equity * float(item["risk_per_trade"]), 2),
            "daily_stop": item["daily_stop"],
            "pnl_today": round(pnl, 2),
            "stop_remaining_usd": round(limit - max(0.0, -pnl), 2),
            "stop_hit": bool(limit > 0 and pnl <= -limit + 1e-9),
            "trades_today": trades_today,
            "max_trades_per_day": item["max_trades_per_day"],
            "open_risk_usd": round(open_risk, 2),
            "max_open_risk": max_open_risk,
            "max_open_risk_remaining": (
                round(max(0.0, equity * float(max_open_risk) - open_risk), 2)
                if max_open_risk is not None else None
            ),
        },
        "symbols": {},
        "positions": [
            {
                "ticket": position.get("ticket"),
                "symbol": position.get("symbol"),
                "side": position.get("side"),
                "volume": position.get("volume"),
                "profit": _compact(position.get("profit"), 2),
            }
            for position in lane
        ],
        "events_24h": _events_24h(db_path, now),
    }
    if assigned:
        payload["allowed"] = {
            canonical.get(symbol.lower(), symbol): {
                strategy: list(frames) for strategy, frames in strategies.items()
            }
            for symbol, strategies in assigned.items()
        }

    for symbol in wanted:
        key = symbol.upper()
        if key.lower() not in canonical:
            raise AiTraderError(f"símbolo fuera del universo: {symbol}")
        canonical_symbol = canonical[key.lower()]
        if canonical_symbol.upper() not in {s.upper() for s in item["universe"]}:
            raise AiTraderError(f"{canonical_symbol} fuera del universo de {style}")
        snap = snapshot_symbol(broker, canonical_symbol, cfg, db_path, style=style)
        strategies = assigned.get(key, {})
        used = sorted({tf for frames in strategies.values() for tf in frames})
        payload["symbols"][canonical_symbol] = {
            "price": _compact(snap.get("price")),
            "spread": _compact(snap.get("spread")),
            "cost_r": {
                tf: (snap.get("cost_r") or {}).get(tf, "Sin datos")
                for tf in (used or item["timeframes"])
            },
            "data": _style_data(snap, strategies),
            "setups": _style_setups(snap, strategies),
        }

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    estimate = max(1, math.ceil(len(text) / 4))
    if estimate > 3000 and isinstance(payload["events_24h"], list):
        # Recorte conservador: primero los eventos, nunca los niveles.
        payload["events_24h"] = payload["events_24h"][:5]
        payload["truncated"] = True
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        estimate = max(1, math.ceil(len(text) / 4))
    payload["token_estimate"] = estimate
    if estimate > 3000:
        raise AiTraderError(
            f"snapshot de {style} supera 3000 tokens ({estimate}); reduce --symbols"
        )
    return payload


def _snapshot_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ validación


def _infer_style(config: dict, symbol: str, strategy: str, timeframe: str) -> str:
    matches = [
        name for name, item in config["styles"].items()
        if timeframe in item["allowed"].get(symbol.upper(), {}).get(strategy, [])
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AiTraderError(f"{strategy} no asignada a {symbol} para {timeframe}")
    raise AiTraderError("style obligatorio: la combinación está en varios estilos")


def _validate_payload(payload: dict, config: dict) -> dict:
    if not isinstance(payload, dict):
        raise AiTraderError("propuesta inválida")
    symbol = str(payload.get("symbol") or "").strip()
    universe = {str(item).lower(): str(item) for item in config["universe"]}
    if symbol.lower() not in universe:
        raise AiTraderError(f"símbolo fuera del universo: {symbol}")
    canonical = universe[symbol.lower()]
    strategy = str(payload.get("strategy") or payload.get("setup") or "").strip()
    if strategy not in STRATEGY_TIMEFRAME:
        raise AiTraderError(f"estrategia desconocida: {strategy}")
    timeframe = str(
        payload.get("timeframe") or STRATEGY_TIMEFRAME[strategy]
    ).strip().upper()
    if not supports(strategy, timeframe):
        raise AiTraderError(f"{strategy} no soporta {timeframe}")
    raw_style = str(payload.get("style") or "").strip()
    style = raw_style or _infer_style(config, canonical, strategy, timeframe)
    item = style_config(config, style)
    if not item["enabled"]:
        raise AiTraderError(f"estilo {style} deshabilitado")
    if canonical.upper() not in {s.upper() for s in item["universe"]}:
        raise AiTraderError(f"{canonical} fuera del universo de {style}")
    allowed = item["allowed"].get(canonical.upper(), {}).get(strategy, [])
    if not allowed:
        raise AiTraderError(f"{strategy} no asignada a {canonical} en {style}")
    if timeframe not in item["timeframes"]:
        raise AiTraderError(f"timeframe no permitido para {style}: {timeframe}")
    if timeframe not in allowed:
        raise AiTraderError(
            f"{strategy} no asignada a {canonical} en {style} para {timeframe}"
        )
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
        "style": style,
        "symbol": canonical,
        "strategy": strategy,
        "timeframe": timeframe,
        "side": side,
        "thesis": thesis,
        "confidence": confidence,
    }


def _volume_for_risk(broker, symbol: str, stop_distance: float,
                     risk_usd: float) -> tuple[float, float, float]:
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
    if maximum > 0 and lots > maximum:
        lots = math.floor((maximum / step) + 1e-9) * step
        lots = round(lots, 8)
    if maximum > 0 and maximum < minimum - 1e-12:
        raise AiTraderError(
            f"volume_max {maximum:g} < volume_min {minimum:g}: símbolo no operable"
        )
    if lots <= 0 or lots < minimum - 1e-12:
        raise AiTraderError(
            f"volumen {lots:.4f} < mínimo {minimum}: stop demasiado ancho "
            f"(riesgo mínimo {minimum * risk_per_lot:.2f} > {risk_usd:.2f})"
        )
    return lots, lots * risk_per_lot, risk_per_lot


# --------------------------------------------------------------- decisiones


def _json_snapshot(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AiTraderError(f"snapshot no es JSON válido: {exc}") from exc
        value = parsed
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as exc:
        raise AiTraderError(f"snapshot no serializable: {exc}") from exc


def _record_decision(
    *,
    db_path: str | Path,
    config: dict,
    style: str,
    symbol: str,
    timeframe: str | None,
    strategy: str,
    setup_valid: bool,
    decision: str,
    reason: str,
    confidence: int | None = None,
    snapshot_payload=None,
    source: str = "forward",
    plan_id: str | None = None,
    settings: Settings | None = None,
) -> dict:
    if decision not in DECISIONS:
        raise AiTraderError(f"decisión inválida: {decision}")
    if source not in SOURCES:
        raise AiTraderError(f"source inválido: {source}")
    text = str(reason or "").strip()
    if not text:
        raise AiTraderError("motivo obligatorio y <= 200 caracteres")
    text = text[:200]
    init_db(db_path)
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT INTO ai_decisions"
            "(ts, decision_date, session, style, symbol, timeframe, strategy, "
            " setup_valid, decision, reason, confidence, snapshot, "
            " playbook_version, source, plan_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                _reset_date(settings),
                _session(datetime.now(timezone.utc)),
                style,
                symbol,
                timeframe,
                strategy,
                1 if setup_valid else 0,
                decision,
                text,
                confidence,
                _json_snapshot(snapshot_payload),
                config["playbook_version"],
                source,
                plan_id,
            ),
        )
        decision_id = int(cursor.lastrowid)
    return {"id": decision_id, "decision": decision, "reason": text}


def _audit(db_path: str | Path, action: str, params: dict, result: str,
           detail: str = "", ok: int = 1) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        append_hashed(con, "console_actions", {
            "ts": utcnow(),
            "action": action,
            "params": json.dumps(params, ensure_ascii=False, sort_keys=True, default=str),
            "result": result,
            "ok": ok,
            "actor": "opencode",
            "detail": str(detail)[:400],
        })


def _assert_demo(broker) -> dict:
    health = broker.health()
    if str(health.get("mode")) != "demo":
        raise AiTraderError("solo demo: la cuenta no es demo")
    return health


def _daily_state(db_path: str | Path, config: dict, equity: float,
                 broker=None, settings: Settings | None = None) -> dict:
    """PnL del día por estilo y global (cerrado + flotante del carril)."""
    positions = []
    if broker is not None:
        positions = _all_lane_positions(broker, config)
    styles_out = {}
    for name, item in config["styles"].items():
        magic = int(item["magic"])
        pnl = _lane_pnl_today(db_path, magic, settings)
        pnl += _floating_today(positions, magic, settings)
        limit = float(equity) * float(item["daily_stop"])
        styles_out[name] = {
            "pnl": round(pnl, 4),
            "limit_usd": round(limit, 2),
            "remaining_usd": round(limit - max(0.0, -pnl), 2),
            "hit": bool(limit > 0 and pnl <= -limit + 1e-9),
        }
    total = sum(float(item["pnl"]) for item in styles_out.values())
    global_limit = float(equity) * float(config["global"]["daily_stop"])
    out = {
        "styles": styles_out,
        "global": {
            "pnl": round(total, 4),
            "limit_usd": round(global_limit, 2),
            "remaining_usd": round(global_limit - max(0.0, -total), 2),
            "hit": bool(global_limit > 0 and total <= -global_limit + 1e-9),
        },
        "equity": round(float(equity), 2),
    }
    return out


def daily_stop_state(db_path: str | Path = DEFAULT_DB, config: dict | None = None,
                     *, equity: float, broker=None,
                     settings: Settings | None = None) -> dict:
    cfg = config or load_config()
    return _daily_state(db_path, cfg, equity, broker=broker, settings=settings)


# ------------------------------------------------------------------ propose


def _propose(item: dict, *, broker, cfg: dict, settings: Settings,
             db_path: str | Path) -> dict:
    style_name = item["style"]
    style = cfg["styles"][style_name]
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    health = _assert_demo(broker)
    if not style["enabled"]:
        raise AiTraderError(f"estilo {style_name} deshabilitado")
    is_open = session_open(style)
    if is_open is False:
        window = style["session"]
        raise _Reject(
            f"{style_name}: fuera de ventana {window['start']}-{window['end']} "
            f"{window['tz']}",
            decision="skip", setup_valid=0,
        )
    if _cell_status(db_path, item["strategy"], item["symbol"], item["timeframe"]) == "paused":
        raise _Reject(
            "celda pausada por el scoreboard; requiere reactivación del operador",
            decision="skip", setup_valid=1,
        )
    all_positions = _all_lane_positions(broker, cfg)
    if len(all_positions) >= cfg["global"]["max_open_total"]:
        raise _Reject(
            f"máximo global de posiciones alcanzado ({cfg['global']['max_open_total']})",
            decision="skip", setup_valid=1,
        )
    lane = [p for p in all_positions if int(p.get("magic") or 0) == int(style["magic"])]
    same = [p for p in lane if str(p.get("symbol", "")).upper() == item["symbol"].upper()]
    if len(same) >= cfg["global"]["max_open_per_symbol_per_style"]:
        raise _Reject(
            f"{item['symbol']}: {style_name} ya tiene una posición abierta",
            decision="skip", setup_valid=1,
        )
    max_trades = style["max_trades_per_day"]
    if max_trades is not None and _trades_today(db_path, style["magic"], settings) >= max_trades:
        raise _Reject(
            f"{style_name}: máximo de operaciones diarias alcanzado ({max_trades})",
            decision="skip", setup_valid=1,
        )
    equity = float(health.get("equity") or 0.0)
    daily = _daily_state(db_path, cfg, equity, broker=broker, settings=settings)
    if daily["global"]["hit"]:
        raise _Reject(
            "stop diario global tocado: no se abre hasta el reset de FTMO",
            decision="skip", setup_valid=1,
        )
    if daily["styles"][style_name]["hit"]:
        raise _Reject(
            f"stop diario del estilo {style_name} tocado: no se abre hasta el reset de FTMO",
            decision="skip", setup_valid=1,
        )

    snap = snapshot_symbol(broker, item["symbol"], cfg, db_path, style=style_name)
    ok, reason = validate(item["strategy"], item["side"], snap, item["timeframe"])
    if not ok:
        raise _Reject(f"setup no válido: {reason}", decision="no_setup",
                      setup_valid=0, snapshot=snap)
    try:
        level = plan(item["strategy"], item["side"], snap, item["timeframe"])
    except SetupError as exc:
        raise _Reject(f"setup no válido: {exc}", decision="no_setup",
                      setup_valid=0, snapshot=snap) from exc
    tick = broker.tick(item["symbol"])
    entry = float(tick["ask"] if item["side"] == "buy" else tick["bid"])
    dist = abs(entry - level.sl)
    sl = level.sl
    tp = level.tp
    if dist <= 0:
        raise _Reject("distancia de stop no positiva", decision="skip",
                      setup_valid=1, snapshot=snap)
    price = float(snap["price"])
    spec = broker.symbol_spec(item["symbol"])
    point = float(spec.get("point") or 0.0)
    min_sl = max(
        3 * float(snap["spread"]),
        float(spec.get("stops_level") or 0) * point,
    )
    if dist < min_sl - 1e-12:
        raise _Reject(
            f"SL {dist:.5f} < mínimo {min_sl:.5f} (3×spread o stops_level)",
            decision="skip", setup_valid=1, snapshot=snap,
        )
    cost_ratio = _cost_ratio(
        item["symbol"], price, float(snap["spread"]), dist,
        slippage_points=style["slippage_points"], point=point,
    )
    if cost_ratio is None:
        raise _Reject("coste/R Sin datos: comisión no verificada",
                      decision="skip", setup_valid=1, snapshot=snap)
    max_cost = style["max_cost_r"]
    if max_cost is not None and cost_ratio > float(max_cost) + 1e-12:
        raise _Reject(
            f"coste/R {cost_ratio:.3f} > {float(max_cost):.2f}",
            decision="skip", setup_valid=1, snapshot=snap,
        )
    risk_usd = equity * float(style["risk_per_trade"])
    lots, real_risk, risk_per_lot = _volume_for_risk(
        broker, item["symbol"], dist, risk_usd
    )
    if style["max_open_risk"] is not None:
        open_risk = _open_risk(db_path, style["magic"])
        cap = equity * float(style["max_open_risk"])
        if open_risk + real_risk > cap + 1e-9:
            raise _Reject(
                f"riesgo abierto de {style_name} {open_risk + real_risk:.2f} > "
                f"{cap:.2f} ({style['max_open_risk']:.1%})",
                decision="skip", setup_valid=1, snapshot=snap,
            )

    rules = _prop_rules(settings)
    guard = PropGuard(rules)
    try:
        state = PropGuard.state_from_equity(
            rules, broker.equity_series(), initial_balance=rules.account_size,
            open_positions=len(broker.positions()),
        )
        report = guard.evaluate(
            state, proposed_lots=lots, risk_per_lot=risk_per_lot,
            open_risk_usd=_open_risk(db_path, style["magic"]), new_position=True,
        )
    except Exception as exc:
        raise _Reject(f"PropGuard no disponible: {exc}", decision="skip",
                      setup_valid=1, snapshot=snap) from exc
    if not report.allowed:
        raise _Reject(f"PropGuard: {report.reason}", decision="skip",
                      setup_valid=1, snapshot=snap)

    pid = uuid.uuid4().hex
    now = utcnow()
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_trades"
            "(proposal_id, ts, style, symbol, setup, side, timeframe, thesis, "
            " confidence, snapshot_hash, playbook_version, entry, sl, tp, "
            " volume, risk_usd, cost_ratio, magic, status, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid, now, style_name, item["symbol"], item["strategy"], item["side"],
                item["timeframe"], item["thesis"], item["confidence"],
                _snapshot_hash(snap), cfg["playbook_version"], round(entry, 8),
                round(sl, 8), round(tp, 8) if tp is not None else None, lots,
                round(real_risk, 2), round(cost_ratio, 4), style["magic"],
                "proposed", now, now,
            ),
        )
    decision = _record_decision(
        db_path=db_path, config=cfg, style=style_name, symbol=item["symbol"],
        timeframe=item["timeframe"], strategy=item["strategy"], setup_valid=True,
        decision="take", reason="propuesta aceptada", confidence=item["confidence"],
        snapshot_payload=snap, source="forward", plan_id=pid, settings=settings,
    )
    return {
        "id": pid,
        "status": "proposed",
        "style": style_name,
        "strategy": item["strategy"],
        "decision_id": decision["id"],
        "snapshot": snap,
        "order": {
            "style": style_name,
            "symbol": item["symbol"],
            "strategy": item["strategy"],
            "timeframe": item["timeframe"],
            "side": item["side"],
            "volume": lots,
            "entry": round(entry, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8) if tp is not None else None,
            "risk_usd": round(real_risk, 2),
            "risk_pct": round(real_risk / equity * 100, 3) if equity else None,
            "rr": level.rr,
            "cost_ratio": round(cost_ratio, 4),
            "magic": style["magic"],
        },
    }


def propose(payload: dict, *, broker, config: dict | None = None,
            settings: Settings | None = None,
            db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    settings = settings or get_settings()
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    item = _validate_payload(payload, cfg)
    try:
        result = _propose(item, broker=broker, cfg=cfg, settings=settings,
                          db_path=db_path)
    except _Reject as exc:
        params = {
            "style": item.get("style"), "symbol": item.get("symbol"),
            "strategy": item.get("strategy"), "timeframe": item.get("timeframe"),
            "decision": exc.decision,
        }
        try:
            _record_decision(
                db_path=db_path, config=cfg, style=item["style"],
                symbol=item["symbol"], timeframe=item["timeframe"],
                strategy=item["strategy"], setup_valid=bool(exc.setup_valid),
                decision=exc.decision, reason=str(exc),
                confidence=item.get("confidence"),
                snapshot_payload=exc.snapshot, source="forward", settings=settings,
            )
        except Exception:
            pass
        _audit(db_path, "ai_trader_reject", params, "rejected",
               detail=str(exc), ok=0)
        raise
    _audit(
        db_path, "ai_trader_propose",
        {"proposal_id": result["id"], "style": item["style"],
         "symbol": item["symbol"], "strategy": item["strategy"],
         "timeframe": item["timeframe"], "side": item["side"],
         "volume": result["order"]["volume"], "magic": result["order"]["magic"]},
        "proposed", detail=item["thesis"],
    )
    return result


def skip(payload: dict, *, config: dict | None = None,
         settings: Settings | None = None,
         db_path: str | Path = DEFAULT_DB) -> dict:
    """Registra una decisión de NO operar (también es una decisión)."""
    cfg = config or load_config()
    settings = settings or get_settings()
    if not isinstance(payload, dict):
        raise AiTraderError("decisión inválida")
    style_name = str(payload.get("style") or "").strip()
    style = style_config(cfg, style_name)
    symbol = str(payload.get("symbol") or "").strip().upper()
    universe = {item.lower(): item for item in cfg["universe"]}
    if symbol.lower() not in universe:
        raise AiTraderError(f"símbolo fuera del universo: {symbol}")
    symbol = universe[symbol.lower()]
    if symbol not in {item.upper() for item in style["universe"]}:
        raise AiTraderError(f"{symbol} fuera del universo de {style_name}")
    strategy = str(payload.get("strategy") or "").strip()
    if strategy not in STRATEGY_TIMEFRAME:
        raise AiTraderError(f"estrategia desconocida: {strategy}")
    timeframe = str(
        payload.get("timeframe") or STRATEGY_TIMEFRAME[strategy]
    ).strip().upper()
    allowed = style["allowed"].get(symbol.upper(), {}).get(strategy, [])
    if not allowed or timeframe not in allowed:
        raise AiTraderError(
            f"{strategy} no asignada a {symbol} en {style_name} para {timeframe}"
        )
    try:
        confidence = int(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AiTraderError("confidence debe ser entero 1-5") from exc
    if not 1 <= confidence <= 5:
        raise AiTraderError("confidence debe estar entre 1 y 5")
    reason = str(payload.get("reason") or "").strip()
    if not reason or len(reason) > 200:
        raise AiTraderError("motivo obligatorio y <= 200 caracteres")
    source = str(payload.get("source") or "forward").strip().lower()
    result = _record_decision(
        db_path=db_path, config=cfg, style=style_name, symbol=symbol,
        timeframe=timeframe, strategy=strategy,
        setup_valid=bool(payload.get("setup_valid", False)), decision="skip",
        reason=reason, confidence=confidence,
        snapshot_payload=payload.get("snapshot"), source=source,
        plan_id=payload.get("plan_id"), settings=settings,
    )
    _audit(
        db_path, "ai_trader_skip",
        {"decision_id": result["id"], "style": style_name, "symbol": symbol,
         "strategy": strategy, "timeframe": timeframe, "confidence": confidence},
        "skip", detail=reason,
    )
    return result


# ------------------------------------------------------------------ execute


def execute(proposal_id: str, *, broker, config: dict | None = None,
            db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    _assert_demo(broker)
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM ai_trades WHERE proposal_id=?", (proposal_id,)).fetchone()
    if row is None:
        raise AiTraderError(f"propuesta no encontrada: {proposal_id}")
    if row["status"] != "proposed":
        raise AiTraderError(f"propuesta en estado {row['status']}, no proposed")
    style_name = row["style"] or style_for_magic(cfg, int(row["magic"] or 0))
    if not style_name or style_name not in cfg["styles"]:
        raise AiTraderError(f"propuesta con estilo desconocido: {row['style']!r}")
    style = cfg["styles"][style_name]
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
        bot=f"ai:{style_name}", reason=str(row["thesis"])[:400],
        magic=style["magic"], dry_run=False,
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
    fills = None
    fills_error = None
    try:
        from .mt5_fills import lab_magic_map, sync_mt5_fills

        fills = sync_mt5_fills(
            broker, db_path, magics=lab_magic_map(cfg), account=cfg["account"]
        )
    except Exception as exc:
        fills_error = str(exc)
    _audit(
        db_path, "ai_trader_execute",
        {"proposal_id": proposal_id, "style": style_name, "symbol": row["symbol"],
         "strategy": row["strategy"], "timeframe": row["timeframe"], "side": side,
         "volume": float(row["volume"]), "magic": style["magic"]},
        "executed", detail=str(row["thesis"]),
    )
    return {
        "id": proposal_id, "status": "open", "style": style_name,
        "order": order, "fills": fills, "fills_error": fills_error,
    }


# -------------------------------------------------------- manage / cierres


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


def _forced_close_reason(setup: str, opened: datetime, now: datetime) -> str | None:
    """Cierre obligatorio de las estrategias intradía con hora de salida."""
    if setup == "orb_ny":
        zone, close_at = NEW_YORK, dtime(16, 0)
    elif setup == "london_breakout":
        zone, close_at = LONDON, dtime(16, 0)
    else:
        return None
    opened_local = _as_utc(opened).astimezone(zone)
    now_local = _as_utc(now).astimezone(zone)
    if opened_local.date() < now_local.date() or now_local.time() >= close_at:
        return f"cierre de sesión {setup} ({close_at.strftime('%H:%M')} {zone.key})"
    return None


def _rsi2_exit(broker, symbol: str, entry_time: datetime,
               now: datetime) -> str | None:
    """Salida de rsi2_connors: cierre D1 completado por encima de la SMA5."""
    try:
        h4 = broker.rates(symbol, "H4", 800)
    except Exception:
        return None
    d1 = _daily(h4)
    d1 = d1[d1.index < pd.Timestamp(now).normalize()]
    if len(d1) < 5:
        return None
    if d1.index[-1].date() <= pd.Timestamp(entry_time).date():
        return None
    sma5 = float(d1["close"].rolling(5).mean().iloc[-1])
    if float(d1["close"].iloc[-1]) > sma5:
        return "cierre D1 sobre SMA5"
    return None


def _donchian_stop(broker, symbol: str, side: str, entry: float,
                   current_sl: float, profit_r: float, now: datetime,
                   digits: int) -> float | None:
    """Trailing de 10 días de donchian_turtle; nunca aleja el stop."""
    try:
        h4 = broker.rates(symbol, "H4", 800)
    except Exception:
        return None
    d1 = _daily(h4)
    d1 = d1[d1.index < pd.Timestamp(now).normalize()]
    if len(d1) < 10:
        return None
    short = str(side).lower() == "sell"
    channel = (
        float(d1["high"].tail(10).max()) if short
        else float(d1["low"].tail(10).min())
    )
    if profit_r >= 0.5:
        channel = min(channel, entry) if short else max(channel, entry)
    if short:
        if current_sl and channel >= current_sl - 1e-9:
            return None
        return round(channel, digits)
    if current_sl and channel <= current_sl + 1e-9:
        return None
    return round(channel, digits)


def manage(*, broker, config: dict | None = None,
           db_path: str | Path = DEFAULT_DB) -> list[dict]:
    cfg = config or load_config()
    now = datetime.now(timezone.utc)
    init_db(db_path)
    with connect(db_path) as con:
        rows = {int(r["ticket"]): dict(r) for r in con.execute(
            "SELECT * FROM ai_trades WHERE status='open' AND ticket IS NOT NULL").fetchall()}
    out = []
    for position in _all_lane_positions(broker, cfg):
        ticket = int(position["ticket"])
        row = rows.get(ticket) or {}
        style_name = row.get("style") or style_for_magic(
            cfg, int(position.get("magic") or 0))
        setup = str(row.get("setup") or "")
        timeframe = str(row.get("timeframe") or "H1")
        opened = pd.Timestamp(position["time"])
        if opened.tzinfo is None:
            opened = opened.tz_localize("UTC")
        short = str(position["side"]).lower() == "sell"
        entry = float(position["price_open"])
        sl = float(position["sl"] or 0)
        if sl <= 0:
            continue

        forced = _forced_close_reason(setup, opened.to_pydatetime(), now)
        if forced is None and setup == "rsi2_connors":
            forced = _rsi2_exit(
                broker, position["symbol"], opened.to_pydatetime(), now
            )
        if forced is not None:
            try:
                broker.close_position(ticket)
                out.append({
                    "ticket": ticket, "symbol": position["symbol"],
                    "side": position["side"], "style": style_name,
                    "setup": setup, "timeframe": timeframe,
                    "profit_r": None, "sl": sl, "new_sl": None,
                    "closed": forced,
                })
            except Exception as exc:
                out.append({
                    "ticket": ticket, "symbol": position["symbol"],
                    "side": position["side"], "style": style_name,
                    "setup": setup, "timeframe": timeframe,
                    "profit_r": None, "sl": sl, "new_sl": None,
                    "closed": None, "close_error": str(exc)[:120],
                })
            continue

        bars = None
        try:
            bars = broker.rates(position["symbol"], timeframe, 500)
        except Exception as exc:
            out.append({
                "ticket": ticket, "symbol": position["symbol"],
                "side": position["side"], "style": style_name,
                "setup": setup, "timeframe": timeframe,
                "profit_r": None, "sl": sl, "new_sl": None,
                "closed": None, "error": str(exc)[:120],
            })
            continue
        since = bars[bars.index >= opened]
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
        digits = int(spec.get("digits") or 2)
        if setup == "donchian_turtle":
            candidate = _donchian_stop(
                broker, position["symbol"], position["side"], entry, sl,
                profit_r, now, digits,
            )
        else:
            candidate = next_stop(
                side=position["side"], entry=entry, best=best,
                atr_value=float(atr(bars).iloc[-1]),
                current_sl=sl, profit_r=profit_r,
                digits=digits,
                min_distance=float(spec.get("stops_level") or 0) * float(spec.get("point") or 0),
            )
        moved = None
        if candidate is not None and ((short and candidate < sl) or (not short and candidate > sl)):
            try:
                broker.modify_position(ticket, sl=round(candidate, digits))
                moved = round(candidate, digits)
            except Exception:
                moved = None
        out.append({"ticket": ticket, "symbol": position["symbol"], "side": position["side"],
                    "style": style_name, "setup": setup, "timeframe": timeframe,
                    "profit_r": round(profit_r, 4), "sl": sl, "new_sl": moved,
                    "closed": None})
    for name, item in cfg["styles"].items():
        sync_closed(broker, magic=int(item["magic"]), db_path=db_path, now=now)
    return out


def sync_closed(broker, *, magic: int, db_path: str | Path = DEFAULT_DB,
                now: datetime | None = None) -> int:
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
            deals = broker.history_deals(
                datetime.fromisoformat(str(row["ts"])) - timedelta(hours=2),
                moment + timedelta(hours=1),
            )
        except Exception:
            continue
        rel = [d for d in deals if int(d.get("position_id") or 0) == ticket
               and int(d.get("magic") or 0) == magic]
        if not rel:
            continue
        pnl = sum(float(d.get("profit") or 0) + float(d.get("swap") or 0)
                  + float(d.get("commission") or 0) for d in rel)
        risk = float(row.get("risk_usd") or 0)
        result_r = round(pnl / risk, 4) if risk else None
        with connect(db_path) as con:
            con.execute(
                "UPDATE ai_trades SET status='closed', exit_price=?, exit_ts=?, pnl=?, "
                "r_multiple=?, result_r=?, updated_at=? WHERE proposal_id=?",
                (float(rel[-1].get("price") or 0), str(rel[-1].get("ts_utc") or moment.isoformat()),
                 round(pnl, 2), result_r, result_r, utcnow(), row["proposal_id"]),
            )
        closed += 1
    return closed


# ------------------------------------------------------------- scoreboard


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


def resume_cell(strategy: str, symbol: str, timeframe: str,
                db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, reason, updated_at) "
            "VALUES(?,?,?,'active',?,?) ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
            "status='active', reason=excluded.reason, updated_at=excluded.updated_at",
            (strategy, symbol, timeframe, "reactivada por el operador", utcnow()),
        )
    return {"strategy": strategy, "symbol": symbol, "timeframe": timeframe,
            "status": "active"}


def scoreboard(*, broker, config: dict | None = None,
               db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM ai_trades ORDER BY ts").fetchall()]
    positions = {int(p["ticket"]): p for p in (broker.positions() or [])}
    out = []
    for row in rows:
        real_r = None
        if row["status"] == "closed":
            value = row.get("result_r") if row.get("result_r") is not None else row.get("r_multiple")
            if value is not None:
                real_r = float(value)
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
                    "style": row.get("style"), "strategy": row["setup"],
                    "timeframe": row.get("timeframe") or "Sin datos",
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
        styles = sorted({str(i["style"]) for i in items if i["style"]})
        cells.append({
            "strategy": strategy, "symbol": symbol, "timeframe": timeframe,
            "style": styles[0] if len(styles) == 1 else (",".join(styles) or None),
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


# ------------------------------------------------------------------ status


def status(*, broker, config: dict | None = None, settings: Settings | None = None,
           db_path: str | Path = DEFAULT_DB) -> dict:
    cfg = config or load_config()
    settings = settings or get_settings()
    health = _assert_demo(broker)
    equity = float(health.get("equity") or 0.0)
    positions = _all_lane_positions(broker, cfg)
    daily = _daily_state(db_path, cfg, equity, broker=broker, settings=settings)
    styles = {}
    for name, item in cfg["styles"].items():
        magic = int(item["magic"])
        lane = [p for p in positions if int(p.get("magic") or 0) == magic]
        state = daily["styles"][name]
        risk_used = _open_risk(db_path, magic)
        styles[name] = {
            "style": name,
            "magic": magic,
            "enabled": item["enabled"],
            "equity": round(equity, 2),
            "risk_per_trade": item["risk_per_trade"],
            "max_cost_r": item["max_cost_r"],
            "max_open_risk": item["max_open_risk"],
            "max_trades_per_day": item["max_trades_per_day"],
            "trades_today": _trades_today(db_path, magic, settings),
            "risk_used_usd": round(risk_used, 2),
            "risk_used_pct": round(risk_used / equity, 4) if equity else None,
            "pnl_today": state["pnl"],
            "daily_stop_usd": state["limit_usd"],
            "stop_remaining_usd": max(0.0, state["remaining_usd"]),
            "stop_hit": state["hit"],
            "open_count": len(lane),
            "session_open": session_open(item),
            "positions": [
                {"ticket": int(p["ticket"]), "symbol": p["symbol"], "side": p["side"],
                 "volume": float(p["volume"]), "profit": float(p.get("profit") or 0.0),
                 "magic": int(p.get("magic") or 0)}
                for p in lane
            ],
        }
    global_state = daily["global"]
    return {
        "generated_at": utcnow(),
        "account": cfg["account"],
        "playbook_version": cfg["playbook_version"],
        "equity": round(equity, 2),
        "styles": styles,
        "global": {
            "daily_stop": cfg["global"]["daily_stop"],
            "daily_stop_usd": global_state["limit_usd"],
            "pnl_today": global_state["pnl"],
            "stop_remaining_usd": max(0.0, global_state["remaining_usd"]),
            "stop_hit": global_state["hit"],
            "max_open_total": cfg["global"]["max_open_total"],
            "open_count": len(positions),
            "magics": cfg["magics"],
            "positions": [
                {"ticket": int(p["ticket"]), "symbol": p["symbol"], "side": p["side"],
                 "volume": float(p["volume"]), "profit": float(p.get("profit") or 0.0),
                 "magic": int(p.get("magic") or 0)}
                for p in positions
            ],
        },
    }


# ------------------------------------------------------------ panel / review


def log_no_trade(reason: str, *, symbols: list[str] | None = None,
                 db_path: str | Path = DEFAULT_DB) -> dict:
    text = str(reason or "").strip()
    if not text or len(text) > 500:
        raise AiTraderError("motivo obligatorio y <= 500 caracteres")
    _audit(db_path, "ai_trader_no_trade", {"symbols": symbols or []},
           "no_trade", detail=text)
    return {"ok": True, "reason": text}


def panel(db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT proposal_id, ts, style, symbol, setup, side, timeframe, thesis, "
            "confidence, entry, sl, tp, volume, risk_usd, status, pnl, r_multiple, "
            "result_r, shadow_side, shadow_r, cost_ratio FROM ai_trades "
            "ORDER BY ts DESC LIMIT 100").fetchall()]
        decisions = [dict(r) for r in con.execute(
            "SELECT id, ts, style, symbol, strategy, timeframe, decision, reason, "
            "confidence FROM ai_decisions ORDER BY id DESC LIMIT 50").fetchall()]
        lessons = [dict(r) for r in con.execute(
            "SELECT id, hypothesis, status FROM lessons WHERE status='proposed' "
            "AND kind='lesson' ORDER BY id DESC LIMIT 10").fetchall()]
        cells = [dict(r) for r in con.execute(
            "SELECT strategy, symbol, timeframe, status, reason FROM ai_cell_state "
            "WHERE status='paused' ORDER BY updated_at DESC").fetchall()]
    opened = [r for r in rows if r["status"] == "open"]
    closed = [r for r in rows if r["status"] == "closed"]
    real = [float(r["result_r"] if r["result_r"] is not None else r["r_multiple"])
            for r in closed if r["result_r"] is not None or r["r_multiple"] is not None]
    shadow = [float(r["shadow_r"]) for r in closed if r["shadow_r"] is not None]
    return {"open": opened, "closed": {"n": len(closed),
            "avg_r": round(sum(real) / len(real), 4) if real else None,
            "shadow_avg_r": round(sum(shadow) / len(shadow), 4) if shadow else None},
            "decisions": decisions, "lessons": lessons, "paused": cells, "n": len(rows)}


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
    rs = [float(r["result_r"] if r.get("result_r") is not None else r["r_multiple"])
          for r in rows if r.get("result_r") is not None or r.get("r_multiple") is not None]
    lines = ["# IA discrecional · revisión semanal",
             f"- Ventana: últimos {days} días · cerradas: {len(rows)}",
             f"- Playbook: v{cfg['playbook_version']}",
             f"- R medio: {sum(rs)/len(rs):+.3f}" if rs else "- R medio: Sin datos",
             f"- PnL: {sum(float(r.get('pnl') or 0) for r in rows):+.2f} USD", "",
             "| id | estilo | símbolo | estrategia | tf | lado | R | PnL |",
             "|---|---|---|---|---|---|---:|---:|"]
    for row in rows:
        value = row.get("result_r") if row.get("result_r") is not None else row.get("r_multiple")
        lines.append(f"| {row['proposal_id'][:8]} | {row.get('style') or '-'} | "
                     f"{row['symbol']} | {row['setup']} | {row.get('timeframe') or '-'} | "
                     f"{row['side']} | {float(value or 0):+.2f} | "
                     f"{float(row.get('pnl') or 0):+.2f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lessons = []
    if len(rs) >= 5:
        from .learning import create_lesson

        def avg(items): return sum(items) / len(items) if items else 0.0

        conditions = []
        for strategy in sorted({str(r["setup"]) for r in rows}):
            with_ = []
            for r in rows:
                if r["setup"] != strategy:
                    continue
                value = r.get("result_r") if r.get("result_r") is not None else r.get("r_multiple")
                if value is not None:
                    with_.append(float(value))
            without = []
            for r in rows:
                if r["setup"] == strategy:
                    continue
                value = r.get("result_r") if r.get("result_r") is not None else r.get("r_multiple")
                if value is not None:
                    without.append(float(value))
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
                   db_path: str | Path = DEFAULT_DB,
                   settings: Settings | None = None) -> dict:
    from .learning import approve

    lesson = approve(db_path, lesson_id, by="operador", settings=settings)
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    global_block = data.get("global")
    if isinstance(global_block, dict):
        current = int(global_block.get("playbook_version") or data.get("playbook_version") or 1)
        global_block["playbook_version"] = current + 1
        data["global"] = global_block
        version = global_block["playbook_version"]
    else:
        version = int(data.get("playbook_version") or 1) + 1
        data["playbook_version"] = version
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"lesson": lesson, "playbook_version": version}
