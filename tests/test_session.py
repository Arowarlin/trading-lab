from __future__ import annotations

from datetime import datetime, timezone

from tradinglab.prop import AccountState, PropGuard, ftmo
from tradinglab.session import session_block


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
