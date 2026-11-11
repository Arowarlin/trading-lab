from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.prop import AccountState, PropGuard, monte_carlo
from tradinglab.prop.rules import from_yaml, ftmo


def state(equity: float = 100_000.0, **kw) -> AccountState:
    base = dict(
        balance=equity,
        equity=equity,
        initial_balance=100_000.0,
        day_start_balance=100_000.0,
        day_start_equity=100_000.0,
        peak_balance=100_000.0,
        peak_equity=100_000.0,
    )
    base.update(kw)
    return AccountState(**base)


def test_ftmo_presets():
    c = ftmo(100_000, "challenge")
    v = ftmo(100_000, "verification")
    f = ftmo(100_000, "funded")
    assert c.profit_target_usd == pytest.approx(10_000)
    assert v.profit_target_usd == pytest.approx(5_000)
    assert f.profit_target_usd == 0
    assert c.daily_limit_usd == pytest.approx(5_000)
    assert c.max_loss_usd == pytest.approx(10_000)


def test_floors_with_buffer():
    rules = ftmo(100_000, buffer_pct=0.10)
    guard = PropGuard(rules)
    daily, maximum = guard.floors(state())
    assert daily == pytest.approx(100_000 - 5_000 * 0.9)
    assert maximum == pytest.approx(100_000 - 10_000 * 0.9)
    assert max(daily, maximum) == pytest.approx(95_500)


def test_no_buffer_uses_full_limit():
    rules = ftmo(100_000, buffer_pct=0.0)
    daily, maximum = PropGuard(rules).floors(state())
    assert daily == pytest.approx(95_000)
    assert maximum == pytest.approx(90_000)


def test_allows_inside_rules_and_blocks_breach():
    rules = ftmo(100_000)
    guard = PropGuard(rules)
    ok = guard.evaluate(state(96_000))
    assert ok.allowed and not ok.breached

    bad = guard.evaluate(state(95_000))
    assert not bad.allowed
    assert bad.breached


def test_trailing_eod_moves_the_floor():
    rules = ftmo(100_000, max_loss_mode="trailing_eod")
    guard = PropGuard(rules)
    st = state(105_000, peak_balance=110_000, day_start_equity=105_000)
    report = guard.evaluate(st)
    # 110.000 - 9.000 = 101.000 -> 105.000 está por encima, pero el suelo subió
    assert report.max_floor == pytest.approx(101_000)
    assert report.allowed

    st2 = state(100_500, peak_balance=110_000, day_start_equity=105_000)
    assert guard.evaluate(st2).breached


def test_daily_usage_uses_the_configured_base():
    rules = ftmo(100_000, daily_loss_mode="balance")
    st = state(
        98_000,
        day_start_balance=100_000,
        day_start_equity=99_000,
        peak_equity=100_000,
    )
    report = PropGuard(rules).evaluate(st)
    # base = balance (100k), límite real 5k -> 2k usados = 40%
    assert report.daily_used_pct == pytest.approx(2_000 / 5_000)


def test_max_usage_uses_the_trailing_peak():
    rules = ftmo(100_000, max_loss_mode="trailing_eod")
    st = state(105_000, peak_balance=110_000, day_start_equity=105_000)
    report = PropGuard(rules).evaluate(st)
    # base = pico 110k, límite real 10k -> 5k usados = 50% (no negativo)
    assert report.max_used_pct == pytest.approx(5_000 / 10_000)


def test_target_reached_blocks_new_risk():
    rules = ftmo(100_000)
    report = PropGuard(rules).evaluate(state(110_000))
    assert report.target_reached
    assert not report.allowed
    assert "objetivo" in report.reason


def test_closing_is_allowed_even_at_floor():
    rules = ftmo(100_000)
    report = PropGuard(rules).evaluate(state(95_000), closing=True)
    assert report.allowed
    assert report.severity == "ok"


def test_order_risk_cannot_exceed_remaining_buffer():
    rules = ftmo(100_000)
    guard = PropGuard(rules)
    st = state(96_000, open_lots=0.1)
    report = guard.evaluate(st, proposed_lots=2.0, risk_per_lot=1_000)
    assert not report.allowed
    assert "colchón" in report.reason


def test_max_lots_blocks():
    rules = ftmo(100_000, max_lots=5)
    report = PropGuard(rules).evaluate(
        state(100_000, open_lots=4.5), proposed_lots=1.0, risk_per_lot=10
    )
    assert not report.allowed
    assert "lotes" in report.reason


def test_el_riesgo_de_otro_simbolo_no_se_multiplica_por_este_lote():
    """2,04 lotes de EURUSD no valen el riesgo/lote del oro (bug de agregación)."""
    rules = ftmo(100_000, max_open_risk_pct=0.02)  # tope 2 % -> 2.000 USD
    guard = PropGuard(rules)
    st = state(100_000, open_lots=2.04)
    # sin open_risk_usd: (2,04 + 0,07) x 6.628 = 13.985 -> bloquea
    blocked = guard.evaluate(st, proposed_lots=0.07, risk_per_lot=6_628.14)
    assert not blocked.allowed
    assert "riesgo abierto" in blocked.reason
    # con el riesgo real del símbolo (500 EURUSD + 464 oro) -> permite
    allowed = guard.evaluate(
        st,
        proposed_lots=0.07,
        risk_per_lot=6_628.14,
        open_risk_usd=500.0,
    )
    assert allowed.allowed


def test_el_riesgo_abierto_en_usd_respeta_el_tope():
    rules = ftmo(100_000, max_open_risk_pct=0.02)
    report = PropGuard(rules).evaluate(
        state(100_000, open_lots=2.04),
        proposed_lots=0.07,
        risk_per_lot=6_628.14,
        open_risk_usd=1_800.0,
    )
    assert not report.allowed
    assert "riesgo abierto" in report.reason


def test_consistency_is_a_warning_not_a_block():
    rules = ftmo(100_000, consistency_pct=0.5)
    st = state(105_000, closed_pnl_today=6_000, total_profit=10_000)
    report = PropGuard(rules).evaluate(st)
    assert report.allowed
    assert report.consistency_ok is False
    assert report.severity == "warn"


def test_rules_load_from_yaml():
    c = from_yaml("ftmo", "challenge", 100_000)
    v = from_yaml("ftmo", "verification", 100_000)
    assert c.profit_target_pct == pytest.approx(0.10)
    assert v.profit_target_pct == pytest.approx(0.05)
    assert c.max_daily_loss_pct == pytest.approx(0.05)
    assert c.reset_tz == "Europe/Prague"


def test_topstep_50k_preset_es_plantilla_inactiva():
    t = from_yaml("topstep", "challenge", 50_000)
    assert t.profit_target_pct == pytest.approx(0.06)
    assert t.max_loss_pct == pytest.approx(0.04)
    assert t.max_loss_mode == "trailing_eod"
    assert t.reset_tz == "America/Chicago"
    assert t.weekend_holding is False
    assert "PLANTILLA" in t.notes
    # La firma activa sigue siendo FTMO: añadir el preset no la cambia.
    assert from_yaml("ftmo", "challenge", 100_000).firm == "FTMO"


def test_plantillas_apex_lucid_y_myfundedfutures_inactivas():
    apex = from_yaml("apex", "challenge", 50_000)
    assert apex.template is True
    assert apex.enabled is False
    assert apex.automation_allowed is False
    assert "automatizados" in apex.automation_note.lower()
    assert "bots/ea" in apex.automation_note.lower()
    assert "automatización prohibida" in apex.describe()

    for firm in ("lucid", "myfundedfutures"):
        rules = from_yaml(firm, "challenge", 50_000)
        assert rules.template is True
        assert rules.enabled is False
        assert rules.automation_allowed is None
        assert "no verificada" in rules.automation_note.lower()
        assert rules.profit_target_pct == pytest.approx(0.06)

    # La firma activa sigue intacta.
    ftmo = from_yaml("ftmo", "challenge", 100_000)
    assert ftmo.template is False
    assert ftmo.enabled is True
    assert ftmo.automation_allowed is None


def test_state_from_equity_splits_by_reset_timezone():
    idx = pd.to_datetime(
        ["2026-11-03 23:00", "2026-11-04 01:00", "2026-11-04 12:00", "2026-11-05 01:00"]
    ).tz_localize("UTC")
    eq = pd.Series([100_000, 101_000, 102_000, 99_000], index=idx)
    rules = ftmo(100_000)
    st = PropGuard.state_from_equity(rules, eq, initial_balance=100_000)
    # 2026-11-05 01:00 UTC = 02:00 en Praga -> el día empieza en 99.000
    assert st.day_start_equity == pytest.approx(99_000)
    assert st.peak_equity == pytest.approx(102_000)
    assert st.trading_days == 2


def test_monte_carlo_positive_drift_passes():
    rules = ftmo(100_000)
    result = monte_carlo(rules, [0.005] * 250, n_paths=500, horizon=60, seed=1)
    assert result["pass_rate"] == pytest.approx(1.0)
    assert result["breach_rate"] == pytest.approx(0.0)
    assert result["median_days_to_pass"] is not None


def test_monte_carlo_negative_drift_breaches():
    rules = ftmo(100_000)
    result = monte_carlo(rules, [-0.01] * 250, n_paths=500, horizon=60, seed=1)
    assert result["pass_rate"] == pytest.approx(0.0)
    assert result["breach_rate"] == pytest.approx(1.0)


def test_monte_carlo_is_deterministic():
    rules = ftmo(100_000)
    import random

    rets = [random.Random(7).gauss(0.0005, 0.01) for _ in range(300)]
    a = monte_carlo(rules, rets, n_paths=300, horizon=60, seed=42)
    b = monte_carlo(rules, rets, n_paths=300, horizon=60, seed=42)
    assert a["pass_rate"] == b["pass_rate"]
    assert a["breach_rate"] == b["breach_rate"]
