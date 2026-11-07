from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow


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

    report = _data(tmp_path).research(limit=1)
    assert report["candidates"] == 2
    assert len(report["results"]) == 1
    assert report["proposals"][0]["enabled"] is False
    assert report["pbo"]["verdict"] == "ok"
    assert report["walk_forward"]["verdict"] == "ok"


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


@pytest.mark.network
def test_servidor_http_responde(tmp_path: Path) -> None:
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

        with urllib.request.urlopen(f"{base}/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "<title>TradingLab Console</title>" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
