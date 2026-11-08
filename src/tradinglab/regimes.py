"""Régimen de mercado informativo y causal.

Clasificador por reglas (tendencia + volatilidad) sin información futura.
GMM/HMM no se adopta en esta etapa: no hay dependencia instalada y añadirla no
está justificado para la muestra disponible. El selector por régimen es una
propuesta `proposed`; nunca activa ni desactiva bots.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .datacheck import find_cache

REGIMES = ("trend_up", "trend_down", "range", "unknown")
VOL_STATES = ("low", "high")
WARMUP = 200


def load_cached(
    symbol: str,
    cache_dir: str | Path,
) -> tuple[pd.DataFrame | None, Path | None]:
    """Lee la caché más reciente; no descarga."""
    path = find_cache(cache_dir, symbol)
    if path is None:
        return None, None
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return None, path
    if frame.empty:
        return None, path
    frame = frame.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    if "close" not in frame.columns:
        return None, path
    return frame, path


def classify(
    df: pd.DataFrame,
    *,
    trend_window: int = 200,
    slope_window: int = 50,
    vol_window: int = 20,
    vol_lookback: int = 252,
) -> pd.DataFrame:
    """Etiquetas causales: cada fila usa solo datos hasta esa fecha."""
    close = pd.to_numeric(df["close"], errors="coerce").astype(float)
    sma_trend = close.rolling(trend_window, min_periods=trend_window).mean()
    sma_slope_series = (
        close.rolling(slope_window, min_periods=slope_window).mean().diff(10)
    )
    returns = close.pct_change()
    vol = returns.rolling(vol_window, min_periods=vol_window).std() * math.sqrt(252)
    vol_median = vol.rolling(
        vol_lookback,
        min_periods=max(20, vol_lookback // 2),
    ).median()

    labels = pd.Series("unknown", index=df.index, dtype=object)
    trend_up = (close > sma_trend) & (sma_slope_series > 0)
    trend_down = (close < sma_trend) & (sma_slope_series < 0)
    valid = sma_trend.notna() & vol.notna() & vol_median.notna()
    labels[valid & trend_up] = "trend_up"
    labels[valid & trend_down] = "trend_down"
    labels[valid & ~trend_up & ~trend_down] = "range"
    labels[~valid] = "unknown"

    vol_state = pd.Series("high", index=df.index, dtype=object)
    vol_state[vol <= vol_median] = "low"
    vol_state[~valid] = "unknown"
    trend_strength = (close / sma_trend - 1.0).replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame(
        {
            "label": labels,
            "vol_state": vol_state,
            "vol": vol,
            "vol_median": vol_median,
            "above_trend": close > sma_trend,
            "slope": sma_slope_series,
            "trend_strength": trend_strength,
        },
        index=df.index,
    )


def _run_lengths(labels: pd.Series) -> list[int]:
    values = [value for value in labels.tolist() if value != "unknown"]
    if not values:
        return []
    runs: list[int] = []
    current = 1
    for previous, value in zip(values, values[1:]):
        if value == previous:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    return runs


def _false_changes(labels: pd.Series, horizon: int = 5) -> tuple[int, int, float | None]:
    values = labels.tolist()
    changes = 0
    false = 0
    for index in range(1, len(values)):
        if values[index] == values[index - 1] or values[index] == "unknown":
            continue
        if values[index - 1] == "unknown":
            continue
        changes += 1
        future = index + horizon
        if future < len(values) and values[future] == values[index - 1]:
            false += 1
    return changes, false, (false / changes) if changes else None


def _reference_labels(labels: pd.Series, window: int = 21) -> pd.Series:
    """Mayoría centrada solo para evaluación; nunca se usa en vivo."""
    reference = labels.copy()
    values = labels.tolist()
    for index in range(len(values)):
        start = max(0, index - window // 2)
        end = min(len(values), index + window // 2 + 1)
        chunk = [value for value in values[start:end] if value != "unknown"]
        if not chunk:
            reference.iloc[index] = "unknown"
            continue
        counts: dict[str, int] = {}
        for value in chunk:
            counts[value] = counts.get(value, 0) + 1
        reference.iloc[index] = max(counts, key=counts.get)
    return reference


def detection_delay(labels: pd.Series) -> dict[str, Any]:
    reference = _reference_labels(labels)
    delays: list[int] = []
    causal_changes = [
        index
        for index in range(1, len(labels))
        if labels.iloc[index] != labels.iloc[index - 1]
        and labels.iloc[index] != "unknown"
        and labels.iloc[index - 1] != "unknown"
    ]
    for index in range(1, len(reference)):
        if reference.iloc[index] == reference.iloc[index - 1]:
            continue
        if reference.iloc[index] == "unknown":
            continue
        later = [value for value in causal_changes if value >= index]
        if later:
            delays.append(later[0] - index)
    return {
        "n": len(delays),
        "mean_days": round(float(np.mean(delays)), 2) if delays else None,
        "median_days": round(float(np.median(delays)), 2) if delays else None,
        "max_days": max(delays) if delays else None,
        "reference": "mayoría centrada de 21 días; solo evaluación",
    }


def _regime_stats(returns: pd.Series, labels: pd.Series) -> list[dict[str, Any]]:
    aligned = returns.reindex(labels.index).fillna(0.0)
    rows: list[dict[str, Any]] = []
    for regime in REGIMES:
        subset = aligned[labels == regime]
        if len(subset) == 0:
            rows.append({"regime": regime, "n": 0})
            continue
        equity = (1.0 + subset).cumprod()
        peak = equity.cummax()
        drawdown = equity / peak - 1.0
        std = float(subset.std(ddof=1)) if len(subset) > 1 else 0.0
        mean = float(subset.mean())
        rows.append(
            {
                "regime": regime,
                "n": len(subset),
                "total_return": float(equity.iloc[-1] - 1.0),
                "sharpe": (mean / std * math.sqrt(252)) if std > 0 else None,
                "volatility": std * math.sqrt(252),
                "max_drawdown": float(drawdown.min()),
                "hit_rate": float((subset > 0).mean()),
                "avg_return": mean,
            }
        )
    return rows


def metrics(labels: pd.Series, returns: pd.Series) -> dict[str, Any]:
    valid = labels[labels != "unknown"]
    stability = (
        float((valid == valid.shift(1)).iloc[1:].mean()) if len(valid) > 1 else None
    )
    runs = _run_lengths(labels)
    changes, false, false_pct = _false_changes(labels)
    return {
        "stability_pct": stability,
        "avg_duration_days": round(float(np.mean(runs)), 2) if runs else None,
        "changes": changes,
        "false_changes": false,
        "false_changes_pct": false_pct,
        "detection_delay": detection_delay(labels),
        "regime_stats": _regime_stats(returns, labels),
        "n_observations": len(valid),
    }


def selector_proposal(label: str, vol_state: str) -> dict[str, Any]:
    """Propuesta informativa; nunca se aplica ni activa nada."""
    if label == "trend_up" and vol_state == "low":
        bot = "trend-spy"
    elif label == "trend_up":
        bot = "trend-spy"
    elif label == "range" and vol_state == "low":
        bot = "meanrev-large"
    else:
        bot = "flat"
    return {
        "regime": label,
        "vol_state": vol_state,
        "bot": bot,
        "status": "proposed",
        "enabled": False,
        "applied": False,
        "note": "Solo propuesta; requiere aprobación humana. No activa ni desactiva bots.",
    }


def selector_proposals() -> list[dict[str, Any]]:
    return [
        selector_proposal(label, vol)
        for label in ("trend_up", "trend_down", "range")
        for vol in VOL_STATES
    ]


def report(
    symbol: str,
    df: pd.DataFrame,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    signals = classify(df)
    returns = pd.to_numeric(df["close"], errors="coerce").pct_change().fillna(0.0)
    valid = signals[signals["label"] != "unknown"]
    if valid.empty:
        return {
            "symbol": symbol.upper(),
            "status": "Sin datos",
            "reason": "histórico insuficiente para régimen (warmup 200)",
            "current": None,
            "metrics": None,
            "selector": selector_proposals(),
            "source": source,
        }
    last = valid.iloc[-1]
    return {
        "symbol": symbol.upper(),
        "status": "ok",
        "as_of": str(pd.Timestamp(valid.index[-1]).date()),
        "current": {
            "label": str(last["label"]),
            "vol_state": str(last["vol_state"]),
            "vol": float(last["vol"]) if pd.notna(last["vol"]) else None,
            "vol_median": float(last["vol_median"])
            if pd.notna(last["vol_median"])
            else None,
            "trend_strength": float(last["trend_strength"])
            if pd.notna(last["trend_strength"])
            else None,
        },
        "metrics": metrics(signals["label"], returns),
        "selector": selector_proposals(),
        "proposed_selector": selector_proposal(
            str(last["label"]), str(last["vol_state"])
        ),
        "source": source,
    }


def bot_performance_by_regime(
    returns: pd.Series,
    labels: pd.Series,
) -> list[dict[str, Any]]:
    return _regime_stats(returns, labels)


__all__ = [
    "REGIMES",
    "VOL_STATES",
    "bot_performance_by_regime",
    "classify",
    "detection_delay",
    "load_cached",
    "metrics",
    "report",
    "selector_proposal",
    "selector_proposals",
]
