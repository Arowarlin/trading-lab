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
from tradinglab.f13 import config_check, config_hash, freeze
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
    assert {"paper_main", "alpaca_paper", "ftmo_demo", "topstep_template"} <= set(accounts)
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
        account_id="paper_main",
        changes={"per_trade_risk_pct": 0.005},
        accounts=accounts,
        now=now,
    )
    assert result["ok"] is True
    assert own_limits(db, accounts["paper_main"], now=now).per_trade_risk_pct == pytest.approx(0.005)

    denied = set_limits(
        db,
        account_id="paper_main",
        changes={"max_trades_per_day": 8},
        accounts=accounts,
        now=now,
    )
    assert denied["ok"] is False
    assert "confirmación" in denied["errors"][0]

    accepted = set_limits(
        db,
        account_id="paper_main",
        changes={"max_trades_per_day": 8},
        confirm=True,
        accounts=accounts,
        now=now,
    )
    assert accepted["ok"] is True
    assert accepted["pending"] is True
    assert own_limits(db, accounts["paper_main"], now=now).max_trades_per_day == 5
    later = now + timedelta(days=2)
    assert own_limits(db, accounts["paper_main"], now=later).max_trades_per_day == 8
    assert history(db, "paper_main")


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


def test_f13_congelado_solo_aprieta(tmp_path):
    accounts = load_accounts()
    db = tmp_path / "lab.db"
    root = tmp_path / "repo"
    root.mkdir()
    (root / "config").mkdir()
    freeze(db, bot="qqq-trend-f13", symbol="QQQ", start_date="2026-11-09", root=root)

    loosen = set_limits(
        db,
        account_id="paper_main",
        changes={"daily_loss_pct": 0.06},
        accounts=accounts,
        confirm=True,
    )
    assert loosen["ok"] is False
    assert "solo se permite apretar" in loosen["errors"][0]
    tighten = set_limits(
        db,
        account_id="paper_main",
        changes={"daily_loss_pct": 0.03},
        accounts=accounts,
    )
    assert tighten["ok"] is True


def test_editar_limites_no_cambia_hash_f13(tmp_path):
    db = tmp_path / "lab.db"
    before = config_check(db)
    set_limits(
        db,
        account_id="paper_main",
        changes={"daily_loss_pct": 0.04},
        accounts=load_accounts(),
    )
    after = config_check(db)
    assert after["status"] == "not_started"
    assert after["current"] == before["current"] == config_hash()


def test_tres_bots_misma_cuenta_y_dos_cuentas(tmp_path):
    accounts = load_accounts()
    paper_limits = effective_limits(tmp_path / "paper.db", accounts["paper_main"])
    alpaca_limits = effective_limits(tmp_path / "alpaca.db", accounts["alpaca_paper"])
    state = _state(open_risk_usd=0)
    open_risk = 0.0
    results = []
    for risk in (700.0, 700.0, 700.0):
        report = evaluate_account(
            from_yaml("ftmo", "challenge", 100_000),
            _state(open_risk_usd=open_risk),
            limits=paper_limits,
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
        limits=alpaca_limits,
        proposed_risk_usd=600,
    )
    assert strict.allowed is False
    assert loose.allowed is True
