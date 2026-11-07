"""Investigación intradía forex/CFD con datos MT5 locales.

- Cachea velas M15/H1 ya corregidas a UTC por MT5Broker.rates.
- Modela spread por hora (si existe), slippage y comisión.
- Incluye tres estrategias acotadas y las pasa por DSR/PBO/WF/regímenes.
- No descarga datos de pago ni envía órdenes.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .indicators import atr, ema
from .profiles import get_profile
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo
from .research import deflated_sharpe
from .strategies.base import StrategyResult
from .validation import cscv_pbo, returns_matrix
from .walkforward import regime_gate, regime_report, walk_forward

INTRADAY_GRIDS = {
    "orb": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [8, 16]},
    "pullback": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "asian_rev": {"buffer_atr": [0.1, 0.3], "max_hold": [8, 16]},
}
DEFAULT_HORIZONS = (22, 44, 120)


def _bars_per_year(timeframe: str) -> float:
    if timeframe.upper() == "M15":
        return 252 * 96
    if timeframe.upper() == "H1":
        return 252 * 24
    return 252


def cache_file(cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol).upper()
    return Path(cache_dir) / "mt5" / f"{safe}_{timeframe.upper()}.parquet"


def save_bars(df: pd.DataFrame, cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    path = cache_file(cache_dir, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index.name = "ts"
    frame.to_parquet(path)
    return path


def load_bars(cache_dir: str | Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = cache_file(cache_dir, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"no existe caché MT5: {path}")
    frame = pd.read_parquet(path)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.sort_index()


def cache_metadata(df: pd.DataFrame, timeframe: str) -> dict:
    if df.empty:
        return {"rows": 0, "start": None, "end": None, "years": 0.0, "timeframe": timeframe}
    start = df.index[0]
    end = df.index[-1]
    days = max(0.0, (end - start).total_seconds() / 86400)
    return {
        "rows": int(len(df)),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": round(days / 365.25, 2),
        "timeframe": timeframe,
    }


def _spread_bps(df: pd.DataFrame, point: float) -> tuple[pd.Series, bool]:
    if "spread" not in df.columns:
        return pd.Series(3.0, index=df.index), False
    raw = pd.to_numeric(df["spread"], errors="coerce").fillna(0.0)
    close = pd.to_numeric(df["close"], errors="coerce")
    spread = (raw * point / close * 10_000).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    hourly = spread.groupby(spread.index.hour).median()
    mapped = pd.Series(
        [float(hourly.get(ts.hour, hourly.median())) for ts in spread.index],
        index=spread.index,
    )
    reliable = bool(len(hourly) >= 2 and float(spread.median()) > 0.0)
    return mapped, reliable


def backtest_intraday(
    df: pd.DataFrame,
    target: pd.Series,
    *,
    timeframe: str = "M15",
    commission_bps: float = 1.0,
    slippage_bps: float = 2.0,
    point: float = 0.0001,
) -> dict:
    """Retorno neto con costes por spread horario, slippage y comisión."""
    close = pd.to_numeric(df["close"], errors="coerce")
    pos = target.reindex(df.index).fillna(0.0).clip(-1.0, 1.0).shift(1).fillna(0.0)
    gross = close.pct_change().fillna(0.0) * pos
    turnover = pos.diff().abs().fillna(pos.abs())
    spread, reliable = _spread_bps(df, point)
    cost_bps = float(commission_bps) + float(slippage_bps) + spread
    net = gross - turnover * cost_bps / 10_000.0
    equity = (1.0 + net).cumprod()
    std = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    ann = _bars_per_year(timeframe)
    sharpe = float(net.mean() / std * np.sqrt(ann)) if std > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "returns": net,
        "equity": equity,
        "metrics": {
            "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
            "sharpe": sharpe,
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "num_trades": int((turnover > 0).sum()),
            "bars": int(len(net)),
        },
        "spread_bps_median": float(spread.median()) if len(spread) else 0.0,
        "spread_reliable": reliable,
    }


def _session_mask(index: pd.DatetimeIndex, start_hour: int, end_hour: int) -> pd.Series:
    hours = index.hour
    return pd.Series((hours >= start_hour) & (hours < end_hour), index=index)


def opening_range_breakout(
    df: pd.DataFrame,
    *,
    range_bars: int = 4,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
    start_hour: int = 7,
    end_hour: int = 16,
) -> StrategyResult:
    """Ruptura del rango de apertura de Londres/NY (UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    mask = _session_mask(df.index, start_hour, end_hour)
    for day in sorted({ts.date() for ts in df.index}):
        session = df[mask & (pd.Index(df.index.date) == day)]
        if len(session) < range_bars + 2:
            continue
        rng = session.iloc[:range_bars]
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        pos, hold = 0.0, 0
        for i in range(range_bars, len(session)):
            bar = session.iloc[i]
            if pos == 0.0:
                atr_value = float(atr_s.loc[bar.name]) if bar.name in atr_s.index else 0.0
                if bar["close"] > hi + buffer_atr * atr_value:
                    pos = 1.0
                elif bar["close"] < lo - buffer_atr * atr_value:
                    pos = -1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos = 0.0
                    hold = 0
            target.loc[bar.name] = pos
    return StrategyResult(
        "orb",
        target,
        {"range_bars": range_bars, "buffer_atr": buffer_atr, "max_hold": max_hold},
    )


def trend_pullback(
    df: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 100,
    pullback_atr: float = 0.25,
    max_hold: int = 8,
) -> StrategyResult:
    """Tendencia con retroceso a la media rápida."""
    close = df["close"]
    fast_ma, slow_ma, atr_s = ema(close, fast), ema(close, slow), atr(df)
    target = pd.Series(0.0, index=df.index)
    pos, hold = 0.0, 0
    for ts, row in df.iterrows():
        if pos == 0.0:
            atr_value = float(atr_s.loc[ts])
            if fast_ma.loc[ts] > slow_ma.loc[ts] and row["low"] <= fast_ma.loc[ts] - pullback_atr * atr_value:
                pos = 1.0
            elif fast_ma.loc[ts] < slow_ma.loc[ts] and row["high"] >= fast_ma.loc[ts] + pullback_atr * atr_value:
                pos = -1.0
        else:
            hold += 1
            if hold >= max_hold or (pos > 0 and fast_ma.loc[ts] < slow_ma.loc[ts]) or (pos < 0 and fast_ma.loc[ts] > slow_ma.loc[ts]):
                pos, hold = 0.0, 0
        target.loc[ts] = pos
    return StrategyResult(
        "pullback",
        target,
        {"fast": fast, "slow": slow, "pullback_atr": pullback_atr, "max_hold": max_hold},
    )


def asian_range_reversal(
    df: pd.DataFrame,
    *,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
) -> StrategyResult:
    """Reversión en el rango asiático (00:00-07:00 UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    for day in sorted({ts.date() for ts in df.index}):
        day_mask = pd.Index(df.index.date) == day
        asian = df[day_mask & (pd.Index(df.index.hour) < 7)]
        rest = df[day_mask & (pd.Index(df.index.hour) >= 7)]
        if len(asian) < 4 or rest.empty:
            continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        pos, hold = 0.0, 0
        for ts, row in rest.iterrows():
            if pos == 0.0:
                atr_value = float(atr_s.loc[ts])
                if row["close"] > hi + buffer_atr * atr_value:
                    pos = -1.0
                elif row["close"] < lo - buffer_atr * atr_value:
                    pos = 1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos, hold = 0.0, 0
            target.loc[ts] = pos
    return StrategyResult(
        "asian_rev",
        target,
        {"buffer_atr": buffer_atr, "max_hold": max_hold},
    )


STRATEGIES = {
    "orb": opening_range_breakout,
    "pullback": trend_pullback,
    "asian_rev": asian_range_reversal,
}


def _combos(grid: dict[str, list]) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _aligned(series: dict[str, pd.Series]) -> tuple[np.ndarray, list[str]] | None:
    if len(series) < 2:
        return None
    frame = pd.concat(series, axis=1, join="inner").dropna()
    if len(frame) < 80:
        return None
    return returns_matrix({k: frame[k].to_numpy(dtype=float) for k in frame.columns})


def run_intraday(
    df: pd.DataFrame,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    paths: int = 500,
    point: float = 0.0001,
    commission_bps: float = 1.0,
    slippage_bps: float = 2.0,
) -> dict:
    """Valida las estrategias intradía con los controles existentes."""
    profile = get_profile("intraday_fx")
    if profile is None:
        raise RuntimeError("falta perfil intraday_fx")
    outcomes = []
    returns_by_id: dict[str, pd.Series] = {}
    for name, grid in INTRADAY_GRIDS.items():
        for params in _combos(grid):
            result = STRATEGIES[name](df, **params)
            bt = backtest_intraday(
                df,
                result.target,
                timeframe=timeframe,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
                point=point,
            )
            key = f"{name}|{json.dumps(params, sort_keys=True)}"
            returns_by_id[key] = bt["returns"]
            outcomes.append(
                {
                    "strategy": name,
                    "params": params,
                    "metrics": bt["metrics"],
                    "spread_bps_median": bt["spread_bps_median"],
                    "spread_reliable": bt["spread_reliable"],
                }
            )

    sr_values = [row["metrics"]["sharpe"] for row in outcomes]
    sr_std = float(np.std(sr_values, ddof=1)) if len(sr_values) > 1 else 0.0
    for row in outcomes:
        row["dsr"] = deflated_sharpe(
            row["metrics"]["sharpe"],
            int(row["metrics"]["bars"]),
            0.0,
            3.0,
            sr_std,
            len(outcomes),
        )

    aligned = _aligned(returns_by_id)
    pbo = None
    if aligned is not None:
        matrix, _ = aligned
        try:
            pbo = cscv_pbo(matrix, n_slices=16, max_combinations=2_000).to_dict()
        except ValueError:
            pbo = None
    train_len = min(2_016, max(126, len(df) // 4))
    test_len = min(504, max(21, len(df) // 12))
    wf = None
    if aligned is not None:
        try:
            wf = walk_forward(aligned[0], train_len=train_len, test_len=test_len)
        except ValueError:
            wf = None

    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        report = regime_report(returns_by_id[key])
        gate = regime_gate(report)
        row["regime_report"] = report.to_dict()
        row["regime_gate"] = gate.to_dict()
        row["wf_verdict"] = wf.verdict() if wf else "sin datos"
        row["pbo"] = pbo["pbo"] if pbo else None
        row["passed"] = bool(
            row["metrics"]["num_trades"] >= profile.validation.min_trades
            and row["dsr"] is not None
            and row["dsr"] >= profile.validation.min_dsr
            and pbo is not None
            and pbo["pbo"] <= profile.validation.max_pbo
            and wf is not None
            and wf.verdict() == "ok"
            and gate.passed
            and row["spread_reliable"]
        )

    rules = [from_yaml("ftmo", "challenge", 100_000), from_yaml("topstep", "challenge", 50_000)]
    mc = []
    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        for rule in rules:
            for horizon in DEFAULT_HORIZONS:
                sim = monte_carlo(
                    rule,
                    returns_by_id[key].to_numpy(),
                    n_paths=max(50, paths),
                    horizon=horizon,
                    block_size=5,
                    seed=42,
                )
                mc.append(
                    {
                        "firm": rule.firm,
                        "strategy": row["strategy"],
                        "params": row["params"],
                        "horizon": horizon,
                        "pass_rate": sim["pass_rate"],
                        "breach_rate": sim["breach_rate"],
                    }
                )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": cache_metadata(df, timeframe),
        "profile": profile.id,
        "spread_reliable": all(row["spread_reliable"] for row in outcomes),
        "pbo": pbo,
        "walk_forward": wf.to_dict() if wf else None,
        "walk_forward_verdict": wf.verdict() if wf else "sin datos",
        "n_trials": len(outcomes),
        "passed": sum(1 for row in outcomes if row["passed"]),
        "outcomes": outcomes,
        "monte_carlo": mc,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Investigación intradía forex/CFD",
        "",
        f"- Símbolo: {report['symbol']} · {report['timeframe']}",
        f"- Barras: {report['bars']['rows']:,} · {report['bars']['start']} → {report['bars']['end']} · {report['bars']['years']} años",
        f"- Perfil: {report['profile']} · DSR n_trials={report['n_trials']}",
        f"- Spread realista: {'sí' if report['spread_reliable'] else 'NO — resultados no confiables'}",
        f"- PBO: {report['pbo']['pbo']:.1%}" if report.get("pbo") else "- PBO: sin datos",
        f"- Walk-forward: {report['walk_forward_verdict']}",
        f"- Pasan: {report['passed']}/{len(report['outcomes'])}",
        "",
        "> Solo informativo; no activa bots ni cambia criterios. "
        "El riesgo intradía real puede ser mayor que el modelado.",
        "",
        "## Estrategias",
        "",
        "| Estrategia | Parámetros | Trades | Sharpe | MaxDD | DSR | WF | Régimen | Spread | Pasa |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["outcomes"]:
        lines.append(
            f"| {row['strategy']} | `{row['params']}` | {row['metrics']['num_trades']} | "
            f"{row['metrics']['sharpe']:.2f} | {row['metrics']['max_drawdown']:.1%} | "
            f"{(row['dsr'] or 0):.1%} | {row['wf_verdict']} | "
            f"{'ok' if row['regime_gate']['passed'] else 'no'} | "
            f"{'sí' if row['spread_reliable'] else 'no'} | "
            f"{'sí' if row['passed'] else 'no'} |"
        )
    lines += [
        "",
        "## Monte Carlo 22/44/120d",
        "",
        "| Firma | Estrategia | Horizonte | Pasa | Revienta |",
        "|---|---|---|---|---|",
    ]
    for row in report["monte_carlo"][:40]:
        lines.append(
            f"| {row['firm']} | {row['strategy']} | {row['horizon']}d | "
            f"{row['pass_rate']:.1%} | {row['breach_rate']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def write(report: dict, out_dir: str | Path = ROOT / "reports" / "research") -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "intraday.json"
    md_path = out / "intraday.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


__all__ = [
    "DEFAULT_HORIZONS",
    "INTRADAY_GRIDS",
    "STRATEGIES",
    "asian_range_reversal",
    "backtest_intraday",
    "cache_file",
    "cache_metadata",
    "load_bars",
    "opening_range_breakout",
    "render_markdown",
    "run_intraday",
    "save_bars",
    "trend_pullback",
]
