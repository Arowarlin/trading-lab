"""Investigación intradía forex/CFD con datos MT5 locales.

- Cachea velas M15/H1 ya corregidas a UTC por MT5Broker.rates.
- Modela spread por hora (si existe), slippage y comisión.
- Incluye tres estrategias acotadas y las pasa por DSR/PBO/WF/regímenes.
- No descarga datos de pago ni envía órdenes.
"""
from __future__ import annotations

import itertools
import json
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DEFAULT_DB, ROOT
from .indicators import atr, ema
from .intraday_costs import asset_costs
from .learning import count_tests, get_lesson
from .profiles import get_profile
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo
from .research import deflated_sharpe
from .strategies.base import StrategyResult
from .trials import record_trial
from .validation import cscv_pbo, returns_matrix
from .walkforward import regime_gate, regime_report, walk_forward

INTRADAY_GRIDS = {
    "orb": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [8, 16]},
    "pullback": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "asian_rev": {"buffer_atr": [0.1, 0.3], "max_hold": [8, 16]},
    "orb_ny": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [8, 16]},
    "trend_intraday": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "overlap_breakout": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [4, 8]},
    "range_reversal": {"lookback": [12, 24], "entry_z": [1.5, 2.0], "max_hold": [8, 16]},
    "london_pullback": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "session_trend": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "tokyo_breakout": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [4, 12]},
}
ASSET_FAMILIES = {
    "US100.CASH": ("orb_ny", "trend_intraday"),
    "NASDAQ": ("orb_ny", "trend_intraday"),
    "XAUUSD": ("asian_rev", "overlap_breakout"),
    "EURUSD": ("range_reversal", "london_pullback"),
    "USDJPY": ("session_trend", "tokyo_breakout"),
}
DEFAULT_HORIZONS = (22, 44, 120)
COST_GRID_BPS = (0.0, 0.5, 1.0, 2.0, 3.0)
FAMILY_HYPOTHESES = {
    "orb": (
        "Ruptura del rango de apertura: la continuación de la momentum tras la "
        "apertura de Londres/NY tiene ventaja en M15."
    ),
    "pullback": (
        "Tendencia intradía con retroceso a la media: los retrocesos dentro de "
        "la tendencia ofrecen mejor precio de entrada."
    ),
    "asian_rev": (
        "Reversión del rango asiático: el rango formado en la sesión asiática "
        "suele revertirse al inicio de la sesión europea."
    ),
    "orb_ny": (
        "Ruptura del rango de apertura de Nueva York: la momentum posterior a "
        "las 09:30 ET continúa en el índice."
    ),
    "trend_intraday": (
        "Tendencia intradía en la sesión de Nueva York: el índice mantiene "
        "dirección tras la apertura."
    ),
    "overlap_breakout": (
        "Ruptura en el solape Londres/NY: el oro amplía rango cuando coinciden "
        "las dos sesiones."
    ),
    "range_reversal": (
        "Reversión a la media en rango durante Londres: los extremos del rango "
        "vuelven a la media."
    ),
    "london_pullback": (
        "Tendencia con retroceso en Londres: el retroceso a la media rápida "
        "ofrece entrada a favor de la tendencia del euro."
    ),
    "session_trend": (
        "Tendencia con filtro de sesión en USDJPY: la dirección dominante "
        "persiste durante Tokio/Londres."
    ),
    "tokyo_breakout": (
        "Ruptura tras la sesión de Tokio: el rango asiático se rompe al abrir "
        "Europa."
    ),
}


def families_for_symbol(symbol: str) -> tuple[str, ...]:
    """Familias asignadas al activo (todas si no está en el mapa)."""
    return ASSET_FAMILIES.get(str(symbol).upper(), tuple(INTRADAY_GRIDS))


def _bars_per_year(timeframe: str) -> float:
    if timeframe.upper() == "M15":
        return 252 * 96
    if timeframe.upper() == "H1":
        return 252 * 24
    return 252


def _sharpe_returns(returns: pd.Series, timeframe: str) -> float:
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    if std <= 0:
        return 0.0
    return float(returns.mean() / std * np.sqrt(_bars_per_year(timeframe)))


def _sharpe_at_cost(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    cost_bps: float,
) -> float:
    net = gross - turnover * float(cost_bps) / 10_000.0
    return _sharpe_returns(net, timeframe)


def _cost_curve(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    grid: tuple[float, ...] = COST_GRID_BPS,
) -> dict[str, float]:
    return {
        str(cost): _sharpe_at_cost(gross, turnover, timeframe, cost)
        for cost in grid
    }


def break_even_cost_bps(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    *,
    upper: float = 200.0,
) -> float | None:
    """Coste uniforme por unidad de turnover donde el Sharpe neto cruza 0.

    Si el Sharpe bruto ya es <= 0, no hay coste de equilibrio positivo: 0.0.
    """
    if _sharpe_at_cost(gross, turnover, timeframe, 0.0) <= 0:
        return 0.0
    low = 0.0
    high = float(upper)
    while _sharpe_at_cost(gross, turnover, timeframe, high) > 0 and high < 10_000:
        high *= 2.0
    if _sharpe_at_cost(gross, turnover, timeframe, high) > 0:
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if _sharpe_at_cost(gross, turnover, timeframe, middle) > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def cache_file(cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol).upper()
    return Path(cache_dir) / "mt5" / f"{safe}_{timeframe.upper()}.parquet"


def save_bars(df: pd.DataFrame, cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    path = cache_file(cache_dir, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index.name = "ts"
    frame.to_parquet(path)
    return path


def load_bars(cache_dir: str | Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = cache_file(cache_dir, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"no existe caché MT5: {path}")
    frame = pd.read_parquet(path)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.sort_index()


def cache_metadata(df: pd.DataFrame, timeframe: str) -> dict:
    if df.empty:
        return {"rows": 0, "start": None, "end": None, "years": 0.0, "timeframe": timeframe}
    start = df.index[0]
    end = df.index[-1]
    days = max(0.0, (end - start).total_seconds() / 86400)
    return {
        "rows": int(len(df)),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": round(days / 365.25, 2),
        "timeframe": timeframe,
    }


def _spread_bps(df: pd.DataFrame, point: float) -> tuple[pd.Series, bool]:
    if "spread" not in df.columns:
        return pd.Series(3.0, index=df.index), False
    raw = pd.to_numeric(df["spread"], errors="coerce").fillna(0.0)
    close = pd.to_numeric(df["close"], errors="coerce")
    spread = (raw * point / close * 10_000).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    hourly = spread.groupby(spread.index.hour).median()
    mapped = pd.Series(
        [float(hourly.get(ts.hour, hourly.median())) for ts in spread.index],
        index=spread.index,
    )
    reliable = bool(len(hourly) >= 2 and float(spread.median()) > 0.0)
    return mapped, reliable


def _cost_series(value: float | pd.Series, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.reindex(index).astype(float).ffill().bfill()
    return pd.Series(float(value), index=index, dtype=float)


def backtest_intraday(
    df: pd.DataFrame,
    target: pd.Series,
    *,
    timeframe: str = "M15",
    commission_bps: float | pd.Series = 1.0,
    slippage_bps: float = 2.0,
    slippage_optimistic_bps: float | None = None,
    point: float = 0.0001,
    spread_override_bps: float | None = None,
) -> dict:
    """Retorno neto con costes por spread horario, slippage y comisión.

    `spread_override_bps=0` es solo diagnóstico: conserva la fiabilidad real
    del spread observado, pero elimina su coste para medir el Sharpe bruto.
    """
    close = pd.to_numeric(df["close"], errors="coerce")
    pos = target.reindex(df.index).fillna(0.0).clip(-1.0, 1.0).shift(1).fillna(0.0)
    gross = close.pct_change().fillna(0.0) * pos
    turnover = pos.diff().abs().fillna(pos.abs())
    observed_spread, reliable = _spread_bps(df, point)
    if spread_override_bps is None:
        spread = observed_spread
    else:
        spread = pd.Series(float(spread_override_bps), index=df.index)
    commission = _cost_series(commission_bps, df.index)
    optimistic = (
        float(slippage_bps)
        if slippage_optimistic_bps is None
        else float(slippage_optimistic_bps)
    )
    cost_bps = commission + float(slippage_bps) + spread
    cost_optimistic = commission + optimistic + spread
    net = gross - turnover * cost_bps / 10_000.0
    net_optimistic = gross - turnover * cost_optimistic / 10_000.0
    equity = (1.0 + net).cumprod()
    std = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    ann = _bars_per_year(timeframe)
    sharpe = float(net.mean() / std * np.sqrt(ann)) if std > 0 else 0.0
    sharpe_optimistic = _sharpe_returns(net_optimistic, timeframe)
    weights = turnover.clip(lower=0.0)
    weight_sum = float(weights.sum())
    calibrated_cost = (
        float((cost_bps * weights).sum() / weight_sum)
        if weight_sum > 0
        else float(cost_bps.median())
    )
    drawdown = equity / equity.cummax() - 1.0
    return {
        "returns": net,
        "equity": equity,
        "metrics": {
            "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
            "sharpe": sharpe,
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "num_trades": int((turnover > 0).sum()),
            "bars": int(len(net)),
        },
        "spread_bps_median": float(spread.median()) if len(spread) else 0.0,
        "spread_observed_bps_median": float(observed_spread.median()) if len(observed_spread) else 0.0,
        "spread_override_bps": spread_override_bps,
        "spread_reliable": reliable,
        "commission_bps_median": float(commission.median()) if len(commission) else 0.0,
        "calibrated_cost_bps": calibrated_cost,
        "breakeven_cost_bps": break_even_cost_bps(gross, turnover, timeframe),
        "cost_curve_bps": _cost_curve(gross, turnover, timeframe),
        "sharpe_optimistic": sharpe_optimistic,
        "sharpe_conservative": sharpe,
        "slippage_optimistic_bps": optimistic,
    }


def _session_mask(index: pd.DatetimeIndex, start_hour: int, end_hour: int) -> pd.Series:
    hours = index.hour
    return pd.Series((hours >= start_hour) & (hours < end_hour), index=index)


def opening_range_breakout(
    df: pd.DataFrame,
    *,
    range_bars: int = 4,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
    start_hour: int = 7,
    end_hour: int = 16,
) -> StrategyResult:
    """Ruptura del rango de apertura de Londres/NY (UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    mask = _session_mask(df.index, start_hour, end_hour)
    for day in sorted({ts.date() for ts in df.index}):
        session = df[mask & (pd.Index(df.index.date) == day)]
        if len(session) < range_bars + 2:
            continue
        rng = session.iloc[:range_bars]
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        pos, hold = 0.0, 0
        for i in range(range_bars, len(session)):
            bar = session.iloc[i]
            if pos == 0.0:
                atr_value = float(atr_s.loc[bar.name]) if bar.name in atr_s.index else 0.0
                if bar["close"] > hi + buffer_atr * atr_value:
                    pos = 1.0
                elif bar["close"] < lo - buffer_atr * atr_value:
                    pos = -1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos = 0.0
                    hold = 0
            target.loc[bar.name] = pos
    return StrategyResult(
        "orb",
        target,
        {"range_bars": range_bars, "buffer_atr": buffer_atr, "max_hold": max_hold},
    )


def trend_pullback(
    df: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 100,
    pullback_atr: float = 0.25,
    max_hold: int = 8,
    start_hour: int = 0,
    end_hour: int = 24,
) -> StrategyResult:
    """Tendencia con retroceso a la media rápida, con filtro de sesión opcional."""
    close = df["close"]
    fast_ma, slow_ma, atr_s = ema(close, fast), ema(close, slow), atr(df)
    mask = _session_mask(df.index, start_hour, end_hour)
    target = pd.Series(0.0, index=df.index)
    pos, hold = 0.0, 0
    for ts, row in df.iterrows():
        if not bool(mask.loc[ts]):
            pos, hold = 0.0, 0
            target.loc[ts] = 0.0
            continue
        if pos == 0.0:
            atr_value = float(atr_s.loc[ts])
            if fast_ma.loc[ts] > slow_ma.loc[ts] and row["low"] <= fast_ma.loc[ts] - pullback_atr * atr_value:
                pos = 1.0
            elif fast_ma.loc[ts] < slow_ma.loc[ts] and row["high"] >= fast_ma.loc[ts] + pullback_atr * atr_value:
                pos = -1.0
        else:
            hold += 1
            if hold >= max_hold or (pos > 0 and fast_ma.loc[ts] < slow_ma.loc[ts]) or (pos < 0 and fast_ma.loc[ts] > slow_ma.loc[ts]):
                pos, hold = 0.0, 0
        target.loc[ts] = pos
    return StrategyResult(
        "pullback",
        target,
        {
            "fast": fast,
            "slow": slow,
            "pullback_atr": pullback_atr,
            "max_hold": max_hold,
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
    )


def range_reversal(
    df: pd.DataFrame,
    *,
    lookback: int = 24,
    entry_z: float = 1.5,
    max_hold: int = 8,
    start_hour: int = 7,
    end_hour: int = 16,
) -> StrategyResult:
    """Reversión a la media dentro de un rango móvil y una sesión."""
    close = df["close"]
    mean = close.rolling(lookback).mean()
    std = close.rolling(lookback).std(ddof=0).replace(0.0, np.nan)
    zscore = (close - mean) / std
    mask = _session_mask(df.index, start_hour, end_hour)
    target = pd.Series(0.0, index=df.index)
    pos, hold = 0.0, 0
    for ts in df.index:
        value = float(zscore.loc[ts]) if np.isfinite(zscore.loc[ts]) else 0.0
        if not bool(mask.loc[ts]) or not np.isfinite(zscore.loc[ts]):
            pos, hold = 0.0, 0
            target.loc[ts] = 0.0
            continue
        if pos == 0.0:
            if value <= -entry_z:
                pos = 1.0
            elif value >= entry_z:
                pos = -1.0
        else:
            hold += 1
            if hold >= max_hold or (pos > 0 and value >= 0.0) or (pos < 0 and value <= 0.0):
                pos, hold = 0.0, 0
        target.loc[ts] = pos
    return StrategyResult(
        "range_reversal",
        target,
        {
            "lookback": lookback,
            "entry_z": entry_z,
            "max_hold": max_hold,
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
    )


def orb_ny(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=13, end_hour=20, **kwargs)


def trend_intraday(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=13, end_hour=20, **kwargs)


def overlap_breakout(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=12, end_hour=16, **kwargs)


def london_pullback(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=7, end_hour=16, **kwargs)


def session_trend(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=0, end_hour=16, **kwargs)


def tokyo_breakout(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=0, end_hour=3, **kwargs)


def asian_range_reversal(
    df: pd.DataFrame,
    *,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
) -> StrategyResult:
    """Reversión en el rango asiático (00:00-07:00 UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    for day in sorted({ts.date() for ts in df.index}):
        day_mask = pd.Index(df.index.date) == day
        asian = df[day_mask & (pd.Index(df.index.hour) < 7)]
        rest = df[day_mask & (pd.Index(df.index.hour) >= 7)]
        if len(asian) < 4 or rest.empty:
            continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        pos, hold = 0.0, 0
        for ts, row in rest.iterrows():
            if pos == 0.0:
                atr_value = float(atr_s.loc[ts])
                if row["close"] > hi + buffer_atr * atr_value:
                    pos = -1.0
                elif row["close"] < lo - buffer_atr * atr_value:
                    pos = 1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos, hold = 0.0, 0
            target.loc[ts] = pos
    return StrategyResult(
        "asian_rev",
        target,
        {"buffer_atr": buffer_atr, "max_hold": max_hold},
    )


STRATEGIES = {
    "orb": opening_range_breakout,
    "pullback": trend_pullback,
    "asian_rev": asian_range_reversal,
    "orb_ny": orb_ny,
    "trend_intraday": trend_intraday,
    "overlap_breakout": overlap_breakout,
    "range_reversal": range_reversal,
    "london_pullback": london_pullback,
    "session_trend": session_trend,
    "tokyo_breakout": tokyo_breakout,
}


def _combos(grid: dict[str, list]) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _aligned(series: dict[str, pd.Series]) -> tuple[np.ndarray, list[str]] | None:
    if len(series) < 2:
        return None
    frame = pd.concat(series, axis=1, join="inner").dropna()
    if len(frame) < 80:
        return None
    return returns_matrix({k: frame[k].to_numpy(dtype=float) for k in frame.columns})


def _failure_reason(
    row: dict,
    *,
    profile,
    pbo: dict | None,
    wf_verdict: str,
) -> str:
    """Motivo de descarte de una variante (vacío si pasó)."""
    if row.get("passed"):
        return ""
    parts: list[str] = []
    metrics = row.get("metrics") or {}
    if int(metrics.get("num_trades", 0)) < profile.validation.min_trades:
        parts.append(
            f"trades {int(metrics.get('num_trades', 0))} < {profile.validation.min_trades}"
        )
    dsr = row.get("dsr")
    if dsr is None or dsr < profile.validation.min_dsr:
        parts.append(f"DSR {(dsr or 0):.0%} < {profile.validation.min_dsr:.0%}")
    if pbo is None:
        parts.append("PBO sin datos")
    elif pbo.get("pbo", 1.0) > profile.validation.max_pbo:
        parts.append(f"PBO {pbo['pbo']:.0%} > {profile.validation.max_pbo:.0%}")
    if wf_verdict != "ok":
        parts.append(f"WF {wf_verdict}")
    if not (row.get("regime_gate") or {}).get("passed"):
        parts.append("régimen no aprobado")
    if not row.get("spread_reliable"):
        parts.append("spread no fiable")
    return "; ".join(parts)


def run_intraday(
    df: pd.DataFrame,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    paths: int = 500,
    point: float = 0.0001,
    commission_bps: float | None = None,
    slippage_bps: float | None = None,
    slippage_optimistic_bps: float | None = None,
    spread_override_bps: float | None = None,
    db_path: str | Path | None = None,
    run_id: str | None = None,
    lesson_id: int | None = None,
    record: bool = True,
    families: tuple[str, ...] | None = None,
) -> dict:
    """Valida las estrategias intradía con los controles existentes."""
    profile = get_profile("intraday_fx")
    if profile is None:
        raise RuntimeError("falta perfil intraday_fx")
    asset = asset_costs(symbol)
    if commission_bps is None:
        if not asset.verified:
            raise RuntimeError(
                f"comisión sin verificar para {symbol}: no se inventa la cifra"
            )
        commission = asset.commission_bps(df["close"])
        commission_source = asset.source or "sin verificar"
        commission_verified = True
    else:
        commission = float(commission_bps)
        commission_source = "override diagnóstico"
        commission_verified = False
    if slippage_bps is None:
        slippage_bps = asset.slippage_conservative_bps
    if slippage_optimistic_bps is None:
        slippage_optimistic_bps = asset.slippage_optimistic_bps
    commission_median = (
        float(commission.median())
        if isinstance(commission, pd.Series)
        else float(commission)
    )
    selected_families = tuple(families) if families else families_for_symbol(symbol)
    unknown = [name for name in selected_families if name not in INTRADAY_GRIDS]
    if unknown:
        raise ValueError(f"familias intradía desconocidas: {', '.join(unknown)}")
    outcomes = []
    returns_by_id: dict[str, pd.Series] = {}
    for name in selected_families:
        grid = INTRADAY_GRIDS[name]
        for params in _combos(grid):
            result = STRATEGIES[name](df, **params)
            bt = backtest_intraday(
                df,
                result.target,
                timeframe=timeframe,
                commission_bps=commission,
                slippage_bps=slippage_bps,
                slippage_optimistic_bps=slippage_optimistic_bps,
                point=point,
                spread_override_bps=spread_override_bps,
            )
            key = f"{name}|{json.dumps(params, sort_keys=True)}"
            returns_by_id[key] = bt["returns"]
            outcomes.append(
                {
                    "strategy": name,
                    "params": params,
                    "metrics": bt["metrics"],
                    "spread_bps_median": bt["spread_bps_median"],
                    "spread_observed_bps_median": bt["spread_observed_bps_median"],
                    "spread_reliable": bt["spread_reliable"],
                    "commission_bps_median": bt["commission_bps_median"],
                    "calibrated_cost_bps": bt["calibrated_cost_bps"],
                    "breakeven_cost_bps": bt["breakeven_cost_bps"],
                    "cost_curve_bps": bt["cost_curve_bps"],
                    "sharpe_optimistic": bt["sharpe_optimistic"],
                    "sharpe_conservative": bt["sharpe_conservative"],
                }
            )

    sr_values = [row["metrics"]["sharpe"] for row in outcomes]
    sr_std = float(np.std(sr_values, ddof=1)) if len(sr_values) > 1 else 0.0
    n_trials_dsr = len(outcomes) + (
        count_tests(db_path) if db_path is not None else 0
    )
    for row in outcomes:
        row["dsr"] = deflated_sharpe(
            row["metrics"]["sharpe"],
            int(row["metrics"]["bars"]),
            0.0,
            3.0,
            sr_std,
            n_trials_dsr,
        )
        row["dsr_n_trials"] = n_trials_dsr

    aligned = _aligned(returns_by_id)
    pbo = None
    if aligned is not None:
        matrix, _ = aligned
        try:
            pbo = cscv_pbo(matrix, n_slices=16, max_combinations=2_000).to_dict()
        except ValueError:
            pbo = None
    train_len = min(2_016, max(126, len(df) // 4))
    test_len = min(504, max(21, len(df) // 12))
    wf = None
    if aligned is not None:
        try:
            wf = walk_forward(aligned[0], train_len=train_len, test_len=test_len)
        except ValueError:
            wf = None

    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        report = regime_report(returns_by_id[key])
        gate = regime_gate(report)
        row["regime_report"] = report.to_dict()
        row["regime_gate"] = gate.to_dict()
        row["wf_verdict"] = wf.verdict() if wf else "sin datos"
        row["pbo"] = pbo["pbo"] if pbo else None
        row["passed"] = bool(
            row["metrics"]["num_trades"] >= profile.validation.min_trades
            and row["dsr"] is not None
            and row["dsr"] >= profile.validation.min_dsr
            and pbo is not None
            and pbo["pbo"] <= profile.validation.max_pbo
            and wf is not None
            and wf.verdict() == "ok"
            and gate.passed
            and row["spread_reliable"]
        )
        if (
            spread_override_bps == 0
            and commission_median == 0
            and slippage_bps == 0
            and slippage_optimistic_bps == 0
        ):
            # Diagnóstico: nunca cuenta como candidato que avanza.
            row["passed_zero_cost_diagnostic"] = row["passed"]
            row["passed"] = False
        row["failure_reason"] = _failure_reason(
            row,
            profile=profile,
            pbo=pbo,
            wf_verdict=wf.verdict() if wf else "sin datos",
        )

    rules = [from_yaml("ftmo", "challenge", 100_000), from_yaml("topstep", "challenge", 50_000)]
    mc = []
    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        for rule in rules:
            for horizon in DEFAULT_HORIZONS:
                sim = monte_carlo(
                    rule,
                    returns_by_id[key].to_numpy(),
                    n_paths=max(50, paths),
                    horizon=horizon,
                    block_size=5,
                    seed=42,
                )
                mc.append(
                    {
                        "firm": rule.firm,
                        "strategy": row["strategy"],
                        "params": row["params"],
                        "horizon": horizon,
                        "pass_rate": sim["pass_rate"],
                        "breach_rate": sim["breach_rate"],
                    }
                )
    calibrated_values = [
        row["calibrated_cost_bps"]
        for row in outcomes
        if row["calibrated_cost_bps"] is not None
    ]
    run = run_id or uuid.uuid4().hex[:12]
    window_start = str(df.index[0].date()) if len(df.index) else None
    window_end = str(df.index[-1].date()) if len(df.index) else None
    lesson_hypothesis = ""
    if lesson_id is not None:
        lesson = get_lesson(db_path or DEFAULT_DB, lesson_id)
        lesson_hypothesis = str(lesson.get("hypothesis") or "")
    recorded = 0
    if record and db_path is not None:
        for row in outcomes:
            record_trial(
                db_path,
                family=row["strategy"],
                hypothesis=lesson_hypothesis
                or FAMILY_HYPOTHESES.get(
                    row["strategy"], f"Familia intradía {row['strategy']}."
                ),
                symbol=symbol,
                params=row["params"],
                window_start=window_start,
                window_end=window_end,
                result={
                    "metrics": row["metrics"],
                    "dsr": row.get("dsr"),
                    "pbo": row.get("pbo"),
                    "wf_verdict": row.get("wf_verdict"),
                    "regime_passed": (row.get("regime_gate") or {}).get("passed"),
                    "calibrated_cost_bps": row.get("calibrated_cost_bps"),
                    "breakeven_cost_bps": row.get("breakeven_cost_bps"),
                    "cost_curve_bps": row.get("cost_curve_bps"),
                    "passed": row.get("passed"),
                },
                outcome="passed" if row.get("passed") else "failed",
                reason=row.get("failure_reason", ""),
                source="lesson" if lesson_id is not None else "sweep",
                run_id=run,
                lesson_id=lesson_id,
            )
            recorded += 1
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": cache_metadata(df, timeframe),
        "profile": profile.id,
        "run_id": run,
        "trials_recorded": recorded,
        "window": {"start": window_start, "end": window_end},
        "dsr_n_trials": n_trials_dsr,
        "families": list(selected_families),
        "costs": {
            "commission_bps_median": commission_median,
            "commission_source": commission_source,
            "commission_verified": commission_verified,
            "slippage_bps": float(slippage_bps),
            "slippage_optimistic_bps": float(slippage_optimistic_bps),
            "spread_override_bps": spread_override_bps,
            "diagnostic_zero_costs": spread_override_bps == 0
            and commission_median == 0
            and slippage_bps == 0
            and slippage_optimistic_bps == 0,
        },
        "cost_model": {
            "symbol": symbol,
            "commission": {
                "verified": commission_verified,
                "per_lot_usd": asset.commission_per_lot_usd,
                "side": asset.commission_side,
                "source": commission_source,
                "source_date": asset.source_date,
                "effective_from": asset.effective_from,
                "source_url": asset.source_url,
                "median_bps": commission_median,
                "verified_at": "2026-11-08",
            },
            "spread": {
                "source": "MT5 bars: columna spread, mediana por hora",
                "hourly": True,
                "median_bps": (
                    float(np.median([row["spread_bps_median"] for row in outcomes]))
                    if outcomes
                    else None
                ),
                "reliable": all(row["spread_reliable"] for row in outcomes),
            },
            "slippage": {
                "optimistic_bps": float(slippage_optimistic_bps),
                "conservative_bps": float(slippage_bps),
                "assumption": asset.slippage_assumption,
            },
            "calibrated_cost_bps_median": (
                float(np.median(calibrated_values)) if calibrated_values else None
            ),
            "breakeven_definition": (
                "bps uniformes por unidad de turnover a los que el Sharpe neto "
                "cruza 0; 0 si el Sharpe bruto ya es <= 0"
            ),
        },
        "spread_reliable": all(row["spread_reliable"] for row in outcomes),
        "pbo": pbo,
        "walk_forward": wf.to_dict() if wf else None,
        "walk_forward_verdict": wf.verdict() if wf else "sin datos",
        "n_trials": len(outcomes),
        "passed": sum(1 for row in outcomes if row["passed"]),
        "outcomes": outcomes,
        "monte_carlo": mc,
    }


def render_markdown(report: dict) -> str:
    costs = report.get("costs") or {}
    model = report.get("cost_model") or {}
    commission = model.get("commission") or {}
    spread_model = model.get("spread") or {}
    slippage = model.get("slippage") or {}
    commission_bps = costs.get("commission_bps_median")
    spread_bps = spread_model.get("median_bps")
    lines = [
        "# Investigación intradía forex/CFD",
        "",
        f"- Símbolo: {report['symbol']} · {report['timeframe']}",
        f"- Barras: {report['bars']['rows']:,} · {report['bars']['start']} → {report['bars']['end']} · {report['bars']['years']} años",
        f"- Perfil: {report['profile']} · DSR n_trials={report['n_trials']}",
        f"- Spread realista: {'sí' if report['spread_reliable'] else 'NO — resultados no confiables'}",
        (
            f"- Comisión: {commission_bps:.3f} bps/lado · "
            f"{commission.get('source') or 'sin verificar'}"
            f"{' · ' + str(commission.get('source_date')) if commission.get('source_date') else ''}"
        ),
        (
            f"- Spread: {spread_bps:.3f} bps (mediana; {spread_model.get('source') or 'sin datos'})"
            if spread_bps is not None
            else "- Spread: sin datos"
        ),
        (
            f"- Slippage: optimista {slippage.get('optimistic_bps')} bps / "
            f"conservador {slippage.get('conservative_bps')} bps por lado"
        ),
        (
            "- **Diagnóstico zero-cost: no usar para aprobar estrategias.**"
            if costs.get("diagnostic_zero_costs")
            else "- Modelo de costes calibrado; el avance usa el escenario conservador."
        ),
        f"- PBO: {report['pbo']['pbo']:.1%}" if report.get("pbo") else "- PBO: sin datos",
        f"- Walk-forward: {report['walk_forward_verdict']}",
        f"- Pasan: {report['passed']}/{len(report['outcomes'])}",
        "",
        "> Solo informativo; no activa bots ni cambia criterios. "
        "El riesgo intradía real puede ser mayor que el modelado.",
        "",
        "## Estrategias",
        "",
        "| Estrategia | Parámetros | Trades | Sharpe | MaxDD | DSR | WF | Régimen | Spread | Pasa |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["outcomes"]:
        lines.append(
            f"| {row['strategy']} | `{row['params']}` | {row['metrics']['num_trades']} | "
            f"{row['metrics']['sharpe']:.2f} | {row['metrics']['max_drawdown']:.1%} | "
            f"{(row['dsr'] or 0):.1%} | {row['wf_verdict']} | "
            f"{'ok' if row['regime_gate']['passed'] else 'no'} | "
            f"{'sí' if row['spread_reliable'] else 'no'} | "
            f"{'sí' if row['passed'] else 'no'} |"
        )
    def _cost_text(value: float | None) -> str:
        return "—" if value is None else f"{value:.2f}"

    lines += [
        "",
        "## Coste de equilibrio",
        "",
        "> Coste uniforme en bps por unidad de turnover. 0 bps = bruto; "
        "el avance solo usa el escenario conservador.",
        "",
        "| Estrategia | Parámetros | 0 bps | 0.5 bps | 1 bps | 2 bps | 3 bps | Equilibrio | Calibrado | Pasa |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["outcomes"]:
        curve = row.get("cost_curve_bps") or {}
        breakeven = row.get("breakeven_cost_bps")
        lines.append(
            f"| {row['strategy']} | `{row['params']}` | "
            f"{_cost_text(curve.get('0.0'))} | {_cost_text(curve.get('0.5'))} | "
            f"{_cost_text(curve.get('1.0'))} | {_cost_text(curve.get('2.0'))} | "
            f"{_cost_text(curve.get('3.0'))} | "
            f"{'sin cruce' if breakeven is None else f'{breakeven:.2f}'} | "
            f"{_cost_text(row.get('calibrated_cost_bps'))} | "
            f"{'sí' if row.get('passed') else 'no'} |"
        )
    lines += [
        "",
        "## Monte Carlo 22/44/120d",
        "",
        "| Firma | Estrategia | Horizonte | Pasa | Revienta |",
        "|---|---|---|---|---|",
    ]
    for row in report["monte_carlo"][:40]:
        lines.append(
            f"| {row['firm']} | {row['strategy']} | {row['horizon']}d | "
            f"{row['pass_rate']:.1%} | {row['breach_rate']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def write(report: dict, out_dir: str | Path = ROOT / "reports" / "research") -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "intraday.json"
    md_path = out / "intraday.md"
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    markdown = render_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    safe = "".join(
        char if char.isalnum() or char in "-_." else "_"
        for char in str(report.get("symbol") or "sin_datos").upper()
    )
    asset_dir = out / "intraday"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_json = asset_dir / f"{safe}.json"
    asset_md = asset_dir / f"{safe}.md"
    asset_json.write_text(text, encoding="utf-8")
    asset_md.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path),
        "md": str(md_path),
        "asset_json": str(asset_json),
        "asset_md": str(asset_md),
    }


__all__ = [
    "DEFAULT_HORIZONS",
    "INTRADAY_GRIDS",
    "STRATEGIES",
    "asian_range_reversal",
    "backtest_intraday",
    "break_even_cost_bps",
    "cache_file",
    "cache_metadata",
    "load_bars",
    "opening_range_breakout",
    "render_markdown",
    "run_intraday",
    "save_bars",
    "trend_pullback",
]
