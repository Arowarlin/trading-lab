from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from tradinglab.db import connect, init_db
from tradinglab.decisions import compare as compare_decisions
from tradinglab.decisions import (
    lite_prompt_version,
    record_decision,
    report,
    report_by_source,
    update_outcomes,
)


def _frame(n: int = 30) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-05", periods=n)
    close = [100 + i for i in range(n)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [x + 1 for x in close],
            "low": [x - 1 for x in close],
            "close": close,
            "volume": [1_000] * n,
        },
        index=idx,
    )


def test_prompt_hash_estable():
    version, digest = lite_prompt_version()
    assert version == "lite-v1"
    assert len(digest) == 64


def test_record_y_update_outcomes(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    record_decision(
        db,
        {
            "ticker": "SPY",
            "date": "2026-01-05",
            "rating": "Buy",
            "confidence": 0.6,
            "model": "test",
            "context": {"price": 100.0},
        },
        mode="lite",
    )
    with connect(db) as con:
        row = con.execute("SELECT * FROM decision_outcomes").fetchone()
    assert row["ticker"] == "SPY"
    assert row["ref_price"] == pytest.approx(100.0)

    monkeypatch.setattr("tradinglab.data.fetch", lambda *a, **k: _frame())
    assert update_outcomes(db, tmp_path) == 1

    with connect(db) as con:
        row = con.execute("SELECT * FROM decision_outcomes").fetchone()
    assert row["return_1d"] == pytest.approx(0.01)
    assert row["return_5d"] == pytest.approx(0.05)
    assert row["return_20d"] == pytest.approx(0.20)

    rows = report(db)
    assert rows[0]["rating"] == "Buy"
    assert rows[0]["n"] == 1
    assert rows[0]["mean_20d"] == pytest.approx(0.20)
    assert rows[0]["hit_rate_20d"] == pytest.approx(1.0)
    assert rows[0]["insufficient"] is True
    assert "muestra insuficiente" in rows[0]["sample_warning"]


def test_migracion_decision_outcomes_conserva_historial(tmp_path):
    db = tmp_path / "lab.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE decision_outcomes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
            "ticker TEXT NOT NULL, decision_date TEXT NOT NULL, mode TEXT NOT NULL, "
            "rating TEXT NOT NULL, confidence REAL, model TEXT, prompt_version TEXT, "
            "prompt_hash TEXT, ref_price REAL, return_1d REAL, return_5d REAL, "
            "return_20d REAL, updated_at TEXT, UNIQUE(ticker, decision_date, mode))"
        )
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating) VALUES(?,?,?,?,?)",
            ("2026-01-05T00:00:00+00:00", "SPY", "2026-01-05", "lite", "Buy"),
        )
    init_db(db)
    with connect(db) as con:
        columns = {
            row["name"] for row in con.execute("PRAGMA table_info(decision_outcomes)")
        }
        row = con.execute("SELECT * FROM decision_outcomes").fetchone()
    assert {"analysts", "duration_s"} <= columns
    assert row["ticker"] == "SPY"


def test_reporte_por_fuente_y_retornos_pendientes(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating, return_20d) "
            "VALUES(?,?,?,?,?,?)",
            ("2026-01-05T00:00:00+00:00", "SPY", "2026-01-05", "lite", "Buy", 0.10),
        )
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating) VALUES(?,?,?,?,?)",
            ("2026-01-06T00:00:00+00:00", "QQQ", "2026-01-06", "deep", "Hold"),
        )
    rows = {row["source"]: row for row in report_by_source(db)}
    assert rows["lite"]["n"] == 1
    assert rows["lite"]["n_20d"] == 1
    assert rows["lite"]["mean_20d"] == pytest.approx(0.10)
    assert rows["deep"]["n"] == 1
    assert rows["deep"]["n_20d"] == 0
    assert rows["deep"]["mean_20d"] is None
    assert rows["deep"]["insufficient"] is True
    assert "retornos 20d insuficientes" in rows["deep"]["sample_warning"]


def test_compare_llm_buy_hold_y_trend(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    rows = [
        ("SPY", "2026-01-05", "Buy", 0.10),
        ("QQQ", "2026-01-05", "Hold", 0.02),
        ("IWM", "2026-01-05", "Sell", -0.05),
    ]
    with connect(db) as con:
        for ticker, day, rating, ret in rows:
            con.execute(
                "INSERT INTO decision_outcomes"
                "(ts, ticker, decision_date, mode, rating, return_20d) VALUES(?,?,?,?,?,?)",
                ("2026-01-05T00:00:00+00:00", ticker, day, "lite", rating, ret),
            )

    idx = pd.bdate_range("2024-01-01", periods=700)
    close = [100 + i for i in range(700)]
    frame = pd.DataFrame(
        {
            "open": close,
            "high": [x + 1 for x in close],
            "low": [x - 1 for x in close],
            "close": close,
            "volume": [1_000] * 700,
        },
        index=idx,
    )
    monkeypatch.setattr("tradinglab.data.fetch", lambda *a, **k: frame)

    result = compare_decisions(db, tmp_path)
    assert result["n"] == 3
    assert result["matched_n"] == 3
    assert result["llm_mean_20d"] == pytest.approx((0.10 + 0.0 + 0.0) / 3)
    assert result["buy_hold_mean_20d"] == pytest.approx((0.10 + 0.02 - 0.05) / 3)
    assert result["trend_n"] == 3
    assert result["trend_coverage"] == pytest.approx(1.0)
    assert result["matched_llm_mean_20d"] == pytest.approx((0.10 + 0.0 + 0.0) / 3)
    assert result["matched_buy_hold_mean_20d"] == pytest.approx((0.10 + 0.02 - 0.05) / 3)
    assert result["matched_trend_mean_20d"] == pytest.approx((0.10 + 0.02 - 0.05) / 3)
    assert result["matched_llm_hit_rate"] == pytest.approx(1 / 3)
    assert result["matched_buy_hold_hit_rate"] == pytest.approx(2 / 3)
    assert result["insufficient"] is True
    assert "muestra insuficiente" in result["sample_warning"]


def test_compare_solo_compara_fechas_con_trend(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    rows = [
        ("SPY", "2026-01-05", "Buy", 0.10),
        ("QQQ", "2026-01-05", "Hold", 0.02),
        ("IWM", "2026-01-05", "Sell", -0.05),
    ]
    with connect(db) as con:
        for ticker, day, rating, ret in rows:
            con.execute(
                "INSERT INTO decision_outcomes"
                "(ts, ticker, decision_date, mode, rating, return_20d) VALUES(?,?,?,?,?,?)",
                ("2026-01-05T00:00:00+00:00", ticker, day, "lite", rating, ret),
            )

    def fake_trend(ticker, day, cache_dir):
        return None if ticker == "IWM" else 1.0

    monkeypatch.setattr("tradinglab.decisions.trend_target_at", fake_trend)
    result = compare_decisions(db, tmp_path)
    assert result["n"] == 3
    assert result["trend_n"] == 2
    assert result["matched_n"] == 2
    assert result["trend_coverage"] == pytest.approx(2 / 3)
    assert result["matched_llm_mean_20d"] == pytest.approx((0.10 + 0.0) / 2)
    assert result["matched_buy_hold_mean_20d"] == pytest.approx((0.10 + 0.02) / 2)
    assert result["matched_trend_mean_20d"] == pytest.approx((0.10 + 0.02) / 2)
