"""Exportador determinista de estrategias DSL a un EA MQL5 (F12a).

La entrada es el AST que ya evalua ``compiler.py`` (genoma + parametros); la
salida es un ``.mq5`` autonomo y un ``manifest.json`` con su sha256. La misma
entrada produce siempre los mismos bytes: no se escriben fechas, rutas
absolutas ni ordenes dependientes del entorno.

Semantica que replica el EA (fastbt/compiler):
  * senal en barra cerrada y entrada en el open de la barra siguiente;
  * una sola posicion a la vez, stop antes que objetivo, salida forzada;
  * sesion y huso America/New_York con DST calculado por reglas de EE. UU.;
  * stop/objetivo del DSL, BE/trailing desde la barra siguiente y ``flat_at``;
  * magic derivado del hash de la estrategia;
  * riesgo por operacion y limites de perdida diaria/total tomados del perfil
    de la cuenta (``config/propfund``), nunca hardcodeados.

Cobertura: cada bloque de ``blocks.py`` tiene traduccion MQL5 o el exportador
falla con ``bloque <nombre> no exportable``. No se exportan aproximaciones en
silencio. ``vwap_distance`` queda fuera porque el backtest usa ``tickvol`` o
volumen unitario segun el dataset y el EA no puede saber cual se uso. Los nodos
``htf`` quedan fuera porque la rejilla HTF del backtest esta anclada a las
17:00 de Nueva York y la del servidor MT5 no necesariamente coincide.

Traza de paridad: ``trace_csv`` ejecuta el mismo DSL con ``fastbt`` sobre barras
sinteticas y devuelve ``bar_time,side,entry,stop,target``. El EA escribe la
misma traza en ``InpTraceFile`` cuando ``InpEmitTrace=true`` (open de la barra
de entrada, no el fill). Para comparar: exportar la estrategia, cargar en el
Tester las mismas barras con ``InpServerUtcOffsetMinutes`` ajustado al servidor
y comparar ambos CSV por ``bar_time`` con tolerancia 1e-6 en precios. Una
diferencia de direccion o de barra es un fallo de logica, no de redondeo.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import yaml
from pydantic import ValidationError

from ..config import ROOT
from ..propfund.registry import load_registry
from . import dsl, specs
from .blocks import BLOCKS, get_block
from .compiler import compile as compile_signals
from .fastbt import CostPanel
from .fastbt import run as run_fastbt
from .timeframes import minutes_to_bars

EXPORTER_VERSION = "1.0.0"

UNSUPPORTED_BLOCKS: dict[str, str] = {
    "vwap_distance": (
        "depende del volumen del dataset (tickvol o volumen unitario); "
        "el EA no puede saber cual uso el backtest"
    ),
}

MQL5_PERIODS = {
    "M1": "PERIOD_M1",
    "M5": "PERIOD_M5",
    "M15": "PERIOD_M15",
    "M30": "PERIOD_M30",
    "H1": "PERIOD_H1",
    "H4": "PERIOD_H4",
    "D1": "PERIOD_D1",
}

_WEEKDAY_MQL5 = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0}


class ExportError(ValueError):
    """La estrategia o el perfil no se pueden exportar sin aproximar."""


@dataclass(frozen=True)
class TraceRow:
    bar_time: str
    side: str
    entry: float
    stop: float
    target: float | None


@dataclass(frozen=True)
class ExportResult:
    mq5_path: Path
    manifest_path: Path
    trace_path: Path | None
    sha256: str
    magic: int
    strategy_hash: str
    blocks: tuple[str, ...]
    account: str
    firm: str


# ---------------------------------------------------------------------------
# Perfil de la firma
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RiskProfile:
    account: str
    firm: str
    daily_loss: float
    max_loss: float
    risk_pct: float
    drawdown_mode: str


def _firm_profile(
    account_id: str,
    instrument: str,
    *,
    market: str | None = None,
    daily_loss: float | None = None,
    max_loss: float | None = None,
    risk_pct: float | None = None,
) -> _RiskProfile:
    registry = load_registry()
    account = registry.accounts.get(str(account_id).strip().upper())
    if account is None:
        raise ExportError(f"cuenta no registrada: {account_id}")
    firm = registry.firm_of(account.id)
    if market is not None and str(market) != account.market.value:
        raise ExportError(
            f"{account.id} es {account.market.value}; la estrategia declara {market}"
        )
    if instrument not in account.allowed_instruments:
        raise ExportError(
            f"{account.id} no permite {instrument}; "
            f"permitidos: {', '.join(account.allowed_instruments) or 'ninguno'}"
        )
    daily = daily_loss if daily_loss is not None else account.limits.daily_loss
    total = max_loss if max_loss is not None else account.limits.max_loss
    if daily is None or float(daily) <= 0:
        raise ExportError(
            f"Sin datos: {account.id} no declara perdida diaria; usa --daily-loss"
        )
    if total is None or float(total) <= 0:
        raise ExportError(
            f"Sin datos: {account.id} no declara perdida total; usa --max-loss"
        )
    if risk_pct is None:
        percent = float(account.risk.per_trade_risk_pct) * 100.0
    else:
        percent = float(risk_pct)
    if percent <= 0 or percent >= 100:
        raise ExportError(f"riesgo por operacion invalido: {percent}")
    return _RiskProfile(
        account=account.id,
        firm=firm.id,
        daily_loss=float(daily),
        max_loss=float(total),
        risk_pct=percent,
        drawdown_mode=str(account.limits.drawdown_mode),
    )


# ---------------------------------------------------------------------------
# Cobertura de bloques
# ---------------------------------------------------------------------------


_SUPPORTED = {
    "sma",
    "ema",
    "rsi",
    "atr",
    "zscore",
    "macd",
    "adx",
    "bollinger_pct",
    "stochastic",
    "cci",
    "donchian_pos",
    "keltner_pos",
    "realized_vol",
    "atr_pct_rank",
    "range_compression",
    "swing_high",
    "swing_low",
    "bos_up",
    "bos_down",
    "choch_up",
    "choch_down",
    "engulfing",
    "pin_bar",
    "inside_bar",
    "range_expansion",
    "trending",
    "ranging",
    "vol_high",
    "vol_low",
    "session_return",
}


def block_coverage() -> dict[str, tuple[bool, str]]:
    """Mapa completo ``BLOCKS`` -> (exportable, motivo si no)."""

    coverage: dict[str, tuple[bool, str]] = {}
    for name in BLOCKS:
        if name in UNSUPPORTED_BLOCKS:
            coverage[name] = (False, UNSUPPORTED_BLOCKS[name])
        elif name in _SUPPORTED:
            coverage[name] = (True, "")
        else:  # pragma: no cover - protege ante un bloque nuevo sin decision
            coverage[name] = (False, "sin traduccion MQL5 decidida")
    return coverage


def _require_exportable(name: str) -> None:
    if name in UNSUPPORTED_BLOCKS:
        raise ExportError(f"bloque {name} no exportable: {UNSUPPORTED_BLOCKS[name]}")
    if name not in _SUPPORTED:  # pragma: no cover - cubierto por el test de cobertura
        raise ExportError(f"bloque {name} no exportable: sin traduccion MQL5")


# ---------------------------------------------------------------------------
# Utilidades deterministas
# ---------------------------------------------------------------------------


def magic_number(strategy_hash: str) -> int:
    """Magic estable de 9 digitos derivado del hash del genoma."""

    digest = str(strategy_hash or "")
    if len(digest) < 8:
        raise ExportError("hash de estrategia demasiado corto para el magic")
    return int(digest[:8], 16) % 900_000_000 + 100_000_000


def _fmt(value: float) -> str:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ExportError(f"valor no finito en la estrategia: {value!r}")
    text = format(number, ".17g")
    if text == "-0":
        return "0"
    return text


def _hash_json(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _template_info(name: str | None) -> tuple[str, str, str | None]:
    """(nombre, version, sha256) de la plantilla; ``ninguna`` si no hay."""

    if not name:
        return "ninguna", "n/a", None
    if not all(char.isalnum() or char in {"_", "-"} for char in str(name)):
        raise ExportError(f"nombre de plantilla invalido: {name}")
    path = ROOT / "config" / "discovery" / "templates" / f"{name}.yaml"
    if not path.exists():
        raise ExportError(f"plantilla no encontrada: {path.name}")
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ExportError(f"plantilla YAML invalida {path.name}: {exc}") from exc
    version = str(data.get("version") or digest[:16])
    return str(name), version, digest


def _slug(text: str) -> str:
    cleaned = []
    for char in str(text):
        cleaned.append(char if char.isalnum() or char in {"_", "-"} else "_")
    return "".join(cleaned).strip("_") or "x"


def _model(strategy: dsl.Strategy | dict) -> dsl.Strategy:
    if isinstance(strategy, dsl.Strategy):
        return strategy
    try:
        return dsl.Strategy.model_validate(strategy)
    except ValidationError as exc:
        raise ExportError(f"estrategia invalida: {exc}") from exc


# ---------------------------------------------------------------------------
# Parametros de bloque
# ---------------------------------------------------------------------------


def _resolved_params(expr: dsl.Expr, name: str) -> dict[str, float | int]:
    spec = get_block(name)
    raw = dsl.indicator_params(expr)
    values: dict[str, float | int] = {}
    for param_name, param_spec in spec.params.items():
        value = raw.get(param_name, param_spec.default)
        values[param_name] = int(value) if param_spec.integer else float(value)
    return values


def _warmup_expr(expr: dsl.Expr | None) -> int:
    if expr is None:
        return 0
    if expr.kind in {"indicator", "pattern", "regime"}:
        name = expr.ind if expr.kind == "indicator" else expr.pattern if expr.kind == "pattern" else expr.regime
        assert name is not None
        return int(get_block(name).warmup(_resolved_params(expr, name)))
    if expr.kind == "level":
        if expr.level in {"donchian_high", "donchian_low"}:
            return int(expr.n or 20) + 1
        return 0
    if expr.kind == "htf":
        raise ExportError("nodo htf no exportable: la rejilla 17:00 NY no coincide con la del servidor")
    if expr.kind in {"held_for", "within_bars"}:
        child = _warmup_expr(expr.args[0] if expr.args else None)
        return child + int(expr.n or 0)
    if expr.kind in {"and", "or", "not", "gt", "lt", "ge", "le", "between", "cross_up", "cross_down"}:
        children = [*expr.args, expr.left, expr.right]
        return max((_warmup_expr(child) for child in children if child is not None), default=0)
    return 0


# ---------------------------------------------------------------------------
# Compilador de expresiones a MQL5
# ---------------------------------------------------------------------------


class _MqlCompiler:
    def __init__(self, strategy: dsl.Strategy, weekdays: Sequence[int]) -> None:
        self.strategy = strategy
        self.weekdays = tuple(int(day) for day in weekdays)
        self.functions: list[str] = []
        self.globals: list[str] = []
        self.states: list[tuple[str, str, dict[str, Any]]] = []
        self.state_keys: dict[str, str] = {}
        self.value_names: dict[str, str] = {}
        self.bool_names: dict[str, str] = {}
        self.blocks: set[str] = set()

    # -- estados ---------------------------------------------------------
    def _state(self, kind: str, params: dict[str, Any]) -> str:
        key = f"{kind}:{json.dumps(params, sort_keys=True)}"
        existing = self.state_keys.get(key)
        if existing is not None:
            return existing
        digest = _hash_json({"kind": kind, "params": params})[:10]
        prefix = "g_ema_" if kind == "ema" else "g_adx_"
        name = f"{prefix}{digest}"
        self.state_keys[key] = name
        self.states.append((name, kind, params))
        return name

    # -- funciones -------------------------------------------------------
    def _emit(self, text: str) -> None:
        self.functions.append(text.strip("\n"))

    def _value(self, expr: dsl.Expr) -> str:
        key = json.dumps(expr.model_dump(mode="json", exclude_none=True), sort_keys=True)
        cached = self.value_names.get(key)
        if cached is not None:
            return cached
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        name = f"V_{digest}"
        body: list[str] = [f"double {name}(const int shift, bool &ok)", "{"]
        kind = expr.kind
        if kind == "const":
            if expr.value is None:
                raise ExportError("const sin value")
            body.append(f"   ok = true; return {_fmt(float(expr.value))};")
        elif kind == "price":
            field = str(expr.price)
            if field == "open":
                body.append("   ok = true; return iOpen(_Symbol, _Period, shift);")
            elif field == "high":
                body.append("   ok = true; return iHigh(_Symbol, _Period, shift);")
            elif field == "low":
                body.append("   ok = true; return iLow(_Symbol, _Period, shift);")
            elif field == "close":
                body.append("   ok = true; return iClose(_Symbol, _Period, shift);")
            elif field == "range":
                body.append("   ok = true; return iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift);")
            elif field == "body":
                body.append("   ok = true; return iClose(_Symbol, _Period, shift) - iOpen(_Symbol, _Period, shift);")
            else:  # pragma: no cover - dsl.validate ya lo impide
                raise ExportError(f"precio no exportable: {field}")
        elif kind == "level":
            level = str(expr.level)
            if level in {"prev_session_high", "prev_session_low"}:
                which = "true" if level.endswith("high") else "false"
                body.append(f"   return PrevSessionLevelAt(shift, {which}, ok);")
            elif level in {"prev_day_high", "prev_day_low"}:
                which = "true" if level.endswith("high") else "false"
                body.append(f"   return PrevDayLevelAt(shift, {which}, ok);")
            elif level in {"opening_range_high", "opening_range_low"}:
                which = "true" if level.endswith("high") else "false"
                body.append(f"   return OpeningRangeAt(shift, {which}, ok);")
            elif level in {"donchian_high", "donchian_low"}:
                which = "true" if level.endswith("high") else "false"
                n = int(expr.n or 20)
                body.append(f"   return DonchianLevelAt(shift, {n}, {which}, ok);")
            else:  # pragma: no cover
                raise ExportError(f"nivel no exportable: {level}")
            self.blocks.add(f"level:{level}")
        elif kind == "indicator":
            block_name = str(expr.ind)
            _require_exportable(block_name)
            self.blocks.add(block_name)
            call = self._indicator_call(expr, block_name)
            body.append(f"   return {call};")
        else:
            raise ExportError(f"nodo de valor no exportable: {kind}")
        body.append("}")
        self._emit("\n".join(body))
        self.value_names[key] = name
        return name

    def _indicator_call(self, expr: dsl.Expr, name: str) -> str:
        params = _resolved_params(expr, name)
        if name == "sma":
            return f"SmaAt(shift, {params['n']}, ok)"
        if name == "ema":
            state = self._state("ema", {"span": int(params["n"])})
            return f"EmaAt({state}, shift, ok)"
        if name == "rsi":
            return f"RsiAt(shift, {params['n']}, ok)"
        if name == "atr":
            return f"AtrAt(shift, {params['n']}, ok)"
        if name == "zscore":
            return f"ZScoreAt(shift, {params['n']}, ok)"
        if name == "macd":
            fast_n = int(params["fast"])
            slow_n = int(params["slow"])
            if fast_n >= slow_n:
                raise ExportError(f"macd: fast {fast_n} debe ser menor que slow {slow_n}")
            fast_state = self._state("ema", {"span": fast_n})
            slow_state = self._state("ema", {"span": slow_n})
            return f"MacdAt({fast_state}, {slow_state}, shift, ok)"
        if name == "adx":
            state = self._state("adx", {"n": int(params["n"])})
            return f"AdxAt({state}, shift, ok)"
        if name == "bollinger_pct":
            return f"BollingerPctAt(shift, {params['n']}, {_fmt(params['k'])}, ok)"
        if name == "stochastic":
            return f"StochasticAt(shift, {params['n']}, ok)"
        if name == "cci":
            return f"CciAt(shift, {params['n']}, ok)"
        if name == "donchian_pos":
            return f"DonchianPosAt(shift, {params['n']}, ok)"
        if name == "keltner_pos":
            state = self._state("ema", {"span": int(params["n"])})
            return f"KeltnerPosAt(shift, {params['n']}, {_fmt(params['mult'])}, {state}, ok)"
        if name == "realized_vol":
            return f"RealizedVolAt(shift, {params['n']}, ok)"
        if name == "atr_pct_rank":
            return f"AtrPctRankAt(shift, {params['n']}, {params['lookback']}, ok)"
        if name == "range_compression":
            return f"RangeCompressionAt(shift, {params['n']}, ok)"
        if name == "swing_high":
            return f"SwingHighAt(shift, {params['left']}, {params['right']}, ok)"
        if name == "swing_low":
            return f"SwingLowAt(shift, {params['left']}, {params['right']}, ok)"
        if name == "session_return":
            return f"SessionReturnAt(shift, {params['start']}, {params['end']}, ok)"
        raise ExportError(f"bloque {name} no exportable: sin generador de valor")

    def _pattern_call(self, expr: dsl.Expr, name: str) -> str:
        params = _resolved_params(expr, name)
        if name == "bos_up":
            return f"BosUpAt(shift, {params['left']}, {params['right']})"
        if name == "bos_down":
            return f"BosDownAt(shift, {params['left']}, {params['right']})"
        if name == "choch_up":
            return f"ChochUpAt(shift, {params['left']}, {params['right']})"
        if name == "choch_down":
            return f"ChochDownAt(shift, {params['left']}, {params['right']})"
        if name == "engulfing":
            return "EngulfingAt(shift)"
        if name == "pin_bar":
            return f"PinBarAt(shift, {_fmt(params['ratio'])})"
        if name == "inside_bar":
            return "InsideBarAt(shift)"
        if name == "range_expansion":
            return f"RangeExpansionAt(shift, {params['n']}, {_fmt(params['mult'])})"
        if name in {"trending", "ranging"}:
            state = self._state("adx", {"n": int(params["n"])})
            comparator = ">" if name == "trending" else "<"
            return (
                f"(AdxAt({state}, shift, _ok) {comparator} {_fmt(params['threshold'])} "
                "&& _ok)"
            )
        if name in {"vol_high", "vol_low"}:
            comparator = ">" if name == "vol_high" else "<"
            return (
                f"(AtrPctRankAt(shift, {params['n']}, {params['lookback']}, _ok) "
                f"{comparator} {_fmt(params['pct'])} && _ok)"
            )
        raise ExportError(f"bloque {name} no exportable: sin generador booleano")

    def _bool(self, expr: dsl.Expr) -> str:
        key = json.dumps(expr.model_dump(mode="json", exclude_none=True), sort_keys=True)
        cached = self.bool_names.get(key)
        if cached is not None:
            return cached
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        name = f"B_{digest}"
        kind = expr.kind
        body: list[str] = [f"bool {name}(const int shift)", "{", "   bool _ok = false;"]
        if kind == "and":
            calls = " && ".join(f"{self._bool(child)}(shift)" for child in expr.args)
            body.append(f"   return {calls};")
        elif kind == "or":
            calls = " || ".join(f"{self._bool(child)}(shift)" for child in expr.args)
            body.append(f"   return {calls};")
        elif kind == "not":
            body.append(f"   return !{self._bool(expr.args[0])}(shift);")
        elif kind in {"gt", "lt", "ge", "le", "between"}:
            left_name = self._value(expr.left) if expr.left is not None else None
            if left_name is None:
                raise ExportError(f"{kind} sin operando izquierdo")
            if kind == "between":
                if expr.low is None or expr.high is None:
                    raise ExportError("between sin low/high")
                body.append(f"   double left = {left_name}(shift, _ok);")
                body.append("   if(!_ok) return false;")
                body.append(f"   return left >= {_fmt(float(expr.low))} && left <= {_fmt(float(expr.high))};")
            else:
                if expr.right is None:
                    raise ExportError(f"{kind} sin operando derecho")
                right_name = self._value(expr.right)
                operator = {"gt": ">", "lt": "<", "ge": ">=", "le": "<="}[kind]
                body.append(f"   double left = {left_name}(shift, _ok);")
                body.append("   if(!_ok) return false;")
                body.append(f"   double right = {right_name}(shift, _ok);")
                body.append("   if(!_ok) return false;")
                body.append(f"   return left {operator} right;")
        elif kind in {"cross_up", "cross_down"}:
            if expr.left is None or expr.right is None:
                raise ExportError(f"{kind} sin operandos")
            for side in (expr.left, expr.right):
                if side.kind not in {"const", "price", "level", "indicator"}:
                    raise ExportError("cross sobre un nodo booleano no exportable")
            left_name = self._value(expr.left)
            right_name = self._value(expr.right)
            if kind == "cross_up":
                compare_now, compare_prev = ">", "<="
            else:
                compare_now, compare_prev = "<", ">="
            body.append("   bool ok0 = false, ok1 = false;")
            body.append(f"   double l0 = {left_name}(shift, ok0);")
            body.append("   double r0 = 0.0;")
            body.append("   if(!ok0) return false;")
            body.append(f"   r0 = {right_name}(shift, ok0);")
            body.append("   if(!ok0) return false;")
            body.append("   if(shift + 1 >= Bars(_Symbol, _Period)) return false;")
            body.append(f"   double l1 = {left_name}(shift + 1, ok1);")
            body.append("   double r1 = 0.0;")
            body.append("   if(!ok1) return false;")
            body.append(f"   r1 = {right_name}(shift + 1, ok1);")
            body.append("   if(!ok1) return false;")
            body.append(f"   return (l0 {compare_now} r0) && (l1 {compare_prev} r1);")
        elif kind == "held_for":
            child = self._bool(expr.args[0])
            window = int(expr.n or 1)
            body.append(f"   for(int k = 0; k < {window}; k++)")
            body.append("   {")
            body.append("      if(shift + k >= Bars(_Symbol, _Period)) return false;")
            body.append(f"      if(!{child}(shift + k)) return false;")
            body.append("   }")
            body.append("   return true;")
        elif kind == "within_bars":
            child = self._bool(expr.args[0])
            window = int(expr.n or 1)
            body.append(f"   for(int k = 0; k < {window}; k++)")
            body.append("   {")
            body.append("      if(shift + k >= Bars(_Symbol, _Period)) break;")
            body.append(f"      if({child}(shift + k)) return true;")
            body.append("   }")
            body.append("   return false;")
        elif kind == "time_between":
            start = str(expr.start or "")
            end = str(expr.end or "")
            start_min = _hhmm(start)
            end_min = _hhmm(end)
            body.append("   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;")
            body.append("   datetime ny = ServerToNy(iTime(_Symbol, _Period, shift));")
            body.append("   int minute = NyMinute(ny);")
            if start_min < end_min:
                body.append(f"   return minute >= {start_min} && minute < {end_min};")
            else:
                body.append(f"   return minute >= {start_min} || minute < {end_min};")
        elif kind == "weekday_in":
            days = sorted({_WEEKDAY_MQL5[str(day).lower()] for day in expr.days})
            test = " || ".join(f"dow == {day}" for day in days)
            body.append("   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;")
            body.append("   int dow = TimeDayOfWeek(ServerToNy(iTime(_Symbol, _Period, shift)));")
            body.append(f"   return {test};")
        elif kind == "pattern":
            block_name = str(expr.pattern)
            _require_exportable(block_name)
            self.blocks.add(block_name)
            call = self._pattern_call(expr, block_name)
            body.append(f"   return {call};")
        elif kind == "regime":
            block_name = str(expr.regime)
            _require_exportable(block_name)
            self.blocks.add(block_name)
            call = self._pattern_call(expr, block_name)
            body.append(f"   return {call};")
        elif kind == "htf":
            raise ExportError("nodo htf no exportable: la rejilla 17:00 NY no coincide con la del servidor")
        else:
            raise ExportError(f"nodo booleano no exportable: {kind}")
        body.append("}")
        self._emit("\n".join(body))
        self.bool_names[key] = name
        return name

    # -- ensamblado ------------------------------------------------------
    def state_code(self) -> str:
        lines: list[str] = []
        for name, kind, params in self.states:
            if kind == "ema":
                lines.append(f"EmaState {name};")
            else:
                lines.append(f"AdxState {name};")
        return "\n".join(lines)

    def init_code(self) -> str:
        lines = ["void InitIndicators()", "{"]
        for name, kind, params in self.states:
            if kind == "ema":
                lines.append(f"   EmaReset({name}, {int(params['span'])});")
            else:
                lines.append(f"   AdxReset({name}, {int(params['n'])});")
        lines.append("}")
        return "\n".join(lines)

    def update_code(self) -> str:
        lines = ["void UpdateIndicatorsAt(const int shift)", "{"]
        for name, kind, _params in self.states:
            if kind == "ema":
                lines.append(f"   EmaAppend({name}, iClose(_Symbol, _Period, shift));")
            else:
                lines.append(f"   AdxAppend({name}, shift);")
        lines.append("}")
        return "\n".join(lines)


def _hhmm(value: str) -> int:
    text = str(value or "").strip()
    if len(text) != 5 or text[2] != ":":
        raise ExportError(f"hora invalida: {value!r}")
    return int(text[:2]) * 60 + int(text[3:])


# ---------------------------------------------------------------------------
# Plantilla MQL5 fija
# ---------------------------------------------------------------------------

_MQL5_PRELUDE = r"""
struct EmaState
{
   int    span;
   double alpha;
   int    count;
   int    size;
   double value;
   double hist[];
};

void EmaReset(EmaState &s, const int span)
{
   s.span = span;
   s.alpha = 2.0 / (span + 1.0);
   s.count = 0;
   s.size = 0;
   s.value = 0.0;
   ArrayResize(s.hist, 0);
}

void EmaAppend(EmaState &s, const double price)
{
   s.count++;
   if(s.count == 1) s.value = price;
   else s.value = (1.0 - s.alpha) * s.value + s.alpha * price;
   if(s.size >= ArraySize(s.hist)) ArrayResize(s.hist, s.size + 4096);
   s.hist[s.size] = (s.count >= s.span) ? s.value : EMPTY_VALUE;
   s.size++;
}

double EmaAt(EmaState &s, const int shift, bool &ok)
{
   int index = s.size - shift;
   if(index < 0 || index >= s.size) { ok = false; return 0.0; }
   double value = s.hist[index];
   if(value == EMPTY_VALUE) { ok = false; return 0.0; }
   ok = true;
   return value;
}

struct AdxState
{
   int    n;
   double alpha;
   int    count;
   double atr;
   double plus;
   double minus;
   bool   has_dx;
   int    dx_last;
   int    dx_count;
   double dx_ewm;
   int    size;
   double hist[];
};

void AdxReset(AdxState &s, const int n)
{
   s.n = n;
   s.alpha = 1.0 / (double)n;
   s.count = 0;
   s.atr = 0.0;
   s.plus = 0.0;
   s.minus = 0.0;
   s.has_dx = false;
   s.dx_last = -1;
   s.dx_count = 0;
   s.dx_ewm = 0.0;
   s.size = 0;
   ArrayResize(s.hist, 0);
}

void AdxAppend(AdxState &s, const int shift)
{
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double tr = high - low;
   double up = 0.0;
   double down = 0.0;
   if(s.count > 0)
   {
      double prev_high = iHigh(_Symbol, _Period, shift + 1);
      double prev_low = iLow(_Symbol, _Period, shift + 1);
      double prev_close = iClose(_Symbol, _Period, shift + 1);
      up = high - prev_high;
      down = prev_low - low;
      tr = MathMax(tr, MathMax(MathAbs(high - prev_close), MathAbs(low - prev_close)));
   }
   double plus_dm = (up > down && up > 0.0) ? up : 0.0;
   double minus_dm = (down > up && down > 0.0) ? down : 0.0;
   if(s.count == 0)
   {
      s.atr = tr;
      s.plus = plus_dm;
      s.minus = minus_dm;
   }
   else
   {
      s.atr = (1.0 - s.alpha) * s.atr + s.alpha * tr;
      s.plus = (1.0 - s.alpha) * s.plus + s.alpha * plus_dm;
      s.minus = (1.0 - s.alpha) * s.minus + s.alpha * minus_dm;
   }
   double value = EMPTY_VALUE;
   int index = s.count;
   if(index >= s.n - 1 && s.atr != 0.0)
   {
      double plus = s.plus / s.atr;
      double minus = s.minus / s.atr;
      double denominator = plus + minus;
      if(denominator != 0.0)
      {
         double dx = MathAbs(plus - minus) / denominator * 100.0;
         if(!s.has_dx)
         {
            s.dx_ewm = dx;
            s.has_dx = true;
            s.dx_count = 1;
         }
         else
         {
            int gap = index - s.dx_last;
            double weight = 1.0 - MathPow(1.0 - s.alpha, (double)gap);
            s.dx_ewm = (1.0 - weight) * s.dx_ewm + weight * dx;
            s.dx_count++;
         }
         s.dx_last = index;
         if(s.dx_count >= s.n) value = s.dx_ewm;
      }
   }
   if(s.size >= ArraySize(s.hist)) ArrayResize(s.hist, s.size + 4096);
   s.hist[s.size] = value;
   s.size++;
   s.count++;
}

double AdxAt(AdxState &s, const int shift, bool &ok)
{
   int index = s.size - shift;
   if(index < 0 || index >= s.size) { ok = false; return 0.0; }
   double value = s.hist[index];
   if(value == EMPTY_VALUE) { ok = false; return 0.0; }
   ok = true;
   return value;
}

int NyOffsetSeconds(const datetime utc)
{
   MqlDateTime t;
   TimeToStruct(utc, t);
   int year = t.year;
   MqlDateTime a;
   a.year = year; a.mon = 3; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
   a.day_of_week = 0; a.day_of_year = 0;
   datetime first = StructToTime(a);
   int weekday = TimeDayOfWeek(first);
   int sunday = 1 + ((7 - weekday) % 7);
   datetime dst_start;
   datetime dst_end;
   if(year <= 2006)
   {
      a.mon = 4; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday;
      a.hour = 7;
      dst_start = StructToTime(a);
      a.mon = 10; a.day = 31; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      datetime last = StructToTime(a);
      weekday = TimeDayOfWeek(last);
      a.day = 31 - weekday;
      a.hour = 6;
      dst_end = StructToTime(a);
   }
   else
   {
      a.mon = 3; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday + 7;
      a.hour = 7;
      dst_start = StructToTime(a);
      a.mon = 11; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday;
      a.hour = 6;
      dst_end = StructToTime(a);
   }
   if(utc >= dst_start && utc < dst_end) return -4 * 3600;
   return -5 * 3600;
}

datetime ServerToUtc(const datetime server)
{
   long value = (long)server - (long)InpServerUtcOffsetMinutes * 60;
   return (datetime)value;
}

datetime ServerToNy(const datetime server)
{
   datetime utc = ServerToUtc(server);
   long value = (long)utc + (long)NyOffsetSeconds(utc);
   return (datetime)value;
}

int NyMinute(const datetime ny)
{
   MqlDateTime t;
   TimeToStruct(ny, t);
   return t.hour * 60 + t.min;
}

int NyDateKey(const datetime ny)
{
   MqlDateTime t;
   TimeToStruct(ny, t);
   return t.year * 10000 + t.mon * 100 + t.day;
}

bool InSession(const datetime server)
{
   int minute = NyMinute(ServerToNy(server));
   if(SESSION_START < SESSION_END) return (minute >= SESSION_START && minute < SESSION_END);
   return (minute >= SESSION_START || minute < SESSION_END);
}

bool InEntryWindow(const datetime server)
{
   int minute = NyMinute(ServerToNy(server));
   if(SESSION_START < SESSION_END) return (minute >= SESSION_START && minute <= SESSION_END);
   return (minute >= SESSION_START || minute <= SESSION_END);
}

bool IsTradingWeekday(const datetime server)
{
   int dow = TimeDayOfWeek(ServerToNy(server));
   return WEEKDAY_TEST;
}

int SessionDayKey(const datetime server)
{
   datetime ny = ServerToNy(server);
   int minute = NyMinute(ny);
   int key = NyDateKey(ny);
   if(SESSION_START > SESSION_END && minute < SESSION_END)
   {
      key = NyDateKey(ny - (datetime)86400);
   }
   return key;
}

bool FlatFlag(const datetime server)
{
   datetime ny = ServerToNy(server);
   int minute = NyMinute(ny);
   int relative = (minute - SESSION_START + 1440) % 1440;
   int duration = (MANAGE_END - SESSION_START + 1440) % 1440;
   if(duration == 0) duration = 1440;
   int flat_relative = (FLAT_AT - SESSION_START + 1440) % 1440;
   return (relative >= flat_relative && relative <= duration);
}

bool HasBars(const int shift, const int count)
{
   if(shift < 0 || count <= 0) return false;
   return (shift + count <= Bars(_Symbol, _Period));
}

double TrAt(const int shift)
{
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double value = high - low;
   if(shift + 1 < Bars(_Symbol, _Period))
   {
      double prev_close = iClose(_Symbol, _Period, shift + 1);
      value = MathMax(value, MathMax(MathAbs(high - prev_close), MathAbs(low - prev_close)));
   }
   return value;
}

double SmaAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += iClose(_Symbol, _Period, shift + k);
   ok = true;
   return sum / (double)n;
}

double RsiAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n + 1)) { ok = false; return 0.0; }
   double gain = 0.0;
   double loss = 0.0;
   for(int k = 0; k < n; k++)
   {
      double delta = iClose(_Symbol, _Period, shift + k) - iClose(_Symbol, _Period, shift + k + 1);
      if(delta > 0.0) gain += delta;
      else loss -= delta;
   }
   gain /= (double)n;
   loss /= (double)n;
   if(loss == 0.0) { ok = false; return 0.0; }
   ok = true;
   return 100.0 - 100.0 / (1.0 + gain / loss);
}

double AtrAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += TrAt(shift + k);
   ok = true;
   return sum / (double)n;
}

double ZScoreAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += iClose(_Symbol, _Period, shift + k);
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int k = 0; k < n; k++)
   {
      double diff = iClose(_Symbol, _Period, shift + k) - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   if(variance <= 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - mean) / MathSqrt(variance);
}

double MacdAt(EmaState &fast, EmaState &slow, const int shift, bool &ok)
{
   bool fast_ok = false;
   bool slow_ok = false;
   double fast_value = EmaAt(fast, shift, fast_ok);
   double slow_value = EmaAt(slow, shift, slow_ok);
   if(!fast_ok || !slow_ok) { ok = false; return 0.0; }
   ok = true;
   return fast_value - slow_value;
}

double BollingerPctAt(const int shift, const int n, const double k, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int j = 0; j < n; j++) sum += iClose(_Symbol, _Period, shift + j);
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int j = 0; j < n; j++)
   {
      double diff = iClose(_Symbol, _Period, shift + j) - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   double width = 2.0 * k * MathSqrt(variance);
   if(width == 0.0) { ok = false; return 0.0; }
   double lower = mean - k * MathSqrt(variance);
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double StochasticAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double highest = -DBL_MAX;
   double lowest = DBL_MAX;
   for(int j = 0; j < n; j++)
   {
      highest = MathMax(highest, iHigh(_Symbol, _Period, shift + j));
      lowest = MathMin(lowest, iLow(_Symbol, _Period, shift + j));
   }
   if(highest == lowest) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lowest) / (highest - lowest) * 100.0;
}

double CciAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double values[];
   ArrayResize(values, n);
   double sum = 0.0;
   for(int j = 0; j < n; j++)
   {
      double typical = (iHigh(_Symbol, _Period, shift + j) + iLow(_Symbol, _Period, shift + j) + iClose(_Symbol, _Period, shift + j)) / 3.0;
      values[j] = typical;
      sum += typical;
   }
   double mean = sum / (double)n;
   double deviation = 0.0;
   for(int j = 0; j < n; j++) deviation += MathAbs(values[j] - mean);
   deviation /= (double)n;
   if(deviation == 0.0) { ok = false; return 0.0; }
   double current = (iHigh(_Symbol, _Period, shift) + iLow(_Symbol, _Period, shift) + iClose(_Symbol, _Period, shift)) / 3.0;
   ok = true;
   return (current - mean) / (0.015 * deviation);
}

double DonchianPosAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double upper = -DBL_MAX;
   double lower = DBL_MAX;
   for(int j = 0; j < n; j++)
   {
      upper = MathMax(upper, iHigh(_Symbol, _Period, shift + j));
      lower = MathMin(lower, iLow(_Symbol, _Period, shift + j));
   }
   double width = upper - lower;
   if(width == 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double KeltnerPosAt(const int shift, const int n, const double mult, EmaState &ema, bool &ok)
{
   bool ema_ok = false;
   bool atr_ok = false;
   double middle = EmaAt(ema, shift, ema_ok);
   double atr = AtrAt(shift, n, atr_ok);
   if(!ema_ok || !atr_ok) { ok = false; return 0.0; }
   double width = 2.0 * mult * atr;
   if(width == 0.0) { ok = false; return 0.0; }
   double lower = middle - mult * atr;
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double RealizedVolAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n + 1)) { ok = false; return 0.0; }
   double returns[];
   ArrayResize(returns, n);
   double sum = 0.0;
   for(int j = 0; j < n; j++)
   {
      double current = iClose(_Symbol, _Period, shift + j);
      double previous = iClose(_Symbol, _Period, shift + j + 1);
      double value = (current - previous) / previous;
      returns[j] = value;
      sum += value;
   }
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int j = 0; j < n; j++)
   {
      double diff = returns[j] - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   ok = true;
   return MathSqrt(variance);
}

double AtrPctRankAt(const int shift, const int n, const int lookback, bool &ok)
{
   ok = false;
   if(!HasBars(shift, n)) return 0.0;
   int minimum = (lookback / 2 > 10) ? lookback / 2 : 10;
   double current_atr = AtrAt(shift, n, ok);
   if(!ok) return 0.0;
   double current_close = iClose(_Symbol, _Period, shift);
   if(current_close <= 0.0) return 0.0;
   double current = current_atr / current_close;
   double window_sum = 0.0;
   for(int j = 0; j < n; j++) window_sum += TrAt(shift + j);
   int count = 0;
   int less = 0;
   int equal = 0;
   for(int k = 0; k < lookback; k++)
   {
      if(shift + k + n - 1 >= Bars(_Symbol, _Period)) break;
      double close_k = iClose(_Symbol, _Period, shift + k);
      if(close_k > 0.0)
      {
         double value = (window_sum / (double)n) / close_k;
         count++;
         if(value < current) less++;
         else if(value == current) equal++;
      }
      if(shift + k + n < Bars(_Symbol, _Period))
      {
         window_sum += TrAt(shift + k + n) - TrAt(shift + k);
      }
   }
   if(count < minimum || count == 0) return 0.0;
   double rank = (double)less + ((double)equal + 1.0) / 2.0;
   ok = true;
   return rank / (double)count;
}

double RangeCompressionAt(const int shift, const int n, bool &ok)
{
   bool atr_ok = false;
   double atr = AtrAt(shift, n, atr_ok);
   if(!atr_ok || atr == 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift)) / atr;
}

double SwingHighAt(const int shift, const int left, const int right, bool &ok)
{
   int pivot = shift + right;
   if(pivot + left >= Bars(_Symbol, _Period)) { ok = false; return 0.0; }
   double value = iHigh(_Symbol, _Period, pivot);
   for(int k = -left; k <= right; k++)
   {
      if(iHigh(_Symbol, _Period, pivot - k) > value) { ok = false; return 0.0; }
   }
   ok = true;
   return value;
}

double SwingLowAt(const int shift, const int left, const int right, bool &ok)
{
   int pivot = shift + right;
   if(pivot + left >= Bars(_Symbol, _Period)) { ok = false; return 0.0; }
   double value = iLow(_Symbol, _Period, pivot);
   for(int k = -left; k <= right; k++)
   {
      if(iLow(_Symbol, _Period, pivot - k) < value) { ok = false; return 0.0; }
   }
   ok = true;
   return value;
}

bool BosUpAt(const int shift, const int left, const int right)
{
   for(int k = 0; k < InpPivotScanBars; k++)
   {
      bool ok = false;
      double level = SwingHighAt(shift + k, left, right, ok);
      if(ok) return (iClose(_Symbol, _Period, shift) > level);
      if(shift + k + right + left >= Bars(_Symbol, _Period)) break;
   }
   return false;
}

bool BosDownAt(const int shift, const int left, const int right)
{
   for(int k = 0; k < InpPivotScanBars; k++)
   {
      bool ok = false;
      double level = SwingLowAt(shift + k, left, right, ok);
      if(ok) return (iClose(_Symbol, _Period, shift) < level);
      if(shift + k + right + left >= Bars(_Symbol, _Period)) break;
   }
   return false;
}

bool ChochUpAt(const int shift, const int left, const int right)
{
   bool previous = false;
   if(shift + 1 < Bars(_Symbol, _Period)) previous = BosUpAt(shift + 1, left, right);
   return BosUpAt(shift, left, right) && !previous;
}

bool ChochDownAt(const int shift, const int left, const int right)
{
   bool previous = false;
   if(shift + 1 < Bars(_Symbol, _Period)) previous = BosDownAt(shift + 1, left, right);
   return BosDownAt(shift, left, right) && !previous;
}

bool EngulfingAt(const int shift)
{
   if(shift + 1 >= Bars(_Symbol, _Period)) return false;
   double open_ = iOpen(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double previous_open = iOpen(_Symbol, _Period, shift + 1);
   double previous_close = iClose(_Symbol, _Period, shift + 1);
   bool bullish = (close > open_) && (previous_close < previous_open) && (open_ <= previous_close) && (close >= previous_open);
   bool bearish = (close < open_) && (previous_close > previous_open) && (open_ >= previous_close) && (close <= previous_open);
   return bullish || bearish;
}

bool PinBarAt(const int shift, const double ratio)
{
   double open_ = iOpen(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double body = MathAbs(close - open_);
   double upper = high - MathMax(open_, close);
   double lower = MathMin(open_, close) - low;
   return ((lower > ratio * body) && (lower > upper)) || ((upper > ratio * body) && (upper > lower));
}

bool InsideBarAt(const int shift)
{
   if(shift + 1 >= Bars(_Symbol, _Period)) return false;
   return (iHigh(_Symbol, _Period, shift) < iHigh(_Symbol, _Period, shift + 1)) &&
          (iLow(_Symbol, _Period, shift) > iLow(_Symbol, _Period, shift + 1));
}

bool RangeExpansionAt(const int shift, const int n, const double mult)
{
   if(!HasBars(shift, n + 1)) return false;
   double sum = 0.0;
   for(int k = 1; k <= n; k++) sum += iHigh(_Symbol, _Period, shift + k) - iLow(_Symbol, _Period, shift + k);
   double mean = sum / (double)n;
   double current = iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift);
   return current > mult * mean;
}

double PrevSessionLevelAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!InSession(time)) return 0.0;
   int key = SessionDayKey(time);
   int total = Bars(_Symbol, _Period);
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   for(int k = shift + 1; k < total; k++)
   {
      datetime other = iTime(_Symbol, _Period, k);
      if(!InSession(other)) continue;
      int other_key = SessionDayKey(other);
      if(other_key >= key) continue;
      int target = other_key;
      for(; k < total; k++)
      {
         datetime stamp = iTime(_Symbol, _Period, k);
         if(!InSession(stamp) || SessionDayKey(stamp) != target) break;
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
      break;
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double PrevDayLevelAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   int key = NyDateKey(ServerToNy(iTime(_Symbol, _Period, shift)));
   int total = Bars(_Symbol, _Period);
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   for(int k = shift + 1; k < total; k++)
   {
      int other_key = NyDateKey(ServerToNy(iTime(_Symbol, _Period, k)));
      if(other_key >= key) continue;
      int target = other_key;
      for(; k < total; k++)
      {
         if(NyDateKey(ServerToNy(iTime(_Symbol, _Period, k))) != target) break;
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
      break;
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double OpeningRangeAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!InSession(time)) return 0.0;
   int key = SessionDayKey(time);
   int relative = (NyMinute(ServerToNy(time)) - SESSION_START + 1440) % 1440;
   if(relative < OR_MINUTES) return 0.0;
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   int total = Bars(_Symbol, _Period);
   for(int k = shift; k < total; k++)
   {
      datetime stamp = iTime(_Symbol, _Period, k);
      if(!InSession(stamp) || SessionDayKey(stamp) != key) break;
      int item_relative = (NyMinute(ServerToNy(stamp)) - SESSION_START + 1440) % 1440;
      if(item_relative < OR_MINUTES)
      {
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double DonchianLevelAt(const int shift, const int n, const bool want_high, bool &ok)
{
   if(!HasBars(shift + 1, n)) { ok = false; return 0.0; }
   double value = want_high ? -DBL_MAX : DBL_MAX;
   for(int k = 1; k <= n; k++)
   {
      double item = want_high ? iHigh(_Symbol, _Period, shift + k) : iLow(_Symbol, _Period, shift + k);
      value = want_high ? MathMax(value, item) : MathMin(value, item);
   }
   ok = true;
   return value;
}

double SessionReturnAt(const int shift, const int start_minute, const int end_minute, bool &ok)
{
   ok = false;
   if(start_minute >= end_minute) return 0.0;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   int total = Bars(_Symbol, _Period);
   datetime time = iTime(_Symbol, _Period, shift);
   int day_key = NyDateKey(ServerToNy(time));
   int oldest = shift;
   while(oldest + 1 < total)
   {
      if(NyDateKey(ServerToNy(iTime(_Symbol, _Period, oldest + 1))) != day_key) break;
      oldest++;
   }
   int start_pos = -1;
   int end_pos = -1;
   int start_shift = -1;
   int end_shift = -1;
   int position = 0;
   for(int k = oldest; k >= 0; k--)
   {
      datetime stamp = iTime(_Symbol, _Period, k);
      if(NyDateKey(ServerToNy(stamp)) != day_key) break;
      int minute = NyMinute(ServerToNy(stamp));
      if(start_pos < 0 && minute == start_minute) { start_pos = position; start_shift = k; }
      if(end_pos < 0 && minute == end_minute) { end_pos = position; end_shift = k; }
      position++;
   }
   if(start_pos < 0 || end_pos < 0 || end_pos <= start_pos) return 0.0;
   int newest = oldest - (position - 1);
   if(!(shift < end_shift && shift >= newest)) return 0.0;
   double begin = iOpen(_Symbol, _Period, start_shift);
   double finish = iClose(_Symbol, _Period, end_shift);
   if(begin <= 0.0) return 0.0;
   ok = true;
   return finish / begin - 1.0;
}
"""


_TRADING_RUNTIME = r"""
long g_magic = 0;
datetime g_last_bar = 0;
datetime g_entry_bar = 0;
double g_entry_price = 0.0;
double g_entry_risk = 0.0;
int g_day_key = 0;
int g_day_trades = 0;
double g_day_start_equity = 0.0;
double g_initial_equity = 0.0;
bool g_total_blocked = false;
int g_trace = INVALID_HANDLE;

bool FindPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong current = PositionGetTicket(i);
      if(current == 0) continue;
      if(!PositionSelectByTicket(current)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      ticket = current;
      return true;
   }
   return false;
}

void CloseOurPosition()
{
   ulong ticket = 0;
   if(FindPosition(ticket)) trade.PositionClose(ticket);
}

int BarsHeld()
{
   if(g_entry_bar == 0) return -1;
   int elapsed = iBarShift(_Symbol, _Period, g_entry_bar, false);
   return elapsed - 1;
}

void UpdateDayState(const datetime server)
{
   int key = SessionDayKey(server);
   if(key != g_day_key)
   {
      g_day_key = key;
      g_day_trades = 0;
      g_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   }
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpMaxLossLimit > 0.0 && g_initial_equity > 0.0 && equity <= g_initial_equity - InpMaxLossLimit)
   {
      g_total_blocked = true;
   }
}

bool RiskAllowsEntry(const datetime server)
{
   UpdateDayState(server);
   if(g_total_blocked) return false;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpDailyLossLimit > 0.0 && g_day_start_equity > 0.0 &&
      equity <= g_day_start_equity - InpDailyLossLimit) return false;
   if(MAX_TRADES_PER_DAY > 0 && g_day_trades >= MAX_TRADES_PER_DAY) return false;
   return true;
}

bool CooldownAllows()
{
   if(COOLDOWN_BARS <= 0 || g_entry_bar == 0) return true;
   return iBarShift(_Symbol, _Period, g_entry_bar, false) >= COOLDOWN_BARS;
}

bool EntryWindowAllows(const int shift)
{
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!IsTradingWeekday(time)) return false;
   if(!InEntryWindow(time)) return false;
   if(FlatFlag(time)) return false;
   return true;
}

bool BuildExit(const int signal_shift, const int side, const double entry,
               double &stop, double &target, bool &has_target, double &risk)
{
   double distance = 0.0;
   stop = 0.0;
   target = 0.0;
   has_target = false;
   risk = 0.0;
   if(STOP_KIND == 0)
   {
      bool ok = false;
      double atr = AtrAt(signal_shift, STOP_N, ok);
      if(!ok || atr <= 0.0) return false;
      distance = STOP_MULT * atr;
      stop = entry - side * distance;
   }
   else if(STOP_KIND == 1)
   {
      distance = entry * STOP_MULT / 100.0;
      stop = entry - side * distance;
   }
   else
   {
      stop = STOP_FIXED;
      distance = (entry - stop) * side;
   }
   if(distance <= 0.0 || distance >= DBL_MAX) return false;
   if(TARGET_KIND != 3)
   {
      if(TARGET_KIND == 0) target = entry + side * TARGET_RR * distance;
      else if(TARGET_KIND == 1) target = entry + side * entry * TARGET_PCT / 100.0;
      else target = TARGET_FIXED;
      if((side > 0 && target <= entry) || (side < 0 && target >= entry)) return false;
      has_target = true;
   }
   risk = distance;
   return true;
}

double CalcLots(const double risk_price)
{
   if(risk_price <= 0.0) return 0.0;
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_value <= 0.0 || tick_size <= 0.0) return 0.0;
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPerTradePct / 100.0;
   if(risk_money <= 0.0) return 0.0;
   double per_lot = risk_price / tick_size * tick_value;
   if(per_lot <= 0.0) return 0.0;
   double lots = risk_money / per_lot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minimum = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maximum = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step > 0.0) lots = MathFloor(lots / step) * step;
   lots = MathMin(lots, maximum);
   if(lots < minimum) return 0.0;
   return lots;
}

void TraceEntry(const datetime server_time, const int side, const double entry,
                const double stop, const bool has_target, const double target)
{
   if(g_trace == INVALID_HANDLE) return;
   datetime utc = ServerToUtc(server_time);
   MqlDateTime t;
   TimeToStruct(utc, t);
   string stamp = StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                               t.year, t.mon, t.day, t.hour, t.min, t.sec);
   string side_text = (side > 0) ? "long" : "short";
   string target_text = has_target ? DoubleToString(target, 8) : "";
   FileWriteString(g_trace, stamp + "," + side_text + "," + DoubleToString(entry, 8) +
                   "," + DoubleToString(stop, 8) + "," + target_text + "\n");
}

void UpdateProtection(const int side, const ulong ticket)
{
   if(g_entry_risk <= 0.0) return;
   double close = iClose(_Symbol, _Period, 1);
   double current_stop = PositionGetDouble(POSITION_SL);
   double current_target = PositionGetDouble(POSITION_TP);
   double new_stop = current_stop;
   if(BE_AT_R > 0.0)
   {
      double current_r = (close - g_entry_price) * side / g_entry_risk;
      if(current_r >= BE_AT_R)
      {
         if(side > 0 && (new_stop == 0.0 || g_entry_price > new_stop)) new_stop = g_entry_price;
         if(side < 0 && (new_stop == 0.0 || g_entry_price < new_stop)) new_stop = g_entry_price;
      }
   }
   if(TRAIL_MULT > 0.0)
   {
      bool ok = false;
      double atr = AtrAt(1, TRAIL_N, ok);
      if(ok && atr > 0.0)
      {
         double level = close - side * TRAIL_MULT * atr;
         if(side > 0 && (new_stop == 0.0 || level > new_stop)) new_stop = level;
         if(side < 0 && (new_stop == 0.0 || level < new_stop)) new_stop = level;
      }
   }
   if(new_stop == current_stop || new_stop <= 0.0) return;
   double normalized = NormalizeDouble(new_stop, _Digits);
   if(normalized == NormalizeDouble(current_stop, _Digits)) return;
   trade.PositionModify(ticket, normalized, current_target);
}

void OnNewBar(const datetime previous)
{
   int shift = 1;
   if(shift >= Bars(_Symbol, _Period)) return;
   int elapsed = 1;
   if(previous != 0)
   {
      elapsed = iBarShift(_Symbol, _Period, previous, false);
      if(elapsed < 1) elapsed = 1;
   }
   for(int missed = elapsed; missed >= 1; missed--) UpdateIndicatorsAt(missed);
   bool long_signal = LongSignal(shift);
   bool short_signal = ShortSignal(shift);
   datetime entry_time = iTime(_Symbol, _Period, 0);
   UpdateDayState(entry_time);
   ulong ticket = 0;
   bool has_position = FindPosition(ticket);
   if(has_position)
   {
      long position_type = PositionGetInteger(POSITION_TYPE);
      int side = (position_type == POSITION_TYPE_BUY) ? 1 : -1;
      if((side > 0 && short_signal) || (side < 0 && long_signal))
      {
         CloseOurPosition();
         has_position = false;
      }
      else if(FlatFlag(iTime(_Symbol, _Period, 1)))
      {
         CloseOurPosition();
         has_position = false;
      }
      else if(TIME_EXIT_BARS > 0 && BarsHeld() >= TIME_EXIT_BARS)
      {
         CloseOurPosition();
         has_position = false;
      }
      if(has_position) UpdateProtection(side, ticket);
   }
   if(has_position) return;
   int side = long_signal ? 1 : (short_signal ? -1 : 0);
   if(side == 0) return;
   if(!RiskAllowsEntry(entry_time)) return;
   if(!EntryWindowAllows(1) || !EntryWindowAllows(0)) return;
   if(!CooldownAllows()) return;
   double entry = iOpen(_Symbol, _Period, 0);
   double stop = 0.0;
   double target = 0.0;
   double risk = 0.0;
   bool has_target = false;
   if(!BuildExit(1, side, entry, stop, target, has_target, risk)) return;
   double lots = CalcLots(risk);
   if(lots <= 0.0) return;
   g_day_trades++;
   g_entry_bar = entry_time;
   g_entry_price = entry;
   g_entry_risk = risk;
   TraceEntry(entry_time, side, entry, stop, has_target, target);
   double normalized_stop = NormalizeDouble(stop, _Digits);
   double normalized_target = has_target ? NormalizeDouble(target, _Digits) : 0.0;
   if(side > 0) trade.Buy(lots, _Symbol, 0.0, normalized_stop, normalized_target, "F12a");
   else trade.Sell(lots, _Symbol, 0.0, normalized_stop, normalized_target, "F12a");
}
"""


def _mql5_source(
    strategy: dsl.Strategy,
    compiler: _MqlCompiler,
    *,
    header: str,
    magic: int,
    profile: _RiskProfile,
    weekdays: Sequence[int],
) -> str:
    session = strategy.session
    start = _hhmm(session.start)
    end = _hhmm(session.end)
    flat = _hhmm(session.flat_at)
    manage_end = max(end, flat)
    weekday_days = sorted({_WEEKDAY_MQL5[("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day]] for day in weekdays})
    weekday_test = " || ".join(f"dow == {day}" for day in weekday_days) or "false"
    stop = strategy.exit.stop
    stop_kind = {"atr": 0, "pct": 1, "fixed": 2}[stop.type]
    stop_mult = stop.mult if stop.type != "fixed" else 0.0
    if stop.type == "pct" and stop.value is not None:
        stop_mult = float(stop.value)
    stop_fixed = float(stop.value or 0.0)
    target = strategy.exit.target
    if target is None:
        target_kind = 3
        target_rr = 0.0
        target_pct = 0.0
        target_fixed = 0.0
    elif target.type == "rr":
        target_kind = 0
        target_rr = float(target.rr)
        target_pct = 0.0
        target_fixed = 0.0
    elif target.type == "pct":
        target_kind = 1
        target_rr = 0.0
        target_pct = float(target.value if target.value is not None else target.rr)
        target_fixed = 0.0
    else:
        target_kind = 2
        target_rr = 0.0
        target_pct = 0.0
        target_fixed = float(target.value or 0.0)
    breakeven = strategy.exit.breakeven or {}
    trailing = strategy.exit.trailing or {}
    be_at_r = float(breakeven.get("at_r", 0.0) or 0.0)
    trail_mult = float(trailing.get("atr_mult", trailing.get("mult", 0.0)) or 0.0)
    trail_n = int(trailing.get("n", 14))
    time_exit = specs.time_exit_bars(strategy) or 0
    cooldown = specs.cooldown_bars(strategy)
    warmup = max(
        _warmup_expr(strategy.long_entry),
        _warmup_expr(strategy.short_entry),
        minutes_to_bars(strategy.warmup_minutes or 0, strategy.timeframe),
    )
    long_name = compiler._bool(strategy.long_entry) if strategy.long_entry is not None else None
    short_name = compiler._bool(strategy.short_entry) if strategy.short_entry is not None else None
    long_body = f"   return {long_name}(shift);" if long_name else "   return false;"
    short_body = f"   return {short_name}(shift);" if short_name else "   return false;"
    init_code = compiler.init_code()
    update_code = compiler.update_code()
    state_code = compiler.state_code()
    prelude = _MQL5_PRELUDE.replace("WEEKDAY_TEST", weekday_test)
    constants = "\n".join(
        [
            f"const int SESSION_START = {start};",
            f"const int SESSION_END = {end};",
            f"const int FLAT_AT = {flat};",
            f"const int MANAGE_END = {manage_end};",
            f"const int OR_MINUTES = {int(session.or_minutes)};",
            f"const int MAX_TRADES_PER_DAY = {int(strategy.limits.max_trades_per_day)};",
            f"const int COOLDOWN_BARS = {int(cooldown)};",
            f"const int STOP_KIND = {stop_kind};",
            f"const double STOP_MULT = {_fmt(stop_mult)};",
            f"const double STOP_FIXED = {_fmt(stop_fixed)};",
            f"const int STOP_N = {int(stop.n)};",
            f"const int TARGET_KIND = {target_kind};",
            f"const double TARGET_RR = {_fmt(target_rr)};",
            f"const double TARGET_PCT = {_fmt(target_pct)};",
            f"const double TARGET_FIXED = {_fmt(target_fixed)};",
            f"const double BE_AT_R = {_fmt(be_at_r)};",
            f"const double TRAIL_MULT = {_fmt(trail_mult)};",
            f"const int TRAIL_N = {trail_n};",
            f"const int TIME_EXIT_BARS = {int(time_exit)};",
            f"const int WARMUP_BARS = {int(warmup)};",
        ]
    )
    inputs = "\n".join(
        [
            'input double InpRiskPerTradePct = %s;' % _fmt(profile.risk_pct),
            'input double InpDailyLossLimit = %s;' % _fmt(profile.daily_loss),
            'input double InpMaxLossLimit = %s;' % _fmt(profile.max_loss),
            'input long   InpMagic = %d;' % magic,
            'input int    InpServerUtcOffsetMinutes = 0;',
            'input int    InpSlippagePoints = 20;',
            'input int    InpPivotScanBars = 5000;',
            'input bool   InpEmitTrace = true;',
            'input string InpTraceFile = "%s_%s_%s_trace.csv";'
            % (_slug(strategy.instrument), strategy.timeframe, profile.account),
        ]
    )
    functions = "\n\n".join(compiler.functions)
    if compiler.states:
        backfill = [
            "   int total = Bars(_Symbol, _Period);",
            "   for(int shift = total - 1; shift >= 1; shift--) UpdateIndicatorsAt(shift);",
        ]
    else:
        backfill = ["   // sin indicadores con estado"]
    source = "\n".join(
        [
            header,
            "",
            '#include <Trade\\Trade.mqh>',
            "",
            'CTrade trade;',
            "",
            inputs,
            "",
            constants,
            "",
            prelude,
            "",
            state_code,
            "",
            init_code,
            "",
            update_code,
            "",
            functions,
            "",
            "bool LongSignal(const int shift)",
            "{",
            "   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;",
            "   if((Bars(_Symbol, _Period) - 1 - shift) < WARMUP_BARS) return false;",
            "   if(!InSession(iTime(_Symbol, _Period, shift))) return false;",
            long_body,
            "}",
            "",
            "bool ShortSignal(const int shift)",
            "{",
            "   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;",
            "   if((Bars(_Symbol, _Period) - 1 - shift) < WARMUP_BARS) return false;",
            "   if(!InSession(iTime(_Symbol, _Period, shift))) return false;",
            short_body,
            "}",
            "",
            _TRADING_RUNTIME,
            "",
            "int OnInit()",
            "{",
            "   g_magic = InpMagic;",
            "   trade.SetExpertMagicNumber((ulong)InpMagic);",
            "   trade.SetDeviationInPoints((ulong)InpSlippagePoints);",
            "   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);",
            "   g_day_start_equity = g_initial_equity;",
            "   datetime start_time = iTime(_Symbol, _Period, 0);",
            "   if(start_time > 0) g_day_key = SessionDayKey(start_time);",
            "   InitIndicators();",
            *backfill,
            "   if(InpEmitTrace)",
            "   {",
            "      g_trace = FileOpen(InpTraceFile, FILE_WRITE | FILE_TXT | FILE_ANSI);",
            "      if(g_trace != INVALID_HANDLE)",
            "         FileWriteString(g_trace, \"bar_time,side,entry,stop,target\\n\");",
            "   }",
            "   g_last_bar = iTime(_Symbol, _Period, 0);",
            "   return INIT_SUCCEEDED;",
            "}",
            "",
            "void OnDeinit(const int reason)",
            "{",
            "   if(g_trace != INVALID_HANDLE) FileClose(g_trace);",
            "}",
            "",
            "void OnTick()",
            "{",
            "   datetime current = iTime(_Symbol, _Period, 0);",
            "   if(current == g_last_bar) return;",
            "   datetime previous = g_last_bar;",
            "   g_last_bar = current;",
            "   OnNewBar(previous);",
            "}",
            "",
        ]
    )
    return source


def _header(
    strategy: dsl.Strategy,
    strategy_hash: str,
    template_name: str,
    template_version: str,
    magic: int,
    profile: _RiskProfile,
    weekdays: Sequence[int],
) -> str:
    session = strategy.session
    days = ",".join(str(int(day) + 1) for day in weekdays)
    lines = [
        "//+------------------------------------------------------------------+",
        "//| TradingLab 2.0 - Discovery Lab - EA exportado (determinista)     |",
        "//| Genoma (sha256): %s" % strategy_hash,
        "//| Plantilla: %s - version %s" % (template_name, template_version),
        "//| Exportador: %s" % EXPORTER_VERSION,
        "//| Simbolo: %s - TF: %s - Cuenta: %s - Firma: %s"
        % (strategy.instrument, strategy.timeframe, profile.account, profile.firm),
        "//| Magic: %d - Riesgo: %s%% - Perdida diaria: %s - Total: %s"
        % (magic, _fmt(profile.risk_pct), _fmt(profile.daily_loss), _fmt(profile.max_loss)),
        "//| Sizing DSL: %sR (evaluacion); el EA usa el riesgo del perfil.     |"
        % _fmt(strategy.sizing.risk_per_trade_r),
        "//| Sesion: %s-%s NY - flat %s - dias (1=lun): %s"
        % (session.start, session.end, session.flat_at, days),
        "//| BOS/CHOCH: pivote mas reciente dentro de InpPivotScanBars.       |",
        "//| Hora de barras: InpServerUtcOffsetMinutes = minutos del servidor  |",
        "//| por delante de UTC (0 = barras UTC; GMT+2 -> 120; GMT+3 -> 180). |",
        "//| Costes y fills intrabar: los aplica el broker, no el EA.          |",
        "//| Sin fechas ni rutas: la misma entrada produce los mismos bytes.   |",
        "//+------------------------------------------------------------------+",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Traza de paridad
# ---------------------------------------------------------------------------


class _ZeroCosts:
    """Coste cero solo para la traza de senales (no es un backtest)."""

    def __init__(self, market: str) -> None:
        self.market = market

    def label(self) -> str:
        return "sin coste (traza F12a)"

    def panel(self, bars: pd.DataFrame) -> CostPanel:
        zeros = np.zeros(len(bars), dtype=float)
        return CostPanel(
            entry_bps=zeros,
            stop_bps=zeros.copy(),
            target_bps=zeros.copy(),
            spread_bps=zeros.copy(),
        )


def trace_signals(
    strategy: dsl.Strategy | dict,
    bars: pd.DataFrame,
    *,
    weekdays: Sequence[int] | None = None,
) -> list[TraceRow]:
    """Traza de entradas que produce el DSL con fastbt sobre ``bars``."""

    model = _model(strategy)
    errors = dsl.validate(model)
    if errors:
        raise ExportError("estrategia invalida: " + "; ".join(errors))
    session_tz = dsl.resolved_session_tz(model)
    if session_tz != "America/New_York":
        raise ExportError(
            f"huso {session_tz} no exportable: el EA implementa America/New_York con DST"
        )
    signals = compile_signals(model, bars)
    exit_spec = specs.exit_spec_from_strategy(model)
    days = tuple(int(day) for day in (weekdays if weekdays is not None else range(5)))
    if any(day < 0 or day > 6 for day in days):
        raise ExportError(f"weekdays invalidos: {weekdays}")
    setup = type(
        "Setup",
        (),
        {
            "session_tz": session_tz,
            "weekdays": days,
        },
    )()
    limits = specs.run_limits_from_strategy(model, setup)
    result = run_fastbt(
        signals,
        bars,
        exit_spec,
        _ZeroCosts(model.market),
        limits,
        collect_metrics=False,
    )
    rows: list[TraceRow] = []
    for trade in result.trades:
        stamp = trade.entry_time.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append(
            TraceRow(
                bar_time=stamp,
                side=trade.side,
                entry=float(trade.entry_price),
                stop=float(trade.stop),
                target=None if trade.target is None else float(trade.target),
            )
        )
    return rows


def trace_csv(
    strategy: dsl.Strategy | dict,
    bars: pd.DataFrame,
    *,
    weekdays: Sequence[int] | None = None,
) -> str:
    lines = ["bar_time,side,entry,stop,target"]
    for row in trace_signals(strategy, bars, weekdays=weekdays):
        target = "" if row.target is None else f"{row.target:.8f}"
        lines.append(
            f"{row.bar_time},{row.side},{row.entry:.8f},{row.stop:.8f},{target}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Exportacion
# ---------------------------------------------------------------------------


def _load_spec(path: str | Path) -> tuple[dsl.Strategy, str | None, str | None, Sequence[int] | None]:
    target = Path(path)
    if not target.exists():
        raise ExportError(f"Sin datos: no existe la especificacion {target}")
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ExportError(f"YAML invalido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ExportError("la especificacion debe ser un mapa YAML")
    if "strategy" in raw:
        strategy_data = raw["strategy"]
        template = raw.get("template")
        account = raw.get("account")
        weekdays = raw.get("weekdays")
    elif "dsl" in raw:
        strategy_data = raw["dsl"]
        template = raw.get("template")
        account = raw.get("account")
        weekdays = raw.get("weekdays")
    else:
        strategy_data = raw
        template = raw.get("template") if isinstance(raw, dict) else None
        account = raw.get("account") if isinstance(raw, dict) else None
        weekdays = raw.get("weekdays") if isinstance(raw, dict) else None
        if isinstance(strategy_data, dict):
            strategy_data = {
                key: value
                for key, value in strategy_data.items()
                if key not in {"template", "account", "weekdays", "risk"}
            }
    if not isinstance(strategy_data, dict):
        raise ExportError("la especificacion no contiene una estrategia")
    model = _model(strategy_data)
    return model, (str(template) if template else None), (str(account).upper() if account else None), weekdays


def _write_text(path: Path, text: str) -> bytes:
    data = text.replace("\r\n", "\n").encode("utf-8")
    path.write_bytes(data)
    return data


def export_strategy(
    strategy: dsl.Strategy | dict,
    *,
    account_id: str,
    out_dir: str | Path = "reports/export/",
    template: str | None = None,
    daily_loss: float | None = None,
    max_loss: float | None = None,
    risk_pct: float | None = None,
    weekdays: Sequence[int] | None = None,
    bars: pd.DataFrame | None = None,
    write_trace: bool = False,
    stem: str | None = None,
) -> ExportResult:
    """Exporta ``strategy`` a un .mq5 determinista y su manifest."""

    model = _model(strategy)
    errors = dsl.validate(model)
    if errors:
        raise ExportError("estrategia invalida: " + "; ".join(errors))
    if write_trace and bars is None:
        raise ExportError("Sin datos: la traza necesita barras")
    if model.timeframe not in MQL5_PERIODS:  # pragma: no cover - dsl.validate
        raise ExportError(f"timeframe no soportado por MQL5: {model.timeframe}")
    session_tz = dsl.resolved_session_tz(model)
    if session_tz != "America/New_York":
        raise ExportError(
            f"huso {session_tz} no exportable: el EA implementa America/New_York con DST"
        )
    days = tuple(int(day) for day in (weekdays if weekdays is not None else range(5)))
    if any(day < 0 or day > 6 for day in days):
        raise ExportError(f"weekdays invalidos: {weekdays}")
    profile = _firm_profile(
        account_id,
        model.instrument,
        market=model.market,
        daily_loss=daily_loss,
        max_loss=max_loss,
        risk_pct=risk_pct,
    )
    template_name, template_version, template_sha = _template_info(template)
    digest = dsl.strategy_hash(model)
    magic = magic_number(digest)
    compiler = _MqlCompiler(model, days)
    header = _header(model, digest, template_name, template_version, magic, profile, days)
    source = _mql5_source(
        model,
        compiler,
        header=header,
        magic=magic,
        profile=profile,
        weekdays=days,
    )
    target_dir = Path(out_dir).expanduser()
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    base = "_".join(
        [
            _slug(model.instrument).upper(),
            model.timeframe,
            _slug(profile.account).upper(),
            digest[:12],
        ]
    )
    if stem:
        base = _slug(stem)
    mq5_path = target_dir / f"{base}.mq5"
    manifest_path = target_dir / f"{base}.manifest.json"
    trace_path = target_dir / f"{base}.trace.csv" if write_trace else None
    mq5_bytes = _write_text(mq5_path, source)
    sha = hashlib.sha256(mq5_bytes).hexdigest()
    if write_trace:
        assert trace_path is not None
        assert bars is not None
        _write_text(trace_path, trace_csv(model, bars, weekdays=days))
    manifest = {
        "exporter_version": EXPORTER_VERSION,
        "strategy_hash": digest,
        "template": {
            "name": template_name,
            "version": template_version,
            "sha256": template_sha,
        },
        "instrument": model.instrument,
        "timeframe": model.timeframe,
        "account": profile.account,
        "firm": profile.firm,
        "drawdown_mode": profile.drawdown_mode,
        "magic": magic,
        "file": mq5_path.name,
        "sha256": sha,
        "blocks": sorted(compiler.blocks),
        "risk": {
            "per_trade_risk_pct": profile.risk_pct,
            "daily_loss": profile.daily_loss,
            "max_loss": profile.max_loss,
        },
        "weekdays": list(days),
        "trace_file": trace_path.name if trace_path is not None else None,
    }
    _write_text(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return ExportResult(
        mq5_path=mq5_path,
        manifest_path=manifest_path,
        trace_path=trace_path,
        sha256=sha,
        magic=magic,
        strategy_hash=digest,
        blocks=tuple(sorted(compiler.blocks)),
        account=profile.account,
        firm=profile.firm,
    )


def export_spec(
    path: str | Path,
    *,
    out_dir: str | Path = "reports/export/",
    account_id: str | None = None,
    template: str | None = None,
    daily_loss: float | None = None,
    max_loss: float | None = None,
    risk_pct: float | None = None,
    weekdays: Sequence[int] | None = None,
) -> ExportResult:
    model, spec_template, spec_account, spec_days = _load_spec(path)
    account = account_id or spec_account
    if not account:
        raise ExportError("Sin datos: la especificacion no declara cuenta; usa --account")
    return export_strategy(
        model,
        account_id=account,
        out_dir=out_dir,
        template=template or spec_template,
        daily_loss=daily_loss,
        max_loss=max_loss,
        risk_pct=risk_pct,
        weekdays=weekdays if weekdays is not None else spec_days,
    )


def export_strategy_id(
    strategy_id: int,
    *,
    out_dir: str | Path = "reports/export/",
    account_id: str | None = None,
    template: str | None = None,
    daily_loss: float | None = None,
    max_loss: float | None = None,
    risk_pct: float | None = None,
    weekdays: Sequence[int] | None = None,
    db_path: str | Path | None = None,
) -> ExportResult:
    from . import databank

    strategy_row = databank.get_strategy(int(strategy_id), db_path=db_path)
    if strategy_row is None:
        raise ExportError(f"estrategia no encontrada: {strategy_id}")
    campaign = databank.get_campaign(strategy_row["campaign_id"], db_path=db_path)
    config = (campaign or {}).get("config") or {}
    account = (
        account_id
        or config.get("account")
        or (config.get("cost") or {}).get("account")
    )
    if not account:
        raise ExportError("Sin datos: la campana no declara cuenta; usa --account")
    template_name = template or config.get("template") or (campaign or {}).get("template")
    days = weekdays
    if days is None:
        configured = (config.get("limits") or {}).get("weekdays")
        if configured:
            days = tuple(int(day) for day in configured)
    return export_strategy(
        strategy_row["dsl"],
        account_id=str(account),
        out_dir=out_dir,
        template=template_name,
        daily_loss=daily_loss,
        max_loss=max_loss,
        risk_pct=risk_pct,
        weekdays=days,
    )


__all__ = [
    "EXPORTER_VERSION",
    "ExportError",
    "ExportResult",
    "TraceRow",
    "UNSUPPORTED_BLOCKS",
    "block_coverage",
    "export_spec",
    "export_strategy",
    "export_strategy_id",
    "magic_number",
    "trace_csv",
    "trace_signals",
]
