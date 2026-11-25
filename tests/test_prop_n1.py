"""N1 · Reglas oficiales y simulador de dos fases."""

from __future__ import annotations

import numpy as np

from tradinglab.prop.rules import PropRules
from tradinglab.prop.simulator import monte_carlo, monte_carlo_program


def _rules(**overrides) -> PropRules:
    base = dict(
        firm="FTMO",
        program="2-step",
        phase="challenge",
        account_size=100_000.0,
        profit_target_pct=0.10,
        max_daily_loss_pct=0.05,
        max_loss_pct=0.10,
        max_loss_mode="static",
        daily_loss_mode="equity",
        min_trading_days=0,
        max_days=None,
        buffer_pct=0.0,
    )
    base.update(overrides)
    return PropRules(**base)


def test_fundingpips_no_usa_el_balance_inicial_en_el_modelo_diario():
    max_base = _rules(
        firm="FundingPips",
        daily_loss_mode="higher_of_balance_or_equity",
    )
    equity_base = _rules(firm="FundingPips", daily_loss_mode="equity")

    # En el modelo diario no hay posiciones abiertas entre días, así que
    # balance = equidad al inicio del día (base = day_start). Dos días de
    # -3 %: el suelo del segundo día es 97k - 5k = 92k y la equidad 94,09k,
    # así que no rompe. El código anterior usaba el balance inicial (95k) y
    # marcaba rotura diaria.
    max_path = monte_carlo(max_base, [-0.03], n_paths=200, horizon=2, seed=7)
    equity_path = monte_carlo(equity_base, [-0.03], n_paths=200, horizon=2, seed=7)

    assert max_path["breach_rate"] == 0.0
    assert equity_path["breach_rate"] == 0.0


def test_verificacion_del_2step_empieza_en_el_balance_inicial():
    challenge = _rules(profit_target_pct=0.10, min_trading_days=0)
    verification = _rules(
        phase="verification",
        profit_target_pct=0.05,
        min_trading_days=0,
    )

    result = monte_carlo_program(
        [challenge, verification],
        [np.array([0.10]), np.array([0.0])],
        n_paths=100,
        horizon=5,
        seed=7,
    )

    assert result["phases"][0]["pass_rate"] == 1.0
    # La verificación empieza en 100k, no en los 110k del final del reto.
    assert result["phases"][1]["pass_rate"] == 0.0
    assert result["pass_rate"] == 0.0


def test_dias_minimos_impiden_pasar_antes_del_dia_4():
    rules = _rules(
        profit_target_pct=0.01,
        min_trading_days=4,
        max_daily_loss_pct=0.50,
        max_loss_pct=0.50,
    )

    result = monte_carlo(
        rules, [0.02], n_paths=100, horizon=6, seed=7
    )

    assert result["pass_rate"] == 1.0
    assert result["median_days_to_pass"] >= 4


def test_1step_rompe_con_3_por_cien_diario():
    one_step = _rules(
        program="1-step",
        profit_target_pct=0.10,
        max_daily_loss_pct=0.03,
        min_trading_days=0,
    )
    two_step = _rules(max_daily_loss_pct=0.05, min_trading_days=0)

    broken = monte_carlo(one_step, [-0.031], n_paths=100, horizon=2, seed=7)
    survives = monte_carlo(two_step, [-0.031], n_paths=100, horizon=2, seed=7)

    assert broken["breach_rate"] == 1.0
    assert survives["breach_rate"] == 0.0
