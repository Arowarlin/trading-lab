"""Sensibilidad del top de research a comisión y slippage.

Reejecuta el backtest existente con los mismos datos y parámetros, sin tocar
criterios de propuesta ni enviar órdenes.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as data_mod
from .backtest import run as run_backtest
from .config import ROOT
from .strategies import STRATEGIES

SCENARIOS = {
    "zero": (0.0, 0.0),
    "base": (1.0, 5.0),
    "double": (2.0, 10.0),
    "stress": (2.0, 20.0),
}


def _metrics(returns: pd.Series) -> dict:
    equity = (1.0 + returns).cumprod()
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    dd = equity / equity.cummax() - 1.0
    return {
        "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "sharpe": float(returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0,
        "max_drawdown": float(dd.min()) if len(dd) else 0.0,
    }


def run_costs(
    report_dir: str | Path = ROOT / "reports" / "research",
    *,
    cache_dir: str | Path = ROOT / "data" / "cache",
    top: int = 10,
    source: str = "none",
    db_path: str | Path | None = None,
    ticks_dir: str | Path | None = None,
) -> dict:
    report_dir = Path(report_dir)
    latest_path = report_dir / "latest.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"no existe {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    results = list(latest.get("results") or [])[: max(1, top)]
    cfg = latest.get("config") or {}
    start = str(cfg.get("start") or "2015-01-01")
    end = str(cfg.get("end") or date.today().isoformat())
    selected_source = str(source or "none").strip().lower()
    if selected_source not in {"none", "broker", "dukascopy"}:
        raise ValueError("source debe ser broker, dukascopy o none")
    spread_cache: dict[str, dict] = {}
    rows = []
    data_cache: dict[str, pd.DataFrame] = {}
    for rank, result in enumerate(results, 1):
        symbol = str(result.get("symbol"))
        strategy = str(result.get("strategy"))
        params = result.get("params") or {}
        exposure = float(result.get("exposure") or 1.0)
        spread_bps = 0.0
        spread_source = "none"
        spread_method = None
        data_ok = True
        if selected_source in {"broker", "dukascopy"}:
            if symbol not in spread_cache:
                from .broker_costs import DB_PATH, TICKS_DIR, source_spread

                spread_cache[symbol] = source_spread(
                    symbol,
                    selected_source,
                    db_path=db_path or DB_PATH,
                    ticks_dir=ticks_dir or TICKS_DIR,
                )
            item = spread_cache[symbol]
            spread_method = item.get("method")
            if item.get("p75_bps") is None:
                data_ok = False
                spread_source = "sin datos"
            else:
                spread_bps = float(item["p75_bps"])
                spread_source = selected_source
        if symbol not in data_cache:
            data_cache[symbol] = data_mod.fetch(symbol, start, end, cache_dir)
        df = data_cache[symbol]
        sig = STRATEGIES[strategy](df, **params)
        scenarios = {}
        for name, (commission, slippage) in SCENARIOS.items():
            bt = run_backtest(
                df,
                sig.target,
                starting_cash=100_000,
                commission_bps=commission + spread_bps,
                slippage_bps=slippage,
            )
            metrics = _metrics(bt.returns * exposure)
            metrics["num_trades"] = int(bt.metrics.get("num_trades") or 0)
            metrics["spread_bps"] = spread_bps
            scenarios[name] = metrics
        base = scenarios["base"]["total_return"]
        stress = scenarios["stress"]["total_return"]
        fragile = None
        if data_ok:
            fragile = bool(base <= 0 or stress <= 0 or (base > 0 and stress <= 0))
        rows.append(
            {
                "rank": rank,
                "symbol": symbol,
                "strategy": strategy,
                "params": params,
                "exposure": exposure,
                "spread_bps": spread_bps,
                "spread_source": spread_source,
                "spread_method": spread_method,
                "data_ok": data_ok,
                "scenarios": scenarios,
                "fragile": fragile,
                "cost_drag": float(base - stress),
            }
        )
    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": str(latest_path),
        "start": start,
        "end": end,
        "spread_source": selected_source,
        "scenarios": {
            k: {"commission_bps": v[0], "slippage_bps": v[1]}
            for k, v in SCENARIOS.items()
        },
        "results": rows,
        "fragile_count": sum(1 for row in rows if row["fragile"] is True),
        "sin_datos_count": sum(1 for row in rows if not row["data_ok"]),
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# Sensibilidad a costes del top de research",
        "",
        f"- Fuente: {payload['source']}",
        f"- Muestra: {payload['start']} → {payload['end']}",
        f"- Escenarios: {', '.join(payload['scenarios'])}",
        f"- Spread: {payload.get('spread_source', 'none')}",
        f"- Frágiles: {payload['fragile_count']}/{len(payload['results'])}",
        f"- Sin datos de spread: {payload.get('sin_datos_count', 0)}/{len(payload['results'])}",
        "",
        "> Solo informativo. Un edge que desaparece con costes realistas no se propone.",
        "",
        "| # | Variante | Base | Doble | Estrés | Zero | Spread | Fragil |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["results"]:
        base = row["scenarios"]["base"]["total_return"]
        double = row["scenarios"]["double"]["total_return"]
        stress = row["scenarios"]["stress"]["total_return"]
        zero = row["scenarios"]["zero"]["total_return"]
        spread = "sin datos" if not row.get("data_ok", True) else f"{row.get('spread_bps', 0.0):.2f}"
        fragile = "sin datos" if row.get("fragile") is None else ("sí" if row["fragile"] else "no")
        label = f"{row['symbol']} · {row['strategy']} · {json.dumps(row['params'], ensure_ascii=False, sort_keys=True)}"
        lines.append(
            f"| {row['rank']} | {label} | {base:.1%} | {double:.1%} | "
            f"{stress:.1%} | {zero:.1%} | {spread} | {fragile} |"
        )
    lines.append("")
    return "\n".join(lines)


def write(payload: dict, out_dir: str | Path = ROOT / "reports" / "research") -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "costs.json"
    md_path = out / "costs.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


__all__ = ["SCENARIOS", "render_markdown", "run_costs", "write"]
