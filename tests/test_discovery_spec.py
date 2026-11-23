from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tradinglab.config import DEFAULT_DB
from tradinglab.discovery import databank, engine, feasibility
from tradinglab.discovery.spec import SpecError, load_spec
from tradinglab.learning import count_tests


def _spec_text(timeframe: str = "H1") -> str:
    return f"""
instrument: US100
timeframe: {timeframe}
template: asia_range_reversion
profile: small
mode: ga
seed: 11
data_source: dukascopy
account: CFD-001
segments:
  is: ["2024-01-01", "2024-03-31"]
  oos1: ["2024-04-01", "2024-05-31"]
  oos2: ["2024-06-01", null]
"""


def _campaign_rows() -> int:
    path = Path(databank.DEFAULT_DISCOVERY_DB)
    if not path.exists():
        return 0
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return int(
            con.execute("SELECT COUNT(*) FROM disc_campaigns").fetchone()[0]
        )
    finally:
        con.close()


def test_spec_incompatible_rechaza_h4(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(_spec_text("H4"), encoding="utf-8")
    with pytest.raises(SpecError, match="no declara H4"):
        load_spec(path)


def test_preflight_y_feasibility_spec_no_tocan_db(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(_spec_text(), encoding="utf-8")
    frame = engine.synthetic_frame(years=0.5, seed=2)
    before_tests = count_tests(DEFAULT_DB)
    before_rows = _campaign_rows()

    preflight = engine.preflight_spec(path)
    report = feasibility.check_spec(path, bars=frame)

    assert preflight["campaign_id"] == "spec-spec"
    assert preflight["generated"] == preflight["population"] == 40
    assert report["campaign_id"] == "spec-spec"
    assert report["n_checked"] == 40
    assert count_tests(DEFAULT_DB) == before_tests
    assert _campaign_rows() == before_rows


def test_register_from_spec_no_aprueba(tmp_path: Path) -> None:
    from tradinglab.discovery import campaigns, databank

    path = tmp_path / "grid.yaml"
    path.write_text(
        """
campaign_id: c1-test
instrument: US100
timeframe: M5
template: asia_range_reversion
profile: small
mode: grid
seed: 2
data_source: dukascopy
account: CFD-001
cost_mode: best
cost_accounts: [CFD-001, CFD-006]
segments:
  is: ["2023-01-02", "2023-09-30"]
  oos1: ["2023-10-01", "2023-11-30"]
  oos2: ["2023-12-01", null]
grid:
  dimensions:
    - name: regime
      kind: path
      path: long_entry.args[1].params.threshold
      values: [15, 20, 25]
    - name: stop
      kind: path
      path: exit.stop.mult
      values: [1.5, 2.0, 2.5]
    - name: target
      kind: path
      path: exit.target.rr
      values: [1.5, 2.0, 2.5]
""",
        encoding="utf-8",
    )
    db = tmp_path / "discovery.db"
    campaign = campaigns.register_from_spec(
        path,
        frame=engine.synthetic_frame(years=1.0, seed=2),
        db_path=db,
    )
    assert campaign["campaign_id"] == "c1-test"
    assert campaign["status"] == "draft"
    assert campaign["n_total"] == 27
    assert campaign["config"]["mode"] == "grid"
    assert len(campaign["config"]["grid"]["dimensions"]) == 3
    assert databank.get_campaign("c1-test", db_path=db) is not None


def test_register_approve_run_aplica_grid_del_spec(tmp_path: Path) -> None:
    from tradinglab.discovery import campaigns, databank

    path = tmp_path / "grid.yaml"
    path.write_text(
        """
campaign_id: c1-run
instrument: US100
timeframe: M5
template: asia_range_reversion
profile: small
mode: grid
seed: 2
data_source: dukascopy
account: CFD-001
cost_mode: target
segments:
  is: ["2023-01-02", "2023-09-30"]
  oos1: ["2023-10-01", "2023-11-30"]
  oos2: ["2023-12-01", null]
grid:
  dimensions:
    - name: regime
      kind: path
      path: long_entry.args[1].params.threshold
      values: [15, 20, 25]
    - name: stop
      kind: path
      path: exit.stop.mult
      values: [1.5, 2.0, 2.5]
    - name: target
      kind: path
      path: exit.target.rr
      values: [1.5, 2.0, 2.5]
""",
        encoding="utf-8",
    )
    frame = engine.synthetic_frame(years=1.0, seed=2)
    db = tmp_path / "discovery.db"
    campaigns.register_from_spec(path, frame=frame, db_path=db)
    campaigns.approve("c1-run", db_path=db, verify=False)
    summary = engine.run_campaign(
        "c1-run", workers=2, db_path=db, bars=frame
    )
    campaign = databank.get_campaign("c1-run", db_path=db)
    assert campaign is not None
    assert campaign["n_total"] == 27
    assert campaign["n_evaluated"] == 27
    assert campaign["status"] == "done"
    assert summary["n_evaluated"] == 27

    con = sqlite3.connect(db)
    try:
        payloads = [
            json.loads(row[0])
            for row in con.execute(
                "SELECT dsl_json FROM disc_strategies WHERE campaign_id = ?",
                ("c1-run",),
            )
        ]
    finally:
        con.close()
    assert len(payloads) == 27
    assert {item["long_entry"]["args"][1]["params"]["threshold"] for item in payloads} == {
        15,
        20,
        25,
    }
    assert {item["exit"]["stop"]["mult"] for item in payloads} == {1.5, 2.0, 2.5}
    assert {item["exit"]["target"]["rr"] for item in payloads} == {1.5, 2.0, 2.5}

    from typer.testing import CliRunner

    from tradinglab.cli import app

    con = sqlite3.connect(db)
    try:
        strategy_id = con.execute(
            "SELECT id FROM disc_strategies WHERE campaign_id = ? LIMIT 1",
            ("c1-run",),
        ).fetchone()[0]
    finally:
        con.close()
    shown = CliRunner().invoke(
        app, ["discovery", "show", str(strategy_id), "--db", str(db)]
    )
    assert shown.exit_code == 0, shown.output


def test_reopen_running_vacio_vuelve_a_registered(tmp_path: Path) -> None:
    from tradinglab.discovery import campaigns, databank

    db = tmp_path / "discovery.db"
    config = {
        "instrument": "US100",
        "timeframe": "M5",
        "template": "asia_range_reversion",
        "profile": "small",
        "mode": "grid",
        "seed": 2,
        "data_source": "dukascopy",
        "cost": {"account": "CFD-001", "firm": "ftmo", "mode": "target"},
    }
    databank.add_campaign(
        "stuck",
        config,
        instrument="US100",
        timeframe="M5",
        template="asia_range_reversion",
        status="running",
        n_total=27,
        db_path=db,
    )
    reopened = campaigns.reopen_empty_running("stuck", db_path=db)
    assert reopened["status"] == "registered"


def test_run_grid_sin_grid_falla_antes_de_evaluar(tmp_path: Path) -> None:
    from tradinglab.discovery import campaigns, databank

    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=1.0, seed=2)
    config = {
        "instrument": "US100",
        "timeframe": "M5",
        "template": "asia_range_reversion",
        "profile": "small",
        "mode": "grid",
        "seed": 2,
        "data_source": "dukascopy",
        "is_start": "2023-01-02",
        "is_end": "2023-09-30",
        "oos1_start": "2023-10-01",
        "oos1_end": "2023-11-30",
        "oos2_start": "2023-12-01",
        "oos2_end": None,
        "cost": {"account": "CFD-001", "firm": "ftmo", "mode": "target"},
    }
    databank.add_campaign(
        "bad-grid",
        config,
        instrument="US100",
        timeframe="M5",
        template="asia_range_reversion",
        status="draft",
        n_total=27,
        db_path=db,
    )
    databank.approve_campaign("bad-grid", db_path=db)
    with pytest.raises(campaigns.CampaignError, match="sin grid"):
        engine.run_campaign(
            "bad-grid", workers=2, db_path=db, bars=frame
        )
    campaign = databank.get_campaign("bad-grid", db_path=db)
    assert campaign is not None
    assert campaign["status"] == "registered"
    con = sqlite3.connect(db)
    try:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM disc_strategies WHERE campaign_id = ?",
                ("bad-grid",),
            ).fetchone()[0]
            == 0
        )
    finally:
        con.close()
