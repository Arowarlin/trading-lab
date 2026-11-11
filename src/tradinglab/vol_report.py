"""Comparación con y sin objetivo de volatilidad.

No activa nada: es un informe. `lab research --vol-target on` ejecuta el
research normal y después escribe esta comparación en
`reports/research/vol_target/comparison.md`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import run as run_backtest
from .config import ROOT, get_settings
from .data import fetch
from .orchestrator import BotSpec, load_bots
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo
from .strategies import STRATEGIES
from .vol_target import profile_vol_config

DEFAULT_BOTS = ("qqq-trend-f13", "trend-spy", "meanrev-large")
MC_PATHS = 2_000
MC_HORIZON = 120
MC_BLOCK = 5
MC_SEED = 42


def _specs(bot_ids: tuple[str, ...] | list[str]) -> list[BotSpec]:
    catalog = {spec.id: spec for spec in load_bots()}
    out: list[BotSpec] = []
    for bot_id in bot_ids:
        spec = catalog.get(bot_id)
        if spec is None:
            # permite el nombre de la estrategia (p. ej. "meanrev") como atajo
            candidates = [item for item in catalog.values() if item.strategy == bot_id]
            spec = candidates[0] if len(candidates) == 1 else None
        if spec is None:
            continue
        out.append(spec)
    return out


def _cost_metrics(bt, slippage_bps: float) -> dict:
    trades = bt.trades
    turnover_notional = 0.0
    fees = 0.0
    if trades is not None and not trades.empty:
        turnover_notional = float((trades["qty"].abs() * trades["price"]).sum())
        fees = float(trades["fee"].sum())
    equity = bt.equity.astype(float)
    average_equity = float(equity.mean()) if len(equity) else 0.0
    turnover = turnover_notional / average_equity if average_equity else 0.0
    slippage_cost = turnover_notional * float(slippage_bps) / 10_000.0
    return {
        "turnover": turnover,
        "commission": fees,
        "slippage_cost": slippage_cost,
        "cost": fees + slippage_cost,
    }


def _run(spec: BotSpec, *, vol_target: dict | None):
    settings = get_settings()
    symbol = (spec.universe or ["SPY"])[0].upper()
    df = fetch(symbol, "2015-01-01", "", settings.data.cache_dir)
    strategy_fn = STRATEGIES[spec.strategy]
    signal = strategy_fn(df, **(spec.params or {}))
    exposure = float(spec.exposure or 1.0)
    target = (signal.target.astype(float) * exposure).clip(-1.0, 1.0)
    bt = run_backtest(
        df,
        target,
        starting_cash=100_000.0,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
        vol_target=vol_target,
    )
    return bt, symbol


def _mc(returns: pd.Series) -> dict:
    rules = from_yaml("ftmo", "challenge", 100_000.0)
    try:
        result = monte_carlo(
            rules,
            returns,
            n_paths=MC_PATHS,
            horizon=MC_HORIZON,
            block_size=MC_BLOCK,
            seed=MC_SEED,
        )
        return {
            "pass_rate": result["pass_rate"],
            "breach_rate": result["breach_rate"],
            "timeout_rate": result["timeout_rate"],
        }
    except Exception as exc:
        return {"pass_rate": None, "breach_rate": None, "error": str(exc)[:160]}


def compare(
    bot_ids: tuple[str, ...] | list[str] = DEFAULT_BOTS,
    out_dir: Path | None = None,
) -> Path:
    """Ejecuta ambos backtests por bot y escribe el informe."""
    settings = get_settings()
    target_dir = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "vol_target"
    target_dir.mkdir(parents=True, exist_ok=True)
    rules = from_yaml("ftmo", "challenge", 100_000.0)

    rows: list[dict] = []
    for spec in _specs(list(bot_ids)):
        profile = profile_vol_config(spec.profile or "swing_equity")
        target_vol = profile.get("target_vol")
        if not target_vol:
            continue
        try:
            base_bt, symbol = _run(spec, vol_target=None)
            vol_bt, _ = _run(
                spec,
                vol_target={
                    "target_vol_annual": float(target_vol),
                    "halflife_days": 30,
                    "max_leverage": 2.0,
                    "rebalance": "W",
                },
            )
        except Exception as exc:
            rows.append({"bot": spec.id, "error": str(exc)[:200]})
            continue

        base = base_bt.metrics
        vol = vol_bt.metrics
        base_cost = _cost_metrics(base_bt, settings.execution.slippage_bps)
        vol_cost = _cost_metrics(vol_bt, settings.execution.slippage_bps)
        rows.append(
            {
                "bot": spec.id,
                "symbol": symbol,
                "profile": spec.profile,
                "target_vol": float(target_vol),
                "base": {
                    "sharpe": base.get("sharpe"),
                    "max_drawdown": base.get("max_drawdown"),
                    "total_return": base.get("total_return"),
                    "num_trades": base.get("num_trades"),
                    **base_cost,
                    "mc": _mc(base_bt.returns),
                },
                "vol": {
                    "sharpe": vol.get("sharpe"),
                    "max_drawdown": vol.get("max_drawdown"),
                    "total_return": vol.get("total_return"),
                    "num_trades": vol.get("num_trades"),
                    **vol_cost,
                    "mc": _mc(vol_bt.returns),
                },
            }
        )

    lines = [
        "# Objetivo de volatilidad: con y sin",
        "",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Límites del simulador: {rules.describe()}",
        f"- Monte Carlo: {MC_PATHS} paths, {MC_HORIZON} días, bloque {MC_BLOCK}, seed {MC_SEED}",
        "- El perfil mantiene `vol_target.enabled: false`: este informe **no activa nada**.",
        "",
    ]
    if not rows:
        lines += ["Sin datos: no hay bots con perfil y `target_vol` conocido.", ""]
    for row in rows:
        lines += [f"## {row.get('bot')}"]
        if row.get("error"):
            lines += [f"- Error: {row['error']}", ""]
            continue
        base = row["base"]
        vol = row["vol"]
        lines += [
            f"- Símbolo {row['symbol']} · perfil {row['profile']} · objetivo de volatilidad "
            f"{row['target_vol']:.1%}",
            "",
            "| Métrica | Sin objetivo | Con objetivo |",
            "|---|---:|---:|",
            f"| Sharpe | {base['sharpe']:.2f} | {vol['sharpe']:.2f} |",
            f"| MaxDD | {base['max_drawdown']:.2%} | {vol['max_drawdown']:.2%} |",
            f"| Retorno total | {base['total_return']:.2%} | {vol['total_return']:.2%} |",
            f"| Operaciones | {base['num_trades']} | {vol['num_trades']} |",
            f"| Turnover | {base['turnover']:.2f} | {vol['turnover']:.2f} |",
            f"| Coste total | {base['cost']:,.0f} | {vol['cost']:,.0f} |",
            f"| Coste extra | - | {vol['cost'] - base['cost']:,.0f} |",
            f"| P(pasar) FTMO | {_pct(base['mc'].get('pass_rate'))} | {_pct(vol['mc'].get('pass_rate'))} |",
            f"| P(breach) FTMO | {_pct(base['mc'].get('breach_rate'))} | {_pct(vol['mc'].get('breach_rate'))} |",
            "",
        ]

    path = target_dir / "comparison.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    (target_dir / "comparison.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return path


def _pct(value: float | None) -> str:
    return "Sin datos" if value is None else f"{float(value):.2%}"


__all__ = ["DEFAULT_BOTS", "compare"]
