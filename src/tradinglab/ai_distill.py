"""Destilación semanal del carril IA discrecional.

Convierte una celda ganadora del carril IA en un bot determinista con un filtro
legible (árbol de profundidad <= 2, sin sklearn) y lo valida con el embudo del
laboratorio: backtest con costes, DSR, PBO, walk-forward y Monte Carlo FTMO.

Nunca activa nada: el bot candidato se escribe con ``enabled: false`` y la
incubación solo congela criterios. La promoción final sigue siendo del operador.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .ai_trader import (
    NEW_YORK,
    _as_utc,
    _bootstrap_ci,
    _cell_status,
    _snapshot_condition,
)
from .ai_trader import (
    load_config as load_ai_config,
)
from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .db import connect, init_db, utcnow
from .learning import count_tests
from .trials import record_trial

AI_CONFIG = ROOT / "config" / "ai_trader.yaml"
INTRADAY_BOTS = ROOT / "config" / "intraday_bots.yaml"
SWING_BOTS = ROOT / "config" / "bots.yaml"
FORWARD_CONFIG = ROOT / "config" / "intraday_forward.yaml"
DOCS_PATH = ROOT / "docs" / "ai_trader_skill.md"
SKILL_PATH = (
    Path.home() / ".config" / "opencode" / "skills" /
    "trading-lab-operador" / "SKILL.md"
)
MIN_CELL_N = 30
MIN_RULE_SUPPORT = 8
MIN_RULE_GAIN = 0.02
MIN_PLAN_N = 30
FEATURES = (
    "session", "is_index", "trend_d1", "trend_h4", "bb_squeeze",
    "sweep_high", "sweep_low", "inside_bar", "rsi2_lt10", "cost_r",
    "hour_ny", "weekday",
)
SCALPING_CRITERIA = {
    "window_days": 60,
    "min_trades": 15,
    "min_forward_sharpe": 0.0001,
    "max_slippage_bps": 3.0,
    "max_guard_breaches": 0,
    "max_drift_status": "ok",
    "require_tick_confirmation": True,
}


class DistillError(ValueError):
    pass


# ------------------------------------------------------------------ utilidades


def _stamp(value) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json(value) -> dict | list | None:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return None
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return None


def _seed(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def _bot_id(strategy: str, symbol: str, timeframe: str) -> str:
    raw = f"ai-{strategy}-{symbol}-{timeframe}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


def _profile_for(style: str) -> str:
    return "swing_cfd" if style == "swing" else "intraday_fx"


def _config_for(style: str, timeframe: str) -> Path:
    if style == "swing" or str(timeframe).upper() in {"H4", "D1"}:
        return SWING_BOTS
    return INTRADAY_BOTS


# ------------------------------------------------------------------ aprendizaje


def _decision_rows(
    db_path: str | Path,
    *,
    style: str,
    symbol: str,
    strategy: str,
    timeframe: str,
    version: int,
) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = [dict(row) for row in con.execute(
            "SELECT d.id, d.ts, d.decision, d.snapshot, d.plan_id, "
            "t.result_r, t.cost_ratio, p.bias AS plan_bias, "
            "p.forbidden_hours AS plan_forbidden "
            "FROM ai_decisions d "
            "LEFT JOIN ai_trades t ON t.proposal_id = d.plan_id "
            "LEFT JOIN ai_plans p ON p.plan_id = d.plan_id "
            "WHERE d.source='forward' AND d.setup_valid=1 "
            "AND d.decision IN ('take','skip') "
            "AND d.style=? AND d.symbol=? AND d.strategy=? AND d.timeframe=? "
            "AND d.playbook_version=? ORDER BY d.id",
            (style, symbol, strategy, timeframe, int(version)),
        ).fetchall()]
    out: list[dict] = []
    for row in rows:
        snapshot = _json(row.get("snapshot"))
        if not isinstance(snapshot, dict):
            snapshot = {}
        features = _features(row, snapshot, timeframe)
        if not features:
            continue
        out.append({
            **row,
            "features": features,
            "target": 1 if row["decision"] == "take" else 0,
        })
    return out


def _features(row: dict, snapshot: dict, timeframe: str) -> dict:
    out: dict = {}
    for field in FEATURES:
        if field in {"cost_r", "hour_ny", "weekday"}:
            continue
        try:
            value = _snapshot_condition(snapshot, field, timeframe)
        except Exception:
            value = None
        if value is None:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        out[field] = value
    cost = _float(row.get("cost_ratio"))
    if cost is None:
        costs = snapshot.get("cost_r") or {}
        if isinstance(costs, dict):
            cost = _float(costs.get(str(timeframe).upper()))
    if cost is not None:
        out["cost_r"] = round(cost, 6)
    try:
        local = _stamp(row.get("ts")).astimezone(NEW_YORK)
        out["hour_ny"] = int(local.hour)
        out["weekday"] = int(local.weekday())
    except Exception:
        pass
    plan_bias = str(row.get("plan_bias") or "").strip().lower()
    if plan_bias:
        out["plan_bias"] = plan_bias
        forbidden = _json(row.get("plan_forbidden")) or []
        if isinstance(forbidden, list):
            out["plan_hours_allowed"] = _allowed_hour(
                out.get("hour_ny"), forbidden
            )
    return out


def _allowed_hour(hour: int | None, forbidden: list) -> bool:
    if hour is None:
        return True
    for raw in forbidden:
        try:
            start_s, end_s = str(raw).split("-", 1)
            start = int(start_s.split(":")[0])
            end = int(end_s.split(":")[0])
        except (TypeError, ValueError):
            continue
        if start <= end:
            if start <= hour < end:
                return False
        elif hour >= start or hour < end:
            return False
    return True


def _condition_text(field: str, op: str, value) -> str:
    if isinstance(value, bool):
        shown = "sí" if value else "no"
    elif isinstance(value, float):
        shown = f"{value:g}"
    else:
        shown = str(value)
    return f"{field} {op} {shown}"


def _matches(features: dict, condition: dict) -> bool:
    field = condition.get("field")
    if field not in features:
        return False
    actual = features[field]
    expected = condition.get("value")
    op = condition.get("op")
    if op == "==":
        if isinstance(actual, bool) or isinstance(expected, bool):
            return bool(actual) == bool(expected)
        return str(actual) == str(expected)
    try:
        left = float(actual)
        right = float(expected)
    except (TypeError, ValueError):
        return False
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    return False


def _match_all(features: dict, conditions: list[dict]) -> bool:
    return all(_matches(features, condition) for condition in conditions)


def _condition_candidates(rows: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for field in FEATURES:
        values = [row["features"].get(field) for row in rows]
        clean = [value for value in values if value is not None]
        if not clean:
            continue
        if isinstance(clean[0], bool):
            for value in (True, False):
                candidates.append({"field": field, "op": "==", "value": value})
            continue
        if isinstance(clean[0], (int, float)) and not isinstance(clean[0], bool):
            numeric = sorted({round(float(value), 8) for value in clean})
            if len(numeric) < 2:
                continue
            thresholds = sorted({
                round((left + right) / 2.0, 8)
                for left, right in zip(numeric, numeric[1:])
            })
            if len(thresholds) > 12:
                picks = np.linspace(0, len(thresholds) - 1, 12).astype(int)
                thresholds = [thresholds[index] for index in picks]
            for threshold in thresholds:
                candidates.append({
                    "field": field, "op": "<=", "value": threshold,
                })
                candidates.append({
                    "field": field, "op": ">", "value": threshold,
                })
            continue
        for value in sorted({str(item) for item in clean}):
            candidates.append({"field": field, "op": "==", "value": value})
    return candidates


def _rule_metrics(rows: list[dict], conditions: list[dict]) -> dict | None:
    total = len(rows)
    if total == 0:
        return None
    selected_flags = [
        _match_all(row["features"], conditions) for row in rows
    ]
    selected = [row for row, flag in zip(rows, selected_flags) if flag]
    if len(selected) < MIN_RULE_SUPPORT:
        return None
    total_take = sum(int(row["target"]) for row in rows)
    take = sum(int(row["target"]) for row in selected)
    outside = [row for row, flag in zip(rows, selected_flags) if not flag]
    outside_take = sum(int(row["target"]) for row in outside)
    true_negative = len(outside) - outside_take
    accuracy = (take + true_negative) / total
    precision = take / len(selected)
    coverage = len(selected) / total
    recall = take / total_take if total_take else 0.0
    return {
        "n": len(selected),
        "takes": take,
        "skips": len(selected) - take,
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "baseline": round(total_take / total, 4),
        "gain": round(accuracy - total_take / total, 4),
        "conditions": conditions,
        "description": " y ".join(
            _condition_text(item["field"], item["op"], item["value"])
            for item in conditions
        ),
    }


def learn_filter(rows: list[dict]) -> dict:
    """Árbol de profundidad <= 2; si no separa mejor que tomar siempre, vacío."""
    if not rows:
        return _empty_filter(0, 0, "sin filas")
    total_take = sum(int(row["target"]) for row in rows)
    baseline = total_take / len(rows)
    if total_take == 0 or total_take == len(rows):
        return _empty_filter(
            len(rows), total_take, "una sola clase: no hay separación"
        )
    candidates = _condition_candidates(rows)
    best: dict | None = None
    for root in candidates:
        subset = [
            row for row in rows if _matches(row["features"], root)
        ]
        if len(subset) < MIN_RULE_SUPPORT:
            continue
        for conditions in ([root],):
            score = _rule_metrics(rows, conditions)
            if score is not None and _better(score, best, baseline):
                best = score
        inner = _condition_candidates(subset)
        for child in inner:
            if child["field"] == root["field"]:
                continue
            conditions = [root, child]
            score = _rule_metrics(rows, conditions)
            if score is not None and _better(score, best, baseline):
                best = score
    if best is None or best["gain"] < MIN_RULE_GAIN:
        return _empty_filter(len(rows), total_take, "no separa mejor que tomar siempre")
    if best["precision"] < baseline + 0.02:
        return _empty_filter(len(rows), total_take, "precisión sin ventaja")
    return {
        "logic": "all",
        "conditions": best["conditions"],
        "description": best["description"],
        "n": best["n"],
        "takes": best["takes"],
        "skips": best["skips"],
        "coverage": best["coverage"],
        "precision": best["precision"],
        "recall": best["recall"],
        "accuracy": best["accuracy"],
        "baseline": best["baseline"],
        "gain": best["gain"],
        "empty": False,
    }


def _better(score: dict, best: dict | None, baseline: float) -> bool:
    if score["gain"] < MIN_RULE_GAIN:
        return False
    if best is None:
        return True
    return (
        score["accuracy"], score["precision"], score["coverage"],
        -len(score["conditions"]),
    ) > (
        best["accuracy"], best["precision"], best["coverage"],
        -len(best["conditions"]),
    )


def _empty_filter(n: int, takes: int, reason: str) -> dict:
    return {
        "logic": "all",
        "conditions": [],
        "description": "sin filtro: tomar siempre",
        "n": n,
        "takes": takes,
        "skips": max(0, n - takes),
        "coverage": 1.0 if n else 0.0,
        "precision": round(takes / n, 4) if n else None,
        "recall": 1.0 if takes else None,
        "accuracy": round(takes / n, 4) if n else None,
        "baseline": round(takes / n, 4) if n else None,
        "gain": 0.0,
        "empty": True,
        "reason": reason,
    }


def filter_applies(filter_payload: dict | None, features: dict) -> bool:
    if not filter_payload:
        return True
    conditions = filter_payload.get("conditions") or []
    if not conditions:
        return True
    return _match_all(features, conditions)


# ------------------------------------------------------------------ ganadoras


def winning_cells(
    db_path: str | Path = DEFAULT_DB,
    *,
    version: int | None = None,
) -> list[dict]:
    init_db(db_path)
    cfg = load_ai_config()
    playbook = int(version or cfg["playbook_version"])
    with connect(db_path) as con:
        rows = [dict(row) for row in con.execute(
            "SELECT style, symbol, setup AS strategy, timeframe, "
            "result_r, r_multiple, shadow2_r, ts "
            "FROM ai_trades WHERE COALESCE(source,'forward')='forward' "
            "AND status='closed' AND playbook_version=? "
            "ORDER BY ts",
            (playbook,),
        ).fetchall()]
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in rows:
        value = row.get("result_r")
        if value is None:
            value = row.get("r_multiple")
        value = _float(value)
        if value is None:
            continue
        key = (
            str(row.get("style") or "Sin datos"),
            str(row.get("symbol") or "Sin datos"),
            str(row.get("strategy") or "Sin datos"),
            str(row.get("timeframe") or "Sin datos"),
        )
        groups.setdefault(key, []).append({**row, "result_r": value})
    winners: list[dict] = []
    for key, items in sorted(groups.items()):
        style, symbol, strategy, timeframe = key
        values = [float(item["result_r"]) for item in items]
        if len(values) < MIN_CELL_N:
            continue
        seed = _seed(style, symbol, strategy, timeframe)
        ci = _bootstrap_ci(values, seed=seed)
        if not ci or ci[0] <= 0:
            continue
        plan = _plan_evidence(items, seed + 1)
        if style == "scalping":
            if (
                plan["n"] < MIN_PLAN_N
                or not plan["ci90"]
                or plan["ci90"][0] <= 0
            ):
                continue
        winners.append({
            "style": style, "symbol": symbol, "strategy": strategy,
            "timeframe": timeframe, "n": len(values),
            "avg_r": round(sum(values) / len(values), 4),
            "ci90": ci, "plan": plan if style == "scalping" else None,
        })
    return winners


def _plan_evidence(items: list[dict], seed: int) -> dict:
    pairs = [
        (float(item["result_r"]), _float(item.get("shadow2_r")))
        for item in items
        if _float(item.get("shadow2_r")) is not None
    ]
    values = [real - other for real, other in pairs]
    if not values:
        return {"n": 0, "diff": None, "ci90": None, "avg_noplan": None}
    return {
        "n": len(values),
        "diff": round(sum(values) / len(values), 4),
        "ci90": _bootstrap_ci(values, seed=seed),
        "avg_noplan": round(sum(other for _, other in pairs) / len(pairs), 4),
    }


# ------------------------------------------------------------------ histórico


def _load_history(
    symbol: str,
    timeframe: str,
    *,
    cache_dir: str | Path | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame | None:
    from .intraday import load_bars

    settings = settings or get_settings()
    root = Path(cache_dir) if cache_dir else settings.data.cache_dir
    try:
        frame = load_bars(root, symbol, timeframe)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if frame is not None and len(frame) >= 260:
        return frame
    return None


def _ensure_volume(df: pd.DataFrame) -> pd.DataFrame:
    if "volume" in df.columns:
        return df
    for column in ("tick_volume", "real_volume"):
        if column in df.columns:
            return df.assign(volume=df[column].clip(lower=0))
    return df.assign(volume=1.0)


def _map_daily(series: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    from .strategies.swing import trading_day

    shifted = series.shift(1)
    by_day = shifted.copy()
    by_day.index = pd.DatetimeIndex(by_day.index).normalize()
    by_day = by_day.groupby(level=0).last()
    days = trading_day(index)
    mapped = by_day.reindex(days)
    return pd.Series(
        mapped.to_numpy(), index=pd.DatetimeIndex(index)
    ).ffill()


def _historical_features(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    from .indicators import atr, ema, rsi
    from .intraday import _spread_bps
    from .strategies.swing import daily_bars

    df = _ensure_volume(df)
    frame = pd.DataFrame(index=df.index)
    frame["is_index"] = "US100" in symbol.upper()
    local = df.index.tz_convert(NEW_YORK)
    frame["hour_ny"] = local.hour
    frame["weekday"] = local.weekday
    frame["session"] = [
        "Asia" if hour < 7 else "Londres" if hour < 13
        else "Nueva York" if hour < 21 else "Fuera de sesión"
        for hour in local.hour
    ]
    daily = daily_bars(df)
    if len(daily) >= 20:
        trend = pd.Series(
            np.where(
                daily["close"] > daily["close"].rolling(200).mean(),
                "up", "down",
            ),
            index=daily.index,
        )
        frame["trend_d1"] = _map_daily(trend, df.index)
        rsi2 = rsi(daily["close"], 2)
        frame["rsi2_lt10"] = _map_daily(rsi2 < 10, df.index)
        prev_high = _map_daily(daily["high"], df.index)
        prev_low = _map_daily(daily["low"], df.index)
        frame["sweep_high"] = (
            (df["high"] > prev_high) & (df["close"] < prev_high)
        )
        frame["sweep_low"] = (
            (df["low"] < prev_low) & (df["close"] > prev_low)
        )
    h4 = df.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    if len(h4) >= 60:
        e9 = ema(h4["close"], 9)
        e21 = ema(h4["close"], 21)
        e50 = ema(h4["close"], 50)
        trend = pd.Series(
            np.where(e9 > e21, np.where(e21 > e50, "up", "flat"),
                     np.where(e21 < e50, "down", "flat")),
            index=h4.index,
        )
        frame["trend_h4"] = _map_daily(trend, df.index)
    close = df["close"]
    mean20 = close.rolling(20).mean()
    sd20 = close.rolling(20).std(ddof=0)
    width = 4 * sd20 / mean20
    frame["bb_squeeze"] = width <= width.rolling(120, min_periods=20).min()
    if str(timeframe).upper() in {"H4", "D1"} and len(df) >= 3:
        mother = df.shift(2)
        prev = df.shift(1)
        frame["inside_bar"] = (
            (prev["high"] <= mother["high"])
            & (prev["low"] >= mother["low"])
        )
    elif len(daily) >= 5:
        mother = daily.shift(2)
        prev = daily.shift(1)
        inside = (
            (prev["high"] <= mother["high"])
            & (prev["low"] >= mother["low"])
        )
        frame["inside_bar"] = _map_daily(inside, df.index).fillna(False)
    else:
        frame["inside_bar"] = False
    try:
        from .intraday_costs import asset_costs

        asset = asset_costs(symbol)
        commission = asset.commission_bps(close)
        point = 0.01 if "XAU" in symbol.upper() or "US100" in symbol.upper() else 0.0001
        spread, _ = _spread_bps(df, point)
        stop = atr(df).replace(0.0, np.nan)
        frame["cost_r"] = (
            (spread + commission + 1.0) / 10_000.0 * close / stop
        )
    except Exception:
        frame["cost_r"] = np.nan
    return frame


def _ai_signal(
    df: pd.DataFrame,
    strategy: str,
    timeframe: str,
) -> pd.Series:
    from .indicators import atr, ema, rsi
    from .intraday import (
        h1_orb_session,
        opening_range_breakout,
        range_reversal,
        trend_pullback,
    )
    from .strategies.swing import (
        atr_close_stop,
        daily_bars,
        daily_target_to_intraday,
    )

    df = _ensure_volume(df)
    if strategy in {"orb_ny", "orb_5m"}:
        bars = 4 if strategy == "orb_ny" else 3
        result = opening_range_breakout(
            df, range_bars=bars, buffer_atr=0.1, max_hold=8,
            start_hour=13, end_hour=17,
        )
        return result.target
    if strategy == "london_breakout":
        return h1_orb_session(df, session="LDN", max_hold=8).target
    if strategy in {"ema_pullback", "trend_pullback"}:
        return trend_pullback(
            df, fast=20, slow=50, pullback_atr=0.25, max_hold=8
        ).target
    if strategy in {"vwap_reversion", "vwap_bounce"}:
        return range_reversal(
            df, lookback=12, entry_z=1.5, max_hold=8
        ).target
    if strategy == "momentum_burst":
        atr_s = atr(df)
        span = df["high"] - df["low"]
        target = pd.Series(0.0, index=df.index)
        target[(span > 2 * atr_s) & (df["close"] >= df["low"] + 0.8 * span)] = 1.0
        target[(span > 2 * atr_s) & (df["close"] <= df["low"] + 0.2 * span)] = -1.0
        return target
    if strategy == "bollinger_squeeze":
        close = df["close"]
        mid = close.rolling(20).mean()
        sd = close.rolling(20).std(ddof=0)
        upper, lower = mid + 2 * sd, mid - 2 * sd
        width = (upper - lower) / mid
        squeeze = width <= width.rolling(120, min_periods=20).min()
        target = pd.Series(0.0, index=df.index)
        target[squeeze & (close > upper)] = 1.0
        target[squeeze & (close < lower)] = -1.0
        return target
    if strategy == "liquidity_sweep":
        daily = daily_bars(df)
        prev_high = _map_daily(daily["high"], df.index)
        prev_low = _map_daily(daily["low"], df.index)
        target = pd.Series(0.0, index=df.index)
        target[(df["high"] > prev_high) & (df["close"] < prev_high)] = -1.0
        target[(df["low"] < prev_low) & (df["close"] > prev_low)] = 1.0
        return target
    if strategy == "ema_ribbon_pullback":
        e8, e13, e21 = ema(df["close"], 8), ema(df["close"], 13), ema(df["close"], 21)
        target = pd.Series(0.0, index=df.index)
        up = (e8 > e13) & (e13 > e21) & (df["low"] <= e13) & (df["close"] > e13)
        down = (e8 < e13) & (e13 < e21) & (df["high"] >= e13) & (df["close"] < e13)
        target[up & (df["close"] > df["open"])] = 1.0
        target[down & (df["close"] < df["open"])] = -1.0
        return target
    if strategy == "rsi2_connors":
        daily = daily_bars(df)
        if len(daily) < 55:
            return pd.Series(0.0, index=df.index)
        close = daily["close"]
        enter = (close > close.rolling(200).mean()) & (rsi(close, 2) < 10)
        exit_ = close > close.rolling(5).mean()
        target = pd.Series(0.0, index=daily.index)
        position = 0.0
        for stamp in daily.index:
            if position == 0.0 and bool(enter.loc[stamp]):
                position = 1.0
            elif position != 0.0 and bool(exit_.loc[stamp]):
                position = 0.0
            target.loc[stamp] = position
        return daily_target_to_intraday(target, df.index)
    if strategy == "donchian_turtle":
        daily = daily_bars(df)
        if len(daily) < 60:
            return pd.Series(0.0, index=df.index)
        close = daily["close"]
        high20 = daily["high"].rolling(20).max().shift(1)
        low20 = daily["low"].rolling(20).min().shift(1)
        high55 = daily["high"].rolling(55).max().shift(1)
        low55 = daily["low"].rolling(55).min().shift(1)
        target = pd.Series(0.0, index=daily.index)
        target[(close > high20) & (close > high55)] = 1.0
        target[(close < low20) & (close < low55)] = -1.0
        target = target.replace(0.0, np.nan).ffill().fillna(0.0)
        return daily_target_to_intraday(target, df.index)
    if strategy == "inside_bar":
        daily = daily_bars(df)
        if len(daily) < 5:
            return pd.Series(0.0, index=df.index)
        mother = daily.shift(2)
        prev = daily.shift(1)
        inside = (prev["high"] <= mother["high"]) & (prev["low"] >= mother["low"])
        target = pd.Series(0.0, index=daily.index)
        target[inside & (daily["close"] > mother["high"])] = 1.0
        target[inside & (daily["close"] < mother["low"])] = -1.0
        return daily_target_to_intraday(target, df.index)
    if strategy == "trend_daily_atr":
        daily = daily_bars(df)
        if len(daily) < 60:
            return pd.Series(0.0, index=df.index)
        target = pd.Series(
            np.where(daily["close"] > daily["close"].rolling(100).mean(), 1.0, -1.0),
            index=daily.index,
        )
        mapped = daily_target_to_intraday(target, df.index)
        return atr_close_stop(mapped, df, stop_atr=2.0)
    raise DistillError(f"sin backtest para estrategia: {strategy}")


def _apply_filter_frame(
    frame: pd.DataFrame,
    filter_payload: dict,
) -> pd.Series:
    conditions = (filter_payload or {}).get("conditions") or []
    if not conditions:
        return pd.Series(True, index=frame.index)
    mask = pd.Series(True, index=frame.index)
    for condition in conditions:
        field = condition.get("field")
        if field not in frame.columns:
            return pd.Series(False, index=frame.index)
        series = frame[field]
        value = condition.get("value")
        if condition.get("op") == "==":
            if isinstance(value, bool):
                mask &= series.astype(bool) == bool(value)
            else:
                mask &= series.astype(str) == str(value)
        elif condition.get("op") == "<=":
            mask &= pd.to_numeric(series, errors="coerce") <= float(value)
        elif condition.get("op") == ">":
            mask &= pd.to_numeric(series, errors="coerce") > float(value)
        else:
            return pd.Series(False, index=frame.index)
    return mask.fillna(False)


def _variant(
    df: pd.DataFrame,
    signal: pd.Series,
    filter_payload: dict,
    *,
    symbol: str,
    timeframe: str,
    features: pd.DataFrame,
) -> dict:
    from .intraday import backtest_intraday
    from .intraday_costs import asset_costs

    asset = asset_costs(symbol)
    if not asset.verified:
        raise DistillError(f"comisión sin verificar para {symbol}")
    commission = asset.commission_bps(df["close"])
    point = 0.01 if "XAU" in symbol.upper() or "US100" in symbol.upper() else 0.0001
    allowed = _apply_filter_frame(features, filter_payload)
    target = signal.where(allowed, 0.0)
    bt = backtest_intraday(
        df, target, timeframe=timeframe,
        commission_bps=commission,
        slippage_bps=asset.slippage_conservative_bps,
        point=point,
    )
    return {
        "returns": bt["returns"],
        "metrics": bt["metrics"],
        "spread_reliable": bt["spread_reliable"],
        "calibrated_cost_bps": bt["calibrated_cost_bps"],
        "breakeven_cost_bps": bt["breakeven_cost_bps"],
        "spread_bps_median": bt["spread_bps_median"],
        "slippage_bps": asset.slippage_conservative_bps,
        "commission_bps": float(commission.median()),
        "target": target,
    }


def _validation_payload(
    variants: dict[str, dict],
    *,
    n_trials: int,
    profile,
    db_path: str | Path = DEFAULT_DB,
) -> dict:
    from .global_dsr import global_srs
    from .prop.rules import from_yaml
    from .prop.simulator import monte_carlo
    from .stats import dsr_local_global, period_sharpe
    from .validation import cscv_pbo, returns_matrix
    from .walkforward import regime_gate, regime_report, walk_forward

    trial_srs = [
        period_sharpe(item["returns"]) for item in variants.values()
    ]
    sr_std = float(np.std(trial_srs, ddof=0)) if len(trial_srs) > 1 else 0.0
    global_info = global_srs(db_path, "daily")
    series = {name: item["returns"].to_numpy(dtype=float) for name, item in variants.items()}
    matrix, _ = returns_matrix(series)
    pbo = None
    try:
        pbo = cscv_pbo(matrix, n_slices=8, max_combinations=2_000).to_dict()
    except ValueError:
        pbo = None
    wf = None
    try:
        train_len = max(126, min(2_016, len(matrix) // 4))
        test_len = max(21, min(504, len(matrix) // 12))
        wf = walk_forward(matrix, train_len=train_len, test_len=test_len)
    except ValueError:
        wf = None
    rules = from_yaml("ftmo", "challenge", 100_000)
    for name, item in variants.items():
        metrics = item["metrics"]
        metrics["sharpe"] = float(metrics.get("sharpe") or 0.0)
        pair = dsr_local_global(
            item["returns"],
            trial_srs,
            global_info["srs"],
            len(trial_srs),
            n_trials,
            global_sources=global_info["sources"],
            frequency="daily",
        )
        local = pair["local"]
        global_payload = pair["global"]
        metrics["dsr_local"] = local["dsr"]
        metrics["dsr_global"] = global_payload["dsr"]
        metrics["dsr"] = global_payload["dsr"]
        metrics["dsr_gate"] = (
            "global" if global_payload["dsr"] is not None else "pendiente"
        )
        metrics["metric_version"] = local["metric_version"]
        metrics["dsr_local_meta"] = local
        metrics["dsr_global_meta"] = global_payload
        returns = item["returns"]
        daily = returns.resample("1D").sum()
        try:
            mc = monte_carlo(
                rules, daily.to_numpy(), n_paths=1_000, horizon=60,
                block_size=5, seed=42,
            ) if len(daily) >= 5 else None
        except Exception:
            mc = None
        report = regime_report(returns)
        gate = regime_gate(report)
        item["dsr"] = metrics["dsr"]
        item["pbo"] = pbo["pbo"] if pbo else None
        item["wf_verdict"] = wf.verdict() if wf else "sin datos"
        item["regime_gate"] = gate.to_dict()
        item["monte_carlo"] = mc
        item["passed"] = bool(
            int(metrics.get("num_trades") or 0) >= profile.validation.min_trades
            and metrics["dsr"] is not None
            and metrics["dsr"] >= profile.validation.min_dsr
            and pbo is not None
            and pbo["pbo"] <= profile.validation.max_pbo
            and wf is not None
            and wf.verdict() == "ok"
            and gate.passed
            and bool(item.get("spread_reliable"))
            and mc is not None
            and float(mc.get("pass_rate") or 0.0) >= 0.35
            and float(mc.get("breach_rate") or 1.0) <= 0.15
        )
    return {
        "n_trials": n_trials,
        "sr_std": round(sr_std, 6),
        "pbo": pbo,
        "walk_forward": wf.to_dict() if wf else None,
        "variants": {
            name: {
                "sharpe": item["metrics"]["sharpe"],
                "num_trades": int(item["metrics"].get("num_trades") or 0),
                "dsr": item["metrics"]["dsr"],
                "pbo": item["pbo"],
                "wf_verdict": item["wf_verdict"],
                "regime_gate": item["regime_gate"],
                "spread_reliable": item.get("spread_reliable"),
                "calibrated_cost_bps": item.get("calibrated_cost_bps"),
                "breakeven_cost_bps": item.get("breakeven_cost_bps"),
                "slippage_bps": item.get("slippage_bps"),
                "monte_carlo": item.get("monte_carlo"),
                "passed": item["passed"],
            }
            for name, item in variants.items()
        },
    }


def validate_candidate(
    *,
    symbol: str,
    strategy: str,
    timeframe: str,
    style: str,
    filter_payload: dict,
    db_path: str | Path = DEFAULT_DB,
    cache_dir: str | Path | None = None,
    settings: Settings | None = None,
) -> dict:
    from .profiles import get_profile

    settings = settings or get_settings()
    profile = get_profile(_profile_for(style))
    if profile is None:
        return {"ok": False, "reason": f"perfil no disponible: {style}"}
    df = _load_history(
        symbol, timeframe, cache_dir=cache_dir, settings=settings
    )
    if df is None or len(df) < 260:
        return {"ok": False, "reason": f"Sin datos de {symbol} {timeframe}"}
    try:
        signal = _ai_signal(df, strategy, timeframe)
        features = _historical_features(df, symbol, timeframe)
        variants = {
            "sin_filtro": _variant(
                df, signal, {}, symbol=symbol, timeframe=timeframe,
                features=features,
            ),
            "con_filtro": _variant(
                df, signal, filter_payload, symbol=symbol, timeframe=timeframe,
                features=features,
            ),
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:300]}
    n_trials = count_tests(db_path) + 2
    payload = _validation_payload(
        variants, n_trials=n_trials, profile=profile, db_path=db_path
    )
    unfiltered = payload["variants"]["sin_filtro"]
    filtered = payload["variants"]["con_filtro"]
    filtered_wins = bool(
        filtered["passed"]
        and filtered["sharpe"] > unfiltered["sharpe"]
    )
    winner = None
    if filtered_wins:
        winner = "con_filtro"
    elif unfiltered["passed"]:
        winner = "sin_filtro"
    payload.update({
        "ok": True,
        "window": {
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "bars": len(df),
        },
        "winner": winner,
        "reason": (
            "sin versión que pase el embudo"
            if winner is None
            else f"pasa {winner}"
        ),
    })
    return payload


# ------------------------------------------------------------------ configuración


def _allocate_magic(paths: list[Path]) -> int:
    used: set[int] = set()
    for path in paths:
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for style in (data.get("styles") or {}).values():
            try:
                used.add(int(style.get("magic")))
            except (TypeError, ValueError):
                continue
        for item in data.get("bots") or []:
            try:
                used.add(int(item.get("magic")))
            except (TypeError, ValueError):
                continue
    magic = 20262100
    while magic in used:
        magic += 1
    return magic


def _append_bot(path: str | Path, candidate: dict) -> bool:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text) or {}
    bots = loaded.get("bots") if isinstance(loaded, dict) else None
    if isinstance(bots, list) and any(
        str(item.get("id")) == candidate["id"] for item in bots
    ):
        return False
    block = yaml.safe_dump(
        [candidate], sort_keys=False, allow_unicode=True,
        default_flow_style=False,
    )
    block = "\n".join(f"  {line}" for line in block.rstrip().splitlines())
    target.write_text(text.rstrip() + "\n\n" + block + "\n", encoding="utf-8")
    check = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not any(
        str(item.get("id")) == candidate["id"]
        for item in (check.get("bots") or [])
    ):
        raise DistillError(f"no se pudo escribir el candidato en {target}")
    return True


def _candidate_payload(
    *,
    cell: dict,
    bot: str,
    filter_payload: dict,
    validation: dict,
    config: dict | None = None,
    magic: int | None = None,
) -> dict:
    cfg = config or load_ai_config()
    from .ai_setups import describe as describe_setups

    style = cfg["styles"][cell["style"]]
    chosen = validation["variants"][validation["winner"]]
    description = (
        f"{cell['strategy']} {cell['symbol']} {cell['timeframe']} · "
        f"origen destilado de ia-discrecional · {filter_payload['description']}"
    )
    return {
        "id": bot,
        "type": "deterministic",
        "profile": _profile_for(cell["style"]),
        "cluster": "ai_distilled",
        "account": "ftmo_demo",
        "strategy": cell["strategy"],
        "universe": [cell["symbol"]],
        "timeframe": cell["timeframe"],
        "enabled": False,
        "exposure": 1.0,
        "magic": int(magic or _allocate_magic([AI_CONFIG, INTRADAY_BOTS, SWING_BOTS])),
        "risk_per_trade": float(style["risk_per_trade"]),
        "origin": "destilado de ia-discrecional",
        "playbook_version": int(cfg["playbook_version"]),
        "filter": filter_payload,
        "params": {
            "catalog": describe_setups().get(cell["strategy"], ""),
            "source_cell": {
                "style": cell["style"], "symbol": cell["symbol"],
                "strategy": cell["strategy"], "timeframe": cell["timeframe"],
            },
            "validation": {
                "winner": validation["winner"],
                "sharpe": chosen["sharpe"],
                "dsr": chosen["dsr"],
                "pbo": chosen["pbo"],
                "wf": chosen["wf_verdict"],
            },
        },
        "description": description,
    }


def _mark_cell(db_path: str | Path, cell: dict, bot: str, version: int) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, "
            "reason, updated_at) VALUES(?,?,?,'destilada',?,?) "
            "ON CONFLICT(strategy,symbol,timeframe) DO UPDATE SET "
            "status='destilada', reason=excluded.reason, "
            "updated_at=excluded.updated_at",
            (
                cell["strategy"], cell["symbol"], cell["timeframe"],
                f"destilada a {bot} (playbook v{version})", utcnow(),
            ),
        )


def _record_run(
    db_path: str | Path,
    *,
    cell: dict,
    bot: str,
    status: str,
    reason: str,
    filter_payload: dict,
    evidence: dict,
    validation: dict | None,
    version: int,
) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO ai_distill_runs(ts, style, symbol, strategy, timeframe, "
            "bot, status, reason, filter, evidence, validation, playbook_version) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(), cell["style"], cell["symbol"], cell["strategy"],
                cell["timeframe"], bot, status, reason[:1000],
                json.dumps(filter_payload, ensure_ascii=False, sort_keys=True),
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                json.dumps(validation or {}, ensure_ascii=False, sort_keys=True),
                int(version),
            ),
        )


def _record_trials(
    db_path: str | Path,
    *,
    cell: dict,
    bot: str,
    filter_payload: dict,
    validation: dict | None,
) -> None:
    from .global_dsr import periods_for_timeframe

    outcome = "passed" if (validation or {}).get("winner") else "failed"
    reason = (validation or {}).get("reason") or "sin validación"
    periods = periods_for_timeframe(cell.get("timeframe"))
    for variant in ("sin_filtro", "con_filtro"):
        variant_payload = ((validation or {}).get("variants") or {}).get(
            variant, {}
        )
        sharpe = (variant_payload.get("metrics") or {}).get("sharpe")
        record_trial(
            db_path,
            family=f"ai-distill-{cell['strategy']}",
            hypothesis=(
                f"Destilar {cell['strategy']}/{cell['symbol']}/"
                f"{cell['timeframe']} de ia-discrecional"
            ),
            symbol=cell["symbol"],
            params={
                "bot": bot, "variant": variant,
                "style": cell["style"], "filter": filter_payload,
            },
            result={
                "winner": (validation or {}).get("winner"),
                "variants": (validation or {}).get("variants"),
            },
            outcome=outcome,
            reason=reason,
            source="lesson",
            sr_period=(
                float(sharpe) / np.sqrt(periods)
                if sharpe is not None and periods
                else None
            ),
            periods_per_year=periods,
        )


def _write_docs(path: Path, summary: dict) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lines = [
        "## Destilación semanal",
        "<!-- distill:start -->",
        "`lab ai-trader distill` corre los domingos 12:00 DOM, sin LLM.",
        "Solo toma celdas ganadoras del carril IA (n≥30, IC90 del R > 0);",
        "en scalping exige además que el plan supere a la sombra sin plan.",
        "Aprende un filtro legible de profundidad ≤2 sobre el snapshot y valida",
        "con/sin filtro con costes, DSR, PBO, walk-forward y Monte Carlo FTMO.",
        "El candidato nace `enabled: false`; si pasa, queda incubando 60 días",
        "con ≥15 trades, Sharpe forward >0, slippage ≤3 bps y 0 breach.",
        "En scalping la promoción exige ticks Dukascopy de las mismas horas.",
        "",
        f"- IA ganadoras: {summary.get('winning', 0)}",
        f"- Destiladas: {summary.get('distilled', 0)}",
        f"- Incubando: {summary.get('incubating', 0)}",
        f"- Cementerio: {summary.get('rejected', 0)}",
        "<!-- distill:end -->",
    ]
    block = "\n".join(lines)
    if "<!-- distill:start -->" in text:
        text = re.sub(
            r"(?ms)^## Destilación semanal.*?<!-- distill:end -->",
            block, text, count=1,
        )
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ promoción


def scalping_tick_confirmation(
    db_path: str | Path,
    bot: str,
    *,
    criteria: dict | None = None,
    ticks_dir: str | Path | None = None,
) -> dict:
    """Confirma slippage forward y ticks Dukascopy de las mismas horas."""
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT evidence, criteria FROM lifecycle_bots WHERE bot=?",
            (bot,),
        ).fetchone()
    if row is None:
        return {"ok": False, "reason": "bot sin lifecycle"}
    evidence = _json(row["evidence"]) or {}
    criteria = criteria or _json(row["criteria"]) or {}
    assumption = _float(evidence.get("slippage_assumption_bps"))
    max_bps = float(criteria.get("max_slippage_bps") or 3.0)
    with connect(db_path) as con:
        tca = con.execute(
            "SELECT AVG(slippage_bps) AS avg, COUNT(*) AS n FROM tca "
            "WHERE bot=? AND tca_version >= 2",
            (bot,),
        ).fetchone()
    avg = _float(tca["avg"]) if tca else None
    if avg is None or int(tca["n"] or 0) < 10:
        return {"ok": False, "reason": "slippage forward sin muestra"}
    if avg > max_bps:
        return {"ok": False, "reason": f"slippage forward {avg:.2f} > {max_bps:.2f} bps"}
    if assumption is not None and avg > assumption + 1e-9:
        return {"ok": False, "reason": f"slippage forward {avg:.2f} > supuesto {assumption:.2f}"}
    symbol = str(evidence.get("symbol") or "")
    hours = evidence.get("hours_ny") or []
    if not symbol or not hours:
        return {"ok": False, "reason": "horas o símbolo sin datos"}
    from .broker_costs import TICKS_DIR

    root = Path(ticks_dir) if ticks_dir else TICKS_DIR
    files = sorted(root.glob(f"{symbol.upper()}_*.parquet"))
    if not files:
        return {"ok": False, "reason": "sin ticks Dukascopy"}
    frames = []
    for path in files:
        try:
            frames.append(pd.read_parquet(path))
        except OSError:
            continue
    if not frames:
        return {"ok": False, "reason": "ticks Dukascopy ilegibles"}
    frame = pd.concat(frames, ignore_index=True)
    if not {"ts", "bid", "ask"}.issubset(frame.columns):
        return {"ok": False, "reason": "ticks sin bid/ask/ts"}
    stamps = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    local = stamps.dt.tz_convert(NEW_YORK)
    mask = local.dt.hour.isin([int(hour) for hour in hours])
    if not mask.any():
        return {"ok": False, "reason": "sin ticks en las horas del plan"}
    mid = (pd.to_numeric(frame["bid"], errors="coerce")
           + pd.to_numeric(frame["ask"], errors="coerce")) / 2.0
    spread = (
        (pd.to_numeric(frame["ask"], errors="coerce")
         - pd.to_numeric(frame["bid"], errors="coerce")) / mid * 10_000
    )[mask].dropna()
    if spread.empty:
        return {"ok": False, "reason": "ticks sin spread válido"}
    p75 = float(spread.quantile(0.75))
    median = float(spread.median())
    ok = p75 <= max_bps and (assumption is None or p75 <= assumption * 2.0)
    return {
        "ok": ok,
        "reason": (
            "ticks Dukascopy ok" if ok
            else f"ticks Dukascopy p75 {p75:.2f} bps"
        ),
        "tca_avg_bps": round(avg, 3),
        "ticks_median_bps": round(median, 3),
        "ticks_p75_bps": round(p75, 3),
        "hours_ny": sorted({int(hour) for hour in hours}),
        "files": len(files),
    }


# ------------------------------------------------------------------ panel


def panel_payload(db_path: str | Path = DEFAULT_DB) -> dict:
    init_db(db_path)
    cfg = load_ai_config()
    with connect(db_path) as con:
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM ai_distill_runs ORDER BY id DESC"
        ).fetchall()]
        bots = [dict(row) for row in con.execute(
            "SELECT * FROM lifecycle_bots WHERE bot LIKE 'ai-%' ORDER BY bot"
        ).fetchall()]
    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(str(row.get("bot") or ""), row)
    lifecycle = {str(row["bot"]): row for row in bots}
    winners = winning_cells(db_path, version=int(cfg["playbook_version"]))
    items = []
    for bot, row in sorted(latest.items()):
        if not bot:
            continue
        validation = _json(row.get("validation")) or {}
        variants = validation.get("variants") or {}
        winner = validation.get("winner")
        chosen = variants.get(winner) or {}
        state = str((lifecycle.get(bot) or {}).get("state") or row.get("status"))
        items.append({
            "bot": bot,
            "state": state,
            "filter": _json(row.get("filter")) or {},
            "filter_text": (_json(row.get("filter")) or {}).get("description"),
            "reason": row.get("reason"),
            "style": row.get("style"),
            "symbol": row.get("symbol"),
            "strategy": row.get("strategy"),
            "timeframe": row.get("timeframe"),
            "validation": {
                "winner": winner,
                "sharpe": chosen.get("sharpe"),
                "dsr": chosen.get("dsr"),
                "pbo": chosen.get("pbo"),
                "wf": chosen.get("wf_verdict"),
                "passed": chosen.get("passed"),
            },
            "slippage_p95_bps": (lifecycle.get(bot) or {}).get("slippage_p95_bps"),
            "criteria": _json((lifecycle.get(bot) or {}).get("criteria")) or {},
        })
    funnel = {
        "ia_ganadoras": len(winners),
        "destiladas": len({
            str(row.get("bot"))
            for row in rows
            if row.get("status") in {"incubando", "validada", "cemetery"}
        }),
        "validadas": sum(
            1 for row in latest.values()
            if (_json(row.get("validation")) or {}).get("winner")
        ),
        "incubando": sum(
            1 for row in bots if row.get("state") == "incubando"
        ),
        "promovibles": sum(
            1 for row in bots if row.get("state") == "promovible"
        ),
    }
    return {"funnel": funnel, "bots": items, "n": len(items)}


# ------------------------------------------------------------------ entrada


def distill(
    *,
    db_path: str | Path = DEFAULT_DB,
    ai_config_path: str | Path = AI_CONFIG,
    intraday_bots_path: str | Path = INTRADAY_BOTS,
    swing_bots_path: str | Path = SWING_BOTS,
    docs_path: str | Path = DOCS_PATH,
    skill_path: str | Path = SKILL_PATH,
    now: datetime | None = None,
    apply: bool = True,
    validate: bool = True,
    cache_dir: str | Path | None = None,
    settings: Settings | None = None,
) -> dict:
    moment = _as_utc(now)
    settings = settings or get_settings()
    cfg = load_ai_config(ai_config_path)
    version = int(cfg["playbook_version"])
    winners = winning_cells(db_path, version=version)
    summary = {
        "winning": len(winners),
        "distilled": 0,
        "validated": 0,
        "incubating": 0,
        "rejected": 0,
        "skipped": 0,
        "dry_run": not apply,
        "playbook_version": version,
        "runs": [],
    }
    for cell in winners:
        bot = _bot_id(cell["strategy"], cell["symbol"], cell["timeframe"])
        if _cell_status(
            db_path, cell["strategy"], cell["symbol"], cell["timeframe"]
        ) == "destilada":
            summary["skipped"] += 1
            continue
        rows = _decision_rows(
            db_path, style=cell["style"], symbol=cell["symbol"],
            strategy=cell["strategy"], timeframe=cell["timeframe"],
            version=version,
        )
        learned = learn_filter(rows)
        if apply and not validate:
            summary["runs"].append({
                "bot": bot, "status": "dry_run", "filter": learned,
            })
            continue
        if not apply:
            summary["runs"].append({
                "bot": bot, "status": "dry_run", "filter": learned,
            })
            summary["skipped"] += 1
            continue
        validation = validate_candidate(
            symbol=cell["symbol"], strategy=cell["strategy"],
            timeframe=cell["timeframe"], style=cell["style"],
            filter_payload=learned, db_path=db_path,
            cache_dir=cache_dir, settings=settings,
        )
        _record_trials(
            db_path, cell=cell, bot=bot,
            filter_payload=learned, validation=validation,
        )
        if not validation.get("ok") or not validation.get("winner"):
            reason = validation.get("reason") or "sin validación"
            _record_run(
                db_path, cell=cell, bot=bot, status="cemetery",
                reason=reason, filter_payload=learned,
                evidence={"cell": cell, "filter": learned},
                validation=validation, version=version,
            )
            summary["rejected"] += 1
            summary["runs"].append({
                "bot": bot, "status": "cemetery", "reason": reason,
                "filter": learned,
            })
            continue
        chosen = validation["winner"]
        filter_payload = learned if chosen == "con_filtro" else _empty_filter(
            learned["n"], learned["takes"],
            "la versión sin filtro gana; se registra la estrategia",
        )
        magic = _allocate_magic([
            Path(ai_config_path), Path(intraday_bots_path),
            Path(swing_bots_path), FORWARD_CONFIG,
        ])
        candidate = _candidate_payload(
            cell=cell, bot=bot, filter_payload=filter_payload,
            validation=validation, config=cfg, magic=magic,
        )
        target = Path(
            swing_bots_path
            if (
                cell["style"] == "swing"
                or str(cell["timeframe"]).upper() in {"H4", "D1"}
            )
            else intraday_bots_path
        )
        _append_bot(target, candidate)
        from .lifecycle import LifecycleError, register_candidate, start_incubation

        evidence = {
            "datacheck_ok": True,
            "n_trades": int(
                validation["variants"][chosen].get("num_trades") or 0
            ),
            "breakeven_cost_bps": validation["variants"][chosen].get(
                "breakeven_cost_bps"
            ),
            "calibrated_cost_bps": validation["variants"][chosen].get(
                "calibrated_cost_bps"
            ),
            "catastrophic_regime": not bool(
                (validation["variants"][chosen].get("regime_gate") or {}).get(
                    "passed"
                )
            ),
            "symbol": cell["symbol"],
            "style": cell["style"],
            "timeframe": cell["timeframe"],
            "magic": magic,
            "filter": filter_payload,
            "cell": cell,
            "validation": validation,
            "slippage_assumption_bps": validation["variants"][chosen].get(
                "slippage_bps"
            ),
            "hours_ny": sorted({
                int(row["features"]["hour_ny"])
                for row in rows
                if "hour_ny" in row["features"]
            }),
        }
        register_candidate(
            db_path, bot=bot, asset=cell["symbol"],
            evidence=evidence,
            note=f"destilado de {cell['strategy']}/{cell['timeframe']}",
        )
        criteria = (
            SCALPING_CRITERIA if cell["style"] == "scalping"
            else {
                "window_days": 60,
                "min_trades": 15,
                "min_forward_sharpe": 0.0001,
                "max_slippage_bps": 3.0,
                "max_guard_breaches": 0,
                "max_drift_status": "ok",
            }
        )
        state = "candidato"
        try:
            start_incubation(
                db_path, bot=bot, start_date=moment.date().isoformat(),
                actor="sistema", reason="destilación semanal validada",
                criteria_override=criteria,
            )
            state = "incubando"
            _mark_cell(db_path, cell, bot, version)
            summary["incubating"] += 1
        except LifecycleError as exc:
            state = "candidato"
            summary["runs"].append({
                "bot": bot, "status": "candidato",
                "reason": f"no incuba: {exc}",
            })
        summary["distilled"] += 1
        summary["validated"] += 1
        _record_run(
            db_path, cell=cell, bot=bot, status=state,
            reason=(
                f"validada con {chosen}"
                if state == "incubando" else "validada; no incuba"
            ),
            filter_payload=filter_payload,
            evidence=evidence, validation=validation, version=version,
        )
        summary["runs"].append({
            "bot": bot, "status": state, "winner": chosen,
            "filter": filter_payload,
            "validation": validation["variants"][chosen],
        })
    if apply and summary["distilled"]:
        for path in (Path(docs_path), Path(skill_path)):
            try:
                _write_docs(path, summary)
            except Exception:
                pass
    return summary


__all__ = [
    "AI_CONFIG",
    "DistillError",
    "FEATURES",
    "INTRADAY_BOTS",
    "SCALPING_CRITERIA",
    "SWING_BOTS",
    "distill",
    "filter_applies",
    "learn_filter",
    "panel_payload",
    "scalping_tick_confirmation",
    "validate_candidate",
    "winning_cells",
]
