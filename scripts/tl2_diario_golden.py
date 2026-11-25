r"""TL2-DIARIO · salida de referencia (golden) de los modos balance/equity.

Genera `tests/data/prop_daily_golden.json` con el codigo **anterior** a la
correccion del suelo diario `higher_of_balance_or_equity`. Solo usa los modos
`balance` y `equity`: sus resultados deben quedar identicos bit a bit tras el
cambio (test de identidad de P4).

Uso:  .\.venv\Scripts\python.exe scripts\tl2_diario_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tradinglab.prop.rules import PropRules, from_yaml
from tradinglab.prop.simulator import monte_carlo, monte_carlo_program

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "data" / "prop_daily_golden.json"

SEED = 42
N_PATHS = 2_000
DAYS = 20_000
RISKS = [0.0025, 0.005, 0.01]
HORIZON_MC = 60
HORIZON_PROGRAM = 180


def zero_edge_returns(b: int, risk: float) -> np.ndarray:
    """Retornos sinteticos de D2: p = 1/(1+b), +b R con p y -1 R si no."""
    rng = np.random.default_rng(SEED)
    p = 1.0 / (1.0 + b)
    wins = rng.random(DAYS) < p
    return np.where(wins, b, -1.0) * risk


def synthetic_equity_returns() -> np.ndarray:
    """Serie determinista con dias planos, verdes y rojos (sin RNG)."""
    pattern = [0.004, -0.006, 0.002, -0.003, 0.005, -0.001, 0.0, -0.004, 0.003, -0.002]
    return np.asarray(pattern * 9, dtype=float)


def _ftmo_1step() -> PropRules:
    return PropRules(
        firm="FTMO", program="1-step", phase="challenge", account_size=100_000,
        profit_target_pct=0.10, max_daily_loss_pct=0.03, max_loss_pct=0.10,
        max_loss_mode="static", daily_loss_mode="equity",
        min_trading_days=0, max_days=None, buffer_pct=0.10,
    )


def _equity_synthetic() -> PropRules:
    return PropRules(
        firm="Synthetic", program="1-step", phase="challenge", account_size=100_000,
        profit_target_pct=0.10, max_daily_loss_pct=0.03, max_loss_pct=0.10,
        max_loss_mode="static", daily_loss_mode="equity",
        min_trading_days=0, max_days=None, buffer_pct=0.0,
    )


def _canonical(value):
    return json.loads(json.dumps(value, sort_keys=True))


def build_cases() -> list[dict]:
    ftmo_challenge = from_yaml("ftmo", "challenge", 100_000)
    ftmo_verification = from_yaml("ftmo", "verification", 100_000)
    ftmo_program = [ftmo_challenge, ftmo_verification]
    b2_risk05 = zero_edge_returns(2, 0.005)
    one = _ftmo_1step()
    synthetic = _equity_synthetic()
    synthetic_returns = synthetic_equity_returns()

    cases: list[dict] = [
        {
            "name": "ftmo_2step_monte_carlo",
            "function": "monte_carlo",
            "rules": [ftmo_challenge],
            "returns": b2_risk05,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_MC, "seed": SEED},
        },
        {
            "name": "ftmo_2step_program",
            "function": "monte_carlo_program",
            "rules": ftmo_program,
            "returns": b2_risk05,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_PROGRAM, "seed": SEED},
        },
        {
            "name": "ftmo_1step_monte_carlo",
            "function": "monte_carlo",
            "rules": [one],
            "returns": b2_risk05,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_MC, "seed": SEED},
        },
        {
            "name": "ftmo_1step_program",
            "function": "monte_carlo_program",
            "rules": [one],
            "returns": b2_risk05,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_PROGRAM, "seed": SEED},
        },
        {
            "name": "equity_synthetic_monte_carlo",
            "function": "monte_carlo",
            "rules": [synthetic],
            "returns": synthetic_returns,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_MC, "seed": SEED},
        },
        {
            "name": "equity_synthetic_program",
            "function": "monte_carlo_program",
            "rules": [synthetic],
            "returns": synthetic_returns,
            "kwargs": {"n_paths": N_PATHS, "horizon": HORIZON_PROGRAM, "seed": SEED},
        },
    ]

    for b in (1, 2, 3):
        for risk in RISKS:
            cases.append(
                {
                    "name": f"ftmo_2step_b{b}_r{int(risk * 10_000)}",
                    "function": "monte_carlo_program",
                    "rules": ftmo_program,
                    "returns": zero_edge_returns(b, risk),
                    "kwargs": {
                        "n_paths": N_PATHS,
                        "horizon": HORIZON_PROGRAM,
                        "seed": SEED,
                    },
                }
            )
    return cases


def run_case(case: dict) -> dict:
    rules = case["rules"]
    func = monte_carlo if case["function"] == "monte_carlo" else monte_carlo_program
    target = rules[0] if len(rules) == 1 and func is monte_carlo else rules
    result = func(target, case["returns"], **case["kwargs"])
    return _canonical(result)


def build_payload() -> dict:
    cases = build_cases()
    out = []
    for case in cases:
        out.append(
            {
                "name": case["name"],
                "function": case["function"],
                "rules": [rules.describe() for rules in case["rules"]],
                "kwargs": case["kwargs"],
                "result": run_case(case),
            }
        )
    return {
        "note": (
            "Golden de TL2-DIARIO generado con el codigo anterior a la correccion. "
            "Solo modos balance/equity: deben ser identicos bit a bit tras el cambio."
        ),
        "return_sets": {
            "zero_edge_b2_r50": {
                "kind": "zero_edge",
                "b": 2,
                "risk": 0.005,
                "days": DAYS,
                "seed": SEED,
            },
            "synthetic_equity": {"kind": "synthetic_equity", "days": 90},
        },
        "cases": out,
    }


def main() -> None:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    GOLDEN.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"escrito {GOLDEN.relative_to(ROOT)} con {len(payload['cases'])} casos")


if __name__ == "__main__":
    main()
