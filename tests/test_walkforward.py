from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.walkforward import (
    regime_gate,
    regime_report,
    walk_forward,
)


def _noise(t=1400, n=8, seed=1):
    return np.random.default_rng(seed).normal(0, 0.01, size=(t, n))


def test_walk_forward_edge_passes():
    r = _noise(n=6, seed=2)
    r[:, 2] += 0.0015  # edge persistente (~Sharpe 2,4)
    result = walk_forward(r, train_len=504, test_len=126)
    assert result.verdict() == "ok"
    assert result.stitched_sharpe > 0.5
    assert result.frac_positive >= 0.5
    assert result.median_rank_pct >= 0.5
    assert result.stability >= 0.3


def test_walk_forward_noise_does_not_pass():
    # Muchas variantes sin edge: la seleccionada cambia de fold a fold.
    result = walk_forward(_noise(n=16, seed=3), train_len=504, test_len=126)
    assert result.verdict() == "fallido"


def test_walk_forward_insufficient_folds_returns_fallido():
    result = walk_forward(_noise(t=700), train_len=504, test_len=126)
    assert result.n_folds < 3
    assert result.verdict() == "fallido"


def test_walk_forward_fields_and_folds():
    r = _noise(t=1400, n=4)
    result = walk_forward(r, train_len=504, test_len=126)
    assert result.n_variants == 4
    assert result.n_folds == (1400 - 504) // 126
    assert result.train_len == 504 and result.test_len == 126
    assert len(result.fold_details) == result.n_folds
    assert len(result.oos_returns) == result.n_folds * 126
    payload = result.to_dict()
    assert set(payload) == {
        "stitched_sharpe",
        "frac_positive",
        "efficiency",
        "median_rank_pct",
        "stability",
        "n_folds",
        "n_variants",
        "train_len",
        "test_len",
    }


def test_walk_forward_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="2-D"):
        walk_forward(np.zeros(100))
    bad = _noise(t=700)
    bad[3, 3] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        walk_forward(bad, train_len=504, test_len=126)
    with pytest.raises(ValueError, match="insuficiente"):
        walk_forward(_noise(t=500), train_len=504, test_len=126)
    with pytest.raises(ValueError):
        walk_forward(_noise(t=700), train_len=1, test_len=126)


def test_walk_forward_zero_variance_is_weak():
    r = np.zeros((1400, 3))
    result = walk_forward(r, train_len=504, test_len=126)
    assert result.stitched_sharpe == 0.0
    assert result.verdict() == "fallido"


def _years_series():
    idx = pd.date_range("2017-01-01", "2023-12-31", freq="B")
    values = np.where(np.arange(len(idx)) % 2 == 0, 0.002, -0.001)
    return pd.Series(values, index=idx)


def test_regime_report_computes_each_year():
    report = regime_report(_years_series())
    assert report.missing == []
    assert set(report.years) == {2018, 2020, 2022}
    for stats in report.years.values():
        assert stats["n"] > 20
        assert stats["total_return"] > 0
        assert stats["sharpe"] > 0
    payload = report.to_dict()
    assert "2018" in payload["years"]
    assert payload["missing"] == []


def test_regime_gate_passes_positive_regimes():
    gate = regime_gate(regime_report(_years_series()))
    assert gate.passed is True
    assert gate.reasons == []
    assert gate.to_dict()["passed"] is True


def test_regime_gate_blocks_missing_regime():
    idx = pd.date_range("2017-01-01", "2023-12-31", freq="B")
    values = np.where(np.arange(len(idx)) % 2 == 0, 0.002, -0.001)
    series = pd.Series(values, index=idx)
    series = series[series.index.year != 2020]
    gate = regime_gate(regime_report(series))
    assert gate.passed is False
    assert 2020 in gate.missing
    assert any("sin datos" in reason for reason in gate.reasons)


def test_regime_gate_blocks_losing_regime():
    series = _years_series()
    series.loc[series.index.year == 2022] = -0.002
    gate = regime_gate(regime_report(series))
    assert gate.passed is False
    assert any("2022" in reason for reason in gate.reasons)


def test_regime_report_requires_datetime_index():
    report = regime_report(pd.Series([0.01, -0.01, 0.02]))
    assert report.missing == [2018, 2020, 2022]
    assert regime_gate(report).passed is False


def test_walk_forward_single_variant_is_stable():
    r = _noise(t=1400, n=1, seed=4)
    result = walk_forward(r, train_len=504, test_len=126)
    assert result.stability == 1.0
    assert result.median_rank_pct == 1.0
