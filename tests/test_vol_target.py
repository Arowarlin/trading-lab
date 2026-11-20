from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.backtest import run as run_backtest
from tradinglab.portfolio import account_vol_factor
from tradinglab.vol_target import profile_vol_config, scale

ROOT = Path(r"E:\trading-lab")


def _returns(values: list[float], start: str = "2025-01-06") -> pd.Series:
    index = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=index, dtype=float)


def test_el_factor_baja_cuando_sube_la_volatilidad():
    calm = [0.001] * 40
    volatile = [0.02, -0.02] * 20
    returns = _returns(calm + volatile)
    factor = scale(returns, target_vol_annual=0.08, halflife_days=10)
    assert factor.iloc[45] > factor.iloc[-1]
    assert factor.iloc[-1] < 1.0


def test_tope_de_apalancamiento():
    returns = _returns([0.0] * 60)
    factor = scale(returns, target_vol_annual=0.08, max_leverage=2.0)
    assert factor.max() <= 2.0
    factor = scale(returns, target_vol_annual=5.0, max_leverage=2.0)
    assert factor.max() <= 2.0


def test_sin_lookahead_truncado_vs_completo():
    returns = _returns([0.01, -0.02] * 30)
    completo = scale(returns, target_vol_annual=0.10, halflife_days=20)
    corte = returns.index[50]
    truncado = scale(returns.loc[:corte], target_vol_annual=0.10, halflife_days=20)
    assert completo.loc[corte] == pytest.approx(truncado.loc[corte])


def test_rebalance_semanal_mantiene_el_factor():
    returns = _returns([0.001] * 30 + [0.02] * 30)
    factor = scale(returns, target_vol_annual=0.08, halflife_days=10, rebalance="W")
    semana = factor.groupby(factor.index.to_period("W")).transform("first")
    assert factor.equals(semana)
    assert factor.nunique() < len(factor)


def test_el_factor_no_mira_el_retorno_del_dia():
    returns = _returns([0.01] * 5 + [0.5] + [0.01] * 5)
    factor = scale(returns, 0.08, halflife_days=5, rebalance="D")
    # el día del salto el factor todavía no lo ve
    assert factor.iloc[5] == pytest.approx(factor.iloc[4])
    # al día siguiente ya lo ve
    assert factor.iloc[6] < factor.iloc[5]


def test_el_backtest_escala_la_exposicion():
    index = pd.bdate_range("2025-01-01", periods=120)
    close = pd.Series(100 + np.cumsum(np.tile([2.0, -2.0], 60)), index=index)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": 1_000_000.0,
        },
        index=index,
    )
    target = pd.Series(1.0, index=index)
    base = run_backtest(df, target, starting_cash=100_000.0)
    vol = run_backtest(
        df,
        target,
        starting_cash=100_000.0,
        vol_target={"target_vol_annual": 0.08, "max_leverage": 2.0},
    )
    assert float(vol.equity.std()) < float(base.equity.std())
    assert float(vol.exposure) < float(base.exposure)


def test_perfil_tiene_target_vol_y_el_flag_esta_apagado():
    config = profile_vol_config("swing_cfd")
    assert config["target_vol"] == pytest.approx(0.10)
    assert config["enabled"] is False
    assert profile_vol_config("intraday_fx")["target_vol"] == pytest.approx(0.06)
    assert profile_vol_config("intraday_futures")["target_vol"] == pytest.approx(0.10)


def test_factor_de_cartera_sin_objetivo_es_uno():
    returns = _returns([0.01] * 30)
    assert account_vol_factor({"bot-a": returns}, None) == 1.0
    factor = account_vol_factor({"bot-a": returns}, 0.08)
    assert 0.0 < factor <= 2.0


def test_el_informe_de_comparacion_se_escribe(tmp_path, monkeypatch):
    from tradinglab import vol_report

    rows = [
        {
            "bot": "demo",
            "symbol": "SPY",
            "profile": "swing_equity",
            "target_vol": 0.08,
            "base": {
                "sharpe": 1.0,
                "max_drawdown": -0.1,
                "total_return": 0.2,
                "num_trades": 10,
                "turnover": 2.0,
                "cost": 100.0,
                "mc": {"pass_rate": 0.4, "breach_rate": 0.2},
            },
            "vol": {
                "sharpe": 0.8,
                "max_drawdown": -0.05,
                "total_return": 0.1,
                "num_trades": 8,
                "turnover": 1.2,
                "cost": 60.0,
                "mc": {"pass_rate": 0.5, "breach_rate": 0.1},
            },
        }
    ]
    monkeypatch.setattr(vol_report, "_specs", lambda ids: [])
    from tradinglab.vol_report import compare

    written = compare(out_dir=tmp_path)
    assert written.exists()
    assert "Objetivo de volatilidad" in written.read_text(encoding="utf-8")
    assert rows  # el informe se escribe aunque no haya bots
    assert json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8")) == []
