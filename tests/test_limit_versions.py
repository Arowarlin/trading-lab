from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradinglab.accounts import load_accounts, own_limits, set_limits
from tradinglab.db import init_db
from tradinglab.f13 import config_hash, freeze
from tradinglab.limit_versions import (
    LimitVersionError,
    bot_capital,
    cap_quantity,
    list_bot_capital,
    list_versions,
    rollback_version,
    set_bot_capital,
    snapshot_limits,
)


def test_snapshot_versiones_y_rollback_aprieta(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    account = load_accounts()["paper_main"]
    v1 = snapshot_limits(db, "paper_main", reason="base")
    assert v1["version"] == 1
    assert v1["limits"]["daily_loss_pct"] == pytest.approx(0.05)
    set_limits(
        db,
        account_id="paper_main",
        changes={"daily_loss_pct": 0.04},
        accounts=load_accounts(),
    )
    assert own_limits(db, account).daily_loss_pct == pytest.approx(0.04)
    result = rollback_version(db, "paper_main", 1, confirm=True)
    assert result["ok"] is True
    assert result["changes"]
    # 0.05 es aflojar: queda pendiente al siguiente día hábil.
    assert own_limits(db, account).daily_loss_pct == pytest.approx(0.04)
    later = datetime.now(timezone.utc) + timedelta(days=3)
    assert own_limits(db, account, now=later).daily_loss_pct == pytest.approx(0.05)
    rows = list_versions(db, "paper_main")
    assert rows[0]["version"] == 1
    assert rows[0]["hash"]


def test_rollback_con_f13_solo_aprieta(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    root = tmp_path / "repo"
    root.mkdir()
    before = config_hash()
    snapshot_limits(db, "paper_main")
    set_limits(
        db,
        account_id="paper_main",
        changes={"daily_loss_pct": 0.04},
        accounts=load_accounts(),
    )
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-01-05",
        root=root,
    )
    with pytest.raises(LimitVersionError) as exc:
        rollback_version(db, "paper_main", 1, confirm=True)
    assert "F13" in str(exc.value)
    assert config_hash() == before
    with pytest.raises(LimitVersionError):
        rollback_version(db, "paper_main", 1, confirm=False)


def test_capital_maximo_por_bot(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    assert bot_capital(db, "trend-spy") is None
    result = set_bot_capital(db, "trend-spy", 25_000, by="test")
    assert result["old"] is None
    assert bot_capital(db, "trend-spy") == pytest.approx(25_000)
    rows = list_bot_capital(db)
    assert rows[0]["bot"] == "trend-spy"
    assert cap_quantity(1000, 100.0, 25_000) == 250
    assert cap_quantity(10, 100.0, 25_000) == 10
    assert cap_quantity(10, 100.0, None) == 10
    with pytest.raises(LimitVersionError):
        set_bot_capital(db, "trend-spy", 0)
    with pytest.raises(LimitVersionError):
        set_bot_capital(db, "no-existe", 1000)
