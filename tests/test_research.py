from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import tradinglab.research as research
from tradinglab.prop.rules import ftmo


def _frame(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0004, 0.009, n)
    close = 100 * np.exp(np.cumsum(rets))
    idx = pd.bdate_range("2019-01-01", periods=n)
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, n)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=idx,
    )


def test_run_research_ranks_and_never_enables(monkeypatch):
    monkeypatch.setattr(research.data_mod, "fetch", lambda *a, **k: _frame())

    cfg = research.ResearchConfig(
        symbols=["TEST"],
        strategies=["trend"],
        start="2019-01-01",
        end="2024-12-31",
        paths=100,
        horizon=20,
        block_size=1,
        min_pass=0.0,
        max_breach=1.0,
        min_trades=0,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["candidates"] == 4  # fast × slow
    assert len(report["results"]) == 4
    assert report["results"][0]["score"] >= report["results"][1]["score"]
    assert all("family_median_pass" in r for r in report["results"])
    assert all(p["enabled"] is False for p in report["proposals"])
    assert all(p["status"] == "proposed" for p in report["proposals"])
    assert all("oos_pass_rate" in p for p in report["proposals"])


def test_run_research_survives_bad_symbol(monkeypatch):
    def fake_fetch(symbol, *a, **k):
        if symbol == "BAD":
            raise RuntimeError("sin datos")
        return _frame()

    monkeypatch.setattr(research.data_mod, "fetch", fake_fetch)
    cfg = research.ResearchConfig(
        symbols=["BAD", "OK"],
        strategies=["trend"],
        paths=50,
        horizon=10,
        block_size=1,
        min_trades=0,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert any(e["symbol"] == "BAD" for e in report["errors"])
    assert report["candidates"] == 4


def test_write_outputs_creates_files(tmp_path, monkeypatch):
    monkeypatch.setattr(research.data_mod, "fetch", lambda *a, **k: _frame())
    cfg = research.ResearchConfig(
        symbols=["TEST"],
        strategies=["trend"],
        paths=50,
        horizon=10,
        block_size=1,
        min_pass=0.0,
        max_breach=1.0,
        min_trades=0,
        min_oos_pass=0.0,
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")
    files = research.write_outputs(report, tmp_path)

    for key in ("latest_json", "latest_md", "proposals_json", "proposals_md"):
        assert Path(files[key]).exists()

    proposals = json.loads((tmp_path / "proposals.json").read_text(encoding="utf-8"))
    assert proposals["auto_enable"] is False
    md = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "Ranking" in md
    assert "enabled: false" in md


def test_near_misses_are_listed_but_not_actionable(monkeypatch):
    monkeypatch.setattr(research.data_mod, "fetch", lambda *a, **k: _frame())
    cfg = research.ResearchConfig(
        symbols=["TEST"],
        strategies=["trend"],
        paths=50,
        horizon=10,
        block_size=1,
        min_pass=0.0,
        max_breach=1.0,
        min_trades=10_000,
        near_miss_slack=10_000,
        min_oos_pass=0.0,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["proposals"] == []
    assert report["near_misses"]
    assert all(p["enabled"] is False for p in report["near_misses"])
    assert all(p["status"] == "watchlist_few_trades" for p in report["near_misses"])
    md = research.render_markdown(report)
    assert "Casi propuestas" in md
    assert "no se proponen" in md


def test_render_markdown_handles_no_results():
    report = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "rules": "FTMO",
        "config": {
            "symbols": ["SPY"],
            "strategies": ["trend"],
            "start": "2019-01-01",
            "end": "2024-01-01",
            "paths": 10,
            "horizon": 5,
            "block_size": 1,
            "min_trades": 1,
            "min_pass": 0.5,
            "min_oos_pass": 0.25,
            "max_breach": 0.1,
            "holdout_fraction": 0.3,
            "exposures": [1.0],
        },
        "results": [],
        "proposals": [],
        "errors": [],
        "candidates": 0,
    }
    md = research.render_markdown(report)
    assert "Ningún candidato" in md
