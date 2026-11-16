"""Puente forward intradía para los dos candidatos fijos de forex.

Este módulo es deliberadamente independiente del orquestador diario: no activa
bots, no usa ``bots.yaml`` y no envía nada si falta cualquier guarda. Su modo
por defecto es dry-run; la ejecución real exige ``enabled: true`` en
``config/intraday_forward.yaml`` y el comando explícito con confirmación.

Reglas duras:
- Solo demo, identidad verificada y cuenta ``ftmo_demo``.
- Volumen mínimo del símbolo, nunca más.
- Una entrada por bot y día UTC.
- Stop ATR en el bróker y cierre por señal, ``max_hold`` o corte de sesión.
- Nunca se cierra una posición que no lleve el ``magic`` del bot.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

from .accounts import (
    AccountDefinition,
    effective_limits,
    load_accounts,
    rules_for_account,
)
from .alerts import send as send_alert
from .asset_aliases import symbol_allowed
from .clock import STATUS_FALLA as CLOCK_FALLA
from .clock import check_clock
from .config import DEFAULT_DB, ROOT, Settings
from .db import connect, init_db, utcnow
from .freshness import STATUS_FALLA as FRESHNESS_FALLA
from .freshness import check as check_freshness
from .indicators import atr
from .intel.calendar import calendar_block_for_settings
from .intraday import STRATEGIES as INTRADAY_STRATEGIES
from .killswitch import ensure as ensure_killswitch
from .profiles import BotProfile, get_profile
from .prop.defense import DailyCircuitBreaker, TrailingDrawdown
from .prop.guard import AccountSnapshot, PropGuard, evaluate_account
from .risk_budget import assess_open, news_blackout
from .session import flatten_required, session_block

CONFIG_PATH = ROOT / "config" / "intraday_forward.yaml"
DEFAULT_BARS = 5_000
MIN_BARS = 210
DEFAULT_CLOSE_ATTEMPTS = 3
DEFAULT_CLOSE_RETRY_S = 0.5
FORWARD_BOT_PREFIX = "forward:"
TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


class ForwardError(RuntimeError):
    """El forward no puede evaluar o una guarda falló."""


@dataclass(frozen=True)
class ForwardBot:
    id: str
    canonical_symbol: str
    strategy: str
    timeframe: str
    account: str
    params: dict
    entry_start: dt_time
    entry_end: dt_time
    force_exit: dt_time | None
    stop_atr: float
    max_trades_per_day: int
    magic: int
    enabled: bool
    notes: str = ""
    # off | report | enforce. `report` calcula y publica en guards sin bloquear.
    defense_mode: str = "report"
    # Swing: sin corte diario, puede dormir fuera del día; 1 entrada por señal.
    swing: bool = False
    # Fracción del volumen mínimo objetivo (0-1). El mínimo manda siempre.
    exposure: float = 1.0

    @property
    def signal_bot(self) -> str:
        return f"{FORWARD_BOT_PREFIX}{self.id}"


@dataclass
class ForwardDecision:
    bot: str
    symbol: str
    signal: float
    action: str
    reason: str
    price: float | None = None
    atr: float | None = None
    stop: float | None = None
    volume: float | None = None
    position_ticket: int | None = None
    dry_run: bool = True
    order: dict | None = None
    guards: dict = field(default_factory=dict)


def _parse_hhmm(value: str) -> dt_time:
    try:
        hour, minute = str(value).strip().split(":")
        return dt_time(int(hour), int(minute), tzinfo=timezone.utc)
    except Exception as exc:
        raise ForwardError(f"hora inválida: {value!r}") from exc


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_forward_bots(path: str | Path | None = None) -> list[ForwardBot]:
    """Carga los candidatos congelados; falla si algo no es explícito."""
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        raise ForwardError(f"falta la configuración forward: {target}")
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ForwardError("configuración forward inválida")
    account = str(raw.get("account") or "").strip()
    if account != "ftmo_demo":
        raise ForwardError("el forward solo permite account=ftmo_demo")
    defense_mode = str(raw.get("defense") or "report").strip().lower()
    if defense_mode not in {"off", "report", "enforce"}:
        raise ForwardError("defense debe ser off, report o enforce")
    items = raw.get("bots") or []
    if not isinstance(items, list) or not items:
        raise ForwardError("el forward no tiene bots configurados")

    out: list[ForwardBot] = []
    ids: set[str] = set()
    magics: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ForwardError("bot forward inválido")
        bot_id = str(item.get("id") or "").strip()
        if not bot_id or bot_id in ids:
            raise ForwardError(f"id forward vacío o duplicado: {bot_id!r}")
        ids.add(bot_id)
        strategy = str(item.get("strategy") or "").strip()
        if strategy not in INTRADAY_STRATEGIES:
            raise ForwardError(f"{bot_id}: estrategia intradía desconocida {strategy!r}")
        timeframe = str(item.get("timeframe") or "M15").strip().upper()
        if timeframe not in TIMEFRAME_MINUTES:
            raise ForwardError(f"{bot_id}: timeframe desconocido {timeframe!r}")
        bot_account = str(item.get("account") or account).strip()
        if bot_account != "ftmo_demo":
            raise ForwardError(f"{bot_id}: solo se permite ftmo_demo")
        params = item.get("params") or {}
        if not isinstance(params, dict) or not params:
            raise ForwardError(f"{bot_id}: params vacíos")
        entry_start = _parse_hhmm(str(item.get("entry_start") or ""))
        entry_end = _parse_hhmm(str(item.get("entry_end") or ""))
        raw_force_exit = item.get("force_exit")
        force_exit = (
            _parse_hhmm(str(raw_force_exit))
            if raw_force_exit not in (None, "", "none")
            else None
        )
        swing = bool(item.get("swing", force_exit is None))
        if swing and force_exit is not None:
            raise ForwardError(f"{bot_id}: swing no admite force_exit")
        if not swing and force_exit is None:
            raise ForwardError(f"{bot_id}: falta force_exit (o marca swing: true)")
        if not (entry_start < entry_end):
            raise ForwardError(f"{bot_id}: entry_start debe ser anterior a entry_end")
        if force_exit is not None and force_exit < entry_end:
            raise ForwardError(f"{bot_id}: force_exit no puede ser anterior a entry_end")
        exposure = float(item.get("exposure") or 1.0)
        if not 0 < exposure <= 1:
            raise ForwardError(f"{bot_id}: exposure debe estar en (0, 1]")
        stop_atr = float(item.get("stop_atr") or 0.0)
        if stop_atr <= 0:
            raise ForwardError(f"{bot_id}: stop_atr debe ser > 0")
        max_trades = int(item.get("max_trades_per_day") or 0)
        if max_trades < 1 or max_trades > 2:
            raise ForwardError(f"{bot_id}: max_trades_per_day debe estar entre 1 y 2")
        magic = int(item.get("magic") or 0)
        if magic <= 0 or magic in magics:
            raise ForwardError(f"{bot_id}: magic inválido o duplicado")
        magics.add(magic)
        enabled = item.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ForwardError(f"{bot_id}: enabled debe ser true o false")
        out.append(
            ForwardBot(
                id=bot_id,
                canonical_symbol=str(item.get("canonical_symbol") or "").strip().upper(),
                strategy=strategy,
                timeframe=timeframe,
                account=bot_account,
                params=dict(params),
                entry_start=entry_start,
                entry_end=entry_end,
                force_exit=force_exit,
                stop_atr=stop_atr,
                max_trades_per_day=max_trades,
                magic=magic,
                enabled=enabled,
                notes=str(item.get("notes") or ""),
                defense_mode=defense_mode,
                swing=swing,
                exposure=exposure,
            )
        )
        if not out[-1].canonical_symbol:
            raise ForwardError(f"{bot_id}: canonical_symbol vacío")
    return out


def get_forward_bot(bot_id: str, path: str | Path | None = None) -> ForwardBot | None:
    return next((bot for bot in load_forward_bots(path) if bot.id == bot_id), None)


def _require_health_true(health: dict, key: str, message: str) -> None:
    if health.get(key) is not True:
        raise ForwardError(message)


def _health_guard(broker) -> dict:
    try:
        health = broker.health()
    except Exception as exc:
        raise ForwardError(f"health del bróker no disponible: {exc}") from exc
    if not isinstance(health, dict):
        raise ForwardError("health del bróker inválido")
    if health.get("mode") != "demo":
        raise ForwardError(
            f"cuenta no demo: mode={health.get('mode')!r}; no se envía nada"
        )
    _require_health_true(health, "identity_ok", "identity_ok != True; no se envía nada")
    _require_health_true(health, "connected", "connected != True; no se envía nada")
    _require_health_true(
        health, "trade_allowed", "trade_allowed != True; no se envía nada"
    )
    _require_health_true(
        health, "require_demo", "require_demo != True; no se envía nada"
    )
    expected_login = health.get("expected_login")
    if expected_login is None or health.get("login") != expected_login:
        raise ForwardError("login MT5 no coincide con el esperado; no se envía nada")
    expected_server = health.get("expected_server")
    if not expected_server or health.get("server") != expected_server:
        raise ForwardError("servidor MT5 no coincide con el esperado; no se envía nada")
    return health


def _account_for(bot: ForwardBot) -> AccountDefinition:
    account = load_accounts().get(bot.account)
    if account is None:
        raise ForwardError(f"cuenta desconocida: {bot.account}")
    if account.id != "ftmo_demo":
        raise ForwardError(f"{bot.id}: solo se permite la cuenta ftmo_demo")
    if account.platform != "mt5":
        raise ForwardError(f"{bot.id}: la cuenta ftmo_demo debe ser MT5")
    if account.status != "demo":
        raise ForwardError(f"{bot.id}: la cuenta ftmo_demo debe estar en demo")
    return account


def _broker_symbol(db_path: str | Path, canonical: str) -> str:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT broker_symbol FROM asset_aliases "
            "WHERE canonical = ? AND profile = 'intraday_fx'",
            (canonical.upper(),),
        ).fetchone()
        if row is None:
            # El forward puede declarar el símbolo del bróker como canónico
            # (p. ej. US100.CASH); el alias lo conoce por su forma real.
            row = con.execute(
                "SELECT broker_symbol FROM asset_aliases "
                "WHERE UPPER(broker_symbol) = ? AND profile = 'intraday_fx'",
                (canonical.upper(),),
            ).fetchone()
    if row is None:
        raise ForwardError(
            f"{canonical}: falta alias del bróker; ejecuta `lab mt5 aliases`"
        )
    symbol = str(row["broker_symbol"]).strip()
    allowed, reason = symbol_allowed(db_path, symbol)
    if not allowed:
        raise ForwardError(reason or f"{symbol}: símbolo no permitido")
    return symbol


def _load_bars(
    broker,
    symbol: str,
    timeframe: str,
    *,
    count: int,
    now: datetime,
) -> tuple[pd.DataFrame, datetime]:
    try:
        frame = broker.rates(symbol, timeframe, count)
    except Exception as exc:
        raise ForwardError(f"{symbol}: no se pudieron leer velas: {exc}") from exc
    if frame is None or frame.empty:
        raise ForwardError(f"{symbol}: sin velas {timeframe}")
    required = {"open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ForwardError(f"{symbol}: velas sin columnas {sorted(required)}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ForwardError(f"{symbol}: índice de velas sin fecha")
    df = frame.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()

    minutes = TIMEFRAME_MINUTES[timeframe]
    close_times = df.index + pd.Timedelta(minutes=minutes)
    df = df.loc[close_times <= pd.Timestamp(now)]
    if len(df) < MIN_BARS:
        raise ForwardError(
            f"{symbol}: histórico insuficiente ({len(df)} velas cerradas; "
            f"mínimo {MIN_BARS})"
        )
    last_close = (df.index[-1] + pd.Timedelta(minutes=minutes)).to_pydatetime()
    return df, last_close


def _atr_value(df: pd.DataFrame) -> float:
    try:
        value = float(atr(df).iloc[-1])
    except Exception as exc:
        raise ForwardError(f"ATR no disponible: {exc}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ForwardError("ATR inválido")
    return value


def _strategy_signal(
    df: pd.DataFrame,
    bot: ForwardBot,
    strategy_fn: Callable | None = None,
) -> float:
    fn = strategy_fn or INTRADAY_STRATEGIES.get(bot.strategy)
    if fn is None:
        raise ForwardError(f"{bot.id}: estrategia no implementada")
    try:
        result = fn(df, **bot.params)
        target = result.target.reindex(df.index).fillna(0.0)
        signal = float(target.iloc[-1])
    except Exception as exc:
        raise ForwardError(f"{bot.id}: no se pudo calcular la señal: {exc}") from exc
    if signal > 0:
        return 1.0
    if signal < 0:
        return -1.0
    return 0.0


def _positions(broker, symbol: str) -> list[dict]:
    try:
        positions = broker.positions(symbol=symbol)
    except Exception as exc:
        raise ForwardError(f"{symbol}: no se pudieron leer posiciones: {exc}") from exc
    return [dict(item) for item in (positions or [])]


def _split_positions(
    positions: list[dict], symbol: str, magic: int
) -> tuple[list[dict], list[dict]]:
    ours: list[dict] = []
    foreign: list[dict] = []
    for position in positions:
        if str(position.get("symbol") or "").upper() != symbol.upper():
            continue
        if int(position.get("magic") or 0) == int(magic):
            ours.append(position)
        else:
            foreign.append(position)
    return ours, foreign


def _today_trade_count(
    db_path: str | Path,
    bot_id: str | None = None,
    *,
    now: datetime,
) -> int:
    moment = _as_utc(now)
    start = moment.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    init_db(db_path)
    try:
        with connect(db_path) as con:
            if bot_id:
                orders = con.execute(
                    "SELECT COUNT(*) AS n FROM orders "
                    "WHERE bot = ? AND ts >= ? AND side IN ('buy','sell') "
                    "AND status = 'filled'",
                    (f"{FORWARD_BOT_PREFIX}{bot_id}", start),
                ).fetchone()
                signals = con.execute(
                    "SELECT COUNT(*) AS n FROM signals "
                    "WHERE bot = ? AND ts >= ? AND side IN ('buy','sell') "
                    "AND reason LIKE '%executed%'",
                    (f"{FORWARD_BOT_PREFIX}{bot_id}", start),
                ).fetchone()
            else:
                orders = con.execute(
                    "SELECT COUNT(*) AS n FROM orders "
                    "WHERE bot LIKE ? AND ts >= ? AND side IN ('buy','sell') "
                    "AND status = 'filled'",
                    (f"{FORWARD_BOT_PREFIX}%", start),
                ).fetchone()
                signals = con.execute(
                    "SELECT COUNT(*) AS n FROM signals "
                    "WHERE bot LIKE ? AND ts >= ? AND side IN ('buy','sell') "
                    "AND reason LIKE '%executed%'",
                    (f"{FORWARD_BOT_PREFIX}%", start),
                ).fetchone()
    except Exception as exc:
        raise ForwardError(f"no se pudo contar trades del día: {exc}") from exc
    return max(int(orders["n"]), int(signals["n"]))


def _record_signal(
    db_path: str | Path,
    bot: ForwardBot,
    symbol: str,
    signal: float,
    price: float | None,
    reason: str,
) -> None:
    side = "buy" if signal > 0 else "sell" if signal < 0 else "flat"
    init_db(db_path)
    try:
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    symbol,
                    bot.signal_bot,
                    side,
                    signal,
                    price,
                    str(reason)[:500],
                ),
            )
    except Exception as exc:
        raise ForwardError(f"{bot.id}: no se pudo registrar la señal: {exc}") from exc


def _last_signal(db_path: str | Path, bot_name: str) -> float | None:
    """Última señal que el bot llegó a operar (o 0 si quedó plano)."""
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT last_signal FROM forward_state WHERE bot = ?",
            (bot_name,),
        ).fetchone()
    return float(row["last_signal"]) if row is not None else None


def _set_last_signal(db_path: str | Path, bot_name: str, signal: float) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO forward_state(bot, last_signal, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(bot) DO UPDATE SET "
            "last_signal = excluded.last_signal, updated_at = excluded.updated_at",
            (bot_name, float(signal), utcnow()),
        )


def _exposure_volume(spec: dict, exposure: float) -> float:
    """Volumen objetivo = mínimo × exposición, redondeado al step.

    Si el mínimo ya es el 100 % del tamaño disponible (0,75 × mínimo cae por
    debajo del mínimo), se usa el mínimo y se documenta en la nota del bot.
    """
    minimum = _min_volume(spec)
    step = float(spec.get("volume_step") or 0.0) or minimum
    if not 0 < exposure <= 1:
        raise ForwardError(f"exposición inválida: {exposure}")
    steps = math.floor((minimum * exposure) / step + 1e-9)
    volume = max(minimum, round(steps * step, 8))
    return volume


def _symbol_spec(broker, symbol: str) -> dict:
    try:
        spec = broker.symbol_spec(symbol)
    except Exception as exc:
        raise ForwardError(f"{symbol}: especificación no disponible: {exc}") from exc
    if not isinstance(spec, dict):
        raise ForwardError(f"{symbol}: especificación inválida")
    return spec


def _tick(broker, symbol: str) -> dict:
    try:
        tick = broker.tick(symbol)
    except Exception as exc:
        raise ForwardError(f"{symbol}: tick no disponible: {exc}") from exc
    if not isinstance(tick, dict):
        raise ForwardError(f"{symbol}: tick inválido")
    if float(tick.get("bid") or 0.0) <= 0 or float(tick.get("ask") or 0.0) <= 0:
        raise ForwardError(f"{symbol}: bid/ask inválidos")
    return tick


def _instrument(broker, symbol: str):
    try:
        return broker.instrument(symbol)
    except Exception as exc:
        raise ForwardError(f"{symbol}: instrumento no disponible: {exc}") from exc


def _quote_rate(broker, instrument) -> float:
    quote = str(getattr(instrument, "quote_ccy", "USD") or "USD").upper()
    if quote == "USD":
        return 1.0
    try:
        symbol = str(getattr(instrument, "symbol", "") or "").upper()
        if symbol.startswith("USD"):
            return float(broker.tick(symbol)["bid"])
        if quote in {"JPY", "CHF", "CAD"}:
            return float(broker.tick(f"USD{quote}")["bid"])
        return 1.0 / float(broker.tick(f"{quote}USD")["bid"])
    except Exception as exc:
        raise ForwardError(f"no se pudo obtener el cambio {quote}/USD: {exc}") from exc


def _min_volume(spec: dict) -> float:
    volume_min = float(spec.get("volume_min") or 0.0)
    volume_step = float(spec.get("volume_step") or 0.0)
    volume_max = float(spec.get("volume_max") or 0.0)
    if volume_min <= 0 or volume_step <= 0:
        raise ForwardError("volume_min/volume_step inválidos")
    if volume_max > 0 and volume_min > volume_max:
        raise ForwardError("volume_min > volume_max")
    steps = round(volume_min / volume_step)
    if steps < 1 or not math.isclose(
        steps * volume_step, volume_min, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise ForwardError(
            f"volume_min {volume_min:g} no es múltiplo de step {volume_step:g}"
        )
    return volume_min


def _stop_distance(bot: ForwardBot, spec: dict, atr_value: float) -> float:
    distance = float(bot.stop_atr) * float(atr_value)
    minimum = float(spec.get("stops_level") or 0.0) * float(spec.get("point") or 0.0)
    if distance <= 0:
        raise ForwardError("distancia de stop inválida")
    if minimum > 0 and distance < minimum:
        raise ForwardError(
            f"stop {distance:.6f} menor que el mínimo del bróker {minimum:.6f}"
        )
    return distance


def _round_price(value: float, digits: int) -> float:
    return round(float(value), int(digits))


def _force_exit_at(bot: ForwardBot, position_time: datetime | None, now: datetime) -> datetime | None:
    if bot.force_exit is None:
        return None
    base = _as_utc(position_time or now)
    return datetime.combine(base.date(), bot.force_exit, tzinfo=timezone.utc)


def _past_force_exit(bot: ForwardBot, position: dict, now: datetime) -> bool:
    target = _force_exit_at(bot, position.get("time"), now)
    return target is not None and _as_utc(now) >= target


def _bars_held(
    position_time: datetime | None,
    last_bar_open: pd.Timestamp,
    timeframe: str,
) -> int | None:
    if position_time is None:
        return None
    started = _as_utc(position_time)
    current = _as_utc(last_bar_open.to_pydatetime())
    minutes = TIMEFRAME_MINUTES[timeframe]
    return max(0, int((current - started).total_seconds() // (minutes * 60)))


def _held_too_long(
    bot: ForwardBot, position: dict, last_bar_open: pd.Timestamp
) -> bool:
    bars = _bars_held(position.get("time"), last_bar_open, bot.timeframe)
    max_hold = bot.params.get("max_hold")
    return bars is not None and max_hold is not None and bars >= int(max_hold)


def _bar_in_entry_window(
    bot: ForwardBot, last_bar_open: pd.Timestamp, now: datetime
) -> bool:
    moment = _as_utc(now)
    if moment.weekday() > 4:
        return False
    bar = _as_utc(last_bar_open.to_pydatetime())
    if bar.weekday() > 4:
        return False
    bar_time = bar.time().replace(tzinfo=timezone.utc)
    return bot.entry_start <= bar_time < bot.entry_end


def _stale(last_close: datetime, now: datetime, timeframe: str) -> bool:
    max_age = timedelta(minutes=2 * TIMEFRAME_MINUTES[timeframe])
    return _as_utc(now) - _as_utc(last_close) > max_age


def _alert_stale(
    db_path: str | Path,
    bot: ForwardBot,
    symbol: str,
    now: datetime,
    reason: str,
) -> None:
    try:
        from .alerts import send_once

        event = (
            f"stale_data:{_as_utc(now).date().isoformat()}:"
            f"{bot.id}:{str(symbol).upper()}"
        )
        send_once(
            event,
            f"{bot.id} {symbol}: {reason}",
            severity="warning",
            db_path=db_path,
        )
    except Exception:
        pass



def _equity_series(broker):
    try:
        series = broker.equity_series()
    except Exception as exc:
        raise ForwardError(f"equity no disponible: {exc}") from exc
    if series is None or len(series) == 0:
        raise ForwardError("equity vacío: no se puede evaluar el guard")
    return series


def _open_risk_usd(positions: list[dict], broker) -> float:
    total = 0.0
    for position in positions:
        symbol = str(position.get("symbol") or "")
        try:
            instrument = _instrument(broker, symbol)
            volume = abs(float(position.get("volume") or 0.0))
            entry = float(position.get("price_open") or 0.0)
            stop = float(position.get("sl") or 0.0)
            if volume <= 0:
                continue
            if stop > 0 and entry > 0:
                rate = _quote_rate(broker, instrument)
                total += volume * float(
                    instrument.risk_per_lot(abs(entry - stop), quote_rate=rate)
                )
            else:
                price = float(position.get("price_current") or entry or 0.0)
                if price <= 0 or instrument.contract_size <= 0:
                    raise ForwardError(
                        f"{symbol}: posición sin precio para estimar riesgo"
                    )
                quote = str(instrument.quote_ccy or "USD").upper()
                rate = 1.0 if quote == "USD" else _quote_rate(broker, instrument)
                notional = volume * instrument.contract_size * price / rate
                total += notional * 0.02
        except ForwardError:
            raise
        except Exception as exc:
            raise ForwardError(
                f"{symbol or '?'}: no se pudo estimar el riesgo abierto: {exc}"
            ) from exc
    return total


def _position_is_open(
    broker, symbol: str, ticket: int, *, magic: int | None = None
) -> bool:
    try:
        return any(
            int(position.get("ticket") or 0) == int(ticket)
            and (
                magic is None
                or int(position.get("magic") or 0) == int(magic)
            )
            for position in _positions(broker, symbol)
        )
    except Exception:
        return True


def _close_with_retries(
    broker,
    symbol: str,
    ticket: int,
    volume: float,
    *,
    magic: int,
    sleep: Callable[[float], None],
    attempts: int = DEFAULT_CLOSE_ATTEMPTS,
    retry_s: float = DEFAULT_CLOSE_RETRY_S,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        current = _positions(broker, symbol)
        match = next(
            (item for item in current if int(item.get("ticket") or 0) == int(ticket)),
            None,
        )
        if match is None:
            return {"ok": True, "already_closed": True, "ticket": ticket}
        _health_guard(broker)
        if str(match.get("symbol") or "").upper() != symbol.upper():
            raise ForwardError(
                f"{symbol}: la posición {ticket} cambió de símbolo; no se cierra"
            )
        if int(match.get("magic") or 0) != int(magic):
            raise ForwardError(
                f"{symbol}: la posición {ticket} ya no lleva el magic del bot; "
                "no se cierra"
            )
        try:
            return broker.close_position(
                int(ticket), volume=float(match.get("volume") or volume)
            )
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                sleep(retry_s)
    if _position_is_open(broker, symbol, ticket, magic=magic):
        message = (
            f"Posición huérfana en {symbol} ticket={ticket} tras {attempts} "
            f"intentos de cierre: {last_error}"
        )
        try:
            send_alert("intraday_forward_orphan", message, severity="error")
        except Exception:
            pass
        raise ForwardError(message)
    return {"ok": True, "already_closed": True, "ticket": ticket}


def _defense_guard(
    bot: ForwardBot,
    state,
    equity: float,
    now: datetime,
    rules,
) -> dict:
    """Evalúa HWM y circuit breaker; en modo `report` no bloquea."""
    if bot.defense_mode == "off":
        return {
            "allowed": True,
            "label": "off",
            "reason": "",
            "level": "off",
            "size_factor": 1.0,
            "drawdown_pct": 0.0,
            "utilization": 0.0,
            "breaker_tripped": False,
        }

    max_dd = rules.effective_max_loss_usd / rules.account_size
    max_daily = rules.effective_daily_limit_usd / rules.account_size
    peak = float(state.peak_equity or equity)
    try:
        drawdown = TrailingDrawdown(max_dd, start_equity=peak)
        dd_report = drawdown.observe(equity)
        breaker = DailyCircuitBreaker(
            max_daily_loss_pct=max_daily,
            day_start_equity=state.day_start_equity or equity,
            tz=rules.reset_tz,
        )
        breaker_report = breaker.observe(equity, now)
    except Exception as exc:
        return {
            "allowed": False,
            "label": f"error: {exc}",
            "reason": f"defensa no disponible: {exc}",
            "level": "error",
            "size_factor": 0.0,
            "drawdown_pct": 0.0,
            "utilization": 0.0,
            "breaker_tripped": False,
        }

    if not dd_report.allowed:
        reason = dd_report.reason
    elif breaker_report.tripped:
        reason = f"circuit breaker: {breaker_report.reason}"
    elif dd_report.size_factor < 1.0:
        reason = (
            f"zona {dd_report.level}: factor {dd_report.size_factor:g}x "
            "no operable con volumen mínimo"
        )
    else:
        reason = "ok"

    allowed = reason == "ok"
    label = f"{dd_report.level} {dd_report.size_factor:g}x"
    if not allowed:
        label += " (bloquea)"
    if bot.defense_mode == "report":
        label = f"report:{label}"
    return {
        "allowed": allowed,
        "label": label,
        "reason": reason,
        "level": dd_report.level,
        "size_factor": dd_report.size_factor,
        "drawdown_pct": dd_report.drawdown_pct,
        "utilization": dd_report.utilization,
        "breaker_tripped": breaker_report.tripped,
    }


def _blocked(
    bot: ForwardBot,
    symbol: str,
    signal: float,
    reason: str,
    *,
    price: float | None,
    atr_value: float,
    guards: dict,
) -> ForwardDecision:
    return ForwardDecision(
        bot=bot.id,
        symbol=symbol,
        signal=signal,
        action="bloqueado",
        reason=reason,
        price=price,
        atr=atr_value,
        dry_run=True,
        guards=guards,
    )


def _manage_position(
    bot: ForwardBot,
    broker,
    symbol: str,
    position: dict,
    signal: float,
    now: datetime,
    rules,
    atr_value: float,
    last_bar_open: pd.Timestamp,
    dry_run: bool,
    db_path: str | Path,
    sleep: Callable[[float], None],
    guards: dict,
) -> ForwardDecision:
    ticket = int(position.get("ticket") or 0)
    side = str(position.get("side") or "").lower()
    volume = float(position.get("volume") or 0.0)
    if ticket <= 0 or side not in {"buy", "sell"} or volume <= 0:
        raise ForwardError(f"{bot.id}: posición propia inválida: {position}")
    if int(position.get("magic") or 0) != int(bot.magic):
        raise ForwardError(f"{bot.id}: la posición {ticket} no lleva el magic del bot")
    if str(position.get("symbol") or "").upper() != symbol.upper():
        raise ForwardError(f"{bot.id}: la posición {ticket} no es del símbolo {symbol}")

    reason: str | None = None
    if float(position.get("sl") or 0.0) <= 0:
        reason = "stop ausente"
    elif (side == "buy" and signal < 0) or (side == "sell" and signal > 0):
        reason = "señal contraria"
    elif not bot.swing and signal == 0:
        reason = "señal plana"
    elif not bot.swing and _past_force_exit(bot, position, now):
        reason = "corte de sesión"
    elif not bot.swing and _held_too_long(bot, position, last_bar_open):
        reason = "max_hold"
    elif not bot.swing and flatten_required(rules, now, asset_class="forex"):
        reason = "fin de semana"

    price = float(position.get("price_current") or 0.0) or None
    if reason is None:
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"hold ticket={ticket} side={side} volume={volume:g}",
        )
        return ForwardDecision(
            bot=bot.id,
            symbol=symbol,
            signal=signal,
            action="hold",
            reason="posición a favor; se mantiene",
            price=price,
            atr=atr_value,
            position_ticket=ticket,
            dry_run=dry_run,
            guards=guards,
        )

    if dry_run:
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"close ticket={ticket} reason={reason} dry_run",
        )
        return ForwardDecision(
            bot=bot.id,
            symbol=symbol,
            signal=signal,
            action="close",
            reason=reason,
            price=price,
            atr=atr_value,
            volume=volume,
            position_ticket=ticket,
            dry_run=True,
            guards=guards,
        )

    result = _close_with_retries(
        broker,
        symbol,
        ticket,
        volume,
        magic=bot.magic,
        sleep=sleep,
    )
    _record_signal(
        db_path,
        bot,
        symbol,
        signal,
        price,
        f"closed ticket={ticket} reason={reason}",
    )
    return ForwardDecision(
        bot=bot.id,
        symbol=symbol,
        signal=signal,
        action="closed",
        reason=reason,
        price=price,
        atr=atr_value,
        volume=volume,
        position_ticket=ticket,
        dry_run=False,
        order=result,
        guards=guards,
    )


def run_forward_bot(
    bot: ForwardBot,
    broker,
    settings: Settings,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
    db_path: str | Path = DEFAULT_DB,
    profile: BotProfile | None = None,
    account: AccountDefinition | None = None,
    limits=None,
    bars: int = DEFAULT_BARS,
    strategy_fn: Callable | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ForwardDecision:
    """Evalúa un candidato y, solo si ``dry_run=False``, envía o cierra."""
    moment = _as_utc(now)
    init_db(db_path)
    from .lease import acquire as acquire_lease

    lease = acquire_lease(
        db_path, session=f"forward:{bot.id}", now=moment,
    )
    if not lease["ok"]:
        raise ForwardError(f"{bot.id}: otro host tiene el lease: {lease['reason']}")
    health = _health_guard(broker)
    account = account or _account_for(bot)
    if account.id != bot.account:
        raise ForwardError(f"{bot.id}: cuenta {account.id} != {bot.account}")
    if profile is None:
        profile = get_profile("intraday_fx")
    if profile is None:
        raise ForwardError("falta el perfil intraday_fx")
    limits = limits or effective_limits(db_path, account)
    symbol = _broker_symbol(db_path, bot.canonical_symbol)
    df, last_close = _load_bars(
        broker, symbol, bot.timeframe, count=bars, now=moment
    )
    signal = _strategy_signal(df, bot, strategy_fn)
    atr_value = _atr_value(df)
    tick = _tick(broker, symbol)
    positions = _positions(broker, symbol)
    account_positions = broker.positions() or []
    ours, foreign = _split_positions(positions, symbol, bot.magic)
    if len(ours) > 1:
        raise ForwardError(
            f"{bot.id}: hay {len(ours)} posiciones con su magic; no se toca nada"
        )
    position = ours[0] if ours else None
    rules = rules_for_account(account)
    equity_series = _equity_series(broker)
    try:
        state = PropGuard.state_from_equity(
            rules,
            equity_series,
            initial_balance=rules.account_size,
            open_positions=len(positions),
        )
    except Exception as exc:
        raise ForwardError(f"{bot.id}: guard de cuenta no disponible: {exc}") from exc

    equity = float(health.get("equity") or state.equity or 0.0)
    if equity <= 0:
        raise ForwardError(f"{bot.id}: equity inválido")
    from .symbol_risk import (
        alert_risk_events,
        group_cap_usd,
        risk_group,
        risk_snapshot,
        symbol_cap_usd,
        total_cap_usd,
    )

    balance = float(state.day_start_balance or state.day_start_equity or equity)
    risk = risk_snapshot(
        account_positions,
        broker,
        account_id=account.id,
        account=account,
        balance=balance,
    )
    guards = {
        "health": "ok",
        "account": "ok",
        "session": "pendiente",
        "calendar": "pendiente",
        "news": "pendiente",
        "killswitch": "pendiente",
        "account_guard": "pendiente",
        "risk_budget": "pendiente",
        "defense": "pendiente",
        "freshness": "pendiente",
        "clock": "pendiente",
    }
    defense = _defense_guard(bot, state, equity, moment, rules)
    guards["defense"] = defense["label"]

    if position is not None:
        return _manage_position(
            bot=bot,
            broker=broker,
            symbol=symbol,
            position=position,
            signal=signal,
            now=moment,
            rules=rules,
            atr_value=atr_value,
            last_bar_open=df.index[-1],
            dry_run=dry_run,
            db_path=db_path,
            sleep=sleep,
            guards=guards,
        )

    price = float(tick["bid"])
    if signal == 0:
        if bot.swing:
            _set_last_signal(db_path, bot.signal_bot, 0.0)
        _record_signal(
            db_path, bot, symbol, signal, price, "flat sin posición"
        )
        return ForwardDecision(
            bot=bot.id,
            symbol=symbol,
            signal=signal,
            action="flat",
            reason="sin señal y sin posición",
            price=price,
            atr=atr_value,
            dry_run=dry_run,
            guards=guards,
        )

    if bot.swing:
        previous = _last_signal(db_path, bot.signal_bot)
        if previous is not None and abs(previous - signal) < 1e-9:
            _record_signal(
                db_path,
                bot,
                symbol,
                signal,
                price,
                "blocked repeated_signal: ya se operó esta señal",
            )
            return _blocked(
                bot,
                symbol,
                signal,
                "señal ya operada; se espera un cambio de señal",
                price=price,
                atr_value=atr_value,
                guards=guards,
            )

    # Datos frescos y reloj sano: sin esto no se abre nada. El cierre de una
    # posición ya está gestionado antes (rama `position is not None`).
    fresh = check_freshness(symbol, bot.timeframe, db_path=db_path)
    guards["freshness"] = f"{fresh['status']}: {fresh['reason']}"
    if fresh["status"] == FRESHNESS_FALLA:
        stale_reason = f"datos obsoletos: {fresh['reason']}"
        _alert_stale(db_path, bot, symbol, moment, stale_reason)
        _record_signal(
            db_path, bot, symbol, signal, price, f"skip: {stale_reason}"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"skip: {stale_reason}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )
    clock_state = check_clock()
    guards["clock"] = f"{clock_state['status']}: {clock_state['reason']}"
    if clock_state["status"] == CLOCK_FALLA:
        _record_signal(
            db_path, bot, symbol, signal, price, f"blocked clock: {clock_state['reason']}"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"reloj: {clock_state['reason']}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    if foreign:
        guards["session"] = "bloqueada"
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            "blocked foreign_position",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            "hay una posición ajena en el símbolo; no se abre",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    session = session_block(rules, moment, asset_class="forex")
    guards["session"] = "ok" if not session.blocked else session.reason
    if session.blocked:
        _record_signal(
            db_path, bot, symbol, signal, price, f"blocked session: {session.reason}"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"sesión: {session.reason}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    if not _bar_in_entry_window(bot, df.index[-1], moment):
        _record_signal(
            db_path, bot, symbol, signal, price, "blocked outside_entry_window"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            "fuera de la ventana de entrada",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )
    if _past_force_exit(bot, {"time": moment}, moment):
        _record_signal(
            db_path, bot, symbol, signal, price, "blocked past_force_exit"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            "ya pasó el corte de sesión; no se abre",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )
    if _stale(last_close, moment, bot.timeframe):
        stale_reason = f"datos obsoletos: última vela cerró {last_close.isoformat()}"
        _alert_stale(db_path, bot, symbol, moment, stale_reason)
        _record_signal(
            db_path, bot, symbol, signal, price, f"skip: {stale_reason}"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"skip: {stale_reason}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    try:
        killswitch, _ = ensure_killswitch(
            db_path,
            equity_series,
            settings.risk,
            current=equity,
            tz=settings.timezone,
            now=moment,
        )
    except Exception as exc:
        raise ForwardError(f"{bot.id}: kill-switch no disponible: {exc}") from exc
    guards["killswitch"] = "activo" if killswitch.active else "ok"
    if killswitch.active:
        _record_signal(
            db_path, bot, symbol, signal, price, f"blocked killswitch: {killswitch.reason}"
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"kill switch: {killswitch.reason}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    try:
        blackout = calendar_block_for_settings(db_path, settings, now=moment)
    except Exception as exc:
        raise ForwardError(f"{bot.id}: calendario no disponible: {exc}") from exc
    guards["calendar"] = "ok" if not blackout.blocked else blackout.reason
    if blackout.blocked:
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"blocked calendar: {blackout.reason}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"calendario: {blackout.reason}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    try:
        news = news_blackout(db_path, symbol, now=moment)
    except Exception as exc:
        raise ForwardError(f"{bot.id}: noticias no disponibles: {exc}") from exc
    if not news.get("data_ok"):
        guards["news"] = "sin datos"
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"blocked news_data: {news.get('reason')}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"noticias sin datos: {news.get('reason')}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )
    guards["news"] = "ok" if not news.get("blocked") else news.get("reason")
    if news.get("blocked"):
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"blocked news: {news.get('reason')}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"noticias: {news.get('reason')}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    bot_trades = _today_trade_count(db_path, bot.id, now=moment)
    account_trades = _today_trade_count(db_path, None, now=moment)
    max_trades = min(
        bot.max_trades_per_day,
        profile.max_trades_per_day or bot.max_trades_per_day,
        limits.max_trades_per_day or bot.max_trades_per_day,
    )
    if bot_trades >= max_trades:
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"blocked max_trades {bot_trades}/{max_trades}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"máximo de trades/día alcanzado ({bot_trades}/{max_trades})",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    if bot.defense_mode == "enforce" and not defense["allowed"]:
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            price,
            f"blocked defense: {defense['reason']}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"defensa: {defense['reason']}",
            price=price,
            atr_value=atr_value,
            guards=guards,
        )

    spec = _symbol_spec(broker, symbol)
    volume = _min_volume(spec)
    if bot.swing and bot.exposure < 1.0:
        volume = _exposure_volume(spec, bot.exposure)
    stop_distance = _stop_distance(bot, spec, atr_value)
    sign = 1 if signal > 0 else -1
    entry = float(tick["ask"] if sign > 0 else tick["bid"])
    digits = int(spec.get("digits") or 0)
    stop = _round_price(entry - sign * stop_distance, digits)
    if (sign > 0 and stop >= entry) or (sign < 0 and stop <= entry):
        raise ForwardError(f"{symbol}: stop inválido tras redondear ({stop} vs {entry})")

    instrument = _instrument(broker, symbol)
    rate = _quote_rate(broker, instrument)
    risk_per_lot = float(
        instrument.risk_per_lot(stop_distance, quote_rate=rate)
    )
    risk_usd = volume * risk_per_lot
    alert_risk_events(account.id, risk, db_path=db_path)
    if risk["ea_over"]:
        first = risk["ea_over"][0]
        reason = (
            f"skip: riesgo agregado ({first['kind']}) EA {first['name']} "
            f"{first['risk_usd']:,.2f} > {first['cap_usd']:,.2f}"
        )
        _record_signal(db_path, bot, symbol, signal, entry, reason)
        return _blocked(
            bot,
            symbol,
            signal,
            reason,
            price=entry,
            atr_value=atr_value,
            guards=guards,
        )
    group = risk_group(account, symbol)
    try:
        account_report = evaluate_account(
            rules,
            AccountSnapshot(
                equity=equity,
                day_start_equity=state.day_start_equity,
                initial_balance=rules.account_size,
                peak_equity=state.peak_equity or equity,
                realized_pnl_today=state.closed_pnl_today,
                open_positions=len(account_positions),
                open_risk_usd=risk["total_usd"],
                trades_today=account_trades,
                missing_sl=bool(risk["missing_sl"]),
            ),
            limits=limits,
            max_risk_pct=profile.max_risk_pct,
            max_trades_per_day=max_trades,
            proposed_risk_usd=risk_usd,
            symbol_open_risk_usd=risk["by_symbol"].get(symbol.upper(), 0.0),
            symbol_risk_cap_usd=symbol_cap_usd(account, symbol, balance),
            symbol=symbol,
            group_open_risk_usd=risk["by_group"].get(group, 0.0),
            group_risk_cap_usd=group_cap_usd(account, group, balance),
            group=group,
            total_open_risk_usd=risk["total_usd"],
            total_risk_cap_usd=total_cap_usd(account, balance),
        )
    except Exception as exc:
        raise ForwardError(f"{bot.id}: guard de cuenta no disponible: {exc}") from exc
    guards["account_guard"] = "ok" if account_report.allowed else account_report.reason
    if not account_report.allowed:
        reason = str(account_report.reason)
        if reason.startswith("riesgo agregado"):
            reason = f"skip: {reason}"
        else:
            reason = f"guard de cuenta: {reason}"
        _record_signal(db_path, bot, symbol, signal, entry, reason)
        return _blocked(
            bot,
            symbol,
            signal,
            reason,
            price=entry,
            atr_value=atr_value,
            guards=guards,
        )

    try:
        budget = assess_open(
            db_path,
            symbol=symbol,
            side="buy" if sign > 0 else "sell",
            proposed_risk_usd=risk_usd,
            equity=equity,
            positions=positions,
            limits=limits,
            bot=bot.signal_bot,
        )
    except Exception as exc:
        raise ForwardError(f"{bot.id}: presupuesto no disponible: {exc}") from exc
    guards["risk_budget"] = "ok" if budget.get("allowed") else budget.get("reason")
    if not budget.get("allowed"):
        _record_signal(
            db_path,
            bot,
            symbol,
            signal,
            entry,
            f"blocked risk_budget: {budget.get('reason')}",
        )
        return _blocked(
            bot,
            symbol,
            signal,
            f"presupuesto: {budget.get('reason')}",
            price=entry,
            atr_value=atr_value,
            guards=guards,
        )

    action = "open_long" if sign > 0 else "open_short"
    reason = (
        f"target={signal:+.0f} ATR={atr_value:.5f} "
        f"stop={bot.stop_atr:g}ATR max_hold={bot.params.get('max_hold')}"
    )
    if dry_run:
        _record_signal(
            db_path, bot, symbol, signal, entry, f"{action} dry_run: {reason}"
        )
        return ForwardDecision(
            bot=bot.id,
            symbol=symbol,
            signal=signal,
            action=action,
            reason=reason,
            price=entry,
            atr=atr_value,
            stop=stop,
            volume=volume,
            dry_run=True,
            guards=guards,
        )

    if not bot.enabled:
        raise ForwardError(
            f"{bot.id}: enabled:false; no se envía ninguna apertura"
        )

    try:
        order = broker.submit_market(
            symbol,
            sign * volume,
            sl=stop,
            bot=bot.signal_bot,
            reason=reason,
            risk_usd=risk_usd,
            stop_price=stop,
            magic=bot.magic,
            dry_run=False,
        )
    except Exception as exc:
        _record_signal(
            db_path, bot, symbol, signal, entry, f"{action} error: {exc}"
        )
        raise ForwardError(f"{bot.id}: no se pudo abrir: {exc}") from exc
    _record_signal(
        db_path,
        bot,
        symbol,
        signal,
        float(order.get("price") or entry),
        f"{action} executed: {reason}",
    )
    if bot.swing:
        _set_last_signal(db_path, bot.signal_bot, signal)
    return ForwardDecision(
        bot=bot.id,
        symbol=symbol,
        signal=signal,
        action="opened_long" if sign > 0 else "opened_short",
        reason=reason,
        price=float(order.get("price") or entry),
        atr=atr_value,
        stop=stop,
        volume=volume,
        dry_run=False,
        order=order,
        guards=guards,
    )


def run_forward_all(
    bots: list[ForwardBot],
    broker,
    settings: Settings,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
    db_path: str | Path = DEFAULT_DB,
    bars: int = DEFAULT_BARS,
) -> list[ForwardDecision]:
    """Evalúa la lista de candidatos en orden; un fallo detiene el lote."""
    return [
        run_forward_bot(
            bot,
            broker,
            settings,
            dry_run=dry_run,
            now=now,
            db_path=db_path,
            bars=bars,
        )
        for bot in bots
    ]


__all__ = [
    "CONFIG_PATH",
    "DEFAULT_BARS",
    "ForwardBot",
    "ForwardDecision",
    "ForwardError",
    "get_forward_bot",
    "load_forward_bots",
    "run_forward_all",
    "run_forward_bot",
]
