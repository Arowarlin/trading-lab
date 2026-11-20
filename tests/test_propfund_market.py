from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from tradinglab.propfund.market import (
    CFD_UNIVERSE,
    FUTURES_UNIVERSE,
    briefing_slot,
    broker_symbol,
    quote,
    quotes,
    session_now,
    universe,
)


class FakeBroker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def connect(self):
        return {"connected": True, "mode": "demo"}

    def tick(self, symbol: str) -> dict:
        self.calls.append(symbol)
        if "GER40" in symbol:
            raise RuntimeError("símbolo no disponible")
        return {
            "bid": 100.0,
            "ask": 100.5,
            "last": 100.25,
            "time": "2026-11-19T10:00:00Z",
        }

    def rates(self, symbol: str, timeframe: str = "D1", count: int = 260):
        return pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [10]}
        )


def test_universo_solo_cfd_y_futuros() -> None:
    payload = universe()
    ids = {row["id"] for row in payload["instruments"]}
    assert set(CFD_UNIVERSE) <= ids
    assert set(FUTURES_UNIVERSE) <= ids
    assert "SPY" not in ids and "QQQ" not in ids
    assert payload["read_only"] is True
    assert all(row["data"].startswith("Sin datos") for row in payload["instruments"] if row["id"] in FUTURES_UNIVERSE)


def test_alias_de_bróker_para_mt5() -> None:
    assert broker_symbol("US100") == "US100.cash"
    assert broker_symbol("EURUSD") == "EURUSD"
    assert broker_symbol("XAUUSD") == "XAUUSD"


def test_quote_con_broker_sintetico() -> None:
    broker = FakeBroker()
    item = quote("US100", broker=broker)
    assert item["status"] == "ok"
    assert item["read_only"] is True and item["source"] == "mt5"
    assert item["price"] == 100.25
    assert item["spread_price"] == 0.5
    assert broker.calls == ["US100.cash"]


def test_quote_sin_datos_no_inventa() -> None:
    item = quote("GER40", broker=FakeBroker())
    assert item["status"] == "Sin datos"
    assert "error" in item and "price" not in item


def test_quotes_aisla_fallos_por_activo() -> None:
    rows = quotes(["US100", "GER40", "EURUSD"], broker=FakeBroker())
    status = {row["instrument"]: row["status"] for row in rows}
    assert status["US100"] == "ok"
    assert status["GER40"] == "Sin datos"
    assert status["EURUSD"] == "ok"


def test_sesiones_y_ventanas_de_briefing() -> None:
    assert session_now(datetime(2026, 11, 19, 3, tzinfo=timezone.utc)).name == "asia"
    assert session_now(datetime(2026, 11, 19, 9, tzinfo=timezone.utc)).name == "london"
    assert session_now(datetime(2026, 11, 19, 15, tzinfo=timezone.utc)).name == "ny"
    # 06:30 en Londres (UTC+0 en noviembre) es pre-Londres.
    assert briefing_slot(datetime(2026, 11, 19, 6, 30, tzinfo=timezone.utc)) == "pre_london"
    # 13:30 UTC = 08:30 en Nueva York (EST) es pre-NY.
    assert briefing_slot(datetime(2026, 11, 19, 13, 30, tzinfo=timezone.utc)) == "pre_ny"
    assert briefing_slot(datetime(2026, 11, 21, 13, 30, tzinfo=timezone.utc)) == "fuera"
