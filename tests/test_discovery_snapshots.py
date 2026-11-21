"""R2d: snapshot congelado por campaña y reemplazo sin doble conteo."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import campaigns, databank
from tradinglab.learning import count_tests

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
    campaign_id: str = "old",
    now: pd.Timestamp | None = None,
) -> dict:
    return campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id=campaign_id,
        now=now,
        db_path=db,
    )


def _approved_failure(
    db: Path,
    frame: pd.DataFrame,
    *,
    campaign_id: str = "old",
    now: pd.Timestamp | None = None,
) -> dict:
    old = _register(db, frame, campaign_id=campaign_id, now=now)
    campaigns.approve(campaign_id, db_path=db, verify=False)
    databank.set_campaign_rejected(
        campaign_id,
        "dataset_hash no coincide con el rango fijo de la campaña",
        db_path=db,
    )
    return databank.get_campaign(campaign_id, db_path=db) or old


def test_registration_freezes_range_and_excludes_forming_bar(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=2)  # la última vela sigue abierta

    campaign = _register(db, frame, now=now)

    assert campaign["oos2_end"] == frame.index[-2].isoformat()
    snapshot = pd.read_parquet(Path(campaign["snapshot_path"]))
    assert snapshot.index.max() == frame.index[-2]
    assert frame.index[-1] not in snapshot.index
    assert campaign["snapshot_rows"] == len(snapshot)
    assert campaign["snapshot_hash"] == campaign["dataset_hash"]


def test_registered_campaign_ignores_live_cache_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=10)
    campaign = _register(db, frame, now=now)
    original = campaigns.load_segment("old", "is", db_path=db)

    def _no_live(*_args, **_kwargs):
        raise AssertionError("la campaña no debe leer la caché viva")

    monkeypatch.setattr(campaigns, "_source_frame", _no_live)
    refreshed = frame.copy()
    refreshed.iloc[100, refreshed.columns.get_loc("close")] += 99.0
    extra = refreshed.iloc[[-1]].copy()
    extra.index = [refreshed.index[-1] + pd.Timedelta(minutes=5)]
    refreshed = pd.concat([refreshed, extra])

    again = campaigns.load_segment("old", "is", frame=refreshed, db_path=db)
    assert again.equals(original)
    assert campaign["snapshot_hash"] == databank.get_campaign(
        "old", db_path=db
    )["snapshot_hash"]


def test_snapshot_corruption_rejects_campaign(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=10)
    campaign = _register(db, frame, now=now)

    changed = pd.read_parquet(Path(campaign["snapshot_path"]))
    changed.iloc[10, changed.columns.get_loc("close")] += 1.0
    changed.to_parquet(Path(campaign["snapshot_path"]))

    with pytest.raises(campaigns.CampaignError, match="snapshot corrupto"):
        campaigns.load_segment("old", "is", db_path=db)
    assert databank.get_campaign("old", db_path=db)["status"] == "rejected"


def test_supersede_rejects_a_campaign_with_evaluations(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=10)
    _approved_failure(db, frame, now=now)
    strategy_id = databank.add_strategy("old", _strategy(), db_path=db)
    databank.add_evaluation(
        strategy_id,
        segment="is_full",
        cost_profile="ftmo",
        metrics={"expectancy_r": 0.1},
        trades_count=3,
        returns=[0.1, -0.1],
        db_path=db,
    )

    with pytest.raises(campaigns.CampaignError, match="evaluaciones"):
        campaigns.supersede("old", db_path=db, now=now)
    assert databank.get_campaign("old", db_path=db)["status"] == "rejected"
    assert count_tests(tmp_path / "lab.db", discovery_db=db) == 440


def test_supersede_rejects_without_hash_or_startup_failure(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=10)
    _register(db, frame, now=now)
    campaigns.approve("old", db_path=db, verify=False)

    with pytest.raises(campaigns.CampaignError, match="hash o al arrancar"):
        campaigns.supersede("old", db_path=db, now=now)


def test_supersede_keeps_count_and_writes_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    frame = _frame()
    now = frame.index[-1] + pd.Timedelta(minutes=10)
    old = _approved_failure(db, frame, now=now)
    assert count_tests(lab, discovery_db=db) == 440

    changed = frame.copy()
    for column in ("open", "high", "low", "close"):
        changed.iloc[100, changed.columns.get_loc(column)] += 50.0
    monkeypatch.setattr(campaigns, "_source_frame", lambda *_a, **_k: changed)

    new = campaigns.supersede("old", db_path=db, now=now)

    assert new["status"] == "registered"
    assert new["approved_at"] is not None
    assert new["config_hash"] == old["config_hash"]
    assert new["template"] == old["template"]
    assert new["config"]["seed"] == old["config"]["seed"]
    assert new["config"]["mode"] == old["config"]["mode"]
    assert new["snapshot_hash"] != old["dataset_hash"]
    assert Path(new["snapshot_path"]).exists()

    old_row = databank.get_campaign("old", db_path=db)
    assert old_row["status"] == "superseded"
    assert old_row["superseded_by"] == new["campaign_id"]
    assert count_tests(lab, discovery_db=db) == 440

    old_segment = campaigns.load_segment("old", "is", db_path=db)
    new_segment = campaigns.load_segment(new["campaign_id"], "is", db_path=db)
    assert old_segment.iloc[100]["close"] != new_segment.iloc[100]["close"]

    audit = tmp_path / "audit.log"
    assert audit.exists()
    record = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert record["action"] == "supersede"
    assert record["old_id"] == "old"
    assert record["new_id"] == new["campaign_id"]
    assert record["count_before"] == record["count_after"] == 440
