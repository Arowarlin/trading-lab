from __future__ import annotations

import http.client
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.accounts import history, load_accounts, own_limits
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow
from tradinglab.learning import (
    apply_lesson,
    approve,
    count_tests,
    create_lesson,
    holdout_info,
    list_lessons,
    record_test,
    reject,
    revert_lesson,
    weekly_lessons,
)
from tradinglab.orchestrator import load_bots


def test_holdout_y_contador_trials(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    info = holdout_info(db, settings)
    assert info["start_date"] == settings.learning.holdout_start
    assert info["hash"]
    lesson = create_lesson(
        db,
        hypothesis="probar filtro",
        evidence="sintético",
        author="qwen",
        settings=settings,
    )
    result = record_test(
        db,
        lesson["id"],
        period_start="2024-01-01",
        period_end="2024-12-31",
        metric="sharpe",
        value=0.8,
        passed=True,
        settings=settings,
    )
    assert result["global_trials"] == 1
    assert count_tests(db, settings) == 1
    with pytest.raises(ValueError) as exc:
        record_test(
            db,
            lesson["id"],
            period_start="2025-06-01",
            period_end="2025-07-01",
            settings=settings,
        )
    assert "holdout" in str(exc.value)


def test_aprobar_aplicar_revertir_reduce_riesgo(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    account = load_accounts()["paper_main"]
    lesson = create_lesson(
        db,
        hypothesis="reducir pérdida diaria",
        evidence="test",
        author="humano",
        action={
            "kind": "reduce_risk",
            "account_id": "paper_main",
            "changes": {"daily_loss_pct": 0.04},
        },
        settings=settings,
    )
    with pytest.raises(ValueError):
        apply_lesson(db, lesson["id"], settings=settings)
    approve(db, lesson["id"], settings=settings)
    applied = apply_lesson(db, lesson["id"], settings=settings)
    assert applied["status"] == "approved"
    assert applied["applied_at"]
    assert own_limits(db, account).daily_loss_pct == pytest.approx(0.04)
    with pytest.raises(ValueError):
        apply_lesson(db, lesson["id"], settings=settings)

    revert_lesson(
        db, lesson["id"], confirm=True, settings=settings, actor="humano"
    )
    later = datetime.now(timezone.utc) + timedelta(days=3)
    assert own_limits(db, account, now=later).daily_loss_pct == pytest.approx(0.05)
    rows = history(db, "paper_main")
    assert any(row["origin"] == "lesson-revert" and abs(row["new_value"] - 0.05) < 1e-9 for row in rows)


def test_auto_aplicar_solo_reduce_riesgo(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    other = create_lesson(
        db,
        hypothesis="otra acción",
        evidence="test",
        author="humano",
        action={"kind": "other", "account_id": "paper_main", "changes": {}},
        settings=settings,
    )
    with pytest.raises(ValueError):
        apply_lesson(db, other["id"], auto=True, settings=settings)
    reduce = create_lesson(
        db,
        hypothesis="reducir riesgo",
        evidence="test",
        author="qwen",
        action={
            "kind": "reduce_risk",
            "account_id": "paper_main",
            "changes": {"daily_loss_pct": 0.03},
        },
        settings=settings,
    )
    result = apply_lesson(db, reduce["id"], auto=True, settings=settings)
    assert result["status"] == "approved"
    assert result["applied_by"] == "auto"
    assert own_limits(db, load_accounts()["paper_main"]).daily_loss_pct == pytest.approx(0.03)


def test_rechazar_y_challenger_no_activa(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    challenger = create_lesson(
        db,
        hypothesis="retador paper",
        evidence="test",
        author="qwen",
        kind="challenger",
        champion="trend-spy",
        challenger="qqq-trend-f13",
        settings=settings,
    )
    assert challenger["status"] == "proposed"
    assert challenger["champion"] == "trend-spy"
    assert challenger["challenger"] == "qqq-trend-f13"
    before = {bot.id: bot.enabled for bot in load_bots()}
    with pytest.raises(ValueError):
        apply_lesson(db, challenger["id"], auto=True, settings=settings)
    reject(db, challenger["id"], reason="sin evidencia", settings=settings)
    assert list_lessons(db, status="rejected", settings=settings)[0]["id"] == challenger["id"]
    assert {bot.id: bot.enabled for bot in load_bots()} == before


def test_learning_api_payload(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    create_lesson(
        db,
        hypothesis="lección api",
        evidence="test",
        author="humano",
        settings=settings,
    )
    data = web.LabData(settings, root=tmp_path, db_path=db, external=False)
    payload = data.learning()
    assert payload["lessons"]
    assert payload["holdout"]["hash"]
    assert payload["trials"] == 0
    assert payload["auto_apply_reduce_risk"] is True
    text = web.INDEX_FILE.read_text(encoding="utf-8")
    assert 'id="view-learning"' in text
    assert 'id="learning-list"' in text


def test_web_learning_aprobar_y_aplicar(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    settings = Settings()
    lesson = create_lesson(        db,
        hypothesis="reducir por panel",
        evidence="test",
        author="humano",
        action={
            "kind": "reduce_risk",
            "account_id": "paper_main",
            "changes": {"daily_loss_pct": 0.04},
        },
        settings=settings,
    )
    data = web.LabData(settings, root=tmp_path, db_path=db, external=False)
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(method: str, path: str, body: dict | None = None, token: str | None = None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        try:
            payload = json.dumps(body).encode("utf-8") if body is not None else None
            headers = {"Content-Type": "application/json"} if payload is not None else {}
            if token:
                headers["X-CSRF-Token"] = token
            if payload is not None:
                headers["Content-Length"] = str(len(payload))
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b"{}")
        finally:
            connection.close()

    try:
        status, session = call("GET", "/api/session")
        assert status == 200
        token = session["csrf"]
        status, approved = call(
            "POST", "/api/learning/approve", {"id": lesson["id"]}, token
        )
        assert status == 200, approved
        assert approved["lesson"]["status"] == "approved"
        status, applied = call(
            "POST", "/api/learning/apply", {"id": lesson["id"], "confirm": True}, token
        )
        assert status == 200, applied
        assert applied["lesson"]["applied_at"]
        assert own_limits(db, load_accounts()["paper_main"]).daily_loss_pct == pytest.approx(0.04)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _seed_outcomes(db: Path) -> None:
    with connect(db) as con:
        for rating, ret in (("Buy", 0.08), ("Sell", -0.05)):
            month = 1 if rating == "Buy" else 2
            for index in range(30):
                con.execute(
                    "INSERT INTO decision_outcomes"
                    "(ts, ticker, decision_date, mode, rating, confidence, return_20d) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        utcnow(),
                        "SPY",
                        f"2026-{month:02d}-{index + 1:02d}",
                        "lite",
                        rating,
                        0.7,
                        ret,
                    ),
                )


def test_weekly_lessons_qwen_solo_redacta(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _seed_outcomes(db)
    settings = Settings()
    result = weekly_lessons(
        db,
        settings,
        min_sample=30,
        draft_fn=lambda evidence: "Hipótesis semanal desde " + evidence[:40],
    )
    assert result["created"]
    assert all(lesson["author"] == "qwen" for lesson in result["created"])
    assert all(lesson["status"] == "proposed" for lesson in result["created"])
    assert all(not lesson.get("applied_at") for lesson in result["created"])
    again = weekly_lessons(
        db,
        settings,
        min_sample=30,
        draft_fn=lambda evidence: result["created"][0]["hypothesis"],
    )
    assert again["created"] == [] or len(again["created"]) < len(result["created"])


def test_weekly_lessons_sin_muestra_o_llm(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    empty = weekly_lessons(db, Settings(), min_sample=30, draft_fn=lambda _: "x")
    assert empty["created"] == []
    assert "Sin datos" in empty["reason"]
    _seed_outcomes(db)
    failed = weekly_lessons(
        db,
        Settings(),
        min_sample=30,
        draft_fn=lambda _: (_ for _ in ()).throw(RuntimeError("LLM caído")),
    )
    assert failed["created"] == []
    assert failed["skipped"]
    assert "Sin datos" in failed["reason"]
