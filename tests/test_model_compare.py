from __future__ import annotations

from datetime import date

import pytest

from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.model_compare import (
    ModelCompareError,
    comparisons,
    report,
    run_comparison,
)


def test_comparacion_dos_modelos_y_reporte(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    calls: list[str] = []

    def runner(ticker, day, settings, model):
        calls.append(model)
        rating = "Buy" if model == "model-a" else "Overweight"
        confidence = 0.6 if model == "model-a" else 0.8
        return {
            "rating": rating,
            "confidence": confidence,
            "elapsed_s": 1.5,
        }

    row = run_comparison(
        db,
        "spy",
        ["model-a", "model-b"],
        settings=Settings(),
        runner=runner,
    )
    assert calls == ["model-a", "model-b"]
    assert row["ticker"] == "SPY"
    assert row["rating_a"] == "Buy"
    assert row["rating_b"] == "Overweight"
    assert row["agreement"] == 0
    assert row["prompt_hash_a"] != row["prompt_hash_b"]
    summary = report(db)
    assert summary["n"] == 1
    assert summary["agreement_rate"] == pytest.approx(0.0)
    assert summary["mean_confidence_diff"] == pytest.approx(0.2)
    assert summary["insufficient"] is True
    assert "muestra insuficiente" in summary["sample_warning"]
    assert {item["model"] for item in summary["by_model"]} == {
        "model-a",
        "model-b",
    }
    assert len(comparisons(db)) == 1


def test_comparacion_exige_dos_modelos_distintos(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(ModelCompareError, match="exactamente dos"):
        run_comparison(db, "SPY", ["solo"], settings=Settings())
    with pytest.raises(ModelCompareError, match="distintos"):
        run_comparison(db, "SPY", ["a", "a"], settings=Settings())


def test_comparacion_rechaza_fecha_pasada(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(ModelCompareError, match="fecha de hoy"):
        run_comparison(
            db,
            "SPY",
            ["a", "b"],
            day="2026-01-05",
            settings=Settings(),
        )


def test_error_de_modelo_se_sanea(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)

    def runner(ticker, day, settings, model):
        if model == "b":
            raise RuntimeError("token-abc123 no válido")
        return {"rating": "Hold", "confidence": 0.5, "elapsed_s": 1.0}

    row = run_comparison(
        db, "SPY", ["a", "b"], settings=Settings(), runner=runner
    )
    assert row["rating_a"] == "Hold"
    assert row["rating_b"] is None
    assert row["error_b"] == "[redacted] no válido"
    assert report(db)["by_model"][1]["errors"] == 1
    with connect(db) as con:
        count = con.execute(
            "SELECT COUNT(*) AS n FROM lite_model_comparisons"
        ).fetchone()["n"]
    assert count == 1
    assert date.today().isoformat() == row["decision_date"]
