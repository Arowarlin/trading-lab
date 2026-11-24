from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
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


def test_copy_ticks_etiqueta_utc_con_offset_semanal(monkeypatch):
    bar_stamps = [
        pd.Timestamp("2025-03-03 00:00", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-07 23:45", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-10 00:00", tz="UTC").timestamp(),
        pd.Timestamp("2025-03-14 23:45", tz="UTC").timestamp(),
    ]
    bar_dtype = [
        ("time", "i8"),
        ("open", "f8"),
        ("high", "f8"),
        ("low", "f8"),
        ("close", "f8"),
        ("tick_volume", "f8"),
        ("spread", "f8"),
    ]
    bars = np.array(
        [(stamp, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0) for stamp in bar_stamps],
        dtype=bar_dtype,
    )
    tick_dtype = [("time", "i8"), ("bid", "f8"), ("ask", "f8")]
    ticks = np.array(
        [
            (pd.Timestamp("2025-03-05 10:00", tz="UTC").timestamp(), 1.1000, 1.1002),
            (pd.Timestamp("2025-03-12 11:00", tz="UTC").timestamp(), 1.2000, 1.2003),
            (pd.Timestamp("2025-03-05 11:00", tz="UTC").timestamp(), 1.1001, 1.1000),
            (pd.Timestamp("2025-03-05 12:00", tz="UTC").timestamp(), 0.0, 0.0),
        ],
        dtype=tick_dtype,
    )

    class FakeMT5:
        TIMEFRAME_M15 = 15
        COPY_TICKS_ALL = 2

        def __init__(self):
            self.flags = None

        @staticmethod
        def copy_rates_range(symbol, timeframe, date_from, date_to):
            return bars

        def copy_ticks_range(self, symbol, date_from, date_to, flags):
            self.flags = flags
            return ticks

        @staticmethod
        def last_error():
            return (0, "ok")

    fake = FakeMT5()
    broker = MT5Broker(server_utc_offset_hours=2, dry_run=True)
    broker._connected = True
    monkeypatch.setattr(broker, "_require", lambda: fake)
    monkeypatch.setattr(broker, "symbol_spec", lambda symbol: {})

    frame = broker.copy_ticks(
        "EURUSD",
        datetime(2025, 3, 5, tzinfo=timezone.utc),
        datetime(2025, 3, 12, 23, 59, tzinfo=timezone.utc),
    )

    assert fake.flags == FakeMT5.COPY_TICKS_ALL
    assert list(frame.columns) == ["ts", "bid", "ask"]
    assert len(frame) == 2
    assert frame.iloc[0]["ts"] == pd.Timestamp("2025-03-05 08:00", tz="UTC")
    assert frame.iloc[1]["ts"] == pd.Timestamp("2025-03-12 08:00", tz="UTC")
    assert frame.iloc[0]["bid"] == pytest.approx(1.1000)
    assert frame.iloc[0]["ask"] == pytest.approx(1.1002)


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

def test_submit_market_guarda_bid_ask_y_solicitado(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import tradinglab.tca as tca

    captured = {}

    def fake_record(db_path, **kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(tca, "record_fill", fake_record)

    class FakeMT5:
        TRADE_ACTION_DEAL = 1
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        TRADE_RETCODE_DONE = 10009
        TRADE_RETCODE_INVALID_FILL = 10030
        ORDER_FILLING_IOC = 1
        ORDER_FILLING_FOK = 2
        ORDER_FILLING_RETURN = 3

        def order_send(self, request):
            return SimpleNamespace(
                retcode=self.TRADE_RETCODE_DONE,
                price=100.02,
                order=123,
                deal=456,
                comment="ok",
            )

    broker = MT5Broker(
        path="fake", login=1, server="Fake", dry_run=False,
        db_path=tmp_path / "lab.db",
    )
    fake = FakeMT5()
    monkeypatch.setattr(broker, "_require", lambda: fake)
    monkeypatch.setattr(broker, "_assert_can_trade", lambda mt5: None)
    monkeypatch.setattr(broker, "_require_identity", lambda: None)
    monkeypatch.setattr(
        broker,
        "symbol_spec",
        lambda symbol: {
            "symbol": "XAUUSD",
            "digits": 2,
            "point": 0.01,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "filling_mode": 1,
            "stops_level": 0,
        },
    )
    monkeypatch.setattr(
        broker, "tick", lambda symbol: {"bid": 100.0, "ask": 100.02}
    )
    monkeypatch.setattr(broker, "_record", lambda **kwargs: {"ok": True})

    result = broker.submit_market("XAUUSD", 0.01, bot="bot", dry_run=False)
    assert result["ok"] is True
    assert captured["bid"] == pytest.approx(100.0)
    assert captured["ask"] == pytest.approx(100.02)
    assert captured["requested_price"] == pytest.approx(100.02)
    assert captured["order_type"] == "market"
    assert captured["origin"] == "bot"
