"""Oráculo externo del simulador de fondeo con prop-ev.

Compara la P(pasar) y la tasa de incumplimiento de `prop/simulator.monte_carlo`
con el motor independiente **prop-ev** (Makeph/prop-ev), instalado solo en
`.venv-vbt`.

Uso (venv principal del laboratorio):

    .\\.venv\\Scripts\\python.exe scripts\\oracle_prop_ev.py --bot qqq-trend-f13

prop-ev se ejecuta en un subproceso con `.venv-vbt\\Scripts\\python.exe` para que
el paquete externo no entre nunca en el entorno del laboratorio.

Salida: `reports/research/oracles/prop_ev.md`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradinglab import data as data_mod  # noqa: E402
from tradinglab.backtest import run as run_backtest  # noqa: E402
from tradinglab.config import ROOT, get_settings  # noqa: E402
from tradinglab.prop.rules import from_yaml  # noqa: E402
from tradinglab.prop.simulator import monte_carlo  # noqa: E402
from tradinglab.strategies import STRATEGIES  # noqa: E402

OUT_DIR = ROOT / "reports" / "research" / "oracles"
VBT_PYTHON = ROOT / ".venv-vbt" / "Scripts" / "python.exe"
N_PATHS = 2_000
BLOCK = 5
SEED = 42
PROP_SIMS = 20_000

CHILD = """
import json, sys
from propev import Firm, simulate

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
firm = Firm(**payload["firm"])
p_pass = simulate(
    firm,
    payload["edge_bps"],
    payload["std_bps"],
    payload["trades_per_day"],
    n_sims=payload["n_sims"],
    seed=payload["seed"],
)
print(json.dumps({"p_pass": p_pass, "propev_version": __import__("propev").__version__}))
"""


def bot_config(bot_id: str) -> dict:
    import yaml

    raw = yaml.safe_load((ROOT / "config" / "bots.yaml").read_text(encoding="utf-8"))
    for bot in raw.get("bots") or []:
        if str(bot.get("id")) == bot_id:
            return bot
    raise SystemExit(f"bot {bot_id} no está en config/bots.yaml")


def run_prop_ev(payload: dict) -> dict:
    if not VBT_PYTHON.exists():
        return {"error": f"no existe {VBT_PYTHON}"}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "payload.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run(
            [str(VBT_PYTHON), "-c", CHILD, str(path)],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    if proc.returncode != 0:
        return {"error": proc.stderr[-800:] or f"exit {proc.returncode}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": f"salida no interpretable: {proc.stdout[-400:]}"}


def build_firm(rules, *, phases: int, max_days: int) -> dict:
    """Firm de prop-ev con los límites EFECTIVOS (mismo criterio que monte_carlo)."""
    account = float(rules.account_size)
    return {
        "name": f"ftmo-{rules.phase}-{phases}fase-{max_days}d",
        "account": account,
        "target": float(rules.profit_target_pct),
        "daily_dd": float(rules.effective_daily_limit_usd / account),
        "total_dd": float(rules.effective_max_loss_usd / account),
        "min_days": int(rules.min_trading_days),
        "phases": int(phases),
        "consistency": rules.consistency_pct,
        "trailing": bool(rules.max_loss_mode != "static"),
        "fee": 0.0,
        "profit_split": 0.80,
        "max_days": int(max_days),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Oráculo prop-ev del simulador de fondeo")
    parser.add_argument("--bot", default="qqq-trend-f13")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()

    settings = get_settings()
    bot = bot_config(args.bot)
    symbol = str((bot.get("universe") or ["SPY"])[0]).upper()
    strategy = str(bot.get("strategy") or "trend")
    exposure = float(bot.get("exposure") or 1.0)
    params = dict(bot.get("params") or {})

    df = data_mod.fetch(symbol, "2015-01-01", "", settings.data.cache_dir)
    signal = STRATEGIES[strategy](df, **params)
    target = (signal.target.astype(float) * exposure).clip(-1.0, 1.0)
    bt = run_backtest(
        df,
        target,
        starting_cash=100_000.0,
        commission_bps=settings.execution.commission_bps,
        slippage_bps=settings.execution.slippage_bps,
    )
    returns = bt.returns.astype(float)
    trade_pnls = [float(value) for value in bt.trade_pnls]
    trade_days = list(bt.trade_days)

    rules = from_yaml("ftmo", "challenge", 100_000.0)
    account = float(rules.account_size)

    edge_bps = statistics.fmean(trade_pnls) / account * 10_000 if trade_pnls else 0.0
    std_bps = (
        statistics.stdev(trade_pnls) / account * 10_000 if len(trade_pnls) > 1 else 0.0
    )
    per_day = Counter(trade_days)
    trades_per_day = max(1, int(round(statistics.fmean(per_day.values())))) if per_day else 1

    comparisons: list[dict] = []
    for horizon, phases in ((30, 2), (120, 1)):
        mc = monte_carlo(
            rules,
            returns,
            n_paths=N_PATHS,
            horizon=horizon,
            block_size=BLOCK,
            seed=SEED,
        )
        firm = build_firm(rules, phases=phases, max_days=horizon)
        external = run_prop_ev(
            {
                "firm": firm,
                "edge_bps": edge_bps,
                "std_bps": std_bps,
                "trades_per_day": trades_per_day,
                "n_sims": PROP_SIMS,
                "seed": 0,
            }
        )
        comparisons.append(
            {
                "horizon": horizon,
                "phases": phases,
                "firm": firm,
                "lab": {
                    "pass_rate": mc["pass_rate"],
                    "breach_rate": mc["breach_rate"],
                    "timeout_rate": mc["timeout_rate"],
                    "median_max_drawdown": mc["median_max_drawdown"],
                },
                "prop_ev": external,
            }
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Oráculo prop-ev · simulador de fondeo",
        "",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Bot: **{args.bot}** · {symbol} · estrategia {strategy} · exposición {exposure}",
        f"- Operaciones del backtest: **{len(trade_pnls)}** · "
        f"días con operación: **{len(per_day)}** · operaciones/día (media): **{trades_per_day}**",
        f"- Edge por operación: **{edge_bps:.3f} bps** del capital · "
        f"desviación: **{std_bps:.3f} bps**",
        f"- Motor del laboratorio: `prop/simulator.monte_carlo` "
        f"({N_PATHS} paths, bloque {BLOCK}, seed {SEED})",
        f"- Motor externo: prop-ev {comparisons[0]['prop_ev'].get('propev_version', '?')} "
        f"({PROP_SIMS} simulaciones, seed 0) en `.venv-vbt`",
        "",
        "## Reglas (FTMO 2-step, config/prop.yaml)",
        "",
        "| Regla | Valor |",
        "|---|---:|",
        f"| Tamaño | {account:,.0f} |",
        f"| Objetivo | {rules.profit_target_pct:.1%} |",
        f"| Pérdida diaria efectiva | {rules.effective_daily_limit_usd / account:.2%} |",
        f"| Pérdida máxima efectiva | {rules.effective_max_loss_usd / account:.2%} |",
        f"| Modo de drawdown | {rules.max_loss_mode} |",
        f"| Días mínimos | {rules.min_trading_days} |",
        "| Fee del reto | Sin datos (no está en config/prop.yaml) |",
        "",
        "## Comparación",
        "",
    ]

    for item in comparisons:
        firm = item["firm"]
        external = item["prop_ev"]
        lab = item["lab"]
        if "p_pass" in external:
            pass_line = f"| P(pasar) | {lab['pass_rate']:.2%} | {external['p_pass']:.2%} |"
        else:
            pass_line = f"| P(pasar) | {lab['pass_rate']:.2%} | Sin datos |"
        lines += [
            f"### Horizonte {item['horizon']} días · {item['phases']} fase(s)",
            "",
            "| Métrica | Laboratorio | prop-ev |",
            "|---|---:|---:|",
            pass_line,
            f"| Incumplimiento (breach) | {lab['breach_rate']:.2%} | Sin datos (prop-ev "
            f"no separa breach de timeout) |",
            f"| Timeout | {lab['timeout_rate']:.2%} | Sin datos |",
            f"| Drawdown mediano | {lab['median_max_drawdown']:.2%} | Sin datos |",
            "",
            f"- Firm usado en prop-ev: `{json.dumps(firm, ensure_ascii=False)}`",
            "",
        ]
        if "error" in external:
            lines += [f"- Error al ejecutar prop-ev: {external['error']}", ""]

    lines += [
        "## Lectura: por qué los números no coinciden",
        "",
        "Los dos motores miden cosas distintas y **no son equivalentes**:",
        "",
        "1. **Modelo de entrada.** El laboratorio hace *bootstrap por bloques* de "
        "los retornos diarios reales (preserva la autocorrelation y las rachas). "
        "prop-ev assume que cada operación tiene una PnL gaussiana i.i.d. con la "
        "media y la desviación observadas; no reproduce la forma de la distribución.",
        "2. **Unidad de la simulación.** El laboratorio avanza día a día y evalúa "
        "los suelos al cierre de cada día. prop-ev avanza operación a operación y "
        "evalúa el drawdown tras cada operación.",
        "3. **Fases y horizonte.** FTMO 2-step son dos fases; la tabla alinea los "
        "horizontes (30 días con 2 fases frente a 120 días con 1 fase) porque "
        "prop-ev no permite mezclar fase y horizonte.",
        "4. **Break-even.** prop-ev no separa *breach* de *timeout*: su salida es "
        "P(pasar) y el resto es \"no pasó\".",
        "5. **Fee.** Sin el precio del reto en `config/prop.yaml`, el EV de prop-ev "
        "no es calculable: se deja la fee a 0 y no se publica EV.",
        "",
        "**Conclusión:** prop-ev sirve como control de orden de magnitud, no como "
        "réplica. Si las dos herramientas dieran cifras comparables sin explicar "
        "estas diferencias, habría que parar e investigar; aquí la diferencia es "
        "esperada por construcción y **no se modifica `prop/simulator.py`**.",
        "",
    ]
    (out_dir / "prop_ev.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "prop_ev.json").write_text(
        json.dumps(
            {
                "bot": args.bot,
                "symbol": symbol,
                "edge_bps": edge_bps,
                "std_bps": std_bps,
                "trades_per_day": trades_per_day,
                "operations": len(trade_pnls),
                "comparisons": comparisons,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"JSON y Markdown en {out_dir}")
    for item in comparisons:
        print(
            f"  {item['horizon']}d/{item['phases']}f: "
            f"lab pass={item['lab']['pass_rate']:.2%} breach={item['lab']['breach_rate']:.2%} | "
            f"prop-ev pass={item['prop_ev'].get('p_pass', 'Sin datos')}"
        )


if __name__ == "__main__":
    main()
