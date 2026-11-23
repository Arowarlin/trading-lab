"""Control contra deriva (R8): percentil de entradas aleatorias."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.discovery import campaigns, databank, fastbt, fitness, jobs, results
from tradinglab.discovery.engine import (
    Individual,
    _rank1_candidates,
    synthetic_frame,
)
from tradinglab.propfund.costs import load_profile

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-07-31"],
    "oos2": ["2023-08-01", None],
}

SEGMENTS_SHORT = {
    "is": ["2023-01-02", "2023-02-15"],
    "oos1": ["2023-02-16", "2023-03-01"],
    "oos2": ["2023-03-02", None],
}


def _setup(frame: pd.DataFrame) -> jobs.QueueSetup:
    return jobs.QueueSetup(
        instrument="US100",
        timeframe="M5",
        start=None,
        end=None,
        session_tz="America/New_York",
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        bars=frame,
        campaign_id="drift-test",
        drift_simulations=1000,
        drift_percentile_min=90.0,
    )


def _prepared(frame: pd.DataFrame):
    cost = fastbt.cost_from_profile(load_profile("CFD-001", "US100", firm="ftmo"))
    limits = fastbt.RunLimits(
        session_tz="America/New_York",
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        weekdays=(0, 1, 2, 3, 4, 5, 6),
    )
    prepared = fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))
    return cost, prepared


def _strategy(entry: dict, time_exit: int = 20) -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "00:00", "end": "23:59", "flat_at": "23:59"},
        "long_entry": entry,
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "n": 14, "mult": 1.5},
            "target": {"type": "rr", "rr": 1.5},
            "time_exit_bars": time_exit,
        },
        "limits": {"max_trades_per_day": 10, "cooldown_bars": 0},
    }


def _trend_frame(periods: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = 20_000.0 + 0.02 * np.arange(periods) + rng.normal(0, 2, periods)
    index = pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC")
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 5.0,
            "low": np.minimum(open_, close) - 5.0,
            "close": close,
        },
        index=index,
    )


def _edge_frame(periods: int = 6000) -> pd.DataFrame:
    """Subida fuerte y breve tras una caída; el resto es ruido plano."""

    rng = np.random.default_rng(7)
    close = np.empty(periods)
    price = 20_000.0
    for index in range(periods):
        phase = index % 100
        if phase == 0:
            price -= 160.0
        elif phase <= 10:
            price += 30.0
        else:
            price += rng.normal(0.0, 2.0)
        close[index] = price
    index = pd.date_range("2026-01-01", periods=periods, freq="5min", tz="UTC")
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + 5.0,
            "low": np.minimum(open_, close) - 5.0,
            "close": close,
        },
        index=index,
    )


def _evaluate(frame: pd.DataFrame, strategy: dict) -> dict:
    setup = _setup(frame)
    cost, prepared = _prepared(frame)
    return fitness.evaluate(
        strategy,
        frame,
        cost,
        setup,
        prepared,
        campaign_id=setup.campaign_id,
        drift_simulations=1000,
        drift_percentile_min=90.0,
    )


def test_deriva_pura_percentil_cerca_de_50_y_no_pasa() -> None:
    strategy = _strategy(
        {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 0.0},
        }
    )
    result = _evaluate(_trend_frame(), strategy)
    drift = result["drift"]
    assert drift["trades"] > 50
    assert 35.0 <= float(drift["percentile"]) <= 65.0
    assert drift["passed"] is False
    assert drift["percentile_min"] == pytest.approx(90.0)


def test_ventaja_sintetica_pasa() -> None:
    strategy = _strategy(
        {
            "kind": "lt",
            "left": {"kind": "indicator", "ind": "rsi", "src": "close", "n": 14},
            "right": {"kind": "const", "value": 30.0},
        },
        time_exit=10,
    )
    result = _evaluate(_edge_frame(), strategy)
    drift = result["drift"]
    assert drift["trades"] > 20
    assert float(drift["percentile"]) >= 90.0
    assert drift["passed"] is True


def test_campana_antigua_sin_marca_no_calcula_deriva() -> None:
    campaign = {
        "id": "old",
        "instrument": "US100",
        "timeframe": "M5",
        "config": {},
    }
    setup = jobs.QueueSetup.from_campaign(campaign)
    assert setup.drift_simulations == 0
    assert setup.drift_percentile_min == 0.0
    frame = synthetic_frame(years=0.2, seed=3)
    cost, prepared = _prepared(frame)
    strategy = _strategy(
        {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 0.0},
        }
    )
    result = fitness.evaluate(
        strategy, frame, cost, setup, prepared, campaign_id="old"
    )
    assert result["drift"] is None
    assert "drift" not in result["metrics"]


def test_campana_nueva_lleva_marca_y_activa_el_control(tmp_path) -> None:
    frame = synthetic_frame(years=0.2, seed=17)
    preview = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS_SHORT,
        frame=frame,
        campaign_id="new-control",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    control = preview["config"]["controls"]["test_vs_random_direction"]
    assert control["simulations"] == 1000
    assert control["percentile_min"] == 90
    setup = jobs.QueueSetup.from_campaign(
        {
            "id": "new-control",
            "instrument": "US100",
            "timeframe": "M5",
            "is_start": SEGMENTS_SHORT["is"][0],
            "is_end": SEGMENTS_SHORT["is"][1],
            "config": preview["config"],
        }
    )
    assert setup.campaign_id == "new-control"
    assert setup.drift_simulations == 1000
    assert setup.drift_percentile_min == pytest.approx(90.0)


def test_campana_sintetica_no_lleva_control(tmp_path) -> None:
    frame = synthetic_frame(years=0.2, seed=17)
    campaign = campaigns.register_synthetic(
        frame,
        profile="small",
        segments=SEGMENTS_SHORT,
        seed=17,
        campaign_id="synthetic-control",
        db_path=tmp_path / "discovery.db",
    )
    assert "controls" not in campaign["config"]
    setup = jobs.QueueSetup.from_campaign(campaign, bars=frame)
    assert setup.drift_simulations == 0


def _individual(metrics: dict) -> Individual:
    item = Individual(
        strategy={},
        strategy_hash="hash",
        generation=0,
        operator="seed",
        origin="template",
        parents=(None, None),
        metrics=metrics,
        feasible=True,
        folds=[{"expectancy_r": 0.1}] * 4,
    )
    item.rank = 0
    return item


def test_rank1_exige_percentil_solo_si_la_evaluacion_lo_trae() -> None:
    old = _individual({"is": {"expectancy_r": 0.2}})
    low = _individual(
        {
            "is": {"expectancy_r": 0.2},
            "drift": {"percentile": 55.0, "percentile_min": 90.0},
        }
    )
    high = _individual(
        {
            "is": {"expectancy_r": 0.2},
            "drift": {"percentile": 95.0, "percentile_min": 90.0},
        }
    )
    candidates, discarded = _rank1_candidates([old, low, high], 4)
    assert [id(item) for item in candidates] == [id(old), id(high)]
    assert len(discarded) == 1
    assert "percentil deriva 55.0 < 90" in discarded[0][1]


def test_results_muestra_percentil_de_deriva(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    databank.add_campaign(
        "camp",
        {"instrument": "US100", "timeframe": "M5"},
        instrument="US100",
        timeframe="M5",
        status="done",
        n_total=1,
        db_path=db,
    )
    strategy_id = databank.add_strategy(
        "camp",
        _strategy(
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 0.0},
            }
        ),
        status="evaluated",
        db_path=db,
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile=None,
        metrics={
            "is": {
                "expectancy_r": 0.2,
                "gross_expectancy_r": 0.25,
                "trades": 100,
                "profit_factor": 1.4,
            },
            "folds": [{"expectancy_r": 0.1}] * 4,
            "drift": {"percentile": 93.5, "percentile_min": 90.0, "passed": True},
        },
        trades_count=100,
        db_path=db,
    )
    report = results.campaign_results("camp", db_path=db)
    row = report["rows"][0]
    assert row["drift_percentile"] == pytest.approx(93.5)
    assert row["drift_passed"] is True
    output = CliRunner().invoke(
        cli_mod.app,
        ["discovery", "results", "camp", "--db", str(db)],
        env={"COLUMNS": "240"},
    )
    assert output.exit_code == 0, output.output
    assert "93.5" in output.output


def test_campana_antigua_conserva_estado_sin_percentil(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    config = {"instrument": "US100", "timeframe": "M5"}
    databank.add_campaign(
        "old-camp",
        config,
        instrument="US100",
        timeframe="M5",
        status="done",
        n_total=1,
        db_path=db,
    )
    strategy_id = databank.add_strategy(
        "old-camp",
        _strategy(
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 0.0},
            }
        ),
        status="finalist",
        db_path=db,
    )
    databank.set_strategy_selection(
        strategy_id, "finalist", "finalista: OOS-1 histórico", db_path=db
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile=None,
        metrics={
            "is": {
                "expectancy_r": 0.2,
                "gross_expectancy_r": 0.25,
                "trades": 100,
                "profit_factor": 1.4,
            },
            "folds": [{"expectancy_r": 0.1}] * 4,
        },
        trades_count=100,
        db_path=db,
    )
    report = results.campaign_results("old-camp", db_path=db)
    row = report["rows"][0]
    assert row["drift_percentile"] is None
    assert row["status"] == "finalist"
    assert row["verdict"] == "FINALISTA"
    assert row["reason"] == "finalista: OOS-1 histórico"
