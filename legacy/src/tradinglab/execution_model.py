"""Informe de coste efectivo por operación: serie vs eventos.

No reejecuta backtests ni registra trials. Lee las variantes ya registradas en
``reports/research/intraday_<ACTIVO>/intraday_broker.json`` y el coste bróker
p75 medido en la tarea 1B. El modo de eventos se expresa como rango porque los
informes de variantes no guardan el mix de salidas (objetivo, stop o forzada);
no se inventa ese mix.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .broker_costs import load_broker_report
from .config import ROOT

REPORT_DIR = ROOT / "reports" / "research"
ASSETS = ("EURUSD", "USDJPY", "XAUUSD", "US100")
DEFAULT_SLIPPAGE_BPS = 2.0


def _asset_report(reports_dir: Path, asset: str) -> tuple[dict | None, Path | None]:
    base = reports_dir / f"intraday_{asset}"
    for name in ("intraday_broker.json", "intraday.json"):
        path = base / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8")), path
            except (OSError, ValueError):
                return None, path
    return None, None


def _params_text(params: dict | None) -> str:
    return json.dumps(params or {}, ensure_ascii=False, sort_keys=True)


def _fmt(value: float | None) -> str:
    return "sin datos" if value is None else f"{float(value):.2f}"


def _median(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return statistics.median(clean) if clean else None


def _dsr_count_readonly(db_path: str | Path) -> int | None:
    """Lee el contador DSR sin crear tablas ni escribir en la base."""
    path = Path(db_path)
    if not path.exists():
        return None
    connection = None
    try:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3
        )
        connection.row_factory = sqlite3.Row
        total = 0
        for table in (
            "lesson_tests",
            "optimization_trials",
            "holdout_reads",
            "strategy_trials",
        ):
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                total += int(
                    connection.execute(
                        f"SELECT COUNT(*) AS n FROM {table}"
                    ).fetchone()["n"]
                )
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_bots'"
        ).fetchone()
        if exists:
            total += int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM lifecycle_bots "
                    "WHERE frozen_at IS NOT NULL"
                ).fetchone()["n"]
            )
        return total
    except sqlite3.Error:
        return None
    finally:
        if connection is not None:
            connection.close()


def collect_variants(
    reports_dir: str | Path = REPORT_DIR,
    *,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Devuelve las variantes con coste serie, rango de eventos y DSR leído."""
    reports = Path(reports_dir)
    broker = load_broker_report(reports)
    dsr_count = _dsr_count_readonly(db_path) if db_path is not None else None
    rows: list[dict] = []
    for asset in ASSETS:
        data, path = _asset_report(reports, asset)
        if not data:
            continue
        symbol = str(data.get("symbol") or asset)
        summary = (
            (broker.get("symbols") or {}).get(symbol.upper(), {}).get("summary")
            or {}
        )
        broker_p75 = summary.get("p75_bps")
        slippage = float(
            ((data.get("cost_model") or {}).get("slippage") or {}).get(
                "conservative_bps", DEFAULT_SLIPPAGE_BPS
            )
        )
        for outcome in data.get("outcomes") or []:
            commission = float(outcome.get("commission_bps_median") or 0.0)
            spread = outcome.get("spread_bps_median")
            if spread is None:
                spread = broker_p75
            spread = None if spread is None else float(spread)
            series_side = outcome.get("calibrated_cost_bps")
            series_side = None if series_side is None else float(series_side)
            if spread is None:
                event_min = event_base = event_max = None
            else:
                event_min = 2.0 * commission
                event_base = 2.0 * commission + spread + slippage
                event_max = 2.0 * (commission + spread + slippage)
            rows.append(
                {
                    "asset": asset,
                    "symbol": symbol,
                    "strategy": str(outcome.get("strategy") or ""),
                    "params": outcome.get("params") or {},
                    "trades": int(
                        ((outcome.get("metrics") or {}).get("num_trades") or 0)
                    ),
                    "commission_bps": commission,
                    "spread_p75_bps": spread,
                    "slippage_bps": slippage,
                    "series_bps_op": (
                        None if series_side is None else 2.0 * series_side
                    ),
                    "event_min_bps_op": event_min,
                    "event_base_bps_op": event_base,
                    "event_max_bps_op": event_max,
                    "source": str(path),
                    "dsr_count": dsr_count,
                }
            )
    return rows


def _summary(rows: list[dict]) -> list[dict]:
    out = []
    for asset in ASSETS:
        group = [row for row in rows if row["asset"] == asset]
        if not group:
            out.append(
                {
                    "asset": asset,
                    "n": 0,
                    "commission_bps": None,
                    "spread_p75_bps": None,
                    "series_bps_op": None,
                    "event_min_bps_op": None,
                    "event_base_bps_op": None,
                    "event_max_bps_op": None,
                }
            )
            continue
        out.append(
            {
                "asset": asset,
                "n": len(group),
                "commission_bps": _median([row["commission_bps"] for row in group]),
                "spread_p75_bps": _median(
                    [row["spread_p75_bps"] for row in group]
                ),
                "series_bps_op": _median(
                    [row["series_bps_op"] for row in group]
                ),
                "event_min_bps_op": _median(
                    [row["event_min_bps_op"] for row in group]
                ),
                "event_base_bps_op": _median(
                    [row["event_base_bps_op"] for row in group]
                ),
                "event_max_bps_op": _median(
                    [row["event_max_bps_op"] for row in group]
                ),
            }
        )
    return out


def render_report(rows: list[dict]) -> str:
    summary = _summary(rows)
    variant_count = len(rows)
    dsr_count = rows[0].get("dsr_count") if rows else None
    dsr_text = "sin datos" if dsr_count is None else str(dsr_count)
    lines = [
        "# Modelo de ejecución: coste efectivo por operación",
        "",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Variantes registradas: **{variant_count}**.",
        f"- Contador DSR leído: **{dsr_text}** (sin cambios; el informe no registra trials).",
        "- Medición, no búsqueda: no se registraron trials ni se cambió el contador DSR.",
        "- No se cambió ningún umbral de aprobación ni se activó ningún bot.",
        "- Serie: coste calibrado del recálculo con spread bróker p75 (por turnover) ×2 "
        "para una operación de ida y vuelta.",
        "- Eventos: entrada limitada sin spread; salida en objetivo limitada sin spread; "
        "stop/salida forzada y entrada a mercado pagan spread p75 + slippage; comisión por lado.",
        "- El coste de eventos se expresa como rango porque las variantes registradas no "
        "guardan el mix de salidas; no se inventa ese mix. `min` = limit/target, "
        "`base` = limit/stop, `max` = market/stop.",
        "- El spread usado es el bróker p75 de la tarea 1B; no se mezcla con Dukascopy.",
        "- La serie usa la comisión efectiva ponderada por turnover y el evento la "
        "comisión mediana; las diferencias de centésimas son de ponderación.",
        "",
        "## Resumen por activo",
        "",
        "| Activo | Variantes | Comisión bps | Spread p75 bps | Serie bps/op | Eventos mín. | Eventos base | Eventos máx. |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['asset']} | {row['n']} | {_fmt(row['commission_bps'])} | "
            f"{_fmt(row['spread_p75_bps'])} | {_fmt(row['series_bps_op'])} | "
            f"{_fmt(row['event_min_bps_op'])} | {_fmt(row['event_base_bps_op'])} | "
            f"{_fmt(row['event_max_bps_op'])} |"
        )
    lines += [
        "",
        f"## Detalle de las {variant_count} variantes",
        "",
        "| Activo | Estrategia | Parámetros | Trades | Comisión bps | Spread p75 bps | Serie bps/op | Eventos mín. | Eventos base | Eventos máx. |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['asset']} | {row['strategy']} | `{_params_text(row['params'])}` | "
            f"{row['trades']} | {_fmt(row['commission_bps'])} | "
            f"{_fmt(row['spread_p75_bps'])} | {_fmt(row['series_bps_op'])} | "
            f"{_fmt(row['event_min_bps_op'])} | {_fmt(row['event_base_bps_op'])} | "
            f"{_fmt(row['event_max_bps_op'])} |"
        )
    lines += [
        "",
        "## Lectura",
        "",
        "- El modo de serie paga comisión + spread + slippage en cada lado; el evento "
        "solo evita el spread en la entrada limitada y en la salida por objetivo.",
        "- Con entrada a **mercado** y salida por stop/forzada, el coste de eventos "
        "se aproxima al máximo de serie; la diferencia es la comisión ponderada de "
        "la serie. El test de reconciliación de `tests/test_execution_fills.py` "
        "fuerza ese caso y falla si el retorno neto de eventos supera al de serie.",
        "- El ahorro potencial del modo de eventos depende de que la entrada y el "
        f"objetivo sean limitados; no se extrapola a partir de estas {variant_count} "
        "variantes.",
        "",
    ]
    return "\n".join(lines)


def build_report(
    out_dir: str | Path = REPORT_DIR,
    *,
    reports_dir: str | Path = REPORT_DIR,
    db_path: str | Path | None = None,
) -> Path:
    """Escribe ``execution_model.md`` sin registrar trials ni escribir SQLite."""
    rows = collect_variants(reports_dir, db_path=db_path)
    out = Path(out_dir) / "execution_model.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(rows), encoding="utf-8")
    return out


__all__ = [
    "ASSETS",
    "REPORT_DIR",
    "build_report",
    "collect_variants",
    "render_report",
]
