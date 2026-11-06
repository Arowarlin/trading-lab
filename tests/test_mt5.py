from __future__ import annotations

import pytest

from tradinglab.execution.mt5 import MT5Broker, MT5Error, normalize_volume


def test_normalize_volume_rounds_down_to_step():
    assert normalize_volume(0.129, 0.01, 100, 0.01) == pytest.approx(0.12)
    assert normalize_volume(0.10, 0.01, 100, 0.01) == pytest.approx(0.10)
    assert normalize_volume(1.99, 1, 100, 1) == pytest.approx(1)


def test_normalize_volume_respects_min_and_max():
    assert normalize_volume(0.001, 0.01, 100, 0.01) == 0.0
    assert normalize_volume(500, 0.01, 100, 0.01) == pytest.approx(100)


def test_normalize_volume_rejects_bad_step():
    with pytest.raises(MT5Error):
        normalize_volume(1.0, 0.01, 100, 0)


def test_broker_requires_connection():
    broker = MT5Broker(dry_run=True)
    with pytest.raises(MT5Error):
        broker.health()


def test_broker_defaults_to_dry_run():
    broker = MT5Broker()
    assert broker.dry_run is True


def test_to_utc_subtracts_server_offset():
    from datetime import datetime, timedelta, timezone

    broker = MT5Broker(server_utc_offset_hours=2)
    ts = 1_793_929_184
    expected = datetime.fromtimestamp(ts, tz=timezone.utc) - timedelta(hours=2)
    assert broker._to_utc(ts) == expected


# ---------------------------------------------------------- guard de identidad


class _Account:
    def __init__(self, login=3000112071, server="Darwinex-Demo", trade_mode=0):
        self.login = login
        self.server = server
        self.trade_mode = trade_mode


def test_identity_accepts_expected_demo():
    broker = MT5Broker(login=3000112071, server="Darwinex-Demo")
    assert broker._identity_problems(_Account()) == []


def test_identity_rejects_wrong_login():
    broker = MT5Broker(login=1111111, server="Darwinex-Demo")
    problems = broker._identity_problems(_Account())
    assert any("login" in p for p in problems)


def test_identity_rejects_wrong_server():
    broker = MT5Broker(login=3000112071, server="FTMO-Server")
    problems = broker._identity_problems(_Account())
    assert any("servidor" in p for p in problems)


def test_identity_rejects_real_account_by_default():
    broker = MT5Broker(login=3000112071, server="Darwinex-Live")
    problems = broker._identity_problems(_Account(server="Darwinex-Live", trade_mode=2))
    assert any("REAL" in p for p in problems)


def test_identity_allows_real_only_when_explicitly_disabled():
    broker = MT5Broker(login=3000112071, server="Darwinex-Live", require_demo=False)
    assert broker._identity_problems(_Account(server="Darwinex-Live", trade_mode=2)) == []
