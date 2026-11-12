from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradinglab.ai_distill import (
    distill,
    learn_filter,
    scalping_tick_confirmation,
)
from tradinglab.ai_trader import AiTraderError, _cell_status, propose
from tradinglab.db import connect, init_db
from tradinglab.learning import count_tests
from tradinglab.runtime import effective_enabled


class _Broker:
    def health(self):
        return {"mode": "demo", "equity": 100_000.0}

    def positions(self):
        return []


def _rows() -> list[dict]:
    rows = []
    for i in range(40):
        trend = "up" if i < 20 else "down"
        cost = 0.03 if i % 2 == 0 else 0.10
        target = 1 if trend == "up" and cost <= 0.06 else 0
        rows.append({
            "features": {"trend_d1": trend, "cost_r": cost},
            "target": target,
        })
    return rows


def _configs(tmp_path: Path) -> tuple[Path, Path, Path]:
    ai = tmp_path / "ai_trader.yaml"
    ai.write_text(
        Path("config/ai_trader.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    intraday = tmp_path / "intraday_bots.yaml"
    intraday.write_text(
        Path("config/intraday_bots.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    swing = tmp_path / "bots.yaml"
    swing.write_text(
        Path("config/bots.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return ai, intraday, swing


def _winning_cell(db: Path) -> None:
    init_db(db)
    with connect(db) as con:
        for i in range(30):
            stamp = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc).isoformat()
            pid = f"p{i}"
            con.execute(
                "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, "
                "side, timeframe, status, source, result_r, playbook_version) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    pid, stamp, "intraday", "XAUUSD", "liquidity_sweep", "sell",
                    "H1", "closed", "forward", 0.5, 1,
                ),
            )
            snapshot = {
                "session": "Nueva York",
                "is_index": False,
                "d1": {"close": 100.0, "sma200": 90.0, "rsi2": 50.0},
                "h1": {"bb_squeeze": False, "sweep_high": True, "sweep_low": False},
            }
            con.execute(
                "INSERT INTO ai_decisions(ts, decision_date, session, style, "
                "symbol, timeframe, strategy, setup_valid, decision, reason, "
                "snapshot, playbook_version, source, plan_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    stamp, "2026-09-01", "Nueva York", "intraday", "XAUUSD",
                    "H1", "liquidity_sweep", 1, "take", "test",
                    json.dumps(snapshot), 1, "forward", pid,
                ),
            )


def _validation_pass() -> dict:
    return {
        "ok": True,
        "winner": "sin_filtro",
        "reason": "pasa sin_filtro",
        "variants": {
            "sin_filtro": {
                "passed": True, "sharpe": 1.2, "num_trades": 20,
                "dsr": 0.95, "pbo": 0.1, "wf_verdict": "ok",
                "regime_gate": {"passed": True}, "spread_reliable": True,
                "calibrated_cost_bps": 2.0, "breakeven_cost_bps": 3.0,
                "slippage_bps": 2.0,
            },
            "con_filtro": {
                "passed": False, "sharpe": 0.9, "num_trades": 20,
                "dsr": 0.9, "pbo": 0.1, "wf_verdict": "ok",
                "regime_gate": {"passed": True}, "spread_reliable": True,
                "calibrated_cost_bps": 2.0, "breakeven_cost_bps": 3.0,
                "slippage_bps": 2.0,
            },
        },
    }


def test_arbol_aprende_regla_conocida():
    learned = learn_filter(_rows())
    assert learned["empty"] is False
    assert learned["gain"] > 0.5
    assert "trend_d1" in learned["description"]
    assert "cost_r" in learned["description"]


def test_sin_separacion_el_filtro_queda_vacio():
    rows = [
        {
            "features": {"trend_d1": "up" if i < 20 else "down"},
            "target": 1 if i % 4 in (0, 1) else 0,
        }
        for i in range(40)
    ]
    learned = learn_filter(rows)
    assert learned["empty"] is True
    assert learned["conditions"] == []


def test_dsr_suma_dos_pruebas_y_no_activa_nada(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    _winning_cell(db)
    ai, intraday, swing = _configs(tmp_path)
    docs = tmp_path / "docs.md"
    docs.write_text("# skill\n", encoding="utf-8")
    skill = tmp_path / "skill.md"
    skill.write_text("# skill\n", encoding="utf-8")
    monkeypatch.setattr(
        "tradinglab.ai_distill.validate_candidate",
        lambda **kwargs: _validation_pass(),
    )
    import tradinglab.lifecycle as lifecycle

    monkeypatch.setattr(
        lifecycle, "start_incubation",
        lambda *args, **kwargs: {"state": "incubando"},
    )
    before = count_tests(db)
    result = distill(
        db_path=db, ai_config_path=ai, intraday_bots_path=intraday,
        swing_bots_path=swing, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc),
    )
    assert result["distilled"] == 1
    assert result["incubating"] == 1
    assert count_tests(db) == before + 2
    assert _cell_status(db, "liquidity_sweep", "XAUUSD", "H1") == "destilada"
    import yaml

    bots = yaml.safe_load(intraday.read_text(encoding="utf-8"))["bots"]
    candidate = next(item for item in bots if str(item["id"]).startswith("ai-"))
    assert candidate["enabled"] is False
    assert candidate["origin"] == "destilado de ia-discrecional"
    assert int(candidate["magic"]) >= 20262100
    assert effective_enabled(db, candidate["id"], candidate["enabled"]) is False
    with connect(db) as con:
        run = con.execute(
            "SELECT status, filter FROM ai_distill_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert run["status"] == "incubando"
    assert json.loads(run["filter"])["conditions"] == []


def test_celda_destilada_deja_de_operar(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, "
            "reason, updated_at) VALUES(?,?,?,'destilada',?,?)",
            (
                "liquidity_sweep", "XAUUSD", "H1", "bot destilado",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    payload = {
        "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
        "timeframe": "H1", "side": "sell", "thesis": "prueba", "confidence": 3,
    }
    with pytest.raises(AiTraderError, match="destilada"):
        propose(payload, broker=_Broker(), db_path=db)


def test_scalping_sin_ticks_no_se_promociona(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO lifecycle_bots(bot, asset, state, created_at, "
            "updated_at, evidence, criteria) VALUES(?,?,?,?,?,?,?)",
            (
                "ai-orb-5m-us100-cash-m5", "US100.cash", "incubando",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                json.dumps({"symbol": "US100.cash", "hours_ny": [10]}),
                json.dumps({"max_slippage_bps": 3.0}),
            ),
        )
    result = scalping_tick_confirmation(db, "ai-orb-5m-us100-cash-m5")
    assert result["ok"] is False
    assert "slippage forward sin muestra" in result["reason"] or "sin muestra" in result["reason"]
