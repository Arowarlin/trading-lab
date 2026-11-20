"""Motor: solo IS, OOS-1 al final, reproducibilidad y guardas del CLI."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tradinglab.cli import app
from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, dsl, engine, genetic
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.learning import count_tests

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}


def _register(db: Path, seed: int, campaign_id: str) -> dict:
    frame = synthetic_frame(years=0.5, seed=seed)
    campaigns.register_synthetic(
        frame,
        template="ny_open_vol_filter",
        profile="small",
        segments=SEGMENTS,
        seed=seed,
        campaign_id=campaign_id,
        db_path=db,
    )
    return frame


def test_engine_source_never_reads_holdout() -> None:
    import ast

    source = Path(engine.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name == "read_holdout":
            calls.append("read_holdout")
        if name == "load_segment":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == "oos2":
                    calls.append("load_segment(oos2)")
    assert calls == []
    assert source.index("mark_done") < source.index('"oos1"')
    assert 'load_segment(campaign_id, "is"' in source


def test_engine_is_reproducible(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    frame = _register(db, 9, "rep-1")
    second_frame = _register(db, 9, "rep-2")
    assert frame.equals(second_frame)
    first = engine.run_campaign(
        "rep-1", workers=8, synthetic=True, db_path=db, bars=frame
    )
    second = engine.run_campaign(
        "rep-2", workers=8, synthetic=True, db_path=db, bars=second_frame
    )
    assert first["n_evaluated"] == second["n_evaluated"]
    assert first["n_effective"] == second["n_effective"]
    assert first["frontier"] == second["frontier"]
    assert [item["strategy_hash"] for item in first["finalists"]] == [
        item["strategy_hash"] for item in second["finalists"]
    ]
    rows_first = databank.list_strategies(
        campaign_id="rep-1", limit=None, db_path=db
    )
    rows_second = databank.list_strategies(
        campaign_id="rep-2", limit=None, db_path=db
    )
    assert [row["strategy_hash"] for row in rows_first] == [
        row["strategy_hash"] for row in rows_second
    ]
    assert [row["generation"] for row in rows_first] == [
        row["generation"] for row in rows_second
    ]
    diagnostics = first["diagnostics"]
    assert diagnostics["init"]["generated"] == load_engine_config().profile(
        "small"
    ).population
    assert diagnostics["submitted"] == (
        diagnostics["init"]["generated"]
        + sum(row["submitted"] for row in diagnostics["generations"])
    )
    assert (
        diagnostics["evaluated"] + diagnostics["evaluation_errors"]
        == diagnostics["submitted"]
    )
    assert diagnostics["stop_reason"] in {
        "generations",
        "empty_offspring",
        "budget",
        "time_limit",
    }
    assert all(
        row["submitted"] <= row["slots"] for row in diagnostics["generations"]
    )
    assert count_tests(lab, discovery_db=db) == 0


def test_cli_run_requires_registered_and_flag(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    frame = synthetic_frame(years=0.3, seed=4)
    campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments={
            "is": ["2023-01-02", "2023-02-28"],
            "oos1": ["2023-03-01", "2023-03-31"],
            "oos2": ["2023-04-01", None],
        },
        frame=frame,
        campaign_id="draft",
        db_path=db,
    )
    runner = CliRunner()
    without = runner.invoke(
        app, ["discovery", "run", "draft", "--db", str(db)]
    )
    assert without.exit_code == 1
    with_flag = runner.invoke(
        app,
        [
            "discovery",
            "run",
            "draft",
            "--approved-by-operator",
            "--db",
            str(db),
        ],
    )
    assert with_flag.exit_code == 1
    assert databank.get_campaign("draft", db_path=db)["status"] == "draft"


def test_initial_population_uses_real_instrument(tmp_path) -> None:
    """Campaña sobre ``US100.CASH`` con barras sintéticas y la plantilla real."""

    db = tmp_path / "discovery.db"
    frame = synthetic_frame(years=0.5, seed=20261120)
    campaigns.register(
        "US100.CASH",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        seed=20261120,
        campaign_id="real-instrument",
        frame=frame,
        db_path=db,
    )
    campaigns.approve("real-instrument", db_path=db)
    campaign = databank.get_campaign("real-instrument", db_path=db)
    assert campaign is not None
    profile = load_engine_config().profile("small")

    strategies = engine.initial_strategies(
        campaign,
        template="ny_open_vol_filter",
        population=profile.population,
        rng=random.Random(20261120),
    )

    assert len(strategies) >= 40
    for strategy in strategies:
        assert dsl.validate(strategy) == []
        assert strategy["instrument"] == "US100.CASH"
        assert strategy["timeframe"] == "M5"
        assert strategy["session"]["tz"] == "America/New_York"


class _RejectedEvaluator:
    """Evaluador falso: todos los candidatos fallan antes de tocar barras."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_RejectedEvaluator":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def evaluate(self, strategies, kind: str = "fitness") -> list[dict]:
        return [
            {"error": "QueueError: instrumento US100 != US100.CASH de la campaña"}
            for _strategy in strategies
        ]


class _BrokenEvaluator:
    """Evaluador falso: el arranque del worker falla antes de evaluar nada."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_BrokenEvaluator":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def evaluate(self, strategies, kind: str = "fitness") -> list[dict]:
        raise RuntimeError("Sin datos: menos de 100 barras en el tramo IS")


def _register_real(db, campaign_id: str, seed: int, frame) -> None:
    campaigns.register(
        "US100.CASH",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        seed=seed,
        campaign_id=campaign_id,
        frame=frame,
        db_path=db,
    )
    campaigns.approve(campaign_id, db_path=db)


def test_failed_initialization_restores_registered(tmp_path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    frame = synthetic_frame(years=0.5, seed=5)
    _register_real(db, "real-instrument-fail", 5, frame)
    monkeypatch.setattr(engine.jobs, "BatchEvaluator", _RejectedEvaluator)
    before = count_tests(lab, discovery_db=db)
    approved_at = databank.get_campaign(
        "real-instrument-fail", db_path=db
    )["approved_at"]

    for _attempt in range(2):
        with pytest.raises(campaigns.CampaignError) as excinfo:
            engine.run_campaign(
                "real-instrument-fail", workers=1, db_path=db, bars=frame
            )
        message = str(excinfo.value)
        assert "población inicial vacía" in message
        assert "instrumento US100 != US100.CASH" in message
        row = databank.get_campaign("real-instrument-fail", db_path=db)
        assert row is not None
        assert row["status"] == "registered"
        assert not row["n_evaluated"]
        assert row["n_total"] == 440
        assert row["approved_at"] == approved_at
        assert "población inicial vacía" in row["last_error"]

    # Dos intentos fallidos: el DSR sigue contando la campaña una sola vez.
    assert before == 440
    assert count_tests(lab, discovery_db=db) == before


def test_startup_error_restores_registered_with_reason(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "discovery.db"
    frame = synthetic_frame(years=0.5, seed=6)
    _register_real(db, "real-startup-fail", 6, frame)
    monkeypatch.setattr(engine.jobs, "BatchEvaluator", _BrokenEvaluator)
    approved_at = databank.get_campaign(
        "real-startup-fail", db_path=db
    )["approved_at"]

    with pytest.raises(RuntimeError):
        engine.run_campaign(
            "real-startup-fail", workers=1, db_path=db, bars=frame
        )

    row = databank.get_campaign("real-startup-fail", db_path=db)
    assert row is not None
    assert row["status"] == "registered"
    assert row["n_total"] == 440
    assert row["approved_at"] == approved_at
    assert not row["n_evaluated"]
    assert "menos de 100 barras" in row["last_error"]
    assert databank.count_strategies("real-startup-fail", db_path=db) == 0


def test_preflight_counts_generated_valid_and_rejected(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    frame = synthetic_frame(years=0.5, seed=20261120)
    campaigns.register(
        "US100.CASH",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        seed=20261120,
        campaign_id="real-preflight",
        frame=frame,
        db_path=db,
    )

    report = engine.preflight("real-preflight", db_path=db)

    assert report["status"] == "draft"
    assert report["instrument"] == "US100.CASH"
    assert report["population"] == 40
    assert report["generated"] >= 40
    assert report["valid"] >= 40
    assert report["rejected"] == 0
    assert report["reasons"] == {}
    # Sin efectos: el borrador sigue igual y no hay estrategias guardadas.
    assert databank.get_campaign("real-preflight", db_path=db)["status"] == "draft"
    assert databank.count_strategies("real-preflight", db_path=db) == 0


def test_cli_preflight_fails_below_population(tmp_path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    frame = synthetic_frame(years=0.5, seed=7)
    campaigns.register(
        "US100.CASH",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        seed=7,
        campaign_id="real-preflight-fail",
        frame=frame,
        db_path=db,
    )

    def _only_template(campaign, **kwargs):
        return [genetic.template_strategy("ny_open_vol_filter")]

    monkeypatch.setattr(engine, "initial_strategies", _only_template)
    result = CliRunner().invoke(
        app, ["discovery", "preflight", "real-preflight-fail", "--db", str(db)]
    )

    assert result.exit_code == 1
    assert "instrumento US100 != US100.CASH" in result.output
    assert "Preflight FAIL" in result.output
    assert databank.count_strategies("real-preflight-fail", db_path=db) == 0


def test_finalist_rule_requires_positive_full_is() -> None:
    folds = [{"expectancy_r": 0.1}] * 3 + [{"expectancy_r": -0.1}]
    negative = engine.Individual(
        strategy={},
        strategy_hash="neg",
        feasible=True,
        rank=0,
        folds=folds,
        metrics={"is": {"expectancy_r": -0.01}},
    )
    candidates, discarded = engine._rank1_candidates([negative], 4)
    assert candidates == []
    assert "IS completa" in discarded[0][1]

    positive = engine.Individual(
        strategy={},
        strategy_hash="pos",
        feasible=True,
        rank=0,
        folds=folds,
        metrics={"is": {"expectancy_r": 0.01}},
    )
    candidates, discarded = engine._rank1_candidates([positive], 4)
    assert candidates == [positive]
    assert discarded == []


def test_noise_fixtures_have_valid_finalists() -> None:
    import json

    from tradinglab.discovery import dsl

    cases = {
        ROOT / "tests" / "fixtures" / "discovery_noise_seed2_finalists.json": 1,
        ROOT
        / "tests"
        / "fixtures"
        / "discovery_noise_09y_seed2_finalists.json": 2,
    }
    for path, expected in cases.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert len(payload["finalists"]) == expected
        for item in payload["finalists"]:
            assert dsl.validate(item["dsl"]) == []
            assert "finalista" in item["selection_reason"]
