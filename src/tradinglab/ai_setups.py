"""Biblioteca de estrategias del carril IA discrecional.

El LLM elige estrategia, símbolo, timeframe y dirección. Los niveles (SL, TP,
distancias) los calcula este módulo; una propuesta con niveles propios no
existe. Cada estrategia tiene un timeframe fijo y una asignación por activo.
"""
from __future__ import annotations

from dataclasses import dataclass

TIMEFRAMES = ("M15", "H1", "D1")

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
}

ALLOWED = {
    "US100.CASH": {
        "orb_ny": "M15",
        "vwap_reversion": "M15",
        "bollinger_squeeze": "H1",
        "rsi2_connors": "D1",
        "donchian_turtle": "D1",
    },
    "XAUUSD": {
        "liquidity_sweep": "H1",
        "donchian_turtle": "D1",
        "inside_bar": "D1",
    },
    "EURUSD": {
        "london_breakout": "H1",
        "ema_pullback": "H1",
        "inside_bar": "D1",
    },
    "GBPUSD": {
        "london_breakout": "H1",
        "ema_pullback": "H1",
        "inside_bar": "D1",
    },
    "USDJPY": {
        "ema_pullback": "H1",
        "donchian_turtle": "D1",
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


def _f(snap: dict, section: str, key: str) -> float:
    block = snap.get(section) or {}
    value = block.get(key)
    if value in (None, "", "Sin datos"):
        raise SetupError(f"Sin datos: {section}.{key}")
    return float(value)


def _ok(condition: bool, reason: str) -> tuple[bool, str]:
    return (True, "") if condition else (False, reason)


def validate(strategy: str, side: str, snap: dict) -> tuple[bool, str]:
    if strategy not in STRATEGY_TIMEFRAME:
        return False, f"estrategia desconocida: {strategy}"
    tf = STRATEGY_TIMEFRAME[strategy]
    if allowed_timeframe(str(snap.get("symbol") or ""), strategy) != tf:
        return False, f"{strategy} no asignada a {snap.get('symbol')} ({tf})"
    if side not in {"buy", "sell"}:
        return False, f"side inválido: {side}"
    try:
        price = float(snap["price"])
        if strategy == "orb_ny":
            if not bool(snap["m15"].get("orb_valid")):
                return False, "rango de apertura NY incompleto"
            high, low = _f(snap, "m15", "orb_high"), _f(snap, "m15", "orb_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro del rango de apertura")
        if strategy == "vwap_reversion":
            vwap, sigma = _f(snap, "m15", "vwap"), _f(snap, "m15", "vwap_sigma")
            return _ok(
                (side == "buy" and price < vwap - 2 * sigma)
                or (side == "sell" and price > vwap + 2 * sigma),
                "precio a menos de 2 desviaciones del VWAP",
            )
        if strategy == "bollinger_squeeze":
            if not bool(snap["h1"].get("bb_squeeze")):
                return False, "Bollinger fuera del mínimo de 120 barras"
            close = _f(snap, "h1", "close")
            return _ok(
                (side == "buy" and close > _f(snap, "h1", "bb_upper"))
                or (side == "sell" and close < _f(snap, "h1", "bb_lower")),
                "cierre dentro de las bandas",
            )
        if strategy == "liquidity_sweep":
            return _ok(
                (side == "sell" and bool(snap["h1"].get("sweep_high")))
                or (side == "buy" and bool(snap["h1"].get("sweep_low"))),
                "no hay barrido del día anterior",
            )
        if strategy == "london_breakout":
            if not bool(snap["h1"].get("asian_valid")):
                return False, "rango asiático incompleto"
            high, low = _f(snap, "h1", "asian_high"), _f(snap, "h1", "asian_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro del rango asiático")
        if strategy == "ema_pullback":
            e9, e21, e50 = (_f(snap, "h1", k) for k in ("ema9", "ema21", "ema50"))
            high, low = _f(snap, "h1", "high"), _f(snap, "h1", "low")
            close, open_ = _f(snap, "h1", "close"), _f(snap, "h1", "open")
            if side == "buy":
                return _ok(e9 > e21 > e50 and low <= e21 and close > e21 and close > open_,
                           "sin retroceso a EMA21 con reanudación")
            return _ok(e9 < e21 < e50 and high >= e21 and close < e21 and close < open_,
                       "sin retroceso a EMA21 con reanudación")
        if strategy == "rsi2_connors":
            if side != "buy":
                return False, "rsi2_connors solo opera largos"
            return _ok(
                bool(snap.get("is_index"))
                and price > _f(snap, "d1", "sma200")
                and _f(snap, "d1", "rsi2") < 10
                and _f(snap, "d1", "sma5") > price,
                "índice bajo SMA200, RSI2 >= 10 o SMA5 por debajo",
            )
        if strategy == "donchian_turtle":
            if side == "buy":
                return _ok(price > _f(snap, "d1", "dc20_high") and price > _f(snap, "d1", "dc55_high"),
                           "sin ruptura de 20 días con filtro de 55")
            return _ok(price < _f(snap, "d1", "dc20_low") and price < _f(snap, "d1", "dc55_low"),
                       "sin ruptura de 20 días con filtro de 55")
        if strategy == "inside_bar":
            if not bool(snap["d1"].get("inside_bar")):
                return False, "la última vela no es inside bar"
            high, low = _f(snap, "d1", "mother_high"), _f(snap, "d1", "mother_low")
            return _ok((side == "buy" and price > high) or (side == "sell" and price < low),
                       "precio dentro de la vela madre")
    except (KeyError, TypeError) as exc:
        return False, f"snapshot incompleto: {exc}"
    except SetupError as exc:
        return False, str(exc)
    return False, f"estrategia sin validación: {strategy}"


def plan(strategy: str, side: str, snap: dict) -> LevelPlan:
    ok, reason = validate(strategy, side, snap)
    if not ok:
        raise SetupError(reason)
    price = float(snap["price"])
    stop = 1.0 if side == "buy" else -1.0
    tp: float | None
    if strategy == "orb_ny":
        sl = _f(snap, "m15", "orb_low") if side == "buy" else _f(snap, "m15", "orb_high")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "vwap_reversion":
        dist = _f(snap, "m15", "atr")
        sl = price - stop * dist
        tp = _f(snap, "m15", "vwap")
    elif strategy == "bollinger_squeeze":
        sl = _f(snap, "h1", "bb_mid")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "liquidity_sweep":
        sl = _f(snap, "h1", "high") if side == "sell" else _f(snap, "h1", "low")
        dist = abs(price - sl)
        mid = _f(snap, "h1", "prev_mid")
        two_r = price + stop * 2 * dist
        tp = max(mid, two_r) if side == "sell" else min(mid, two_r)
    elif strategy == "london_breakout":
        high, low = _f(snap, "h1", "asian_high"), _f(snap, "h1", "asian_low")
        sl = (high + low) / 2
        dist = abs(price - sl)
        tp = price + stop * 1.5 * (high - low)
    elif strategy == "ema_pullback":
        dist_atr = _f(snap, "h1", "atr")
        e50 = _f(snap, "h1", "ema50")
        sl = e50 - dist_atr if side == "buy" else e50 + dist_atr
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
    elif strategy == "rsi2_connors":
        sl = price - 2 * _f(snap, "d1", "atr")
        tp = _f(snap, "d1", "sma5")
        dist = abs(price - sl)
    elif strategy == "donchian_turtle":
        sl = price - 2 * _f(snap, "d1", "atr") if side == "buy" else price + 2 * _f(snap, "d1", "atr")
        dist = abs(price - sl)
        tp = None
    elif strategy == "inside_bar":
        sl = _f(snap, "d1", "mother_low") if side == "buy" else _f(snap, "d1", "mother_high")
        dist = abs(price - sl)
        tp = price + stop * 2 * dist
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
        timeframe=STRATEGY_TIMEFRAME[strategy],
        entry=round(price, 8),
        sl=round(sl, 8),
        tp=round(tp, 8) if tp is not None else None,
        stop_distance=dist,
        rr=round(rr, 4) if rr is not None else None,
    )


def describe() -> dict:
    return {
        "orb_ny": "M15: rango de los primeros 4 bloques M15 de NY; ruptura; SL al otro lado; TP 2R; cierre de sesión",
        "vwap_reversion": "M15: precio >2σ del VWAP de sesión; vuelta al VWAP; SL 1 ATR M15",
        "bollinger_squeeze": "H1: BB(20,2) en mínimo de 120 barras y cierre fuera; SL banda media; TP 2R",
        "liquidity_sweep": "H1: barrido del máximo/mínimo de ayer y cierre dentro; SL tras la mecha; TP centro de ayer o 2R",
        "london_breakout": "H1: rango asiático 00:00-07:00; ruptura 07:00-10:00; SL centro; TP 1,5×rango",
        "ema_pullback": "H1: EMA9>21>50 (o inverso); toque EMA21 y reanudación; SL 1 ATR tras EMA50; TP 2R",
        "rsi2_connors": "D1: índices sobre SMA200, RSI2<10; salida en SMA5; SL 2 ATR D1",
        "donchian_turtle": "D1: ruptura 20 días con filtro 55; SL 2 ATR D1; trailing 10 días",
        "inside_bar": "D1: inside bar; ruptura de la madre; SL al otro lado; TP 2R",
    }
