from __future__ import annotations

from datetime import date

import pytest

from tradinglab.config import Settings
from tradinglab.db import init_db
from tradinglab.learning import count_tests
from tradinglab.lifecycle import (
    LifecycleError,
    evaluate_criteria,
    evaluate_incubation,
    gate_eligible,
    load_config,
    register_candidate,
    report_bot,
    set_final_state,
    start_incubation,
)
from tradinglab.trials import count_incubated


def _evidence(**overrides):
    base = {
        "datacheck_ok": True,
        "n_trades": 20,
        "breakeven_cost_bps": 3.0,
        "calibrated_cost_bps": 2.0,
        "catastrophic_regime": False,
    }
    base.update(overrides)
    return base


def test_gate_eligible_puerta():
    assert gate_eligible(_evidence())["eligible"] is True
    assert gate_eligible(_evidence(datacheck_ok=False))["eligible"] is False
    assert gate_eligible(_evidence(n_trades=5))["eligible"] is False
    assert (
        gate_eligible(_evidence(breakeven_cost_bps=2.0, calibrated_cost_bps=2.0))[
            "eligible"
        ]
        is False
    )
    assert gate_eligible(_evidence(catastrophic_regime=True))["eligible"] is False


def test_start_incubation_congela_y_suma_prueba(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    register_candidate(db, bot="eurusd-range-reversal", asset="EURUSD", evidence=_evidence())
    before = count_tests(db)
    assert count_incubated(db) == 0
    row = start_incubation(db, bot="eurusd-range-reversal", actor="humano")
    assert row["state"] == "incubando"
    assert row["criteria_hash"]
    assert row["frozen_at"]
    assert count_incubated(db) == 1
    assert count_tests(db) == before + 1
    # El hash no cambia al releer.
    assert report_bot(db, "eurusd-range-reversal")["criteria_hash"] == row["criteria_hash"]


def test_gate_rechaza_sin_evidencia(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    register_candidate(db, bot="x", asset="XAUUSD", evidence={"datacheck_ok": False})
    with pytest.raises(LifecycleError, match="no elegible"):
        start_incubation(db, bot="x")


def test_limite_incubando(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    cfg = load_config()
    cfg["max_concurrent"] = 1
    register_candidate(db, bot="a", asset="EURUSD", evidence=_evidence())
    register_candidate(db, bot="b", asset="USDJPY", evidence=_evidence())
    start_incubation(db, bot="a", config=cfg)
    with pytest.raises(LifecycleError, match="límite"):
        start_incubation(db, bot="b", config=cfg)


def test_evaluate_criteria():
    criteria = load_config()["criteria"]
    assert evaluate_criteria(
        {
            "n_trades": 20,
            "sharpe": 0.8,
            "slippage_p95_bps": 5.0,
            "drift_status": "ok",
            "guard_breaches": 0,
        },
        criteria,
    ) == []
    failures = evaluate_criteria(
        {
            "n_trades": 2,
            "sharpe": 0.1,
            "slippage_p95_bps": 50.0,
            "drift_status": "deriva",
            "guard_breaches": 1,
        },
        criteria,
    )
    assert len(failures) >= 4


def test_report_sin_datos(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    register_candidate(db, bot="x", asset="EURUSD", evidence=_evidence())
    start_incubation(db, bot="x", start_date=date.today().isoformat())
    report = report_bot(db, "x", settings=Settings())
    assert report["metrics"]["n_trades"] == 0
    assert report["proposal"] is None
    assert report["failures"]


def test_evaluate_incubation_propone_y_estado_final(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    register_candidate(db, bot="x", asset="EURUSD", evidence=_evidence())
    start_incubation(db, bot="x", start_date="2026-01-01")
    import tradinglab.lifecycle as lifecycle

    monkeypatch.setattr(
        lifecycle,
        "report_bot",
        lambda *a, **k: {
            "bot": "x",
            "state": "incubando",
            "criteria_hash": "hash",
            "evidence": "{}",
            "proposal": "promovible",
            "failures": [],
            "metrics": {"n_trades": 20, "sharpe": 1.0, "expectancy": 10.0},
            "slippage_p95_bps": 3.0,
            "drift": {"status": "ok"},
            "guard_breaches": 0,
        },
    )
    result = evaluate_incubation(db, "x", today=date(2026, 2, 1))
    assert result["state"] == "evaluado" or result.get("state") == "incubando"
    # El estado persistido es evaluado; la propuesta queda en evidencia.
    from tradinglab.db import connect

    with connect(db) as con:
        row = con.execute("SELECT state FROM lifecycle_bots WHERE bot='x'").fetchone()
    assert row["state"] == "evaluado"
    final = set_final_state(db, "x", "promovible", actor="humano", reason="ok")
    assert final["state"] == "promovible"
    with pytest.raises(LifecycleError):
        set_final_state(db, "x", "real", actor="humano")
