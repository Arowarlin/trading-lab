from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab import optimize
from tradinglab.config import Settings
from tradinglab.db import init_db
from tradinglab.learning import count_tests


def _frame(rows: int = 420) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    close = 100.0 + 0.15 * x + 2.0 * np.sin(x / 20.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=pd.bdate_range("2020-01-01", periods=rows),
    )


def test_run_optuna_sintetico_suma_trials_y_no_toca_holdout(
    tmp_path: Path, monkeypatch
) -> None:
    frame = _frame()

    def fake_fetch(symbol, start, end, cache_dir):
        assert str(start) <= str(end), "fetch con fechas invertidas"
        if str(start) >= "2025-01-01":
            return frame.iloc[0:0]
        return frame

    monkeypatch.setattr(optimize.data_mod, "fetch", fake_fetch)
    db = tmp_path / "lab.db"
    init_db(db)
    report = optimize.run_optuna(
        "SPY",
        "trend",
        start="2020-01-01",
        end="2021-12-31",
        trials=3,
        train_days=100,
        test_days=50,
        step=50,
        cache_dir=tmp_path,
        db_path=db,
        settings=Settings(),
    )
    assert report["trials"] >= 1
    assert report["n_trials_dsr"] >= 3
    assert count_tests(db) >= 3
    assert report["holdout"]["status"] == "Sin datos"
    assert "dsr" in report["gates"]
    assert "pbo" in report["gates"]
    assert report["config"]["dev_end"] < report["config"]["sealed_start"]
    assert isinstance(report["proposals"], list)
    assert report["best_params"]
