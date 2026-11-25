"""T3 · Registro y candados."""

from __future__ import annotations

from tradinglab.tl3 import gates, registry
from tradinglab.tl3.report import status_table


def test_identidad_bloquea_hash_rechazado_y_permite_parent(tmp_path):
    db = tmp_path / "tl3.db"
    structural = registry.structural_hash("fx_fix", "cfd", "H1", {"x": 1})
    registry.init_db(db)
    registry.add_hypothesis(
        "H-1",
        economic_rationale="r",
        behavior="b",
        refs="refs",
        market="cfd",
        instrument_class="cfd",
        timeframe="H1",
        entry="e",
        exit_rule="x",
        benchmark="placebo",
        primary_metric="expectancy_r",
        rejection_rule="rule",
        dev_window={"start": "2010-01-01", "end": "2014-12-31"},
        holdout_window={"start": "2015-01-01", "end": "2016-12-31"},
        holdout_kind="out_of_period",
        structural=structural,
        status="rejected",
        rejection_reason="gross_lt_cost",
        db_path=db,
    )

    blocked = gates.identity_gate(structural, db_path=db)
    allowed = gates.identity_gate(structural, parent_id="H-1", db_path=db)

    assert blocked["ok"] is False
    assert allowed["ok"] is True


def test_holdout_solapado_se_rechaza(tmp_path):
    db = tmp_path / "tl3.db"
    registry.init_db(db)
    registry.add_sample(
        "US100", "M5", "2020-01-01", "2021-12-31", "H-1", "dev", db_path=db
    )

    overlap = gates.holdout_gate(
        "US100", "M5", "2021-06-01", "2022-06-01", db_path=db
    )
    free = gates.holdout_gate(
        "US100", "M5", "2022-01-01", "2022-12-31", db_path=db
    )

    assert overlap["ok"] is False
    assert free["ok"] is True


def test_experimento_con_otro_hash_es_invalid():
    current = registry.thresholds_hash()
    assert gates.experiment_valid(current)["status"] == "valid"
    assert gates.experiment_valid("otro-hash")["status"] == "invalid"


def test_potencia_y_coste():
    assert gates.power_gate(0.10, 1.0, 625)["ok"] is True
    assert gates.power_gate(0.05, 1.0, 100)["ok"] is False
    assert gates.cost_gate(10.0, 5.0)["ok"] is True
    assert gates.cost_gate(9.0, 5.0)["ok"] is False


def test_add_status_y_tabla(tmp_path):
    db = tmp_path / "tl3.db"
    registry.init_db(db)
    registry.add_hypothesis(
        "H-1",
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
    registry.add_status("H-1b", "H-1", "rejected", "holdout_fail", db_path=db)
    table = status_table(db)
    assert "H-1b" in table
    assert "holdout_fail" in table
    with registry.connect(db) as con:
        parent = con.execute("SELECT status FROM hypotheses WHERE hypothesis_id='H-1'").fetchone()
    assert parent["status"] == "draft"
