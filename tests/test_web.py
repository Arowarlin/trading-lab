from __future__ import annotations

import json
import threading
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
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
    assert "chart-empty" in text
    assert "research-intraday" in text
    assert "research-clusters" in text
    assert "research-portfolio" in text
    assert "research-costs" in text
    assert "research-profiles" in text
    assert "view-fund" in text
    assert "view-journal" in text
    assert "journal-apply" in text
    assert "journal-summary" in text
    assert "view-operator" in text
    assert "console-audit" in text
    assert "fund-save" in text
    assert "fund-killswitch" in text


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
    (runs_dir / "lite_EURUSD_2026-11-06.json").write_text(
        json.dumps(
            {
                "mode": "lite",
                "ticker": "EURUSD",
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
    assert dry == []


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
    (runs_dir / "ta_EURUSD_2026-11-05.json").write_text(
        json.dumps({"ok": False, "ticker": "EURUSD", "error": "Connection error"}),
        encoding="utf-8",
    )

    runs = _data(tmp_path).agent_runs()
    assert runs[0]["ok"] is False
    assert runs[0]["rating"] == "ERROR"
    assert "Connection error" in runs[0]["decision"]


def test_research_usa_informes_ea_lab(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "research" / "ea_us500_nyopen"
    report_dir.mkdir(parents=True)
    (report_dir / "validation.json").write_text(
        json.dumps(
            {
                "ea": "us500-nyopen",
                "symbol": "US500.cash",
                "generated_at": "2026-11-19T21:42:32+00:00",
                "verdict": "PASA",
                "pre_registration_hash": "abc123def456",
                "sharpe": 1.4,
                "dsr_local": 0.97,
                "dsr_global": 0.93,
                "n_trials": 8,
                "relative_cost": 0.11,
                "verdict_reasons": [],
            }
        ),
        encoding="utf-8",
    )
    report = _data(tmp_path).research(limit=1)
    assert report["candidates"] == 1
    assert report["profiles"][0]["label"] == "us500-nyopen"
    assert report["profiles"][0]["status"] == "pasa"
    assert "abc123def456"[:12] in report["profiles"][0]["notes"]
    assert report["config"]["symbols"] == ["US500.cash"]
    assert report["dsr_n_trials"] is not None


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


def test_market_lee_mt5(tmp_path: Path, monkeypatch) -> None:
    rows = [
        {
            "instrument": "US100",
            "symbol": "US100",
            "close": 27500.0,
            "return_1d": 0.004,
            "return_5d": 0.01,
            "return_20d": 0.03,
            "trend": "up",
            "spark": [27000, 27500],
            "as_of": "2026-11-19",
            "status": "ok",
        }
    ]
    monkeypatch.setattr(
        "tradinglab.propfund.market.market_snapshot",
        lambda: {"rows": rows, "error": None, "status": "ok"},
    )
    market = _data(tmp_path).market()
    assert market["count"] == 1
    assert market["source"] == "mt5"
    row = market["rows"][0]
    assert row["instrument"] == "US100"
    assert row["close"] == pytest.approx(27500.0)
    assert row["return_1d"] == pytest.approx(0.004)
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
            (utcnow(), "EURUSD", "2026-01-05", "lite", "Buy", 0.10),
        )
    monkeypatch.setattr("tradinglab.decisions.trend_target_at", lambda *a, **k: 1.0)
    data = _data(tmp_path, db=db)
    decision = data.decisions()
    assert decision["total"] == 1
    assert decision["rows"][0]["rating"] == "Buy"
    assert decision["rows"][0]["hit_rate_20d"] == pytest.approx(1.0)
    assert decision["by_source"][0]["source"] == "lite"
    assert decision["by_source"][0]["n"] == 1
    comparison = data.decisions_compare()
    assert comparison["matched_n"] == 1
    assert comparison["matched_llm_mean_20d"] == pytest.approx(0.10)
    assert comparison["matched_buy_hold_mean_20d"] == pytest.approx(0.10)
    assert comparison["matched_trend_mean_20d"] == pytest.approx(0.10)


def test_agent_comparisons_y_lifecycle_web(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO agent_comparisons"
            "(ts, ticker, decision_date, lite_rating, deep_rating, agreement) "
            "VALUES(?,?,?,?,?,?)",
            (utcnow(), "SPY", "2026-01-05", "Buy", "Buy", 1),
        )
        con.execute(
            "INSERT INTO lifecycle_bots"
            "(bot, asset, state, created_at, updated_at, evidence) "
            "VALUES(?,?,?,?,?,?)",
            ("bot-x", "EURUSD", "candidato", utcnow(), utcnow(), "{}"),
        )
    data = _data(tmp_path, db=db)
    comparisons = data.agent_comparisons()
    assert comparisons["n"] == 1
    assert comparisons["agreement_rate"] == pytest.approx(1.0)
    lifecycle = data.lifecycle()
    assert lifecycle["count"] == 1
    assert lifecycle["bots"][0]["bot"] == "bot-x"
    assert lifecycle["max_concurrent"] == 3
    assert lifecycle["config"]["criteria"]["min_trades"] == 10


def test_repo_audit_licencias(tmp_path: Path) -> None:
    audit = _data(tmp_path).repo_audit()
    assert len(audit["repos"]) == 3
    licenses = {repo["id"]: repo["license"] for repo in audit["repos"]}
    assert licenses["autohedge"] == "MIT"
    assert licenses["vibe-trading"] == "MIT"
    assert licenses["fincept-terminal"] == "AGPL-3.0"


def test_build_id_cambia_con_ui(tmp_path: Path) -> None:
    from tradinglab.web import compute_build_id

    (tmp_path / "src" / "tradinglab" / "webui").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    index = tmp_path / "src" / "tradinglab" / "webui" / "index.html"
    index.write_text("<html>uno</html>", encoding="utf-8")
    first = compute_build_id(tmp_path)
    index.write_text("<html>dos</html>", encoding="utf-8")
    assert compute_build_id(tmp_path) != first


def test_research_muestra_holdout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "holdout_usage",
        lambda db: {"reads": 3, "configs": 1, "last": None, "top": []},
    )
    report = _data(tmp_path).research()
    assert report["holdout"]["reads"] == 3


def test_regime_payload(tmp_path: Path, monkeypatch) -> None:
    from tradinglab import regimes
    rows = 420
    close = 100.0 + 0.2 * np.arange(rows)
    frame = pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=pd.bdate_range("2019-01-01", periods=rows),
    )
    monkeypatch.setattr(
        regimes, "load_cached", lambda symbol, cache_dir: (frame, Path("qqq.parquet"))
    )
    payload = _data(tmp_path).regime("QQQ")
    assert payload["status"] == "ok"
    assert payload["current"]["label"] == "trend_up"
    assert payload["proposed_selector"]["status"] == "proposed"
    assert payload["proposed_selector"]["enabled"] is False


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
def test_overview_datos_para_dashboard(tmp_path: Path, monkeypatch) -> None:
    prop = {
        "ok": True,
        "summary": {"firms": 1, "accounts": 1, "strategies": 1},
        "accounts": [
            {"id": "CFD-001", "template": False, "size": 100000, "state": "DEMO"}
        ],
        "exposure": {
            "ok": True,
            "generated_at": "2026-11-19T20:00:00+00:00",
            "totals": {"gross_notional_usd": 12000.0},
            "accounts": [
                {
                    "ok": True,
                    "snapshot": {"equity": 101500.0, "balance": 100000.0},
                }
            ],
            "positions": [],
        },
        "protection": {"ok": True, "status": "OK", "groups": {}},
        "firms": [],
        "strategies": [],
        "assignments": [],
        "instruments": [],
        "warnings": [],
    }
    monkeypatch.setattr(web.LabData, "propfund", lambda self: prop)
    overview = _data(tmp_path).overview()
    account = overview["account"]
    assert account["equity"] == pytest.approx(101500.0)
    assert account["return_pct"] == pytest.approx(0.015)
    assert account["equity_curve"][0]["equity"] == pytest.approx(101500.0)
    assert overview["propfund"]["ok"] is True
    assert overview["meta"]["mode"] == "PAPER/DEMO"
    assert "bots" in overview


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
        assert health["build"]

        with urllib.request.urlopen(f"{base}/api/overview", timeout=5) as response:
            overview = json.load(response)
        assert overview["meta"]["mode"] == "PAPER/DEMO"
        assert overview["meta"]["build"] == health["build"]
        assert overview["account"]["equity"] is None or overview["account"]["equity"] >= 0
        assert "propfund" in overview
        assert "market" in overview and "calendar" in overview and "repos" in overview
        assert "agent_comparisons" in overview and "lifecycle" in overview

        for path in ("/api/market", "/api/calendar", "/api/decisions", "/api/decisions/compare", "/api/repos", "/api/research/horizons", "/api/research/intraday", "/api/research/clusters", "/api/research/portfolio", "/api/research/costs", "/api/instruments", "/api/markets", "/api/models"):
            with urllib.request.urlopen(f"{base}{path}", timeout=5) as response:
                payload = json.load(response)
            assert isinstance(payload, dict)
            if path == "/api/markets":
                assert payload["pilots"]["count"] >= 3
            if path == "/api/instruments":
                assert payload["validation"]["ok"] is True
            if path == "/api/models":
                assert "qlib" in payload

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
