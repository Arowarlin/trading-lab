from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradinglab.ai_learn import learn
from tradinglab.ai_trader import (
    _cell_status,
    _exclusion_reason,
    load_config,
    scoreboard,
)
from tradinglab.db import connect, init_db

MAGIC = 20261192


class _Broker:
    def positions(self):
        return []


def _config(tmp_path: Path) -> Path:
    source = Path("config/ai_trader.yaml")
    target = tmp_path / "ai_trader.yaml"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _docs(tmp_path: Path) -> tuple[Path, Path]:
    docs = tmp_path / "docs_skill.md"
    docs.write_text("# skill\n", encoding="utf-8")
    skill = tmp_path / "operator_skill.md"
    skill.write_text("# skill\n", encoding="utf-8")
    return docs, skill


def _trade(db: Path, i: int, *, r: float, ts: datetime | None = None,
           style: str = "intraday", symbol: str = "EURUSD",
           strategy: str = "ema_pullback", timeframe: str = "H1",
           version: int = 1, snapshot: dict | None = None) -> None:
    init_db(db)
    moment = ts or datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    pid = f"p{i}"
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "timeframe, status, source, result_r, playbook_version, magic) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, moment.isoformat(), style, symbol, strategy, "buy",
             timeframe, "closed", "forward", r, version, MAGIC),
        )
        if snapshot is not None:
            con.execute(
                "INSERT INTO ai_decisions(ts, decision_date, session, style, "
                "symbol, timeframe, strategy, setup_valid, decision, reason, "
                "snapshot, playbook_version, source, plan_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (moment.isoformat(), moment.date().isoformat(), "Nueva York",
                 style, symbol, timeframe, strategy, 1, "take", "test",
                 json.dumps(snapshot), version, "forward", pid),
            )


def test_learn_pausa_celda_perdedora(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    for i in range(30):
        _trade(
            db, i, r=-0.5,
            ts=start + timedelta(days=i, hours=i % 24),
        )
    config = _config(tmp_path)
    with config.open("a", encoding="utf-8") as handle:
        handle.write(
            "\nlearned:\n  risk_overrides:\n    intraday:\n      EURUSD: 0.0025\n"
        )
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    assert result["version_before"] == 1
    assert result["version_after"] == 2
    assert result["applied"] and result["applied"][0]["kind"] == "pause"
    assert _cell_status(db, "ema_pullback", "EURUSD", "H1") == "paused"
    assert load_config(config)["playbook_version"] == 2
    assert "playbook v2" in docs.read_text(encoding="utf-8")


def test_learn_mitad_de_riesgo_por_simbolo(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    for i in range(30):
        strategy = ("ema_pullback", "london_breakout", "inside_bar")[i % 3]
        _trade(db, i, r=-0.5, strategy=strategy, timeframe="H1")
    config = _config(tmp_path)
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    applied = [item for item in result["applied"] if item["kind"] == "half_risk"]
    assert applied
    loaded = load_config(config)
    assert loaded["styles"]["intraday"]["risk_overrides"]["EURUSD"] == pytest.approx(0.0025)


def test_learn_limite_semanal(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    for i in range(30):
        _trade(db, i, r=-0.5)
    init_db(db)
    now = datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc)
    with connect(db) as con:
        for i in range(2):
            con.execute(
                "INSERT INTO ai_learn_changes(ts, kind, detail, playbook_version) "
                "VALUES(?,?,?,?)",
                ((now - timedelta(days=1)).isoformat(), "pause", "previo", 1 + i),
            )
    config = _config(tmp_path)
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=now,
    )
    assert result["applied"] == []
    assert result["weekly_used_before"] == 2
    assert any(item["reason"] == "límite semanal de 2" for item in result["skipped"])
    assert _cell_status(db, "ema_pullback", "EURUSD", "H1") == "active"


def test_learn_reactivacion_queda_proposed(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_cell_state(strategy, symbol, timeframe, status, "
            "reason, updated_at) VALUES(?,?,?,'paused',?,?)",
            ("ema_pullback", "EURUSD", "H1", "replay", datetime.now(timezone.utc).isoformat()),
        )
    for i in range(30):
        _trade(db, i, r=0.5)
    config = _config(tmp_path)
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    assert result["applied"] == []
    assert _cell_status(db, "ema_pullback", "EURUSD", "H1") == "paused"
    assert any(
        isinstance(item.get("action"), dict)
        and item["action"].get("type") == "resume_cell"
        for item in result["proposed"]
    )


def test_learn_subir_riesgo_queda_proposed(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    for i in range(30):
        _trade(db, i, r=0.5)
    config = _config(tmp_path)
    with config.open("a", encoding="utf-8") as handle:
        handle.write(
            "\nlearned:\n  risk_overrides:\n    intraday:\n      EURUSD: 0.001\n"
        )
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    assert result["applied"] == []
    assert any(
        isinstance(item.get("action"), dict)
        and item["action"].get("type") == "raise_risk"
        for item in result["proposed"]
    )
    assert load_config(config)["styles"]["intraday"]["risk_overrides"]["EURUSD"] == pytest.approx(0.001)


def test_learn_exclusion_horaria(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    for i in range(20):
        _trade(db, i, r=-0.6)
    config = _config(tmp_path)
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    assert any(item["kind"] == "exclude_hour" for item in result["applied"])
    loaded = load_config(config)
    assert loaded["exclusions"]
    item = {
        "style": "intraday", "symbol": "EURUSD",
        "strategy": "ema_pullback", "timeframe": "H1",
    }
    reason = _exclusion_reason(
        loaded, item, {"d1": {}, "h1": {}},
        datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc),
    )
    assert reason and "hora" in reason


def test_learn_exclusion_por_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("tradinglab.ai_learn.send_alert", lambda *a, **k: None)
    db = tmp_path / "lab.db"
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    snapshot = {
        "d1": {"close": 100.0, "sma200": 90.0, "rsi2": 5.0},
        "h1": {"bb_squeeze": True},
    }
    for i in range(20):
        _trade(
            db, i, r=-0.6, snapshot=snapshot,
            ts=start + timedelta(days=i, hours=i % 24),
        )
    config = _config(tmp_path)
    docs, skill = _docs(tmp_path)
    result = learn(
        db_path=db, config_path=config, docs_path=docs, skill_path=skill,
        now=datetime(2026, 11, 12, 22, 0, tzinfo=timezone.utc),
    )
    assert any(item["kind"] == "exclude_snapshot" for item in result["applied"])
    loaded = load_config(config)
    assert any(item["kind"] == "snapshot" for item in loaded["exclusions"])


def test_marcador_separa_playbook_version(tmp_path):
    db = tmp_path / "lab.db"
    for i, version in ((0, 1), (1, 2)):
        _trade(db, i, r=0.5, version=version)
    board = scoreboard(broker=_Broker(), db_path=db)
    versions = sorted(cell["playbook_version"] for cell in board["cells"])
    assert versions == [1, 2]
