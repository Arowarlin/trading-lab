"""Compilador del DSL a señales vectorizadas.

``compile(strategy, bars)`` evalúa el AST con numpy/pandas y devuelve
``Signals(long_entry, short_entry, valid_from)``. Todas las señales usan barras
cerradas; la entrada se ejecuta en el open siguiente (Fase 3). El índice de
``bars`` debe ser tz-aware (UTC, como devuelve ``discovery.data_sources``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators_ext as ext
from .blocks import get_block
from .config import load_engine_config
from .dsl import (
    COMPARE,
    CROSS,
    LOGICAL,
    DslError,
    Expr,
    Strategy,
    indicator_params,
    resolved_session_tz,
    validate,
)
from .indicator_cache import MISSING, IndicatorCache

_HTF_RULES = {
    "M15": ("15min", pd.Timedelta(minutes=15)),
    "H1": ("1h", pd.Timedelta(hours=1)),
    "H4": ("4h", pd.Timedelta(hours=4)),
}
_WEEKDAY = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Signals:
    long_entry: np.ndarray
    short_entry: np.ndarray
    valid_from: int = 0

    def arrays(self, n: int) -> tuple[np.ndarray, np.ndarray, int]:
        """Copia, valida y enmascara las señales antes de ``valid_from``."""

        long_arr = np.array(self.long_entry, dtype=bool).reshape(-1)
        short_arr = np.array(self.short_entry, dtype=bool).reshape(-1)
        if len(long_arr) != n or len(short_arr) != n:
            raise ValueError(
                f"señales de longitud {len(long_arr)}/{len(short_arr)} != barras {n}"
            )
        start = int(self.valid_from or 0)
        if start < 0 or start > n:
            raise ValueError(f"valid_from fuera de rango: {start}")
        long_arr[:start] = False
        short_arr[:start] = False
        return long_arr, short_arr, start


def _require_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars, pd.DataFrame):
        raise ValueError("bars debe ser un pandas.DataFrame")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("bars.index debe ser un DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError(
            "bars.index debe tener zona horaria (tz-aware); no se asume UTC. "
            "Usa discovery.data_sources.load_source()."
        )
    if len(bars) == 0:
        raise ValueError("bars está vacío")
    if bars.index.has_duplicates:
        raise ValueError("bars.index tiene timestamps duplicados")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("bars.index debe estar ordenado de forma creciente")
    missing = {"open", "high", "low", "close"} - set(bars.columns)
    if missing:
        raise ValueError(f"bars: faltan columnas {', '.join(sorted(missing))}")
    return bars


def _aggregations(bars: pd.DataFrame) -> dict[str, str]:
    aggregations = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for column in ("tickvol", "volume"):
        if column in bars.columns:
            aggregations[column] = "sum"
    return aggregations


def _htf_bars(bars: pd.DataFrame, tf: str, tz: str) -> tuple[pd.DataFrame, pd.Timedelta]:
    aggregations = _aggregations(bars)
    if tf == "D1":
        local = bars.index.tz_convert(tz)
        keys = local.normalize()
        htf = bars.groupby(keys).agg(aggregations).dropna()
        htf.index = pd.DatetimeIndex(htf.index).tz_convert("UTC")
        return htf, pd.Timedelta(days=1)
    try:
        rule, duration = _HTF_RULES[tf]
    except KeyError as exc:
        raise DslError(f"timeframe HTF no soportado: {tf}") from exc
    htf = bars.resample(rule, label="left", closed="left").agg(aggregations).dropna()
    return htf, duration


def _htf_positions(
    base_index: pd.DatetimeIndex,
    htf_index: pd.DatetimeIndex,
    duration: pd.Timedelta,
) -> np.ndarray:
    """Última vela HTF cuyo cierre (inicio + duración) es <= la barra base."""
    return htf_index.searchsorted(base_index - duration, side="right") - 1


def _align_htf(
    base_index: pd.DatetimeIndex,
    htf_index: pd.DatetimeIndex,
    values: pd.Series,
    duration: pd.Timedelta,
    *,
    fill,
) -> pd.Series:
    positions = _htf_positions(base_index, htf_index, duration)
    if values.dtype == bool:
        array = np.full(len(base_index), bool(fill), dtype=bool)
    else:
        array = np.full(len(base_index), fill, dtype=float)
    valid = positions >= 0
    if valid.any():
        array[valid] = values.to_numpy()[positions[valid]]
    return pd.Series(array, index=base_index)


class _Evaluator:
    def __init__(
        self,
        bars: pd.DataFrame,
        strategy: Strategy,
        tz: str,
        *,
        cache: IndicatorCache | None = None,
    ) -> None:
        self.bars = bars
        self.strategy = strategy
        self.tz = tz
        self.index = bars.index
        self.session = strategy.session
        self.ctx = {
            "tz": tz,
            "start": self.session.start,
            "end": self.session.end,
            "or_minutes": self.session.or_minutes,
        }
        self.cache = cache
        self.local_cache: dict[tuple, pd.Series] = {}
        self.close = bars["close"].astype(float)
        self.open = bars["open"].astype(float)
        self.high = bars["high"].astype(float)
        self.low = bars["low"].astype(float)

    def _series(self, values) -> pd.Series:
        if isinstance(values, pd.Series):
            return values.reindex(self.index)
        return pd.Series(values, index=self.index)

    def _cache_key(self, kind: str, name: str, params: dict, extra=None) -> tuple:
        return (
            kind,
            name,
            tuple(sorted((str(key), float(value)) for key, value in params.items())),
            self.tz,
            self.session.start,
            self.session.end,
            self.session.or_minutes,
            extra,
        )

    def _cached(self, key: tuple, builder) -> pd.Series:
        if self.cache is None:
            if key not in self.local_cache:
                self.local_cache[key] = self._series(builder())
            return self.local_cache[key]
        value = self.cache.get(key)
        if value is not MISSING:
            return value
        series = self._series(builder())
        self.cache.put(key, series)
        return series

    def eval(self, expr: Expr | None) -> pd.Series:
        if expr is None:
            return pd.Series(False, index=self.index)
        kind = expr.kind
        if kind in LOGICAL:
            return self._logical(expr)
        if kind in COMPARE:
            return self._compare(expr)
        if kind in CROSS:
            return self._cross(expr)
        if kind == "held_for":
            condition = self.eval(expr.args[0]).astype(bool)
            window = int(expr.n or 1)
            return condition.rolling(window, min_periods=window).sum() == window
        if kind == "within_bars":
            condition = self.eval(expr.args[0]).astype(bool)
            window = int(expr.n or 1)
            return condition.rolling(window, min_periods=1).sum() > 0
        if kind == "time_between":
            _local, mask = ext._session_mask(self.index, self.tz, expr.start, expr.end)
            return mask
        if kind == "weekday_in":
            return self._weekday_in(expr)
        if kind == "const":
            return pd.Series(float(expr.value), index=self.index)
        if kind == "price":
            return self._price(expr)
        if kind == "level":
            return self._level(expr)
        if kind == "indicator":
            return self._indicator(expr)
        if kind == "pattern":
            return self._pattern(expr, "pattern")
        if kind == "regime":
            return self._pattern(expr, "regime")
        if kind == "htf":
            return self._htf(expr)
        raise DslError(f"nodo no evaluable: {kind}")

    def _logical(self, expr: Expr) -> pd.Series:
        values = [self.eval(item).astype(bool) for item in expr.args]
        if expr.kind == "not":
            return ~values[0]
        if not values:
            return pd.Series(True, index=self.index)
        result = values[0].copy()
        for value in values[1:]:
            result = result & value if expr.kind == "and" else result | value
        return result

    def _compare(self, expr: Expr) -> pd.Series:
        left = self.eval(expr.left)
        if expr.kind == "between":
            return (left >= float(expr.low)) & (left <= float(expr.high))
        right = self.eval(expr.right)
        if expr.kind == "gt":
            return left > right
        if expr.kind == "lt":
            return left < right
        if expr.kind == "ge":
            return left >= right
        return left <= right

    def _cross(self, expr: Expr) -> pd.Series:
        left = self.eval(expr.left)
        right = self.eval(expr.right)
        previous_left = left.shift(1)
        previous_right = right.shift(1)
        if expr.kind == "cross_up":
            return (left > right) & (previous_left <= previous_right)
        return (left < right) & (previous_left >= previous_right)

    def _weekday_in(self, expr: Expr) -> pd.Series:
        local = self.index.tz_convert(self.tz)
        days = {_WEEKDAY[str(day).lower()] for day in expr.days if str(day).lower() in _WEEKDAY}
        return pd.Series(np.isin(local.weekday.to_numpy(), sorted(days)), index=self.index)

    def _price(self, expr: Expr) -> pd.Series:
        if expr.price == "open":
            return self.open
        if expr.price == "high":
            return self.high
        if expr.price == "low":
            return self.low
        if expr.price == "close":
            return self.close
        if expr.price == "range":
            return self.high - self.low
        if expr.price == "body":
            return self.close - self.open
        raise DslError(f"precio no soportado: {expr.price}")

    def _level(self, expr: Expr) -> pd.Series:
        name = str(expr.level)
        if name in {"prev_session_high", "prev_session_low"}:
            which = "high" if name.endswith("high") else "low"
            return self._cached(
                self._cache_key("level", name, {}),
                lambda: ext.prev_session_level(
                    self.bars,
                    tz=self.tz,
                    start=self.session.start,
                    end=self.session.end,
                    which=which,
                ),
            )
        if name in {"opening_range_high", "opening_range_low"}:
            which = "high" if name.endswith("high") else "low"
            return self._cached(
                self._cache_key("level", name, {}),
                lambda: ext.opening_range(
                    self.bars,
                    tz=self.tz,
                    start=self.session.start,
                    end=self.session.end,
                    minutes=self.session.or_minutes,
                    which=which,
                ),
            )
        if name in {"prev_day_high", "prev_day_low"}:
            which = "high" if name.endswith("high") else "low"
            return self._cached(
                self._cache_key("level", name, {}),
                lambda: ext.prev_day_level(self.bars, tz=self.tz, which=which),
            )
        if name in {"donchian_high", "donchian_low"}:
            which = "high" if name.endswith("high") else "low"
            n = int(expr.n or 20)
            return self._cached(
                self._cache_key("level", name, {"n": n}),
                lambda: ext.donchian_level(self.bars, n=n, which=which),
            )
        raise DslError(f"nivel no soportado: {name}")

    def _indicator(self, expr: Expr) -> pd.Series:
        spec = get_block(expr.ind)
        params = indicator_params(expr)
        return self._cached(
            self._cache_key("indicator", spec.name, params),
            lambda: spec.compute(self.bars, params, self.ctx).astype(float),
        )

    def _pattern(self, expr: Expr, kind: str) -> pd.Series:
        name = expr.pattern if kind == "pattern" else expr.regime
        spec = get_block(name)
        params = indicator_params(expr)
        return self._cached(
            self._cache_key(kind, spec.name, params),
            lambda: spec.compute(self.bars, params, self.ctx).astype(bool),
        )

    def _htf(self, expr: Expr) -> pd.Series:
        htf_bars, duration = _htf_bars(self.bars, expr.tf, self.tz)
        child = _Evaluator(htf_bars, self.strategy, self.tz)
        values = child.eval(expr.expr)
        fill = False if values.dtype == bool else np.nan
        return _align_htf(self.index, htf_bars.index, values, duration, fill=fill)


def _children(expr: Expr) -> list[Expr]:
    children = [*expr.args]
    if expr.left is not None:
        children.append(expr.left)
    if expr.right is not None:
        children.append(expr.right)
    if expr.expr is not None:
        children.append(expr.expr)
    return children


def _warmup(expr: Expr | None, bars: pd.DataFrame, tz: str, strategy: Strategy) -> int:
    if expr is None:
        return 0
    if expr.kind in {"indicator", "pattern", "regime"}:
        name = expr.ind if expr.kind == "indicator" else expr.pattern if expr.kind == "pattern" else expr.regime
        return int(get_block(name).warmup(indicator_params(expr)))
    if expr.kind == "level":
        if expr.level in {"donchian_high", "donchian_low"}:
            return int(expr.n or 20) + 1
        return 0
    if expr.kind == "htf":
        htf_bars, duration = _htf_bars(bars, expr.tf, tz)
        inner = _warmup(expr.expr, htf_bars, tz, strategy)
        positions = _htf_positions(bars.index, htf_bars.index, duration)
        valid = np.where(positions >= inner)[0]
        return int(valid[0]) if valid.size else len(bars)
    if expr.kind in {"held_for", "within_bars"}:
        child = _warmup(expr.args[0] if expr.args else None, bars, tz, strategy)
        return child + int(expr.n or 0)
    if expr.kind in LOGICAL or expr.kind in COMPARE or expr.kind in CROSS:
        return max((_warmup(child, bars, tz, strategy) for child in _children(expr)), default=0)
    return 0


def compile(
    strategy: Strategy | dict,
    bars: pd.DataFrame,
    *,
    cache: IndicatorCache | None = None,
    _skip_validation_for_archived: bool = False,
) -> Signals:
    """Compila la estrategia en señales booleanas alineadas a ``bars``.

    ``cache`` es la LRU del worker; si se pasa, debe pertenecer a este dataset.
    ``_skip_validation_for_archived`` es privado: solo ``perturb.py`` lo usa y
    solo tras comprobar que la estrategia ya existe en ``disc_strategies``.
    """

    model = strategy if isinstance(strategy, Strategy) else Strategy.model_validate(strategy)
    if not _skip_validation_for_archived:
        errors = validate(model)
        if errors:
            raise DslError("; ".join(errors))
    bars = _require_bars(bars)
    if cache is not None:
        token = id(bars)
        if cache.dataset_token is None:
            cache.dataset_token = token
        elif cache.dataset_token != token:
            raise DslError("la caché de indicadores pertenece a otro dataset")
    config = load_engine_config()
    tz = resolved_session_tz(model, config)
    evaluator = _Evaluator(bars, model, tz, cache=cache)
    length = len(bars)
    zeros = np.zeros(length, dtype=bool)
    if model.long_entry is not None:
        long_values = evaluator.eval(model.long_entry)
        if long_values.dtype != bool:
            raise DslError("long_entry debe ser booleana")
        long_entry = long_values.to_numpy(dtype=bool)
    else:
        long_entry = zeros.copy()
    if model.short_entry is not None:
        short_values = evaluator.eval(model.short_entry)
        if short_values.dtype != bool:
            raise DslError("short_entry debe ser booleana")
        short_entry = short_values.to_numpy(dtype=bool)
    else:
        short_entry = zeros.copy()
    valid_from = min(
        max(
            _warmup(model.long_entry, bars, tz, model),
            _warmup(model.short_entry, bars, tz, model),
        ),
        length,
    )
    _local, session_mask = ext._session_mask(
        bars.index,
        tz,
        model.session.start,
        model.session.end,
    )
    mask = session_mask.to_numpy(dtype=bool)
    long_entry = long_entry & mask
    short_entry = short_entry & mask
    long_entry[:valid_from] = False
    short_entry[:valid_from] = False
    return Signals(long_entry=long_entry, short_entry=short_entry, valid_from=valid_from)


__all__ = ["Signals", "compile"]
