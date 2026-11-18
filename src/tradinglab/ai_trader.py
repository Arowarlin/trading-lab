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
import os
import random
import statistics
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import yaml

from .ai_setups import (
    STRATEGY_TIMEFRAME,
    TIMEFRAMES,
    SetupError,
    supports,
    validate,
)
from .ai_setups import plan as setup_plan
from .audit import append_hashed
from .carry import cost_model_from_asset
from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .db import connect, init_db, utcnow
from .indicators import atr, ema
from .intraday_costs import asset_costs
from .killswitch import ensure as ensure_killswitch
from .killswitch import load_state as load_killswitch_state
from .prop.guard import PropGuard
from .prop.rules import from_yaml
from .trailing import next_stop, tp_protection_stop

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


class StaleDataError(AiTraderError):
    """La vela usada por la se?al es m?s vieja que dos velas del timeframe."""


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
        "max_open": 2,
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

    slippage_raw = (
        global_raw.get("slippage_price")
        or data.get("slippage_price")
        or {}
    )
    if not isinstance(slippage_raw, dict):
        raise AiTraderError("global.slippage_price debe ser un objeto")
    slippage_price: dict[str, float] = {}
    for raw_symbol, raw_value in slippage_raw.items():
        raw_symbol = str(raw_symbol).strip()
        if raw_symbol.lower() not in canonical:
            raise AiTraderError(
                f"slippage_price con símbolo fuera del universo: {raw_symbol}"
            )
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise AiTraderError(
                f"slippage_price inválido para {raw_symbol}: {raw_value!r}"
            ) from exc
        if value <= 0:
            raise AiTraderError(
                f"slippage_price debe ser > 0 para {raw_symbol}"
            )
        slippage_price[canonical[raw_symbol.lower()].upper()] = value

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
        max_open = int(raw.get("max_open") or 2)
        if not 1 <= max_open <= 100:
            raise AiTraderError(f"{name}: max_open fuera de rango")
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
            "max_open": max_open,
            "universe": style_universe,
            "session": _parse_session(raw.get("session")),
            "max_open_risk": max_open_risk,
            "allowed": allowed,
            "risk_overrides": {},
        }

    magics = [int(item["magic"]) for item in styles.values()]
    if len(set(magics)) != len(magics):
        raise AiTraderError("cada estilo debe tener un magic distinto")

    learned_raw = data.get("learned") or {}
    if not isinstance(learned_raw, dict):
        raise AiTraderError("learned debe ser un objeto")
    exclusions: list[dict] = []
    for entry in learned_raw.get("exclusions") or []:
        if not isinstance(entry, dict):
            raise AiTraderError("learned.exclusions debe ser una lista de objetos")
        style_name = str(entry.get("style") or "").strip()
        if style_name not in styles:
            raise AiTraderError(f"learned: estilo desconocido en exclusión: {style_name}")
        raw_symbol = str(entry.get("symbol") or "").strip()
        if raw_symbol.lower() not in canonical:
            raise AiTraderError(f"learned: símbolo desconocido en exclusión: {raw_symbol}")
        symbol = canonical[raw_symbol.lower()]
        strategy = str(entry.get("strategy") or "").strip()
        timeframe = str(entry.get("timeframe") or "").strip().upper()
        allowed = styles[style_name]["allowed"].get(symbol.upper(), {})
        if strategy not in allowed or timeframe not in allowed[strategy]:
            raise AiTraderError(
                f"learned: exclusión fuera de asignación: "
                f"{style_name}/{symbol}/{strategy}/{timeframe}"
            )
        kind = str(entry.get("kind") or "").strip().lower()
        if kind not in {"hour", "weekday", "snapshot"}:
            raise AiTraderError(f"learned: kind de exclusión inválido: {kind}")
        value = entry.get("value")
        field = entry.get("field")
        if kind == "hour":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise AiTraderError("learned: hour debe ser entero") from exc
            if not 0 <= value <= 23:
                raise AiTraderError("learned: hour fuera de 0-23")
        elif kind == "weekday":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise AiTraderError("learned: weekday debe ser entero") from exc
            if not 0 <= value <= 6:
                raise AiTraderError("learned: weekday fuera de 0-6")
        else:
            field = str(field or "").strip()
            if field not in {
                "session", "is_index", "trend_d1", "trend_h4", "bb_squeeze",
                "sweep_high", "sweep_low", "inside_bar", "rsi2_lt10",
            }:
                raise AiTraderError(f"learned: campo de snapshot inválido: {field}")
        exclusions.append({
            "style": style_name, "symbol": symbol, "strategy": strategy,
            "timeframe": timeframe, "kind": kind, "field": field,
            "value": value, "reason": str(entry.get("reason") or "")[:200],
        })
    risk_map = learned_raw.get("risk_overrides") or {}
    if not isinstance(risk_map, dict):
        raise AiTraderError("learned.risk_overrides debe ser un objeto")
    for style_name, mapping in risk_map.items():
        if style_name not in styles:
            raise AiTraderError(f"learned: estilo desconocido en risk_overrides: {style_name}")
        if not isinstance(mapping, dict):
            raise AiTraderError("learned.risk_overrides.<estilo> debe ser un objeto")
        for raw_symbol, risk in mapping.items():
            raw_symbol = str(raw_symbol).strip()
            if raw_symbol.lower() not in canonical:
                raise AiTraderError(f"learned: símbolo desconocido en riesgo: {raw_symbol}")
            symbol = canonical[raw_symbol.lower()]
            if symbol.upper() not in {
                item.upper() for item in styles[style_name]["universe"]
            }:
                raise AiTraderError(
                    f"learned: {symbol} fuera del universo de {style_name}"
                )
            risk = float(risk)
            if not 0 < risk <= 0.02:
                raise AiTraderError("learned: risk_overrides fuera de (0, 2%]")
            styles[style_name]["risk_overrides"][symbol.upper()] = risk

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
            "slippage_price": slippage_price,
        },
        "styles": styles,
        "magics": sorted(magics),
        "magic": styles["scalping"]["magic"] if "scalping" in styles else magics[0],
        "universe": universe,
        "daily_stop": daily_stop,
        "max_open_total": max_open_total,
        "max_open_per_symbol": per_symbol,
        "playbook_version": playbook,
        "slippage_price": slippage_price,
        "timeframes": sorted({tf for item in styles.values() for tf in item["timeframes"]}),
        "allowed": allowed_flat,
        "exclusions": exclusions,
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


def daily_stop_check(config: dict, account_daily_stop: float | None = None) -> dict:
    total = sum(float(item["daily_stop"]) for item in config["styles"].values())
    global_limit = float(config["global"]["daily_stop"])
    limit = float(account_daily_stop) if account_daily_stop is not None else global_limit
    warn = total > limit + 1e-12
    detail = (
        f"suma de estilos {total:.2%} vs cuenta {limit:.2%} "
        f"({len(config['styles'])} estilos)"
    )
    if warn:
        detail += " · un estilo puede consumir el stop de la cuenta"
    return {
        "sum": total,
        "global": global_limit,
        "account_daily_stop": limit,
        "warn": warn,
        "detail": detail,
    }


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


def _snapshot_condition(snap: dict, field: str, timeframe: str):
    """Valor actual de una condición aprendida del snapshot."""
    if field == "session":
        return snap.get("session")
    if field == "is_index":
        return bool(snap.get("is_index"))
    d1 = snap.get("d1") or {}
    if field == "trend_d1":
        return (
            "up" if float(d1["close"]) > float(d1["sma200"]) else "down"
        )
    if field == "trend_h4":
        h4 = snap.get("h4") or {}
        e9, e21, e50 = (float(h4[key]) for key in ("ema9", "ema21", "ema50"))
        if e9 > e21 > e50:
            return "up"
        if e9 < e21 < e50:
            return "down"
        return "flat"
    block = snap.get(TF_SECTION.get(str(timeframe).upper(), "")) or {}
    if field == "bb_squeeze":
        return bool(block.get("bb_squeeze"))
    if field == "sweep_high":
        return bool(block.get("sweep_high"))
    if field == "sweep_low":
        return bool(block.get("sweep_low"))
    if field == "inside_bar":
        return bool(d1.get("inside_bar"))
    if field == "rsi2_lt10":
        return float(d1["rsi2"]) < 10
    return None


def _exclusion_reason(cfg: dict, item: dict, snap: dict,
                      now: datetime | None = None) -> str | None:
    """Motivo de una exclusión aprendida que aplique a esta propuesta."""
    local = _as_utc(now).astimezone(NEW_YORK)
    for exclusion in cfg.get("exclusions") or []:
        if (
            exclusion.get("style") != item.get("style")
            or str(exclusion.get("symbol", "")).upper()
            != str(item.get("symbol", "")).upper()
            or exclusion.get("strategy") != item.get("strategy")
            or str(exclusion.get("timeframe", "")).upper()
            != str(item.get("timeframe", "")).upper()
        ):
            continue
        kind = exclusion.get("kind")
        if kind == "hour" and local.hour == int(exclusion["value"]):
            return f"exclusión aprendida: hora {local.hour} NY"
        if kind == "weekday" and local.weekday() == int(exclusion["value"]):
            return f"exclusión aprendida: día {local.strftime('%A')}"
        if kind == "snapshot":
            try:
                actual = _snapshot_condition(
                    snap, str(exclusion.get("field") or ""),
                    str(item.get("timeframe") or ""),
                )
            except Exception:
                actual = None
            if actual is None:
                continue
            expected = exclusion.get("value")
            if isinstance(actual, bool):
                match = bool(actual) == bool(expected)
            elif isinstance(actual, (int, float)):
                try:
                    match = float(actual) == float(expected)
                except (TypeError, ValueError):
                    match = False
            else:
                match = str(actual).lower() == str(expected).lower()
            if match:
                return (
                    f"exclusión aprendida: {exclusion.get('field')}="
                    f"{actual}"
                )
    return None


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
            "AND status IN ('open','closed') "
            "AND COALESCE(source,'forward')='forward'",
            (magic, _day_start(settings).isoformat()),
        ).fetchone()
    return int(row["n"])


def _open_risk(db_path: str | Path, magic: int) -> float:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(SUM(risk_usd), 0) AS risk FROM ai_trades "
            "WHERE magic=? AND status='open' "
            "AND COALESCE(source,'forward')='forward'",
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


def _swing_holding_nights(db_path: str | Path) -> float:
    """Mediana de noches cerradas del estilo swing; 3 si no hay datos."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT ts, exit_ts FROM ai_trades "
            "WHERE style='swing' AND status='closed' AND exit_ts IS NOT NULL "
            "AND COALESCE(source,'forward')='forward'"
        ).fetchall()
    nights: list[int] = []
    for row in rows:
        try:
            entry = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            exit_at = datetime.fromisoformat(
                str(row["exit_ts"]).replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            continue
        nights.append(max(0, (exit_at.date() - entry.date()).days))
    if not nights:
        return 3.0
    return float(statistics.median(nights))


def _swap_cost_price(
    symbol: str,
    price: float,
    side: str,
    *,
    holding_nights: float,
    start_day: date,
    value_per_price: float,
) -> float | None:
    """Carry esperado en unidades de precio (positivo = coste)."""
    if holding_nights <= 0:
        return 0.0
    if value_per_price <= 0:
        return None
    try:
        asset = asset_costs(symbol)
        model = cost_model_from_asset(asset)
    except Exception:
        return None
    if model.swap_long is None or model.swap_short is None:
        return None
    # La tasa actual es la foto de swap de costs.yaml. Se usa como carry fijo
    # para el gate; no se inventa una tasa histórica si falta DFF/markup.
    model = replace(
        model,
        read_date=None,
        dff=None,
        markup_long=None,
        markup_short=None,
    )
    nights = max(0, int(math.ceil(float(holding_nights))))
    if nights <= 0:
        return 0.0
    cash = model.carry_for_nights(
        "long" if str(side).strip().lower() in {"buy", "long"} else "short",
        notional=float(price) * float(model.contract_size or 1.0),
        shares=1.0,
        start_day=start_day,
        end_day=start_day + timedelta(days=nights),
    )
    return -float(cash) / float(value_per_price)


def _cost_ratio(
    symbol: str,
    price: float,
    spread: float,
    stop_distance: float,
    *,
    slippage_price: float | None = None,
    side: str | None = None,
    holding_nights: float = 0.0,
    start_day: date | None = None,
    value_per_price: float | None = None,
) -> float | None:
    """Coste/R en precio: spread + comisión + 2× slippage + swap esperado."""
    commission = _commission_bps(symbol, price)
    if commission is None or stop_distance <= 0 or slippage_price is None:
        return None
    cost_price = (
        spread
        + price * commission / 10_000.0
        + 2.0 * float(slippage_price)
    )
    if holding_nights and holding_nights > 0:
        if side is None or start_day is None or value_per_price is None:
            return None
        swap_cost = _swap_cost_price(
            symbol,
            price,
            side,
            holding_nights=holding_nights,
            start_day=start_day,
            value_per_price=float(value_per_price),
        )
        if swap_cost is None:
            return None
        cost_price += swap_cost
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

    expected_orb5 = max(1, 15 // minutes)
    orb5 = bars[(bars.index >= et_open.astimezone(timezone.utc))
                & (bars.index < (et_open + timedelta(minutes=15)).astimezone(timezone.utc))]
    orb5_complete = moment >= (et_open + timedelta(minutes=15)).astimezone(timezone.utc)
    orb5_valid = orb5_complete and len(orb5) >= expected_orb5
    orb5_high = float(orb5["high"].max()) if orb5_valid else float("nan")
    orb5_low = float(orb5["low"].min()) if orb5_valid else float("nan")

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
        "ema8": _round_or_none(float(ema(bars["close"], 8).iloc[-1])),
        "ema9": _round_or_none(float(ema(bars["close"], 9).iloc[-1])),
        "ema13": _round_or_none(float(ema(bars["close"], 13).iloc[-1])),
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
        "orb5_high": _round_or_none(orb5_high if orb5_valid else None),
        "orb5_low": _round_or_none(orb5_low if orb5_valid else None),
        "orb5_valid": orb5_valid,
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
        "last_bar": bars.index[-1].isoformat(),
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
        "ema8": _round_or_none(float(ema(d1["close"], 8).iloc[-1])),
        "ema9": _round_or_none(float(ema(d1["close"], 9).iloc[-1])),
        "ema13": _round_or_none(float(ema(d1["close"], 13).iloc[-1])),
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
        "orb5_high": "Sin datos",
        "orb5_low": "Sin datos",
        "orb5_valid": False,
        "asian_high": "Sin datos",
        "asian_low": "Sin datos",
        "asian_valid": False,
        "prev_mid": round((float(prev["high"]) + float(prev["low"])) / 2, 8),
        "sweep_high": False,
        "sweep_low": False,
        "last_bar": d1.index[-1].isoformat(),
    }


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.drop(frame.index[frame.index.duplicated()])
    return frame.sort_index()


def _safe_rates(broker, symbol: str, timeframe: str, count: int,
                *, now: datetime | None = None,
                closed_only: bool = False) -> pd.DataFrame | None:
    """Velas del bróker; si el offset no se puede confirmar, Sin datos.

    Con ``closed_only`` se descarta la vela en formación: el scalp solo
    evalúa velas cerradas.
    """
    try:
        frame = broker.rates(symbol, timeframe, count)
    except Exception:
        return None
    if frame is None or len(frame) == 0:
        return None
    frame = _clean(frame)
    if closed_only:
        moment = _as_utc(now)
        duration = pd.Timedelta(minutes=TF_MINUTES.get(timeframe, 60))
        frame = frame[frame.index + duration <= moment]
        if len(frame) == 0:
            return None
    return frame


def _stale_reason(
    broker, symbol: str, timeframe: str, now: datetime
) -> str | None:
    """Motivo si la ?ltima vela cerrada es m?s vieja que 2 velas."""
    tf = "H4" if str(timeframe).upper() == "D1" else str(timeframe).upper()
    counts = {"M1": 20_000, "M5": 6_000, "M15": 2_000, "H1": 1_000, "H4": 3_000}
    frame = _safe_rates(
        broker, symbol, tf, counts.get(tf, 1_000), now=now
    )
    if frame is None or len(frame) == 0:
        return "Sin datos: no se pudieron leer velas"
    last = frame.index[-1]
    duration = pd.Timedelta(minutes=TF_MINUTES.get(tf, 60))
    age = _as_utc(now) - _as_utc(pd.Timestamp(last).to_pydatetime())
    if age > 2 * duration:
        return (
            f"datos obsoletos: ?ltima vela {last.isoformat()} "
            f"({age / duration:.1f} velas de retraso)"
        )
    return None


def _alert_stale(
    db_path: str | Path,
    style: str,
    symbol: str,
    timeframe: str,
    reason: str,
) -> None:
    try:
        from .alerts import send_once
        from .time_utils import market_today

        event = (
            f"stale_data:{market_today().isoformat()}:{style}:"
            f"{symbol.upper()}:{str(timeframe).upper()}"
        )
        send_once(
            event,
            f"{style} {symbol} {timeframe}: {reason}",
            severity="warning",
            db_path=db_path,
        )
    except Exception:
        pass


def _empty_block(reason: str) -> dict:
    return {
        "error": reason,
        "atr": "Sin datos", "sma20": "Sin datos",
        "ema8": "Sin datos", "ema9": "Sin datos", "ema13": "Sin datos",
        "ema21": "Sin datos", "ema50": "Sin datos",
        "bb_upper": "Sin datos", "bb_mid": "Sin datos",
        "bb_lower": "Sin datos", "bb_width": "Sin datos", "bb_squeeze": False,
        "vwap": "Sin datos", "vwap_sigma": "Sin datos",
        "orb_high": "Sin datos", "orb_low": "Sin datos", "orb_valid": False,
        "orb5_high": "Sin datos", "orb5_low": "Sin datos", "orb5_valid": False,
        "asian_high": "Sin datos", "asian_low": "Sin datos", "asian_valid": False,
        "prev_high": "Sin datos", "prev_low": "Sin datos", "prev_mid": "Sin datos",
        "sweep_high": False, "sweep_low": False,
        "open": "Sin datos", "high": "Sin datos", "low": "Sin datos",
        "close": "Sin datos", "last_bar": "Sin datos",
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
                    style: str | None = None,
                    closed_only: bool = False) -> dict:
    key = str(symbol).upper()
    now = datetime.now(timezone.utc)
    counts = {"M1": 20_000, "M5": 6_000, "M15": 2_000, "H1": 1_000, "H4": 3_000}
    frames = {
        tf: _safe_rates(broker, symbol, tf, count, now=now, closed_only=closed_only)
        for tf, count in counts.items()
    }
    tick = broker.tick(symbol)
    price = (float(tick["bid"]) + float(tick["ask"])) / 2.0
    spread = float(tick["ask"]) - float(tick["bid"])

    d1 = None
    if frames["H4"] is not None and len(frames["H4"]) >= 300:
        raw_daily = _daily(frames["H4"])
        today = pd.Timestamp(now).normalize()
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
    slippage_price = config.get("slippage_price", {}).get(str(symbol).upper())
    costs = {}
    for tf in TIMEFRAMES:
        raw_atr = blocks[tf].get("atr")
        try:
            atr_value = float(raw_atr)
        except (TypeError, ValueError):
            atr_value = 0.0
        ratio = _cost_ratio(
            symbol, price, spread, atr_value,
            slippage_price=slippage_price,
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
            "risk_overrides": item.get("risk_overrides") or {},
            "daily_stop": item["daily_stop"],
            "max_trades_per_day": item["max_trades_per_day"],
            "max_cost_r": item["max_cost_r"],
            "max_open": item["max_open"],
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
    try:
        from .data.vix import latest_structure

        vix = latest_structure().get("latest") or "Sin datos"
    except Exception:
        vix = "Sin datos"
    payload = {
        "symbol": symbol,
        "is_index": "US100" in key,
        "price": round(price, 8),
        "spread": round(spread, 8),
        "point": point,
        "now": now.isoformat(),
        "session": _session(now),
        "cost_r": costs,
        "vix": vix,
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
            "risk_overrides": item.get("risk_overrides") or {},
                "daily_stop": item["daily_stop"],
                "max_trades_per_day": item["max_trades_per_day"],
                "max_cost_r": item["max_cost_r"],
                "max_open": item["max_open"],
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
    "ema_ribbon_pullback": (
        "atr", "ema8", "ema13", "ema21", "high", "low", "open", "close",
    ),
    "vwap_bounce": ("atr", "vwap", "high", "low", "open", "close"),
    "orb_5m": ("atr", "orb5_high", "orb5_low", "orb5_valid"),
    "momentum_burst": ("atr", "high", "low", "open", "close"),
}

# Secciones adicionales que una estrategia mira fuera de su timeframe.
STRATEGY_EXTRA = {
    "trend_pullback": {"d1": ("close", "sma200")},
    "vwap_bounce": {"m15": ("ema9", "ema21", "ema50")},
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
                    level = setup_plan(strategy, side, snap, tf)
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
    window_open = session_open(item, now)
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
        "session_open": window_open,
        "budget": {
            "equity": round(equity, 2),
            "risk_per_trade": item["risk_per_trade"],
            "risk_overrides": item.get("risk_overrides") or {},
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
            "setups": [] if window_open is False else _style_setups(snap, strategies),
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
    model: str | None = None,
    settings: Settings | None = None,
) -> dict:
    if decision not in DECISIONS:
        raise AiTraderError(f"decisión inválida: {decision}")
    if source not in SOURCES:
        raise AiTraderError(f"source inválido: {source}")
    # El orquestador de sesión exporta TRADINGLAB_AI_MODEL con el modelo que
    # está usando opencode; si no hay modelo conocido se guarda NULL.
    model_name = model or os.getenv("TRADINGLAB_AI_MODEL") or None
    model_name = str(model_name).strip() if model_name else None
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
            " playbook_version, source, plan_id, model) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                model_name,
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
             db_path: str | Path, plan_id: str | None = None,
             defer_decision: bool = False,
             now: datetime | None = None) -> dict:
    style_name = item["style"]
    style = cfg["styles"][style_name]
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    health = _assert_demo(broker)
    if not style["enabled"]:
        raise AiTraderError(f"estilo {style_name} deshabilitado")
    from .lease import acquire as acquire_lease

    lease = acquire_lease(
        db_path, session=f"ai:{style_name}", now=now,
    )
    if not lease["ok"]:
        raise _Reject(
            f"otro host tiene el lease: {lease['reason']}",
            decision="skip", setup_valid=0,
        )
    if str(item["symbol"]).upper() not in cfg["slippage_price"]:
        raise _Reject(
            "Sin datos de slippage", decision="skip", setup_valid=0,
        )
    is_open = session_open(style, now)
    if is_open is False:
        window = style["session"]
        raise _Reject(
            f"{style_name}: fuera de ventana {window['start']}-{window['end']} "
            f"{window['tz']}",
            decision="skip", setup_valid=0,
        )
    cell_state = _cell_status(
        db_path, item["strategy"], item["symbol"], item["timeframe"]
    )
    if cell_state == "paused":
        raise _Reject(
            "celda pausada por el scoreboard; requiere reactivación del operador",
            decision="skip", setup_valid=1,
        )
    if cell_state == "destilada":
        raise _Reject(
            "celda destilada: la opera el bot destilado, no el LLM",
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
    if len(lane) >= int(style["max_open"]):
        raise _Reject(
            f"{style_name}: máximo de posiciones del estilo alcanzado "
            f"({style['max_open']})",
            decision="skip", setup_valid=1,
        )
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
    try:
        from .account_daily import account_daily_report

        account_daily = account_daily_report(
            db_path, cfg["account"], broker=broker, now=now,
        )
    except Exception as exc:
        raise _Reject(
            f"stop diario de cuenta sin datos: {exc}",
            decision="skip", setup_valid=0,
        ) from exc
    if not account_daily["allowed"]:
        raise _Reject(
            f"stop diario de la cuenta: {account_daily['reason']}",
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
    excluded = _exclusion_reason(
        cfg, item, snap, now or datetime.now(timezone.utc)
    )
    if excluded:
        raise _Reject(excluded, decision="skip", setup_valid=1, snapshot=snap)
    ok, reason = validate(item["strategy"], item["side"], snap, item["timeframe"])
    if not ok:
        raise _Reject(f"setup no válido: {reason}", decision="no_setup",
                      setup_valid=0, snapshot=snap)
    try:
        level = setup_plan(item["strategy"], item["side"], snap, item["timeframe"])
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
    tick_size = float(spec.get("tick_size") or spec.get("point") or 0.0)
    tick_value = float(spec.get("tick_value") or 0.0)
    value_per_price = (
        tick_value / tick_size if tick_size > 0 and tick_value > 0 else None
    )
    holding_nights = (
        _swing_holding_nights(db_path) if style_name == "swing" else 0.0
    )
    start_day = (now or datetime.now(timezone.utc)).date()
    cost_ratio = _cost_ratio(
        item["symbol"], price, float(snap["spread"]), dist,
        slippage_price=cfg["slippage_price"].get(
            str(item["symbol"]).upper()
        ),
        side=item["side"],
        holding_nights=holding_nights,
        start_day=start_day,
        value_per_price=value_per_price,
    )
    if cost_ratio is None:
        raise _Reject("coste/R Sin datos: comisión o swap no verificado",
                      decision="skip", setup_valid=1, snapshot=snap)
    max_cost = style["max_cost_r"]
    if max_cost is not None and cost_ratio > float(max_cost) + 1e-12:
        reason = (
            "skip: coste/R con swap"
            if holding_nights > 0
            else f"coste/R {cost_ratio:.3f} > {float(max_cost):.2f}"
        )
        raise _Reject(
            reason,
            decision="skip", setup_valid=1, snapshot=snap,
        )
    risk_pct = float(
        (style.get("risk_overrides") or {}).get(
            str(item["symbol"]).upper(), style["risk_per_trade"]
        )
    )
    risk_usd = equity * risk_pct
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
        from .accounts import load_accounts
        from .symbol_risk import (
            alert_risk_events,
            group_cap_usd,
            risk_group,
            risk_snapshot,
            symbol_cap_usd,
            total_cap_usd,
        )

        account_cfg = load_accounts().get(cfg["account"])
        live_positions = broker.positions()
        state = PropGuard.state_from_equity(
            rules, broker.equity_series(), initial_balance=rules.account_size,
            open_positions=len(live_positions),
        )
        balance = float(
            state.day_start_balance or state.day_start_equity or equity
        )
        risk = risk_snapshot(
            live_positions,
            broker,
            account_id=cfg["account"],
            account=account_cfg,
            balance=balance,
        )
        alert_risk_events(cfg["account"], risk, db_path=db_path)
        if risk["ea_over"]:
            first = risk["ea_over"][0]
            raise _Reject(
                f"skip: riesgo agregado ({first['kind']}) EA {first['name']} "
                f"{first['risk_usd']:,.2f} > {first['cap_usd']:,.2f}",
                decision="skip", setup_valid=1, snapshot=snap,
            )
        symbol = str(item["symbol"]).upper()
        group = risk_group(account_cfg, symbol)
        report = guard.evaluate(
            state, proposed_lots=lots, risk_per_lot=risk_per_lot,
            open_risk_usd=risk["total_usd"], new_position=True,
            symbol_open_risk_usd=risk["by_symbol"].get(symbol, 0.0),
            symbol_risk_cap_usd=symbol_cap_usd(account_cfg, symbol, balance),
            symbol=symbol,
            group_open_risk_usd=risk["by_group"].get(group, 0.0),
            group_risk_cap_usd=group_cap_usd(account_cfg, group, balance),
            group=group,
            total_open_risk_usd=risk["total_usd"],
            total_risk_cap_usd=total_cap_usd(account_cfg, balance),
            missing_sl=bool(risk["missing_sl"]),
        )
    except _Reject:
        raise
    except Exception as exc:
        raise _Reject(f"PropGuard no disponible: {exc}", decision="skip",
                      setup_valid=1, snapshot=snap) from exc
    if not report.allowed:
        reason = str(report.reason)
        if reason.startswith("riesgo agregado"):
            reason = f"skip: {reason}"
        else:
            reason = f"PropGuard: {reason}"
        raise _Reject(reason, decision="skip",
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
    decision = None
    if not defer_decision:
        decision = _record_decision(
            db_path=db_path, config=cfg, style=style_name, symbol=item["symbol"],
            timeframe=item["timeframe"], strategy=item["strategy"], setup_valid=True,
            decision="take", reason="propuesta aceptada", confidence=item["confidence"],
            snapshot_payload=snap, source="forward", plan_id=plan_id or pid,
            settings=settings,
        )
    return {
        "id": pid,
        "status": "proposed",
        "style": style_name,
        "strategy": item["strategy"],
        "decision_id": decision["id"] if decision else None,
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
            db_path: str | Path = DEFAULT_DB,
            plan_id: str | None = None,
            defer_decision: bool = False,
            now: datetime | None = None) -> dict:
    cfg = config or load_config()
    settings = settings or get_settings()
    if not cfg["enabled"]:
        raise AiTraderError("carril ai_trader deshabilitado")
    item = _validate_payload(payload, cfg)
    try:
        result = _propose(item, broker=broker, cfg=cfg, settings=settings,
                          db_path=db_path, plan_id=plan_id,
                          defer_decision=defer_decision, now=now)
    except _Reject as exc:
        params = {
            "style": item.get("style"), "symbol": item.get("symbol"),
            "strategy": item.get("strategy"), "timeframe": item.get("timeframe"),
            "decision": exc.decision,
        }
        if plan_id:
            params["plan_id"] = plan_id
        try:
            _record_decision(
                db_path=db_path, config=cfg, style=item["style"],
                symbol=item["symbol"], timeframe=item["timeframe"],
                strategy=item["strategy"], setup_valid=bool(exc.setup_valid),
                decision=exc.decision, reason=str(exc),
                confidence=item.get("confidence"),
                snapshot_payload=exc.snapshot, source="forward",
                plan_id=plan_id, settings=settings,
            )
        except Exception:
            pass
        _audit(db_path, "ai_trader_reject", params, "rejected",
               detail=str(exc), ok=0)
        raise
    audit_params = {
        "proposal_id": result["id"], "style": item["style"],
        "symbol": item["symbol"], "strategy": item["strategy"],
        "timeframe": item["timeframe"], "side": item["side"],
        "volume": result["order"]["volume"], "magic": result["order"]["magic"],
    }
    if plan_id:
        audit_params["plan_id"] = plan_id
    _audit(db_path, "ai_trader_propose", audit_params, "proposed",
           detail=item["thesis"])
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
    if symbol.upper() not in {item.upper() for item in style["universe"]}:
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


def _noplan_side(style_name: str, side: str) -> str | None:
    """Lado de la sombra sin plan: el contrario al real, solo en scalping."""
    if style_name != "scalping":
        return None
    return "sell" if str(side).lower() == "buy" else "buy"


def _twin_levels(entry: float, sl: float, tp: float | None, *,
                 seed: int, side: str | None = None) -> dict:
    """Niveles de una sombra con la misma geometría que la operación real.

    Sin ``side`` la dirección sale de una semilla fija (determinista por id).
    Con ``side`` se usa esa dirección; el scalping la usa para la sombra "sin
    plan", que toma el lado contrario al real (el que el bias habría excluido).
    """
    rng = random.Random(int(seed))
    twin_side = side or rng.choice(["buy", "sell"])
    sl_dist = abs(float(entry) - float(sl))
    tp_dist = abs(float(tp) - float(entry)) if tp is not None else sl_dist
    return {
        "side": twin_side,
        "entry": round(float(entry), 8),
        "sl": round(
            float(entry) - sl_dist if twin_side == "buy" else float(entry) + sl_dist, 8
        ),
        "tp": round(
            float(entry) + tp_dist if twin_side == "buy" else float(entry) - tp_dist, 8
        ),
    }


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
    stale = _stale_reason(
        broker, row["symbol"], row["timeframe"], datetime.now(timezone.utc)
    )
    if stale:
        reason = f"skip: {stale}"
        try:
            _record_decision(
                db_path=db_path,
                config=cfg,
                style=style_name,
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                strategy=str(row["setup"] or ""),
                setup_valid=False,
                decision="skip",
                reason=reason,
                source="forward",
            )
        except Exception:
            pass
        _alert_stale(db_path, style_name, row["symbol"], row["timeframe"], stale)
        raise StaleDataError(reason)
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
    entry = float(row["entry"])
    real_sl = float(row["sl"])
    real_tp = float(row["tp"]) if row["tp"] is not None else None
    shadow = _twin_levels(entry, real_sl, real_tp, seed=seed)
    noplan = None
    noplan_side = _noplan_side(style_name, side)
    if noplan_side:
        noplan = _twin_levels(
            entry, real_sl, real_tp, seed=seed, side=noplan_side,
        )
    with connect(db_path) as con:
        con.execute(
            "UPDATE ai_trades SET status='open', ticket=?, entry=?, shadow_side=?, "
            "shadow_entry=?, shadow_sl=?, shadow_tp=?, shadow_status='open', "
            "shadow_seed=?, shadow2_side=?, shadow2_entry=?, shadow2_sl=?, "
            "shadow2_tp=?, shadow2_status=?, updated_at=? WHERE proposal_id=?",
            (
                int(order.get("order_id") or 0), round(entry, 8),
                shadow["side"], shadow["entry"], shadow["sl"], shadow["tp"], seed,
                noplan["side"] if noplan else None,
                noplan["entry"] if noplan else None,
                noplan["sl"] if noplan else None,
                noplan["tp"] if noplan else None,
                "open" if noplan else None,
                now, proposal_id,
            ),
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
         "strategy": row["setup"], "timeframe": row["timeframe"], "side": side,
         "volume": float(row["volume"]), "magic": style["magic"]},
        "executed", detail=str(row["thesis"]),
    )
    return {
        "id": proposal_id, "status": "open", "style": style_name,
        "order": order, "fills": fills, "fills_error": fills_error,
    }


# --------------------------------------------------------------- plan/scalp


def _active_plans(db_path: str | Path, session_date: str) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM ai_plans WHERE session_date=? AND active=1 ORDER BY id",
            (session_date,),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            setups = json.loads(row["setups"] or "[]")
        except (TypeError, ValueError):
            setups = []
        if isinstance(setups, list):
            setups = [
                item if isinstance(item, dict)
                else {
                    "strategy": str(item),
                    "timeframe": STRATEGY_TIMEFRAME.get(str(item), ""),
                }
                for item in setups
                if isinstance(item, (dict, str))
            ]
        try:
            forbidden = json.loads(row["forbidden_hours"] or "[]")
        except (TypeError, ValueError):
            forbidden = []
        if not isinstance(setups, list) or not setups:
            continue
        out.append({
            "plan_id": str(row["plan_id"]),
            "session_date": str(row["session_date"]),
            "symbol": str(row["symbol"]),
            "setups": setups,
            "bias": (
                str(row["bias"] or "both")
                if str(row["bias"] or "both") in {"long", "short", "both"}
                else "both"
            ),
            "forbidden_hours": forbidden if isinstance(forbidden, list) else [],
            "reason": str(row["reason"] or ""),
            "playbook_version": int(row["playbook_version"] or 0),
            "active": bool(row["active"]),
        })
    return out


def _forbidden_match(now: datetime, ranges: list, zone_name: str) -> str | None:
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = NEW_YORK
    current = _as_utc(now).astimezone(zone).time()
    for text in ranges:
        raw = str(text).strip()
        try:
            start_s, end_s = raw.split("-", 1)
            start = dtime.fromisoformat(start_s.strip())
            end = dtime.fromisoformat(end_s.strip())
        except ValueError:
            continue
        if start <= end:
            if start <= current < end:
                return raw
        elif current >= start or current < end:
            return raw
    return None


def _record_scalp_skip(plan: dict, setup: dict, reason: str, *,
                       cfg: dict, settings: Settings, db_path: str | Path,
                       snapshot: dict | None = None,
                       setup_valid: bool = False) -> None:
    try:
        _record_decision(
            db_path=db_path, config=cfg, style="scalping",
            symbol=plan["symbol"], timeframe=setup.get("timeframe"),
            strategy=setup.get("strategy") or "scalp", setup_valid=setup_valid,
            decision="skip", reason=reason, confidence=None,
            snapshot_payload=snapshot, source="forward",
            plan_id=plan.get("plan_id"), settings=settings,
        )
    except Exception:
        pass


def create_plan(payload: dict, *, config: dict | None = None,
                settings: Settings | None = None,
                db_path: str | Path = DEFAULT_DB) -> dict:
    """Valida y guarda el plan de scalping de un símbolo y sesión."""
    cfg = config or load_config()
    settings = settings or get_settings()
    if not isinstance(payload, dict):
        raise AiTraderError("plan inválido")
    style = cfg["styles"].get("scalping")
    if style is None:
        raise AiTraderError("estilo scalping no configurado")
    raw_symbol = str(payload.get("symbol") or "").strip()
    universe = {str(item).lower(): str(item) for item in cfg["universe"]}
    if raw_symbol.lower() not in universe:
        raise AiTraderError(f"símbolo fuera del universo: {raw_symbol}")
    symbol = universe[raw_symbol.lower()]
    if symbol.upper() not in {str(item).upper() for item in style["universe"]}:
        raise AiTraderError(f"{symbol} fuera del universo de scalping")
    allowed = style["allowed"].get(symbol.upper(), {})
    if not allowed:
        raise AiTraderError(f"scalping no tiene estrategias asignadas a {symbol}")
    raw_setups = payload.get("setups")
    if raw_setups is None:
        raw_setups = payload.get("setups_permitidos")
    if not isinstance(raw_setups, list) or not raw_setups:
        raise AiTraderError("setups debe ser una lista no vacía")
    setups: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_setups:
        if isinstance(raw, str):
            strategy = raw.strip()
            timeframe = None
        elif isinstance(raw, dict):
            strategy = str(raw.get("strategy") or "").strip()
            timeframe = raw.get("timeframe")
        else:
            raise AiTraderError("cada setup debe ser texto u objeto {strategy,timeframe}")
        if strategy not in allowed:
            raise AiTraderError(f"estrategia no permitida en scalping/{symbol}: {strategy}")
        frames = allowed[strategy]
        tf = str(timeframe or frames[0]).strip().upper()
        if tf not in frames:
            raise AiTraderError(f"{strategy} no asignada a {symbol} en {tf}")
        key = (strategy, tf)
        if key not in seen:
            setups.append({"strategy": strategy, "timeframe": tf})
            seen.add(key)
    bias = str(payload.get("bias") or "").strip().lower()
    if bias not in {"long", "short", "both"}:
        raise AiTraderError("bias debe ser long, short o both")
    raw_forbidden = payload.get("forbidden_hours")
    if raw_forbidden is None:
        raw_forbidden = payload.get("horas_prohibidas", [])
    if isinstance(raw_forbidden, str):
        raw_forbidden = [part.strip() for part in raw_forbidden.split(",") if part.strip()]
    if raw_forbidden is None:
        raw_forbidden = []
    if not isinstance(raw_forbidden, list):
        raise AiTraderError("forbidden_hours debe ser una lista")
    forbidden: list[str] = []
    for item in raw_forbidden:
        text = str(item).strip()
        try:
            start_s, end_s = text.split("-", 1)
            start = dtime.fromisoformat(start_s.strip())
            end = dtime.fromisoformat(end_s.strip())
        except ValueError as exc:
            raise AiTraderError(f"hora prohibida inválida: {text}") from exc
        if start == end:
            raise AiTraderError(f"hora prohibida vacía: {text}")
        forbidden.append(
            f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        )
    reason = str(payload.get("reason") or payload.get("motivo") or "").strip()
    if not reason or len(reason) > 300:
        raise AiTraderError("motivo obligatorio y <= 300 caracteres")
    plan_id = str(payload.get("plan_id") or uuid.uuid4().hex).strip()
    if not plan_id:
        raise AiTraderError("plan_id inválido")
    session_date = _reset_date(settings)
    init_db(db_path)
    with connect(db_path) as con:
        exists = con.execute(
            "SELECT plan_id FROM ai_plans WHERE plan_id=?", (plan_id,)
        ).fetchone()
        if exists is not None:
            raise AiTraderError(f"plan_id ya existe: {plan_id}")
        con.execute(
            "UPDATE ai_plans SET active=0 WHERE symbol=? AND session_date=? AND active=1",
            (symbol, session_date),
        )
        con.execute(
            "INSERT INTO ai_plans(plan_id, ts, session_date, symbol, setups, bias, "
            "forbidden_hours, reason, playbook_version, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,1,?)",
            (
                plan_id, utcnow(), session_date, symbol,
                json.dumps(setups, ensure_ascii=False, separators=(",", ":")),
                bias,
                json.dumps(forbidden, ensure_ascii=False, separators=(",", ":")),
                reason, cfg["playbook_version"], utcnow(),
            ),
        )
    out = {
        "plan_id": plan_id,
        "session_date": session_date,
        "symbol": symbol,
        "setups": setups,
        "bias": bias,
        "forbidden_hours": forbidden,
        "reason": reason,
        "playbook_version": cfg["playbook_version"],
        "active": True,
    }
    _audit(
        db_path, "ai_trader_plan",
        {"plan_id": plan_id, "symbol": symbol, "bias": bias,
         "setups": [item["strategy"] for item in setups]},
        "active", detail=reason,
    )
    return out


def scalp_window_open(now: datetime | None = None, *,
                      config: dict | None = None) -> bool:
    cfg = config or load_config()
    style = cfg["styles"].get("scalping")
    return style is not None and session_open(style, now) is True


def scalp(*, broker=None, config: dict | None = None,
          settings: Settings | None = None,
          db_path: str | Path = DEFAULT_DB,
          now: datetime | None = None) -> dict:
    """Una pasada del scalper sin LLM. El plan manda; fuera de ventana no hace nada."""
    cfg = config or load_config()
    settings = settings or get_settings()
    moment = _as_utc(now)
    style = cfg["styles"].get("scalping")
    if not cfg["enabled"] or style is None or not style["enabled"]:
        return {"status": "disabled"}
    # El scalp corre cada minuto y su candado deja sin turno a AI-Manage.
    # Proteger aquí garantiza que BE/50 % del TP se aplique a tiempo.
    protected: list[dict] = []
    if broker is not None:
        try:
            protected = manage(broker=broker, config=cfg, db_path=db_path)
        except Exception:
            protected = []
    if session_open(style, moment) is not True:
        return {
            "status": "outside_window", "now": moment.isoformat(),
            "managed": len(protected),
        }
    session_date = _reset_date(settings)
    plans = _active_plans(db_path, session_date)
    if not plans:
        return {
            "status": "no_plan", "session_date": session_date,
            "managed": len(protected),
        }

    def fail(status: str, reason: str, *, ok: int = 0) -> dict:
        for plan in plans:
            if plan["setups"]:
                _record_scalp_skip(
                    plan, plan["setups"][0], reason, cfg=cfg, settings=settings,
                    db_path=db_path,
                )
        _audit(
            db_path, "ai_trader_scalp",
            {"session_date": session_date, "plans": len(plans)},
            status, detail=reason, ok=ok,
        )
        return {
            "status": status, "reason": reason,
            "session_date": session_date, "plans": len(plans),
            "managed": len(protected),
        }

    try:
        state = load_killswitch_state(db_path)
    except Exception:
        state = None
    if state is not None and state.active:
        return fail(
            "killswitch", f"kill-switch activo: {state.reason}", ok=1
        )
    if broker is None:
        return fail("mt5_down", "MT5 no responde")
    try:
        health = _assert_demo(broker)
    except Exception as exc:
        return fail("mt5_down", f"MT5 no responde: {exc}")
    try:
        state, _ = ensure_killswitch(
            db_path, broker.equity_series(), settings.risk,
            current=float(health.get("equity") or 0),
            tz=settings.timezone, now=moment,
        )
    except Exception:
        try:
            state = load_killswitch_state(db_path)
        except Exception:
            state = None
    if state is not None and state.active:
        return fail(
            "killswitch", f"kill-switch activo: {state.reason}", ok=1
        )

    missing_slippage = sorted({
        plan["symbol"] for plan in plans
        if plan["symbol"].upper() not in cfg["slippage_price"]
    })
    if missing_slippage:
        return fail(
            "no_slippage",
            f"Sin datos de slippage: {', '.join(missing_slippage)}",
            ok=1,
        )
    try:
        from .account_daily import account_daily_report

        account_daily = account_daily_report(
            db_path, cfg["account"], broker=broker, now=moment,
        )
    except Exception as exc:
        return fail(
            "account_stop", f"stop diario de cuenta sin datos: {exc}", ok=1
        )
    if not account_daily["allowed"]:
        return fail(
            "account_stop",
            f"stop diario de la cuenta: {account_daily['reason']}",
            ok=1,
        )

    executed: list[dict] = []
    skipped = 0
    for plan in plans:
        if plan["playbook_version"] != int(cfg["playbook_version"]):
            reason = (
                f"plan de playbook {plan['playbook_version']}; "
                f"actual {cfg['playbook_version']}"
            )
            if plan["setups"]:
                _record_scalp_skip(
                    plan, plan["setups"][0], reason, cfg=cfg, settings=settings,
                    db_path=db_path,
                )
            skipped += 1
            continue
        if plan["symbol"].upper() not in {
            str(item).upper() for item in style["universe"]
        }:
            if plan["setups"]:
                _record_scalp_skip(
                    plan, plan["setups"][0],
                    "símbolo fuera del universo de scalping",
                    cfg=cfg, settings=settings, db_path=db_path,
                )
            skipped += 1
            continue
        window_tz = (style.get("session") or {}).get("tz") or "America/New_York"
        forbidden = _forbidden_match(
            moment, plan["forbidden_hours"], window_tz
        )
        if forbidden:
            reason = f"plan: hora prohibida {forbidden}"
            if plan["setups"]:
                _record_scalp_skip(
                    plan, plan["setups"][0], reason, cfg=cfg, settings=settings,
                    db_path=db_path,
                )
            skipped += 1
            continue
        try:
            snap = snapshot_symbol(
                broker, plan["symbol"], cfg, db_path,
                style="scalping", closed_only=True,
            )
        except Exception as exc:
            reason = f"Sin datos: {exc}"
            for setup in plan["setups"]:
                _record_scalp_skip(
                    plan, setup, reason, cfg=cfg, settings=settings,
                    db_path=db_path,
                )
            skipped += len(plan["setups"])
            continue
        snap_now = pd.Timestamp(snap.get("now") or moment)
        plan_executed = False
        for setup in plan["setups"]:
            strategy = str(setup.get("strategy") or "")
            timeframe = str(
                setup.get("timeframe") or STRATEGY_TIMEFRAME.get(strategy, "")
            ).upper()
            if not supports(strategy, timeframe):
                _record_scalp_skip(
                    plan, setup, "estrategia/timeframe no soportado",
                    cfg=cfg, settings=settings, db_path=db_path,
                )
                skipped += 1
                continue
            block = snap.get(TF_SECTION.get(timeframe, "")) or {}
            if block.get("error"):
                _record_scalp_skip(
                    plan, setup, f"Sin datos: {block['error']}",
                    cfg=cfg, settings=settings, db_path=db_path,
                )
                skipped += 1
                continue
            last_raw = block.get("last_bar")
            if last_raw in (None, "", "Sin datos"):
                _record_scalp_skip(
                    plan, setup, "Sin datos: última vela",
                    cfg=cfg, settings=settings, db_path=db_path,
                )
                skipped += 1
                continue
            duration = pd.Timedelta(minutes=TF_MINUTES.get(timeframe, 60))
            last_close = pd.Timestamp(last_raw) + duration
            if snap_now - last_close > 2 * duration:
                _record_scalp_skip(
                    plan, setup,
                    f"datos obsoletos: última vela {last_raw}",
                    cfg=cfg, settings=settings, db_path=db_path,
                    snapshot=snap,
                )
                skipped += 1
                continue
            sides = {
                "long": ["buy"],
                "short": ["sell"],
                "both": ["buy", "sell"],
            }[plan["bias"]]
            for side in sides:
                payload = {
                    "style": "scalping",
                    "strategy": strategy,
                    "symbol": plan["symbol"],
                    "timeframe": timeframe,
                    "side": side,
                    "thesis": plan["reason"][:300],
                    "confidence": 3,
                }
                try:
                    result = propose(
                        payload, broker=broker, config=cfg, settings=settings,
                        db_path=db_path, plan_id=plan["plan_id"],
                        defer_decision=True, now=moment,
                    )
                except AiTraderError as exc:
                    if not isinstance(exc, _Reject):
                        _record_scalp_skip(
                            plan, setup, str(exc), cfg=cfg, settings=settings,
                            db_path=db_path, snapshot=snap,
                        )
                    skipped += 1
                    continue
                try:
                    order = execute(
                        result["id"], broker=broker, config=cfg,
                        db_path=db_path,
                    )
                except StaleDataError:
                    skipped += 1
                    continue
                except Exception as exc:
                    _record_scalp_skip(
                        plan, setup, f"execute: {exc}",
                        cfg=cfg, settings=settings, db_path=db_path,
                        snapshot=result.get("snapshot"), setup_valid=True,
                    )
                    skipped += 1
                    continue
                _record_decision(
                    db_path=db_path, config=cfg, style="scalping",
                    symbol=plan["symbol"], timeframe=timeframe,
                    strategy=strategy, setup_valid=True, decision="take",
                    reason="señal ejecutada", confidence=3,
                    snapshot_payload=result.get("snapshot"), source="forward",
                    plan_id=plan["plan_id"], settings=settings,
                )
                executed.append({
                    "plan_id": plan["plan_id"],
                    "proposal_id": result["id"],
                    "symbol": plan["symbol"],
                    "strategy": strategy,
                    "timeframe": timeframe,
                    "side": side,
                    "ticket": (order.get("order") or {}).get("order_id"),
                })
                plan_executed = True
                break
            if plan_executed:
                break

    _audit(
        db_path, "ai_trader_scalp",
        {"session_date": session_date, "plans": len(plans)},
        "executed" if executed else "no_trade",
        detail=f"executed={len(executed)} skipped={skipped}",
    )
    return {
        "status": "ok",
        "session_date": session_date,
        "plans": len(plans),
        "executed": executed,
        "skipped": skipped,
    }


# -------------------------------------------------------- manage / cierres


SHADOW_RATE_COUNTS = {
    "M1": 20_000,
    "M5": 6_000,
    "M15": 2_000,
    "H1": 1_000,
    "H4": 3_000,
}


def _shadow_rates(broker, symbol: str, timeframe: str) -> pd.DataFrame:
    """Barras suficientes para inferir el offset semanal también en M1."""
    key = str(timeframe or "H1").upper()
    return broker.rates(symbol, key, SHADOW_RATE_COUNTS.get(key, 800))


def _shadow_window(
    bars: pd.DataFrame, start, end, timeframe: str
) -> pd.DataFrame:
    """Incluye la vela que contiene la entrada y la que contiene la salida."""
    minutes = max(1, int(TF_MINUTES.get(str(timeframe).upper(), 60)))
    first = pd.Timestamp(start).floor(f"{minutes}min")
    last = pd.Timestamp(end).ceil(f"{minutes}min")
    return bars[(bars.index >= first) & (bars.index <= last)]


def _shadow_sim(row: dict, bars: pd.DataFrame, prefix: str = "shadow",
                strategy: str | None = None) -> dict:
    side = str(row.get(f"{prefix}_side") or "")
    entry = float(row.get(f"{prefix}_entry") or row.get("entry") or 0)
    sl = float(row.get(f"{prefix}_sl") or row.get("sl") or 0)
    tp = float(row.get(f"{prefix}_tp") or row.get("tp") or 0)
    if not side or bars is None or len(bars) < 1:
        return {"status": "Sin datos", "r": None}
    short = side == "sell"
    risk = abs(entry - sl)
    if risk <= 0:
        return {"status": "Sin datos", "r": None}
    strat = strategy or str(row.get("setup") or "")
    atr_series = atr(bars)
    sma5 = bars["close"].rolling(5).mean() if strat == "rsi2_connors" else None
    lows10 = bars["low"].rolling(10).min() if strat == "donchian_turtle" else None
    highs10 = bars["high"].rolling(10).max() if strat == "donchian_turtle" else None
    best = entry
    for ts, bar in bars.iterrows():
        high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        if short:
            best = min(best, low)
            if high >= sl:
                return {"status": "closed", "r": round((entry - sl) / risk, 4)}
            if tp and low <= tp:
                return {"status": "closed", "r": round((entry - tp) / risk, 4)}
            profit_r = (entry - close) / risk
        else:
            best = max(best, high)
            if low <= sl:
                return {"status": "closed", "r": round((sl - entry) / risk, 4)}
            if tp and high >= tp:
                return {"status": "closed", "r": round((tp - entry) / risk, 4)}
            profit_r = (close - entry) / risk
        if strat == "rsi2_connors" and not short and sma5 is not None:
            value = sma5.loc[ts]
            if pd.notna(value) and close > float(value):
                return {"status": "closed", "r": round((close - entry) / risk, 4)}
        if strat == "donchian_turtle":
            if short:
                channel = highs10.loc[ts]
                if pd.notna(channel):
                    candidate = float(channel)
                    if profit_r >= 0.5:
                        candidate = min(candidate, entry)
                    if candidate < sl:
                        sl = candidate
            else:
                channel = lows10.loc[ts]
                if pd.notna(channel):
                    candidate = float(channel)
                    if profit_r >= 0.5:
                        candidate = max(candidate, entry)
                    if candidate > sl:
                        sl = candidate
        else:
            new_sl = next_stop(
                side=side, entry=entry, best=best,
                atr_value=float(atr_series.loc[ts]),
                current_sl=sl, profit_r=profit_r, digits=8,
            )
            if new_sl is not None:
                sl = new_sl
    last = float(bars["close"].iloc[-1])
    r = (entry - last) / risk if short else (last - entry) / risk
    return {"status": "open", "r": round(r, 4)}


SCALPING_SETUPS = {
    "ema_ribbon_pullback",
    "vwap_bounce",
    "orb_5m",
    "momentum_burst",
}


def _forced_close_reason(setup: str, opened: datetime, now: datetime) -> str | None:
    """Cierre obligatorio de las estrategias con hora de salida."""
    if setup in SCALPING_SETUPS:
        zone, close_at = NEW_YORK, dtime(12, 0)
    elif setup == "orb_ny":
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
            base = _donchian_stop(
                broker, position["symbol"], position["side"], entry, sl,
                profit_r, now, digits,
            )
        else:
            base = next_stop(
                side=position["side"], entry=entry, best=best,
                atr_value=float(atr(bars).iloc[-1]),
                current_sl=sl, profit_r=profit_r,
                digits=digits,
                min_distance=float(spec.get("stops_level") or 0) * float(spec.get("point") or 0),
            )
        min_distance = float(spec.get("stops_level") or 0) * float(spec.get("point") or 0)
        candidates: list[float] = []
        if base is not None:
            candidates.append(base)
        tp_price = float(position.get("tp") or 0)
        if tp_price > 0:
            protected = tp_protection_stop(
                side=position["side"], entry=entry, tp=tp_price,
                best=best, price=price, current_sl=sl, digits=digits,
                min_distance=min_distance,
            )
            if protected is not None:
                candidates.append(protected)

        def stop_valid(value: float) -> bool:
            # El SL debe quedar al lado correcto del precio actual; el
            # trailing puede proponer un nivel ya atravesado y el bróker lo
            # rechaza, dejando sin aplicar también el candidato del TP.
            if short:
                return value > price + min_distance + 1e-9
            return value < price - min_distance - 1e-9

        candidates = [value for value in candidates if stop_valid(value)]
        candidate = (
            min(candidates) if short else max(candidates)
        ) if candidates else None
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
    sync_closed(broker, db_path=db_path, now=now)
    return out


def sync_closed(broker, *, db_path: str | Path = DEFAULT_DB,
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
            # El terminal interpreta el rango como hora de servidor (GMT+2);
            # con `now + 1h` un cierre reciente podía quedar fuera y la fila
            # seguía "open" aunque el broker ya la había cerrado.
            deals = broker.history_deals(
                datetime.fromisoformat(str(row["ts"])) - timedelta(hours=2),
                moment + timedelta(days=1),
            )
        except Exception:
            continue
        rel = [d for d in deals if int(d.get("position_id") or 0) == ticket]
        # El cierre puede llevar el magic por defecto de MT5 (20261105), no
        # el magic de la entrada; el position_id es el identificador único.
        # Solo se cierra con un deal de salida. Si la posición acaba de abrir
        # y el broker aún no la lista, un deal de entrada no es un cierre:
        # marcarla cerrada con pnl 0 falseaba el marcador (race del 17/11).
        exits = [d for d in rel if int(d.get("entry") or 0) != 0]
        if not exits:
            continue
        pnl = sum(float(d.get("profit") or 0) + float(d.get("swap") or 0)
                  + float(d.get("commission") or 0) for d in rel)
        risk = float(row.get("risk_usd") or 0)
        result_r = round(pnl / risk, 4) if risk else None
        shadow_r = None
        shadow2_r = None
        try:
            bars = _shadow_rates(
                broker, row["symbol"], str(row.get("timeframe") or "H1")
            )
            start = pd.Timestamp(row["ts"])
            end = pd.Timestamp(str(exits[-1].get("ts_utc") or moment.isoformat()))
            since = _shadow_window(
                bars, start, end, str(row.get("timeframe") or "H1")
            )
            if len(since) and row.get("shadow_entry"):
                shadow_r = _shadow_sim(
                    row, since, prefix="shadow", strategy=row.get("setup")
                ).get("r")
            if len(since) and row.get("shadow2_entry"):
                shadow2_r = _shadow_sim(
                    row, since, prefix="shadow2", strategy=row.get("setup")
                ).get("r")
        except Exception:
            pass
        with connect(db_path) as con:
            con.execute(
                "UPDATE ai_trades SET status='closed', exit_price=?, exit_ts=?, pnl=?, "
                "r_multiple=?, result_r=?, shadow_r=?, shadow2_r=?, updated_at=? "
                "WHERE proposal_id=?",
                (float(exits[-1].get("price") or 0),
                 str(exits[-1].get("ts_utc") or moment.isoformat()),
                 round(pnl, 2), result_r, result_r, shadow_r, shadow2_r,
                 utcnow(), row["proposal_id"]),
            )
        closed += 1
    return closed


# ------------------------------------------------------------- scoreboard


def _bootstrap_ci(values: list, *, level: float = 0.90, iterations: int = 2000,
                  seed: int = 0) -> list | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    if len(clean) == 1:
        return [round(clean[0], 4), round(clean[0], 4)]
    rng = random.Random(int(seed))
    n = len(clean)
    means = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(n):
            total += clean[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    alpha = (1.0 - level) / 2.0
    lo = means[max(0, int(alpha * iterations))]
    hi = means[min(iterations - 1, int((1.0 - alpha) * iterations) - 1)]
    return [round(lo, 4), round(hi, 4)]


def _diff_stats(pairs: list[tuple], *, seed: int = 0) -> dict:
    clean = [
        (float(real), float(other))
        for real, other in pairs
        if real is not None and other is not None
    ]
    if not clean:
        return {"n": 0, "diff": None, "ci90": None, "avg_r": None}
    diffs = [real - other for real, other in clean]
    return {
        "n": len(diffs),
        "diff": round(sum(diffs) / len(diffs), 4),
        "ci90": _bootstrap_ci(diffs, seed=seed),
        "avg_r": round(sum(other for _, other in clean) / len(clean), 4),
    }


def _slippage_avg(db_path: str | Path, bot: str, symbol: str) -> tuple:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT AVG(slippage_bps) AS avg, COUNT(*) AS n FROM tca "
            "WHERE bot=? AND symbol=? AND slippage_bps IS NOT NULL",
            (bot, symbol),
        ).fetchone()
    if row is None or row["avg"] is None:
        return None, 0
    return round(float(row["avg"]), 2), int(row["n"])


def _summarize_cells(items: list[dict], db_path: str | Path) -> list[dict]:
    groups: dict[tuple, list] = {}
    for item in items:
        key = (
            item.get("style") or "Sin datos",
            item.get("strategy") or "Sin datos",
            item.get("symbol") or "Sin datos",
            item.get("timeframe") or "Sin datos",
            item.get("playbook_version"),
        )
        groups.setdefault(key, []).append(item)
    cells = []
    for (style, strategy, symbol, timeframe, playbook_version), rows in sorted(
        groups.items(), key=lambda pair: tuple(str(part) for part in pair[0])
    ):
        rs = [float(row["r"]) for row in rows if row.get("r") is not None]
        n = len(rs)
        seed = int(hashlib.sha256(
            f"{style}|{strategy}|{symbol}|{timeframe}".encode()
        ).hexdigest()[:8], 16)
        ci = _bootstrap_ci(rs, seed=seed)
        if n < 30:
            state = "exploring"
        elif ci is not None and ci[0] > 0:
            state = "winner"
        elif ci is not None and ci[1] < 0:
            state = "loser"
        else:
            state = "neutral"
        shadow = _diff_stats(
            [(row.get("r"), row.get("shadow_r")) for row in rows], seed=seed + 1
        )
        noplan = _diff_stats(
            [(row.get("r"), row.get("noplan_r")) for row in rows], seed=seed + 2
        )
        costs = [
            float(row["cost_ratio"]) for row in rows
            if row.get("cost_ratio") is not None
        ]
        slippage, slippage_n = _slippage_avg(
            db_path, f"ai:{style}", symbol
        )
        cells.append({
            "style": style,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "playbook_version": playbook_version,
            "n": n,
            "hit": round(sum(1 for r in rs if r > 0) / n, 3) if n else None,
            "avg_r": round(sum(rs) / n, 4) if n else None,
            "expectancy_r": round(sum(rs) / n, 4) if n else None,
            "ci90_r": ci,
            "state": state,
            "shadow": shadow,
            "noplan": noplan if noplan["n"] else None,
            "shadow_expectancy_r": shadow["avg_r"],
            "cost_ratio_avg": round(sum(costs) / len(costs), 4) if costs else None,
            "slippage_avg": slippage,
            "slippage_n": slippage_n,
            "insufficient": n < 30,
            "cell_status": _cell_status(db_path, strategy, symbol, timeframe),
        })
    return cells


def _pause_cells(cells: list[dict], db_path: str | Path) -> None:
    init_db(db_path)
    for cell in cells:
        if cell["n"] < 30:
            continue
        state = cell.get("state")
        if state == "loser":
            ci = cell.get("ci90_r") or [None, None]
            reason = f"IC90 R [{ci[0]:.3f}, {ci[1]:.3f}] < 0"
        elif state is None and cell.get("expectancy_r") is not None and cell.get("shadow_expectancy_r") is not None:
            if cell["expectancy_r"] >= cell["shadow_expectancy_r"]:
                continue
            reason = (
                f"expectativa {cell['expectancy_r']:.3f}R < "
                f"sombra {cell['shadow_expectancy_r']:.3f}R"
            )
        else:
            continue
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, reason, updated_at) "
                "VALUES(?,?,?,'paused',?,?) ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
                "status='paused', reason=excluded.reason, updated_at=excluded.updated_at",
                (cell["strategy"], cell["symbol"], cell["timeframe"], reason, utcnow()),
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
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM ai_trades "
            "WHERE COALESCE(source,'forward')='forward' "
            "AND status IN ('open','closed') ORDER BY ts").fetchall()]
    positions = {int(p["ticket"]): p for p in (broker.positions() or [])}
    bars_cache: dict[tuple, pd.DataFrame] = {}
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
        timeframe = str(row.get("timeframe") or "H1")

        def _simulate(prefix: str) -> dict:
            if row["status"] == "closed":
                stored = row.get(f"{prefix}_r")
                if stored is not None:
                    return {"status": "closed", "r": round(float(stored), 4)}
            if not row.get(f"{prefix}_entry"):
                return {"status": "Sin datos", "r": None}
            key = (row["symbol"], timeframe)
            if key not in bars_cache:
                bars_cache[key] = _shadow_rates(
                    broker, row["symbol"], timeframe
                )
            bars = bars_cache[key]
            end = (
                pd.Timestamp(row["exit_ts"]) if row.get("exit_ts")
                else pd.Timestamp.now(tz="UTC")
            )
            since = _shadow_window(
                bars, row["ts"], end, timeframe
            )
            if len(since) == 0:
                return {"status": "Sin datos", "r": None}
            return _shadow_sim(
                row, since, prefix=prefix, strategy=row.get("setup")
            )

        shadow = {"status": "Sin datos", "r": None}
        noplan = {"status": "Sin datos", "r": None}
        try:
            shadow = _simulate("shadow")
        except Exception:
            pass
        try:
            noplan = _simulate("shadow2")
        except Exception:
            pass
        out.append({
            "id": row["proposal_id"], "ts": row["ts"], "symbol": row["symbol"],
            "style": row.get("style"), "strategy": row["setup"],
            "timeframe": row.get("timeframe") or "Sin datos",
            "side": row["side"], "status": row["status"],
            "r": round(real_r, 4) if real_r is not None else None,
            "shadow_r": shadow.get("r"), "noplan_r": noplan.get("r"),
            "cost_ratio": row.get("cost_ratio"),
            "playbook_version": row.get("playbook_version"),
        })
    cells = _summarize_cells(
        [
            {
                "style": item["style"] or "Sin datos",
                "strategy": item["strategy"],
                "symbol": item["symbol"],
                "timeframe": item["timeframe"],
                "r": item["r"],
                "shadow_r": item["shadow_r"],
                "noplan_r": item["noplan_r"],
                "cost_ratio": item["cost_ratio"],
                "playbook_version": item["playbook_version"],
            }
            for item in out
        ],
        db_path,
    )
    for cell in cells:
        cell["cell_status"] = _cell_status(
            db_path, cell["strategy"], cell["symbol"], cell["timeframe"]
        )
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
            "risk_overrides": item.get("risk_overrides") or {},
            "max_cost_r": item["max_cost_r"],
            "max_open": item["max_open"],
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
    try:
        from .account_daily import account_daily_report

        account_daily = account_daily_report(
            db_path, cfg["account"], broker=broker,
        )
    except Exception as exc:
        account_daily = {
            "allowed": None, "reason": f"Sin datos: {exc}",
            "daily_stop_pct": None, "daily_stop_usd": None,
            "pnl_today": None, "loss_used_usd": None,
            "remaining_usd": None, "floating_by_magic": {},
        }
    account_daily["ai_pnl_today"] = round(
        sum(float(item["pnl_today"]) for item in styles.values()), 2
    )
    if account_daily.get("pnl_today") is not None:
        account_daily["forward_otros_pnl_today"] = round(
            float(account_daily["pnl_today"])
            - float(account_daily["ai_pnl_today"]), 2
        )
    return {
        "generated_at": utcnow(),
        "account": cfg["account"],
        "playbook_version": cfg["playbook_version"],
        "equity": round(equity, 2),
        "styles": styles,
        "account_daily": account_daily,
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


def _distill_panel(db_path: str | Path) -> dict:
    try:
        from .ai_distill import panel_payload

        return panel_payload(db_path)
    except Exception as exc:
        return {
            "funnel": {
                "ia_ganadoras": 0, "destiladas": 0, "validadas": 0,
                "incubando": 0, "promovibles": 0,
            },
            "bots": [],
            "n": 0,
            "error": str(exc)[:200],
        }


def panel(db_path: str | Path = DEFAULT_DB, *,
          equity: float | None = None,
          account_risk: dict | None = None) -> dict:
    cfg = load_config()
    settings = get_settings()
    init_db(db_path)
    with connect(db_path) as con:
        all_rows = [dict(r) for r in con.execute(
            "SELECT proposal_id, ts, style, symbol, setup, side, timeframe, thesis, "
            "confidence, entry, sl, tp, volume, risk_usd, status, pnl, r_multiple, "
            "result_r, shadow_r, shadow2_r, cost_ratio, ticket, exit_ts "
            "FROM ai_trades WHERE COALESCE(source,'forward')='forward' "
            "ORDER BY ts DESC").fetchall()]
        decisions = [dict(r) for r in con.execute(
            "SELECT id, ts, style, symbol, strategy, timeframe, decision, reason, "
            "confidence FROM ai_decisions WHERE source='forward' "
            "ORDER BY id DESC LIMIT 50").fetchall()]
        lessons = [dict(r) for r in con.execute(
            "SELECT id, hypothesis, status FROM lessons WHERE status='proposed' "
            "AND kind='lesson' ORDER BY id DESC LIMIT 10").fetchall()]
        cells = [dict(r) for r in con.execute(
            "SELECT strategy, symbol, timeframe, status, reason FROM ai_cell_state "
            "WHERE status='paused' ORDER BY updated_at DESC").fetchall()]
    rows = all_rows
    opened = [r for r in rows if r["status"] == "open"]
    closed = [r for r in rows if r["status"] == "closed"]
    real = [
        float(r["result_r"] if r["result_r"] is not None else r["r_multiple"])
        for r in closed
        if r["result_r"] is not None or r["r_multiple"] is not None
    ]
    shadow = [float(r["shadow_r"]) for r in closed if r["shadow_r"] is not None]
    noplan = [float(r["shadow2_r"]) for r in closed if r["shadow2_r"] is not None]
    items = []
    for row in all_rows:
        if row["status"] != "closed":
            continue
        value = (
            row["result_r"] if row["result_r"] is not None
            else row["r_multiple"]
        )
        if value is None:
            continue
        items.append({
            "style": row.get("style") or "Sin datos",
            "strategy": row["setup"], "symbol": row["symbol"],
            "timeframe": row.get("timeframe") or "Sin datos",
            "r": float(value), "shadow_r": row.get("shadow_r"),
            "noplan_r": row.get("shadow2_r"),
            "cost_ratio": row.get("cost_ratio"),
            "playbook_version": row.get("playbook_version"),
        })
    day_start = pd.Timestamp(_day_start(settings))
    styles_budget = {}
    for name, style in cfg["styles"].items():
        style_rows = [r for r in all_rows if (r.get("style") or "") == name]
        pnl_today = 0.0
        open_risk = 0.0
        for row in style_rows:
            if row["status"] == "open":
                open_risk += float(row.get("risk_usd") or 0.0)
                continue
            stamp = row.get("exit_ts") or row.get("ts")
            try:
                if pd.Timestamp(stamp) < day_start:
                    continue
            except (TypeError, ValueError):
                continue
            pnl_today += float(row.get("pnl") or 0.0)
        limit = float(equity) * float(style["daily_stop"]) if equity else None
        loss_used = max(0.0, -pnl_today)
        styles_budget[name] = {
            "daily_stop": style["daily_stop"],
            "pnl_today": round(pnl_today, 2),
            "loss_used_usd": round(loss_used, 2),
            "open_risk_usd": round(open_risk, 2),
            "limit_usd": round(limit, 2) if limit is not None else None,
            "remaining_usd": (
                round(max(0.0, limit - loss_used), 2)
                if limit is not None else None
            ),
            "stop_hit": bool(limit is not None and pnl_today <= -limit + 1e-9),
        }
    total_pnl = 0.0
    total_open = 0.0
    for row in all_rows:
        if row["status"] == "open":
            total_open += float(row.get("risk_usd") or 0.0)
            continue
        if row["status"] != "closed":
            continue
        stamp = row.get("exit_ts") or row.get("ts")
        try:
            if pd.Timestamp(stamp) < day_start:
                continue
        except (TypeError, ValueError):
            continue
        total_pnl += float(row.get("pnl") or 0.0)
    global_limit = (
        float(equity) * float(cfg["global"]["daily_stop"]) if equity else None
    )
    total_loss = max(0.0, -total_pnl)
    global_budget = {
        "daily_stop": cfg["global"]["daily_stop"],
        "pnl_today": round(total_pnl, 2),
        "loss_used_usd": round(total_loss, 2),
        "open_risk_usd": round(total_open, 2),
        "limit_usd": round(global_limit, 2) if global_limit is not None else None,
        "remaining_usd": (
            round(max(0.0, global_limit - total_loss), 2)
            if global_limit is not None else None
        ),
        "stop_hit": bool(
            global_limit is not None and total_pnl <= -global_limit + 1e-9
        ),
    }
    open_by_style: dict[str, list] = {}
    for row in opened:
        open_by_style.setdefault(row.get("style") or "Sin datos", []).append(row)
    try:
        from .accounts import load_accounts

        account_cfg = load_accounts().get(cfg["account"])
        account_stop = (
            account_cfg.account_daily_stop if account_cfg is not None else None
        )
    except Exception:
        account_stop = None
    ai_pnl = sum(
        float(item.get("pnl_today") or 0.0)
        for item in styles_budget.values()
    )
    account_block = {
        "daily_stop": account_stop,
        "source": (account_risk or {}).get("source"),
        "used_pct": (account_risk or {}).get("daily_used_pct"),
        "limit_usd": (account_risk or {}).get("effective_daily_limit"),
        "remaining_usd": (account_risk or {}).get("remaining_usd"),
        "stop_hit": bool(
            (account_risk or {}).get("severity") == "breach"
            or (account_risk or {}).get("allowed") is False
        ),
        "ai_pnl_today": round(ai_pnl, 2),
        "ai_loss_used_usd": round(max(0.0, -ai_pnl), 2),
        "lanes": {
            name: round(float(item.get("pnl_today") or 0.0), 2)
            for name, item in styles_budget.items()
        },
    }
    if account_risk and account_risk.get("daily_used_pct") is not None:
        total_loss = float(account_risk.get("effective_daily_limit") or 0.0) * float(
            account_risk.get("daily_used_pct") or 0.0
        )
        account_block["total_loss_used_usd"] = round(total_loss, 2)
        account_block["forward_otros_loss_used_usd"] = round(
            max(0.0, total_loss - max(0.0, -ai_pnl)), 2
        )
    return {
        "generated_at": utcnow(),
        "equity": round(float(equity), 2) if equity else None,
        "open": opened,
        "open_by_style": open_by_style,
        "closed": {
            "n": len(closed),
            "avg_r": round(sum(real) / len(real), 4) if real else None,
            "shadow_avg_r": round(sum(shadow) / len(shadow), 4) if shadow else None,
            "noplan_avg_r": round(sum(noplan) / len(noplan), 4) if noplan else None,
        },
        "budget": {
            "equity": round(float(equity), 2) if equity else None,
            "styles": styles_budget,
            "global": global_budget,
        },
        "account_daily": account_block,
        "cells": _summarize_cells(items, db_path),
        "plans": _active_plans(db_path, _reset_date(settings)),
        "decisions": decisions,
        "lessons": lessons,
        "paused": cells,
        "distill": _distill_panel(db_path),
        "n": len(all_rows),
    }


def session_activity(db_path: str | Path = DEFAULT_DB, *,
                     settings: Settings | None = None,
                     now: datetime | None = None) -> dict:
    """Filas de ai_decisions por sesión y estado de las tareas programadas."""
    moment = _as_utc(now)
    settings = settings or get_settings()
    session_date = _reset_date(settings)
    init_db(db_path)
    with connect(db_path) as con:
        def count(session: str | None = None, style: str | None = None) -> int:
            sql = (
                "SELECT COUNT(*) AS n FROM ai_decisions "
                "WHERE decision_date=? AND source='forward'"
            )
            params: list = [session_date]
            if session:
                sql += " AND session=?"
                params.append(session)
            if style:
                sql += " AND style=?"
                params.append(style)
            return int(con.execute(sql, params).fetchone()["n"])

        london = count("Londres") > 0
        ny = count("Nueva York") > 0
        daily = count(style="swing") > 0

    decision_warnings: list[str] = []
    task_warnings: list[str] = []
    if moment.weekday() < 5:
        if moment.hour >= 13 and not london:
            decision_warnings.append("Londres sin filas en ai_decisions")
        if moment.hour >= 21 and not ny:
            decision_warnings.append("Nueva York sin filas en ai_decisions")
        if moment.hour >= 21 and not daily:
            decision_warnings.append("swing/daily sin filas en ai_decisions")

    status_dir = ROOT / "logs" / "ai_trader" / "status"
    santo = moment.astimezone(ZoneInfo("America/Santo_Domingo"))
    date_key = santo.date().isoformat()

    def statuses(session: str) -> list[dict]:
        if not status_dir.exists():
            return []
        out: list[dict] = []
        for path in status_dir.glob(f"{date_key}_{session}_*.json"):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8-sig")))
            except Exception:
                continue
        return out

    def latest(items: list[dict]) -> dict | None:
        valid = [item for item in items if item.get("ts")]
        if not valid:
            return None
        return max(valid, key=lambda item: str(item.get("ts")))

    tasks: dict[str, dict] = {}
    london_local = moment.astimezone(LONDON)
    ny_local = moment.astimezone(NEW_YORK)
    if london_local.weekday() < 5 and london_local.time() >= dtime(10, 0):
        items = statuses("london")
        ok = any(item.get("status") == "ok" for item in items)
        tasks["london"] = {"ok": ok, "runs": len(items)}
        if not ok:
            task_warnings.append("London no corrió o falló")
    if ny_local.weekday() < 5 and ny_local.time() >= dtime(10, 0):
        items = statuses("ny")
        ok = any(item.get("status") == "ok" for item in items)
        tasks["ny"] = {"ok": ok, "runs": len(items)}
        if not ok:
            task_warnings.append("NY no corrió o falló")
    if ny_local.weekday() < 5 and ny_local.time() >= dtime(23, 0):
        items = statuses("daily")
        ok = any(item.get("status") == "ok" for item in items)
        tasks["daily"] = {"ok": ok, "runs": len(items)}
        if not ok:
            task_warnings.append("Daily no corrió o falló")

    from .ai_session import session_window

    scalp_open, _ = session_window("scalp", moment)
    scalp_items = statuses("scalp")
    scalp_latest = latest(scalp_items)
    if scalp_open:
        fresh = False
        if scalp_latest:
            try:
                fresh = (
                    pd.Timestamp(moment) - pd.Timestamp(str(scalp_latest.get("ts")))
                ).total_seconds() <= 300
            except Exception:
                fresh = False
        tasks["scalp"] = {
            "ok": bool(scalp_latest and scalp_latest.get("status") == "ok" and fresh),
            "runs": len(scalp_items),
        }
        if not tasks["scalp"]["ok"]:
            task_warnings.append("Scalp sin ejecución reciente")
    elif ny_local.weekday() < 5 and ny_local.time() >= dtime(12, 5):
        ok = any(item.get("status") == "ok" for item in scalp_items)
        tasks["scalp"] = {"ok": ok, "runs": len(scalp_items)}
        if not ok:
            task_warnings.append("Scalp no corrió hoy")

    manage_open, _ = session_window("manage", moment)
    manage_items = statuses("manage")
    manage_latest = latest(manage_items)
    if manage_open:
        fresh = False
        if manage_latest:
            try:
                fresh = (
                    pd.Timestamp(moment) - pd.Timestamp(str(manage_latest.get("ts")))
                ).total_seconds() <= 1800
            except Exception:
                fresh = False
        tasks["manage"] = {
            "ok": bool(manage_latest and manage_latest.get("status") == "ok" and fresh),
            "runs": len(manage_items),
        }
        if not tasks["manage"]["ok"]:
            task_warnings.append("Manage sin ejecución reciente")

    detail = (
        f"Londres={'ok' if london else 'sin filas'} · "
        f"NY={'ok' if ny else 'sin filas'} · "
        f"daily={'ok' if daily else 'sin filas'} · "
        f"tareas={len(tasks)}"
    )
    warnings = decision_warnings + task_warnings
    return {
        "session_date": session_date,
        "london": london,
        "ny": ny,
        "daily": daily,
        "tasks": tasks,
        "decision_warnings": decision_warnings,
        "task_warnings": task_warnings,
        "warnings": warnings,
        "detail": detail,
    }


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
