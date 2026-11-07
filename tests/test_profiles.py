from __future__ import annotations

from datetime import datetime, timezone

from tradinglab.orchestrator import BotSpec, run_all
from tradinglab.profiles import load_profiles
from tradinglab.prop.guard import AccountSnapshot, evaluate_account
from tradinglab.prop.rules import ftmo


def test_profiles_definidos_y_bots_con_perfil():
    profiles = load_profiles()
    assert set(profiles) == {"swing_equity", "intraday_fx", "intraday_futures"}
    assert profiles["swing_equity"].timeframe == "1d"
    assert profiles["intraday_fx"].timeframe == "M15"
    assert profiles["intraday_fx"].max_risk_pct == 0.0025
    assert profiles["intraday_futures"].validation.min_trades == 80
    from tradinglab.orchestrator import load_bots

    assert all(spec.profile for spec in load_bots())


def test_schedule_bloquea_fin_de_semana_y_permite_lunes():
    profile = load_profiles()["swing_equity"]
    saturday = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
    assert not profile.schedule.allows(saturday)
    assert profile.schedule.allows(monday)


def test_bot_sin_perfil_no_se_ejecuta(monkeypatch):
    specs = [
        BotSpec(id="sin-perfil", type="deterministic", strategy="trend", universe=["QQQ"]),
        BotSpec(
            id="con-perfil",
            type="deterministic",
            strategy="trend",
            universe=["QQQ"],
            profile="swing_equity",
        ),
    ]
    executed: list[str] = []
    monkeypatch.setattr("tradinglab.orchestrator.load_bots", lambda: specs)
    monkeypatch.setattr(
        "tradinglab.orchestrator.run_bot",
        lambda spec, *a, **k: executed.append(spec.id) or [],
    )
    run_all(
        type("S", (), {"risk": None})(),
        object(),
        include_disabled=True,
        now=datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc),
    )
    assert executed == ["con-perfil"]


def test_guard_cuenta_suma_tres_bots_y_permite_cerrar():
    rules = ftmo(100_000, max_open_risk_pct=0.02)
    state = AccountSnapshot(
        equity=100_000,
        day_start_equity=100_000,
        initial_balance=100_000,
        peak_equity=100_000,
        open_risk_usd=0.0,
        open_positions=0,
    )
    open_risk = 0.0
    results = []
    for risk in (700.0, 700.0, 700.0):
        report = evaluate_account(
            rules,
            AccountSnapshot(
                equity=state.equity,
                day_start_equity=state.day_start_equity,
                initial_balance=state.initial_balance,
                peak_equity=state.peak_equity,
                open_risk_usd=open_risk,
                open_positions=0,
            ),
            max_risk_pct=0.01,
            max_trades_per_day=3,
            proposed_risk_usd=risk,
        )
        results.append(report.allowed)
        if report.allowed:
            open_risk += risk
    assert results == [True, True, False]  # 2.100 > 2.000 (2% de 100k)
    assert evaluate_account(rules, state, proposed_risk_usd=999, closing=True).allowed
    assert not evaluate_account(
        rules,
        AccountSnapshot(
            equity=100_000,
            day_start_equity=100_000,
            initial_balance=100_000,
            peak_equity=100_000,
            trades_today=1,
        ),
        max_trades_per_day=1,
        proposed_risk_usd=100,
    ).allowed
