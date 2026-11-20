"""DSL del Strategy Builder: AST JSON validado con pydantic.

La estrategia es un árbol de reglas. ``validate`` devuelve una lista de errores
semánticos (vacía = válida); ``canonical_json`` y ``strategy_hash`` permiten
deduplicar de forma estable. La zona horaria de sesión sale de
``data_quality.session_tz`` del instrumento en ``engine.yaml``.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import load_engine_config

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}
HTF_TIMEFRAMES = {"M15", "H1", "H4", "D1"}
WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
PRICE_FIELDS = {"open", "high", "low", "close", "range", "body"}
LEVELS = {
    "prev_session_high",
    "prev_session_low",
    "opening_range_high",
    "opening_range_low",
    "prev_day_high",
    "prev_day_low",
    "donchian_high",
    "donchian_low",
}
COMPARE = {"gt", "lt", "ge", "le", "between"}
CROSS = {"cross_up", "cross_down"}
LOGICAL = {"and", "or", "not"}
TEMPORAL = {"held_for", "within_bars", "time_between", "weekday_in"}
OPERANDS = {"const", "price", "level", "indicator", "htf", "pattern", "regime"}
KINDS = OPERANDS | LOGICAL | COMPARE | CROSS | TEMPORAL


class DslError(ValueError):
    pass


class Expr(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    args: list["Expr"] = Field(default_factory=list)
    left: "Expr | None" = None
    right: "Expr | None" = None
    low: float | None = None
    high: float | None = None
    n: int | None = None
    value: float | None = None
    src: str | None = None
    ind: str | None = None
    lookback: int | None = None
    params: dict[str, float] = Field(default_factory=dict)
    tf: str | None = None
    expr: "Expr | None" = None
    price: str | None = None
    level: str | None = None
    pattern: str | None = None
    regime: str | None = None
    start: str | None = None
    end: str | None = None
    days: list[str] = Field(default_factory=list)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in KINDS:
            raise ValueError(f"tipo de nodo desconocido: {value}")
        return value


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tz: str | None = None
    start: str = "09:35"
    end: str = "11:30"
    flat_at: str = "15:45"
    or_minutes: int = Field(default=15, ge=1, le=120)

    @field_validator("start", "end", "flat_at")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        if not HHMM.match(str(value)):
            raise ValueError(f"hora inválida: {value}")
        return str(value)

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"zona horaria inválida: {value}") from exc
        return str(value)


class StopSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["atr", "pct", "fixed"] = "atr"
    mult: float = Field(default=1.5, gt=0)
    n: int = Field(default=14, ge=1)
    value: float | None = Field(default=None, gt=0)


class TargetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["rr", "pct", "fixed"] = "rr"
    rr: float = Field(default=2.0, gt=0)
    value: float | None = Field(default=None, gt=0)


class Exit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop: StopSpec = Field(default_factory=StopSpec)
    target: TargetSpec = Field(default_factory=TargetSpec)
    breakeven: dict[str, float] | None = None
    trailing: dict[str, float] | None = None
    time_exit_bars: int | None = Field(default=None, ge=1)
    opposite_signal: bool = False


class Sizing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_per_trade_r: float = Field(default=1.0, gt=0, le=10)


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_trades_per_day: int = Field(default=2, ge=0, le=100)
    cooldown_bars: int = Field(default=0, ge=0, le=1000)


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dsl_version: str = "1"
    instrument: str
    market: Literal["cfd", "futures"]
    timeframe: str
    session: Session = Field(default_factory=Session)
    long_entry: Expr | None = None
    short_entry: Expr | None = None
    exit: Exit = Field(default_factory=Exit)
    sizing: Sizing = Field(default_factory=Sizing)
    limits: Limits = Field(default_factory=Limits)

    @field_validator("instrument")
    @classmethod
    def _instrument(cls, value: str) -> str:
        text = str(value or "").strip().upper()
        if not text:
            raise ValueError("instrumento vacío")
        return text

    @field_validator("timeframe")
    @classmethod
    def _timeframe(cls, value: str) -> str:
        text = str(value or "").strip().upper()
        if text not in TIMEFRAMES:
            raise ValueError(f"timeframe no soportado: {value}")
        return text


Expr.model_rebuild()


def _node_dict(expr: Expr) -> dict:
    return expr.model_dump(mode="json", exclude_none=True)


def _same_node(left: Expr | None, right: Expr | None) -> bool:
    if left is None or right is None:
        return False
    return _node_dict(left) == _node_dict(right)


def _walk(expr: Expr):
    yield expr
    for item in expr.args:
        yield from _walk(item)
    if expr.left is not None:
        yield from _walk(expr.left)
    if expr.right is not None:
        yield from _walk(expr.right)
    if expr.expr is not None:
        yield from _walk(expr.expr)


def count_nodes(strategy: Strategy | dict) -> int:
    model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)
    total = 0
    for expr in (model.long_entry, model.short_entry):
        if expr is not None:
            total += sum(1 for _ in _walk(expr))
    return total


def depth(strategy: Strategy | dict) -> int:
    model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)

    def _depth(expr: Expr | None) -> int:
        if expr is None:
            return 0
        children = [*expr.args]
        if expr.left is not None:
            children.append(expr.left)
        if expr.right is not None:
            children.append(expr.right)
        if expr.expr is not None:
            children.append(expr.expr)
        return 1 + max((_depth(child) for child in children), default=0)

    return max(_depth(model.long_entry), _depth(model.short_entry))


def canonical_json(strategy: Strategy | dict) -> str:
    model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)
    return json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def strategy_hash(strategy: Strategy | dict) -> str:
    return hashlib.sha256(canonical_json(strategy).encode("utf-8")).hexdigest()


def resolved_session_tz(strategy: Strategy | dict, config=None) -> str:
    """Zona de sesión del instrumento según ``data_quality.session_tz``."""
    model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)
    cfg = config or load_engine_config()
    return cfg.data_quality.tz_for(model.instrument)


def indicator_params(expr: Expr) -> dict[str, float]:
    """Parámetros efectivos de un bloque: ``params`` + ``n``/``lookback``."""
    params = dict(expr.params)
    if expr.n is not None:
        params["n"] = expr.n
    if expr.lookback is not None:
        params["lookback"] = expr.lookback
    return params


def _block_names() -> set[str]:
    from .blocks import BLOCKS

    return set(BLOCKS)


def _validate_param(name: str, value: float, spec, errors: list[str], path: str) -> None:
    if spec.step <= 0:
        errors.append(f"{path}.{name}: ParamSpec con paso inválido ({spec.step})")
        return
    numeric = float(value)
    if spec.integer and not numeric.is_integer():
        errors.append(f"{path}.{name}: debe ser entero ({value})")
        return
    if numeric < spec.low - 1e-9 or numeric > spec.high + 1e-9:
        errors.append(
            f"{path}.{name}: {value} fuera de rango [{spec.low}, {spec.high}]"
        )
        return
    steps = (numeric - spec.low) / spec.step
    if abs(steps - round(steps)) > 1e-6:
        errors.append(
            f"{path}.{name}: {value} no sigue el paso {spec.step} desde {spec.low}"
        )


def _validate_block_params(expr: Expr, spec, errors: list[str], path: str) -> None:
    params = indicator_params(expr)
    for name, value in params.items():
        param_spec = spec.params.get(name)
        if param_spec is None:
            errors.append(f"{path}.{name}: parámetro desconocido para {spec.name}")
            continue
        _validate_param(name, value, param_spec, errors, path)


def _has_price(expr: Expr | None) -> bool:
    if expr is None:
        return False
    if expr.kind == "price":
        return True
    for child in expr.args:
        if _has_price(child):
            return True
    for child in (expr.left, expr.right, expr.expr):
        if _has_price(child):
            return True
    return False


def _price_direction(expr: Expr | None, *, negated: bool = False) -> str | None:
    """Dirección de la primera condición que compara un precio.

    ``gt``/``ge``/``cross_up`` son alcistas; ``lt``/``le``/``cross_down``
    bajistas. ``not`` invierte la dirección. Sirve para impedir que largo y
    corto compartan la misma condición de precio (p. ej. ambos ``close > ORH``).
    """

    if expr is None:
        return None
    if expr.kind == "not":
        child = expr.args[0] if len(expr.args) == 1 else None
        return _price_direction(child, negated=not negated)
    if expr.kind == "htf":
        return _price_direction(expr.expr, negated=negated)
    if expr.kind in {"and", "or"}:
        for child in expr.args:
            direction = _price_direction(child, negated=negated)
            if direction is not None:
                return direction
        return None
    if expr.kind in {"held_for", "within_bars"}:
        child = expr.args[0] if expr.args else None
        return _price_direction(child, negated=negated)
    if expr.kind in COMPARE or expr.kind in CROSS:
        if not (_has_price(expr.left) or _has_price(expr.right)):
            return None
        if expr.kind in {"gt", "ge", "cross_up"}:
            direction = "up"
        elif expr.kind in {"lt", "le", "cross_down"}:
            direction = "down"
        else:
            return None
        if negated:
            direction = "down" if direction == "up" else "up"
        return direction
    return None


def _validate_expr(expr: Expr | None, errors: list[str], path: str = "expr") -> None:
    if expr is None:
        return
    kind = expr.kind
    if kind in LOGICAL:
        if kind == "not" and len(expr.args) != 1:
            errors.append(f"{path}.not necesita exactamente 1 argumento")
        if kind in {"and", "or"} and len(expr.args) < 2:
            errors.append(f"{path}.{kind} necesita al menos 2 argumentos")
        for index, item in enumerate(expr.args):
            _validate_expr(item, errors, f"{path}.args[{index}]")
    elif kind in COMPARE:
        if kind == "between":
            if expr.left is None or expr.low is None or expr.high is None:
                errors.append(f"{path}.between necesita left, low y high")
            elif expr.low > expr.high:
                errors.append(f"{path}.between: low > high")
        else:
            if expr.left is None or expr.right is None:
                errors.append(f"{path}.{kind} necesita left y right")
            elif _same_node(expr.left, expr.right):
                errors.append(f"{path}.{kind}: compara un nodo consigo mismo")
        _validate_expr(expr.left, errors, f"{path}.left")
        _validate_expr(expr.right, errors, f"{path}.right")
    elif kind in CROSS:
        if expr.left is None or expr.right is None:
            errors.append(f"{path}.{kind} necesita left y right")
        elif _same_node(expr.left, expr.right):
            errors.append(f"{path}.{kind}: cruza un nodo consigo mismo")
        _validate_expr(expr.left, errors, f"{path}.left")
        _validate_expr(expr.right, errors, f"{path}.right")
    elif kind in {"held_for", "within_bars"}:
        if len(expr.args) != 1 or expr.n is None or expr.n < 1:
            errors.append(f"{path}.{kind} necesita 1 condición y n >= 1")
        for index, item in enumerate(expr.args):
            _validate_expr(item, errors, f"{path}.args[{index}]")
    elif kind == "time_between":
        if not expr.start or not expr.end or not HHMM.match(expr.start) or not HHMM.match(expr.end):
            errors.append(f"{path}.time_between necesita start/end HH:MM")
        elif expr.start == expr.end:
            errors.append(f"{path}.time_between: start y end no pueden ser iguales")
    elif kind == "weekday_in":
        if not expr.days:
            errors.append(f"{path}.weekday_in necesita días")
        for day in expr.days:
            if str(day).lower() not in WEEKDAYS:
                errors.append(f"{path}.weekday_in: día inválido {day}")
    elif kind == "const":
        if expr.value is None:
            errors.append(f"{path}.const necesita value")
    elif kind == "price":
        if expr.price not in PRICE_FIELDS:
            errors.append(f"{path}.price inválido: {expr.price}")
    elif kind == "level":
        if expr.level not in LEVELS:
            errors.append(f"{path}.level inválido: {expr.level}")
        elif expr.level in {"donchian_high", "donchian_low"} and expr.n is not None:
            from .blocks import get_block

            param = get_block("donchian_pos").params["n"]
            _validate_param("n", expr.n, param, errors, path)
    elif kind == "indicator":
        from .blocks import get_block

        if expr.ind not in _block_names():
            errors.append(f"{path}.indicator desconocido: {expr.ind}")
        else:
            spec = get_block(expr.ind)
            if spec.output != "float":
                errors.append(f"{path}.indicator.{expr.ind} devuelve {spec.output}; usa pattern/regime")
            if expr.src is not None and expr.src not in PRICE_FIELDS:
                errors.append(f"{path}.indicator.src inválido: {expr.src}")
            _validate_block_params(expr, spec, errors, path)
    elif kind == "htf":
        if expr.tf not in HTF_TIMEFRAMES:
            errors.append(f"{path}.htf: tf inválido {expr.tf}")
        if expr.expr is None:
            errors.append(f"{path}.htf necesita expr")
        _validate_expr(expr.expr, errors, f"{path}.expr")
    elif kind in {"pattern", "regime"}:
        from .blocks import get_block

        name = expr.pattern if kind == "pattern" else expr.regime
        if name not in _block_names():
            errors.append(f"{path}.{kind} desconocido: {name}")
        else:
            spec = get_block(name)
            if spec.output != "bool":
                errors.append(f"{path}.{kind}.{name} devuelve {spec.output}; usa indicator")
            _validate_block_params(expr, spec, errors, path)


def validate(strategy: Strategy | dict) -> list[str]:
    """Valida la semántica. Devuelve [] si es válida."""
    try:
        model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)
    except ValidationError as exc:
        return [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
    errors: list[str] = []
    config = load_engine_config()
    limits = config.limits
    if count_nodes(model) > limits.max_nodes:
        errors.append(f"nodos {count_nodes(model)} > max_nodes {limits.max_nodes}")
    if depth(model) > limits.max_depth:
        errors.append(f"profundidad {depth(model)} > max_depth {limits.max_depth}")
    if not model.long_entry and not model.short_entry:
        errors.append("la estrategia no tiene entrada larga ni corta")
    _validate_expr(model.long_entry, errors, "long_entry")
    _validate_expr(model.short_entry, errors, "short_entry")
    long_direction = _price_direction(model.long_entry)
    short_direction = _price_direction(model.short_entry)
    if long_direction is not None and short_direction == long_direction:
        errors.append(
            "short_entry: la condición de precio va en la misma dirección que "
            f"long_entry ({long_direction})"
        )
    session = model.session
    if session.start == session.end:
        errors.append("session: start y end no pueden ser iguales")
    if session.start == session.flat_at:
        errors.append("session: start y flat_at no pueden ser iguales")
    configured_tz = config.data_quality.tz_for(model.instrument)
    if session.tz is not None and session.tz != configured_tz:
        errors.append(
            f"session.tz {session.tz} no coincide con session_tz del instrumento "
            f"({configured_tz})"
        )
    if model.exit.stop.type == "fixed" and model.exit.stop.value is None:
        errors.append("exit.stop fixed necesita value")
    if model.exit.target.type == "fixed" and model.exit.target.value is None:
        errors.append("exit.target fixed necesita value")
    if model.exit.stop.type == "atr":
        from .blocks import get_block

        param = get_block("atr").params["n"]
        _validate_param("n", model.exit.stop.n, param, errors, "exit.stop")
    return errors


__all__ = [
    "DslError",
    "Expr",
    "Exit",
    "Limits",
    "Session",
    "Sizing",
    "StopSpec",
    "Strategy",
    "TargetSpec",
    "canonical_json",
    "count_nodes",
    "depth",
    "indicator_params",
    "resolved_session_tz",
    "strategy_hash",
    "validate",
]
