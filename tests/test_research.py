from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import tradinglab.research as research
from tradinglab.backtest import BacktestResult
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


def test_pbo_payload_cuenta_variantes_planas():
    idx = pd.bdate_range("2020-01-01", periods=1600)
    rng = np.random.default_rng(21)
    series = {
        "flat": pd.Series(0.0, index=idx),
        "noise": pd.Series(rng.normal(0, 0.01, len(idx)), index=idx),
        "edge": pd.Series(rng.normal(0.0015, 0.01, len(idx)), index=idx),
    }
    cfg = research.ResearchConfig(pbo_max_combinations=300)
    payload = research._pbo_payload(series, cfg, scope="test")
    assert payload is not None
    assert payload["flat_variants"] == 1
    assert payload["n_variants_nonflat"] == 2
    assert payload["pbo_excluding_flat"] is not None
    assert 0.0 <= payload["pbo_excluding_flat"] <= 1.0


def test_regimenes_incluyen_drawdown_buy_hold():
    payload = {"years": {"2018": {"max_drawdown": -0.10}}}
    enriched = research._with_benchmark_regimes(
        payload,
        {"2018": {"max_drawdown": -0.20, "total_return": 0.05}},
    )
    assert enriched["years"]["2018"]["buy_hold_max_drawdown"] == pytest.approx(-0.20)
    assert enriched["years"]["2018"]["buy_hold_total_return"] == pytest.approx(0.05)


def test_dsr_n_trials_crece_con_activos(monkeypatch):
    _fake_research_world(monkeypatch, with_edge=True)
    base = dict(
        strategies=["trend"],
        paths=5,
        horizon=10,
        block_size=1,
        pbo_max_combinations=200,
        exposures=[1.0],
    )
    one = research.run_research(
        research.ResearchConfig(symbols=["A"], **base), ftmo(100_000), cache_dir="unused"
    )
    two = research.run_research(
        research.ResearchConfig(symbols=["A", "B"], **base), ftmo(100_000), cache_dir="unused"
    )
    assert one["dsr_n_trials"] == len(one["results"]) == 4
    assert two["dsr_n_trials"] == len(two["results"]) == 8
    assert two["dsr_n_trials"] == 2 * one["dsr_n_trials"]


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


def _fake_research_world(monkeypatch, *, with_edge: bool) -> dict:
    """Datos sintéticos controlados para probar los tres controles nuevos.

    Usa un backtest falso: una variante recibe un edge persistente y las demás
    ruido con 2022 negativo. Así el test no depende de que una estrategia real
    encuentre una tendencia en datos aleatorios.
    """
    idx = pd.bdate_range("2017-01-01", "2024-12-31")
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0001, 0.006, len(idx))
    noise[idx.year == 2022] -= 0.002
    edge = rng.normal(0.0006, 0.004, len(idx)) + 0.0004
    edge_params = {"fast": 20, "slow": 100, "regime": 200}

    def fake_strategy(df, **params):
        target = pd.Series(0.0, index=df.index)
        target.attrs["variant"] = json.dumps(params, sort_keys=True)
        return SimpleNamespace(target=target)

    def fake_backtest(df, target, **kwargs):
        params = json.loads(target.attrs.get("variant") or "{}")
        is_edge = with_edge and params == edge_params
        returns = pd.Series(edge if is_edge else noise, index=idx)
        equity = 100_000.0 * (1.0 + returns).cumprod()
        std = float(returns.std(ddof=1))
        metrics = {
            "sharpe": float(returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0,
            "cagr": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
            "max_drawdown": float((equity / equity.cummax() - 1.0).min()),
            "num_trades": 30,
            "win_rate": 0.55,
            "exposure": 1.0,
        }
        return BacktestResult(
            equity=equity,
            returns=returns,
            trades=pd.DataFrame(),
            metrics=metrics,
            exposure=1.0,
        )

    def fake_mc(rules, returns, **kwargs):
        return {
            "pass_rate": 0.75,
            "breach_rate": 0.03,
            "pass_ci95": [0.65, 0.85],
            "timeout_rate": 0.0,
            "median_days_to_pass": 20.0,
        }

    monkeypatch.setattr(research.data_mod, "fetch", lambda *a, **k: _frame(n=400))
    monkeypatch.setitem(research.STRATEGIES, "trend", fake_strategy)
    monkeypatch.setattr(research, "run_backtest", fake_backtest)
    monkeypatch.setattr(research, "monte_carlo", fake_mc)
    return edge_params


def test_run_research_noise_has_no_proposals(monkeypatch):
    _fake_research_world(monkeypatch, with_edge=False)
    cfg = research.ResearchConfig(
        symbols=["TEST"],
        strategies=["trend"],
        paths=10,
        horizon=20,
        block_size=1,
        min_pass=0.5,
        max_breach=0.1,
        min_trades=20,
        pbo_max_combinations=1_000,
        wf_train_len=504,
        wf_test_len=126,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["candidates"] == 4
    assert report["proposals"] == []
    assert report["pbo"] is not None
    assert all(not (r.get("regime_gate") or {}).get("passed") for r in report["results"])


def test_run_research_edge_passes_pbo_walkforward_and_regime(monkeypatch):
    edge_params = _fake_research_world(monkeypatch, with_edge=True)
    cfg = research.ResearchConfig(
        symbols=["TEST"],
        strategies=["trend"],
        paths=10,
        horizon=20,
        block_size=1,
        min_pass=0.5,
        max_breach=0.1,
        min_trades=20,
        pbo_max_combinations=1_000,
        wf_train_len=504,
        wf_test_len=126,
        exposures=[1.0],
    )
    report = research.run_research(cfg, ftmo(100_000), cache_dir="unused")

    assert report["pbo"] is not None and report["pbo"]["pbo"] <= 0.30
    assert report["walk_forward"] is not None
    assert report["walk_forward"]["verdict"] == "ok"
    assert report["dsr_n_trials"] == len(report["results"])
    assert len(report["proposals"]) == 1
    proposal = report["proposals"][0]
    assert proposal["params"] == edge_params
    assert proposal["regime_gate"]["passed"] is True
    assert proposal["enabled"] is False
    assert proposal["validation_failures"] == []
    assert proposal["dsr_n_trials"] == report["dsr_n_trials"]


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
    assert report["walk_forward"] is None  # 400 filas < 504+126
    assert all("regime_gate" in r for r in report["results"])
    assert all("regime_report" in r for r in report["results"])
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
    assert "pbo" in proposals and "walk_forward" in proposals
    md = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "Ranking" in md
    assert "## Propuestas" in md
    assert "PBO (CSCV)" in md
    assert "Drawdown por régimen" in md
    assert "DSR: n_trials" in md


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
    assert all(
        p["status"] in {"watchlist_few_trades", "watchlist_validation"}
        for p in report["near_misses"]
    )
    assert any(p.get("note") for p in report["near_misses"])
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
    assert "Walk-forward global: no disponible" in md
