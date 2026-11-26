"""Databank del Discovery Lab: discovery.db, dedupe, blob y estados."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from tradinglab.db import connect as db_connect
from tradinglab.discovery import databank, dsl


def _strategy(threshold: float = 100.0, instrument: str = "US100") -> dict:
    return {
        "dsl_version": "1",
        "instrument": instrument,
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:35", "end": "11:30", "flat_at": "15:45"},
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": threshold},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "pct", "mult": 1.0},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as con:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_tables_only_in_discovery_db(tmp_path: Path) -> None:
    lab = tmp_path / "lab.db"
    lab.write_bytes(b"centinela-lab")
    target = databank.init_databank(tmp_path / "discovery.db")

    assert target.name == "discovery.db"
    assert lab.read_bytes() == b"centinela-lab"
    names = _tables(target)
    assert {
        "disc_campaigns",
        "disc_strategies",
        "disc_lineage",
        "disc_evaluations",
        "disc_validations",
        "disc_jobs",
        "disc_holdout_reads",
    } <= names
    with sqlite3.connect(target) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    with pytest.raises(databank.DatabankError, match="lab.db"):
        databank.init_databank(lab)


def test_connect_does_not_apply_lab_pragmas(tmp_path: Path) -> None:
    probe = tmp_path / "probe.db"
    with db_connect(probe) as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    with db_connect(tmp_path / "discovery.db") as con:
        con.execute("PRAGMA journal_mode=WAL")
    with db_connect(tmp_path / "discovery.db") as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_add_strategy_dedupes_by_hash(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy = _strategy()
    assert dsl.validate(strategy) == []

    first = databank.add_strategy("camp", strategy, db_path=db)
    second = databank.add_strategy("camp", strategy, db_path=db)
    assert first == second
    rows = databank.list_strategies(campaign_id="camp", db_path=db)
    assert len(rows) == 1
    assert rows[0]["dsl"]["instrument"] == "US100"

    other = databank.add_strategy("camp", _strategy(threshold=101.0), db_path=db)
    assert other != first
    other_campaign = databank.add_strategy("camp-2", strategy, db_path=db)
    assert other_campaign != first


def test_evaluation_blob_and_dedupe(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = databank.add_strategy("camp", _strategy(), db_path=db)
    returns = [1.0, -0.5, 2.0]
    first = databank.add_evaluation(
        strategy_id,
        segment="is_full",
        cost_profile="CFD-001:US100",
        metrics={"expectancy_r": 0.8333, "trades": 3},
        trades_count=3,
        returns=returns,
        db_path=db,
    )
    second = databank.add_evaluation(
        strategy_id,
        segment="is_full",
        cost_profile="CFD-001:US100",
        metrics={"expectancy_r": 999.0},
        trades_count=3,
        returns=[9.0],
        db_path=db,
    )
    assert first == second
    evaluations = databank.list_evaluations(strategy_id, db_path=db)
    assert len(evaluations) == 1
    assert evaluations[0]["metrics"]["expectancy_r"] == pytest.approx(0.8333)
    decoded = databank.decode_returns(evaluations[0]["returns_blob"])
    assert decoded.dtype == np.float32
    assert decoded.tolist() == pytest.approx(returns)

    other_segment = databank.add_evaluation(
        strategy_id,
        segment="retest:x2",
        cost_profile="CFD-001:US100",
        metrics=None,
        trades_count=0,
        returns=[],
        db_path=db,
    )
    assert other_segment != first
    assert len(databank.list_evaluations(strategy_id, db_path=db)) == 2


def test_validation_status_and_lineage(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = databank.add_strategy("camp", _strategy(), db_path=db)

    first = databank.add_validation(
        strategy_id, "wf_matrix", {"folds": 4}, True, db_path=db
    )
    second = databank.add_validation(
        strategy_id, "wf_matrix", {"folds": 99}, False, db_path=db
    )
    assert first == second

    databank.set_status(
        strategy_id, "archived", reject_reason="sin edge", db_path=db
    )
    row = databank.get_strategy(strategy_id, db_path=db)
    assert row is not None
    assert row["status"] == "archived"
    assert row["reject_reason"] == "sin edge"
    assert databank.list_strategies(status="archived", db_path=db)

    databank.add_lineage(
        strategy_id,
        parent_a=None,
        parent_b=None,
        operator="seed",
        param_diff={"stop": 1.0},
        generation=0,
        db_path=db,
    )
    lineage = databank.lineage(strategy_id, db_path=db)
    assert len(lineage) == 1
    assert lineage[0]["operator"] == "seed"
    assert lineage[0]["param_diff"] == {"stop": 1.0}


def test_validation_replace_upserts(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = databank.add_strategy("camp", _strategy(), db_path=db)
    databank.add_validation(
        strategy_id, "retest", {"version": 1}, False, db_path=db
    )
    databank.add_validation(
        strategy_id, "retest", {"version": 2}, True, replace=True, db_path=db
    )
    rows = databank.list_validations(strategy_id, db_path=db)
    assert len(rows) == 1
    assert rows[0]["result"] == {"version": 2}
    assert rows[0]["passed"] == 1


def test_campaign_is_inserted_once(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    config = {"instrument": "US100", "timeframe": "M5", "n_total": 10}
    databank.add_campaign("camp", config, db_path=db)
    databank.add_campaign("camp", {"n_total": 999}, db_path=db)
    row = databank.get_campaign("camp", db_path=db)
    assert row is not None
    assert row["config"]["n_total"] == 10
    assert row["status"] == "registered"
    databank.set_campaign_status("camp", "done", db_path=db)
    assert databank.get_campaign("camp", db_path=db)["status"] == "done"


def test_list_filters(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_strategy("camp", _strategy(100.0), origin="template", level=2, db_path=db)
    databank.add_strategy("camp", _strategy(101.0), origin="random", level=1, db_path=db)
    assert len(databank.list_strategies(campaign_id="camp", db_path=db)) == 2
    assert len(
        databank.list_strategies(origin="template", db_path=db)
    ) == 1
    assert len(databank.list_strategies(level=1, db_path=db)) == 1
    assert databank.list_strategies(limit=1, db_path=db)[0]["origin"] == "template"


def test_approval_keeps_counting_after_reject(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "camp",
        {"instrument": "US100", "timeframe": "M5", "n_total": 440},
        status="draft",
        n_total=440,
        db_path=db,
    )
    assert databank.get_campaign("camp", db_path=db)["approved_at"] is None
    approved = databank.approve_campaign("camp", approved_by="tester", db_path=db)
    assert approved["status"] == "registered"
    assert approved["approved_at"] is not None
    databank.set_campaign_rejected("camp", "hash distinto", db_path=db)
    rejected = databank.get_campaign("camp", db_path=db)
    assert rejected["status"] == "rejected"
    assert rejected["approved_at"] == approved["approved_at"]
    assert rejected["reject_reason"] == "hash distinto"


def test_n_total_immutable_trigger(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "camp",
        {"instrument": "US100", "timeframe": "M5"},
        n_total=440,
        db_path=db,
    )
    with sqlite3.connect(db) as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE disc_campaigns SET n_total = 1 WHERE id = 'camp'")
        con.rollback()
        assert con.execute(
            "SELECT n_total FROM disc_campaigns WHERE id = 'camp'"
        ).fetchone()[0] == 440


def test_final_frontier_verdict_and_campaign_counts(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "camp",
        {"instrument": "US100", "timeframe": "M5", "n_total": 10},
        db_path=db,
    )
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    ids = []
    for index, rank in enumerate((0, 1, 0)):
        strategy_id = databank.add_strategy(
            "camp", _strategy(100.0 + index), db_path=db
        )
        ids.append(strategy_id)
        databank.add_evaluation(
            strategy_id,
            segment="fitness_is",
            cost_profile="CFD-001:US100",
            metrics={
                "raw": {"expectancy_r": 0.1 + index},
                "return_dates": dates,
            },
            trades_count=10,
            returns=[0.01, 0.02, -0.01],
            db_path=db,
        )
        databank.add_lineage(
            strategy_id,
            parent_a=None,
            parent_b=None,
            operator="seed",
            db_path=db,
        )
        databank.set_lineage_rank(
            strategy_id,
            rank,
            0.0,
            final=index != 2,
            db_path=db,
        )
    frontier = databank.frontier("camp", db_path=db)
    assert [row["strategy_id"] for row in frontier] == [ids[0]]
    assert frontier[0]["dates"] == dates

    databank.set_strategy_verdict(ids[0], 3, "MODERADA", db_path=db)
    row = databank.get_strategy(ids[0], db_path=db)
    assert row["level"] == 3
    assert row["verdict"] == "MODERADA"

    databank.set_campaign_counts(
        "camp", n_evaluated=5, n_effective=4, n_finalists=1, db_path=db
    )
    campaign = databank.get_campaign("camp", db_path=db)
    assert campaign["n_evaluated"] == 5
    assert campaign["n_effective"] == 4
    assert campaign["n_finalists"] == 1


def test_holdout_read_is_unique(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    strategy_id = databank.add_strategy("camp", _strategy(), db_path=db)
    first = databank.add_holdout_read(
        strategy_id, "camp", dataset_hash="abc", rows=10, db_path=db
    )
    assert databank.get_holdout_read(strategy_id, db_path=db)["id"] == first
    with pytest.raises(sqlite3.IntegrityError):
        databank.add_holdout_read(
            strategy_id, "camp", dataset_hash="abc", rows=10, db_path=db
        )
    assert databank.count_holdout_reads(db_path=db) == 1
