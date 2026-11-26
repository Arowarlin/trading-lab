from __future__ import annotations

import json

import pytest

from tradinglab.ai_replay import (
    ReplayError,
    pause_by_replay,
    prepare_replay,
    run_replay,
)
from tradinglab.ai_setups import validate
from tradinglab.ai_trader import _cell_status, scoreboard
from tradinglab.db import connect, init_db


class _Broker:
    def positions(self):
        return []


@pytest.mark.requires_local("data/cache/mt5/EURUSD_M15.parquet")
def test_snapshot_anonimizado_sin_fecha_ni_simbolo():
    plan = prepare_replay("intraday", n=1, strategy="ema_pullback", symbol="EURUSD")
    moment = plan.moments[0]
    text = json.dumps(moment.anonymized, ensure_ascii=False)
    assert moment.anonymized["price"] == 100.0
    assert "symbol" not in moment.anonymized
    assert "now" not in moment.anonymized
    assert "EURUSD" not in text
    assert "2021-" not in text and "2022-" not in text and "2023-" not in text
    assert moment.anonymized["asset_class"] == "forex"


@pytest.mark.requires_local("data/cache/mt5/EURUSD_M15.parquet")
def test_solo_momentos_con_setup_valido():
    plan = prepare_replay("intraday", n=3, strategy="ema_pullback", symbol="EURUSD")
    assert plan.moments
    for moment in plan.moments:
        ok, reason = validate(
            moment.strategy, moment.side, moment.snapshot, moment.timeframe
        )
        assert ok is True, reason


@pytest.mark.requires_local("data/cache/mt5/EURUSD_M15.parquet")
def test_respeta_fecha_de_corte():
    plan = prepare_replay(
        "swing", n=3, strategy="trend_pullback", symbol="US100.cash"
    )
    cutoff = plan.cutoff
    assert cutoff is not None
    for moment in plan.moments:
        assert moment.moment < cutoff
        if len(moment.future):
            assert moment.future.index.max() < cutoff


def test_rechaza_scalping():
    with pytest.raises(ReplayError, match="scalping"):
        prepare_replay("scalping", n=1)


def test_replay_excluido_del_marcador_forward(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "timeframe, status, source, result_r, cost_ratio, magic) "
            "VALUES('fwd',?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-11-01T00:00:00+00:00", "intraday", "EURUSD", "ema_pullback",
             "buy", "H1", "closed", "forward", 0.5, 0.02, 20261192),
        )
        con.execute(
            "INSERT INTO ai_decisions(ts, decision_date, session, style, symbol, "
            "timeframe, strategy, setup_valid, decision, reason, snapshot, "
            "playbook_version, source, result_r, shadow_r) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-11-01T00:00:00+00:00", "2026-11-01", "Nueva York", "replay",
             "EURUSD", "H1", "ema_pullback", 1, "take", "replay",
             "{}", 1, "replay", -1.0, -0.2),
        )
    board = scoreboard(broker=_Broker(), db_path=db)
    assert len(board["cells"]) == 1
    assert board["cells"][0]["style"] == "intraday"
    assert board["cells"][0]["n"] == 1
    assert [row["id"] for row in board["trades"]] == ["fwd"]


def test_pausa_por_replay(tmp_path, monkeypatch):
    import tradinglab.ai_replay as module

    monkeypatch.setattr(module, "send_alert", lambda *args, **kwargs: None)
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for i in range(50):
            con.execute(
                "INSERT INTO ai_decisions(ts, decision_date, session, style, symbol, "
                "timeframe, strategy, setup_valid, decision, reason, snapshot, "
                "playbook_version, source, result_r, shadow_r) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"2026-11-01T00:00:{i:02d}+00:00", "2026-11-01", "Nueva York",
                 "replay", "XAUUSD", "H1", "liquidity_sweep", 1, "take",
                 "replay", "{}", 1, "replay", -1.0, -0.4),
            )
    paused = pause_by_replay(db)
    assert len(paused) == 1
    assert paused[0]["n"] == 50
    assert _cell_status(db, "liquidity_sweep", "XAUUSD", "H1") == "paused"
    with connect(db) as con:
        audit = con.execute(
            "SELECT action, result FROM console_actions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert audit["action"] == "ai_trader_replay_pause"
    assert audit["result"] == "paused"


@pytest.mark.requires_local("data/cache/mt5/EURUSD_M15.parquet")
def test_run_replay_con_llm_simulado(tmp_path):
    plan = prepare_replay("intraday", n=2, strategy="ema_pullback", symbol="EURUSD")
    db = tmp_path / "lab.db"

    def ask(prompt):
        return [
            {"id": 0, "decision": "take", "reason": "estructura clara"},
            {"id": 1, "decision": "skip", "reason": "contexto mixto"},
        ]

    result = run_replay(plan, yes=True, db_path=db, ask=ask)
    assert result["executed"] is True
    assert result["take"] == 1
    assert result["skip"] == 1
    with connect(db) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT source, decision, result_r, shadow_r FROM ai_decisions "
            "ORDER BY id"
        ).fetchall()]
    assert len(rows) == 2
    assert all(row["source"] == "replay" for row in rows)
    assert rows[0]["decision"] == "take"
    assert rows[0]["result_r"] is not None
    assert rows[0]["shadow_r"] is not None
