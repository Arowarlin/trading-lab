from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import tradinglab.research as research
from tradinglab.prop.rules import ftmo


def test_deflated_sharpe_penaliza_mas_variantes():
    from tradinglab.research import deflated_sharpe

    bajo = deflated_sharpe(1.0, 1000, 0.0, 3.0, 0.5, 10)
    alto = deflated_sharpe(1.0, 1000, 0.0, 3.0, 0.5, 300)
    assert bajo is not None and alto is not None
    assert bajo > alto
    assert 0.0 <= alto <= 1.0


def test_walk_forward_y_regimenes():
    from tradinglab.research import _block_metrics, _year_returns

    idx = pd.date_range("2020-01-01", periods=40, freq="B")
    returns = pd.Series([0.01, -0.005] * 20, index=idx)
    blocks = _block_metrics(returns, 4)
    assert len(blocks) == 4
    assert all("return" in b and "sharpe" in b for b in blocks)

    years = _year_returns(returns)
    assert "2020" in years
    assert years["2020"] > -1.0


def test_pbo_cscv_detecta_consistencia():
    from tradinglab.validation import cscv_pbo

    rng = np.random.default_rng(11)
    returns = rng.normal(0, 0.01, size=(1600, 6))
    returns[:, 2] += 0.001  # edge persistente
    result = cscv_pbo(returns, n_slices=16, max_combinations=1_000, seed=0)
    assert 0.0 <= result.pbo <= 1.0
    assert result.n_variants == 6
    assert result.verdict() == "ok"


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
        pbo_max_combinations=500,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["candidates"] == 4  # fast × slow
    assert len(report["results"]) == 4
    assert report["results"][0]["score"] >= report["results"][1]["score"]
    assert all("family_median_pass" in r for r in report["results"])
    assert report["pbo"] is not None
    assert report["pbo"]["n_slices"] == cfg.pbo_slices
    assert report["pbo"]["n_variants"] == 4
    assert report["pbo"]["verdict"] in {"ok", "sobreajustado"}
    assert report["pbo_by_symbol"]["TEST"]["n_slices"] == cfg.pbo_slices
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
        pbo_max_combinations=500,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert any(e["symbol"] == "BAD" for e in report["errors"])
    assert report["candidates"] == 4


def test_pbo_alto_bloquea_propuestas(monkeypatch):
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
        min_dsr=0.0,
        min_wf_positive=0,
        max_pbo=0.0,
        pbo_max_combinations=500,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["pbo"]["pbo"] > 0.0
    assert report["pbo_ok"] is False
    assert report["proposals"] == []
    md = research.render_markdown(report)
    assert "## Sobreajuste (CSCV)" in md
    assert "sobreajustado" in md


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
        min_dsr=0.0,
        min_wf_positive=0,
        max_pbo=1.0,
        pbo_max_combinations=500,
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
        min_dsr=0.0,
        min_wf_positive=0,
        max_pbo=1.0,
        pbo_max_combinations=500,
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
    assert "PBO (CSCV): no disponible" in md
