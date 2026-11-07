from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.db import connect, init_db
from tradinglab.decisions import compare as compare_decisions
from tradinglab.decisions import (
    lite_prompt_version,
    record_decision,
    report,
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
    assert result["llm_mean_20d"] == pytest.approx((0.10 + 0.0 + 0.0) / 3)
    assert result["buy_hold_mean_20d"] == pytest.approx((0.10 + 0.02 - 0.05) / 3)
    assert result["trend_n"] == 3
    assert result["trend_coverage"] == pytest.approx(1.0)
