# Tests básicos del motor

import numpy as np
import pandas as pd
import pytest

from tradinglab.backtest import run
from tradinglab.risk import RiskSettings, kill_switch, size_position
from tradinglab.strategies import meanrev_signal, trend_signal


def make_prices(n: int = 400, drift: float = 0.0005, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.01, n)
    close = 100 * np.exp(np.cumsum(rets))
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, n)),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=idx,
    )


def test_trend_signal_bounds():
    df = make_prices()
    res = trend_signal(df)
    assert res.target.between(0, 1).all()
    assert len(res.target) == len(df)


def test_meanrev_signal_bounds():
    df = make_prices()
    res = meanrev_signal(df)
    assert res.target.between(0, 1).all()


def test_backtest_runs_and_conserves_cash():
    df = make_prices()
    res = trend_signal(df)
    bt = run(df, res.target, starting_cash=10_000)
    assert len(bt.equity) > 0
    assert bt.equity.iloc[-1] > 0
    assert np.isfinite(bt.metrics["sharpe"])
    # Sin apalancamiento el equity nunca debe ser negativo
    assert (bt.equity > 0).all()


def test_backtest_short_profits_in_downtrend():
    n = 120
    close = 200 - np.arange(n) * 1.0
    idx = pd.bdate_range("2024-01-01", periods=n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1_000.0,
        },
        index=idx,
    )
    target = pd.Series(-1.0, index=idx)
    bt = run(df, target, starting_cash=10_000, commission_bps=0, slippage_bps=0)
    assert bt.equity.iloc[-1] > 10_000
    assert (bt.equity > 0).all()


def test_backtest_short_loses_when_price_rises():
    n = 120
    close = 100 + np.arange(n) * 1.0
    idx = pd.bdate_range("2024-01-01", periods=n)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1_000.0,
        },
        index=idx,
    )
    target = pd.Series(-1.0, index=idx)
    bt = run(df, target, starting_cash=10_000, commission_bps=0, slippage_bps=0)
    assert bt.equity.iloc[-1] < 10_000
    assert (bt.equity > 0).all()


def test_size_position_respects_cap():
    cfg = RiskSettings(max_position_pct=0.10, per_trade_risk_pct=0.01, atr_stop_mult=2.0)
    qty = size_position(equity=100_000, price=100, atr_value=2.0, cfg=cfg)
    assert qty * 100 <= 100_000 * 0.10 + 1e-6


def test_kill_switch_triggers_on_drawdown():
    cfg = RiskSettings(max_drawdown_pct=0.10, daily_loss_limit_pct=0.5)
    eq = pd.Series([100, 110, 120, 90])
    killed, reason = kill_switch(eq, cfg)
    assert killed
    assert "drawdown" in reason
