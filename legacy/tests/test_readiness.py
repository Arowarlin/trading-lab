from __future__ import annotations

from datetime import date

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.readiness import readiness


def test_readiness_cuenta_decisiones_y_f13(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating, return_20d) "
            "VALUES(?,?,?,?,?,?)",
            ("2026-01-05T00:00:00+00:00", "SPY", "2026-01-05", "lite", "Buy", 0.1),
        )
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating) VALUES(?,?,?,?,?)",
            ("2026-01-06T00:00:00+00:00", "QQQ", "2026-01-06", "deep", "Hold"),
        )
        con.execute(
            "INSERT INTO f13_config"
            "(bot, symbol, start_date, config_hash, criteria, frozen_at) "
            "VALUES(?,?,?,?,?,?)",
            ("qqq", "QQQ", "2026-11-09", "hash", "{}", "2026-11-09T00:00:00+00:00"),
        )
    data = readiness(db, settings=Settings(), today=date(2026, 11, 10))
    assert data["decisions"]["total"] == 2
    assert data["decisions"]["with_20d"] == 1
    assert data["decisions"]["needed"] == 29
    assert data["days_in_paper"] == 1
    assert data["f13"]["bot"] == "qqq"


def test_readiness_sin_datos(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    data = readiness(db, settings=Settings())
    assert data["decisions"]["total"] == 0
    assert data["decisions"]["needed"] == 30
    assert data["f13"] is None
    assert data["calendar"] == []
