from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.prop.defense import (
    DailyCircuitBreaker,
    DefenseError,
    EquityDefense,
    FlattenClock,
    TrailingDrawdown,
)

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)  # 15:00 ET
FLAT = datetime(2026, 11, 10, 21, 5, tzinfo=timezone.utc)  # 16:05 ET
TOMORROW = NOW + timedelta(days=1)
NEXT_FLAT = FLAT + timedelta(days=1)


# ------------------------------------------------------------ trailing drawdown


def test_hwm_solo_sube():
    dd = TrailingDrawdown(0.05, start_equity=100_000)
    report = dd.observe(101_000)
    assert report.hwm == pytest.approx(101_000)
    assert report.drawdown_pct == pytest.approx(0.0)

    report = dd.observe(99_000)
    assert report.hwm == pytest.approx(101_000)
    assert report.drawdown_pct == pytest.approx(2_000 / 101_000)
    assert dd.hwm == pytest.approx(101_000)
    assert dd.floor() == pytest.approx(101_000 * 0.95)


def test_zonas_y_factor_de_tamano():
    dd = TrailingDrawdown(0.05, start_equity=100_000)

    assert dd.observe(100_000).level == "ok"
    assert dd.observe(100_000).size_factor == 1.0

    caution = dd.observe(96_500)  # 3,5% = 70% del límite
    assert caution.level == "caution"
    assert caution.size_factor == 0.75
    assert caution.allowed

    alert = dd.observe(95_750)  # 4,25% = 85%
    assert alert.level == "alert"
    assert alert.size_factor == 0.50

    critical = dd.observe(95_250)  # 4,75% = 95%
    assert critical.level == "critical"
    assert critical.size_factor == 0.25
    assert critical.allowed

    breach = dd.observe(95_000)
    assert breach.level == "breach"
    assert breach.size_factor == 0.0
    assert not breach.allowed
    assert "límite" in breach.reason


def test_drawdown_reporta_aviso_en_zona():
    dd = TrailingDrawdown(0.05, start_equity=100_000)
    report = dd.observe(96_500)
    assert report.warnings
    assert "70%" in report.warnings[0]


def test_configuracion_invalida():
    with pytest.raises(DefenseError):
        TrailingDrawdown(0.0)
    with pytest.raises(DefenseError):
        TrailingDrawdown(1.0)
    with pytest.raises(DefenseError):
        TrailingDrawdown(0.05, start_equity=0)


# ------------------------------------------------------------ circuit breaker


def test_racha_de_perdidas_dispara_el_breaker():
    breaker = DailyCircuitBreaker(max_consecutive_losses=3, day_start_equity=100_000)
    for pnl in (-100.0, -100.0):
        report = breaker.record_trade(pnl, now=NOW)
        assert not report.tripped
    report = breaker.record_trade(-90.0, now=NOW)
    assert report.tripped
    assert report.consecutive_losses == 3
    assert "pérdidas seguidas" in report.reason


def test_una_ganancia_corta_la_racha():
    breaker = DailyCircuitBreaker(max_consecutive_losses=3, day_start_equity=100_000)
    breaker.record_trade(-100.0, now=NOW)
    breaker.record_trade(-100.0, now=NOW)
    breaker.record_trade(250.0, now=NOW)
    report = breaker.record_trade(-100.0, now=NOW)
    assert report.consecutive_losses == 1
    assert not report.tripped


def test_perdida_diaria_latchea_aunque_el_equity_se_recupere():
    breaker = DailyCircuitBreaker(max_daily_loss_pct=0.03, day_start_equity=100_000)
    report = breaker.record_trade(-3_100.0, now=NOW)
    assert report.tripped
    assert report.daily_loss_pct == pytest.approx(0.031)

    later = breaker.observe(100_000.0, now=NOW)
    assert later.tripped
    assert later.reason.startswith("pérdida diaria")


def test_perdida_diaria_por_equity_dispara_sin_trades():
    breaker = DailyCircuitBreaker(max_daily_loss_pct=0.03, day_start_equity=100_000)
    report = breaker.observe(96_000.0, now=NOW)
    assert report.tripped
    assert report.daily_loss_pct == pytest.approx(0.04)
    assert report.consecutive_losses == 0
    assert "pérdida diaria" in report.reason


def test_el_breaker_se_rearma_al_dia_siguiente():
    breaker = DailyCircuitBreaker(max_consecutive_losses=1, day_start_equity=100_000)
    assert breaker.record_trade(-50.0, now=NOW).tripped
    report = breaker.observe(99_950.0, now=TOMORROW)
    assert not report.tripped
    assert report.day == TOMORROW.date()


def test_reset_limpia_el_latch():
    breaker = DailyCircuitBreaker(max_consecutive_losses=1, day_start_equity=100_000)
    breaker.record_trade(-50.0, now=NOW)
    breaker.reset(day_start_equity=99_950.0)
    assert not breaker.observe(99_950.0, now=NOW).tripped


def test_breaker_configuracion_invalida():
    with pytest.raises(DefenseError):
        DailyCircuitBreaker(max_daily_loss_pct=0.0)
    with pytest.raises(DefenseError):
        DailyCircuitBreaker(max_consecutive_losses=0)


# --------------------------------------------------------------- flatten clock


def test_reloj_no_dispara_antes_de_la_hora():
    clock = FlattenClock("15:55", tz="America/New_York")
    assert not clock.due(NOW)


def test_reloj_dispara_una_vez_por_sesion():
    clock = FlattenClock("15:55", tz="America/New_York")
    assert clock.due(FLAT)
    assert clock.due(FLAT)  # sigue pendiente hasta confirmar
    clock.ack(FLAT)
    assert not clock.due(FLAT)
    clock.ack(FLAT)  # confirmar dos veces es inocuo
    assert clock.fired_on == FLAT.date()

    assert clock.due(NEXT_FLAT)


def test_reloj_ignora_fin_de_semana():
    clock = FlattenClock("15:55", tz="America/New_York")
    saturday = datetime(2026, 11, 14, 21, 5, tzinfo=timezone.utc)
    assert not clock.due(saturday)


# -------------------------------------------------------------------- facade


def test_facade_permite_y_reduce_por_zona():
    defense = EquityDefense(start_equity=100_000, max_daily_loss_pct=0.10)
    ok = defense.evaluate(100_000, NOW)
    assert ok.allowed and ok.size_factor == 1.0

    reduced = defense.evaluate(96_500, NOW)
    assert reduced.allowed
    assert reduced.size_factor == 0.75
    assert reduced.drawdown.level == "caution"


def test_facade_bloquea_en_breach():
    defense = EquityDefense(start_equity=100_000)
    report = defense.evaluate(95_000, NOW)
    assert not report.allowed
    assert report.size_factor == 0.0
    assert report.drawdown.level == "breach"


def test_facade_bloquea_si_el_breaker_esta_disparado():
    defense = EquityDefense(start_equity=100_000, max_consecutive_losses=2)
    defense.record_trade(-100.0, now=NOW)
    defense.record_trade(-100.0, now=NOW)
    report = defense.evaluate(99_800, NOW)
    assert not report.allowed
    assert report.breaker.tripped


def test_facade_bloquea_entradas_pasada_la_hora_de_cierre():
    defense = EquityDefense(start_equity=100_000)
    report = defense.evaluate(100_000, FLAT)
    assert not report.allowed
    assert report.flatten_due

    defense.ack_flatten(FLAT)
    assert defense.evaluate(100_000, FLAT).allowed


# ----------------------------------------------------------------------- CLI


def test_cli_defense_muestra_zona_y_factor():
    result = CliRunner().invoke(
        cli_mod.app, ["prop", "defense", "--equity", "93600"]
    )
    assert result.exit_code == 0
    assert "caution" in result.output
    assert "0.75x" in result.output
    assert "Motivo" in result.output


def test_cli_defense_bloquea_en_breach():
    result = CliRunner().invoke(
        cli_mod.app, ["prop", "defense", "--equity", "90900"]
    )
    assert result.exit_code == 0
    assert "breach" in result.output
    assert "bloqueadas" in result.output
