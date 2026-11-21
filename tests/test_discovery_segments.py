"""Campañas: n_total, calidad, segmentos sellados y holdout único."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import campaigns, databank, dsl, jobs

SEGMENTS = {
    "is": ["2024-01-08", "2024-01-20"],
    "oos1": ["2024-01-21", "2024-02-05"],
    "oos2": ["2024-02-06", None],
}


def _frame(bars: int = 20_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-08 00:00", periods=bars, freq="5min", tz="UTC")
    close = 20000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
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
            "right": {"kind": "const", "value": 100.0},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "pct", "mult": 1.0},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def _register(
    db: Path,
    frame: pd.DataFrame,
    *,
    campaign_id: str = "c1",
    approved: bool = False,
) -> dict:
    campaign = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id=campaign_id,
        db_path=db,
    )
    if approved:
        campaign = campaigns.approve(campaign_id, db_path=db, verify=False)
    return campaign


def test_register_draft_n_total_and_real_oos2_end(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    campaign = _register(db, frame)
    assert campaign["status"] == "draft"
    assert campaign["approved_at"] is None
    assert campaign["n_total"] == 40 * (10 + 1) == 440
    assert campaign["oos2_end"] == frame.index[-1].isoformat()
    assert campaign["config"]["segments"]["oos2"][1] == frame.index[-1].isoformat()
    assert campaigns.discovery_tests(db)["total"] == 0
    assert dsl.validate(_strategy()) == []


def test_n_total_is_immutable(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    _register(db, _frame())
    with sqlite3.connect(db) as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE disc_campaigns SET n_total = 1 WHERE id = 'c1'")
        con.rollback()
        value = con.execute(
            "SELECT n_total FROM disc_campaigns WHERE id = 'c1'"
        ).fetchone()[0]
    assert value == 440


def test_quality_fail_rejects(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    frame.iloc[100, frame.columns.get_loc("high")] = frame.iloc[100]["low"] - 1.0
    with pytest.raises(campaigns.CampaignError, match="calidad"):
        _register(db, frame)
    assert databank.get_campaign("c1", db_path=db) is None


def test_segment_before_useful_start_rejects(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    segments = {
        "is": ["2024-01-01", "2024-01-20"],
        "oos1": ["2024-01-21", "2024-02-05"],
        "oos2": ["2024-02-06", None],
    }
    with pytest.raises(campaigns.CampaignError, match="inicio útil"):
        campaigns.register(
            "US100",
            "M5",
            "ny_open_vol_filter",
            "small",
            segments=segments,
            frame=_frame(),
            campaign_id="c1",
            db_path=db,
        )


def test_dataset_hash_fixed_range_and_snapshot(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    campaign = _register(db, frame, approved=True)
    assert campaigns.dataset_matches(campaign, frame)

    later = frame.iloc[[-1]].copy()
    later.index = [frame.index[-1] + pd.Timedelta(minutes=5)]
    extended = pd.concat([frame, later])
    assert campaigns.dataset_matches(campaign, extended)

    modified = frame.copy()
    modified.iloc[100, modified.columns.get_loc("close")] += 1.0
    assert not campaigns.dataset_matches(campaign, modified)
    # La campaña ya no lee la fuente viva: devuelve su snapshot y no se rechaza.
    before = campaigns.load_segment("c1", "is", frame=frame, db_path=db)
    after = campaigns.load_segment("c1", "is", frame=modified, db_path=db)
    assert after.equals(before)
    assert databank.get_campaign("c1", db_path=db)["status"] == "registered"
    assert campaigns.discovery_tests(db)["campaigns"] == 440
    assert campaign["snapshot_hash"] == campaign["dataset_hash"]
    assert Path(campaign["snapshot_path"]).exists()


def test_segments_are_sealed(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    _register(db, frame, approved=True)

    is_frame = campaigns.load_segment("c1", "is", frame=frame, db_path=db)
    assert is_frame.index.min() >= pd.Timestamp("2024-01-08", tz="UTC")
    assert is_frame.index.max() <= pd.Timestamp("2024-01-20 23:59", tz="UTC")
    with pytest.raises(campaigns.CampaignError, match="OOS-1 sellado"):
        campaigns.load_segment("c1", "oos1", frame=frame, db_path=db)
    campaigns.mark_done("c1", db_path=db)
    oos1 = campaigns.load_segment("c1", "oos1", frame=frame, db_path=db)
    assert oos1.index.min() >= pd.Timestamp("2024-01-21", tz="UTC")
    assert oos1.index.max() <= pd.Timestamp("2024-02-05 23:59", tz="UTC")
    with pytest.raises(campaigns.HoldoutError, match="read_holdout"):
        campaigns.load_segment("c1", "oos2", frame=frame, db_path=db)


def test_holdout_one_read_per_strategy(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    _register(db, frame, approved=True)
    campaigns.mark_done("c1", db_path=db)
    first = databank.add_strategy("c1", _strategy(), db_path=db)
    second = databank.add_strategy(
        "c1", {**_strategy(), "instrument": "US100"}, db_path=db
    )
    assert first == second  # mismo hash: reutiliza el id
    other = databank.add_strategy(
        "c1",
        {
            **_strategy(),
            "long_entry": {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 101.0},
            },
        },
        db_path=db,
    )
    sealed = campaigns.read_holdout(first, frame=frame, db_path=db)
    assert sealed.index.min() >= pd.Timestamp("2024-02-06", tz="UTC")
    assert sealed.index.max() <= pd.Timestamp(frame.index[-1])
    with pytest.raises(campaigns.HoldoutError, match="segunda lectura"):
        campaigns.read_holdout(first, frame=frame, db_path=db)
    assert databank.count_holdout_reads(db_path=db) == 1
    campaigns.read_holdout(other, frame=frame, db_path=db)
    assert databank.count_holdout_reads(db_path=db) == 2


def test_queue_builds_setup_from_campaign(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    campaign = _register(db, frame, approved=False)
    with pytest.raises(jobs.QueueError, match="borrador"):
        jobs.run_queue("c1", 1, bars=frame, db_path=db)

    campaigns.approve("c1", db_path=db, verify=False)
    setup = jobs.QueueSetup.from_campaign(
        databank.get_campaign("c1", db_path=db)
    )
    assert setup.instrument == campaign["instrument"]
    assert setup.timeframe == campaign["timeframe"]
    assert setup.start == campaign["is_start"] == "2024-01-08"
    assert setup.end == campaign["is_end"] == "2024-01-20"
    assert "setup" not in inspect.signature(jobs.run_queue).parameters

    jobs.enqueue("c1", [_strategy()], db_path=db)
    summary = jobs.run_queue("c1", 1, bars=frame, db_path=db)
    assert summary["done"] == 1
    assert summary["failed"] == 0

    later = frame.iloc[[-1]].copy()
    later.index = [frame.index[-1] + pd.Timedelta(minutes=5)]
    extended = pd.concat([frame, later])
    jobs.enqueue("c1", [{**_strategy(), "limits": {"max_trades_per_day": 1, "cooldown_bars": 1}}], db_path=db)
    summary = jobs.run_queue("c1", 1, bars=extended, db_path=db)
    assert summary["done"] == 2
    assert summary["queued"] == 0
