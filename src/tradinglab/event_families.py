"""Familia intradía ``caja_ny`` con ejecución por eventos.

Rango de apertura NY 09:15–09:35 (M5), ruptura, entrada limitada en el borde
roto, stop parametrizado (borde opuesto o N×ATR) y salida forzosa a las 15:45
NY. Solo investigación: no activa bots ni envía órdenes. El holdout sellado no
se toca.
"""
from __future__ import annotations

import itertools
import json
import uuid
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .broker_costs import broker_spread_summary
from .config import DEFAULT_DB, ROOT
from .db import connect
from .indicators import atr
from .intraday import (
    FAMILY_HYPOTHESES,
    INTRADAY_GRIDS,
    break_even_cost_bps,
    load_bars,
    run_event_backtest,
)
from .learning import count_tests
from .profiles import get_profile
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo
from .research import deflated_sharpe
from .trials import record_trial
from .validation import cscv_pbo, returns_matrix
from .walkforward import regime_gate, regime_report, walk_forward

NY = ZoneInfo("America/New_York")
REPORT_DIR = ROOT / "reports" / "research"
DEFAULT_RANGE_START = "09:15"
DEFAULT_RANGE_END = "09:35"
DEFAULT_FORCE_EXIT = "15:45"
DEFAULT_SPREAD_BPS = 0.7203598252728787
DEFAULT_SLIPPAGE_BPS = 2.0
ATR_WINDOW = 14


def _combos(grid: dict[str, list]) -> list[dict]:
    keys = list(grid)
    return [
        dict(zip(keys, values))
        for values in itertools.product(*(grid[key] for key in keys))
    ]


def _ny_offset(day: date) -> float:
    stamp = pd.Timestamp.combine(day, time(12, 0)).tz_localize(NY)
    return float(stamp.utcoffset().total_seconds() / 3600.0)


def _parse_time(value: object, default: str) -> time:
    text = str(value if value is not None else default)
    try:
        return time.fromisoformat(text)
    except ValueError:
        return time.fromisoformat(default)


def _stop_for(
    side: str,
    level: float,
    range_high: float,
    range_low: float,
    rule: str,
    atr_value: float | None,
) -> float | None:
    if rule == "range":
        return range_low if side == "buy" else range_high
    if not rule.startswith("atr_"):
        return None
    try:
        multiple = float(rule.split("_", 1)[1])
    except (IndexError, ValueError):
        return None
    if atr_value is None or not np.isfinite(atr_value) or atr_value <= 0:
        return None
    stop = level - multiple * atr_value if side == "buy" else level + multiple * atr_value
    if side == "buy" and stop >= level:
        return None
    if side == "sell" and stop <= level:
        return None
    return float(stop)


def _order_for_day(
    day_bars: pd.DataFrame,
    params: dict,
    atr_series: pd.Series,
) -> dict | None:
    """Construye la orden limitada del día o None si no hay setup."""
    if day_bars.empty:
        return None
    ny_index = day_bars.index.tz_convert(NY)
    ny_times = ny_index.time
    range_start = _parse_time(params.get("range_start"), DEFAULT_RANGE_START)
    range_end = _parse_time(params.get("range_end"), DEFAULT_RANGE_END)
    force_time = _parse_time(params.get("force_exit"), DEFAULT_FORCE_EXIT)
    range_mask = (ny_times >= range_start) & (ny_times < range_end)
    range_bars = day_bars[range_mask]
    if len(range_bars) != 4:
        return None
    range_high = float(range_bars["high"].max())
    range_low = float(range_bars["low"].min())
    if range_high <= range_low:
        return None
    post_mask = (ny_times >= range_end) & (ny_times < force_time)
    post = day_bars[post_mask]
    if post.empty:
        return None
    side: str | None = None
    level: float | None = None
    breakout_ts = None
    for ts, bar in post.iterrows():
        high = float(bar["high"])
        low = float(bar["low"])
        above = high > range_high
        below = low < range_low
        if above and below:
            return None
        if above:
            side, level, breakout_ts = "buy", range_high, ts
            break
        if below:
            side, level, breakout_ts = "sell", range_low, ts
            break
    if side is None or level is None or breakout_ts is None:
        return None
    atr_value = None
    if str(params.get("stop_rule", "range")).startswith("atr_"):
        prior = atr_series.loc[:breakout_ts].dropna()
        if prior.empty:
            return None
        atr_value = float(prior.iloc[-1])
    stop = _stop_for(
        side,
        level,
        range_high,
        range_low,
        str(params.get("stop_rule", "range")),
        atr_value,
    )
    if stop is None:
        return None
    force_local = pd.Timestamp.combine(ny_index[0].date(), force_time).tz_localize(NY)
    force_utc = force_local.tz_convert("UTC")
    expires = force_utc - pd.Timedelta(seconds=1)
    if expires <= breakout_ts:
        return None
    return {
        "side": side,
        "type": "limit",
        "level": level,
        "stop": stop,
        "target": None,
        "created_at": breakout_ts,
        "expires_at": expires,
    }


def _sharpe(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < 2:
        return 0.0
    std = float(values.std(ddof=1))
    if not np.isfinite(std) or std <= 0:
        return 0.0
    return float(values.mean() / std * np.sqrt(252.0))


def _trade_result(trade: dict) -> tuple[float, float, float]:
    entry = float(trade["entry_price"])
    exit_ = float(trade["exit_price"])
    sign = 1.0 if trade["side"] == "buy" else -1.0
    gross = sign * (exit_ / entry - 1.0)
    entry_cost = sum(float(value) for value in trade["entry_costs"].values())
    exit_cost = sum(float(value) for value in trade["exit_costs"].values())
    total_cost = entry_cost + exit_cost
    return gross, gross - total_cost / 10_000.0, total_cost


def _variant_returns(
    bars: pd.DataFrame,
    params: dict,
    atr_series: pd.Series,
    *,
    spread_bps: float,
    commission_bps: float,
    slippage_bps: float,
) -> tuple[pd.Series, pd.Series, pd.Series, list[dict]]:
    ny_dates = bars.index.tz_convert(NY).date
    daily_dates = sorted(set(ny_dates))
    gross = pd.Series(0.0, index=pd.DatetimeIndex(daily_dates), dtype=float)
    net = gross.copy()
    turnover = gross.copy()
    trades: list[dict] = []
    force_time = _parse_time(params.get("force_exit"), DEFAULT_FORCE_EXIT)
    for day in daily_dates:
        day_bars = bars[ny_dates == day]
        order = _order_for_day(day_bars, params, atr_series)
        if order is None:
            continue
        result = run_event_backtest(
            day_bars,
            [order],
            point=0.01,
            commission_bps=commission_bps,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            fill_pessimism_points=0,
            max_trades_per_day=int(params.get("max_trades_per_day", 1)),
            force_exit_time=force_time,
            session_offset_hours=_ny_offset(day),
        )
        if not result["trades"]:
            continue
        trade = result["trades"][0]
        gross_value, net_value, total_cost = _trade_result(trade)
        stamp = pd.Timestamp(day)
        gross.loc[stamp] = gross_value
        net.loc[stamp] = net_value
        turnover.loc[stamp] = 1.0
        trades.append(
            {
                "date": str(day),
                "side": trade["side"],
                "entry_time": str(trade["entry_time"]),
                "exit_time": str(trade["exit_time"]),
                "entry_price": trade["entry_price"],
                "exit_price": trade["exit_price"],
                "exit_reason": trade["exit_reason"],
                "gross_return": gross_value,
                "net_return": net_value,
                "cost_bps": total_cost,
            }
        )
    return gross, net, turnover, trades


def _strategy_trials_count(db_path: str | Path) -> int:
    with connect(db_path) as con:
        return int(con.execute("SELECT COUNT(*) FROM strategy_trials").fetchone()[0])


def _write_report(report: dict, out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "caja_ny.md"
    json_path = out_dir / "caja_ny.json"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    lines = [
        "# Caja NY · ejecución por eventos",
        "",
        f"- Símbolo: {report['symbol']} · {report['timeframe']}",
        f"- Datos: {report['data']['rows']:,} barras · {report['data']['start']} → {report['data']['end']}",
        f"- Ventana de rango: {report['window']['range_start']}–{report['window']['range_end']} NY; "
        f"salida forzosa {report['window']['force_exit']} NY.",
        f"- Stop: {', '.join(report['window']['stop_rules'])}.",
        "- Modo de ejecución: eventos; entrada limitada al borde roto, sin spread; "
        "stop/forzada con spread+slippage; comisión por lado.",
        f"- Spread bróker p75: {report['costs']['spread_bps']:.3f} bps; "
        f"comisión: {report['costs']['commission_bps']:.3f} bps; "
        f"slippage: {report['costs']['slippage_bps']:.1f} bps.",
        f"- Contador DSR: {report['counters']['before']} → {report['counters']['after']} "
        f"(trials {report['counters']['trials_before']} → {report['counters']['trials_after']}).",
        f"- Variantes registradas: {report['variants_count']}. Holdout sellado: no se abrió.",
        "- **enabled: false**; no se activa ningún bot ni se envían órdenes.",
        "",
        "## Variantes",
        "",
        "| Stop | Trades | Sharpe bruto | Sharpe neto | Coste bps/op | Equilibrio bps | PBO | WF | DSR | Pasa |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for row in report["variants"]:
        lines.append(
            f"| {row['params']['stop_rule']} | {row['trades']} | "
            f"{row['gross_sharpe']:.2f} | {row['net_sharpe']:.2f} | "
            f"{row['effective_cost_bps']:.2f} | {row['breakeven_bps'] if row['breakeven_bps'] is not None else 'sin cruce'} | "
            f"{row['pbo'] if row['pbo'] is not None else 'sin datos'} | "
            f"{row['wf_verdict']} | {row['dsr']:.2f} | "
            f"{'sí' if row['passed'] else 'no'} |"
        )
    lines += [
        "",
        "## Veredicto",
        "",
        f"- Mejor variante: {report['best']['params']['stop_rule']} "
        f"(Sharpe neto {report['best']['net_sharpe']:.2f}, bruto {report['best']['gross_sharpe']:.2f}).",
        f"- PBO CSCV: {report['pbo']['pbo'] if report['pbo'] else 'sin datos'}",
        f"- Walk-forward: {report['wf_verdict']}",
        f"- **Veredicto: {'PASA' if report['passed'] else 'NO PASA'}**",
        f"- Motivos: {'; '.join(report['reasons']) if report['reasons'] else 'ninguno'}",
        "",
        "## Monte Carlo",
        "",
        "| Firma | Horizonte | Pasa | Revienta |",
        "|---|---:|---:|---:|",
    ]
    for row in report["monte_carlo"]:
        lines.append(
            f"| {row['firm']} | {row['horizon']}d | "
            f"{row['pass_rate']:.1%} | {row['breach_rate']:.1%} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"md": str(md_path), "json": str(json_path)}


def run_caja_ny(
    *,
    symbol: str = "US100.cash",
    cache_dir: str | Path = ROOT / "data" / "cache",
    db_path: str | Path = DEFAULT_DB,
    out_dir: str | Path | None = None,
    mc_paths: int = 500,
) -> dict:
    """Ejecuta la familia caja_ny, registra trials y escribe el informe."""
    profile = get_profile("intraday_fx")
    if profile is None:
        raise RuntimeError("falta perfil intraday_fx")
    bars = load_bars(cache_dir, symbol, "M5")
    if bars.empty:
        raise RuntimeError(f"sin barras M5 para {symbol}")
    broker = broker_spread_summary(symbol, db_path=db_path)
    spread_bps = broker.get("p75_bps")
    if spread_bps is None:
        raise RuntimeError(f"sin spread bróker p75 para {symbol}")
    spread_bps = float(spread_bps)
    atr_series = atr(bars, window=ATR_WINDOW)
    variants = _combos(INTRADAY_GRIDS["caja_ny"])
    before_count = count_tests(db_path)
    before_trials = _strategy_trials_count(db_path)
    n_trials_dsr = len(variants) + before_count
    results = []
    daily_net: dict[str, pd.Series] = {}
    daily_gross: dict[str, pd.Series] = {}
    trade_data: dict[str, list[dict]] = {}
    for params in variants:
        gross, net, turnover, trades = _variant_returns(
            bars,
            params,
            atr_series,
            spread_bps=spread_bps,
            commission_bps=0.0,
            slippage_bps=2.0,
        )
        label = str(params["stop_rule"])
        daily_gross[label] = gross
        daily_net[label] = net
        trade_data[label] = trades
        effective_cost = (
            float(np.mean([trade["cost_bps"] for trade in trades]))
            if trades
            else 0.0
        )
        breakeven = break_even_cost_bps(gross, turnover, "D1") if trades else None
        results.append(
            {
                "params": params,
                "trades": len(trades),
                "gross_sharpe": _sharpe(gross),
                "net_sharpe": _sharpe(net),
                "effective_cost_bps": effective_cost,
                "breakeven_bps": breakeven,
                "trades_detail": trades,
            }
        )

    matrix, labels = returns_matrix(
        {label: series.to_numpy() for label, series in daily_net.items()}
    )
    pbo = None
    try:
        pbo = cscv_pbo(matrix, n_slices=16, max_combinations=2_000).to_dict()
    except ValueError:
        pbo = None
    wf = None
    try:
        wf = walk_forward(matrix, train_len=63, test_len=21)
    except ValueError:
        wf = None
    wf_verdict = wf.verdict() if wf is not None else "sin datos"
    net_sharpes = [row["net_sharpe"] for row in results]
    sr_std = float(np.std(net_sharpes, ddof=1)) if len(net_sharpes) > 1 else 0.0
    for row in results:
        row["pbo"] = None if pbo is None else float(pbo["pbo"])
        row["wf_verdict"] = wf_verdict
        row["dsr"] = float(
            deflated_sharpe(
                row["net_sharpe"],
                len(matrix),
                0.0,
                3.0,
                sr_std,
                n_trials_dsr,
            )
        )
        net = daily_net[str(row["params"]["stop_rule"])]
        regime = regime_report(net)
        gate = regime_gate(regime)
        row["regime"] = regime.to_dict()
        row["regime_passed"] = bool(gate.passed)
        reasons = []
        if row["trades"] < profile.validation.min_trades:
            reasons.append(
                f"trades {row['trades']} < {profile.validation.min_trades}"
            )
        if row["dsr"] < profile.validation.min_dsr:
            reasons.append(
                f"DSR {row['dsr']:.2f} < {profile.validation.min_dsr:.2f}"
            )
        if row["pbo"] is None:
            reasons.append("PBO sin datos")
        elif row["pbo"] > profile.validation.max_pbo:
            reasons.append(
                f"PBO {row['pbo']:.2f} > {profile.validation.max_pbo:.2f}"
            )
        if wf is None or wf_verdict != "ok":
            reasons.append(f"WF {wf_verdict}")
        if not gate.passed:
            reasons.append("régimen no aprobado")
        row["passed"] = not reasons
        row["reasons"] = reasons

    best = max(results, key=lambda row: row["net_sharpe"])
    best_net = daily_net[str(best["params"]["stop_rule"])]
    rules = [
        from_yaml("ftmo", "challenge", 100_000),
        from_yaml("topstep", "challenge", 50_000),
    ]
    mc = []
    for rule in rules:
        for horizon in (22, 44, 120):
            sim = monte_carlo(
                rule,
                best_net.to_numpy(),
                n_paths=max(50, int(mc_paths)),
                horizon=horizon,
                block_size=5,
                seed=42,
            )
            mc.append(
                {
                    "firm": rule.firm,
                    "horizon": horizon,
                    "pass_rate": sim["pass_rate"],
                    "breach_rate": sim["breach_rate"],
                }
            )

    run_id = uuid.uuid4().hex[:12]
    for row in results:
        record_trial(
            db_path,
            family="caja_ny",
            hypothesis=FAMILY_HYPOTHESES["caja_ny"],
            symbol=symbol,
            params=row["params"],
            window_start=str(bars.index[0].date()),
            window_end=str(bars.index[-1].date()),
            result={
                "trades": row["trades"],
                "gross_sharpe": row["gross_sharpe"],
                "net_sharpe": row["net_sharpe"],
                "effective_cost_bps": row["effective_cost_bps"],
                "breakeven_bps": row["breakeven_bps"],
                "pbo": row["pbo"],
                "wf_verdict": row["wf_verdict"],
                "dsr": row["dsr"],
                "regime_passed": row["regime_passed"],
                "passed": row["passed"],
            },
            outcome="passed" if row["passed"] else "failed",
            reason="; ".join(row["reasons"]),
            source="sweep",
            run_id=run_id,
        )
    after_count = count_tests(db_path)
    after_trials = _strategy_trials_count(db_path)
    report = {
        "family": "caja_ny",
        "symbol": symbol,
        "timeframe": "M5",
        "data": {
            "rows": int(len(bars)),
            "start": str(bars.index[0]),
            "end": str(bars.index[-1]),
        },
        "window": {
            "range_start": DEFAULT_RANGE_START,
            "range_end": DEFAULT_RANGE_END,
            "force_exit": DEFAULT_FORCE_EXIT,
            "stop_rules": [str(item["stop_rule"]) for item in variants],
        },
        "costs": {
            "spread_bps": spread_bps,
            "commission_bps": 0.0,
            "slippage_bps": 2.0,
            "source": broker.get("source"),
        },
        "counters": {
            "before": before_count,
            "after": after_count,
            "trials_before": before_trials,
            "trials_after": after_trials,
        },
        "variants_count": len(variants),
        "variants": results,
        "best": best,
        "pbo": pbo,
        "wf": wf.to_dict() if wf is not None else None,
        "wf_verdict": wf_verdict,
        "monte_carlo": mc,
        "passed": all(row["passed"] for row in results),
        "reasons": sorted(
            {
                reason
                for row in results
                for reason in row["reasons"]
            }
        ),
        "run_id": run_id,
        "enabled": False,
        "holdout_opened": False,
    }
    out = Path(out_dir) if out_dir else REPORT_DIR / "intraday_US100"
    files = _write_report(report, out)
    report["files"] = files
    return report


__all__ = ["run_caja_ny"]
