"""Recalcula el DSR v2 del historial sin correr backtests ni escribir en SQLite.

Lee los Sharpes registrados y los informes guardados. El comando por defecto es
un dry-run: solo escribe `reports/audit/dsr_v2.md` y su JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import DEFAULT_DB, ROOT
from .db import connect
from .global_dsr import (
    DAILY,
    global_srs,
    periods_for_timeframe,
    sr_from_annual,
)
from .learning import count_tests
from .stats import dsr_from_returns


def _ea_row(db_path: str | Path, n_trials: int, global_info: dict) -> dict:
    path = ROOT / "reports" / "ea" / "us100-ftmo1_v3.json"
    payload = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
    return {
        "entity": "EA us100-ftmo1",
        "dsr_v1": 1.0,
        "dsr_v1_note": "v1 documentado; dsr_v1_invalid_units",
        "dsr_local": payload.get("dsr_local"),
        "dsr_global": payload.get("dsr_global"),
        "n_trials": int(n_trials),
        "n_sharpes": int(global_info.get("n_srs") or 0),
        "sources": dict(global_info.get("sources") or {}),
        "note": "dsr_local N=8 informativo; gate = dsr_global",
    }


def _f13_row(db_path: str | Path, n_trials: int, global_info: dict) -> dict:
    with connect(db_path) as con:
        frame = con.execute(
            "SELECT trade_date, daily_return FROM f13_metrics "
            "ORDER BY trade_date"
        ).fetchall()
    returns = [
        float(row["daily_return"])
        for row in frame
        if row["daily_return"] is not None
    ]
    dsr_global = None
    note = "Sin datos: no hay retornos diarios de F13"
    if len(returns) >= 3 and global_info.get("available"):
        payload = dsr_from_returns(
            returns, global_info["srs"], n_trials
        )
        dsr_global = payload["dsr"]
        note = "v2 calculado con f13_metrics; v1 no existía"
    return {
        "entity": "F13 qqq-trend-f13",
        "dsr_v1": None,
        "dsr_v1_note": "Sin datos: F13 no usó DSR",
        "dsr_local": None,
        "dsr_global": dsr_global,
        "n_trials": int(n_trials),
        "n_sharpes": int(global_info.get("n_srs") or 0),
        "sources": dict(global_info.get("sources") or {}),
        "note": note,
    }


def _campaign_sharpes(db_path: str | Path, run_id: str | None) -> int:
    if not run_id:
        return 0
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT params, result FROM strategy_trials WHERE run_id = ?",
            (str(run_id),),
        ).fetchall()
    count = 0
    for row in rows:
        try:
            params = json.loads(row["params"] or "{}")
            result = json.loads(row["result"] or "{}")
        except (TypeError, ValueError):
            continue
        timeframe = params.get("timeframe") if isinstance(params, dict) else None
        periods = periods_for_timeframe(timeframe)
        if periods is None:
            continue
        if sr_from_annual(
            result.get("sharpe") if isinstance(result, dict) else None,
            periods,
        ) is not None:
            count += 1
    return count


def _campaign_row(db_path: str | Path, campaign: str, n_trials: int) -> dict:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT n_total, run_id FROM campaign_registry WHERE campaign_id = ?",
            (campaign,),
        ).fetchone()
    if row is None:
        return {
            "entity": f"Campaña {campaign}",
            "dsr_v1": None,
            "dsr_local": None,
            "dsr_global": None,
            "n_trials": 0,
            "n_sharpes": 0,
            "sources": {},
            "note": "Sin datos: campaña no registrada",
        }
    n_sharpes = _campaign_sharpes(db_path, row["run_id"])
    return {
        "entity": f"Campaña {campaign}",
        "dsr_v1": None,
        "dsr_v1_note": "Sin datos: 0 candidatas confirmadas",
        "dsr_local": None,
        "dsr_global": None,
        "n_trials": int(row["n_total"]),
        "n_sharpes": n_sharpes,
        "sources": {"strategy_trials:campaign": n_sharpes},
        "note": "Sin datos: el run no guardó serie de retorno por celda",
    }


def build_report(db_path: str | Path = DEFAULT_DB) -> dict:
    from .campaign import init_campaigns

    init_campaigns(db_path)
    n_trials = count_tests(db_path)
    daily = global_srs(db_path, DAILY)
    rows = [
        _ea_row(db_path, n_trials, daily),
        _f13_row(db_path, n_trials, daily),
        _campaign_row(db_path, "2026-11-A", n_trials),
        _campaign_row(db_path, "2026-11-B", n_trials),
    ]
    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "read_only": True,
        "metric_version": "dsr_v2",
        "n_trials": n_trials,
        "frequency": DAILY,
        "n_sharpes": int(daily.get("n_srs") or 0),
        "sources": dict(daily.get("sources") or {}),
        "rows": rows,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# DSR v2 · recálculo del historial",
        "",
        f"Generado: {payload['generated_at']} · **solo lectura**",
        "",
        f"- `count_tests`: **{payload['n_trials']}**",
        f"- Sharpes diarios disponibles: **{payload['n_sharpes']}**",
        f"- Fuentes: {payload['sources']}",
        "",
        "| Entidad | DSR v1 | DSR local | DSR global | N | Sharpes | Fuentes |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["rows"]:
        def fmt(value):
            return "Sin datos" if value is None else f"{float(value):.4f}"

        lines.append(
            f"| {row['entity']} | {fmt(row['dsr_v1'])} | "
            f"{fmt(row['dsr_local'])} | {fmt(row['dsr_global'])} | "
            f"{row['n_trials']} | {row['n_sharpes']} | "
            f"{row.get('sources') or {}} |"
        )
    lines += [
        "",
        "## Notas",
        "",
        "- No se ejecutó ningún backtest ni se sumaron pruebas.",
        "- `dsr_global` usa N = `count_tests` y la dispersión de Sharpes por",
        "  periodo convertidos con su temporalidad; si no hay 30, queda Sin datos.",
        "- Las campañas A y B no guardaron la serie de retorno por celda: su",
        "  `dsr_local` y `dsr_global` quedan Sin datos; solo se informa el número",
        "  de Sharpes de sus celdas registradas.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir) if out_dir else ROOT / "reports" / "audit"
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "dsr_v2.json"
    md_path = target / "dsr_v2.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = ["build_report", "render_markdown", "write_report"]
