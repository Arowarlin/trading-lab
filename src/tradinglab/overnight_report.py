"""Informe de la reversión overnight (no activa nada)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.config import ROOT, get_settings
from tradinglab.data import fetch
from tradinglab.prop.rules import from_yaml
from tradinglab.prop.simulator import monte_carlo
from tradinglab.strategies.overnight_reversal import (
    overnight_returns,
    select_terciles,
    simulate_daily,
)

UNIVERSE = (
    "SPY,QQQ,IWM,DIA,XLK,XLF,XLE,XLV,XLY,XLP,XLI,XLU,XLB,XLRE,XLC,TLT,GLD"
)
COSTS_BPS = (0.0, 2.0, 5.0)


def run(out_dir: Path | None = None) -> Path:
    """Backtest diario del universo con la reversión overnight."""
    settings = get_settings()
    target_dir = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "overnight_reversal"
    target_dir.mkdir(parents=True, exist_ok=True)
    symbols = [item.strip().upper() for item in UNIVERSE.split(",") if item.strip()]

    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            frames[symbol] = fetch(symbol, "2015-01-01", "", settings.data.cache_dir)
        except Exception:
            continue
    if not frames:
        path = target_dir / "report.md"
        path.write_text(
            "# Reversión overnight\n\n- Sin datos: no se pudo descargar el universo.\n",
            encoding="utf-8",
        )
        return path

    returns = {symbol: overnight_returns(frame) for symbol, frame in frames.items()}
    cross = pd.DataFrame(returns)
    common = cross.dropna(how="any")
    selection = select_terciles(common)

    rows: list[dict] = []
    series: dict[float, pd.Series] = {}
    for cost in COSTS_BPS:
        net, stats = simulate_daily(frames, selection, cost_bps=cost)
        net = net.reindex(common.index).fillna(0.0)
        series[cost] = net
        equity = (1 + net).cumprod()
        years = max(len(net) / 252, 1 / 252)
        cagr = float(equity.iloc[-1] ** (1 / years) - 1) if len(net) else 0.0
        sharpe = (
            float(net.mean() / (net.std(ddof=1) or 1) * np.sqrt(252)) if len(net) else 0.0
        )
        rows.append(
            {
                "cost_bps": cost,
                "sharpe": sharpe,
                "cagr": cagr,
                "max_drawdown": float((equity / equity.cummax() - 1).min()),
                "trades": stats["trades"],
                "turnover": stats["turnover"],
                "total_return": float(equity.iloc[-1] - 1),
            }
        )

    rules = from_yaml("ftmo", "challenge", 100_000.0)
    mc = {}
    for cost in COSTS_BPS:
        net = series[cost]
        try:
            result = monte_carlo(
                rules, net, n_paths=2000, horizon=120, block_size=5, seed=42
            )
            mc[cost] = {
                "pass_rate": result["pass_rate"],
                "breach_rate": result["breach_rate"],
            }
        except Exception as exc:
            mc[cost] = {"error": str(exc)[:160]}

    lines = [
        "# Reversión overnight",
        "",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Universo: {len(frames)} de {len(symbols)} símbolos con datos",
        f"- Reglas del simulador: {rules.describe()}",
        "- Costes: 0 bps (optimista), 2 bps y 5 bps por lado (conservador).",
        "- Sin posición nocturna: se entra en la apertura y se sale en el cierre.",
        "",
        "| Coste | Sharpe | CAGR | MaxDD | Retorno | Operaciones | Turnover | P(pasar) | P(breach) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        cost = row["cost_bps"]
        lines.append(
            f"| {cost:g} bps | {row['sharpe']:.2f} | {row['cagr']:.2%} | "
            f"{row['max_drawdown']:.2%} | {row['total_return']:.2%} | {row['trades']} | "
            f"{row['turnover']:.2f} | {mc[cost].get('pass_rate', 0):.2%} | "
            f"{mc[cost].get('breach_rate', 0):.2%} |"
        )
    lines += [
        "",
        "La selección es transversal (tercil más bajo y más alto del universo).",
        "",
    ]
    path = target_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    (target_dir / "report.json").write_text(
        json.dumps({"rows": rows, "monte_carlo": mc}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    print(run())
