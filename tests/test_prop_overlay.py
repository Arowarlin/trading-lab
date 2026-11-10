from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.prop.overlay import apply_overlay


def series(values: list[float], index: pd.DatetimeIndex | None = None) -> pd.Series:
    idx = (
        index
        if index is not None
        else pd.date_range("2025-01-01", periods=len(values), freq="D", tz="UTC")
    )
    return pd.Series(values, index=idx)


def test_sin_drawdown_no_cambia_nada():
    returns = series([0.001] * 100)
    result = apply_overlay(returns)
    assert result.size_factor.eq(1.0).all()
    assert np.allclose(result.returns.to_numpy(), returns.to_numpy())
    assert result.max_drawdown_pct == pytest.approx(0.0)
    assert result.total_return > 0


def test_zona_caution_reduce_el_siguiente_retorno():
    values = [0.001] * 20 + [-0.065] + [0.01] * 5
    returns = series(values)
    result = apply_overlay(returns, max_daily_loss_pct=0.10)
    assert result.size_factor.iloc[20] == 1.0
    assert result.size_factor.iloc[21] == pytest.approx(0.75)
    assert result.returns.iloc[21] == pytest.approx(0.01 * 0.75)


def test_breaker_corta_el_resto_del_dia_y_se_rearma():
    index = pd.DatetimeIndex(
        [
            "2026-11-10 09:00",
            "2026-11-10 10:00",
            "2026-11-10 11:00",
            "2026-11-11 09:00",
        ],
        tz="UTC",
    )
    returns = series([-0.05, 0.01, 0.01, 0.01], index)
    result = apply_overlay(
        returns, max_drawdown_pct=0.09, max_daily_loss_pct=0.045
    )
    assert result.size_factor.tolist() == [1.0, 0.0, 0.0, 1.0]
    assert result.breaker_days == 1
    assert result.returns.iloc[1] == pytest.approx(0.0)
    assert result.returns.iloc[2] == pytest.approx(0.0)
    assert result.returns.iloc[3] == pytest.approx(0.01)


def test_breach_deja_factor_cero():
    returns = series([0.001] * 10 + [-0.10] + [0.01] * 3)
    result = apply_overlay(returns, max_daily_loss_pct=0.20)
    assert result.size_factor.iloc[11] == 0.0
    assert result.size_factor.iloc[12] == 0.0
    assert result.max_drawdown_pct <= -0.09


def test_serie_vacia_falla():
    with pytest.raises(ValueError):
        apply_overlay(pd.Series(dtype=float))
