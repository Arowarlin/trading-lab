"""Perturbation Lab: edge que sobrevive, sobreajuste que cae y determinismo."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from tradinglab.cli import app
from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, dsl, fastbt, perturb
from tradinglab.discovery.config import load_engine_config as real_engine_config
from tradinglab.discovery.jobs import QueueSetup
from tradinglab.learning import count_tests


def _setup() -> QueueSetup:
    return QueueSetup(
        instrument="US100.CASH",
        timeframe="M5",
        session_tz="America/New_York",
        session_start="09:35",
        session_end="15:59",
        flat_at="15:55",
    )


def _cost() -> fastbt.CfdBpsCosts:
    return fastbt.CfdBpsCosts(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )


def _session() -> dict:
    return {
        "start": "09:35",
        "end": "15:59",
        "flat_at": "15:55",
        "or_minutes": 15,
        "tz": "America/New_York",
    }


def _trend_case() -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(7)
    n = 3000
    index = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    close = 100 + np.arange(n) * 0.02 + np.cumsum(rng.normal(0, 0.05, n))
    open_ = np.r_[close[0], close[:-1]]
    frame = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 0.05,
            "low": np.minimum(open_, close) - 0.05,
            "close": close,
        },
        index=index,
    )
    strategy = {
        "dsl_version": "1",
        "instrument": "US100.CASH",
        "market": "cfd",
        "timeframe": "M5",
        "session": _session(),
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "indicator", "ind": "ema", "src": "close", "n": 5},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 5.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
            "time_exit_bars": 100,
        },
        "limits": {"max_trades_per_day": 100, "cooldown_bars": 0},
    }
    return frame, strategy


def _overfit_case() -> tuple[pd.DataFrame, dict]:
    n = 80
    index = pd.date_range(
        "2024-01-02 09:35", periods=n, freq="5min", tz="America/New_York"
    )
    close = np.full(n, 100.0)
    close[20] = 110.0
    for offset in range(1, 30):
        close[20 + offset] = 110.0 + offset * 0.2
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.1
    low = np.minimum(open_, close) - 0.1
    high[20] = 111.0
    low[20] = 99.0
    frame = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )
    strategy = {
        "dsl_version": "1",
        "instrument": "US100.CASH",
        "market": "cfd",
        "timeframe": "M5",
        "session": _session(),
        "long_entry": {
            "kind": "between",
            "left": {"kind": "price", "price": "close"},
            "low": 109.99,
            "high": 110.01,
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 2.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
            "time_exit_bars": 20,
        },
        "limits": {"max_trades_per_day": 10, "cooldown_bars": 0},
    }
    return frame, strategy


def test_noise_survives_injected_edge() -> None:
    frame, strategy = _trend_case()
    result = perturb.noise_test(
        strategy,
        frame,
        paths=12,
        scale_atr=0.10,
        seed=1,
        cost=_cost(),
        setup=_setup(),
    )

    assert result["base"] is not None and result["base"] > 0.0
    assert result["median"] is not None and result["median"] > 0.0
    assert result["ratio"] is not None and result["ratio"] >= 0.5
    assert result["positive_frac"] == 1.0


def test_noise_rejects_overfit() -> None:
    frame, strategy = _overfit_case()
    result = perturb.noise_test(
        strategy,
        frame,
        paths=20,
        scale_atr=0.10,
        seed=3,
        cost=_cost(),
        setup=_setup(),
    )

    assert result["base"] is not None and result["base"] > 0.0
    assert result["median"] is not None
    assert result["median"] <= 0.0 or (result["ratio"] or 0.0) < 0.5


def test_delay_and_execution_survive_edge() -> None:
    frame, strategy = _trend_case()
    delay = perturb.delay_test(
        strategy,
        frame,
        entry_delays=(1, 2),
        exit_delays=(1, 2),
        cost=_cost(),
        setup=_setup(),
    )
    assert delay["entry"]["1"]["ratio"] >= 0.5
    assert delay["entry"]["2"]["ratio"] >= 0.5

    execution = perturb.execution_mc(
        strategy,
        frame,
        skip_frac=0.05,
        spread_source=None,
        slippage_pts=0.0,
        paths=20,
        seed=2,
        cost=_cost(),
        setup=_setup(),
    )
    assert execution["median"] is not None and execution["median"] > 0.0
    assert execution["ratio"] >= 0.5


def test_perturb_is_deterministic() -> None:
    frame, strategy = _trend_case()
    first = perturb.noise_test(
        strategy, frame, paths=6, scale_atr=0.1, seed=9, cost=_cost(), setup=_setup()
    )
    second = perturb.noise_test(
        strategy, frame, paths=6, scale_atr=0.1, seed=9, cost=_cost(), setup=_setup()
    )
    assert first == second

    exec_first = perturb.execution_mc(
        strategy,
        frame,
        skip_frac=0.05,
        spread_source={9: 1.0, 10: 1.2},
        slippage_pts=0.5,
        paths=10,
        seed=4,
        cost=_cost(),
        setup=_setup(),
    )
    exec_second = perturb.execution_mc(
        strategy,
        frame,
        skip_frac=0.05,
        spread_source={9: 1.0, 10: 1.2},
        slippage_pts=0.5,
        paths=10,
        seed=4,
        cost=_cost(),
        setup=_setup(),
    )
    assert exec_first == exec_second


def test_perturb_frame_keeps_ohlc_coherent() -> None:
    frame, _strategy = _trend_case()
    for seed in range(5):
        rng = np.random.default_rng(seed)
        noisy = perturb.perturb_frame(frame, scale_atr=0.10, rng=rng)
        assert not noisy[["open", "high", "low", "close"]].isna().any().any()
        assert (noisy[["open", "high", "low", "close"]] > 0).all().all()
        assert (noisy["high"] >= noisy[["open", "close", "low"]].max(axis=1)).all()
        assert (noisy["low"] <= noisy[["open", "close", "high"]].min(axis=1)).all()


def test_perturb_ast_no_lee_oos2() -> None:
    from tradinglab.discovery import perturb as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "read_holdout" not in source
    assert "oos2" not in source.lower()


def test_skip_validation_solo_en_perturb_y_solo_archivadas(tmp_path) -> None:
    from tradinglab.discovery import engine, fitness, genetic, jobs

    for module in (engine, jobs, fitness, genetic):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "_skip_validation_for_archived" not in source
    source = Path(perturb.__file__).read_text(encoding="utf-8")
    assert "_skip_validation_for_archived" in source
    assert "databank.get_strategy" in source

    payload = json.loads(
        (
            Path(ROOT) / "tests" / "fixtures" / "discovery_regla_anomala_258.json"
        ).read_text(encoding="utf-8")
    )
    frame, _strategy = _trend_case()
    db = tmp_path / "discovery.db"
    databank.init_databank(db)
    with pytest.raises(dsl.DslError):
        perturb.noise_test(
            payload["dsl"],
            frame,
            paths=1,
            scale_atr=0.1,
            seed=1,
            cost=_cost(),
            setup=_setup(),
            strategy_id=999999,
            db_path=db,
        )

    databank.add_campaign(
        "archived",
        {"instrument": "US100.CASH", "timeframe": "M5"},
        n_total=1,
        db_path=db,
    )
    strategy_id = databank.add_strategy(
        "archived", payload["dsl"], status="finalist", db_path=db
    )
    result = perturb.noise_test(
        payload["dsl"],
        frame,
        paths=1,
        scale_atr=0.1,
        seed=1,
        cost=_cost(),
        setup=_setup(),
        strategy_id=strategy_id,
        db_path=db,
    )
    assert "base" in result


def test_cli_perturb_no_cambia_count_tests(tmp_path, monkeypatch) -> None:
    import tradinglab.discovery.config as config_module

    frame, strategy = _trend_case()
    db = tmp_path / "discovery.db"
    campaigns.register_synthetic(
        frame,
        instrument="US100.CASH",
        template="ny_open_vol_filter",
        profile="small",
        segments={
            "is": ["2024-01-01", "2024-01-04"],
            "oos1": ["2024-01-05", "2024-01-07"],
            "oos2": ["2024-01-08", None],
        },
        seed=1,
        campaign_id="perturb-cli",
        db_path=db,
    )
    campaign = databank.get_campaign("perturb-cli", db_path=db)
    assert campaign is not None
    campaigns.mark_done("perturb-cli", db_path=db)
    strategy_id = databank.add_strategy(
        "perturb-cli", strategy, status="finalist", db_path=db
    )
    setup = QueueSetup(
        instrument="US100.CASH",
        timeframe="M5",
        session_tz="America/New_York",
        session_start="09:35",
        session_end="15:59",
        flat_at="15:55",
    )
    cost = _cost()
    monkeypatch.setattr(
        perturb,
        "load_campaign_inputs",
        lambda campaign_id, db_path=None: (frame, campaign, setup, cost),
    )
    monkeypatch.setattr(perturb, "load_spread_histogram", lambda symbol: {})
    base_config = real_engine_config()
    fake = base_config.model_copy(
        update={
            "perturb": base_config.perturb.model_copy(
                update={
                    "noise_paths": 3,
                    "exec_paths": 3,
                    "entry_delays": [1],
                    "exit_delays": [1],
                }
            )
        }
    )
    monkeypatch.setattr(config_module, "load_engine_config", lambda *a, **k: fake)

    lab = tmp_path / "lab.db"
    before = count_tests(lab, discovery_db=db)
    result = CliRunner().invoke(
        app, ["discovery", "perturb", str(strategy_id), "--db", str(db)]
    )

    assert result.exit_code == 0, result.output
    assert count_tests(lab, discovery_db=db) == before == 0
    validations = {
        row["test"]
        for row in databank.list_validations(strategy_id, db_path=db)
    }
    assert {"perturb_noise", "perturb_delay", "perturb_execution"} <= validations
