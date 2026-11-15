"""Dispersión global del DSR a partir de pruebas registradas.

No usa series de retorno: toma el Sharpe anualizado de cada prueba guardada y
lo convierte a Sharpe por periodo con su temporalidad. Las pruebas sin
temporalidad identificable se excluyen de la dispersión, aunque sigan contando
en `count_tests`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .config import DEFAULT_DB, ROOT
from .db import connect, init_db
from .learning import count_tests

DAILY = "daily"
INTRADAY = "intraday"

PERIODS_PER_YEAR = {
    "M1": 252.0 * 1440.0,
    "M5": 252.0 * 288.0,
    "M15": 252.0 * 96.0,
    "M30": 252.0 * 48.0,
    "H1": 252.0 * 24.0,
    "H4": 252.0 * 6.0,
    "D1": 252.0,
    "1D": 252.0,
    "D": 252.0,
}


def periods_for_timeframe(timeframe: str | None) -> float | None:
    if not timeframe:
        return None
    return PERIODS_PER_YEAR.get(str(timeframe).strip().upper())


def frequency_for_timeframe(timeframe: str | None) -> str | None:
    periods = periods_for_timeframe(timeframe)
    if periods is None:
        return None
    return DAILY if periods <= 366.0 else INTRADAY


def frequency_for_periods(periods: float | None) -> str | None:
    if periods is None or not math.isfinite(float(periods)) or float(periods) <= 0:
        return None
    return DAILY if float(periods) <= 366.0 else INTRADAY


def sr_from_annual(sr_annual: float | None, periods_per_year: float | None) -> float | None:
    if sr_annual is None or periods_per_year is None:
        return None
    try:
        value = float(sr_annual)
        periods = float(periods_per_year)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not math.isfinite(periods) or periods <= 0:
        return None
    converted = value / math.sqrt(periods)
    if not math.isfinite(converted) or abs(converted) > 1.0:
        return None
    return converted


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "null")
    except (TypeError, ValueError):
        return default


def _add(
    items: list[dict],
    *,
    sr_period: float | None,
    periods_per_year: float | None,
    source: str,
    key: str,
    frequency: str | None = None,
) -> None:
    if sr_period is None or periods_per_year is None:
        return
    freq = frequency or frequency_for_periods(periods_per_year)
    if freq is None:
        return
    items.append(
        {
            "sr_period": float(sr_period),
            "periods_per_year": float(periods_per_year),
            "frequency": freq,
            "source": source,
            "key": key,
        }
    )


def _strategy_trials(db_path: str | Path, items: list[dict]) -> None:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT id, source, params, result, sr_period, periods_per_year "
            "FROM strategy_trials"
        ).fetchall()
    for row in rows:
        params = _json(row["params"], {})
        result = _json(row["result"], {})
        timeframe = params.get("timeframe") if isinstance(params, dict) else None
        periods = periods_for_timeframe(timeframe)
        sr_period = row["sr_period"]
        if sr_period is not None:
            periods = float(row["periods_per_year"] or periods or 0.0) or None
        else:
            sr_annual = result.get("sharpe") if isinstance(result, dict) else None
            sr_period = sr_from_annual(sr_annual, periods)
        _add(
            items,
            sr_period=sr_period,
            periods_per_year=periods,
            source=f"strategy_trials:{row['source'] or 'sin fuente'}",
            key=f"strategy_trials:{row['id']}",
            frequency=frequency_for_timeframe(timeframe),
        )


def _optimization_trials(db_path: str | Path, items: list[dict]) -> None:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT id, sr_period, periods_per_year FROM optimization_trials"
        ).fetchall()
    for row in rows:
        _add(
            items,
            sr_period=row["sr_period"],
            periods_per_year=row["periods_per_year"],
            source="optimization_trials",
            key=f"optimization_trials:{row['id']}",
        )


def _research_report(items: list[dict]) -> None:
    path = ROOT / "reports" / "research" / "latest.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for index, row in enumerate(payload.get("results") or []):
        if not isinstance(row, dict):
            continue
        _add(
            items,
            sr_period=sr_from_annual(row.get("sharpe"), 252.0),
            periods_per_year=252.0,
            source="research_report",
            key=f"research:{index}",
            frequency=DAILY,
        )


def _ea_report(items: list[dict]) -> None:
    path = ROOT / "reports" / "ea" / "us100-ftmo1_v3.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    _add(
        items,
        sr_period=sr_from_annual(payload.get("sharpe"), 252.0),
        periods_per_year=252.0,
        source="ea_report",
        key="ea:us100-ftmo1",
        frequency=DAILY,
    )


def _intraday_reports(items: list[dict]) -> None:
    seen: set[str] = set()
    for path in (ROOT / "reports" / "research").glob("intraday*/*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        timeframe = payload.get("timeframe")
        periods = periods_for_timeframe(timeframe)
        if periods is None:
            continue
        run_id = str(payload.get("run_id") or path.stem)
        for index, row in enumerate(payload.get("outcomes") or []):
            if not isinstance(row, dict):
                continue
            metrics = row.get("metrics") or {}
            key = (
                f"intraday:{run_id}:{row.get('strategy')}:"
                f"{json.dumps(row.get('params') or {}, sort_keys=True)}"
            )
            if key in seen:
                continue
            seen.add(key)
            _add(
                items,
                sr_period=sr_from_annual(metrics.get("sharpe"), periods),
                periods_per_year=periods,
                source="intraday_report",
                key=key,
                frequency=frequency_for_timeframe(timeframe),
            )


def collect_sharpes(
    db_path: str | Path = DEFAULT_DB,
    *,
    include_reports: bool = True,
) -> dict:
    """Devuelve las pruebas con Sharpe por periodo y el desglose por fuente."""
    init_db(db_path)
    items: list[dict] = []
    _strategy_trials(db_path, items)
    _optimization_trials(db_path, items)
    if include_reports:
        _research_report(items)
        _ea_report(items)
        _intraday_reports(items)
    sources: dict[str, int] = {}
    by_frequency = {DAILY: 0, INTRADAY: 0}
    for item in items:
        sources[item["source"]] = sources.get(item["source"], 0) + 1
        by_frequency[item["frequency"]] = by_frequency.get(item["frequency"], 0) + 1
    return {
        "items": items,
        "sources": dict(sorted(sources.items())),
        "by_frequency": by_frequency,
        "n_trials": count_tests(db_path),
    }


def global_srs(
    db_path: str | Path = DEFAULT_DB,
    frequency: str = DAILY,
    *,
    min_count: int = 30,
    include_reports: bool = True,
) -> dict:
    """Sharpes por periodo de la frecuencia pedida, con fuentes y estado."""
    if frequency not in {DAILY, INTRADAY}:
        raise ValueError(f"frecuencia desconocida: {frequency!r}")
    collected = collect_sharpes(db_path, include_reports=include_reports)
    srs = [
        item["sr_period"]
        for item in collected["items"]
        if item["frequency"] == frequency
    ]
    sources = {
        key: sum(
            1
            for item in collected["items"]
            if item["source"] == key and item["frequency"] == frequency
        )
        for key in collected["sources"]
    }
    sources = {key: value for key, value in sources.items() if value}
    available = len(srs) >= min_count
    return {
        "frequency": frequency,
        "srs": srs if available else [],
        "n_srs": len(srs),
        "available": available,
        "sources": sources,
        "n_trials": int(collected["n_trials"]),
        "reason": (
            ""
            if available
            else f"menos de {min_count} Sharpes {frequency} ({len(srs)})"
        ),
    }


__all__ = [
    "DAILY",
    "INTRADAY",
    "PERIODS_PER_YEAR",
    "collect_sharpes",
    "frequency_for_periods",
    "frequency_for_timeframe",
    "global_srs",
    "periods_for_timeframe",
    "sr_from_annual",
]
