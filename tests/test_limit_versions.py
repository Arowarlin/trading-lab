from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradinglab.accounts import load_accounts, own_limits, set_limits
from tradinglab.db import init_db
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
    account = load_accounts()["ftmo_demo"]
    v1 = snapshot_limits(db, "ftmo_demo", reason="base")
    assert v1["version"] == 1
    assert v1["limits"]["daily_loss_pct"] == pytest.approx(0.05)
    set_limits(
        db,
        account_id="ftmo_demo",
        changes={"daily_loss_pct": 0.04},
        accounts=load_accounts(),
    )
    assert own_limits(db, account).daily_loss_pct == pytest.approx(0.04)
    result = rollback_version(db, "ftmo_demo", 1, confirm=True)
    assert result["ok"] is True
    assert result["changes"]
    # 0.05 es aflojar: queda pendiente al siguiente día hábil.
    assert own_limits(db, account).daily_loss_pct == pytest.approx(0.04)
    later = datetime.now(timezone.utc) + timedelta(days=3)
    assert own_limits(db, account, now=later).daily_loss_pct == pytest.approx(0.05)
    rows = list_versions(db, "ftmo_demo")
    assert rows[0]["version"] == 1
    assert rows[0]["hash"]


def test_rollback_sin_confirmacion_falla(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    snapshot_limits(db, "ftmo_demo")
    set_limits(
        db,
        account_id="ftmo_demo",
        changes={"daily_loss_pct": 0.04},
        accounts=load_accounts(),
    )
    with pytest.raises(LimitVersionError):
        rollback_version(db, "ftmo_demo", 1, confirm=False)


def test_capital_maximo_por_bot(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "tradinglab.orchestrator.load_bots",
        lambda: [SimpleNamespace(id="cfd-a")],
    )
    db = tmp_path / "lab.db"
    init_db(db)
    assert bot_capital(db, "cfd-a") is None
    result = set_bot_capital(db, "cfd-a", 25_000, by="test")
    assert result["old"] is None
    assert bot_capital(db, "cfd-a") == pytest.approx(25_000)
    rows = list_bot_capital(db)
    assert rows[0]["bot"] == "cfd-a"
    assert cap_quantity(1000, 100.0, 25_000) == 250
    assert cap_quantity(10, 100.0, 25_000) == 10
    assert cap_quantity(10, 100.0, None) == 10
    with pytest.raises(LimitVersionError):
        set_bot_capital(db, "cfd-a", 0)
    with pytest.raises(LimitVersionError):
        set_bot_capital(db, "no-existe", 1000)
