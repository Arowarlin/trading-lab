from __future__ import annotations

from pathlib import Path

import pandas as pd

from tradinglab.account_daily import account_daily_report
from tradinglab.db import init_db


class _Broker:
    def __init__(self, equity: float) -> None:
        self.equity = equity

    def health(self):
        return {"mode": "demo", "equity": self.equity}

    def positions(self):
        return [
            {"ticket": 1, "symbol": "EURUSD", "magic": 20261151,
             "profit": -2_000.0, "swap": 0.0, "commission": 0.0},
            {"ticket": 2, "symbol": "XAUUSD", "magic": 20261191,
             "profit": -1_500.0, "swap": 0.0, "commission": 0.0},
        ]

    def equity_series(self):
        return pd.Series(
            [100_000.0, 100_000.0],
            index=pd.to_datetime(
                ["2026-11-12T00:00:00Z", "2026-11-12T20:00:00Z"], utc=True
            ),
        )


def test_stop_cuenta_suma_flotante_de_varios_carriles(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    allowed = account_daily_report(db, broker=_Broker(97_000.0))
    assert allowed["allowed"] is True
    assert allowed["daily_stop_pct"] == 0.04
    assert allowed["loss_used_usd"] == 3_000.0
    assert allowed["floating_by_magic"] == {
        "20261151": -2_000.0, "20261191": -1_500.0,
    }

    blocked = account_daily_report(db, broker=_Broker(96_000.0))
    assert blocked["allowed"] is False
    assert blocked["loss_used_usd"] == 4_000.0
    assert "fuera de límite" in blocked["reason"] or "stop" in blocked["reason"].lower()
