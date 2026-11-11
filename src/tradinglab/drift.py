"""Deriva live/paper vs backtest por bot. Solo lectura e informativo.

No bloquea órdenes. Compara Sharpe y expectancy del Diario con la última
evaluación del bot, con intervalos bootstrap, y el slippage real (fills vs
señal) con el supuesto del backtest. Sin muestra suficiente: "sin datos".
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .accounts import load_accounts
from .botlab import latest_evaluations
from .config import Settings
from .f13 import execution_metrics, load_criteria
from .journal import load_closed_trades, summarize
from .orchestrator import load_bots

MIN_TRADES = 20
MIN_SLIPPAGE_FILLS = 5
BOOTSTRAP_PATHS = 1_000
SEED = 42
STATUS_ORDER = {"ok": 0, "vigilar": 1, "deriva": 2}


def classify_metric(
    live: float | None,
    backtest: float | None,
    ci_low: float | None,
    ci_high: float | None,
) -> tuple[str, float | None]:
    """ok si el backtest cae en el IC; vigilar/deriva por z del IC."""
    if live is None or backtest is None or ci_low is None or ci_high is None:
        return "sin datos", None
    if ci_low <= backtest <= ci_high:
        return "ok", 0.0
    half = (ci_high - ci_low) / 2.0
    se = half / 1.96
    if se <= 0:
        return "sin datos", None
    z = abs(live - backtest) / se
    if z > 3.0:
        return "deriva", z
    if z > 1.96:
        return "vigilar", z
    return "ok", z


def classify_slippage(
    fills: int,
    p50_bps: float | None,
    p95_bps: float | None,
    *,
    backtest_bps: float,
    max_p50_bps: float = 10.0,
    max_p95_bps: float = 25.0,
    min_fills: int = MIN_SLIPPAGE_FILLS,
) -> tuple[str, list[str]]:
    if fills < min_fills or p50_bps is None:
        return "sin datos", [f"fills={fills} < {min_fills}"]
    reasons = []
    if p50_bps > max_p50_bps or (p95_bps is not None and p95_bps > max_p95_bps):
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps / p95={p95_bps if p95_bps is not None else float('nan'):.1f}bps "
            f"supera máximos {max_p50_bps:.0f}/{max_p95_bps:.0f}"
        )
        return "deriva", reasons
    if p50_bps > backtest_bps + 5.0:
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps > backtest {backtest_bps:.1f}bps + 5"
        )
        return "vigilar", reasons
    reasons.append(
        f"slippage p50={p50_bps:.1f}bps vs backtest {backtest_bps:.1f}bps"
    )
    return "ok", reasons


def _bootstrap_sharpe(
    trades, capital: float | None
) -> tuple[float | None, float | None, float | None]:
    if not trades or capital is None or capital <= 0:
        return None, None, None
    daily: dict[str, float] = {}
    for trade in trades:
        daily[trade.day] = daily.get(trade.day, 0.0) + trade.pnl
    if len(daily) < 2:
        return None, None, None
    returns = np.asarray(
        [daily[day] / capital for day in sorted(daily)], dtype=float
    )
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(BOOTSTRAP_PATHS):
        sample = rng.choice(returns, size=len(returns), replace=True)
        std = float(sample.std(ddof=1)) if len(sample) > 1 else 0.0
        values.append(
            float(sample.mean() / std * math.sqrt(252)) if std > 0 else 0.0
        )
    low, high = np.percentile(values, [2.5, 97.5])
    return float(np.mean(values)), float(low), float(high)


def _bootstrap_expectancy(trades) -> tuple[float | None, float | None, float | None]:
    values = np.asarray([trade.pnl for trade in trades], dtype=float)
    if values.size < 2:
        return None, None, None
    rng = np.random.default_rng(SEED)
    means = [
        float(rng.choice(values, size=values.size, replace=True).mean())
        for _ in range(BOOTSTRAP_PATHS)
    ]
    low, high = np.percentile(means, [2.5, 97.5])
    return float(np.mean(means)), float(low), float(high)


def _merge_status(statuses: list[str]) -> str:
    known = [status for status in statuses if status in STATUS_ORDER]
    if not known:
        return "sin datos"
    return max(known, key=lambda status: STATUS_ORDER[status])


def build_drift(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    min_trades: int = MIN_TRADES,
    min_slippage_fills: int = MIN_SLIPPAGE_FILLS,
) -> dict:
    """Deriva informativa de todos los bots configurados."""
    settings = settings or Settings()
    specs = load_bots()
    accounts = load_accounts()
    evaluations = latest_evaluations(db_path)
    trades, _diagnostics = load_closed_trades(
        db_path,
        tz=settings.timezone,
        bots={
            spec.id: {"account": spec.account, "profile": spec.profile}
            for spec in specs
        },
    )
    by_bot: dict[str, list] = {}
    for trade in trades:
        by_bot.setdefault(trade.bot, []).append(trade)
    criteria = load_criteria()
    max_p50 = float(criteria.get("max_slippage_bps_p50", 10.0))
    max_p95 = float(criteria.get("max_slippage_bps_p95", 25.0))
    backtest_bps = float(settings.execution.slippage_bps)

    rows = []
    for spec in specs:
        group = by_bot.get(spec.id, [])
        live = summarize(group, accounts) if group else None
        backtest = evaluations.get(spec.id)
        bt_status = str((backtest or {}).get("status") or "")
        bt_valid = bool(backtest and bt_status not in {"no_evaluable", ""})
        bt_sharpe = (
            float(backtest["sharpe"])
            if bt_valid and backtest.get("sharpe") is not None
            else None
        )
        bt_expectancy = (
            float(backtest["expectancy"])
            if bt_valid and backtest.get("expectancy") is not None
            else None
        )
        capital = float(live["capital"]) if live and live.get("capital") else None
        _, sharpe_low, sharpe_high = _bootstrap_sharpe(group, capital)
        _, exp_low, exp_high = _bootstrap_expectancy(group)
        live_sharpe = float(live["sharpe"]) if live and live.get("sharpe") is not None else None
        live_expectancy = (
            float(live["expectancy"])
            if live and live.get("expectancy") is not None
            else None
        )
        reasons: list[str] = []
        if len(group) < min_trades:
            edge_status = "sin datos"
            reasons.append(f"live N={len(group)} < mínimo {min_trades}")
        else:
            sharpe_status, sharpe_z = classify_metric(
                live_sharpe, bt_sharpe, sharpe_low, sharpe_high
            )
            exp_status, exp_z = classify_metric(
                live_expectancy, bt_expectancy, exp_low, exp_high
            )
            edge_status = _merge_status([sharpe_status, exp_status])
            reasons.append(
                f"Sharpe live {live_sharpe if live_sharpe is not None else 'sin datos'} "
                f"vs BT {bt_sharpe if bt_sharpe is not None else 'sin datos'} "
                f"(IC {sharpe_low if sharpe_low is not None else 'sin datos'}…"
                f"{sharpe_high if sharpe_high is not None else 'sin datos'}, z={sharpe_z})"
            )
            reasons.append(
                f"expectancy live {live_expectancy if live_expectancy is not None else 'sin datos'} "
                f"vs BT {bt_expectancy if bt_expectancy is not None else 'sin datos'}"
            )
        start_date = group[0].day if group else "1970-01-01"
        slippage = execution_metrics(db_path, bot=spec.id, start_date=start_date)
        slip_status, slip_reasons = classify_slippage(
            int(slippage.get("fills") or 0),
            slippage.get("slippage_p50_bps"),
            slippage.get("slippage_p95_bps"),
            backtest_bps=backtest_bps,
            max_p50_bps=max_p50,
            max_p95_bps=max_p95,
            min_fills=min_slippage_fills,
        )
        reasons.extend(slip_reasons)
        status = (
            "sin datos"
            if edge_status == "sin datos"
            else _merge_status([edge_status, slip_status])
        )
        rows.append(
            {
                "bot": spec.id,
                "account": spec.account,
                "profile": spec.profile,
                "enabled": spec.enabled,
                "backtest": {
                    "status": bt_status or "Sin datos",
                    "sharpe": bt_sharpe,
                    "expectancy": bt_expectancy,
                    "num_trades": (backtest or {}).get("num_trades"),
                    "win_rate": (backtest or {}).get("win_rate"),
                },
                "live": {
                    "n": len(group),
                    "days": len({trade.day for trade in group}),
                    "sharpe": live_sharpe,
                    "sharpe_ci95": [sharpe_low, sharpe_high],
                    "expectancy": live_expectancy,
                    "expectancy_ci95": [exp_low, exp_high],
                    "win_rate": live.get("win_rate") if live else None,
                    "net_pnl": live.get("net_pnl") if live else None,
                },
                "slippage": {
                    "fills": int(slippage.get("fills") or 0),
                    "p50_bps": slippage.get("slippage_p50_bps"),
                    "p95_bps": slippage.get("slippage_p95_bps"),
                    "backtest_bps": backtest_bps,
                },
                "edge_status": edge_status,
                "slippage_status": slip_status,
                "status": status,
                "reasons": reasons,
                "sample_ok": len(group) >= min_trades,
            }
        )
    rows.sort(key=lambda row: row["bot"])
    try:
        from .tca import attach_to_drift

        rows = attach_to_drift(rows, db_path)
    except Exception:
        pass
    counts = {"ok": 0, "vigilar": 0, "deriva": 0, "sin datos": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_trades": int(min_trades),
        "min_slippage_fills": int(min_slippage_fills),
        "bootstrap_paths": BOOTSTRAP_PATHS,
        "seed": SEED,
        "backtest_slippage_bps": backtest_bps,
        "summary": counts,
        "bots": rows,
    }


__all__ = [
    "MIN_SLIPPAGE_FILLS",
    "MIN_TRADES",
    "build_drift",
    "classify_metric",
    "classify_slippage",
]
