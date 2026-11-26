"""Niveles, veredicto, PBO mínimo, pruebas no calculables y orden del DSR."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import campaigns, databank, levels, robustness
from tradinglab.discovery.engine import synthetic_frame

SEGMENTS = {
    "is": ["2023-01-02", "2023-02-28"],
    "oos1": ["2023-03-01", "2023-03-31"],
    "oos2": ["2023-04-01", None],
}


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
            "right": {"kind": "const", "value": 0.0},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "pct", "value": 2.0},
            "target": {"type": "rr", "rr": 1.5},
            "time_exit_bars": 48,
        },
        "limits": {"max_trades_per_day": 2, "cooldown_bars": 0},
    }


def _campaign(db, *, k: int = 1, status: str = "registered") -> str:
    campaign_id = f"camp-{k}-{status}"
    databank.add_campaign(
        campaign_id,
        {"instrument": "US100", "timeframe": "M5", "n_total": 440},
        n_total=440,
        status=status,
        db_path=db,
    )
    return campaign_id


def _finalist(db, campaign_id: str, *, status: str = "finalist") -> int:
    strategy_id = databank.add_strategy(
        campaign_id,
        _strategy(),
        status=status,
        db_path=db,
    )
    dates = pd.date_range("2023-01-03", periods=60, freq="D").strftime("%Y-%m-%d").tolist()
    returns = np.linspace(0.001, 0.002, 60).tolist()
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile="CFD-001:US100",
        metrics={
            "is": {"expectancy_r": 0.2},
            "raw": {"expectancy_r": 0.2},
            "return_dates": dates,
        },
        trades_count=120,
        returns=returns,
        db_path=db,
    )
    databank.add_evaluation(
        strategy_id,
        segment="oos1",
        cost_profile="CFD-001:US100",
        metrics={"expectancy_r": 0.1, "return_dates": dates},
        trades_count=30,
        returns=returns,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "test_vs_random_insample",
        {"percentile": 99.0},
        None,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "retest",
        {
            "cost_x1_5": {"expectancy_r": 0.1},
            "slippage_plus_2": {"expectancy_r": 0.1},
            "stress_cost_x1_5_ok": True,
        },
        True,
        db_path=db,
    )
    _perturb_tests(db, strategy_id)
    return strategy_id


def _perturb_tests(db, strategy_id: int) -> None:
    for name in ("perturb_noise", "perturb_delay", "perturb_execution"):
        databank.add_validation(
            strategy_id, name, {"passed": True}, True, db_path=db
        )


def _level4_tests(db, strategy_id: int) -> None:
    databank.add_validation(
        strategy_id, "pbo", {"pbo": 0.2}, True, db_path=db
    )
    databank.add_validation(
        strategy_id, "wf", {"ok": True, "verdict": "ok"}, True, db_path=db
    )
    databank.add_validation(
        strategy_id, "regime", {"passed": True}, True, db_path=db
    )
    databank.add_validation(
        strategy_id, "challenge", {"passed": True}, True, db_path=db
    )
    databank.add_evaluation(
        strategy_id,
        segment="oos2",
        cost_profile="CFD-001:US100",
        metrics={"expectancy_r": 0.1, "trades": 40},
        trades_count=40,
        returns=[0.01] * 20,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "test_vs_random_oos2",
        {"percentile": 99.0, "trades_oos2": 40, "min_trades_oos2": 30},
        True,
        db_path=db,
    )
    databank.add_validation(
        strategy_id, "dsr_confirm", {"dsr": 0.95, "k_finalists": 1}, True, db_path=db
    )


def test_level4_requires_dsr_and_pbo(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db)
    strategy_id = _finalist(db, campaign_id)
    no_data = levels.evaluate(strategy_id, db_path=db)
    assert no_data["level"] == 3
    assert no_data["pbo"] is None
    assert "pbo" in no_data["sin_datos"]
    _level4_tests(db, strategy_id)
    complete = levels.evaluate(strategy_id, db_path=db)
    assert complete["level"] == 4
    assert complete["verdict"] == "ROBUSTA"

    databank.add_validation(
        strategy_id, "pbo", {"pbo": 0.2}, True, db_path=db
    )  # no sobreescribe: sigue 0.2
    # Un PBO 0,31 no puede pasar: se prueba en otra base.
    db2 = tmp_path / "discovery2.db"
    campaign2 = _campaign(db2)
    strategy2 = _finalist(db2, campaign2)
    _level4_tests(db2, strategy2)
    with databank.connect(db2) as con:
        con.execute(
            "UPDATE disc_validations SET result_json = ? WHERE strategy_id = ? AND test = 'pbo'",
            ('{"pbo": 0.31}', strategy2),
        )
    blocked = levels.evaluate(strategy2, db_path=db2)
    assert blocked["level"] == 3
    assert blocked["level4"] is False


def test_missing_level4_test_is_sin_datos_and_no_pass(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db)
    strategy_id = _finalist(db, campaign_id)
    _level4_tests(db, strategy_id)
    with databank.connect(db) as con:
        con.execute(
            "DELETE FROM disc_validations WHERE strategy_id = ? AND test = 'wf'",
            (strategy_id,),
        )
    evaluation = levels.evaluate(strategy_id, db_path=db)
    assert evaluation["level"] == 3
    assert evaluation["level4"] is False
    assert "wf" in evaluation["sin_datos"]
    assert evaluation["verdict"] == "MODERADA"


def test_verdict_table() -> None:
    base = {
        "test_vs_random_insample": {"percentile": 99.0},
        "test_vs_random_oos2": {"percentile": 99.0},
        "retest": {
            "cost_x1_5": {"expectancy_r": 0.1},
            "slippage_plus_2": {"expectancy_r": 0.1},
        },
        "challenge": {"passed": True},
        "wf": {"ok": True},
        "regime": {"passed": True},
    }
    assert (
        levels._verdict(4, base, 0.2, 0.1, 0.1, 0.2, is_finalist=True)
        == "ROBUSTA"
    )
    assert (
        levels._verdict(3, base, 0.2, 0.1, -0.1, 0.2, is_finalist=True)
        == "SOBREAJUSTADA"
    )
    fragile = {**base, "test_vs_random_oos2": {"percentile": 90.0}}
    assert (
        levels._verdict(3, fragile, 0.2, 0.1, None, 0.2, is_finalist=True)
        == "FRÁGIL"
    )
    assert (
        levels._verdict(3, base, 0.2, 0.1, None, 0.2, is_finalist=True)
        == "MODERADA"
    )
    assert (
        levels._verdict(1, base, -0.1, -0.1, None, 0.2, is_finalist=False)
        == "SIN VEREDICTO"
    )


def test_level1_non_finalist_is_sin_veredicto(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db)
    strategy_id = databank.add_strategy(
        campaign_id,
        _strategy(),
        status="evaluated",
        db_path=db,
    )
    dates = pd.date_range("2023-01-03", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile="CFD-001:US100",
        metrics={
            "is": {"expectancy_r": -0.1},
            "raw": {"expectancy_r": -0.1},
            "return_dates": dates,
        },
        trades_count=100,
        returns=[-0.01] * 40,
        db_path=db,
    )
    databank.add_validation(
        strategy_id,
        "test_vs_random_insample",
        {"percentile": 10.0},
        None,
        db_path=db,
    )
    evaluation = levels.evaluate(strategy_id, db_path=db)
    assert evaluation["level"] == 1
    assert evaluation["verdict"] == "SIN VEREDICTO"
    assert evaluation["verdict"] != "FRÁGIL"


def test_pbo_needs_minimum_strategies(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db, status="registered")
    dates = pd.date_range("2023-01-03", periods=120, freq="D").strftime("%Y-%m-%d").tolist()
    rng = np.random.default_rng(1)
    for index in range(3):
        strategy_id = databank.add_strategy(
            campaign_id,
            {**_strategy(), "limits": {"max_trades_per_day": 2 + index, "cooldown_bars": 0}},
            status="evaluated",
            db_path=db,
        )
        returns = rng.normal(0.0, 0.01, 120).tolist()
        databank.add_evaluation(
            strategy_id,
            segment="fitness_is",
            cost_profile="CFD-001:US100",
            metrics={"raw": {"expectancy_r": 0.01}, "return_dates": dates},
            trades_count=50,
            returns=returns,
            db_path=db,
        )
        databank.add_lineage(
            strategy_id,
            parent_a=None,
            parent_b=None,
            operator="seed",
            db_path=db,
        )
        databank.set_lineage_rank(
            strategy_id, 0, 0.0, final=True, db_path=db
        )
    pbo, _wf = robustness._pbo_wf(campaign_id, db)
    assert pbo["status"] == "Sin datos"
    assert pbo["pbo"] is None
    assert pbo["pbo_min_strategies"] == 8


def _confirm_db(
    tmp_path,
    name: str,
    *,
    count: int = 2,
    entry_threshold: float = 0.0,
):
    db = tmp_path / f"{name}.db"
    frame = synthetic_frame(years=0.5, seed=7)
    campaign_id = f"confirm-{name}"
    campaigns.register_synthetic(
        frame,
        template="ny_open_vol_filter",
        profile="small",
        segments=SEGMENTS,
        seed=7,
        campaign_id=campaign_id,
        db_path=db,
    )
    campaigns.mark_done(campaign_id, db_path=db)
    ids = []
    for index in range(count):
        strategy = _strategy()
        strategy["long_entry"]["right"]["value"] = entry_threshold
        strategy["limits"] = {
            "max_trades_per_day": 2,
            "cooldown_bars": index,
        }
        strategy_id = databank.add_strategy(
            campaign_id,
            strategy,
            status="finalist",
            db_path=db,
        )
        dates = pd.date_range("2023-01-03", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
        rng = np.random.default_rng(10 + index)
        values = rng.normal(0.001, 0.002, 40).tolist()
        databank.add_evaluation(
            strategy_id,
            segment="fitness_is",
            cost_profile="CFD-001:US100",
            metrics={
                "is": {"expectancy_r": 0.2},
                "raw": {"expectancy_r": 0.2},
                "return_dates": dates,
            },
            trades_count=100,
            returns=values,
            db_path=db,
        )
        databank.add_evaluation(
            strategy_id,
            segment="oos1",
            cost_profile="CFD-001:US100",
            metrics={"expectancy_r": 0.1, "return_dates": dates},
            trades_count=30,
            returns=values,
            db_path=db,
        )
        databank.add_validation(
            strategy_id,
            "test_vs_random_insample",
            {"percentile": 99.0},
            None,
            db_path=db,
        )
        databank.add_validation(
            strategy_id,
            "retest",
            {
                "cost_x1_5": {"expectancy_r": 0.1},
                "slippage_plus_2": {"expectancy_r": 0.1},
            },
            True,
            db_path=db,
        )
        _perturb_tests(db, strategy_id)
        ids.append(strategy_id)
    databank.set_campaign_counts(campaign_id, n_finalists=count, db_path=db)
    return db, frame, campaign_id, ids


def test_confirmation_dsr_is_order_independent(tmp_path) -> None:
    results = []
    for name, order in (("ab", [0, 1]), ("ba", [1, 0])):
        db, frame, campaign_id, ids = _confirm_db(tmp_path, name)
        first = levels.confirm(
            ids[order[0]],
            approved_by_operator=True,
            frame=frame,
            db_path=db,
            learning_db=tmp_path / "lab.db",
        )
        second = levels.confirm(
            ids[order[1]],
            approved_by_operator=True,
            frame=frame,
            db_path=db,
            learning_db=tmp_path / "lab.db",
        )
        results.append(
            (
                first["dsr_confirm"].get("dsr"),
                second["dsr_confirm"].get("dsr"),
            )
        )
    assert results[0] == results[1]


def test_confirm_single_finalist_uses_psr_vs_zero(tmp_path, monkeypatch) -> None:
    # Comportamiento de las puertas v2 (ENG-1: engine.yaml ya usa v3; la
    # confirmación v3 se prueba en tests/test_eng1_gates_v3.py).
    from tradinglab.discovery.config import load_engine_config

    base = load_engine_config()
    v2 = base.model_copy(
        update={"robustness": base.robustness.model_copy(update={"gates_version": 2})}
    )
    monkeypatch.setattr(levels, "load_engine_config", lambda: v2)
    db, frame, _campaign_id, ids = _confirm_db(tmp_path, "single", count=1)
    result = levels.confirm(
        ids[0],
        approved_by_operator=True,
        frame=frame,
        db_path=db,
        learning_db=tmp_path / "lab.db",
    )
    dsr = result["dsr_confirm"]
    assert dsr["k_finalists"] == 1
    assert dsr["kind"] == "psr_sr0"
    assert dsr["dsr"] is not None
    assert dsr["sr0_period"] == 0.0
    assert "PSR" in dsr["note"]
    random_oos2 = result["test_vs_random_oos2"]
    assert random_oos2["status"] == "ok", random_oos2
    assert random_oos2["percentile"] is not None
    assert random_oos2["percentile"] < 95.0
    assert random_oos2["trades_oos2"] >= 30
    assert dsr["dsr"] < 0.90


def test_confirm_min_trades_oos2_blocks_random_and_dsr(tmp_path) -> None:
    db, frame, _campaign_id, ids = _confirm_db(
        tmp_path, "few", count=1, entry_threshold=1e9
    )
    result = levels.confirm(
        ids[0],
        approved_by_operator=True,
        frame=frame,
        db_path=db,
        learning_db=tmp_path / "lab.db",
    )
    assert result["test_vs_random_oos2"]["status"] == "Sin datos"
    assert result["test_vs_random_oos2"]["percentile"] is None
    assert "reason" in result["test_vs_random_oos2"], result["test_vs_random_oos2"]
    assert "min_trades_oos2" in result["test_vs_random_oos2"]["reason"]
    assert result["dsr_confirm"]["status"] == "Sin datos"
    assert result["dsr_confirm"]["dsr"] is None
    assert "min_trades_oos2" in result["dsr_confirm"]["reason"]
    assert result["level"] == 3
    assert result["level4"] is False
    assert "test_vs_random_oos2" in result["sin_datos"]
    assert "dsr_confirm" in result["sin_datos"]
    assert databank.count_holdout_reads(db_path=db) == 1


def test_confirm_without_flag_does_not_read(tmp_path) -> None:
    db, frame, campaign_id, ids = _confirm_db(tmp_path, "noflag")
    with pytest.raises(PermissionError, match="approved-by-operator"):
        levels.confirm(ids[0], approved_by_operator=False, frame=frame, db_path=db)
    assert databank.count_holdout_reads(db_path=db) == 0


def test_sin_perturb_no_es_nivel3(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db)
    strategy_id = _finalist(db, campaign_id)
    with databank.connect(db) as con:
        con.execute(
            "DELETE FROM disc_validations"
            " WHERE strategy_id = ? AND test LIKE 'perturb_%'",
            (strategy_id,),
        )
    evaluation = levels.evaluate(strategy_id, db_path=db)
    assert evaluation["level"] == 2
    assert evaluation["level3"] is False
    assert evaluation["perturb_noise_ok"] is False
    assert "perturb_noise" in evaluation["sin_datos"]
    assert "perturb_delay" in evaluation["sin_datos"]
    assert "perturb_execution" in evaluation["sin_datos"]


def test_perturb_failure_blocks_level3(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    campaign_id = _campaign(db)
    strategy_id = _finalist(db, campaign_id)
    with databank.connect(db) as con:
        con.execute(
            "UPDATE disc_validations SET passed = 0, result_json = ?"
            " WHERE strategy_id = ? AND test = 'perturb_noise'",
            ('{"passed": false}', strategy_id),
        )
    evaluation = levels.evaluate(strategy_id, db_path=db)
    assert evaluation["level"] == 2
    assert evaluation["level3"] is False
    assert evaluation["perturb_noise_ok"] is False
