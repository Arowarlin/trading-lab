"""TL2-DIARIO · regresion del suelo diario higher_of_balance_or_equity.

- Identidad bit a bit de los modos `balance`/`equity` contra el golden
  generado con el codigo anterior (`tests/data/prop_daily_golden.json`).
- El camino de P1.3 (-0,25 % diario durante 30 dias) ya no rompe.
- Un dia de -5,1 % rompe ese mismo dia.
- `guard` usa max(balance, equidad) al inicio del dia.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from tradinglab.prop.guard import AccountState, PropGuard
from tradinglab.prop.rules import PropRules
from tradinglab.prop.simulator import monte_carlo, monte_carlo_program

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tl2_diario_golden as golden  # noqa: E402

GOLDEN = ROOT / "tests" / "data" / "prop_daily_golden.json"


def _fundingpips(**overrides) -> PropRules:
    base = dict(
        firm="FundingPips",
        program="2-step",
        phase="challenge",
        account_size=100_000.0,
        profit_target_pct=0.08,
        max_daily_loss_pct=0.05,
        max_loss_pct=0.10,
        max_loss_mode="static",
        daily_loss_mode="higher_of_balance_or_equity",
        min_trading_days=0,
        max_days=None,
        buffer_pct=0.0,
    )
    base.update(overrides)
    return PropRules(**base)


def _state(**overrides) -> AccountState:
    base = dict(
        balance=99_500.0,
        equity=99_500.0,
        initial_balance=100_000.0,
        day_start_balance=100_000.0,
        day_start_equity=98_000.0,
        peak_balance=100_000.0,
        peak_equity=100_000.0,
    )
    base.update(overrides)
    return AccountState(**base)


def test_identidad_balance_equity_contra_golden():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    generated = {case["name"]: case for case in golden.build_cases()}
    assert len(data["cases"]) == len(generated) == 15
    for expected in data["cases"]:
        case = generated[expected["name"]]
        assert case["function"] == expected["function"]
        assert case["kwargs"] == expected["kwargs"]
        assert golden.run_case(case) == expected["result"], expected["name"]


def test_camino_de_p1_no_rompe_en_30_dias():
    rules = _fundingpips()
    path = np.full(30, -0.0025)

    one = monte_carlo(rules, path, n_paths=10, horizon=30, seed=42)
    assert one["breach_rate"] == 0.0
    assert one["pass_rate"] == 0.0

    program = monte_carlo_program([rules], path, n_paths=10, horizon=30, seed=42)
    assert program["breach_rate"] == 0.0


def test_un_dia_de_menos_51_rompe_ese_dia():
    rules = _fundingpips()

    just_under = monte_carlo(
        rules, np.array([-0.049]), n_paths=10, horizon=1, seed=42
    )
    assert just_under["breach_rate"] == 0.0

    breaks = monte_carlo(
        rules, np.array([-0.051]), n_paths=10, horizon=1, seed=42
    )
    assert breaks["breach_rate"] == 1.0


def test_guard_usa_el_mayor_de_balance_o_equidad():
    rules = _fundingpips()
    guard = PropGuard(rules)
    daily, maximum = guard.floors(_state())
    # max(100.000, 98.000) - 5.000 = 95.000, no 93.000.
    assert daily == pytest.approx(95_000.0)
    assert maximum == pytest.approx(90_000.0)


def test_guard_equity_sigue_usando_solo_la_equidad():
    rules = _fundingpips(daily_loss_mode="equity")
    daily, _ = PropGuard(rules).floors(_state())
    assert daily == pytest.approx(93_000.0)


def test_guard_higher_of_usa_el_disponible_si_falta_uno():
    rules = _fundingpips()
    guard = PropGuard(rules)

    only_equity = guard.floors(_state(day_start_balance=None))[0]
    assert only_equity == pytest.approx(93_000.0)

    only_balance = guard.floors(_state(day_start_equity=None))[0]
    assert only_balance == pytest.approx(95_000.0)
