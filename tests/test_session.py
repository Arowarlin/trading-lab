from __future__ import annotations

from datetime import datetime, timezone

from tradinglab.prop import AccountState, PropGuard, ftmo
from tradinglab.session import flatten_required, session_block


def _rules(**overrides):
    return ftmo(100_000, **overrides)


def test_viernes_bloquea_si_no_weekend_holding():
    rules = _rules(weekend_holding=False, friday_close_utc="20:00")
    block = session_block(rules, datetime(2026, 11, 6, 20, 30, tzinfo=timezone.utc))
    assert block.blocked
    assert block.kind == "friday"

    allowed = session_block(rules, datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc))
    assert not allowed.blocked


def test_fin_de_semana():
    rules = _rules(weekend_holding=False)
    saturday = session_block(rules, datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc))
    assert saturday.blocked
    assert saturday.kind == "weekend"

    holding = _rules(weekend_holding=True)
    assert not session_block(holding, datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)).blocked


def test_viernes_corte_praga_cubre_cambio_de_hora():
    rules = _rules(
        weekend_holding=False,
        friday_cutoff_hour=20,
        reset_tz="Europe/Prague",
    )
    # Invierno (CET, UTC+1): 20:00 Praga = 19:00 UTC.
    invierno_dentro = session_block(rules, datetime(2026, 3, 27, 19, 30, tzinfo=timezone.utc))
    invierno_fuera = session_block(rules, datetime(2026, 3, 27, 18, 30, tzinfo=timezone.utc))
    assert invierno_dentro.blocked and invierno_dentro.kind == "friday"
    assert not invierno_fuera.blocked

    # Verano (CEST, UTC+2): 20:00 Praga = 18:00 UTC.
    verano_dentro = session_block(rules, datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc))
    verano_fuera = session_block(rules, datetime(2026, 4, 10, 17, 30, tzinfo=timezone.utc))
    assert verano_dentro.blocked and verano_dentro.kind == "friday"
    assert not verano_fuera.blocked


def test_sabado_local_aunque_en_utc_sea_viernes():
    rules = _rules(weekend_holding=False, friday_cutoff_hour=20, reset_tz="Europe/Prague")
    # 2026-04-10 23:30 UTC = sábado 01:30 en Praga (CEST).
    block = session_block(rules, datetime(2026, 4, 10, 23, 30, tzinfo=timezone.utc))
    assert block.blocked
    assert block.kind == "weekend"


def test_flatten_required_solo_para_fin_de_semana():
    rules = _rules(weekend_holding=False, friday_cutoff_hour=20, reset_tz="Europe/Prague")
    assert flatten_required(rules, datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc))
    assert not flatten_required(rules, datetime(2026, 4, 9, 18, 30, tzinfo=timezone.utc))
    holding = _rules(weekend_holding=True)
    assert not flatten_required(holding, datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc))


def test_rollover_solo_futuros():
    rules = _rules(weekend_holding=True, rollover_utc="21:00", rollover_blackout_min=30)
    futures = session_block(rules, datetime(2026, 11, 6, 21, 15, tzinfo=timezone.utc), asset_class="futures")
    assert futures.blocked
    assert futures.kind == "rollover"

    later = session_block(rules, datetime(2026, 11, 6, 22, 30, tzinfo=timezone.utc), asset_class="futures")
    assert not later.blocked

    forex = session_block(rules, datetime(2026, 11, 6, 21, 15, tzinfo=timezone.utc), asset_class="forex")
    assert not forex.blocked


def test_guard_bloquea_apertura_y_permite_cierre():
    rules = _rules()
    state = AccountState(
        balance=100_000,
        equity=100_000,
        initial_balance=100_000,
        day_start_balance=100_000,
        day_start_equity=100_000,
        peak_balance=100_000,
        peak_equity=100_000,
    )
    guard = PropGuard(rules)
    blocked = guard.evaluate(state, blocked_by_session=True, session_reason="viernes")
    assert not blocked.allowed
    assert "sesión" in blocked.reason

    closing = guard.evaluate(state, closing=True, blocked_by_session=True)
    assert closing.allowed
