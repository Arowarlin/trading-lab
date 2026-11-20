"""DSR global: borradores que no cuentan, aprobados que sí y holdout una vez."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, jobs
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


def _strategy(threshold: float = 100.0) -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
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


def _register(db: Path, frame: pd.DataFrame, campaign_id: str) -> dict:
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
    return campaigns.approve(campaign_id, db_path=db)


def test_count_tests_includes_only_approved_and_holdout(tmp_path: Path) -> None:
    lab = tmp_path / "lab.db"
    db = tmp_path / "discovery.db"
    frame = _frame()
    base = count_tests(lab, discovery_db=db)
    assert base == 0

    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="draft",
        db_path=db,
    )
    assert count_tests(lab, discovery_db=db) == base

    _register(db, frame, "approved")
    assert count_tests(lab, discovery_db=db) == base + 440

    campaigns.mark_done("approved", db_path=db)
    strategy_id = databank.add_strategy("approved", _strategy(), db_path=db)
    campaigns.read_holdout(strategy_id, frame=frame, db_path=db)
    assert count_tests(lab, discovery_db=db) == base + 440 + 1

    with pytest.raises(campaigns.HoldoutError):
        campaigns.read_holdout(strategy_id, frame=frame, db_path=db)
    assert count_tests(lab, discovery_db=db) == base + 441

    jobs.cancel_campaign("approved", db_path=db)
    assert databank.get_campaign("approved", db_path=db)["status"] == "cancelled"
    assert count_tests(lab, discovery_db=db) == base + 441

    _register(db, frame, "other")
    assert count_tests(lab, discovery_db=db) == base + 441 + 440

    modified = frame.copy()
    modified.iloc[100, modified.columns.get_loc("close")] += 1.0
    with pytest.raises(campaigns.CampaignError, match="dataset_hash"):
        campaigns.load_segment("other", "is", frame=modified, db_path=db)
    assert databank.get_campaign("other", db_path=db)["status"] == "rejected"
    # Rechazada o cancelada, lo aprobado sigue contando.
    assert count_tests(lab, discovery_db=db) == base + 441 + 440


def test_missing_discovery_db_adds_zero(tmp_path: Path) -> None:
    lab = tmp_path / "lab.db"
    missing = tmp_path / "no-existe.db"
    assert count_tests(lab, discovery_db=missing) == 0
    assert not missing.exists()


def test_cli_approve_requires_flag_and_cancel_keeps_count(
    tmp_path: Path,
) -> None:
    from typer.testing import CliRunner

    from tradinglab.cli import app

    db = tmp_path / "discovery.db"
    frame = _frame()
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=frame,
        campaign_id="cli",
        db_path=db,
    )
    runner = CliRunner()
    without = runner.invoke(
        app, ["discovery", "approve", "cli", "--db", str(db)]
    )
    assert without.exit_code == 0
    assert databank.get_campaign("cli", db_path=db)["status"] == "draft"

    approved = runner.invoke(
        app,
        [
            "discovery",
            "approve",
            "cli",
            "--approved-by-operator",
            "--db",
            str(db),
        ],
    )
    assert approved.exit_code == 0
    campaign = databank.get_campaign("cli", db_path=db)
    assert campaign["status"] == "registered"
    assert campaign["approved_at"] is not None

    cancelled = runner.invoke(
        app, ["discovery", "cancel", "cli", "--db", str(db)]
    )
    assert cancelled.exit_code == 0
    assert databank.get_campaign("cli", db_path=db)["status"] == "cancelled"
    lab = tmp_path / "lab.db"
    assert count_tests(lab, discovery_db=db) == 440


def test_approve_only_from_cli() -> None:
    offenders: list[str] = []
    paths = [
        *(ROOT / "src" / "tradinglab").rglob("*.py"),
        *(ROOT / "scripts").rglob("*.py"),
    ]
    for path in paths:
        if path.name in {"campaigns.py", "cli.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_approve = any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and "discovery.campaigns" in node.module
            and any(alias.name == "approve" for alias in node.names)
            for node in ast.walk(tree)
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            calls_campaigns_approve = (
                isinstance(func, ast.Attribute)
                and func.attr == "approve"
                and isinstance(func.value, ast.Name)
                and func.value.id in {"campaigns", "discovery_campaigns"}
            )
            calls_imported_approve = (
                isinstance(func, ast.Name) and func.id == "approve" and imports_approve
            )
            if calls_campaigns_approve or calls_imported_approve:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    register_source = inspect.getsource(campaigns.register)
    assert "approve(" not in register_source
    cli_source = (ROOT / "src" / "tradinglab" / "cli.py").read_text(encoding="utf-8")
    assert "campaigns.approve" in cli_source
