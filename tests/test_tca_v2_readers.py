"""TCA v2 · los lectores ignoran las filas v1."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from tradinglab.ai_distill import scalping_tick_confirmation
from tradinglab.ai_trader import _slippage_avg
from tradinglab.db import connect, init_db
from tradinglab.tca import build_tca


def _insert(db, *, version: int, count: int, slip: float, bot: str = "bot-a") -> None:
    init_db(db)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect(db) as con:
        for _ in range(count):
            con.execute(
                "INSERT INTO tca(bot, symbol, side, signal_px, order_px, fill_px, "
                "slippage_bps, tca_version, ts_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                (bot, "SPY", "buy", 100.0, 100.0, 100.0, slip, version, now),
            )


def test_media_solo_v2_no_diluye_con_v1(tmp_path):
    db = tmp_path / "lab.db"
    _insert(db, version=1, count=66, slip=0.0)
    _insert(db, version=2, count=6, slip=2.0)

    state = build_tca(db, alert=False)
    row = state["rows"][0]
    assert row["fills"] == 6
    assert row["slippage_p50_bps"] == 2.0
    assert row["slippage_ewma_bps"] == 2.0

    avg, n = _slippage_avg(db, "bot-a", "SPY")
    assert avg == 2.0
    assert n == 6


def test_solo_v1_es_sin_datos(tmp_path):
    db = tmp_path / "lab.db"
    _insert(db, version=1, count=66, slip=0.0)

    state = build_tca(db, alert=False)
    assert state["rows"] == []
    assert state["status"] == "sin datos"

    assert _slippage_avg(db, "bot-a", "SPY") == (None, 0)


def test_ai_distill_ignora_v1(tmp_path):
    db = tmp_path / "lab.db"
    _insert(db, version=1, count=20, slip=0.0, bot="bot-a")
    with connect(db) as con:
        con.execute(
            "INSERT INTO lifecycle_bots(bot, asset, created_at, updated_at, evidence, criteria)"
            " VALUES(?,?,?,?,?,?)",
            (
                "bot-a",
                "US100",
                "2026-11-01T00:00:00+00:00",
                "2026-11-01T00:00:00+00:00",
                json.dumps(
                    {
                        "slippage_assumption_bps": 1.0,
                        "symbol": "US100",
                        "hours_ny": [10],
                    }
                ),
                json.dumps({"max_slippage_bps": 3.0}),
            ),
        )

    result = scalping_tick_confirmation(db, "bot-a")

    assert result["ok"] is False
    assert result["reason"] == "slippage forward sin muestra"
