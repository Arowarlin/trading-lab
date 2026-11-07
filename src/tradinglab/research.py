from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import data as data_mod
from .backtest import run as run_backtest
from .prop.rules import PropRules
from .prop.simulator import monte_carlo
from .strategies import STRATEGIES

# Rejillas deliberadamente pequeñas: el objetivo es encontrar candidatos
# robustos, no hacer fuerza bruta sobre miles de combinaciones (sobreajuste).
GRIDS: dict[str, dict[str, list]] = {
    "trend": {"fast": [20, 50], "slow": [100, 200], "regime": [200]},
    "trend-ls": {"fast": [20, 50], "slow": [100, 200], "regime": [200]},
    "meanrev": {
        "window": [10, 20],
        "entry_z": [-1.5, -2.0],
        "exit_z": [0.0],
        "max_hold": [5, 10],
    },
}

DEFAULT_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "IWM", "EURUSD=X"]


@dataclass
class ResearchConfig:
    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    strategies: list[str] = field(default_factory=lambda: list(GRIDS))
    start: str = "2015-01-01"
    end: str = ""
    account_size: float = 100_000.0
    paths: int = 2_000
    horizon: int = 120
    block_size: int = 5
    min_trades: int = 20
    min_pass: float = 0.35
    min_oos_pass: float = 0.25
    max_breach: float = 0.15
    holdout_fraction: float = 0.30
    exposures: list[float] = field(default_factory=lambda: [1.0, 0.5])
    commission_bps: float = 1.0
    slippage_bps: float = 5.0


def _combos(strategy: str) -> list[dict]:
    grid = GRIDS.get(strategy)
    if not grid:
        raise ValueError(f"sin rejilla para la estrategia '{strategy}'")
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _score(pass_rate: float, breach_rate: float, sharpe: float) -> float:
    """Ventaja neta contra las reglas, con el Sharpe como desempate suave."""
    return (pass_rate - breach_rate) + 0.01 * max(min(sharpe, 3.0), -3.0)


def run_research(cfg: ResearchConfig, rules: PropRules, cache_dir: str | Path) -> dict:
    """Escanea activos × estrategias × parámetros y puntúa contra las reglas."""
    end = cfg.end or datetime.now(timezone.utc).date().isoformat()
    results: list[dict] = []
    errors: list[dict] = []

    for symbol in cfg.symbols:
        try:
            df = data_mod.fetch(symbol, cfg.start, end, cache_dir)
        except Exception as exc:  # un símbolo roto no debe tumbar el barrido
            errors.append({"symbol": symbol, "error": str(exc)[:300]})
            continue

        if len(df) < 260:
            errors.append({"symbol": symbol, "error": f"histórico insuficiente ({len(df)} barras)"})
            continue

        for strategy in cfg.strategies:
            for params in _combos(strategy):
                try:
                    sig = STRATEGIES[strategy](df, **params)
                    bt = run_backtest(
                        df,
                        sig.target,
                        starting_cash=rules.account_size,
                        commission_bps=cfg.commission_bps,
                        slippage_bps=cfg.slippage_bps,
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "symbol": symbol,
                            "strategy": strategy,
                            "params": params,
                            "error": str(exc)[:300],
                        }
                    )
                    continue

                m = bt.metrics
                sharpe = float(m.get("sharpe", 0.0))
                cagr = float(m.get("cagr", 0.0))
                split = max(1, int(len(bt.returns) * (1.0 - cfg.holdout_fraction)))
                oos_returns = bt.returns.iloc[split:]
                oos_start = (
                    str(bt.equity.index[split].date()) if split < len(bt.equity) else None
                )
                oos_end = str(bt.equity.index[-1].date())
                for exposure in cfg.exposures:
                    try:
                        mc = monte_carlo(
                            rules,
                            bt.returns * exposure,
                            n_paths=cfg.paths,
                            horizon=cfg.horizon,
                            block_size=cfg.block_size,
                        )
                        oos = (
                            monte_carlo(
                                rules,
                                oos_returns * exposure,
                                n_paths=max(200, cfg.paths // 2),
                                horizon=cfg.horizon,
                                block_size=cfg.block_size,
                            )
                            if len(oos_returns) >= 120
                            else None
                        )
                    except Exception as exc:
                        errors.append(
                            {
                                "symbol": symbol,
                                "strategy": strategy,
                                "params": params,
                                "exposure": exposure,
                                "error": str(exc)[:300],
                            }
                        )
                        continue

                    pass_rate = float(mc["pass_rate"])
                    breach_rate = float(mc["breach_rate"])
                    results.append(
                        {
                            "symbol": symbol,
                            "strategy": strategy,
                            "params": params,
                            "exposure": exposure,
                            "sharpe": sharpe,
                            "cagr": cagr * exposure,
                            "max_drawdown": float(m.get("max_drawdown", 0.0)) * exposure,
                            "num_trades": int(m.get("num_trades", 0)),
                            "win_rate": float(m.get("win_rate", 0.0)),
                            "exposure_avg": float(m.get("exposure", 0.0)),
                            "pass_rate": pass_rate,
                            "pass_ci95": list(mc["pass_ci95"]),
                            "breach_rate": breach_rate,
                            "timeout_rate": float(mc["timeout_rate"]),
                            "median_days_to_pass": mc["median_days_to_pass"],
                            "oos_pass_rate": float(oos["pass_rate"]) if oos else None,
                            "oos_breach_rate": float(oos["breach_rate"]) if oos else None,
                            "oos_start": oos_start,
                            "oos_end": oos_end,
                            "score": _score(pass_rate, breach_rate, sharpe),
                        }
                    )

    results.sort(key=lambda r: r["score"], reverse=True)
    proposals = [
        r
        for r in results
        if r["pass_rate"] >= cfg.min_pass
        and r["breach_rate"] <= cfg.max_breach
        and (r["oos_pass_rate"] is None or r["oos_pass_rate"] >= cfg.min_oos_pass)
        and r["sharpe"] > 0
        and r["num_trades"] >= cfg.min_trades
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": rules.describe(),
        "config": {
            "symbols": cfg.symbols,
            "strategies": cfg.strategies,
            "start": cfg.start,
            "end": end,
            "paths": cfg.paths,
            "horizon": cfg.horizon,
            "block_size": cfg.block_size,
            "min_trades": cfg.min_trades,
            "min_pass": cfg.min_pass,
            "min_oos_pass": cfg.min_oos_pass,
            "max_breach": cfg.max_breach,
            "holdout_fraction": cfg.holdout_fraction,
            "exposures": cfg.exposures,
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
        },
        "results": results,
        "proposals": [
            {
                "id": (
                    f"{p['symbol']}:{p['strategy']}:x{p['exposure']:g}:"
                    f"{json.dumps(p['params'], sort_keys=True)}"
                ),
                "symbol": p["symbol"],
                "strategy": p["strategy"],
                "params": p["params"],
                "exposure": p["exposure"],
                "score": p["score"],
                "pass_rate": p["pass_rate"],
                "breach_rate": p["breach_rate"],
                "oos_pass_rate": p["oos_pass_rate"],
                "oos_breach_rate": p["oos_breach_rate"],
                "num_trades": p["num_trades"],
                "max_drawdown": p["max_drawdown"],
                "sharpe": p["sharpe"],
                "status": "proposed",
                "enabled": False,
                "note": "Requiere aprobación humana; el bucle no activa bots solo.",
            }
            for p in proposals
        ],
        "errors": errors,
        "candidates": len(results),
    }


def render_markdown(report: dict, top: int = 25) -> str:
    cfg = report["config"]
    top_result = report["results"][0] if report.get("results") else {}
    oos_start = top_result.get("oos_start")
    oos_end = top_result.get("oos_end")
    oos_range = f"{oos_start} → {oos_end}" if oos_start else "último tramo de la muestra"
    warning = (
        "> Aviso: al elegir el mejor de cientos de variantes el resultado está sesgado "
        f"al alza. La columna OOS es el filtro mínimo de estabilidad, no una garantía: "
        f"el tramo reservado ({oos_range}) puede caer en un régimen favorable y dar "
        "tasas muy altas que no se repetirán en otro mercado."
    )
    lines = [
        "# Investigación de estrategias",
        "",
        f"- Generado: {report['generated_at']}",
        f"- Reglas: {report['rules']}",
        f"- Activos: {', '.join(cfg['symbols'])}",
        f"- Estrategias: {', '.join(cfg['strategies'])}",
        f"- Muestra: {cfg['start']} → {cfg['end']} · "
        f"{cfg['paths']} paths · horizonte {cfg['horizon']} días · bloque {cfg['block_size']}",
        f"- Escalas de exposición: {', '.join(f'{x:g}' for x in cfg['exposures'])}",
        f"- Validación out-of-sample: último {cfg['holdout_fraction']:.0%} de la muestra",
        f"- Ventana OOS: {oos_range}",
        f"- Variantes evaluadas: {report['candidates']}",
        "",
        warning,
        "",
        "## Ranking",
        "",
        "| # | Activo | Estrategia | Parámetros | Escala | Sharpe | CAGR | MaxDD | Trades | Pasa | Revienta | Pasa OOS | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def pct(x: float) -> str:
        return f"{x * 100:,.1f}%"

    def pct_opt(x) -> str:
        return "—" if x is None else pct(x)

    for i, r in enumerate(report["results"][:top], 1):
        params = " ".join(f"{k}={v}" for k, v in r["params"].items())
        lines.append(
            f"| {i} | {r['symbol']} | {r['strategy']} | {params} | "
            f"{r['exposure']:g}× | {r['sharpe']:,.2f} | {pct(r['cagr'])} | "
            f"{pct(r['max_drawdown'])} | {r['num_trades']} | {pct(r['pass_rate'])} | "
            f"{pct(r['breach_rate'])} | {pct_opt(r.get('oos_pass_rate'))} | {r['score']:,.3f} |"
        )

    lines += [
        "",
        "## Propuestas",
        "",
        f"Criterios: pasa ≥ {cfg['min_pass']:.0%}, revienta ≤ {cfg['max_breach']:.0%}, "
        f"OOS ≥ {cfg['min_oos_pass']:.0%}, Sharpe > 0, trades ≥ {cfg['min_trades']}.",
        "",
    ]
    if report["proposals"]:
        lines += [
            "| Activo | Estrategia | Parámetros | Escala | Pasa | Revienta | OOS | Score |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for p in report["proposals"]:
            params = " ".join(f"{k}={v}" for k, v in p["params"].items())
            lines.append(
                f"| {p['symbol']} | {p['strategy']} | {params} | {p['exposure']:g}× | "
                f"{pct(p['pass_rate'])} | {pct(p['breach_rate'])} | "
                f"{pct_opt(p.get('oos_pass_rate'))} | {p['score']:,.3f} |"
            )
        lines += [
            "",
            "> `enabled: false` — ninguna propuesta se activa automáticamente. "
            "Para promoverla: revisar el backtest, añadirla a `config/bots.yaml` y "
            "volver a simular con datos intradía.",
        ]
    else:
        lines.append(
            "Ningún candidato cumple los criterios. Es un resultado válido: "
            "no pagues un challenge con estas estrategias todavía."
        )

    if report["errors"]:
        lines += ["", "## Errores", ""]
        lines += [f"- `{e}`" for e in report["errors"][:20]]

    lines += [
        "",
        "---",
        "Aproximación con retornos diarios: el riesgo intradía real es mayor. "
        "No es asesoramiento financiero.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(report: dict, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_text = json.dumps(report, indent=2, ensure_ascii=False)
    md_text = render_markdown(report)

    files = {
        "run_json": out / f"research_{stamp}.json",
        "run_md": out / f"research_{stamp}.md",
        "latest_json": out / "latest.json",
        "latest_md": out / "latest.md",
        "proposals_json": out / "proposals.json",
        "proposals_md": out / "proposals.md",
    }
    for key in ("run_json", "latest_json"):
        files[key].write_text(json_text, encoding="utf-8")
    for key in ("run_md", "latest_md"):
        files[key].write_text(md_text, encoding="utf-8")

    proposals = {
        "generated_at": report["generated_at"],
        "rules": report["rules"],
        "auto_enable": False,
        "proposals": report["proposals"],
    }
    files["proposals_json"].write_text(
        json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    proposals_md = [
        "# Propuestas de bots",
        "",
        f"Generado: {report['generated_at']}",
        "",
        "Ninguna propuesta está activa. Requieren revisión y aprobación humana.",
        "",
    ]
    if report["proposals"]:
        for p in report["proposals"]:
            oos = (
                f", OOS {p['oos_pass_rate']:.1%}"
                if p.get("oos_pass_rate") is not None
                else ""
            )
            proposals_md.append(
                f"- **{p['symbol']} · {p['strategy']}** "
                f"({json.dumps(p['params'], ensure_ascii=False)}, escala {p['exposure']:g}×) — "
                f"pasa {p['pass_rate']:.1%}, revienta {p['breach_rate']:.1%}{oos} · "
                f"`{p['status']}`"
            )
    else:
        proposals_md.append("- Sin propuestas que cumplan los criterios.")
    files["proposals_md"].write_text("\n".join(proposals_md) + "\n", encoding="utf-8")

    return {k: str(v) for k, v in files.items()}


__all__ = [
    "ResearchConfig",
    "GRIDS",
    "DEFAULT_SYMBOLS",
    "run_research",
    "render_markdown",
    "write_outputs",
]
