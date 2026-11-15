"""Horizonte del challenge para el EA US100 FTMO1 (sin optimizar nada).

Usa los retornos diarios del motor v3 con el riesgo dinámico del setfile y con
0,35 % fijo, y simula FTMO 100k a 21, 60, 120 y 750 días (el "sin límite"
práctico de `exposure_sweep`). Reutiliza la economía y el Monte Carlo de
`exposure_sweep`; no crea variantes ni toca el EA.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT, Settings, get_settings
from .ea_registry import ExternalEA, get_ea
from .ea_us100 import load_bars, load_setfile, params_from_set
from .ea_us100_engine import run as run_engine
from .exposure_sweep import _economics, eurusd_rate, funded_month_payout
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo

HORIZONS = (21, 60, 120, 750)
NO_LIMIT = 750
PATHS = 5_000
SEED = 42


def _daily_r(df: pd.DataFrame, values: dict) -> pd.Series:
    trades = run_engine(df, params_from_set(values))
    if trades is None or len(trades) == 0:
        return pd.Series(dtype=float)
    stamps = pd.to_datetime(trades["t"]).dt.normalize()
    return trades.assign(day=stamps).groupby("day")["r"].sum().sort_index()


def _fixed_returns(daily_r: pd.Series, risk_pct: float = 0.35) -> pd.Series:
    return daily_r.astype(float) * (float(risk_pct) / 100.0)


def _dynamic_returns(daily_r: pd.Series, values: dict) -> pd.Series:
    base = float(values.get("InpDynBase", 1.0) or 1.0)
    dd1 = float(values.get("InpDynDD1", 2.0) or 2.0)
    dd2 = float(values.get("InpDynDD2", 4.0) or 4.0)
    dd3 = float(values.get("InpDynDD3", 6.0) or 6.0)
    r1 = float(values.get("InpDynR1", 0.60) or 0.60)
    r2 = float(values.get("InpDynR2", 0.35) or 0.35)
    r3 = float(values.get("InpDynR3", 0.25) or 0.25)
    daily_stop = float(values.get("InpDailyLossPct", 1.5) or 1.5)
    initial = 100_000.0
    equity = initial
    previous = initial
    out: dict = {}
    for day, value in daily_r.items():
        dd = max(0.0, (initial - equity) / initial * 100.0)
        risk = base if dd < dd1 else r1 if dd < dd2 else r2 if dd < dd3 else r3
        pnl = float(value) * initial * risk / 100.0
        pnl = max(pnl, -daily_stop / 100.0 * initial)
        out[day] = pnl / previous if previous else 0.0
        equity += pnl
        previous = equity
    return pd.Series(out, dtype=float).sort_index()


def _mc(returns: pd.Series, rules, horizon: int) -> dict:
    return monte_carlo(
        rules,
        returns.values,
        n_paths=PATHS,
        horizon=int(horizon),
        block_size=1,
        seed=SEED,
    )


def _ev(
    returns: pd.Series,
    rules,
    *,
    horizon: int,
    fee_eur: float,
    split: float,
    refund: bool,
    rate: float | None,
) -> dict:
    result = _mc(returns, rules, horizon)
    payout_usd = funded_month_payout(
        returns,
        k=1.0,
        account=float(rules.account_size),
        split=split,
        rules=rules,
        paths=PATHS,
        block=1,
        seed=SEED,
    )
    payout_eur = (
        float(payout_usd["expected_payout_usd"]) / rate if rate else None
    )
    refund_eur = fee_eur if refund else 0.0
    ev = (
        float(result["pass_rate"]) * (payout_eur + refund_eur) - fee_eur
        if payout_eur is not None
        else None
    )
    return {
        "pass_rate": result["pass_rate"],
        "breach_rate": result["breach_rate"],
        "timeout_rate": result["timeout_rate"],
        "median_days_to_pass": result["median_days_to_pass"],
        "median_max_drawdown": result["median_max_drawdown"],
        "p5_max_drawdown": result["p5_max_drawdown"],
        "payout_eur": payout_eur,
        "ev_eur": ev,
    }


def run(
    *,
    ea_id: str = "us100-ftmo1",
    settings: Settings | None = None,
    paths: int = PATHS,
) -> dict:
    global PATHS
    PATHS = int(paths)
    cfg = settings or get_settings()
    ea: ExternalEA | None = get_ea(ea_id)
    if ea is None:
        raise ValueError(f"EA no registrado: {ea_id}")
    values = load_setfile(ea.setfile)
    bars = load_bars(cfg)
    daily_r = _daily_r(bars, values)
    rules = from_yaml("ftmo", "challenge", 100_000)
    economics = _economics(None, None, None)
    rate_info = eurusd_rate(cfg.data.cache_dir)
    rate = rate_info.get("rate")
    modes = {
        "fixed_0.35": _fixed_returns(daily_r),
        "dynamic_v3": _dynamic_returns(daily_r, values),
    }
    rows = {}
    for name, series in modes.items():
        rows[name] = {}
        for horizon in HORIZONS:
            label = "sin_limite" if horizon == NO_LIMIT else str(horizon)
            rows[name][label] = {
                "horizon_days": horizon,
                **_ev(
                    series,
                    rules,
                    horizon=horizon,
                    fee_eur=float(economics["fee_eur"]),
                    split=float(economics["profit_split"]),
                    refund=bool(economics["fee_refund_on_pass"]),
                    rate=float(rate) if rate else None,
                ),
            }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ea": ea.id,
        "symbol": ea.symbol,
        "setfile": str(ea.setfile),
        "bars": {"rows": len(bars), "start": str(bars.index[0]), "end": str(bars.index[-1])},
        "sample_days": int(len(daily_r)),
        "trades": int(round(daily_r.count())) if len(daily_r) else 0,
        "paths": PATHS,
        "seed": SEED,
        "horizons": list(HORIZONS),
        "no_limit_days": NO_LIMIT,
        "economics": economics,
        "eurusd": rate_info,
        "modes": rows,
    }


def render_report(payload: dict) -> str:
    lines = [
        f"# Horizonte del challenge · {payload['ea']}",
        "",
        f"Generado: {payload['generated_at']} · solo lectura",
        "",
        f"- Símbolo: `{payload['symbol']}` · setfile: `{payload['setfile']}`",
        f"- Barras M5: {payload['bars']['rows']} · {payload['bars']['start']} → {payload['bars']['end']}",
        f"- Días con operaciones: {payload['sample_days']} · paths: {payload['paths']:,} · seed {payload['seed']}",
        f"- Economía: cuota {payload['economics']['fee_eur']:.0f} EUR · split {payload['economics']['profit_split']:.0%} · reembolso {'sí' if payload['economics']['fee_refund_on_pass'] else 'no'} · EURUSD {payload['eurusd'].get('rate')}",
        "",
        "## Resultados",
        "",
        "| Riesgo | Horizonte | P(pasar) | P(breach) | Mediana días | DD mediano | EV neto (EUR) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for mode, label in (("fixed_0.35", "0,35 % fijo"), ("dynamic_v3", "dinámico v3")):
        for key, row in payload["modes"][mode].items():
            horizon = "sin límite (750 d)" if key == "sin_limite" else f"{key} d"
            lines.append(
                f"| {label} | {horizon} | {row['pass_rate']:.2%} | "
                f"{row['breach_rate']:.2%} | {row['median_days_to_pass'] or '—'} | "
                f"{row['median_max_drawdown'] * 100:.2f}% | "
                f"{row['ev_eur']:+.0f} |"
                if row["ev_eur"] is not None
                else f"| {label} | {horizon} | {row['pass_rate']:.2%} | "
                f"{row['breach_rate']:.2%} | {row['median_days_to_pass'] or '—'} | "
                f"{row['median_max_drawdown'] * 100:.2f}% | Sin datos |"
            )
    lines += [
        "",
        "> El horizonte \"sin límite\" se corta a 750 días, el máximo práctico de",
        "> `exposure_sweep`. No se optimizó ni se probó ninguna variante nueva.",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "ea_us100_ftmo1"
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "horizon.json"
    md_path = target / "horizon.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "HORIZONS",
    "NO_LIMIT",
    "PATHS",
    "render_report",
    "run",
    "write_report",
]
