from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tradinglab.lease import acquire, release, status


def test_lease_rechaza_otro_host_y_caduca(tmp_path):
    db = tmp_path / "lab.db"
    now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    first = acquire(db, session="ai:scalping", host="PC-A", now=now)
    assert first["ok"] is True
    second = acquire(db, session="ai:scalping", host="PC-B", now=now)
    assert second["ok"] is False
    assert "PC-A" in second["reason"]
    same = acquire(db, session="ai:scalping", host="PC-A", now=now)
    assert same["ok"] is True
    expired = acquire(
        db, session="ai:scalping", host="PC-B",
        now=now + timedelta(seconds=121),
    )
    assert expired["ok"] is True
    assert status(db, now=now + timedelta(seconds=122))["lease"]["host"] == "PC-B"


def test_release_solo_del_mismo_host(tmp_path):
    db = tmp_path / "lab.db"
    now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    assert acquire(db, host="PC-A", now=now)["ok"] is True
    assert release(db, host="PC-B")["ok"] is False
    assert release(db, host="PC-A")["ok"] is True
    assert status(db, now=now)["active"] is False

def test_ai_trader_y_forward_rechazan_lease_de_otro_host(tmp_path):
    from datetime import datetime, time, timezone

    import pytest

    from tradinglab.ai_trader import AiTraderError, propose
    from tradinglab.config import Settings
    from tradinglab.db import init_db
    from tradinglab.forward_intraday import ForwardBot, ForwardError, run_forward_bot

    db = tmp_path / "lab.db"
    init_db(db)
    now = datetime.now(timezone.utc)
    assert acquire(db, host="OTRO-PC", now=now)["ok"] is True

    class Broker:
        def health(self):
            return {"mode": "demo", "equity": 100_000.0}

        def positions(self):
            return []

    with pytest.raises(AiTraderError, match="lease"):
        propose(
            {
                "style": "intraday", "strategy": "liquidity_sweep",
                "symbol": "XAUUSD", "timeframe": "H1", "side": "sell",
                "thesis": "prueba", "confidence": 3,
            },
            broker=Broker(), db_path=db,
        )

    bot = ForwardBot(
        id="x", canonical_symbol="EURUSD", strategy="london_pullback",
        timeframe="M15", account="ftmo_demo", params={},
        entry_start=time(0, 0), entry_end=time(1, 0), force_exit=time(2, 0),
        stop_atr=2.0, max_trades_per_day=1, magic=20261199, enabled=True,
    )
    with pytest.raises(ForwardError, match="lease"):
        run_forward_bot(
            bot, broker=Broker(), settings=Settings(), db_path=db, now=now,
        )
