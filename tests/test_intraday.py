from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.intraday import (
    asian_range_reversal,
    backtest_intraday,
    break_even_cost_bps,
    cache_metadata,
    load_bars,
    opening_range_breakout,
    render_markdown,
    run_intraday,
    save_bars,
    trend_pullback,
)
from tradinglab.intraday_costs import asset_costs


def _bars(days: int = 60, spread: bool = True) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=days * 96, freq="15min", tz="UTC")
    rng = np.random.default_rng(5)
    drift = np.sin(np.arange(len(idx)) / 120.0) * 0.0004
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0008, len(idx)) + drift))
    frame = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.0001, len(idx))),
            "high": close * 1.0004,
            "low": close * 0.9996,
            "close": close,
            "volume": 1000.0,
        },
        index=idx,
    )
    if spread:
        frame["spread"] = 10.0
    return frame


def test_cache_roundtrip(tmp_path):
    df = _bars(days=3)
    path = save_bars(df, tmp_path, "EURUSD", "M15")
    assert path.exists()
    loaded = load_bars(tmp_path, "EURUSD", "M15")
    assert len(loaded) == len(df)
    meta = cache_metadata(loaded, "M15")
    assert meta["rows"] == len(df)
    assert meta["years"] > 0


def test_backtest_intraday_costes_y_spread():
    df = _bars()
    target = opening_range_breakout(df).target
    result = backtest_intraday(df, target, timeframe="M15")
    assert result["metrics"]["bars"] == len(df)
    assert result["metrics"]["num_trades"] >= 0
    assert "returns" in result and "equity" in result
    assert result["spread_reliable"] is True
    no_spread = df.drop(columns=["spread"])
    assert backtest_intraday(no_spread, target, timeframe="M15")["spread_reliable"] is False


def test_backtest_zero_costs_es_diagnostico():
    df = _bars()
    target = opening_range_breakout(df).target
    normal = backtest_intraday(df, target, timeframe="M15")
    zero = backtest_intraday(
        df,
        target,
        timeframe="M15",
        commission_bps=0.0,
        slippage_bps=0.0,
        spread_override_bps=0.0,
    )
    assert zero["spread_reliable"] is True
    assert zero["spread_bps_median"] == 0.0
    assert zero["spread_observed_bps_median"] > 0
    assert zero["metrics"]["sharpe"] >= normal["metrics"]["sharpe"]


def test_run_intraday_marca_costes_cero():
    df = _bars(days=30)
    report = run_intraday(
        df,
        paths=10,
        commission_bps=0.0,
        slippage_bps=0.0,
        slippage_optimistic_bps=0.0,
        spread_override_bps=0.0,
    )
    assert report["costs"]["diagnostic_zero_costs"] is True
    assert "Diagnóstico zero-cost" in render_markdown(report)


def test_costes_eurusd_oficiales():
    cost = asset_costs("EURUSD")
    assert cost.verified is True
    assert cost.commission_per_lot_usd == pytest.approx(2.50)
    assert cost.commission_side == "per_side"
    assert "2025-09-25" in (cost.source_date or "")
    bps = cost.commission_bps(pd.Series([1.10]))
    assert float(bps.iloc[0]) == pytest.approx(2.50 / 110_000 * 10_000, rel=1e-6)


def test_simbolo_sin_comision_verificada_no_inventa():
    cost = asset_costs("XAUUSD")
    assert cost.verified is False
    with pytest.raises(RuntimeError, match="sin verificar"):
        run_intraday(_bars(days=3), symbol="XAUUSD", paths=5)


def test_break_even_cost_bps_sintetico():
    gross = pd.Series([0.002 if index % 2 == 0 else 0.001 for index in range(200)])
    turnover = pd.Series(1.0, index=gross.index)
    # media 0.0015 => 15 bps de coste uniforme llevan el Sharpe a 0
    assert break_even_cost_bps(gross, turnover, "M15") == pytest.approx(15.0, abs=0.1)


def test_curva_de_costes_y_modelo():
    df = _bars(days=30)
    report = run_intraday(df, paths=10)
    model = report["cost_model"]
    assert model["commission"]["verified"] is True
    assert model["commission"]["source_date"] == "2025-09-25"
    assert model["slippage"]["optimistic_bps"] == pytest.approx(0.5)
    assert model["slippage"]["conservative_bps"] == pytest.approx(2.0)
    row = report["outcomes"][0]
    assert set(row["cost_curve_bps"]) == {"0.0", "0.5", "1.0", "2.0", "3.0"}
    assert row["calibrated_cost_bps"] > 0
    assert "Coste de equilibrio" in render_markdown(report)


def test_tres_estrategias_generan_targets():
    df = _bars()
    for fn in (opening_range_breakout, trend_pullback, asian_range_reversal):
        result = fn(df)
        assert len(result.target) == len(df)
        assert result.target.abs().max() <= 1.0


def test_run_intraday_controles_y_tabla():
    df = _bars(days=90)
    report = run_intraday(df, paths=20)
    assert report["n_trials"] > 0
    assert report["pbo"] is not None
    assert report["walk_forward"] is not None
    assert "outcomes" in report and "monte_carlo" in report
    assert report["passed"] == 0  # sin regímenes históricos 2018/2020/2022
    md = render_markdown(report)
    assert "Investigación intradía" in md
    assert "Monte Carlo" in md
