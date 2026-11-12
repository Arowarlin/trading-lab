"""Biblioteca de estrategias del carril IA discrecional.

El LLM elige estilo, estrategia, símbolo, timeframe y dirección. Los niveles
(SL, TP, distancias) los calcula este módulo; una propuesta con niveles propios
no existe. Cada estrategia declara los timeframes en los que el código sabe
calcularla; la asignación final símbolo/estrategia/timeframe vive en
``config/ai_trader.yaml`` (por estilo).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

TIMEFRAMES = ("M1", "M5", "M15", "H1", "H4", "D1")

NEW_YORK = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

# Timeframe nativo (compatibilidad con el carril original de un solo estilo).
STRATEGY_TIMEFRAME = {
    "orb_ny": "M15",
    "vwap_reversion": "M15",
    "bollinger_squeeze": "H1",
    "liquidity_sweep": "H1",
    "london_breakout": "H1",
    "ema_pullback": "H1",
    "rsi2_connors": "D1",
    "donchian_turtle": "D1",
    "inside_bar": "D1",
    "trend_pullback": "H4",
}

# Timeframes en los que cada estrategia tiene una implementación honesta.
STRATEGY_TIMEFRAMES = {
    "orb_ny": ("M1", "M5", "M15"),
    "vwap_reversion": ("M1", "M5", "M15"),
    "bollinger_squeeze": ("M5", "M15", "H1", "H4"),
    "liquidity_sweep": ("M15", "H1", "H4", "D1"),
    "london_breakout": ("M5", "M15", "H1"),
    "ema_pullback": ("M5", "M15", "H1", "H4"),
    "rsi2_connors": ("D1",),
    "donchian_turtle": ("H4", "D1"),
    "inside_bar": ("H4", "D1"),
    "trend_pullback": ("H4",),
}

SECTION = {"M1": "m1", "M5": "m5", "M15": "m15",
           "H1": "h1", "H4": "h4", "D1": "d1"}

ALLOWED = {
    "US100.CASH": {
        "orb_ny": "M15",
        "vwap_reversion": "M15",
        "bollinger_squeeze": "H1",
        "rsi2_connors": "D1",
        "donchian_turtle": "D1",
        "trend_pullback": "H4",
    },
    "XAUUSD": {
        "liquidity_sweep": "H1",
        "donchian_turtle": "D1",
        "inside_bar": "D1",
        "trend_pullback": "H4",
    },
    "EURUSD": {
        "london_breakout": "H1",
        "ema_pullback": "H1",
        "inside_bar": "D1",
        "trend_pullback": "H4",
    },
    "GBPUSD": {
        "london_breakout": "H1",
        "ema_pullback": "H1",
        "inside_bar": "D1",
        "trend_pullback": "H4",
    },
    "USDJPY": {
        "ema_pullback": "H1",
        "donchian_turtle": "D1",
        "trend_pullback": "H4",
    },
}


@dataclass(frozen=True)
class LevelPlan:
    strategy: str
    side: str
    timeframe: str
    entry: float
    sl: float
    tp: float | None
    stop_distance: float
    rr: float | None


class SetupError(ValueError):
    pass


def allowed_timeframe(symbol: str, strategy: str) -> str | None:
    return ALLOWED.get(str(symbol).upper(), {}).get(strategy)


def supports(strategy: str, timeframe: str) -> bool:
    return str(timeframe).upper() in STRATEGY_TIMEFRAMES.get(strategy, ())


def _block(snap: dict, timeframe: str) -> dict:
    section = SECTION.get(str(timeframe).upper())
    if section is None:
        raise SetupError(f"timeframe no soportado: {timeframe}")
    block = snap.get(section)
    if not isinstance(block, dict):
        raise SetupError(f"Sin datos: {section}")
    return block


def _f(snap: dict, section: str, key: str) -> float:
    block = snap.get(section) or {}
    value = block.get(key)
    if value in (None, "", "Sin datos"):
        raise SetupError(f"Sin datos: {section}.{key}")
    return float(value)


def _b(block: dict, key: str) -> float:
    value = block.get(key)
    if value in (None, "", "Sin datos"):
        raise SetupError(f"Sin datos: {key}")
    return float(value)


def _ok(condition: bool, reason: str) -> tuple[bool, str]:
    return (True, "") if condition else (False, reason)


def _snap_now(snap: dict) -> datetime:
    """Hora del snapshot (UTC) para validar ventanas; ahora si no viene."""
    raw = snap.get("now")
    if raw in (None, "", "Sin datos"):
        return datetime.now(timezone.utc)
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate(
    strategy: str, side: str, snap: dict, timeframe: str | None = None
) -> tuple[bool, str]:
    if strategy not in STRATEGY_TIMEFRAME:
        return False, f"estrategia desconocida: {strategy}"
    tf = str(timeframe or STRATEGY_TIMEFRAME[strategy]).upper()
    if not supports(strategy, tf):
        return False, f"{strategy} no soporta {tf}"
    if timeframe is None and allowed_timeframe(
        str(snap.get("symbol") or ""), strategy
    ) not in (None, tf):
        return False, f"{strategy} no asignada a {snap.get('symbol')}"
    if side not in {"buy", "sell"}:
        return False, f"side inválido: {side}"
    try:
        price = float(snap["price"])
        block = _block(snap, tf)
        if block.get("error"):
            return False, f"Sin datos: {block['error']}"
        if strategy == "orb_ny":
            local = _snap_now(snap).astimezone(NEW_YORK)
            if not (time(9, 30) <= local.time() < time(16, 0)):
                return False, "fuera de la sesión NY (09:30-16:00)"
            if not bool(block.get("orb_valid")):
                return False, "rango de apertura NY incompleto"
            high, low = _b(block, "orb_high"), _b(block, "orb_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro del rango de apertura")
        if strategy == "vwap_reversion":
            vwap, sigma = _b(block, "vwap"), _b(block, "vwap_sigma")
            return _ok(
                (side == "buy" and price < vwap - 2 * sigma)
                or (side == "sell" and price > vwap + 2 * sigma),
                "precio a menos de 2 desviaciones del VWAP",
            )
        if strategy == "bollinger_squeeze":
            if not bool(block.get("bb_squeeze")):
                return False, "Bollinger fuera del mínimo de 120 barras"
            close = _b(block, "close")
            return _ok(
                (side == "buy" and close > _b(block, "bb_upper"))
                or (side == "sell" and close < _b(block, "bb_lower")),
                "cierre dentro de las bandas",
            )
        if strategy == "liquidity_sweep":
            return _ok(
                (side == "sell" and bool(block.get("sweep_high")))
                or (side == "buy" and bool(block.get("sweep_low"))),
                "no hay barrido del día anterior",
            )
        if strategy == "london_breakout":
            local = _snap_now(snap).astimezone(LONDON)
            if not (time(7, 0) <= local.time() < time(10, 0)):
                return False, "fuera de la ventana de ruptura 07:00-10:00 Londres"
            if not bool(block.get("asian_valid")):
                return False, "rango asiático incompleto"
            high, low = _b(block, "asian_high"), _b(block, "asian_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro del rango asiático")
        if strategy == "ema_pullback":
            e9, e21, e50 = (_b(block, k) for k in ("ema9", "ema21", "ema50"))
            high, low = _b(block, "high"), _b(block, "low")
            close, open_ = _b(block, "close"), _b(block, "open")
            if side == "buy":
                return _ok(e9 > e21 > e50 and low <= e21 and close > e21 and close > open_,
                           "sin retroceso a EMA21 con reanudación")
            return _ok(e9 < e21 < e50 and high >= e21 and close < e21 and close < open_,
                       "sin retroceso a EMA21 con reanudación")
        if strategy == "rsi2_connors":
            if side != "buy":
                return False, "rsi2_connors solo opera largos"
            # Entrada: índice sobre SMA200 y RSI(2) < 10. La salida (cierre
            # sobre SMA5) la ejecuta `manage`, no se convierte en TP intradía.
            return _ok(
                bool(snap.get("is_index"))
                and price > _f(snap, "d1", "sma200")
                and _f(snap, "d1", "rsi2") < 10,
                "índice bajo SMA200 o RSI2 >= 10",
            )
        if strategy == "donchian_turtle":
            if side == "buy":
                return _ok(price > _f(snap, "d1", "dc20_high") and price > _f(snap, "d1", "dc55_high"),
                           "sin ruptura de 20 días con filtro de 55")
            return _ok(price < _f(snap, "d1", "dc20_low") and price < _f(snap, "d1", "dc55_low"),
                       "sin ruptura de 20 días con filtro de 55")
        if strategy == "inside_bar":
            if not bool(block.get("inside_bar")):
                return False, "la última vela no es inside bar"
            high, low = _b(block, "mother_high"), _b(block, "mother_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro de la vela madre")
        if strategy == "trend_pullback":
            close_d1 = _f(snap, "d1", "close")
            sma200 = _f(snap, "d1", "sma200")
            atr = _b(block, "atr")
            sma20 = _b(block, "sma20")
            low, high, close = (_b(block, key) for key in ("low", "high", "close"))
            zone_low, zone_high = sma20 - 0.5 * atr, sma20 + 0.5 * atr
            if side == "buy":
                return _ok(
                    close_d1 > sma200
                    and zone_low <= low <= zone_high
                    and close >= sma20,
                    "sin tendencia D1 alcista o sin retroceso a SMA20 H4",
                )
            return _ok(
                close_d1 < sma200
                and zone_low <= high <= zone_high
                and close <= sma20,
                "sin tendencia D1 bajista o sin retroceso a SMA20 H4",
            )
    except (KeyError, TypeError) as exc:
        return False, f"snapshot incompleto: {exc}"
    except SetupError as exc:
        return False, str(exc)
    return False, f"estrategia sin validación: {strategy}"


def plan(
    strategy: str, side: str, snap: dict, timeframe: str | None = None
) -> LevelPlan:
    tf = str(timeframe or STRATEGY_TIMEFRAME.get(strategy, "")).upper()
    ok, reason = validate(strategy, side, snap, tf)
    if not ok:
        raise SetupError(reason)
    price = float(snap["price"])
    block = _block(snap, tf)
    stop = 1.0 if side == "buy" else -1.0
    tp: float | None
    if strategy == "orb_ny":
        sl = _b(block, "orb_low") if side == "buy" else _b(block, "orb_high")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "vwap_reversion":
        dist = _b(block, "atr")
        sl = price - stop * dist
        tp = _b(block, "vwap")
    elif strategy == "bollinger_squeeze":
        sl = _b(block, "bb_mid")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "liquidity_sweep":
        sl = _b(block, "high") if side == "sell" else _b(block, "low")
        dist = abs(price - sl)
        mid = _b(block, "prev_mid")
        two_r = price + stop * 2 * dist
        tp = max(mid, two_r) if side == "sell" else min(mid, two_r)
    elif strategy == "london_breakout":
        high, low = _b(block, "asian_high"), _b(block, "asian_low")
        sl = (high + low) / 2
        dist = abs(price - sl)
        tp = price + stop * 1.5 * (high - low)
    elif strategy == "ema_pullback":
        dist_atr = _b(block, "atr")
        e50 = _b(block, "ema50")
        sl = e50 - dist_atr if side == "buy" else e50 + dist_atr
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "rsi2_connors":
        sl = price - 2 * _f(snap, "d1", "atr")
        # Sin TP: la salida es el cierre D1 sobre la SMA5 (la ejecuta manage).
        tp = None
        dist = abs(price - sl)
    elif strategy == "donchian_turtle":
        sl = price - 2 * _f(snap, "d1", "atr") if side == "buy" else price + 2 * _f(snap, "d1", "atr")
        dist = abs(price - sl)
        tp = None
    elif strategy == "inside_bar":
        sl = _b(block, "mother_low") if side == "buy" else _b(block, "mother_high")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "trend_pullback":
        dist_atr = _b(block, "atr")
        dist = 1.5 * dist_atr
        sl = price - stop * dist
        tp = price + stop * 3.0 * dist_atr
    else:
        raise SetupError(f"estrategia sin niveles: {strategy}")
    if dist <= 0:
        raise SetupError("distancia de stop no positiva")
    if tp is not None:
        if (side == "buy" and tp <= price) or (side == "sell" and tp >= price):
            raise SetupError("TP en el lado incorrecto")
    rr = abs(tp - price) / dist if tp is not None else None
    return LevelPlan(
        strategy=strategy,
        side=side,
        timeframe=tf,
        entry=round(price, 8),
        sl=round(sl, 8),
        tp=round(tp, 8) if tp is not None else None,
        stop_distance=dist,
        rr=round(rr, 4) if rr is not None else None,
    )


def describe() -> dict:
    return {
        "orb_ny": "M1/M5/M15: rango de los primeros 60 minutos de NY; ruptura; SL al otro lado; TP 2R",
        "vwap_reversion": "M1/M5/M15: precio >2σ del VWAP de sesión; vuelta al VWAP; SL 1 ATR",
        "bollinger_squeeze": "M5/H1/H4: BB(20,2) en mínimo de 120 barras y cierre fuera; SL banda media; TP 2R",
        "liquidity_sweep": "M15/H1/H4/D1: barrido del máximo/mínimo de ayer y cierre dentro; SL tras la mecha; TP centro de ayer o 2R",
        "london_breakout": "M5/M15/H1: rango asiático 00:00-07:00; ruptura; SL centro; TP 1,5×rango",
        "ema_pullback": "M5/H1/H4: EMA9>21>50 (o inverso); toque EMA21 y reanudación; SL 1 ATR tras EMA50; TP 2R",
        "rsi2_connors": "D1: índices sobre SMA200, RSI2<10; salida en SMA5; SL 2 ATR D1",
        "donchian_turtle": "H4/D1: ruptura 20 días con filtro 55; SL 2 ATR D1; trailing 10 días",
        "inside_bar": "H4/D1: inside bar; ruptura de la madre; SL al otro lado; TP 2R",
        "trend_pullback": "H4: tendencia D1 (close vs SMA200); retroceso a SMA20 H4 ±0,5 ATR; SL 1,5 ATR; TP 3 ATR",
    }
