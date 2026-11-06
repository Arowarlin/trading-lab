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
