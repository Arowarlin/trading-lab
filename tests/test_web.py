from __future__ import annotations

import json
import threading
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from tradinglab import web
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow
from tradinglab.intel.calendar import add_calendar_event


def _data(tmp_path: Path, db: Path | None = None) -> web.LabData:
    return web.LabData(
        Settings(),
        root=tmp_path,
        db_path=db or tmp_path / "missing.db",
        external=False,
    )


def test_index_disponible() -> None:
    assert web.INDEX_FILE.exists()
    text = web.INDEX_FILE.read_text(encoding="utf-8")
    assert "TradingLab Console" in text
    assert "/api/overview" in text
    assert "equity-canvas" in text
    assert "view-market" in text
    assert "view-repos" in text
    assert "command-palette" in text
    assert "research-horizons" in text
    assert "research-intraday" in text
    assert "research-clusters" in text


def test_account_lee_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO positions(ticker, qty, avg_price, updated_at) VALUES(?,?,?,?)",
            ("SPY", 10.0, 500.0, utcnow()),
        )
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            (utcnow(), 96_000.0, 5_000.0, 101_000.0),
        )
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status, bot) VALUES(?,?,?,?,?,?)",
            (utcnow(), "SPY", "buy", 10.0, "filled", "trend-spy"),
        )

    account = _data(tmp_path, db).account()
    assert account["equity"] == pytest.approx(101_000.0)
    assert account["cash"] == pytest.approx(96_000.0)
    assert account["positions"][0]["ticker"] == "SPY"
    assert account["orders"][0]["status"] == "filled"
    assert account["equity_curve"][-1]["equity"] == pytest.approx(101_000.0)
    assert account["return_pct"] == pytest.approx(0.01)


def test_agent_runs_y_dryruns(tmp_path: Path) -> None:
    runs_dir = tmp_path / "data" / "agent_runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "lite_NVDA_2026-11-06.json").write_text(
        json.dumps(
            {
                "mode": "lite",
                "ticker": "NVDA",
                "date": "2026-11-06",
                "rating": "Hold",
                "confidence": 0.55,
                "decision": "tesis",
                "elapsed_s": 84.7,
            }
        ),
        encoding="utf-8",
    )

    dry_dir = tmp_path / "data" / "dryrun"
    dry_dir.mkdir(parents=True)
    (dry_dir / "dryrun_20261107_021504.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-11-07T02:15:04+00:00",
                "broker": "paper",
                "actions": [
                    {"bot": "trend-spy", "ticker": "SPY", "status": "sin_cambios", "delta": 0},
                    {"bot": "trend-spy", "ticker": "QQQ", "status": "sin_cambios", "delta": 0},
                ],
            }
        ),
        encoding="utf-8",
    )

    data = _data(tmp_path)
    runs = data.agent_runs()
    assert runs[0]["mode"] == "lite"
    assert runs[0]["rating"] == "Hold"
    assert runs[0]["confidence"] == pytest.approx(0.55)

    dry = data.dryruns()
    assert dry[0]["counts"] == {"sin_cambios": 2}


def test_agent_report_lee_el_markdown(tmp_path: Path) -> None:
    runs_dir = tmp_path / "data" / "agent_runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "ta_NVDA_2026-11-06.json").write_text(
        json.dumps(
            {
                "ok": True,
                "ticker": "NVDA",
                "rating": "REVIEW",
                "reports_path": "2026-11-06/complete_report.md",
            }
        ),
        encoding="utf-8",
    )
    report = tmp_path / "2026-11-06"
    report.mkdir()
    (report / "complete_report.md").write_text("# Informe\nTesis completa.", encoding="utf-8")

    data = _data(tmp_path)
    payload = data.agent_report("ta_NVDA_2026-11-06.json")
    assert payload["exists"] is True
    assert "Tesis completa" in payload["content"]

    with pytest.raises(FileNotFoundError):
        data.agent_report("../lab.db")


def test_agent_run_fallido_marca_error(tmp_path: Path) -> None:
    runs_dir = tmp_path / "data" / "agent_runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "ta_NVDA_2026-11-05.json").write_text(
        json.dumps({"ok": False, "ticker": "NVDA", "error": "Connection error"}),
        encoding="utf-8",
    )

    runs = _data(tmp_path).agent_runs()
    assert runs[0]["ok"] is False
    assert runs[0]["rating"] == "ERROR"
    assert "Connection error" in runs[0]["decision"]


def test_research_usa_ultimo_informe(tmp_path: Path) -> None:
    research = tmp_path / "reports" / "research"
    research.mkdir(parents=True)
    (research / "latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-11-07T00:42:30+00:00",
                "candidates": 2,
                "results": [
                    {"symbol": "QQQ", "strategy": "trend", "score": 0.6},
                    {"symbol": "SPY", "strategy": "trend", "score": 0.5},
                ],
                "proposals": [{"symbol": "QQQ", "enabled": False}],
                "near_misses": [],
                "pbo": {"pbo": 0.2, "verdict": "ok"},
                "walk_forward": {"verdict": "ok", "stitched_sharpe": 0.8},
            }
        ),
        encoding="utf-8",
    )
    (research / "proposals.json").write_text(
        json.dumps({"proposals": [{"symbol": "QQQ", "enabled": False}]}),
        encoding="utf-8",
    )
    (research / "horizons.json").write_text(
        json.dumps({"top": 1, "firms": []}),
        encoding="utf-8",
    )

    report = _data(tmp_path).research(limit=1)
    assert report["candidates"] == 2
    assert len(report["results"]) == 1
    assert report["proposals"][0]["enabled"] is False
    assert report["pbo"]["verdict"] == "ok"
    assert report["walk_forward"]["verdict"] == "ok"
    assert report["horizons"]["top"] == 1


def test_tail_log_no_permite_salir_de_logs(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "dryrun.log").write_text("línea uno\nlínea dos\n", encoding="utf-8")
    (logs / "deep_test.log").write_text("hola\r\nEXIT=0\r\n", encoding="utf-16")
    (tmp_path / "secreto.txt").write_text("no debe leerse", encoding="utf-8")

    data = _data(tmp_path)
    assert "línea dos" in data.tail_log("dryrun.log")["content"]
    utf16 = data.tail_log("deep_test.log")["content"]
    assert "hola" in utf16 and "EXIT=0" in utf16
    assert data.deep_logs()[0]["running"] is False
    with pytest.raises(FileNotFoundError):
        data.tail_log("../secreto.txt")


def test_accion_valida_ticker(tmp_path: Path) -> None:
    data = _data(tmp_path)
    action, error = data.start_action("agent", "--help")
    assert action is None
    assert "inválido" in (error or "")


def test_market_lee_cache_local(tmp_path: Path) -> None:
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True)
    close = [100 + i for i in range(40)]
    idx = pd.bdate_range("2026-01-01", periods=40)
    frame = pd.DataFrame({"close": close}, index=idx)
    frame.to_parquet(cache / "SPY__2015-01-01__2026-11-07.parquet")

    market = _data(tmp_path).market()
    assert market["count"] == 1
    assert market["error"] is None
    row = market["rows"][0]
    assert row["symbol"] == "SPY"
    assert row["close"] == pytest.approx(139.0)
    assert row["return_1d"] == pytest.approx(1 / 138)
    assert len(row["spark"]) == 40
    assert market["breadth"]["up"] == 1


def test_calendar_lee_macro_events(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    future = datetime.now(UTC) + timedelta(days=5)
    add_calendar_event(db, event="FOMC", ts_utc=future, importance="high")
    calendar = _data(tmp_path, db=db).calendar()
    assert calendar["status"] == "ok"
    assert calendar["count"] == 1
    assert calendar["events"][0]["event"] == "FOMC"


def test_decisions_resume_rating(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO decision_outcomes"
            "(ts, ticker, decision_date, mode, rating, return_20d) VALUES(?,?,?,?,?,?)",
            (utcnow(), "SPY", "2026-01-05", "lite", "Buy", 0.10),
        )
    monkeypatch.setattr("tradinglab.decisions.trend_target_at", lambda *a, **k: 1.0)
    data = _data(tmp_path, db=db)
    decision = data.decisions()
    assert decision["total"] == 1
    assert decision["rows"][0]["rating"] == "Buy"
    assert decision["rows"][0]["hit_rate_20d"] == pytest.approx(1.0)
    comparison = data.decisions_compare()
    assert comparison["matched_n"] == 1
    assert comparison["matched_llm_mean_20d"] == pytest.approx(0.10)
    assert comparison["matched_buy_hold_mean_20d"] == pytest.approx(0.10)
    assert comparison["matched_trend_mean_20d"] == pytest.approx(0.10)


def test_repo_audit_licencias(tmp_path: Path) -> None:
    audit = _data(tmp_path).repo_audit()
    assert len(audit["repos"]) == 3
    licenses = {repo["id"]: repo["license"] for repo in audit["repos"]}
    assert licenses["autohedge"] == "MIT"
    assert licenses["vibe-trading"] == "MIT"
    assert licenses["fincept-terminal"] == "AGPL-3.0"


def test_research_detail_lee_artefacto(tmp_path: Path) -> None:
    artifacts = tmp_path / "reports" / "research" / "artifacts"
    artifacts.mkdir(parents=True)
    idx = pd.bdate_range("2026-01-01", periods=20)
    pd.DataFrame(
        {
            "equity": [100.0, 102.0, 101.0, 105.0] + [105.0] * 16,
            "buy_hold": [100.0, 101.0, 100.0, 103.0] + [103.0] * 16,
        },
        index=idx,
    ).to_parquet(artifacts / "test.parquet")
    data = _data(tmp_path).research_detail("artifacts/test.parquet")
    assert data["ok"] is True
    assert data["rows"] == 20
    assert len(data["points"]) == 20
    assert data["stats"]["total_return"] == pytest.approx(0.05)
    assert data["stats"]["buy_hold_total_return"] == pytest.approx(0.03)
    assert data["stats"]["max_drawdown"] < 0
    assert data["points"][-1]["equity"] == pytest.approx(105.0)

    with pytest.raises(ValueError):
        _data(tmp_path).research_detail("../secret.parquet")
    with pytest.raises(FileNotFoundError):
        _data(tmp_path).research_detail("artifacts/missing.parquet")


@pytest.mark.network
def test_servidor_http_responde(tmp_path: Path) -> None:
    artifacts = tmp_path / "reports" / "research" / "artifacts"
    artifacts.mkdir(parents=True)
    idx = pd.bdate_range("2026-01-01", periods=5)
    pd.DataFrame(
        {"equity": [100, 101, 102, 103, 104], "buy_hold": [100, 100, 101, 102, 103]},
        index=idx,
    ).to_parquet(artifacts / "test.parquet")
    data = _data(tmp_path)
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as response:
            health = json.load(response)
        assert health["ok"] is True

        with urllib.request.urlopen(f"{base}/api/overview", timeout=5) as response:
            overview = json.load(response)
        assert overview["meta"]["mode"] == "paper"
        assert overview["account"]["equity"] == pytest.approx(100_000.0)
        assert "market" in overview and "calendar" in overview and "repos" in overview

        for path in ("/api/market", "/api/calendar", "/api/decisions", "/api/decisions/compare", "/api/repos", "/api/research/horizons", "/api/research/intraday", "/api/research/clusters"):
            with urllib.request.urlopen(f"{base}{path}", timeout=5) as response:
                payload = json.load(response)
            assert isinstance(payload, dict)

        with urllib.request.urlopen(
            f"{base}/api/research/detail?artifact=artifacts/test.parquet", timeout=5
        ) as response:
            detail = json.load(response)
        assert detail["ok"] is True
        assert len(detail["points"]) == 5
        assert detail["stats"]["total_return"] == pytest.approx(0.04)

        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "<title>TradingLab Console</title>" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
