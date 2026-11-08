from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab import quantstats_report as qr


def test_write_reports_sin_propuestas(tmp_path: Path) -> None:
    result = qr.write_reports({"proposals": []}, tmp_path, tmp_path)
    assert result["status"] == "Sin datos"


def test_write_reports_genera_html(tmp_path: Path, monkeypatch) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    index = pd.bdate_range("2020-01-01", periods=120)
    pd.DataFrame(
        {"close": 100.0 + np.arange(len(index)) * 0.1},
        index=index,
    ).to_parquet(cache / "SPY__2020-01-01__2021-01-01.parquet")

    research = tmp_path / "research"
    artifacts = research / "artifacts"
    artifacts.mkdir(parents=True)
    equity = pd.Series(
        100.0 + np.arange(len(index)) * 0.2,
        index=index,
    )
    pd.DataFrame({"equity": equity, "buy_hold": equity}).to_parquet(
        artifacts / "prop.parquet"
    )
    report = {
        "proposals": [
            {
                "id": "prop-1",
                "symbol": "SPY",
                "strategy": "trend",
                "params": {"fast": 20},
                "artifact": "artifacts/prop.parquet",
            }
        ]
    }

    def fake_html(returns, benchmark, output, title):
        Path(output).write_text("<html>ok</html>", encoding="utf-8")

    monkeypatch.setattr(qr.qs.reports, "html", fake_html)
    result = qr.write_reports(report, research, cache)
    assert result["status"] == "ok"
    relative = report["proposals"][0]["quantstats_html"]
    assert relative.startswith("quantstats/")
    assert (research / relative).exists()
    assert result["reports"][0]["benchmark"] == "SPY"
