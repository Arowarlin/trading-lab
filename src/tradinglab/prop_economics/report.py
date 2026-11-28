"""Informe reproducible del motor EV (04 §7.3; encargo del operador: datos, fecha, código, supuestos,
fórmulas, simulaciones, resultados, limitaciones, confianza y evidencia) — FUT-A8."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone

from ..config import ROOT
from .paths import DayPath
from .project import ProjectConfig
from .rules import Program, blocking_unknowns, is_expired
from .scenarios import pool_stats

FORMULAS = [
    "Rotura: E(τ) ≤ L(τ) (igualdad incluida); trailing EOD L = min(máx B − D, K); intradía L = min(máx E − D, K)",
    "Payout disponible = min(fracción·beneficio, tope, beneficio − colchón); recibido = reparto·w − comisión",
    "Neto(H) = payouts cobrados hasta H − tarifas pagadas hasta H (presupuesto aparte)",
    "Bootstrap estacionario (Politis-Romano) con números aleatorios comunes entre escenarios",
]
LIMITS = [
    "Una cuenta a la vez por camino; sin reset (se compra otra evaluación); Live fuera del modelo",
    "Los payouts se suponen aprobados si cumplen las reglas; el cobro llega a los processing_days",
    "Las renovaciones de suscripción se cobran aunque falte caja",
]


def _git_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - el informe no debe caer por git
        return "Sin datos"


def pool_hash(pool: list[DayPath]) -> str:
    h = hashlib.sha256()
    for d in pool:
        h.update(d.session_date.isoformat().encode())
        h.update(d.marks.tobytes())
        h.update(f"{d.n_trades}|{d.gross_pnl}|{d.cost}|{d.source}".encode())
    return h.hexdigest()[:16]


def build_report(program: Program, pool: list[DayPath], cfg: ProjectConfig, result: dict, *, n_paths: int, seed: int,
                 today, extra: dict | None = None) -> dict:
    sources = Counter(d.source for d in pool)
    stats = pool_stats(pool)
    hypothetical = sources.get("synthetic", 0) > 0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": {"git": _git_hash(), "module": "tradinglab.prop_economics"},
        "program": {"id": program.program_id, "rules_version": program.rules_version,
                    "consulted_at": program.consulted_at.isoformat(), "expired": is_expired(program, today),
                    "blocking_unknowns": blocking_unknowns(program)},
        "data": {"n_days": len(pool), "sources": dict(sources), "pool_hash": pool_hash(pool),
                 "first_day": min(d.session_date for d in pool).isoformat(),
                 "last_day": max(d.session_date for d in pool).isoformat(), "hypothetical": hypothetical,
                 "stats_per_trade": stats},
        "config": {"contracts_eval": cfg.contracts_eval, "contracts_funded": cfg.contracts_funded,
                   "budget": cfg.budget, "start_date": cfg.start_date.isoformat(), "policy": cfg.policy,
                   "policy_arg": cfg.policy_arg, "payout_fee": cfg.payout_fee,
                   "assume_processing_days": cfg.assume_processing_days, "assume": dict(cfg.assume),
                   "n_paths": n_paths, "seed": seed},
        "formulas": FORMULAS,
        "limitations": LIMITS + (["POOL SINTÉTICO: ventaja hipotética, no medida"] if hypothetical else []),
        "confidence": "baja (ventaja hipotética)" if hypothetical else "según la muestra del pool (ver stats)",
        "horizons": result["horizons"],
        **(extra or {}),
    }


def to_markdown(rep: dict) -> str:
    lines = [f"# Motor EV · {rep['program']['id']} ({rep['program']['rules_version']})", ""]
    if rep["data"]["hypothetical"]:
        lines += ["> **HIPOTÉTICO:** el pool es sintético; la ventaja no está medida. No es una recomendación.", ""]
    if rep["program"]["expired"]:
        lines += ["> **REGLAS CADUCADAS:** volver a verificar el programa antes de usar estas cifras.", ""]
    lines += [
        f"- Generado: {rep['generated_at']} · código `{rep['code']['git']}`",
        f"- Datos: {rep['data']['n_days']} días ({rep['data']['first_day']} → {rep['data']['last_day']}), fuentes "
        f"{rep['data']['sources']}, hash `{rep['data']['pool_hash']}`",
        f"- Por operación y contrato: neta {rep['data']['stats_per_trade']['mean_net']:.2f} USD, bruta "
        f"{rep['data']['stats_per_trade']['mean_gross']:.2f}, coste {rep['data']['stats_per_trade']['mean_cost']:.2f}",
        f"- Configuración: {json.dumps(rep['config'], ensure_ascii=False)}",
        f"- Incógnitas del programa: {rep['program']['blocking_unknowns'] or 'ninguna'}",
        "",
        "| Horizonte (días) | EV ± EE | Mediana | P5 | P95 | P(neto > 0) | P(≥ 1 payout) | Tarifas | Cuentas | Ruina |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for h, m in sorted(rep["horizons"].items(), key=lambda kv: int(kv[0])):
        lines.append(f"| {h} | {m['ev']:.0f} ± {m['se']:.0f} | {m['median']:.0f} | {m['p5']:.0f} | {m['p95']:.0f} | "
                     f"{m['p_net_pos']:.2f} | {m['p_one_payout_received']:.2f} | {m['fees']:.0f} | "
                     f"{m['accounts_bought']:.1f} | {m['p_ruin']:.3f} |")
    lines += ["", "**Fórmulas:**", *[f"- {f}" for f in rep["formulas"]], "",
              "**Limitaciones:**", *[f"- {f}" for f in rep["limitations"]], "",
              f"**Confianza:** {rep['confidence']}", ""]
    if "mu_star" in rep:
        ms = rep["mu_star"]
        lines += [f"**Ventaja mínima rentable μ\\*:** {ms.get('mu_star_usd')} USD/operación/contrato "
                  f"({ms.get('mu_star_r')} R); monotonía: {ms.get('monotone')}", ""]
    return "\n".join(lines)
