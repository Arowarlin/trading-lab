"""Modo rejilla: 144 combinaciones, estructura bloqueada y preflight."""

from __future__ import annotations

import copy
import json

from tradinglab.discovery import campaigns, dsl, engine, genetic, grid

SEGMENTS = {
    "is": ["2023-01-02", "2023-04-30"],
    "oos1": ["2023-05-01", "2023-05-31"],
    "oos2": ["2023-06-01", None],
}
SESSION = {
    "tz": "America/New_York",
    "start": "09:30",
    "end": "15:55",
    "flat_at": "15:55",
    "or_minutes": 15,
}


def _strategies() -> list[dict]:
    return grid.grid_strategies(
        "intraday_momentum_close",
        instrument="US100.CASH",
        timeframe="M5",
        session=SESSION,
    )


def _skeleton(strategy: dict) -> str:
    long_entry = copy.deepcopy(strategy["long_entry"])
    long_entry["args"][0]["right"]["value"] = 0.0
    long_entry["args"][0]["left"]["params"]["end"] = 0
    long_entry["args"][1]["start"] = "X"
    long_entry["args"] = [
        node for node in long_entry["args"] if node.get("kind") != "regime"
    ]
    exit_block = copy.deepcopy(strategy["exit"])
    exit_block["stop"]["mult"] = 0.0
    exit_block["target"]["rr"] = 0.0
    exit_block["time_exit_bars"] = 0
    session = copy.deepcopy(strategy["session"])
    session["flat_at"] = "X"
    return json.dumps(
        {"long_entry": long_entry, "exit": exit_block, "session": session},
        sort_keys=True,
    )


def test_grid_genera_144_unicas_y_validas() -> None:
    assert grid.grid_size("intraday_momentum_close") == 144
    strategies = _strategies()

    assert len(strategies) == 144
    assert len({dsl.strategy_hash(item) for item in strategies}) == 144
    for item in strategies:
        assert dsl.validate(item) == []
        assert item["instrument"] == "US100.CASH"
        assert item["short_entry"] == genetic.mirror_expr(item["long_entry"])


def test_grid_estructura_bloqueada() -> None:
    skeletons = {_skeleton(item) for item in _strategies()}
    assert len(skeletons) == 1


def test_grid_campaign_n_total_y_preflight(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    frame = engine.synthetic_frame(years=0.5, seed=20261121)
    campaign = campaigns.register_synthetic(
        frame,
        instrument="US100",
        template="intraday_momentum_close",
        profile="small",
        segments=SEGMENTS,
        seed=20261121,
        campaign_id="grid-1",
        mode="grid",
        db_path=db,
    )

    assert campaign["n_total"] == 144
    assert campaign["config"]["mode"] == "grid"
    assert campaign["config"]["grid_size"] == 144
    report = engine.preflight("grid-1", db_path=db)
    assert report["mode"] == "grid"
    assert report["population"] == 144
    assert report["generated"] == 144
    assert report["valid"] == 144
    assert report["rejected"] == 0
