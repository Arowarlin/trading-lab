"""Construye el informe de las familias de sesión intradía.

Lee los informes de research intradía por activo
(`reports/research/intraday/<ACTIVO>.json`) y extrae las familias nuevas
(`session_hold`, `fix_flow`) con la misma tabla que los informes M15:
DSR, PBO, WF, pasan, mejor neto, equilibrio y calibrado, más el Monte Carlo
de FTMO a 120 días (P(pasar) y P(breach)).

Uso:
    .venv\\Scripts\\python.exe scripts\\build_intraday_session_report.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "research"
INTRADAY = REPORTS / "intraday"
OUT = REPORTS / "intraday_session"
FAMILIES = ("session_hold", "fix_flow")
SYMBOLS = ("EURUSD", "USDJPY")
MC_FIRM = "FTMO"


def _fmt(value, digits=2, suffix="") -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _key(params: object) -> str:
    return json.dumps(params or {}, sort_keys=True, default=str)


def _mc_table(doc: dict) -> dict[tuple[str, str], dict]:
    """Monte Carlo por (familia, params) con el horizonte más largo de FTMO."""
    table: dict[tuple[str, str], dict] = {}
    for entry in doc.get("monte_carlo") or []:
        if str(entry.get("firm") or "") != MC_FIRM:
            continue
        key = (str(entry.get("strategy") or ""), _key(entry.get("params")))
        current = table.get(key)
        if current is None or int(entry.get("horizon") or 0) > int(
            current.get("horizon") or 0
        ):
            table[key] = entry
    return table


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    dsr_n = None
    pbo_global = None
    wf_global = None
    missing: list[str] = []

    for symbol in SYMBOLS:
        path = INTRADAY / f"{symbol}.json"
        if not path.exists():
            print(f"sin informe: {path}")
            missing.append(symbol)
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        dsr_n = doc.get("dsr_n_trials", dsr_n)
        pbo_global = (doc.get("pbo") or {}).get("pbo", pbo_global)
        wf_global = doc.get("walk_forward_verdict", wf_global)
        mc_by_variant = _mc_table(doc)
        for outcome in doc.get("outcomes") or []:
            family = str(outcome.get("strategy") or "")
            if family not in FAMILIES:
                continue
            metrics = outcome.get("metrics") or {}
            mc = mc_by_variant.get((family, _key(outcome.get("params")))) or {}
            rows.append(
                {
                    "symbol": symbol,
                    "family": family,
                    "params": outcome.get("params") or {},
                    "net": metrics.get("total_return"),
                    "sharpe": metrics.get("sharpe"),
                    "max_dd": metrics.get("max_drawdown"),
                    "trades": metrics.get("num_trades"),
                    "dsr": outcome.get("dsr"),
                    "pbo": outcome.get("pbo"),
                    "wf": outcome.get("wf_verdict"),
                    "passed": outcome.get("passed"),
                    "reason": outcome.get("failure_reason"),
                    "breakeven_cost_bps": outcome.get("breakeven_cost_bps"),
                    "calibrated_cost_bps": outcome.get("calibrated_cost_bps"),
                    "mc_pass": mc.get("pass_rate"),
                    "mc_breach": mc.get("breach_rate"),
                }
            )

    lines = [
        "# Familias de sesión intradía",
        "",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Familias: {', '.join(FAMILIES)}",
        f"- Activos: {', '.join(SYMBOLS)}"
        + (f" (sin informe: {', '.join(missing)})" if missing else ""),
        f"- DSR n_trials: {dsr_n if dsr_n is not None else 'Sin datos'}",
        f"- PBO global: {_fmt(pbo_global, 3)}",
        f"- Walk-forward global: {wf_global or 'Sin datos'}",
        "- Monte Carlo: FTMO 100k, horizonte 120 días (P(pasar) y P(breach)).",
        "- Costes calibrados por activo (los ya existentes). Ningún bot queda activado.",
        "",
        "| Símbolo | Familia | Params | Neto | Sharpe | MaxDD | Trades | DSR | PBO | WF | Pasan | Equilibrio | Calibrado | P(pasar) | P(breach) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['symbol']} | {row['family']} | `{json.dumps(row['params'], ensure_ascii=False)}` | "
            f"{_fmt(row['net'], 2, '%')} | {_fmt(row['sharpe'])} | {_fmt(row['max_dd'], 2, '%')} | "
            f"{row['trades'] if row['trades'] is not None else 'Sin datos'} | "
            f"{_fmt(row['dsr'], 3)} | {_fmt(row['pbo'], 3)} | {row['wf'] or 'Sin datos'} | "
            f"{'sí' if row['passed'] else 'no'} | {_fmt(row['breakeven_cost_bps'])} | "
            f"{_fmt(row['calibrated_cost_bps'])} | {_fmt(row['mc_pass'], 3)} | "
            f"{_fmt(row['mc_breach'], 3)} |"
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    passed = [row for row in rows if row["passed"]]
    lines += [
        "",
        f"**Resultado: {len(passed)} de {len(rows)} variantes pasan.**",
        "",
    ]
    if not passed:
        lines += [
            "Ninguna variante pasa la puerta: **se documenta y se para**. No se relajan",
            "umbrales ni se activan bots. Las familias quedan en el catálogo con",
            "`enabled: false`.",
            "",
        ]
    else:
        lines += [
            "Las que pasan siguen siendo **candidatas**: ningún bot se crea ni se activa",
            "sin la puerta de incubación y la aprobación humana.",
            "",
        ]

    (OUT / "intraday_session.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "intraday_session.json").write_text(
        json.dumps(
            {
                "rows": rows,
                "dsr_n_trials": dsr_n,
                "pbo": pbo_global,
                "walk_forward": wf_global,
                "missing": missing,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(
        f"escrito: {OUT / 'intraday_session.md'} "
        f"({len(rows)} variantes, {len(passed)} pasan)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
