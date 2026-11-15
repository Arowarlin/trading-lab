"""Integración del EA US100_FTMO1: setfile, backtest y filtros del laboratorio.

El motor es la réplica Python del EA (``ea_us100_engine``). Este módulo no
envía órdenes: lee velas M5 del terminal, ejecuta el motor y pasa el resultado
por DSR, PBO, walk-forward, regímenes, Monte Carlo y sensibilidad a costes.
"""

from __future__ import annotations

import itertools
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import ea_us100_engine as engine
from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .ea_registry import ExternalEA
from .learning import count_tests
from .profiles import get_profile
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo
from .stats import dsr_local_global, period_sharpe
from .trials import record_trial
from .validation import cscv_pbo
from .walkforward import regime_gate, regime_report, walk_forward

CACHE = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
DEFAULT_COUNT = 400_000
RISK_PCT = 0.35
GRID = {
    "min_score": [55],
    "rr": [3.0, 3.5],
    "gap_min": [0.5, 0.7],
    "max_consec": [1, 2],
}
YEARS = (2021, 2022, 2023, 2024, 2025, 2026)


@dataclass(frozen=True)
class EAReport:
    baseline: dict
    stats: dict
    rows: list[dict]
    filters: dict
    dsr: float | None
    pbo: float | None
    wf: dict
    regime: dict
    mc: dict
    costs: dict
    params: dict


def load_setfile(path: str | Path) -> dict:
    values: dict = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if re.fullmatch(r"-?\d+", value):
            values[key] = int(value)
        elif re.fullmatch(r"-?\d+\.\d+", value):
            values[key] = float(value)
        elif value.lower() in {"true", "false"}:
            values[key] = value.lower() == "true"
        else:
            values[key] = value
    return values


def _f(values: dict, key: str, default: float) -> float:
    try:
        return float(values.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _i(values: dict, key: str, default: int) -> int:
    try:
        return int(values.get(key, default))
    except (TypeError, ValueError):
        return int(default)


def _b(values: dict, key: str, default: bool) -> bool:
    value = values.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def params_from_set(values: dict) -> dict:
    """Traduce los inputs del setfile a los parámetros del motor."""
    weights = (
        _f(values, "InpWSweep", 25),
        _f(values, "InpWFvg", 20),
        _f(values, "InpWVwap", 20),
        _f(values, "InpWStruct", 15),
        _f(values, "InpWRvol", 10),
        _f(values, "InpWOr", 10),
    )
    params = dict(engine.DEF)
    params.update(
        {
            "ny_offset_h": 0,
            "or_end": 930 + _i(values, "InpORMinutes", 15),
            "trade_start": _i(values, "InpTradeStart", 945),
            "trade_end": _i(values, "InpTradeEnd", 1100),
            "flat_at": _i(values, "InpFlatAt", 1545),
            "mode": "agg" if _b(values, "InpAggressive", True) else "cons",
            "min_score": _i(values, "InpMinScore", 55),
            "allow_long": _b(values, "InpAllowLong", True),
            "allow_short": _b(values, "InpAllowShort", True),
            "w": weights,
            "use_pd": _b(values, "InpUsePD", True),
            "use_on": _b(values, "InpUseON", True),
            "use_pm": _b(values, "InpUsePM", True),
            "use_or": _b(values, "InpUseOR", True),
            "sweep_cool": _i(values, "InpSweepCool", 10),
            "sweep_window": _i(values, "InpSweepWindow", 12),
            "fvg_min_atr": _f(values, "InpFvgMinAtr", 0.15),
            "fvg_prox_atr": _f(values, "InpFvgProxAtr", 1.0),
            "fvg_ext": _i(values, "InpFvgExt", 40),
            "fvg_max": 20,
            "htf_min": 15,
            "vwap_ext_sd": _f(values, "InpVwapExtSd", 2.0),
            "rvol_len": 20,
            "rvol_thr": _f(values, "InpRvolThr", 1.5),
            "rvol_low": _f(values, "InpRvolLow", 0.7),
            "piv_l": _i(values, "InpPivL", 5),
            "piv_r": _i(values, "InpPivR", 5),
            "sl_mode": "atr" if _i(values, "InpSlType", 0) == 0 else "struct",
            "sl_atr": _f(values, "InpSlAtr", 1.5),
            "sl_buf": _f(values, "InpSlBufAtr", 0.1),
            "max_sl_atr": _f(values, "InpSlMaxAtr", 3.0),
            "min_sl": _f(values, "InpMinSlPts", 2.0),
            "rr": _f(values, "InpRR", 3.5),
            "be": _b(values, "InpBE", False),
            "be_r": _f(values, "InpBER", 1.0),
            "be_off": _f(values, "InpBEOffPts", 0.5),
            "trail": _b(values, "InpTrail", False),
            "trail_atr": _f(values, "InpTrailAtr", 2.0),
            "max_trades": _i(values, "InpMaxTrades", 3),
            "daily_loss_r": 999.0,
            "max_consec": _i(values, "InpMaxConsecLoss", 1),
            "regime": "sma" if _b(values, "InpUseRegime", True) else None,
            "reg_len": _i(values, "InpRegimeLen", 20),
            "gap_min": _f(values, "InpGapMin", 0.7)
            if _b(values, "InpUseGap", True)
            else 0.0,
            "gap_len": 20,
            "cooldown": _i(values, "InpCooldown", 5),
            "max_spread": _f(values, "InpMaxSpreadPts", 300) * 0.01,
            "slip": 0.5,
        }
    )
    return params


def load_bars(
    settings: Settings | None = None,
    *,
    symbol: str = "US100.cash",
    count: int = DEFAULT_COUNT,
    refresh: bool = False,
) -> pd.DataFrame:
    if not refresh and CACHE.exists():
        age = datetime.now(timezone.utc).timestamp() - CACHE.stat().st_mtime
        if age < 12 * 3600:
            frame = pd.read_parquet(CACHE)
            frame.index = pd.DatetimeIndex(frame.index)
            return frame
    from .execution import get_mt5_broker

    cfg = settings or get_settings()
    broker = get_mt5_broker(cfg, dry_run=True)
    broker.connect()
    try:
        frame = broker.rates(symbol, "M5", count)
    finally:
        broker.shutdown()
    frame = frame.rename(columns={"volume": "tickvol"})
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("America/New_York").tz_localize(None)
    frame = frame.sort_index()
    for column in ("tickvol", "spread"):
        if column not in frame.columns:
            frame[column] = 0.0
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(CACHE)
    return frame


def _stats(trades: pd.DataFrame) -> dict:
    if trades is None or len(trades) == 0:
        return {"n": 0, "win": 0.0, "pf": 0.0, "expR": 0.0, "totR": 0.0, "maxDD_R": 0.0}
    raw = engine.stats(trades)
    return {key: float(value) if isinstance(value, (int, float, np.floating)) else value for key, value in raw.items()}


def _daily_r(trades: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    if trades is None or len(trades) == 0:
        return pd.Series(0.0, index=days)
    stamp = pd.to_datetime(trades.t).dt.normalize()
    return trades.assign(day=stamp).groupby("day").r.sum().reindex(days).fillna(0.0)


def _sharpe(series: pd.Series) -> float:
    std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    return float(series.mean() / std * math.sqrt(252)) if std > 0 else 0.0


def _run_variant(df: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, dict]:
    trades = engine.run(df, params)
    return trades, _stats(trades)


def _grid_rows(df: pd.DataFrame, values: dict) -> tuple[list[dict], pd.DataFrame]:
    baseline = params_from_set(values)
    keys = list(GRID)
    combos = [
        dict(zip(keys, combo))
        for combo in itertools.product(*(GRID[key] for key in keys))
    ]
    rth = df.between_time("09:30", "15:59")
    days = pd.DatetimeIndex(sorted(set(rth.index.normalize())))
    rows: list[dict] = []
    series: dict[int, pd.Series] = {}
    for index, patch in enumerate(combos):
        params = dict(baseline)
        params.update(patch)
        trades, stats = _run_variant(df, params)
        series[index] = _daily_r(trades, days) * (
            RISK_PCT / 100.0
        )
        rows.append({"index": index, **patch, **stats})
    matrix = pd.DataFrame(series, index=days).fillna(0.0)
    return rows, matrix


def _dynamic_risk(daily_r: pd.Series, values: dict) -> dict:
    """Simula la escalera v3 sobre el capital inicial, sin interés compuesto."""
    base = _f(values, "InpDynBase", 1.0)
    dd1, dd2, dd3 = (
        _f(values, "InpDynDD1", 2.0),
        _f(values, "InpDynDD2", 4.0),
        _f(values, "InpDynDD3", 6.0),
    )
    r1, r2, r3 = (
        _f(values, "InpDynR1", 0.6),
        _f(values, "InpDynR2", 0.35),
        _f(values, "InpDynR3", 0.25),
    )
    max_dd_pct = _f(values, "InpMaxDDPct", 8.0)
    daily_stop = _f(values, "InpDailyLossPct", 1.5)
    initial = 100_000.0
    equity = initial
    peak = initial
    previous = initial
    killed = False
    returns: list[float] = []
    max_dd = 0.0
    for value in daily_r:
        dd = max(0.0, (initial - equity) / initial * 100.0)
        risk = base if dd < dd1 else r1 if dd < dd2 else r2 if dd < dd3 else r3
        pnl = float(value) * initial * risk / 100.0
        pnl = max(pnl, -daily_stop / 100.0 * initial)
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)
        returns.append(pnl / previous if previous else 0.0)
        previous = equity
        if equity <= initial * (1.0 - max_dd_pct / 100.0):
            killed = True
            break
    mc = {}
    try:
        rules = from_yaml("ftmo", "challenge", 100_000)
        payload = monte_carlo(
            rules, returns, n_paths=5_000, horizon=21, seed=42
        )
        mc = {
            key: payload[key]
            for key in (
                "pass_rate",
                "breach_rate",
                "median_max_drawdown",
                "p5_max_drawdown",
                "worst_max_drawdown",
            )
        }
    except Exception as exc:
        mc = {"error": str(exc)[:200]}
    return {
        "return": equity / initial - 1.0,
        "equity": equity,
        "max_drawdown": max_dd,
        "killed": killed,
        "risk_steps": [base, r1, r2, r3],
        "monte_carlo": mc,
    }


def _baseline_index(rows: list[dict]) -> int:
    want = {"min_score": 55, "rr": 3.5, "gap_min": 0.7, "max_consec": 1}
    for row in rows:
        if all(row.get(key) == value for key, value in want.items()):
            return int(row["index"])
    return 0


def _record_trials(
    db_path: str | Path,
    rows: list[dict],
    *,
    baseline_index: int,
    run_id: str,
    symbol: str,
) -> None:
    for row in rows:
        is_base = int(row["index"]) == baseline_index
        try:
            record_trial(
                db_path,
                family="US100_FTMO_CONFLUENCE",
                hypothesis="Confluencia NY open US100: sweep/FVG/VWAP/estructura/RVOL/OR con régimen y gap.",
                symbol=symbol,
                params={key: row[key] for key in GRID},
                window_start="2021-09-15",
                window_end="2026-11-13",
                result={key: row.get(key) for key in ("n", "win", "pf", "expR", "totR", "maxDD_R")},
                outcome="passed" if is_base else "discarded",
                reason="variante del barrido v3; la base es el setfile v3"
                if not is_base
                else "setfile v3 challenge",
                source="sweep",
                run_id=run_id,
                counted=True,
            )
        except Exception:
            pass


def validate(
    df: pd.DataFrame,
    values: dict,
    *,
    ea: ExternalEA | None = None,
    db_path: str | Path = DEFAULT_DB,
    record: bool = False,
    refresh: bool = False,
) -> dict:
    rows, matrix = _grid_rows(df, values)
    baseline_index = _baseline_index(rows)
    base_returns = matrix[baseline_index]
    baseline_stats = next(
        {key: row[key] for key in ("n", "win", "pf", "expR", "totR", "maxDD_R")}
        for row in rows
        if int(row["index"]) == baseline_index
    )
    sharpe = _sharpe(base_returns)
    series_list = [matrix[index] for index in matrix.columns]
    local_srs = [period_sharpe(series) for series in series_list]
    local_n = len(series_list)
    global_n = count_tests(db_path)
    dsr_pair = dsr_local_global(
        base_returns,
        local_srs,
        local_srs,
        local_n,
        global_n,
        periods_per_year=252,
    )
    dsr_local = dsr_pair["local"]["dsr"]
    dsr_global = dsr_pair["global"]["dsr"]
    pbo = None
    try:
        pbo = float(cscv_pbo(matrix.to_numpy(dtype=float), 16, seed=0).pbo)
    except Exception:
        pbo = None
    wf = {}
    try:
        result = walk_forward(matrix.to_numpy(dtype=float), train_len=252, test_len=63)
        wf = {**result.to_dict(), "verdict": result.verdict()}
    except Exception as exc:
        wf = {"verdict": "error", "error": str(exc)[:200]}
    regime = {}
    try:
        report = regime_report(base_returns, years=YEARS, min_obs=20)
        gate = regime_gate(report)
        regime = {
            "passed": gate.passed,
            "reasons": gate.reasons,
            "years": {
                str(year): {
                    "total_return": float(stats.get("total_return", 0.0)),
                    "sharpe": float(stats.get("sharpe", 0.0)),
                    "max_drawdown": float(stats.get("max_drawdown", 0.0)),
                }
                for year, stats in report.years.items()
            },
        }
    except Exception as exc:
        regime = {"passed": False, "reasons": [str(exc)[:200]], "years": {}}
    mc = {}
    try:
        rules = from_yaml("ftmo", "challenge", 100_000)
        payload = monte_carlo(
            rules, base_returns.values, n_paths=5_000, horizon=21, seed=42
        )
        mc = {
            key: payload[key]
            for key in (
                "pass_rate",
                "breach_rate",
                "timeout_rate",
                "median_days_to_pass",
                "median_max_drawdown",
                "p5_max_drawdown",
                "worst_max_drawdown",
                "mean_daily_return",
                "daily_volatility",
                "sample_days",
            )
        }
    except Exception as exc:
        mc = {"error": str(exc)[:200]}
    costs = {}
    base_params = params_from_set(values)
    for slip in (0.5, 1.0, 2.0):
        params = dict(base_params)
        params["slip"] = slip
        _, stats = _run_variant(df, params)
        costs[str(slip)] = {
            "expR": stats.get("expR"),
            "pf": stats.get("pf"),
            "totR": stats.get("totR"),
        }
    profile = get_profile("intraday_fx")
    min_trades = int(profile.validation.min_trades) if profile else 100
    min_dsr = float(profile.validation.min_dsr) if profile else 0.90
    max_pbo = float(profile.validation.max_pbo) if profile else 0.30
    spread_median = float(pd.to_numeric(df["spread"], errors="coerce").median())
    def _dsr_status(value):
        if value is None:
            return "pendiente"
        return "ok" if value >= min_dsr else "falla"

    filters = {
        "trades": {
            "value": int(baseline_stats["n"]),
            "ok": int(baseline_stats["n"]) >= min_trades,
            "status": "ok" if int(baseline_stats["n"]) >= min_trades else "falla",
        },
        "dsr": {
            "value": dsr_global,
            "ok": dsr_global is not None and dsr_global >= min_dsr,
            "status": _dsr_status(dsr_global),
            "gate": True,
        },
        "dsr_local": {
            "value": dsr_local,
            "ok": dsr_local is not None and dsr_local >= min_dsr,
            "status": "informativo" if dsr_local is not None else "Sin datos",
            "gate": False,
        },
        "pbo": {"value": pbo, "ok": pbo is not None and pbo <= max_pbo},
        "walk_forward": {"value": wf.get("verdict"), "ok": wf.get("verdict") == "ok"},
        "regimen": {"value": regime.get("passed"), "ok": bool(regime.get("passed"))},
        "spread": {"value": spread_median, "ok": spread_median > 0},
        "coste_2pts": {
            "value": costs.get("2.0", {}).get("expR"),
            "ok": float(costs.get("2.0", {}).get("expR") or 0) > 0,
        },
    }
    passed = all(
        item["ok"] for item in filters.values() if item.get("gate", True)
    )
    base_daily_r = base_returns / (RISK_PCT / 100.0)
    dynamic = _dynamic_risk(base_daily_r, values)
    payload = {
        "ea": ea.id if ea else "us100-ftmo1",
        "symbol": ea.symbol if ea else "US100.cash",
        "setfile": str(ea.setfile) if ea else "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bars": {
            "rows": int(len(df)),
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
        },
        "params": base_params,
        "baseline": baseline_stats,
        "baseline_index": baseline_index,
        "rows": rows,
        "sharpe": sharpe,
        "n_trials": global_n,
        "n_trials_local": local_n,
        "filters": filters,
        "passed": passed,
        "dsr": dsr_global,
        "dsr_local": dsr_local,
        "dsr_global": dsr_global,
        "dsr_gate": filters["dsr"]["status"],
        "metric_version": dsr_pair["local"]["metric_version"],
        "dsr_local_meta": dsr_pair["local"],
        "dsr_global_meta": dsr_pair["global"],
        "pbo": pbo,
        "walk_forward": wf,
        "regime": regime,
        "monte_carlo": mc,
        "costs": costs,
        "dynamic_risk": dynamic,
    }
    if record:
        _record_trials(
            db_path,
            rows,
            baseline_index=baseline_index,
            run_id=uuid.uuid4().hex[:12],
            symbol=ea.symbol if ea else "US100.cash",
        )
    return payload


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_report(payload: dict) -> str:
    baseline = payload["baseline"]
    filters = payload["filters"]
    lines = [
        f"# EA US100_FTMO1 · {payload['ea']}",
        "",
        f"Generado: {payload['generated_at']} · solo lectura",
        "",
        f"- Símbolo: `{payload['symbol']}` · setfile: `{payload['setfile']}`",
        f"- Barras M5: {payload['bars']['rows']} · {payload['bars']['start']} → {payload['bars']['end']}",
        f"- Veredicto: **{'PASA' if payload['passed'] else 'NO PASA'}** los filtros del laboratorio",
        "",
        "## Base v3",
        "",
        "| Ops | Win | PF | Expectancy | Total R | DD máx. R |",
        "|---|---|---|---|---|---|",
        f"| {baseline['n']:.0f} | {baseline['win']:.1f}% | {baseline['pf']:.2f} | "
        f"{baseline['expR']:+.3f} | {baseline['totR']:+.1f} | {baseline['maxDD_R']:.1f} |",
        "",
        "## Filtros",
        "",
        "| Filtro | Valor | Estado |",
        "|---|---|---|",
    ]
    for name, item in filters.items():
        lines.append(f"| {name} | {_fmt(item['value'])} | {'OK' if item['ok'] else 'FALLO'} |")
    lines += [
        "",
        "## DSR / PBO / Walk-forward",
        "",
        f"- Sharpe diario anualizado: {payload['sharpe']:.3f}",
        f"- DSR (n_trials={payload['n_trials']}): {_fmt(payload['dsr'])}",
        f"- PBO: {_fmt(payload['pbo'])}",
        f"- Walk-forward: {payload['walk_forward'].get('verdict')} · "
        f"Sharpe OOS {_fmt(payload['walk_forward'].get('stitched_sharpe'), 3)} · "
        f"eficiencia {_fmt(payload['walk_forward'].get('efficiency'), 3)}",
        "",
        "## Monte Carlo 21 días",
        "",
        f"- Pasar +10%: {_fmt(payload['monte_carlo'].get('pass_rate'))}",
        f"- Tocar -5%: {_fmt(payload['monte_carlo'].get('breach_rate'))}",
        f"- DD mediano: {_fmt(payload['monte_carlo'].get('median_max_drawdown'))}",
        "",
        "## Riesgo dinámico v3",
        "",
        f"- Retorno simulado: {_fmt(payload['dynamic_risk'].get('return'))}",
        f"- Equity final: {_fmt(payload['dynamic_risk'].get('equity'))}",
        f"- DD máximo: {_fmt(payload['dynamic_risk'].get('max_drawdown'))}",
        f"- Kill switch 8%: {'sí' if payload['dynamic_risk'].get('killed') else 'no'}",
        "",
        "## Sensibilidad a costes",
        "",
        "| Slippage (pts) | Expectancy | PF | Total R |",
        "|---|---|---|---|",
    ]
    for slip, row in payload["costs"].items():
        lines.append(
            f"| {slip} | {_fmt(row.get('expR'), 3)} | {_fmt(row.get('pf'))} | {_fmt(row.get('totR'), 1)} |"
        )
    lines += [
        "",
        "## Barrido",
        "",
        "| # | score | RR | gap | consec | Ops | Exp. | PF | Total R |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['index']} | {row['min_score']} | {row['rr']} | {row['gap_min']} | "
            f"{row['max_consec']} | {row['n']:.0f} | {row['expR']:+.3f} | "
            f"{row['pf']:.2f} | {row['totR']:+.1f} |"
        )
    lines += [
        "",
        "> Solo lectura. El EA sigue ejecutándose en MT5; este informe no envía órdenes.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir) if out_dir else ROOT / "reports" / "ea"
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "us100-ftmo1_v3.json"
    md_path = target / "us100-ftmo1_v3.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "DEFAULT_COUNT",
    "GRID",
    "load_bars",
    "load_setfile",
    "params_from_set",
    "render_report",
    "validate",
    "write_report",
]
