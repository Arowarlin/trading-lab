from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.backtest import run


def test_entrada_reduccion_y_cierre_es_un_solo_viaje():
    index = pd.bdate_range("2026-11-09", periods=5, tz="UTC")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1_000.0,
        },
        index=index,
    )
    # shift(1): 0, 1, 1, 0.5, 0 -> abre, mantiene, reduce a la mitad, cierra.
    target = pd.Series([1.0, 1.0, 0.5, 0.0, 0.0], index=index)
    result = run(
        bars,
        target,
        starting_cash=100_000.0,
        commission_bps=10.0,
        slippage_bps=0.0,
    )
    assert result.metrics["num_trades"] == 1
    assert len(result.trade_pnls) == 1
    assert len(result.trade_days) == 1
    # 1.000 acciones: entrada 100 + salidas 50 + 50 = 200 de comisión.
    assert result.trade_pnls[0] == pytest.approx(-200.0)
    assert result.metrics["num_trades"] == len(result.trade_pnls)
