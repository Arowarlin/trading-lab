"""Catálogo de bloques del Discovery Lab.

Cada bloque declara parámetros con rango/paso, tipo de salida, warmup y una
función de cálculo que solo usa barras cerradas. ``lookahead_safe=True`` se
verifica bloque a bloque en ``tests/test_discovery_lookahead.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from ..indicators import atr, ema, rsi, sma, zscore
from . import indicators_ext as ext


@dataclass(frozen=True)
class ParamSpec:
    low: float
    high: float
    step: float
    default: float
    integer: bool = False


@dataclass(frozen=True)
class BlockSpec:
    name: str
    output: str
    params: dict[str, ParamSpec]
    warmup: Callable[[dict], int]
    compute: Callable[[pd.DataFrame, dict, dict], pd.Series]
    description: str = ""
    lookahead_safe: bool = True


def _p(params: dict, name: str, spec: ParamSpec):
    value = params.get(name, spec.default)
    return int(value) if spec.integer else float(value)


def _n(params: dict) -> int:
    return max(1, int(params.get("n", 14)))


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {
        "tz": ctx.get("tz", "America/New_York"),
        "start": ctx.get("start", "09:35"),
        "end": ctx.get("end", "16:00"),
        "or_minutes": int(ctx.get("or_minutes", 15)),
    }


def _warm_n(params: dict) -> int:
    return _n(params) + 1


def _warm_lookback(params: dict) -> int:
    return max(_n(params) + 1, int(params.get("lookback", 100)) + 1)


def _rsi_float(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    values = rsi(bars["close"].astype(float), _n(params))
    return pd.to_numeric(values, errors="coerce").astype(float)


def _zscore_float(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    values = zscore(bars["close"].astype(float), _n(params))
    return pd.to_numeric(values, errors="coerce").astype(float)


def _bollinger_pct(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    close = bars["close"].astype(float)
    bands = ext.bollinger(close, _n(params), float(params.get("k", 2.0)))
    width = (bands["upper"] - bands["lower"]).replace(0, np.nan)
    return (close - bands["lower"]) / width


def _donchian_pos(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    close = bars["close"].astype(float)
    bands = ext.donchian(bars, _n(params))
    width = (bands["upper"] - bands["lower"]).replace(0, np.nan)
    return (close - bands["lower"]) / width


def _keltner_pos(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    close = bars["close"].astype(float)
    bands = ext.keltner(bars, _n(params), float(params.get("mult", 2.0)))
    width = (bands["upper"] - bands["lower"]).replace(0, np.nan)
    return (close - bands["lower"]) / width


def _vwap_distance(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    close = bars["close"].astype(float)
    context = _ctx(ctx)
    vwap = ext.vwap_session(
        bars,
        tz=context["tz"],
        start=context["start"],
        end=context["end"],
    )
    return (close - vwap) / vwap.replace(0, np.nan)


def _session_return(bars: pd.DataFrame, params: dict, ctx: dict) -> pd.Series:
    """Retorno close(end)/open(start)-1, constante tras cerrar la vela end."""

    context = _ctx(ctx)
    start_min = int(params.get("start", 570))
    end_min = int(params.get("end", 600))
    if start_min >= end_min:
        return pd.Series(np.nan, index=bars.index, dtype=float)
    local = bars.index.tz_convert(context["tz"])
    minutes = local.hour * 60 + local.minute
    days = local.date
    open_values = bars["open"].astype(float).to_numpy()
    close_values = bars["close"].astype(float).to_numpy()
    values = np.full(len(bars), np.nan, dtype=float)
    positions = np.arange(len(bars))
    unique_days = pd.unique(days)
    for day in unique_days:
        day_mask = days == day
        day_positions = positions[day_mask]
        start_hits = day_positions[minutes[day_mask] == start_min]
        end_hits = day_positions[minutes[day_mask] == end_min]
        if len(start_hits) == 0 or len(end_hits) == 0:
            continue
        start_pos = int(start_hits[0])
        end_pos = int(end_hits[0])
        if end_pos <= start_pos:
            continue
        begin = float(open_values[start_pos])
        finish = float(close_values[end_pos])
        if not np.isfinite(begin) or not np.isfinite(finish) or begin == 0.0:
            continue
        value = finish / begin - 1.0
        day_end = int(day_positions[-1]) + 1
        values[end_pos + 1 : day_end] = value
    return pd.Series(values, index=bars.index, dtype=float)


BLOCKS: dict[str, BlockSpec] = {
    "sma": BlockSpec(
        "sma",
        "float",
        {"n": ParamSpec(2, 400, 1, 20, True)},
        _warm_n,
        lambda bars, params, ctx: sma(bars["close"].astype(float), _n(params)),
        "media móvil simple",
    ),
    "ema": BlockSpec(
        "ema",
        "float",
        {"n": ParamSpec(2, 400, 1, 50, True)},
        _warm_n,
        lambda bars, params, ctx: ema(bars["close"].astype(float), _n(params)),
        "media móvil exponencial",
    ),
    "rsi": BlockSpec(
        "rsi",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True)},
        _warm_n,
        _rsi_float,
        "RSI",
    ),
    "atr": BlockSpec(
        "atr",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True)},
        _warm_n,
        lambda bars, params, ctx: atr(bars, _n(params)),
        "ATR",
    ),
    "zscore": BlockSpec(
        "zscore",
        "float",
        {"n": ParamSpec(5, 200, 1, 20, True)},
        _warm_n,
        _zscore_float,
        "z-score del cierre",
    ),
    "macd": BlockSpec(
        "macd",
        "float",
        {
            "fast": ParamSpec(2, 100, 1, 12, True),
            "slow": ParamSpec(5, 200, 1, 26, True),
        },
        lambda params: int(params.get("slow", 26)) + 1,
        lambda bars, params, ctx: ext.macd(
            bars["close"].astype(float),
            int(params.get("fast", 12)),
            int(params.get("slow", 26)),
        ),
        "línea MACD",
    ),
    "adx": BlockSpec(
        "adx",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True)},
        lambda params: int(params.get("n", 14)) * 2 + 1,
        lambda bars, params, ctx: ext.adx(bars, _n(params)),
        "ADX",
    ),
    "bollinger_pct": BlockSpec(
        "bollinger_pct",
        "float",
        {"n": ParamSpec(5, 200, 1, 20, True), "k": ParamSpec(0.5, 4.0, 0.1, 2.0)},
        _warm_n,
        _bollinger_pct,
        "posición en las bandas de Bollinger",
    ),
    "stochastic": BlockSpec(
        "stochastic",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True)},
        _warm_n,
        lambda bars, params, ctx: ext.stochastic(bars, _n(params)),
        "estocástico %K",
    ),
    "cci": BlockSpec(
        "cci",
        "float",
        {"n": ParamSpec(2, 200, 1, 20, True)},
        _warm_n,
        lambda bars, params, ctx: ext.cci(bars, _n(params)),
        "CCI",
    ),
    "donchian_pos": BlockSpec(
        "donchian_pos",
        "float",
        {"n": ParamSpec(5, 400, 1, 20, True)},
        _warm_n,
        _donchian_pos,
        "posición en el canal Donchian",
    ),
    "keltner_pos": BlockSpec(
        "keltner_pos",
        "float",
        {"n": ParamSpec(5, 200, 1, 20, True), "mult": ParamSpec(0.5, 4.0, 0.1, 2.0)},
        _warm_n,
        _keltner_pos,
        "posición en el canal Keltner",
    ),
    "vwap_distance": BlockSpec(
        "vwap_distance",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True)},
        _warm_n,
        _vwap_distance,
        "distancia al VWAP de la sesión",
    ),
    "realized_vol": BlockSpec(
        "realized_vol",
        "float",
        {"n": ParamSpec(5, 200, 1, 20, True)},
        _warm_n,
        lambda bars, params, ctx: ext.realized_vol(bars["close"].astype(float), _n(params)),
        "volatilidad realizada",
    ),
    "atr_pct_rank": BlockSpec(
        "atr_pct_rank",
        "float",
        {"n": ParamSpec(2, 100, 1, 14, True), "lookback": ParamSpec(10, 500, 1, 100, True)},
        _warm_lookback,
        lambda bars, params, ctx: ext.atr_pct_rank(
            bars, _n(params), int(params.get("lookback", 100))
        ),
        "percentil del ATR porcentual",
    ),
    "range_compression": BlockSpec(
        "range_compression",
        "float",
        {"n": ParamSpec(5, 200, 1, 20, True)},
        _warm_n,
        lambda bars, params, ctx: ext.range_compression(bars, _n(params)),
        "rango / ATR",
    ),
    "swing_high": BlockSpec(
        "swing_high",
        "float",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.swing_high(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "pivote alto confirmado y desplazado",
    ),
    "swing_low": BlockSpec(
        "swing_low",
        "float",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.swing_low(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "pivote bajo confirmado y desplazado",
    ),
    "bos_up": BlockSpec(
        "bos_up",
        "bool",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.bos_up(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "ruptura de estructura al alza",
    ),
    "bos_down": BlockSpec(
        "bos_down",
        "bool",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.bos_down(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "ruptura de estructura a la baja",
    ),
    "choch_up": BlockSpec(
        "choch_up",
        "bool",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.choch_up(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "cambio de carácter al alza",
    ),
    "choch_down": BlockSpec(
        "choch_down",
        "bool",
        {"left": ParamSpec(1, 50, 1, 5, True), "right": ParamSpec(1, 50, 1, 5, True)},
        lambda params: int(params.get("left", 5)) + int(params.get("right", 5)) + 1,
        lambda bars, params, ctx: ext.choch_down(
            bars, int(params.get("left", 5)), int(params.get("right", 5))
        ),
        "cambio de carácter a la baja",
    ),
    "engulfing": BlockSpec(
        "engulfing",
        "bool",
        {},
        lambda params: 2,
        lambda bars, params, ctx: _engulfing(bars),
        "envolvente",
    ),
    "pin_bar": BlockSpec(
        "pin_bar",
        "bool",
        {"ratio": ParamSpec(1.5, 10.0, 0.1, 2.0)},
        lambda params: 1,
        lambda bars, params, ctx: _pin_bar(bars, float(params.get("ratio", 2.0))),
        "pin bar",
    ),
    "inside_bar": BlockSpec(
        "inside_bar",
        "bool",
        {},
        lambda params: 2,
        lambda bars, params, ctx: (bars["high"].astype(float) < bars["high"].astype(float).shift(1))
        & (bars["low"].astype(float) > bars["low"].astype(float).shift(1)),
        "inside bar",
    ),
    "range_expansion": BlockSpec(
        "range_expansion",
        "bool",
        {"n": ParamSpec(5, 100, 1, 20, True), "mult": ParamSpec(1.0, 5.0, 0.1, 1.5)},
        _warm_n,
        lambda bars, params, ctx: (
            (bars["high"].astype(float) - bars["low"].astype(float))
            > float(params.get("mult", 1.5))
            * (bars["high"].astype(float) - bars["low"].astype(float))
            .rolling(_n(params), min_periods=_n(params))
            .mean()
            .shift(1)
        ),
        "expansión de rango",
    ),
    "trending": BlockSpec(
        "trending",
        "bool",
        {"n": ParamSpec(2, 100, 1, 14, True), "threshold": ParamSpec(5, 60, 1, 25)},
        lambda params: int(params.get("n", 14)) * 2 + 1,
        lambda bars, params, ctx: ext.adx(bars, _n(params)) > float(params.get("threshold", 25)),
        "régimen tendencial",
    ),
    "ranging": BlockSpec(
        "ranging",
        "bool",
        {"n": ParamSpec(2, 100, 1, 14, True), "threshold": ParamSpec(5, 60, 1, 20)},
        lambda params: int(params.get("n", 14)) * 2 + 1,
        lambda bars, params, ctx: ext.adx(bars, _n(params)) < float(params.get("threshold", 20)),
        "régimen lateral",
    ),
    "vol_high": BlockSpec(
        "vol_high",
        "bool",
        {"n": ParamSpec(2, 100, 1, 14, True), "lookback": ParamSpec(10, 500, 1, 100, True), "pct": ParamSpec(0.5, 1.0, 0.05, 0.8)},
        _warm_lookback,
        lambda bars, params, ctx: ext.atr_pct_rank(bars, _n(params), int(params.get("lookback", 100)))
        > float(params.get("pct", 0.8)),
        "volatilidad alta",
    ),
    "vol_low": BlockSpec(
        "vol_low",
        "bool",
        {"n": ParamSpec(2, 100, 1, 14, True), "lookback": ParamSpec(10, 500, 1, 100, True), "pct": ParamSpec(0.0, 0.5, 0.05, 0.2)},
        _warm_lookback,
        lambda bars, params, ctx: ext.atr_pct_rank(bars, _n(params), int(params.get("lookback", 100)))
        < float(params.get("pct", 0.2)),
        "volatilidad baja",
    ),
    "session_return": BlockSpec(
        "session_return",
        "float",
        {
            "start": ParamSpec(570, 570, 1, 570, True),
            "end": ParamSpec(600, 660, 30, 600, True),
        },
        lambda params: 0,
        _session_return,
        "retorno close(end)/open(start)-1 de la sesión; NaN hasta cerrar end",
    ),
}


def _engulfing(bars: pd.DataFrame) -> pd.Series:
    open_ = bars["open"].astype(float)
    close = bars["close"].astype(float)
    prev_open = open_.shift(1)
    prev_close = close.shift(1)
    bullish = (close > open_) & (prev_close < prev_open) & (open_ <= prev_close) & (close >= prev_open)
    bearish = (close < open_) & (prev_close > prev_open) & (open_ >= prev_close) & (close <= prev_open)
    return bullish | bearish


def _pin_bar(bars: pd.DataFrame, ratio: float) -> pd.Series:
    open_ = bars["open"].astype(float)
    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    body = (close - open_).abs()
    upper = high - pd.concat([open_, close], axis=1).max(axis=1)
    lower = pd.concat([open_, close], axis=1).min(axis=1) - low
    return ((lower > ratio * body) & (lower > upper)) | ((upper > ratio * body) & (upper > lower))


def get_block(name: str) -> BlockSpec:
    try:
        return BLOCKS[str(name)]
    except KeyError as exc:
        raise KeyError(f"bloque desconocido: {name}") from exc


__all__ = ["BLOCKS", "BlockSpec", "ParamSpec", "get_block"]
