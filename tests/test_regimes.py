from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.regimes import (
    bot_performance_by_regime,
    classify,
    metrics,
    report,
    selector_proposal,
    selector_proposals,
)


def _frame(kind: str = "up", rows: int = 420) -> pd.DataFrame:
    x = np.arange(rows, dtype=float)
    if kind == "up":
        close = 100.0 + 0.20 * x + 2.0 * np.sin(x / 20.0)
    elif kind == "down":
        close = 200.0 - 0.20 * x + 2.0 * np.sin(x / 20.0)
    else:
        close = np.full(rows, 100.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=pd.bdate_range("2019-01-01", periods=rows),
    )


def test_clasificador_causal_no_cambia_con_futuro() -> None:
    frame = _frame("up")
    full = classify(frame)
    for cut in (250, 300, 360):
        truncated = classify(frame.iloc[:cut])
        pd.testing.assert_series_equal(
            full["label"].iloc[:cut],
            truncated["label"],
            check_names=False,
            check_freq=False,
        )
        pd.testing.assert_series_equal(
            full["vol_state"].iloc[:cut],
            truncated["vol_state"],
            check_names=False,
            check_freq=False,
        )
        pd.testing.assert_series_equal(
            full["vol"].iloc[:cut],
            truncated["vol"],
            check_names=False,
            check_freq=False,
            atol=1e-12,
        )


def test_etiquetas_basicas() -> None:
    up = classify(_frame("up"))
    assert up["label"].iloc[-1] == "trend_up"
    down = classify(_frame("down"))
    assert down["label"].iloc[-1] == "trend_down"
    flat = classify(_frame("flat"))
    assert flat["label"].iloc[-1] == "range"
    assert flat["vol_state"].iloc[-1] == "low"


def test_reporte_y_metricas() -> None:
    frame = _frame("up")
    payload = report("TEST", frame, source="cache.parquet")
    assert payload["status"] == "ok"
    assert payload["current"]["label"] == "trend_up"
    assert payload["current"]["vol_state"] in {"low", "high"}
    assert payload["metrics"]["stability_pct"] is not None
    assert payload["metrics"]["changes"] >= 0
    assert "mean_days" in payload["metrics"]["detection_delay"]
    assert payload["metrics"]["regime_stats"]
    assert all(row["status"] == "proposed" for row in payload["selector"])
    assert all(row["enabled"] is False for row in payload["selector"])
    assert payload["proposed_selector"]["applied"] is False


def test_selector_propuesto_no_aplica() -> None:
    assert selector_proposal("trend_up", "low")["bot"] == "trend-spy"
    assert selector_proposal("range", "low")["bot"] == "meanrev-large"
    assert selector_proposal("trend_down", "high")["bot"] == "flat"
    proposals = selector_proposals()
    assert len(proposals) == 6
    assert all(item["status"] == "proposed" and item["enabled"] is False for item in proposals)


def test_rendimiento_por_regimen_suma_dias() -> None:
    frame = _frame("up")
    labels = classify(frame)["label"]
    returns = frame["close"].pct_change().fillna(0.0)
    rows = bot_performance_by_regime(returns, labels)
    known = [row for row in rows if row["regime"] != "unknown"]
    assert sum(row["n"] for row in known) == int((labels != "unknown").sum())
    for row in rows:
        if row["n"]:
            assert "total_return" in row
            assert "sharpe" in row
            assert "max_drawdown" in row


def test_metrics_directo() -> None:
    frame = _frame("up")
    labels = classify(frame)["label"]
    returns = frame["close"].pct_change().fillna(0.0)
    result = metrics(labels, returns)
    assert result["n_observations"] > 0
    assert result["stability_pct"] is not None
    assert result["avg_duration_days"] is not None
