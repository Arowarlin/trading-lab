from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from tradinglab import costs


def _latest(tmp_path: Path) -> Path:
    report = tmp_path / "research"
    report.mkdir()
    (report / "latest.json").write_text(
        json.dumps(
            {
                "config": {"start": "2025-01-01", "end": "2025-12-31"},
                "results": [
                    {
                        "symbol": "SPY",
                        "strategy": "trend",
                        "params": {"fast": 50, "slow": 200},
                        "exposure": 0.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return report


def test_run_costs_source_broker_sin_datos_marca(monkeypatch, tmp_path):
    report = _latest(tmp_path)
    idx = pd.bdate_range("2025-01-01", periods=40)
    base = pd.Series(np.full(40, 0.005), index=idx)
    df = pd.DataFrame({"close": np.linspace(100, 140, 40)}, index=idx)

    monkeypatch.setattr(costs.data_mod, "fetch", lambda *a, **k: df)
    monkeypatch.setattr(
        costs,
        "STRATEGIES",
        {"trend": lambda df, **p: SimpleNamespace(target=pd.Series(1.0, index=df.index))},
    )

    def fake_backtest(df, target, *, commission_bps, slippage_bps, **kwargs):
        drag = (commission_bps + slippage_bps) / 10_000
        returns = base - drag
        return SimpleNamespace(
            returns=returns,
            equity=(1 + returns).cumprod() * 100_000,
            metrics={"num_trades": 12},
            trades=pd.DataFrame(),
            exposure=1.0,
        )

    monkeypatch.setattr(costs, "run_backtest", fake_backtest)
    payload = costs.run_costs(
        report,
        cache_dir=tmp_path,
        top=1,
        source="broker",
        db_path=tmp_path / "lab.db",
        ticks_dir=tmp_path / "ticks",
    )
    row = payload["results"][0]
    assert row["spread_source"] == "sin datos"
    assert row["fragile"] is None
    assert "sin datos" in costs.render_markdown(payload)


def test_run_costs_escenarios_y_fragilidad(monkeypatch, tmp_path):
    report = _latest(tmp_path)
    idx = pd.bdate_range("2025-01-01", periods=40)
    base = pd.Series(np.full(40, 0.005), index=idx)
    df = pd.DataFrame({"close": np.linspace(100, 140, 40)}, index=idx)

    monkeypatch.setattr(costs.data_mod, "fetch", lambda *a, **k: df)
    monkeypatch.setattr(costs, "STRATEGIES", {"trend": lambda df, **p: SimpleNamespace(target=pd.Series(1.0, index=df.index))})

    def fake_backtest(df, target, *, commission_bps, slippage_bps, **kwargs):
        drag = (commission_bps + slippage_bps) / 10_000
        returns = base - drag
        return SimpleNamespace(
            returns=returns,
            equity=(1 + returns).cumprod() * 100_000,
            metrics={"num_trades": 12},
            trades=pd.DataFrame(),
            exposure=1.0,
        )

    monkeypatch.setattr(costs, "run_backtest", fake_backtest)
    payload = costs.run_costs(report, cache_dir=tmp_path, top=1)
    row = payload["results"][0]
    assert set(row["scenarios"]) == {"zero", "base", "double", "stress"}
    assert row["scenarios"]["stress"]["total_return"] < row["scenarios"]["base"]["total_return"]
    assert row["cost_drag"] > 0
    assert row["fragile"] is False
    md = costs.render_markdown(payload)
    assert "Sensibilidad a costes" in md
    files = costs.write(payload, report)
    assert Path(files["json"]).exists()
