from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.portfolio import (
    render_simulation_markdown,
    select_portfolio,
    simulate,
    write_simulation,
)


def _report(tmp_path: Path) -> Path:
    report = tmp_path / "research"
    artifacts = report / "artifacts"
    artifacts.mkdir(parents=True)
    rows = []
    for i in range(3):
        rng = np.random.default_rng(10 + i)
        returns = rng.normal(0.0005 + i * 0.0001, 0.006, 80)
        equity = 100_000 * np.cumprod(1 + returns)
        name = f"a{i}.parquet"
        pd.DataFrame(
            {"equity": equity, "buy_hold": 100_000 * np.cumprod(1 + rng.normal(0.0003, 0.004, 80))},
            index=pd.bdate_range("2025-01-01", periods=80),
        ).to_parquet(artifacts / name)
        rows.append(
            {
                "symbol": ["SPY", "QQQ", "GLD"][i],
                "strategy": "trend",
                "params": {"fast": 50 + i},
                "exposure": 0.5,
                "num_trades": 20 + i,
                "score": 1.0 - i * 0.1,
                "artifact": f"artifacts/{name}",
            }
        )
    (report / "latest.json").write_text(json.dumps({"results": rows}), encoding="utf-8")
    (report / "horizons.json").write_text(
        json.dumps(
            {
                "correlations": {
                    "labels": ["#1 SPY trend x0.5", "#2 QQQ trend x0.5", "#3 GLD trend x0.5"],
                    "matrix": [[1.0, 0.91, 0.1], [0.91, 1.0, 0.2], [0.1, 0.2, 1.0]],
                }
            }
        ),
        encoding="utf-8",
    )
    return report


def test_select_portfolio_respeta_max_por_cluster(tmp_path):
    report = _report(tmp_path)
    selection = select_portfolio(report, top=3, max_per_cluster=1)
    assert len(selection["selected"]) == 2  # SPY del clúster + GLD
    assert {item["result"]["symbol"] for item in selection["selected"]} == {"SPY", "GLD"}


def test_simulate_cartera(tmp_path):
    report = _report(tmp_path)
    payload = simulate(report, top=3, paths=20)
    assert len(payload["members"]) == 3  # máx. 2 del clúster + GLD
    assert payload["portfolio"]["days"] > 0
    assert len(payload["monte_carlo"]) == 6
    assert payload["single_best"] is not None
    md = render_simulation_markdown(payload)
    assert "Cartera simulada" in md
    assert "Monte Carlo" in md
    files = write_simulation(payload, report)
    assert Path(files["json"]).exists()
    assert Path(files["md"]).exists()
