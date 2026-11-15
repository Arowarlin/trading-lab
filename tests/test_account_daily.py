from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.account_daily import account_daily_report
from tradinglab.db import connect, init_db


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


class _BrokerEa(_Broker):
    """El EA empuja la cuenta al límite; el carril del lab no."""

    def positions(self):
        return [
            {"ticket": 1, "symbol": "US100.cash", "magic": 93010001,
             "profit": -3_900.0, "swap": 0.0, "commission": 0.0},
            {"ticket": 2, "symbol": "EURUSD", "magic": 20261151,
             "profit": -100.0, "swap": 0.0, "commission": 0.0},
        ]


def _account_stops(db: Path) -> list[dict]:
    with connect(db) as con:
        rows = con.execute(
            "SELECT action, params, result FROM console_actions "
            "WHERE action = 'account_stop'"
        ).fetchall()
    return [dict(row) for row in rows]


def test_stop_cuenta_por_flotante_del_ea(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    now = pd.Timestamp("2026-11-12T20:00:00Z").to_pydatetime()
    report = account_daily_report(
        db, broker=_BrokerEa(96_000.0), now=now, alert=False,
    )
    assert report["allowed"] is False
    assert report["stop_cause"] == "ea"
    assert report["ea_floating_usd"] == pytest.approx(-3_900.0)
    assert report["lab_floating_usd"] == pytest.approx(-100.0)
    assert report["alerted"] is True

    stops = _account_stops(db)
    assert len(stops) == 1
    payload = json.loads(stops[0]["params"])
    assert payload["cause"] == "ea"
    assert payload["ea_floating"] == pytest.approx(-3_900.0)

    # Una segunda lectura no duplica la alerta ni la acción.
    again = account_daily_report(
        db, broker=_BrokerEa(96_000.0), now=now, alert=False,
    )
    assert again["allowed"] is False
    assert again["alerted"] is False
    assert len(_account_stops(db)) == 1


def test_stop_del_ea_alerta_critical_y_bloquea_aperturas(
    tmp_path: Path, monkeypatch
):
    db = tmp_path / "lab.db"
    init_db(db)
    calls = []

    def fake_send(event, message, *, severity="warning", **kwargs):
        calls.append({"event": event, "message": message, "severity": severity})

    monkeypatch.setattr("tradinglab.account_daily.send_alert", fake_send)
    now = pd.Timestamp("2026-11-12T20:00:00Z").to_pydatetime()
    report = account_daily_report(db, broker=_BrokerEa(96_000.0), now=now)
    assert report["allowed"] is False
    assert report["stop_cause"] == "ea"
    assert report["alerted"] is True
    assert calls
    assert calls[0]["event"] == "account_stop:ftmo_demo"
    assert calls[0]["severity"] == "critical"
    assert "EA flotante" in calls[0]["message"]


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

    blocked = account_daily_report(db, broker=_Broker(96_000.0), alert=False)
    assert blocked["allowed"] is False
    assert blocked["loss_used_usd"] == 4_000.0
    assert "fuera de límite" in blocked["reason"] or "stop" in blocked["reason"].lower()
