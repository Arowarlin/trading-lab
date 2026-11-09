from __future__ import annotations

from tradinglab.asset_aliases import (
    INTRADAY_FX_PROFILE,
    aliases,
    allowed_symbols,
    discover,
    symbol_allowed,
)
from tradinglab.db import connect, init_db


class FakeSpecBroker:
    def symbol_spec(self, symbol: str) -> dict:
        known = {
            "US100.cash": "US100.CASH",
            "XAUUSD": "XAUUSD",
            "EURUSD": "EURUSD",
            "USDJPY": "USDJPY",
        }
        if symbol in known:
            return {"symbol": known[symbol]}
        raise ValueError(f"no existe {symbol}")


def test_descubre_alias_del_broker(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    found = discover(db, FakeSpecBroker())
    assert found == {
        "NASDAQ": "US100.CASH",
        "XAUUSD": "XAUUSD",
        "EURUSD": "EURUSD",
        "USDJPY": "USDJPY",
    }
    rows = aliases(db)
    assert {row["broker_symbol"] for row in rows} == {
        "US100.CASH",
        "XAUUSD",
        "EURUSD",
        "USDJPY",
    }
    assert all(row["profile"] == INTRADAY_FX_PROFILE for row in rows)


def test_symbol_allowed_rechaza_fuera_del_universo(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    discover(db, FakeSpecBroker())
    assert allowed_symbols(db) == {"US100.CASH", "XAUUSD", "EURUSD", "USDJPY"}
    assert symbol_allowed(db, "US100.cash")[0] is True
    assert symbol_allowed(db, "XAUUSD")[0] is True
    ok, reason = symbol_allowed(db, "BTCUSD")
    assert ok is False
    assert "intraday_fx" in reason and "BTCUSD" in reason
    # Otros perfiles no se restringen aquí.
    assert symbol_allowed(db, "BTCUSD", profile="swing_equity")[0] is True


def test_alias_persistido_se_reescribe(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    discover(db, FakeSpecBroker())
    with connect(db) as con:
        con.execute(
            "INSERT OR REPLACE INTO asset_aliases"
            "(canonical, broker_symbol, asset_class, profile, discovered_at, source) "
            "VALUES(?,?,?,?,?,?)",
            ("NASDAQ", "NAS100.cash", "índice", INTRADAY_FX_PROFILE, "2026-11-09", "manual"),
        )
    discover(db, FakeSpecBroker())
    row = next(item for item in aliases(db) if item["canonical"] == "NASDAQ")
    assert row["broker_symbol"] == "US100.CASH"
