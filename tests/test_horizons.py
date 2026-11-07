from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab import horizons
from tradinglab.horizons import matrix, render_markdown, required_22d


def _report(tmp_path: Path, *, missing: bool = False) -> Path:
    report_dir = tmp_path / "research"
    artifacts = report_dir / "artifacts"
    artifacts.mkdir(parents=True)
    rng = np.random.default_rng(3)
    results = []
    for i in range(2):
        returns = rng.normal(0.0008 + i * 0.0002, 0.005, 60)
        equity = 100_000 * np.cumprod(1 + returns)
        name = f"a{i}.parquet"
        pd.DataFrame(
            {"equity": equity, "buy_hold": 100_000 * np.cumprod(1 + rng.normal(0.0003, 0.004, 60))},
            index=pd.bdate_range("2025-01-01", periods=60),
        ).to_parquet(artifacts / name)
        results.append(
            {
                "id": f"bot-{i}",
                "symbol": "QQQ",
                "strategy": "trend",
                "params": {"fast": 50, "slow": 200},
                "num_trades": 25,
                "score": 1.0 - i * 0.1,
                "artifact": f"artifacts/{name}" if not missing else f"artifacts/missing{i}.parquet",
            }
        )
    (report_dir / "latest.json").write_text(
        json.dumps({"results": results}), encoding="utf-8"
    )
    return report_dir


def test_matrix_genera_tabla_por_firmas(tmp_path):
    report_dir = _report(tmp_path)
    payload = matrix(
        report_dir,
        top=2,
        paths=40,
        horizons=(22,),
        exposures=(0.5, 1.0),
        include_required=False,
    )
    assert payload["top"] == 2
    assert len(payload["firms"]) == 2
    assert {firm["id"] for firm in payload["firms"]} == {"ftmo", "topstep"}
    assert "Topstep" in payload["firms"][1]["name"]
    variant = payload["firms"][0]["variants"][0]
    cell = variant["exposures"]["0.5"]["22"]
    assert cell["status"] == "ok"
    assert 0.0 <= cell["pass_rate"] <= 1.0
    assert 0.0 <= cell["breach_rate"] <= 1.0
    md = render_markdown(payload)
    assert "FTMO 100k 2-step" in md
    assert "Topstep 50K" in md
    assert "22d pasa / revienta" in md
    assert "sin datos" not in md


def test_matrix_marca_sin_datos(tmp_path):
    report_dir = _report(tmp_path, missing=True)
    payload = matrix(
        report_dir,
        top=2,
        paths=20,
        horizons=(22,),
        exposures=(1.0,),
        include_required=False,
    )
    cell = payload["firms"][0]["variants"][0]["exposures"]["1"]["22"]
    assert cell["status"] == "sin datos"
    md = render_markdown(payload)
    assert "sin datos" in md


def test_required_22d_estructura(monkeypatch, tmp_path):
    def fake_mc(rules, returns, **kwargs):
        return {
            "pass_rate": 0.60,
            "breach_rate": 0.10,
            "timeout_rate": 0.30,
            "median_days_to_pass": 18.0,
            "median_max_drawdown": -0.04,
            "mean_daily_return": 0.001,
            "daily_volatility": 0.005,
        }

    monkeypatch.setattr(horizons, "monte_carlo", fake_mc)
    payload = required_22d(tmp_path)
    assert payload["horizon"] == 22
    assert payload["min_pass_rate"] == 0.50
    assert payload["max_breach_rate"] == 0.15
    assert len(payload["firms"]) == 2
    for firm in payload["firms"]:
        assert firm["rows"]
        assert firm["rows"][0]["daily_return"] == 0.001
        assert firm["rows"][0]["pass_rate"] == 0.60
