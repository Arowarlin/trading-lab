"""Feasibility: solo operaciones/coste/tiempo, sin DSR y sin OOS."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tradinglab.discovery import campaigns, databank, engine, feasibility
from tradinglab.learning import count_tests

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}


def _grid(tmp_path: Path) -> tuple[Path, str]:
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=20261122)
    campaign = campaigns.register_synthetic(
        frame,
        instrument="US100.CASH",
        template="intraday_momentum_close_v2",
        profile="small",
        segments=SEGMENTS,
        seed=20261122,
        campaign_id="feas-grid",
        mode="grid",
        db_path=db,
    )
    return db, campaign["campaign_id"]


def _counts(db: Path, campaign_id: str) -> tuple[int, int, int, int]:
    with sqlite3.connect(db) as con:
        jobs = con.execute(
            "SELECT COUNT(*) FROM disc_jobs WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()[0]
    return (
        databank.count_evaluations(campaign_id, db_path=db),
        databank.count_strategies(campaign_id, db_path=db),
        int(jobs),
        count_tests(db.parent / "lab.db", discovery_db=db),
    )


def test_feasibility_no_escribe_dsr_ni_lee_oos(tmp_path: Path, monkeypatch) -> None:
    db, campaign_id = _grid(tmp_path)
    before = _counts(db, campaign_id)

    def _no_holdout(*args, **kwargs):
        raise AssertionError("feasibility no puede leer OOS-2")

    monkeypatch.setattr(campaigns, "read_holdout", _no_holdout)
    report = feasibility.check(campaign_id, db_path=db)

    assert report["n_checked"] == 32
    assert len(report["rows"]) == 32
    assert all(len(row["fold_trades"]) == 4 for row in report["rows"])
    assert any(not row["feasible"] for row in report["rows"])
    assert "expectancy" not in report and "pnl" not in report
    assert _counts(db, campaign_id) == before
    assert databank.get_campaign(campaign_id, db_path=db)["status"] == "synthetic"


def test_approve_rechaza_si_feasibility_falla(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=7)
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="gate-fail",
        db_path=db,
    )
    monkeypatch.setattr(
        engine,
        "preflight",
        lambda *args, **kwargs: {"valid": 440, "population": 440},
    )
    monkeypatch.setattr(
        feasibility,
        "check",
        lambda *args, **kwargs: {
            "passes": False,
            "n_feasible": 4,
            "n_checked": 10,
            "feasible_pct": 40.0,
        },
    )
    with pytest.raises(campaigns.CampaignError, match="feasibility"):
        campaigns.approve("gate-fail", db_path=db)
    row = databank.get_campaign("gate-fail", db_path=db)
    assert row["status"] == "draft"
    assert row["approved_at"] is None


def test_approve_pasa_con_feasibility(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=7)
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="gate-pass",
        db_path=db,
    )
    monkeypatch.setattr(
        engine,
        "preflight",
        lambda *args, **kwargs: {"valid": 440, "population": 440},
    )
    monkeypatch.setattr(
        feasibility,
        "check",
        lambda *args, **kwargs: {
            "passes": True,
            "n_feasible": 6,
            "n_checked": 10,
            "feasible_pct": 60.0,
        },
    )
    row = campaigns.approve("gate-pass", db_path=db)
    assert row["status"] == "registered"
    assert row["approved_at"] is not None


def test_cli_feasibility_muestra_tabla(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from tradinglab.cli import app

    monkeypatch.setenv("COLUMNS", "240")
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=3)
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="cli-feas",
        db_path=db,
    )
    monkeypatch.setattr(
        feasibility,
        "check",
        lambda *args, **kwargs: {
            "n_checked": 1,
            "n_feasible": 1,
            "feasible_pct": 100.0,
            "passes": True,
            "rows": [
                {
                    "index": 0,
                    "label": "u=0.002 fin=600 entrada=15:00 stop=4.0",
                    "trades_is": 120,
                    "fold_trades": [30, 30, 30, 30],
                    "cost_r": 0.08,
                    "cost_by_account": {"CFD-001": 0.08, "CFD-006": 0.07},
                    "cost_viable_by_account": {"CFD-001": True, "CFD-006": True},
                    "worst_account": "CFD-001",
                    "worst_share": 1.0,
                    "best_account": "CFD-006",
                    "best_share": 1.0,
                    "selected_account": "CFD-006",
                    "selected_share": 1.0,
                    "mean_bars": 6.0,
                    "mean_minutes": 30.0,
                    "feasible": True,
                    "reasons": [],
                }
            ],
        },
    )
    result = CliRunner().invoke(
        app, ["discovery", "feasibility", "cli-feas", "--db", str(db)]
    )
    assert result.exit_code == 0
    assert "Factibles 1/1" in result.output
    assert "PASA" in result.output
    assert "Más barata" in result.output
    assert "sí" in result.output
