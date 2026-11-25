"""TL3-D · D2: línea base sin ventaja para Prop Fund."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from tradinglab.prop.rules import PropRules, from_yaml
from tradinglab.prop.simulator import monte_carlo_program

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT = Path("TL3_REPORTS/propfund_zero_edge.md")
SEED = 42
PATHS = 5000
HORIZON = 180
DAYS = 20_000
RISKS = [0.0025, 0.005, 0.01]


def _returns(b: int, risk: float):
    rng = np.random.default_rng(SEED)
    p = 1.0 / (1.0 + b)
    wins = rng.random(DAYS) < p
    values = np.where(wins, b, -1.0) * risk
    return values


def _programs():
    challenge = from_yaml("ftmo", "challenge", 100_000)
    verification = from_yaml("ftmo", "verification", 100_000)
    one = PropRules(
        firm="FTMO", program="1-step", phase="challenge", account_size=100_000,
        profit_target_pct=0.10, max_daily_loss_pct=0.03, max_loss_pct=0.10,
        max_loss_mode="static", daily_loss_mode="equity",
        min_trading_days=0, max_days=None, buffer_pct=0.10,
    )
    fp_challenge = PropRules(
        firm="FundingPips", program="2-step", phase="challenge", account_size=100_000,
        profit_target_pct=0.08, max_daily_loss_pct=0.05, max_loss_pct=0.10,
        max_loss_mode="static", daily_loss_mode="higher_of_balance_or_equity",
        min_trading_days=3, max_days=None, buffer_pct=0.10,
    )
    fp_verification = PropRules(
        firm="FundingPips", program="2-step", phase="verification", account_size=100_000,
        profit_target_pct=0.05, max_daily_loss_pct=0.05, max_loss_pct=0.10,
        max_loss_mode="static", daily_loss_mode="higher_of_balance_or_equity",
        min_trading_days=3, max_days=None, buffer_pct=0.10,
    )
    return {
        "FTMO 2-Step": [challenge, verification],
        "FTMO 1-Step": [one],
        "FundingPips 2-Step": [fp_challenge, fp_verification],
    }


def main():
    rows = []
    for name, phases in _programs().items():
        for b in (1, 2, 3):
            for risk in RISKS:
                daily = _returns(b, risk)
                result = monte_carlo_program(
                    phases, daily, n_paths=PATHS, horizon=HORIZON, seed=SEED
                )
                # Aislar el límite total y el diario para informarlos por separado.
                total_only = monte_carlo_program(
                    [
                        phase.with_phase(
                            phase.phase, max_loss_mode="static", max_daily_loss_pct=1.0
                        )
                        for phase in phases
                    ],
                    daily, n_paths=PATHS, horizon=HORIZON, seed=SEED,
                )
                daily_only = monte_carlo_program(
                    [
                        phase.with_phase(phase.phase, max_loss_pct=1.0)
                        for phase in phases
                    ],
                    daily, n_paths=PATHS, horizon=HORIZON, seed=SEED,
                )
                rows.append(
                    {
                        "program": name,
                        "b": b,
                        "risk": risk,
                        "phase_pass": [p["pass_rate"] for p in result["phases"]],
                        "funded": result["pass_rate"],
                        "breach": result["breach_rate"],
                        "daily_breach": daily_only["breach_rate"],
                        "total_breach": total_only["breach_rate"],
                        "median_days": result["median_days_to_pass"],
                    }
                )
                print(name, b, risk, "funded", round(result["pass_rate"], 4), "breach", round(result["breach_rate"], 4))

    lines = [
        "# TL3-D · D2 Línea base sin ventaja (sintética)",
        "",
        "Retornos diarios sintéticos con ventaja bruta exactamente 0:",
        "p = 1/(1+b), +b R con p y −1 R en el resto; 20.000 días de pool,",
        "5.000 caminos, 180 días por fase, semilla 42.",
        "",
        "| Programa | b | Riesgo | P(fase 1) | P(fase 2) | P(financiada) | P(romper) | P(diario) | P(total) | Días |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        phase2 = row["phase_pass"][1] if len(row["phase_pass"]) > 1 else None
        phase2_text = f"{phase2:.2%}" if phase2 is not None else "—"
        lines.append(
            f"| {row['program']} | {row['b']} | {row['risk']:.2%} | "
            f"{row['phase_pass'][0]:.2%} | {phase2_text} | "
            f"{row['funded']:.2%} | {row['breach']:.2%} | "
            f"{row['daily_breach']:.2%} | {row['total_breach']:.2%} | "
            f"{row['median_days'] or '—'} |"
        )
    lines += [
        "",
        "**EV: Sin datos.** `firms.yaml` no trae tarifa y reparto verificados; no se modela pago.",
        "Neto: **Sin datos** (no hay coste por operación en R sin suponer).",
        "",
        "Lectura: una estrategia real aporta sobre las reglas solo si su P(financiada)",
        "o EV supera esta línea base con la misma regla de riesgo.",
        "El simulador con datos diarios subestima el riesgo intradía.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-8:]))


if __name__ == "__main__":
    main()
