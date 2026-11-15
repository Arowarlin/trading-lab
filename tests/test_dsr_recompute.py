from __future__ import annotations

from pathlib import Path

from tradinglab.db import init_db
from tradinglab.dsr_recompute import build_report, write_report
from tradinglab.learning import count_tests


def test_reporte_lista_ea_f13_y_campanas(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    before = count_tests(db)
    payload = build_report(db)
    assert count_tests(db) == before
    assert payload["read_only"] is True
    entities = [row["entity"] for row in payload["rows"]]
    assert entities == [
        "EA us100-ftmo1",
        "F13 qqq-trend-f13",
        "Campaña 2026-11-A",
        "Campaña 2026-11-B",
    ]
    for row in payload["rows"]:
        assert "dsr_v1" in row
        assert "dsr_local" in row
        assert "dsr_global" in row
        assert "n_trials" in row
        assert "n_sharpes" in row


def test_reporte_escribe_md_y_json_sin_tocar_sqlite(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    payload = build_report(db)
    files = write_report(payload, out_dir=tmp_path / "audit")
    md = Path(files["markdown"]).read_text(encoding="utf-8")
    assert "DSR v2" in md
    assert "Sin datos" in md
    assert "EA us100-ftmo1" in md
    assert Path(files["json"]).exists()
