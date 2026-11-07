from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradinglab.db import init_db
from tradinglab.f13 import config_hash, freeze
from tradinglab.journal import ClosedTrade
from tradinglab.riskpause import (
    config,
    pause_status,
    resume,
    set_thresholds,
)


def _trade(day: str, pnl: float, index: int, hour: int = 15) -> ClosedTrade:
    stamp = f"{day}T{hour:02d}:00:00+00:00"
    return ClosedTrade(
        bot="trend-spy",
        account="paper_main",
        profile="swing_equity",
        ticker="SPY",
        qty=1.0,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        entry_ts=stamp,
        exit_ts=stamp,
        pnl=pnl,
        fees=0.0,
        return_pct=pnl / 100.0,
        holding_hours=1.0,
        day=day,
        hour=hour,
        entry_order_id=index,
        exit_order_id=index + 1,
        exit_fill_id=index + 2,
    )


def test_pausa_por_racha_y_reanudacion(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    now = datetime(2026, 1, 7, 20, 0, tzinfo=timezone.utc)
    trades = [
        _trade("2026-01-05", -10.0, 1),
        _trade("2026-01-06", -20.0, 2),
        _trade("2026-01-07", -30.0, 3),
    ]
    state = pause_status(db, "paper_main", trades=trades, tz="UTC", now=now)
    assert state["paused"] is True
    assert state["trigger_type"] == "streak"
    assert state["consecutive_losses"] == 3
    assert "racha perdedora" in state["reason"]
    assert pause_status(db, "paper_main", tz="UTC", now=now)["paused"] is True

    with pytest.raises(ValueError):
        resume(db, "paper_main", confirm=False)
    result = resume(db, "paper_main", confirm=True)
    assert result["paused"] is False
    after = pause_status(db, "paper_main", trades=trades, tz="UTC", now=now)
    assert after["paused"] is False


def test_pausa_por_perdida_diaria(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    now = datetime(2026, 1, 7, 20, 0, tzinfo=timezone.utc)
    trade = _trade("2026-01-07", -2_500.0, 1)
    state = pause_status(db, "paper_main", trades=[trade], tz="UTC", now=now)
    assert state["paused"] is True
    assert state["trigger_type"] == "daily_loss"
    assert state["daily_limit_usd"] == pytest.approx(2_000.0)
    assert state["daily_loss_usd"] == pytest.approx(2_500.0)


def test_umbrales_apretar_aflojar_y_f13(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    root = tmp_path / "repo"
    root.mkdir()
    before = config_hash()
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-01-05",
        root=root,
    )
    with pytest.raises(ValueError):
        set_thresholds(
            db,
            "paper_main",
            changes={"daily_loss_pct": 0.05},
            confirm=True,
        )
    result = set_thresholds(
        db,
        "paper_main",
        changes={"daily_loss_pct": 0.01, "max_consecutive_losses": 2},
    )
    assert result["ok"] is True
    assert config(db, "paper_main").daily_loss_pct == pytest.approx(0.01)
    assert config(db, "paper_main").max_consecutive_losses == 2
    assert config_hash() == before
    with pytest.raises(ValueError):
        resume(db, "paper_main", confirm=True)


def test_umbrales_aflojar_fuera_f13(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(ValueError):
        set_thresholds(
            db,
            "paper_main",
            changes={"daily_loss_pct": 0.05},
        )
    result = set_thresholds(
        db,
        "paper_main",
        changes={"daily_loss_pct": 0.05},
        confirm=True,
    )
    assert result["ok"] is True
    assert config(db, "paper_main").daily_loss_pct == pytest.approx(0.05)
