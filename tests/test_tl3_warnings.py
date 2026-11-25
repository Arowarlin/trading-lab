"""E3 · Avisos append-only, render y columna en status_table."""

from __future__ import annotations

from tradinglab.tl3 import registry, warnings
from tradinglab.tl3.report import status_table


def _hypothesis(db):
    registry.add_hypothesis(
        "H-2026-012",
        economic_rationale="r",
        behavior="b",
        refs="refs",
        market="cfd",
        instrument_class="cfd",
        timeframe="M5",
        entry="e",
        exit_rule="x",
        benchmark="placebo",
        primary_metric="expectancy_r",
        rejection_rule="rule",
        dev_window={"start": "2020-01-01", "end": "2021-12-31"},
        holdout_window={"start": "2022-01-01", "end": "2022-12-31"},
        holdout_kind="out_of_period",
        structural=registry.structural_hash("x", "cfd", "M5", {}),
        status="draft",
        db_path=db,
    )


def test_add_render_y_orden(tmp_path):
    db = tmp_path / "tl3.db"
    assert warnings.add_warning("ai_trader", "2026-11-25", "T5", "primero", {"n": 1}, "a.md", db_path=db)
    assert warnings.add_warning("ai_trader", "2026-11-25", "TCA", "segundo", {"n": 2}, "b.md", db_path=db)
    items = warnings.warnings_for("ai_trader", db_path=db)
    assert [item["texto"] for item in items] == ["primero", "segundo"]
    text = warnings.render("ai_trader", db_path=db)
    assert text.index("primero") < text.index("segundo")
    assert "a.md" in text and "b.md" in text
    assert warnings.render("desconocido", db_path=db) == "Ninguno"


def test_siembra_idempotente_y_sin_update_delete(tmp_path):
    db = tmp_path / "tl3.db"
    first = warnings.add_warning("ai_trader", "2026-11-25", "T5", "uno", {"n": 1}, "a.md", db_path=db)
    second = warnings.add_warning("ai_trader", "2026-11-25", "T5", "uno", {"n": 1}, "a.md", db_path=db)
    assert first is not None and second is None
    assert len(warnings.all_warnings(db_path=db)) == 1
    assert not hasattr(warnings, "update_warning")
    assert not hasattr(warnings, "delete_warning")


def test_status_table_muestra_avisos(tmp_path):
    db = tmp_path / "tl3.db"
    registry.init_db(db)
    _hypothesis(db)
    warnings.add_warning(
        "ai_trader", "2026-11-25", "TCA", "TCA en cero", {"filas": 68}, "TL3_REPORTS/tca_diagnostico.md", db_path=db
    )
    table = status_table(db)
    assert "Avisos" in table
    assert "1 · 2026-11-25 TCA" in table
    assert "Avisos globales: **1**" in table
