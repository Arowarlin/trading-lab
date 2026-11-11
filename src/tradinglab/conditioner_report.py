"""Comparación con y sin condicionadores (informe; no activa nada)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run as run_backtest
from .conditioners import bot_multiplier_table, flags_series, proposal_table
from .config import ROOT, get_settings
from .data import fetch
from .orchestrator import load_bots
from .strategies import STRATEGIES


def _blocks(returns: pd.Series, n: int = 4) -> int:
    """Bloques con retorno medio positivo (proxy de folds de walk-forward)."""
    clean = returns.dropna()
    if len(clean) < n:
        return 0
    positive = 0
    for chunk in np.array_split(clean.to_numpy(), n):
        if float(np.mean(chunk)) > 0:
            positive += 1
    return positive


def _run(bot, *, conditioned: bool, table: dict[str, float]):
    settings = get_settings()
    symbol = (bot.universe or ["SPY"])[0].upper()
    df = fetch(symbol, "2015-01-01", "", settings.data.cache_dir)
    strategy_fn = STRATEGIES[bot.strategy]
    signal = strategy_fn(df, **(bot.params or {}))
    target = (signal.target.astype(float) * float(bot.exposure or 1.0)).clip(-1.0, 1.0)
    days = None
    if conditioned:
        frame, _warnings = flags_series(
            symbol, df["close"].astype(float), db_path=ROOT / "data" / "lab.db"
        )
        from .strategies.base import exposure_multiplier

        multiplier = frame.apply(
            lambda row: exposure_multiplier(
                {name: bool(row.get(name, False)) for name in frame.columns}, table
            ),
            axis=1,
        )
        target = (target * multiplier.reindex(target.index).fillna(1.0)).clip(-1.0, 1.0)
        days = int((multiplier != 1.0).sum())
    bt = run_backtest(
        df,
        target,
        starting_cash=100_000.0,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    return bt, symbol, days


def compare(bot_ids: list[str] | None = None, out_dir: Path | None = None) -> list[Path]:
    """Ejecuta cada bot con y sin condicionadores y escribe el informe."""
    target_dir = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "conditioners"
    target_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_bots()
    if bot_ids:
        catalog = [bot for bot in catalog if bot.id in set(bot_ids)]
    written: list[Path] = []
    for bot in catalog:
        if bot.strategy not in STRATEGIES:
            continue
        table = bot_multiplier_table(bot.id) or proposal_table(bot.id)
        try:
            base, symbol, _ = _run(bot, conditioned=False, table=table)
            cond, _symbol, days = _run(bot, conditioned=True, table=table)
        except Exception as exc:
            path = target_dir / f"{bot.id}.md"
            path.write_text(
                f"# Condicionadores · {bot.id}\n\n- Error: {str(exc)[:300]}\n",
                encoding="utf-8",
            )
            written.append(path)
            continue

        base_returns = base.returns
        cond_returns = cond.returns
        stitched = pd.concat([cond_returns, base_returns], axis=1).ffill().iloc[:, 0]
        lines = [
            f"# Condicionadores · {bot.id}",
            "",
            f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- Símbolo: {symbol} · estrategia {bot.strategy}",
            f"- Multiplicadores: {json.dumps(table, ensure_ascii=False) if table else 'sin tabla (todo 1,0)'}",
            f"- Días afectados: {days}",
            "",
            "| Métrica | Sin condicionadores | Con condicionadores |",
            "|---|---:|---:|",
            f"| Sharpe | {float(base.metrics.get('sharpe', 0.0)):.2f} | {float(cond.metrics.get('sharpe', 0.0)):.2f} |",
            f"| Sharpe stitched | - | {float(stitched.mean() / (stitched.std(ddof=1) or 1) * np.sqrt(252)):.2f} |",
            f"| MaxDD | {float(base.metrics.get('max_drawdown', 0.0)):.2%} | {float(cond.metrics.get('max_drawdown', 0.0)):.2%} |",
            f"| Retorno total | {float(base.metrics.get('total_return', 0.0)):.2%} | {float(cond.metrics.get('total_return', 0.0)):.2%} |",
            f"| Bloques positivos (4) | {_blocks(base_returns)} | {_blocks(cond_returns)} |",
            "",
            "Cada variante condicionada suma **1** al contador de pruebas del DSR.",
            "",
        ]
        path = target_dir / f"{bot.id}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)

        try:
            from .trials import record_trial

            record_trial(
                ROOT / "data" / "lab.db",
                family="conditioners",
                hypothesis=(
                    "los condicionadores (pre_fomc, tom_window, month_end_selloff, "
                    "monday_overnight, boundary_extreme) ajustan la exposicion"
                ),
                symbol=(bot.universe or ["SPY"])[0].upper(),
                params={"bot": bot.id, "multipliers": table},
                result={
                    "sharpe": float(cond.metrics.get("sharpe", 0.0)),
                    "max_drawdown": float(cond.metrics.get("max_drawdown", 0.0)),
                    "days_affected": days,
                },
                outcome="failed",
                reason="informe de condicionadores (no promotiona nada)",
                source="automatico",
                counted=True,
            )
        except Exception:
            pass
    return written


__all__ = ["compare"]
