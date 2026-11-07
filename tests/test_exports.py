from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from urllib.parse import quote

import pytest

import tradinglab.exports as exports_mod
from tradinglab import web
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.exports import (
    ExportError,
    export_drift,
    export_journal,
    export_learning,
    list_exports,
    preview_file,
)


def _trade(db: Path) -> None:
    with connect(db) as con:
        for side, ts, price in (
            ("buy", "2026-01-05T15:00:00+00:00", 100.0),
            ("sell", "2026-01-05T16:00:00+00:00", 110.0),
        ):
            cur = con.execute(
                "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot, reason) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (ts, "SPY", side, 1, "market", "filled", "trend-spy", "test"),
            )
            order_id = int(cur.lastrowid)
            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) "
                "VALUES(?,?,?,?,?)",
                (order_id, ts, 1, price, 0.0),
            )


@pytest.fixture()
def report_root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(exports_mod, "ROOT", tmp_path)
    monkeypatch.setattr(
        exports_mod, "EXPORT_DIR", tmp_path / "reports" / "exports"
    )
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    return tmp_path / "reports"


def test_export_journal_csv_html_y_preview(tmp_path: Path, report_root: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _trade(db)
    csv_result = export_journal(db, out_dir=report_root / "exports", fmt="csv")
    assert csv_result["ok"] is True
    assert csv_result["rows"] == 1
    assert Path(csv_result["path"]).is_file()
    content = Path(csv_result["path"]).read_text(encoding="utf-8")
    assert "trend-spy" in content and "pnl" in content
    html_result = export_journal(db, out_dir=report_root / "exports", fmt="html")
    html_text = Path(html_result["path"]).read_text(encoding="utf-8")
    assert "<table>" in html_text
    assert "http://" not in html_text and "https://" not in html_text
    preview = preview_file(csv_result["path"], rows=5)
    assert preview["format"] == "csv"
    assert preview["rows"][0]["bot"] == "trend-spy"
    listed = list_exports(report_root / "exports")
    assert {row["format"] for row in listed} == {"csv", "html"}


def test_export_validacion_y_sin_datos(tmp_path: Path, report_root: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(ExportError):
        export_journal(db, out_dir=tmp_path, fmt="csv")
    with pytest.raises(ExportError):
        export_journal(db, out_dir=report_root / "exports", fmt="pdf")
    learning = export_learning(db, out_dir=report_root / "exports", fmt="csv")
    text = Path(learning["path"]).read_text(encoding="utf-8")
    assert "Sin datos" in text
    assert learning["rows"] == 0


def test_export_drift_y_learning(tmp_path: Path, report_root: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    drift = export_drift(db, out_dir=report_root / "exports", fmt="csv")
    assert drift["rows"] >= 1
    assert "bot" in drift["preview"][0]
    learning = export_learning(db, out_dir=report_root / "exports", fmt="html")
    assert Path(learning["path"]).is_file()
    with pytest.raises(ExportError):
        preview_file(tmp_path / "no-existe.csv")


def test_api_reports_lista_y_previsualiza(tmp_path: Path, report_root: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    _trade(db)
    export = export_journal(db, out_dir=report_root / "exports", fmt="csv")
    data = web.LabData(
        Settings(), root=tmp_path, db_path=db, external=False
    )
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def get(path: str):
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                return response.status, json.loads(response.read() or b"{}")
            finally:
                connection.close()

        status, payload = get("/api/reports")
        assert status == 200
        assert any(row["name"] == Path(export["path"]).name for row in payload["files"])
        status, preview = get(
            "/api/reports/preview?file=" + quote(str(Path(export["path"])))
        )
        assert status == 200
        assert preview["format"] == "csv"
        assert preview["rows"][0]["bot"] == "trend-spy"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
