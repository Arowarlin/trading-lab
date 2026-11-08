from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.db import init_db
from tradinglab.models import (
    CombinatorialPurgedCV,
    ModelError,
    PurgedKFold,
    compare_models,
    get_model,
    list_models,
    promote_model,
    qlib_status,
    registry_payload,
    rollback_model,
    train_purged_cv,
    train_walk_forward,
)
from tradinglab.orchestrator import load_bots


def _prices(rows: int = 420, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0004, 0.011, rows)
    close = 100 * np.exp(np.cumsum(returns))
    index = pd.bdate_range("2020-01-01", periods=rows)
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, rows)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        },
        index=index,
    )


def test_walk_forward_reproducible_y_sin_lookahead(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    frame = _prices()
    first = train_walk_forward(
        frame,
        symbol="SPY",
        db_path=db,
        train_days=150,
        test_days=30,
        step=30,
    )
    second = train_walk_forward(
        frame,
        symbol="SPY",
        db_path=db,
        train_days=150,
        test_days=30,
        step=30,
    )
    assert first["registry_id"] is not None
    assert first["model"]["hash"] == second["model"]["hash"]
    assert len(first["folds"]) >= 2
    assert first["metrics"]["sharpe"] is not None
    assert first["metrics"]["total_return"] is not None
    for fold in first["folds"]:
        assert fold["train_end"] < fold["test_start"]
    rows = list_models(db, "SPY")
    assert len(rows) == 2
    assert all(row["status"] == "challenger" for row in rows)


def test_promocion_rollback_y_sin_activar_bots(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    frame = _prices()
    before = {bot.id: bot.enabled for bot in load_bots()}
    first = train_walk_forward(
        frame, symbol="SPY", db_path=db, train_days=150, test_days=30, step=30, alpha=1.0
    )
    second = train_walk_forward(
        frame, symbol="SPY", db_path=db, train_days=150, test_days=30, step=30, alpha=2.0
    )
    with pytest.raises(ModelError):
        promote_model(db, first["registry_id"], confirm=False)
    promoted = promote_model(db, first["registry_id"], confirm=True)
    assert promoted["previous_id"] is None
    assert get_model(db, first["registry_id"])["status"] == "champion"
    second_promoted = promote_model(db, second["registry_id"], confirm=True)
    assert second_promoted["previous_id"] == first["registry_id"]
    assert get_model(db, first["registry_id"])["status"] == "retired"
    assert get_model(db, second["registry_id"])["status"] == "champion"
    rollback = rollback_model(db, "SPY", confirm=True)
    assert rollback["restored_id"] == first["registry_id"]
    assert get_model(db, first["registry_id"])["status"] == "champion"
    assert get_model(db, second["registry_id"])["status"] == "retired"
    assert {bot.id: bot.enabled for bot in load_bots()} == before
    compare = compare_models(db, "SPY")
    assert compare["champion"]["id"] == first["registry_id"]


def test_registry_payload_y_qlib(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    frame = _prices()
    result = train_walk_forward(
        frame, symbol="QQQ", db_path=db, train_days=150, test_days=30, step=30
    )
    payload = registry_payload(db)
    assert payload["models"][0]["id"] == result["registry_id"]
    assert payload["qlib"]["available"] in {True, False}
    assert payload["qlib"]["note"]
    text = qlib_status()
    assert text["path"].endswith(".venv-qlib")


def test_purged_kfold_sin_solapamiento() -> None:
    n = 100
    splitter = PurgedKFold(n_splits=5, purge=5, embargo=2)
    covered = set()
    for train_idx, test_idx in splitter.split(n):
        assert not set(train_idx.tolist()) & set(test_idx.tolist())
        covered.update(test_idx.tolist())
        start, end = int(test_idx[0]), int(test_idx[-1]) + 1
        blocked = set(range(max(0, start - 5), start)) | set(
            range(end, min(n, end + 2))
        )
        assert not set(train_idx.tolist()) & blocked
    assert covered == set(range(n))


def test_cpcv_sin_solapamiento_y_numero_de_splits() -> None:
    n = 120
    splitter = CombinatorialPurgedCV(
        n_groups=6, n_test_groups=2, purge=5, embargo=2
    )
    seen = 0
    for train_idx, test_idx in splitter.split(n):
        seen += 1
        assert not set(train_idx.tolist()) & set(test_idx.tolist())
        for group in np.array_split(np.arange(n), 6):
            group_start = int(group[0])
            group_end = int(group[-1]) + 1
            if set(group.tolist()) <= set(test_idx.tolist()):
                blocked = set(range(max(0, group_start - 5), group_start)) | set(
                    range(group_end, min(n, group_end + 2))
                )
                assert not set(train_idx.tolist()) & blocked
    assert seen == splitter.n_splits == 15


def test_train_purged_cv_produce_folds() -> None:
    frame = _prices()
    result = train_purged_cv(
        frame,
        symbol="SPY",
        n_splits=3,
        purge=5,
        embargo=2,
        alpha=1.0,
    )
    assert result["ok"] is True
    assert result["n_splits"] >= 2
    assert result["metrics"]["sharpe"] is not None
    assert all("purge" in fold and "embargo" in fold for fold in result["folds"])
