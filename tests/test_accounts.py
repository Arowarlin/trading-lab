from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradinglab.accounts import (
    effective_limits,
    firm_limits,
    history,
    load_accounts,
    own_limits,
    set_limits,
)
from tradinglab.prop.guard import AccountLimits, AccountSnapshot, evaluate_account
from tradinglab.prop.rules import from_yaml


def _state(**kwargs) -> AccountSnapshot:
    base = dict(
        equity=100_000,
        day_start_equity=100_000,
        initial_balance=100_000,
        peak_equity=100_000,
    )
    base.update(kwargs)
    return AccountSnapshot(**base)


def test_cuentas_y_limites_efectivos(tmp_path):
    accounts = load_accounts()
    assert {"ftmo_demo", "ftmo_trial_ea", "topstep_template"} <= set(accounts)
    assert "paper_main" not in accounts and "alpaca_paper" not in accounts
    ftmo = accounts["ftmo_demo"]
    assert ftmo.type == "fondeo"
    assert firm_limits(ftmo)["daily_loss_pct"] == pytest.approx(0.05)
    effective = effective_limits(tmp_path / "lab.db", ftmo)
    assert effective.daily_loss_pct == pytest.approx(0.04)
    assert effective.max_drawdown_pct == pytest.approx(0.10)
    assert effective.per_trade_risk_pct == pytest.approx(0.005)
    assert effective.max_open_risk_pct == pytest.approx(0.02)
    assert ftmo.risk_caps.symbol_pct == pytest.approx(0.02)
    assert ftmo.risk_caps.group_pct == pytest.approx(0.03)
    assert ftmo.risk_caps.total_pct == pytest.approx(0.04)
    assert ftmo.risk_caps.groups["indices_us"] == (
        "US100", "US500", "US30", "US2000"
    )
    trial = accounts["ftmo_trial_ea"]
    assert trial.risk_caps.total_pct == pytest.approx(0.04)


def test_apretar_inmediato_y_aflojar_confirmado(tmp_path):
    accounts = load_accounts()
    db = tmp_path / "lab.db"
    now = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    result = set_limits(
        db,
        account_id="ftmo_demo",
        changes={"per_trade_risk_pct": 0.002},
        accounts=accounts,
        now=now,
    )
    assert result["ok"] is True
    assert own_limits(db, accounts["ftmo_demo"], now=now).per_trade_risk_pct == pytest.approx(0.002)

    denied = set_limits(
        db,
        account_id="ftmo_demo",
        changes={"max_trades_per_day": 5},
        accounts=accounts,
        now=now,
    )
    assert denied["ok"] is False
    assert "confirmación" in denied["errors"][0]

    accepted = set_limits(
        db,
        account_id="ftmo_demo",
        changes={"per_trade_risk_pct": 0.004},
        confirm=True,
        accounts=accounts,
        now=now,
    )
    assert accepted["ok"] is True
    assert accepted["pending"] is True
    assert own_limits(db, accounts["ftmo_demo"], now=now).per_trade_risk_pct == pytest.approx(0.002)
    later = now + timedelta(days=2)
    assert own_limits(db, accounts["ftmo_demo"], now=later).per_trade_risk_pct == pytest.approx(0.004)
    assert history(db, "ftmo_demo")


def test_limite_propio_no_puede_superar_firma(tmp_path):
    accounts = load_accounts()
    result = set_limits(
        tmp_path / "lab.db",
        account_id="ftmo_demo",
        changes={"daily_loss_pct": 0.06},
        accounts=accounts,
        confirm=True,
    )
    assert result["ok"] is False
    assert "firma" in result["errors"][0]


def test_tres_bots_misma_cuenta_y_dos_cuentas(tmp_path):
    state = _state(open_risk_usd=0)
    open_risk = 0.0
    base = AccountLimits(0.05, 0.10, 0.01, 0.02, 5)
    results = []
    for risk in (700.0, 700.0, 700.0):
        report = evaluate_account(
            from_yaml("ftmo", "challenge", 100_000),
            _state(open_risk_usd=open_risk),
            limits=base,
            proposed_risk_usd=risk,
        )
        results.append(report.allowed)
        if report.allowed:
            open_risk += risk
    assert results == [True, True, False]

    # Otra cuenta con límite propio más estricto se evalúa por separado.
    strict = evaluate_account(
        from_yaml("ftmo", "challenge", 100_000),
        state,
        limits=AccountLimits(0.05, 0.10, 0.005, 0.02, 5),
        proposed_risk_usd=600,
    )
    loose = evaluate_account(
        from_yaml("ftmo", "challenge", 100_000),
        state,
        limits=base,
        proposed_risk_usd=600,
    )
    assert strict.allowed is False
    assert loose.allowed is True
