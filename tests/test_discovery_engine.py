"""Motor: solo IS, OOS-1 al final, reproducibilidad y guardas del CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tradinglab.cli import app
from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, engine
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


def test_noise_fixture_has_valid_finalists() -> None:
    import json

    from tradinglab.discovery import dsl

    path = ROOT / "tests" / "fixtures" / "discovery_noise_seed2_finalists.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["finalists"]) == 3
    for item in payload["finalists"]:
        assert dsl.validate(item["dsl"]) == []
        assert "finalista" in item["selection_reason"]
