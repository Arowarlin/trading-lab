from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradinglab.db import connect, init_db
from tradinglab.global_dsr import (
    DAILY,
    INTRADAY,
    global_srs,
    periods_for_timeframe,
    sr_from_annual,
)
from tradinglab.trials import record_trial


def _insert(
    db: Path,
    *,
    index: int,
    timeframe: str,
    sharpe: float,
    new_columns: bool,
) -> None:
    periods = periods_for_timeframe(timeframe)
    assert periods is not None
    sr_period = sharpe / (periods ** 0.5)
    with connect(db) as con:
        con.execute(
            "INSERT INTO strategy_trials"
            "(ts, family, hypothesis, symbol, params, result, outcome, source,"
            " counted, sr_period, periods_per_year) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "2026-11-15T00:00:00+00:00",
                "TEST",
                "test",
                "EURUSD",
                json.dumps({"timeframe": timeframe}),
                json.dumps({"sharpe": sharpe}),
                "passed",
                "campaign",
                0,
                sr_period if new_columns else None,
                periods if new_columns else None,
            ),
        )


def test_conversion_y_periodos_por_timeframe():
    assert periods_for_timeframe("D1") == pytest.approx(252.0)
    assert periods_for_timeframe("M15") == pytest.approx(252.0 * 96.0)
    assert periods_for_timeframe("desconocido") is None
    assert sr_from_annual(2.5, 252.0) == pytest.approx(
        2.5 / (252.0 ** 0.5)
    )
    assert sr_from_annual(2.5, None) is None


def test_global_daily_necesita_30_sharpes(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    for index in range(29):
        _insert(db, index=index, timeframe="D1", sharpe=0.5, new_columns=True)
    missing = global_srs(db, DAILY, include_reports=False)
    assert missing["available"] is False
    assert missing["n_srs"] == 29

    _insert(db, index=29, timeframe="D1", sharpe=0.5, new_columns=True)
    ready = global_srs(db, DAILY, include_reports=False)
    assert ready["available"] is True
    assert ready["n_srs"] == 30
    assert ready["sources"]["strategy_trials:campaign"] == 30


def test_global_separa_diario_e_intradia_y_lee_legacy(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    for index in range(12):
        _insert(db, index=index, timeframe="D1", sharpe=0.8, new_columns=False)
    for index in range(18):
        _insert(db, index=100 + index, timeframe="M15", sharpe=0.4, new_columns=False)

    daily = global_srs(db, DAILY, include_reports=False)
    intraday = global_srs(db, INTRADAY, include_reports=False)
    assert daily["n_srs"] == 12
    assert daily["available"] is False
    assert intraday["n_srs"] == 18
    assert intraday["available"] is False
    assert daily["sources"] == {"strategy_trials:campaign": 12}
    assert intraday["sources"] == {"strategy_trials:campaign": 18}


def test_record_trial_guarda_sr_period_y_periods(tmp_path: Path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = record_trial(
        db,
        family="TEST",
        hypothesis="test",
        symbol="EURUSD",
        params={"timeframe": "D1"},
        outcome="failed",
        source="sweep",
        counted=False,
        sr_period=0.03,
        periods_per_year=252.0,
    )
    assert row["sr_period"] == pytest.approx(0.03)
    assert row["periods_per_year"] == pytest.approx(252.0)
