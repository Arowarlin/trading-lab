"""Guardia de pre-registro: rendimiento solo con campaña aprobada."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab import learning
from tradinglab.db import connect
from tradinglab.discovery import databank, fastbt, fitness, guard, jobs
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.propfund.costs import load_profile


def _setup(frame, *, campaign_id="draft", approved=False) -> jobs.QueueSetup:
    return jobs.QueueSetup(
        instrument="US100",
        timeframe="M5",
        bars=frame,
        campaign_id=campaign_id,
        approved=approved,
    )


def _strategy() -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45"},
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 0.0},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "n": 14, "mult": 2.0},
            "target": {"type": "rr", "rr": 1.5},
            "time_exit_bars": 24,
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def _prepared(frame, setup):
    cost = fastbt.cost_from_profile(load_profile("CFD-001", "US100", firm="ftmo"))
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
    )
    return cost, fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))


def test_fitness_rechaza_sin_aprobar(monkeypatch) -> None:
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", False)
    frame = synthetic_frame(years=0.2, seed=3)
    setup = _setup(frame)
    cost, prepared = _prepared(frame, setup)
    with pytest.raises(guard.UnapprovedPerformanceError, match="sin register"):
        fitness.evaluate(
            _strategy(), frame, cost, setup, prepared, campaign_id="draft"
        )


def test_fitness_permite_aprobada(monkeypatch) -> None:
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", False)
    frame = synthetic_frame(years=0.2, seed=3)
    setup = _setup(frame, campaign_id="approved", approved=True)
    cost, prepared = _prepared(frame, setup)
    result = fitness.evaluate(
        _strategy(),
        frame,
        cost,
        setup,
        prepared,
        campaign_id="approved",
        approved=True,
    )
    assert result["trades_count"] >= 0


def test_drift_rechaza_sin_aprobar(monkeypatch) -> None:
    from tradinglab.discovery import drift

    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", False)
    with pytest.raises(guard.UnapprovedPerformanceError, match="sin register"):
        drift.percentile(
            strategy_expectancy=0.1,
            trades=10,
            long_fraction=0.5,
            mean_bars=3.0,
            r_long=object(),  # no se llega a usar: la guardia corta antes
            r_short=object(),
            eligible=object(),
        )


def test_record_informal_suma_exacto_y_traza(tmp_path) -> None:
    db = tmp_path / "lab.db"
    discovery = tmp_path / "discovery.db"
    databank.init_databank(discovery)
    learning.init_learning(db)
    before = learning.count_tests(db, discovery_db=discovery)
    with pytest.raises(PermissionError, match="approved-by-operator"):
        learning.record_informal(
            db,
            n=18,
            reason="R9: miradas informativas",
            approved_by_operator=False,
        )
    assert learning.count_tests(db, discovery_db=discovery) == before
    row = learning.record_informal(
        db,
        n=18,
        reason="R9: miradas informativas",
        approved_by_operator=True,
    )
    assert row["n"] == 18
    assert row["reason"] == "R9: miradas informativas"
    assert row["count_tests"] == before + 18
    assert learning.count_tests(db, discovery_db=discovery) == before + 18


def test_cli_record_informal_sin_flag_no_escribe(tmp_path, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    discovery = tmp_path / "discovery.db"
    databank.init_databank(discovery)
    learning.init_learning(db)
    monkeypatch.setattr(learning, "CANONICAL_DISCOVERY_DB", discovery)
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.app,
        [
            "learning",
            "record-informal",
            "--n",
            "18",
            "--reason",
            "prueba",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code == 0
    assert "Sin --approved-by-operator" in result.output
    assert learning.count_tests(db, discovery_db=discovery) == 0

    result = runner.invoke(
        cli_mod.app,
        [
            "learning",
            "record-informal",
            "--n",
            "18",
            "--reason",
            "R9: miradas informativas",
            "--approved-by-operator",
            "--db",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    assert learning.count_tests(db, discovery_db=discovery) == 18
    with connect(db) as con:
        row = con.execute("SELECT n, reason FROM informal_trials").fetchone()
    assert row["n"] == 18
    assert row["reason"] == "R9: miradas informativas"
