"""Coste efectivo del bróker a partir de ticks MT5. Solo lectura.

Mide el spread por símbolo y hora UTC (mediana y p75) con ``COPY_TICKS_ALL``,
lo persiste en ``broker_spreads`` y genera los informes de coste. El recálculo
de la etapa 3 reutiliza las mismas variantes y **no registra trials**.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .config import ROOT
from .db import connect, init_db

REPORT_DIR = ROOT / "reports" / "research"
DB_PATH = ROOT / "data" / "lab.db"
TICKS_DIR = ROOT / "data" / "cache" / "ticks"
SOURCE_BROKER = "broker"
SOURCE_DUKASCOPY = "dukascopy"
SPREAD_COLUMNS = [
    "symbol",
    "hour_utc",
    "median_bps",
    "p75_bps",
    "n_ticks",
    "from_ts",
    "to_ts",
    "source",
]
STAGE3_ASSETS = ("EURUSD", "USDJPY", "XAUUSD", "US100")


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def mt5_swap(symbol: str) -> dict:
    """Swap bruto del símbolo desde `mt5.symbol_info`; nunca inventa.

    No inicializa MT5: usa la conexión que ya exista. Si el paquete o el
    terminal no están disponibles, devuelve ``status="Sin datos"``.
    """
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        return {
            "status": "Sin datos",
            "reason": f"MT5 no disponible: {type(exc).__name__}",
            "symbol": str(symbol).upper(),
        }
    info = mt5.symbol_info(str(symbol))
    if info is None:
        return {
            "status": "Sin datos",
            "reason": "symbol_info sin datos o terminal no inicializado",
            "symbol": str(symbol).upper(),
        }
    return {
        "status": "ok",
        "symbol": str(symbol).upper(),
        "swap_long": float(info.swap_long),
        "swap_short": float(info.swap_short),
        "swap_mode": int(info.swap_mode),
        "source": "mt5.symbol_info",
    }


def _empty_ticks() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts", "bid", "ask", "spread", "spread_bps"])


def add_spread_bps(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Añade spread y spread_bps; descarta ticks sin bid/ask válidos."""
    if frame is None or len(frame) == 0:
        return _empty_ticks()
    out = pd.DataFrame(frame).copy()
    if "ts" not in out.columns:
        raise ValueError("ticks sin columna ts")
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out["bid"] = pd.to_numeric(out.get("bid"), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask"), errors="coerce")
    out = out.dropna(subset=["ts", "bid", "ask"])
    out = out[(out["bid"] > 0) & (out["ask"] > 0) & (out["ask"] >= out["bid"])]
    if out.empty:
        return _empty_ticks()
    out["spread"] = out["ask"] - out["bid"]
    mid = (out["ask"] + out["bid"]) / 2.0
    out["spread_bps"] = out["spread"] / mid.replace(0, np.nan) * 10_000.0
    return out.dropna(subset=["spread_bps"])


def hourly_spreads(
    frame: pd.DataFrame | None,
    symbol: str,
    *,
    source: str = SOURCE_BROKER,
) -> pd.DataFrame:
    """Spread mediano, p75 y cobertura por hora UTC para un símbolo."""
    valid = add_spread_bps(frame)
    if valid.empty:
        return pd.DataFrame(columns=SPREAD_COLUMNS)
    valid = valid.copy()
    valid["hour_utc"] = valid["ts"].dt.hour
    rows = []
    for hour, group in valid.groupby("hour_utc", sort=True):
        values = group["spread_bps"]
        rows.append(
            {
                "symbol": _normalize_symbol(symbol),
                "hour_utc": int(hour),
                "median_bps": float(values.median()),
                "p75_bps": float(values.quantile(0.75)),
                "n_ticks": int(len(group)),
                "from_ts": group["ts"].min().isoformat(),
                "to_ts": group["ts"].max().isoformat(),
                "source": source,
            }
        )
    return pd.DataFrame(rows, columns=SPREAD_COLUMNS).sort_values("hour_utc")


def spread_summary(
    frame: pd.DataFrame | None,
    symbol: str,
    *,
    source: str = SOURCE_BROKER,
) -> dict:
    """Resumen de todo el rango: mediana y p75 globales, ticks y cobertura."""
    valid = add_spread_bps(frame)
    if valid.empty:
        return {
            "symbol": _normalize_symbol(symbol),
            "source": source,
            "status": "sin datos",
            "n_ticks": 0,
            "median_bps": None,
            "p75_bps": None,
            "hours_with_data": 0,
            "from_ts": None,
            "to_ts": None,
        }
    values = valid["spread_bps"]
    return {
        "symbol": _normalize_symbol(symbol),
        "source": source,
        "status": "ok",
        "n_ticks": int(len(valid)),
        "median_bps": float(values.median()),
        "p75_bps": float(values.quantile(0.75)),
        "hours_with_data": int(valid["ts"].dt.hour.nunique()),
        "from_ts": valid["ts"].min().isoformat(),
        "to_ts": valid["ts"].max().isoformat(),
    }


def persist_spreads(
    rows: pd.DataFrame | list[dict] | None,
    db_path: str | Path = DB_PATH,
) -> int:
    """Inserta/actualiza las filas horarias en ``broker_spreads``."""
    if rows is None:
        return 0
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if frame.empty:
        return 0
    for column in SPREAD_COLUMNS:
        if column not in frame.columns:
            raise ValueError(f"falta columna {column} en broker_spreads")
    init_db(db_path)
    payload = []
    for row in frame[SPREAD_COLUMNS].to_dict("records"):
        payload.append(
            (
                _normalize_symbol(row["symbol"]),
                int(row["hour_utc"]),
                None if pd.isna(row["median_bps"]) else float(row["median_bps"]),
                None if pd.isna(row["p75_bps"]) else float(row["p75_bps"]),
                int(row["n_ticks"]),
                row.get("from_ts"),
                row.get("to_ts"),
                str(row["source"]),
            )
        )
    with connect(db_path) as con:
        con.executemany(
            "INSERT INTO broker_spreads"
            "(symbol, hour_utc, median_bps, p75_bps, n_ticks, from_ts, to_ts, source) "
            "VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol, hour_utc, source) DO UPDATE SET "
            "median_bps=excluded.median_bps, p75_bps=excluded.p75_bps, "
            "n_ticks=excluded.n_ticks, from_ts=excluded.from_ts, "
            "to_ts=excluded.to_ts",
            payload,
        )
    return len(payload)


def load_spreads(
    db_path: str | Path = DB_PATH,
    *,
    symbol: str | None = None,
    source: str | None = None,
) -> pd.DataFrame:
    init_db(db_path)
    clauses = []
    params: list = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(_normalize_symbol(symbol))
    if source:
        clauses.append("source = ?")
        params.append(str(source))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as con:
        rows = con.execute(
            f"SELECT {', '.join(SPREAD_COLUMNS)} FROM broker_spreads{where} "
            "ORDER BY symbol, hour_utc",
            params,
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows], columns=SPREAD_COLUMNS)


def collect_broker(
    symbol: str,
    days: int,
    copy_ticks: Callable[[str, datetime, datetime], pd.DataFrame],
    *,
    db_path: str | Path = DB_PATH,
    now: datetime | None = None,
) -> dict:
    """Mide un símbolo con una función ``copy_ticks`` inyectable (sin MT5 en tests)."""
    if days <= 0:
        raise ValueError("days debe ser > 0")
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    end = end.astimezone(timezone.utc)
    start = end - timedelta(days=int(days))
    frame = copy_ticks(symbol, start, end)
    summary = spread_summary(frame, symbol, source=SOURCE_BROKER)
    rows = hourly_spreads(frame, symbol, source=SOURCE_BROKER)
    persist_spreads(rows, db_path)
    return {
        "symbol": _normalize_symbol(symbol),
        "source": SOURCE_BROKER,
        "status": summary["status"],
        "summary": summary,
        "rows": rows.to_dict("records"),
        "hours": {
            str(hour): (
                next(
                    (row for row in rows.to_dict("records") if row["hour_utc"] == hour),
                    None,
                )
            )
            for hour in range(24)
        },
        "window": {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": int(days),
        },
    }


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def merge_broker_report(
    result: dict,
    out_dir: str | Path = REPORT_DIR,
) -> dict:
    """Fusiona un símbolo en ``broker_costs.json`` y reescribe el Markdown."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "broker_costs.json"
    report = _load_json(path)
    report.setdefault("symbols", {})
    key = _normalize_symbol(result["symbol"])
    report["symbols"][key] = result
    report["generated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    report["source"] = SOURCE_BROKER
    report["notes"] = (
        "Ticks del bróker (MT5 copy_ticks, COPY_TICKS_ALL). "
        "Cada celda sin ticks se escribe como 'sin datos'; no se rellena con Dukascopy."
    )
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (out / "broker_costs.md").write_text(
        render_broker_report(report), encoding="utf-8"
    )
    return report


def merge_comparison_into_broker_report(
    comparison: dict,
    out_dir: str | Path = REPORT_DIR,
) -> dict:
    """Incrusta la comparativa en ``broker_costs.md/json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = load_broker_report(out)
    report["comparison"] = comparison
    report["comparison_generated_at"] = comparison.get("generated_at") or pd.Timestamp.now(
        tz="UTC"
    ).isoformat()
    (out / "broker_costs.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (out / "broker_costs.md").write_text(
        render_broker_report(report), encoding="utf-8"
    )
    return report


def load_broker_report(out_dir: str | Path = REPORT_DIR) -> dict:
    return _load_json(Path(out_dir) / "broker_costs.json")


def broker_spread_summary(
    symbol: str,
    *,
    out_dir: str | Path = REPORT_DIR,
    db_path: str | Path = DB_PATH,
) -> dict:
    """p75 global del informe; si falta, usa la mediana de los p75 horarios."""
    key = _normalize_symbol(symbol)
    report = load_broker_report(out_dir)
    item = (report.get("symbols") or {}).get(key)
    if item and (item.get("summary") or {}).get("p75_bps") is not None:
        summary = dict(item["summary"])
        summary["method"] = "all_ticks_p75"
        summary["status"] = summary.get("status", "ok")
        return summary
    rows = load_spreads(db_path, symbol=key, source=SOURCE_BROKER)
    if rows.empty:
        return {
            "symbol": key,
            "source": SOURCE_BROKER,
            "status": "sin datos",
            "p75_bps": None,
            "median_bps": None,
            "n_ticks": 0,
            "method": "sin datos",
        }
    return {
        "symbol": key,
        "source": SOURCE_BROKER,
        "status": "ok_fallback",
        "p75_bps": float(rows["p75_bps"].median()),
        "median_bps": float(rows["median_bps"].median()),
        "n_ticks": int(rows["n_ticks"].sum()),
        "method": "median_hourly_p75",
    }


def dukascopy_summary(
    symbol: str,
    ticks_dir: str | Path = TICKS_DIR,
) -> dict:
    """p75 global de los parquet Dukascopy disponibles; si no hay, 'sin datos'."""
    key = _normalize_symbol(symbol)
    root = Path(ticks_dir)
    files = []
    if root.exists():
        for path in root.glob("*.parquet"):
            if path.name.upper().startswith(f"{key}_"):
                files.append(path)
    if not files:
        return {
            "symbol": key,
            "source": SOURCE_DUKASCOPY,
            "status": "sin datos",
            "p75_bps": None,
            "median_bps": None,
            "n_ticks": 0,
            "files": [],
        }
    frames = []
    for path in sorted(files):
        try:
            frames.append(pd.read_parquet(path))
        except OSError:
            continue
    if not frames:
        return {
            "symbol": key,
            "source": SOURCE_DUKASCOPY,
            "status": "sin datos",
            "p75_bps": None,
            "median_bps": None,
            "n_ticks": 0,
            "files": [str(path) for path in files],
        }
    frame = pd.concat(frames, ignore_index=True)
    summary = spread_summary(frame, symbol, source=SOURCE_DUKASCOPY)
    summary["files"] = [str(path) for path in files]
    summary["method"] = "all_ticks_p75"
    return summary


def source_spread(
    symbol: str,
    source: str,
    *,
    out_dir: str | Path = REPORT_DIR,
    db_path: str | Path = DB_PATH,
    ticks_dir: str | Path = TICKS_DIR,
) -> dict:
    """Spread p75 para ``research-costs`` con la fuente pedida."""
    key = str(source or "").strip().lower()
    if key == SOURCE_BROKER:
        return broker_spread_summary(symbol, out_dir=out_dir, db_path=db_path)
    if key == SOURCE_DUKASCOPY:
        return dukascopy_summary(symbol, ticks_dir=ticks_dir)
    raise ValueError("source debe ser broker o dukascopy")


def _format_bps(value: float | None) -> str:
    return "sin datos" if value is None else f"{float(value):.3f}"


def render_broker_report(report: dict) -> str:
    symbols = report.get("symbols") or {}
    lines = [
        "# Coste efectivo del bróker (ticks MT5)",
        "",
        f"- Generado: {report.get('generated_at') or 'sin datos'}",
        f"- Fuente: {report.get('source') or SOURCE_BROKER}",
        "- Solo lectura: no envía órdenes.",
        "- Una celda **sin datos** significa que no hay ticks para ese símbolo/hora; no se rellena con Dukascopy.",
        "",
        "## Resumen por símbolo",
        "",
        "| Símbolo | Ticks | Mediana bps | P75 bps | Horas | Desde | Hasta | Estado |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for key in sorted(symbols):
        item = symbols[key]
        summary = item.get("summary") or {}
        lines.append(
            f"| {key} | {int(summary.get('n_ticks') or 0):,} | "
            f"{_format_bps(summary.get('median_bps'))} | "
            f"{_format_bps(summary.get('p75_bps'))} | "
            f"{int(summary.get('hours_with_data') or 0)} | "
            f"{summary.get('from_ts') or 'sin datos'} | "
            f"{summary.get('to_ts') or 'sin datos'} | "
            f"{summary.get('status') or 'sin datos'} |"
        )
    for key in sorted(symbols):
        item = symbols[key]
        lines += [
            "",
            f"### {key}",
            "",
            "| Hora UTC | Mediana bps | P75 bps | Ticks | Desde | Hasta | Fuente |",
            "|---:|---:|---:|---:|---|---|---|",
        ]
        hours = item.get("hours") or {}
        for hour in range(24):
            row = hours.get(str(hour))
            if not row:
                lines.append(f"| {hour:02d} | sin datos | sin datos | 0 | — | — | sin datos |")
            else:
                lines.append(
                    f"| {hour:02d} | {_format_bps(row.get('median_bps'))} | "
                    f"{_format_bps(row.get('p75_bps'))} | {int(row.get('n_ticks') or 0):,} | "
                    f"{row.get('from_ts') or 'sin datos'} | {row.get('to_ts') or 'sin datos'} | "
                    f"{row.get('source') or 'sin datos'} |"
                )
    comparison = report.get("comparison")
    if comparison:
        lines += ["", "## Comparativa de costes", ""]
        body = render_comparison(comparison)
        body_lines = body.splitlines()
        if body_lines and body_lines[0].startswith("# "):
            body_lines = body_lines[1:]
        lines.extend(body_lines)
    lines.append("")
    return "\n".join(lines)


def _breakeven_outcome(report: dict) -> dict | None:
    rows = [
        row
        for row in report.get("outcomes") or []
        if row.get("breakeven_cost_bps") is not None
    ]
    return max(rows, key=lambda row: row["breakeven_cost_bps"], default=None)


def _comparison_row(
    original: dict,
    recalc: dict,
    broker: dict,
    dukascopy: dict,
) -> dict:
    symbol = str(original.get("symbol") or recalc.get("symbol") or "sin datos")
    commission = float((recalc.get("costs") or {}).get("commission_bps_median") or 0.0)
    p75 = broker.get("p75_bps")
    broker_cons = None if p75 is None else commission + float(p75) + 2.0
    broker_opt = None if p75 is None else commission + float(p75) + 0.5
    best = _breakeven_outcome(recalc)
    breakeven = (best or {}).get("breakeven_cost_bps")
    old_cost = (original.get("cost_model") or {}).get("calibrated_cost_bps_median")
    old_source = (original.get("cost_model") or {}).get("spread", {}).get("source")
    duk_p75 = dukascopy.get("p75_bps")
    duk_cost = None if duk_p75 is None else commission + float(duk_p75) + 2.0
    if broker_cons is None:
        margin = None
        sentence = (
            f"{symbol}: sin datos de ticks del bróker; no se puede concluir "
            "si pasa a tener margen."
        )
    elif breakeven is None:
        margin = None
        sentence = f"{symbol}: sin cruce de equilibrio; no se puede concluir."
    else:
        margin = bool(float(breakeven) > broker_cons)
        if margin:
            sentence = (
                f"{symbol}: pasa a tener margen con el coste bróker "
                f"({broker_cons:.2f} bps) frente al equilibrio ({float(breakeven):.2f} bps)."
            )
        else:
            sentence = (
                f"{symbol}: no pasa a tener margen; el coste bróker "
                f"({broker_cons:.2f} bps) supera el equilibrio ({float(breakeven):.2f} bps)."
            )
    return {
        "symbol": symbol,
        "old_cost_bps": None if old_cost is None else float(old_cost),
        "old_source": old_source,
        "dukascopy_p75_bps": None if duk_p75 is None else float(duk_p75),
        "dukascopy_cost_bps": duk_cost,
        "dukascopy_status": dukascopy.get("status"),
        "broker_p75_bps": None if p75 is None else float(p75),
        "broker_cost_bps": broker_cons,
        "broker_cost_optimistic_bps": broker_opt,
        "broker_status": broker.get("status"),
        "breakeven_bps": None if breakeven is None else float(breakeven),
        "margin": margin,
        "sentence": sentence,
    }


def render_comparison(comparison: dict) -> str:
    lines = [
        "# Comparativa de costes: Dukascopy vs bróker vs equilibrio",
        "",
        f"- Generado: {comparison.get('generated_at') or 'sin datos'}",
        "- Recálculo de la etapa 3: mismas variantes, sin trials nuevos, sin cambiar umbrales.",
        "- Coste bróker = comisión FTMO + spread p75 medido + slippage 2,0 bps (conservador); "
        "la columna optimista usa 0,5 bps.",
        "- Dukascopy usa solo los parquet de ticks disponibles; **sin datos** si no hay.",
        "- La tabla previa de la etapa 3 usó la columna spread de las velas MT5, no Dukascopy; se conserva como referencia.",
        "",
        "| Activo | Tabla previa MT5 bars | Dukascopy (p75 / coste) | Bróker p75 | Coste bróker (cons./opt.) | Equilibrio | Margen |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in comparison.get("rows") or []:
        old = _format_bps(row.get("old_cost_bps"))
        if row.get("dukascopy_p75_bps") is None:
            duk = "sin datos"
        elif row.get("dukascopy_cost_bps") is None:
            duk = _format_bps(row.get("dukascopy_p75_bps"))
        else:
            duk = (
                f"{_format_bps(row.get('dukascopy_p75_bps'))} / "
                f"{float(row['dukascopy_cost_bps']):.2f}"
            )
        broker = _format_bps(row.get("broker_p75_bps"))
        cost = (
            "sin datos"
            if row.get("broker_cost_bps") is None
            else f"{float(row['broker_cost_bps']):.2f} / "
            f"{float(row['broker_cost_optimistic_bps']):.2f}"
        )
        breakeven = _format_bps(row.get("breakeven_bps"))
        margin = "sin datos" if row.get("margin") is None else ("sí" if row["margin"] else "no")
        lines.append(
            f"| {row['symbol']} | {old} | {duk} | {broker} | {cost} | {breakeven} | {margin} |"
        )
    lines += ["", "## Lectura por activo", ""]
    for row in comparison.get("rows") or []:
        lines.append(f"- {row['sentence']}")
    lines.append("")
    return "\n".join(lines)


def write_comparison(
    comparison: dict,
    out_dir: str | Path = REPORT_DIR,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    comparison.setdefault("generated_at", pd.Timestamp.now(tz="UTC").isoformat())
    json_path = out / "broker_cost_comparison.json"
    md_path = out / "broker_cost_comparison.md"
    json_path.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_comparison(comparison), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def _write_recalc_report(report: dict, asset_dir: Path) -> dict[str, str]:
    asset_dir.mkdir(parents=True, exist_ok=True)
    json_path = asset_dir / "intraday_broker.json"
    md_path = asset_dir / "intraday_broker.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    from .intraday import render_markdown

    banner = (
        "> **Recálculo de coste bróker, no una búsqueda nueva.** "
        "Mismas variantes; no se crearon trials; el contador DSR no cambió.\n\n"
    )
    if report.get("status") == "sin datos":
        body = (
            f"# Recálculo de coste bróker - {report.get('symbol') or 'sin datos'}\n\n"
            f"- Estado: **sin datos**\n"
            f"- Motivo: {report.get('reason') or 'sin ticks del bróker'}\n"
            f"- DSR n_trials original: {report.get('original_dsr_n_trials')}\n"
            "- No se ejecutó el backtest ni se crearon trials.\n"
        )
    else:
        body = render_markdown(report)
    md_path.write_text(banner + body, encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def _sin_datos_report(original: dict, reason: str) -> dict:
    return {
        "symbol": original.get("symbol") or "sin datos",
        "status": "sin datos",
        "reason": reason,
        "original_run_id": original.get("run_id"),
        "original_dsr_n_trials": original.get("dsr_n_trials"),
        "outcomes": [],
        "recalculation": {
            "enabled": True,
            "reason": reason,
            "broker_spread_bps": None,
            "original_dsr_n_trials": original.get("dsr_n_trials"),
            "dsr_n_trials": original.get("dsr_n_trials"),
            "strategy_trials_before": None,
            "strategy_trials_after": None,
            "dsr_counter_unchanged": True,
            "trials_recorded": 0,
        },
    }


def recalculate_stage3(
    *,
    reports_dir: str | Path = REPORT_DIR,
    cache_dir: str | Path = ROOT / "data" / "cache",
    db_path: str | Path = DB_PATH,
    paths: int = 500,
    assets: tuple[str, ...] = STAGE3_ASSETS,
) -> dict:
    """Recalcula la etapa 3 con spread bróker p75, sin crear trials.

    Usa el ``broker_costs.json`` generado por ``lab ticks broker-spread`` y los
    mismos informes originales para conservar familias, variantes y
    ``dsr_n_trials``. Escribe ``intraday_broker.md/json`` en cada carpeta y una
    comparativa global.
    """
    from .intraday import load_bars, run_intraday
    from .learning import count_tests

    reports = Path(reports_dir)
    broker_report = load_broker_report(reports)
    comparison_rows = []
    asset_results = {}
    errors = []
    for asset in assets:
        original_path = reports / f"intraday_{asset}" / "intraday.json"
        if not original_path.exists():
            errors.append(f"{asset}: no existe {original_path}")
            continue
        original = json.loads(original_path.read_text(encoding="utf-8"))
        symbol = str(original.get("symbol") or asset)
        key = _normalize_symbol(symbol)
        broker_item = (broker_report.get("symbols") or {}).get(key) or {}
        summary = broker_item.get("summary") or {}
        p75 = summary.get("p75_bps")
        asset_dir = reports / f"intraday_{asset}"
        if p75 is None:
            report = _sin_datos_report(
                original,
                f"sin ticks del bróker para {key} en broker_costs.json",
            )
            files = _write_recalc_report(report, asset_dir)
            asset_results[asset] = {"report": report, "files": files}
            dukascopy = dukascopy_summary(symbol)
            comparison_rows.append(
                _comparison_row(original, report, {"status": "sin datos", "p75_bps": None}, dukascopy)
            )
            continue
        p75 = float(p75)
        before = count_tests(db_path)
        recalc_meta = {
            "enabled": True,
            "reason": (
                "Recalculo de coste con spread broker p75; mismas variantes, "
                "sin busqueda nueva y sin crear trials."
            ),
            "original_run_id": original.get("run_id"),
            "original_report": str(original_path),
            "original_dsr_n_trials": original.get("dsr_n_trials"),
            "broker_spread_bps": p75,
            "broker_source": summary.get("source"),
            "broker_window": broker_item.get("window"),
            "strategy_trials_before": before,
        }
        try:
            bars = load_bars(cache_dir, symbol, original.get("timeframe") or "M15")
            report = run_intraday(
                bars,
                symbol=symbol,
                timeframe=original.get("timeframe") or "M15",
                paths=paths,
                families=tuple(original.get("families") or ()),
                spread_override_bps=p75,
                spread_override_reliable=True,
                spread_label="broker: MT5 ticks p75",
                db_path=db_path,
                record=False,
                dsr_n_trials=int(
                    original.get("dsr_n_trials")
                    or original.get("n_trials")
                    or 0
                ),
                recalculation=recalc_meta,
            )
        except Exception as exc:
            report = _sin_datos_report(original, f"error en recalculo: {exc}")
            files = _write_recalc_report(report, asset_dir)
            asset_results[asset] = {"report": report, "files": files}
            errors.append(f"{asset}: {exc}")
            dukascopy = dukascopy_summary(symbol)
            comparison_rows.append(
                _comparison_row(original, report, {"status": "sin datos", "p75_bps": None}, dukascopy)
            )
            continue
        after = count_tests(db_path)
        recalc = report.get("recalculation") or {}
        expected = int(original.get("dsr_n_trials") or original.get("n_trials") or 0)
        same_variants = len(report.get("outcomes") or []) == len(original.get("outcomes") or [])
        recalc.update(
            {
                "strategy_trials_before": recalc.get("strategy_trials_before", before),
                "strategy_trials_after": after,
                "dsr_counter_unchanged": before == after,
                "same_variants": same_variants,
                "outcomes_original": len(original.get("outcomes") or []),
                "outcomes_recalc": len(report.get("outcomes") or []),
            }
        )
        report["recalculation"] = recalc
        if before != after:
            raise RuntimeError(
                f"{asset}: el recalculo cambio el contador DSR ({before} -> {after})"
            )
        if not same_variants:
            raise RuntimeError(
                f"{asset}: el recalculo no conservo las variantes "
                f"({len(original.get('outcomes') or [])} -> "
                f"{len(report.get('outcomes') or [])})"
            )
        if int(report.get("dsr_n_trials") or -1) != expected:
            raise RuntimeError(
                f"{asset}: dsr_n_trials cambio ({expected} -> {report.get('dsr_n_trials')})"
            )
        files = _write_recalc_report(report, asset_dir)
        asset_results[asset] = {"report": report, "files": files}
        comparison_rows.append(
            _comparison_row(
                original,
                report,
                {"status": summary.get("status"), "p75_bps": p75},
                dukascopy_summary(symbol),
            )
        )
    comparison = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "broker",
        "note": (
            "Recalculo de la etapa 3 con spread broker p75. Mismas 84 variantes; "
            "no se registraron trials ni se cambio el contador DSR. "
            "La tabla previa uso MT5 bars; Dukascopy solo donde hay parquet."
        ),
        "rows": comparison_rows,
        "errors": errors,
    }
    files = write_comparison(comparison, reports)
    merge_comparison_into_broker_report(comparison, reports)
    return {
        "comparison": comparison,
        "assets": asset_results,
        "files": files,
        "errors": errors,
    }


__all__ = [
    "DB_PATH",
    "REPORT_DIR",
    "SOURCE_BROKER",
    "SOURCE_DUKASCOPY",
    "SPREAD_COLUMNS",
    "TICKS_DIR",
    "add_spread_bps",
    "broker_spread_summary",
    "collect_broker",
    "dukascopy_summary",
    "hourly_spreads",
    "load_broker_report",
    "load_spreads",
    "merge_broker_report",
    "merge_comparison_into_broker_report",
    "mt5_swap",
    "persist_spreads",
    "recalculate_stage3",
    "render_broker_report",
    "render_comparison",
    "source_spread",
    "spread_summary",
    "write_comparison",
]
