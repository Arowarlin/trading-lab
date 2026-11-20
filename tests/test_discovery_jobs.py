"""Cola de trabajos: dedupe, lotes, cancelación y reanudación real."""

from __future__ import annotations

import copy
import os
import pickle
import sqlite3
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, dsl, jobs

TEMPLATE = ROOT / "config" / "discovery" / "templates" / "ny_open_vol_filter.yaml"
SEGMENTS = {
    "is": ["2024-01-08", "2024-01-15"],
    "oos1": ["2024-01-16", "2024-01-25"],
    "oos2": ["2024-01-26", None],
}


def _dataset(bars: int = 8_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-08 00:00", periods=bars, freq="5min", tz="UTC")
    close = 20000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def _strategies(count: int = 6) -> list[dict]:
    base = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))["strategy"]
    result = []
    for index in range(count):
        strategy = copy.deepcopy(base)
        pct = round(0.5 + 0.05 * (index % 10), 2)
        stop_mult = round(1.0 + 0.01 * (index // 10), 4)
        strategy["long_entry"]["args"][1]["params"]["pct"] = pct
        strategy["short_entry"]["args"][1]["params"]["pct"] = pct
        strategy["exit"]["stop"]["mult"] = stop_mult
        strategy["exit"]["target"]["rr"] = round(1.5 + 0.01 * (index // 10), 4)
        assert dsl.validate(strategy) == []
        result.append(strategy)
    return result


def _db(tmp_path: Path) -> Path:
    return tmp_path / "discovery.db"


def _register(
    db: Path,
    frame: pd.DataFrame,
    *,
    campaign_id: str = "camp",
    approved: bool = True,
) -> dict:
    campaigns.register(
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
        return campaigns.approve(campaign_id, db_path=db)
    campaign = databank.get_campaign(campaign_id, db_path=db)
    assert campaign is not None
    return campaign


def _counts(db: Path) -> dict[str, int]:
    with sqlite3.connect(db, timeout=5) as con:
        rows = con.execute(
            "SELECT state, COUNT(*) FROM disc_jobs GROUP BY state"
        ).fetchall()
    return {str(state): int(count) for state, count in rows}


def _job_rows(db: Path) -> list[dict]:
    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM disc_jobs ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def test_enqueue_dedupes_and_rejects_invalid(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _register(db, _dataset())
    strategies = _strategies(5)
    assert jobs.enqueue("camp", strategies, db_path=db) == 5
    assert jobs.enqueue("camp", strategies, db_path=db) == 0
    assert _counts(db)["queued"] == 5

    invalid = copy.deepcopy(strategies[0])
    invalid["long_entry"] = None
    invalid["short_entry"] = None
    with pytest.raises(jobs.QueueError, match="inválida"):
        jobs.enqueue("camp", [invalid], db_path=db)


def test_run_queue_completes_and_is_idempotent(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame)
    jobs.enqueue("camp", _strategies(6), db_path=db)
    summary = jobs.run_queue("camp", 2, bars=frame, db_path=db, batch_size=3)
    assert summary["done"] == 6
    assert summary["failed"] == 0
    assert summary["queued"] == 0
    assert summary["workers"] == 2
    assert databank.get_campaign("camp", db_path=db)["status"] == "done"

    rows = databank.list_strategies(campaign_id="camp", db_path=db)
    assert len(rows) == 6
    for row in rows:
        evaluations = databank.list_evaluations(row["id"], db_path=db)
        assert len(evaluations) == 1
        assert evaluations[0]["segment"] == "is_full"
        assert evaluations[0]["returns"].dtype == np.float32
        assert row["status"] == "evaluated"
    assert all(row["attempts"] == 1 for row in _job_rows(db))

    again = jobs.run_queue("camp", 2, bars=frame, db_path=db)
    assert again["done"] == 6
    assert again["queued"] == 0
    assert len(databank.list_strategies(campaign_id="camp", db_path=db)) == 6


def test_cancel_campaign_skips_queued(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame)
    jobs.enqueue("camp", _strategies(4), db_path=db)
    assert jobs.cancel_campaign("camp", db_path=db) == 4
    summary = jobs.run_queue("camp", 2, bars=frame, db_path=db)
    assert summary["cancelled"] == 4
    assert summary["done"] == 0
    assert databank.get_campaign("camp", db_path=db)["status"] == "cancelled"
    assert databank.list_strategies(campaign_id="camp", db_path=db) == []


def test_resume_orphan_running(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame)
    jobs.enqueue("camp", _strategies(3), db_path=db)
    with sqlite3.connect(db) as con:
        first = con.execute("SELECT id FROM disc_jobs ORDER BY id LIMIT 1").fetchone()[0]
        con.execute(
            "UPDATE disc_jobs SET state = 'running', attempts = 1, started_at = 'x'"
            " WHERE id = ?",
            (first,),
        )
    summary = jobs.run_queue("camp", 2, bars=frame, db_path=db)
    assert summary["done"] == 3
    rows = {row["id"]: row for row in _job_rows(db)}
    assert rows[first]["state"] == "done"
    assert rows[first]["attempts"] == 2


def test_job_error_is_saved(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame)
    strategy = copy.deepcopy(_strategies(1)[0])
    strategy["instrument"] = "US500"
    assert dsl.validate(strategy) == []
    jobs.enqueue("camp", [strategy], db_path=db)
    summary = jobs.run_queue("camp", 1, bars=frame, db_path=db)
    assert summary["failed"] == 1
    row = _job_rows(db)[0]
    assert row["state"] == "failed"
    assert "instrumento" in row["error"]
    assert databank.list_strategies(campaign_id="camp", db_path=db) == []


def test_workers_are_clamped_to_engine_config(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame)
    jobs.enqueue("camp", _strategies(1), db_path=db)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        summary = jobs.run_queue("camp", 99, bars=frame, db_path=db)
    assert summary["workers"] == 12
    assert any("engine.workers" in str(item.message) for item in caught)


def test_draft_campaign_cannot_run(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset()
    _register(db, frame, approved=False)
    jobs.enqueue("camp", _strategies(1), db_path=db)
    with pytest.raises(jobs.QueueError, match="borrador"):
        jobs.run_queue("camp", 1, bars=frame, db_path=db)
    assert _counts(db)["queued"] == 1


def test_run_queue_has_no_free_dates_parameter() -> None:
    import inspect

    parameters = inspect.signature(jobs.run_queue).parameters
    assert "setup" not in parameters
    assert "bars" in parameters


def _child_script(tmp_path: Path) -> Path:
    path = tmp_path / "run_child.py"
    path.write_text(
        "import pickle, sys\n"
        "from pathlib import Path\n"
        "from tradinglab.discovery.jobs import run_queue\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    payload = pickle.loads(Path(sys.argv[1]).read_bytes())\n"
        "    run_queue(\n"
        "        payload['campaign'], payload['workers'],\n"
        "        bars=payload['bars'], db_path=payload['db'], batch_size=4,\n"
        "    )\n",
        encoding="utf-8",
    )
    return path


def _launch(script: Path, payload: Path, tmp_path: Path):
    stdout = open(tmp_path / "child.out", "w", encoding="utf-8")
    stderr = open(tmp_path / "child.err", "w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(script), str(payload)],
        cwd=ROOT,
        stdout=stdout,
        stderr=stderr,
        text=True,
    )
    return process, stdout, stderr


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    else:  # pragma: no cover - Windows es el entorno objetivo
        process.kill()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:  # pragma: no cover
        process.kill()


@pytest.mark.skipif(os.name != "nt", reason="taskkill /T es de Windows")
def test_real_resume_after_kill(tmp_path: Path) -> None:
    db = _db(tmp_path)
    frame = _dataset(bars=60_000)
    _register(db, frame)
    total = 100
    jobs.enqueue("camp", _strategies(total), db_path=db)
    payload_path = tmp_path / "payload.pkl"
    payload_path.write_bytes(
        pickle.dumps(
            {
                "campaign": "camp",
                "workers": 2,
                "db": str(db),
                "bars": frame,
            }
        )
    )
    script = _child_script(tmp_path)

    process, stdout, stderr = _launch(script, payload_path, tmp_path)
    deadline = time.time() + 60
    done_before: dict[int, int] = {}
    killed_midway = False
    while time.time() < deadline:
        if process.poll() is not None:
            break
        counts = _counts(db)
        if counts.get("done", 0) >= 2:
            with sqlite3.connect(db, timeout=5) as con:
                con.row_factory = sqlite3.Row
                done_before = {
                    int(row["id"]): int(row["attempts"])
                    for row in con.execute(
                        "SELECT id, attempts FROM disc_jobs WHERE state = 'done'"
                    ).fetchall()
                }
            pending = counts.get("queued", 0) + counts.get("running", 0)
            if pending > 0 and counts.get("done", 0) < total:
                killed_midway = True
                break
        time.sleep(0.02)
    _kill_tree(process)
    stdout.close()
    stderr.close()
    assert killed_midway, "la cola terminó antes de poder matarla"
    assert done_before

    process2, stdout2, stderr2 = _launch(script, payload_path, tmp_path)
    try:
        code = process2.wait(timeout=180)
    finally:
        stdout2.close()
        stderr2.close()
    error = (tmp_path / "child.err").read_text(encoding="utf-8", errors="replace")
    assert code == 0, error[-2000:]

    counts = _counts(db)
    assert counts.get("done", 0) == total
    assert counts.get("failed", 0) == 0
    assert counts.get("queued", 0) == 0
    assert counts.get("running", 0) == 0
    rows = {row["id"]: row for row in _job_rows(db)}
    for job_id, attempts in done_before.items():
        assert rows[job_id]["state"] == "done"
        assert rows[job_id]["attempts"] == attempts
    with sqlite3.connect(db) as con:
        strategies = con.execute("SELECT COUNT(*) FROM disc_strategies").fetchone()[0]
        evaluations = con.execute("SELECT COUNT(*) FROM disc_evaluations").fetchone()[0]
    assert strategies == total
    assert evaluations == total
