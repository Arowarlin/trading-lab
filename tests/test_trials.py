from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradinglab.db import connect, init_db
from tradinglab.learning import count_tests, create_lesson, get_lesson
from tradinglab.trials import (
    TrialsError,
    budget_status,
    discarded_trials,
    discarded_warning,
    fingerprint,
    list_trials,
    record_trial,
    weekly_attempts,
)


def _trial(db, **kwargs):
    base = {
        "family": "orb",
        "hypothesis": "La momentum posterior a la apertura tiene ventaja.",
        "symbol": "EURUSD",
        "params": {"range_bars": 4},
        "window_start": "2026-01-01",
        "window_end": "2026-06-30",
        "outcome": "failed",
        "reason": "DSR 0%",
        "source": "sweep",
        "run_id": "run1",
    }
    base.update(kwargs)
    return record_trial(db, **base)


def test_columnas_dsr_v2_son_aditivas_y_no_cuentan(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    before = count_tests(db)
    old = _trial(db, counted=False)
    assert old["dsr_v2"] is None
    assert old["metric_version"] is None

    new = _trial(db, counted=False, dsr_v2=0.83, metric_version="dsr_v2")
    assert new["dsr_v2"] == pytest.approx(0.83)
    assert new["metric_version"] == "dsr_v2"
    assert count_tests(db) == before


def test_registra_tambien_las_fallidas(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    before = count_tests(db)
    _trial(db, outcome="failed", reason="DSR 0%")
    _trial(db, outcome="passed", reason="", params={"range_bars": 8}, run_id="run1")
    rows = list_trials(db)
    assert len(rows) == 2
    assert {row["outcome"] for row in rows} == {"failed", "passed"}
    failed = next(row for row in rows if row["outcome"] == "failed")
    assert failed["reason"]
    assert failed["hypothesis"]
    assert failed["symbol"] == "EURUSD"
    # Cada intento suma al contador único del DSR.
    assert count_tests(db) == before + 2


def test_aviso_al_reoptimizar_familia_descartada(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    _trial(db, family="orb", outcome="failed", reason="DSR 0%")
    warning = discarded_warning(
        db,
        family="orb",
        symbol="EURUSD",
        window_start="2026-01-01",
        window_end="2026-06-30",
    )
    assert warning and "orb" in warning and "EURUSD" in warning
    # Otra ventana: no avisa.
    assert (
        discarded_warning(
            db,
            family="orb",
            symbol="EURUSD",
            window_start="2025-01-01",
            window_end="2025-06-30",
        )
        is None
    )
    assert len(discarded_trials(db, family="orb", symbol="EURUSD")) == 1


def test_presupuesto_semanal_por_activo(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    budget = tmp_path / "budget.yaml"
    budget.write_text(
        "max_attempts_per_week_per_asset: 2\nassets:\n  EURUSD: 2\n",
        encoding="utf-8",
    )
    now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    assert budget_status(db, "EURUSD", now, budget)["used"] == 0
    _trial(db, run_id="r1")
    _trial(db, run_id="r2")
    status = budget_status(db, "EURUSD", now, budget)
    assert status["used"] == 2
    assert weekly_attempts(db, "EURUSD", now) == 2
    assert status["exceeded"] is True
    assert status["remaining"] == 0
    # Otro activo no comparte presupuesto.
    assert budget_status(db, "USDJPY", now, budget)["used"] == 0


def test_hipotesis_nace_en_leccion_proposed(tmp_path):
    db = tmp_path / "lab.db"
    lesson = create_lesson(db, hypothesis="hipótesis nueva de Qwen", author="qwen")
    assert lesson["status"] == "proposed"
    row = record_trial(
        db,
        family="orb",
        hypothesis=lesson["hypothesis"],
        symbol="EURUSD",
        params={},
        outcome="failed",
        reason="DSR 0%",
        source="lesson",
        lesson_id=lesson["id"],
    )
    assert row["lesson_id"] == lesson["id"]
    # Qwen redacta, no ejecuta: la lección sigue proposed.
    assert get_lesson(db, lesson["id"])["status"] == "proposed"


def test_outcome_invalido_se_rechaza(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(TrialsError):
        _trial(db, outcome="promovido")


def test_migracion_no_pierde_historial(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO optimization_trials"
            "(ts, study, trial, value, period_start, period_end) "
            "VALUES(?,?,?,?,?,?)",
            ("2026-01-01", "s", 1, 0.1, "2025-01-01", "2025-12-31"),
        )
    init_db(db)
    with connect(db) as con:
        assert (
            con.execute("SELECT COUNT(*) AS n FROM optimization_trials").fetchone()["n"]
            == 1
        )
        assert (
            con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='strategy_trials'"
            ).fetchone()
            is not None
        )


def test_fingerprint_estable():
    first = fingerprint("orb", "EURUSD", "2026-01-01", "2026-06-30")
    assert first == fingerprint("ORB", "eurusd", "2026-01-01", "2026-06-30")
    assert first != fingerprint("orb", "EURUSD", "2026-01-01", "2026-07-30")
