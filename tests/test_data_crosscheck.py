from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tradinglab.data.crosscheck import compare_frames, latest_correlation


def _mt5() -> pd.DataFrame:
    index = pd.date_range("2026-11-01", periods=30, freq="h", tz="UTC")
    close = pd.Series(
        [100 + i * 0.1 for i in range(30)], index=index, dtype=float
    )
    return pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2, "close": close},
        index=index,
    )


def _ticks() -> pd.DataFrame:
    frame = _mt5()
    rows = []
    for stamp, row in frame.iterrows():
        mid = float(row["close"])
        if stamp == frame.index[20]:
            mid = float(frame["close"].iloc[19])  # divergencia conocida
        rows.append({"ts": stamp, "bid": mid - 0.01, "ask": mid + 0.01})
    return pd.DataFrame(rows)


def test_crosscheck_divergencia_conocida():
    result = compare_frames(_mt5(), _ticks(), threshold=2.0)
    assert result["status"] == "ok"
    assert result["n_hours"] >= 20
    assert result["n_divergences"] >= 1
    assert any("2026-11-01 20" in row["ts"] for row in result["divergences"])


def test_latest_correlation_lee_informe(tmp_path: Path):
    target = tmp_path / "XAUUSD.json"
    target.write_text(json.dumps({"corr_1h": 0.94}), encoding="utf-8")
    assert latest_correlation("XAUUSD", out_dir=tmp_path) == 0.94
    assert latest_correlation("EURUSD", out_dir=tmp_path) is None

def test_datacheck_avisa_si_correlacion_baja(monkeypatch):
    import tradinglab.data.crosscheck as crosscheck
    from tradinglab.datacheck import check_frame

    index = pd.date_range("2025-01-01", periods=300, freq="D", tz="UTC")
    close = pd.Series([100 + i * 0.1 for i in range(300)], index=index)
    frame = pd.DataFrame(
        {"open": close, "high": close + 0.2, "low": close - 0.2,
         "close": close, "volume": 1000},
        index=index,
    )
    monkeypatch.setattr(
        crosscheck, "latest_correlation", lambda symbol: 0.90
    )
    result = check_frame(frame, "XAUUSD", timeframe="1d")
    assert result["checks"]["crosscheck"]["status"] == "warn"
