"""Detectores informativos de conducta sobre operaciones cerradas.

No bloquean nada: solo describen patrones para revisarlos en el journal.
- Revenge trading: entrada rápida tras una pérdida, con más riesgo.
- Overtrading: día con muchas más operaciones que la mediana propia.

Los umbrales viven en ``config/journal_detectors.yaml``.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT

DETECTORS_FILE = ROOT / "config" / "journal_detectors.yaml"
DEFAULT_CONFIG: dict[str, dict[str, float | int]] = {
    "revenge": {"window_minutes": 30.0},
    "overtrading": {"min_trades": 4, "median_multiple": 2.0},
}


def _defaults() -> dict[str, dict[str, float | int]]:
    return {section: dict(values) for section, values in DEFAULT_CONFIG.items()}


def load_config(path: str | Path | None = None) -> dict[str, dict[str, float | int]]:
    """Carga los umbrales; si el archivo no existe, usa los defaults."""
    target = Path(path) if path is not None else DETECTORS_FILE
    if not target.exists():
        return _defaults()
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("journal_detectors.yaml debe ser un mapa")
    revenge = data.get("revenge") or {}
    overtrading = data.get("overtrading") or {}
    if not isinstance(revenge, dict) or not isinstance(overtrading, dict):
        raise ValueError("revenge y overtrading deben ser mapas")
    window = float(
        revenge.get("window_minutes", DEFAULT_CONFIG["revenge"]["window_minutes"])
    )
    min_trades = int(
        overtrading.get("min_trades", DEFAULT_CONFIG["overtrading"]["min_trades"])
    )
    multiple = float(
        overtrading.get(
            "median_multiple", DEFAULT_CONFIG["overtrading"]["median_multiple"]
        )
    )
    if window <= 0:
        raise ValueError("revenge.window_minutes debe ser > 0")
    if min_trades < 1:
        raise ValueError("overtrading.min_trades debe ser >= 1")
    if multiple <= 0:
        raise ValueError("overtrading.median_multiple debe ser > 0")
    return {
        "revenge": {"window_minutes": window},
        "overtrading": {"min_trades": min_trades, "median_multiple": multiple},
    }


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def detect_revenge(
    trades: list[Any],
    *,
    window_minutes: float,
) -> dict:
    """Entrada < N minutos tras una pérdida y con riesgo mayor que la anterior."""
    ordered = sorted(
        trades,
        key=lambda trade: _parse_ts(getattr(trade, "entry_ts", None))
        or datetime.min.replace(tzinfo=timezone.utc),
    )
    previous_by_scope: dict[str, Any] = {}
    events: list[dict] = []
    for trade in ordered:
        scope = str(
            getattr(trade, "account", None)
            or getattr(trade, "bot", None)
            or "sin datos"
        )
        previous = previous_by_scope.get(scope)
        if previous is not None:
            previous_pnl = getattr(previous, "pnl", None)
            previous_risk = getattr(previous, "risk_usd", None)
            current_risk = getattr(trade, "risk_usd", None)
            previous_exit = _parse_ts(getattr(previous, "exit_ts", None))
            current_entry = _parse_ts(getattr(trade, "entry_ts", None))
            if (
                previous_pnl is not None
                and float(previous_pnl) < 0
                and previous_risk is not None
                and current_risk is not None
                and float(current_risk) > float(previous_risk)
                and previous_exit is not None
                and current_entry is not None
            ):
                minutes = (current_entry - previous_exit).total_seconds() / 60.0
                if 0.0 <= minutes < window_minutes:
                    events.append(
                        {
                            "scope": scope,
                            "previous_exit": getattr(previous, "exit_ts", None),
                            "entry": getattr(trade, "entry_ts", None),
                            "minutes": round(minutes, 2),
                            "previous_pnl": round(float(previous_pnl), 6),
                            "previous_risk_usd": round(float(previous_risk), 6),
                            "risk_usd": round(float(current_risk), 6),
                        }
                    )
        previous_by_scope[scope] = trade
    return {
        "count": len(events),
        "window_minutes": window_minutes,
        "events": events,
    }


def detect_overtrading(
    trades: list[Any],
    *,
    min_trades: int,
    median_multiple: float,
) -> dict:
    """Días por encima de M operaciones y de M veces la mediana propia."""
    counts: Counter[str] = Counter()
    for trade in trades:
        day = getattr(trade, "day", None)
        if day:
            counts[str(day)] += 1
    if not counts:
        return {
            "count": 0,
            "active_days": 0,
            "median": None,
            "min_trades": min_trades,
            "median_multiple": median_multiple,
            "threshold": None,
            "days": [],
        }
    median = float(statistics.median(counts.values()))
    threshold = max(int(min_trades), int(math.ceil(median * median_multiple)))
    days = [
        {
            "day": day,
            "trades": count,
            "threshold": threshold,
            "excess": count - threshold,
        }
        for day, count in sorted(counts.items())
        if count > threshold
    ]
    return {
        "count": len(days),
        "active_days": len(counts),
        "median": median,
        "min_trades": min_trades,
        "median_multiple": median_multiple,
        "threshold": threshold,
        "days": days,
    }


def detect(
    trades: list[Any],
    config: dict[str, dict[str, float | int]] | None = None,
) -> dict:
    """Ejecuta ambos detectores; nunca lanza por un YAML roto."""
    warning = None
    if config is None:
        try:
            config = load_config()
        except Exception as exc:
            config = _defaults()
            warning = f"journal_detectors.yaml inválido: {exc}; se usan defaults"
    revenge_cfg = config.get("revenge") or DEFAULT_CONFIG["revenge"]
    over_cfg = config.get("overtrading") or DEFAULT_CONFIG["overtrading"]
    return {
        "informative": True,
        "blocking": False,
        "warning": warning,
        "config": config,
        "revenge": detect_revenge(
            trades,
            window_minutes=float(revenge_cfg["window_minutes"]),
        ),
        "overtrading": detect_overtrading(
            trades,
            min_trades=int(over_cfg["min_trades"]),
            median_multiple=float(over_cfg["median_multiple"]),
        ),
    }


__all__ = [
    "DEFAULT_CONFIG",
    "DETECTORS_FILE",
    "detect",
    "detect_overtrading",
    "detect_revenge",
    "load_config",
]
