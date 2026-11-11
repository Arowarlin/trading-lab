from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradinglab.conditioners import business_days_around
from tradinglab.funnel import discipline, funnel
from tradinglab.instruments import Instrument
from tradinglab.intraday import fix_flow, session_hold
from tradinglab.strategies.overnight_reversal import (
    overnight_returns,
    select_terciles,
    simulate_daily,
)


def _bars(n: int = 240, start: str = "2026-01-05 00:00") -> pd.DataFrame:
    index = pd.date_range(start, periods=n, freq="h", tz="UTC")
    close = 100 + np.arange(n) * 0.01
    return pd.DataFrame(
        {
            "open": close - 0.01,
            "high": close + 0.02,
            "low": close - 0.02,
            "close": close,
            "volume": 1000.0,
        },
        index=index,
    )


def test_session_hold_una_operacion_por_sesion():
    df = _bars(240)
    result = session_hold(df, session="LDN", direction=1)
    target = result.target
    cambios = target[target != target.shift(1)].dropna()
    assert len(cambios) <= 24  # una entrada por día de sesión
    assert set(target.unique()) <= {-1.0, 0.0, 1.0}


def test_fix_flow_solo_en_la_ventana_antes_del_fix():
    df = _bars(240)
    result = fix_flow(df, window_min=60, fix="ecb", side="short_usd")
    objetivo = result.target
    assert objetivo.max() == 0.0  # solo se exposure 0 o 1
    horas = {pd.Timestamp(stamp).hour for stamp in objetivo[objetivo != 0].index}
    assert horas  # hay horas con posición
    assert all(12 <= hora <= 13 for hora in horas)


def test_overnight_returns_usa_el_cierre_anterior():
    df = _bars(3)
    returns = overnight_returns(df)
    esperado = float(df["open"].iloc[1] / df["close"].iloc[0] - 1.0)
    assert returns.iloc[1] == pytest.approx(esperado)


def test_terciles_largo_bajo_y_corto_alto():
    cross = pd.DataFrame(
        {
            "A": [0.09, 0.08],
            "B": [0.07, 0.06],
            "C": [0.05, 0.04],
            "D": [0.03, 0.02],
            "E": [0.01, 0.00],
            "F": [-0.01, -0.02],
            "G": [-0.03, -0.04],
            "H": [-0.05, -0.06],
            "I": [-0.07, -0.08],
        }
    )
    selection = select_terciles(cross)
    assert selection.iloc[0]["I"] == 1.0
    assert selection.iloc[0]["H"] == 1.0
    assert selection.iloc[0]["A"] == -1.0
    assert selection.iloc[0]["D"] == 0.0


def test_simulate_daily_no_deja_posicion_nocturna():
    frame = _bars(3)
    frames = {"A": frame}
    selection = pd.DataFrame(
        {"A": [1.0, 0.0, 0.0]},
        index=pd.date_range("2026-01-05", periods=3, freq="D", tz="UTC"),
    )
    net, stats = simulate_daily(frames, selection, cost_bps=0.0)
    assert len(net) == 3
    assert stats["trades"] == 1
    assert net.iloc[0] != 0.0
    esperado = float(frame["close"].iloc[-1] / frame["open"].iloc[0] - 1.0)
    assert float(net.sum()) == pytest.approx(esperado, abs=5e-4)


def test_tick_ratio_necesita_precio_y_volatilidad():
    instrument = Instrument(symbol="EURUSD", asset_class="fx", tick_size=0.00001)
    assert instrument.tick_ratio(price=1.1, daily_vol=0.01) == pytest.approx(
        0.00001 / (1.1 * 0.01)
    )
    assert instrument.tick_ratio(price=0, daily_vol=0.01) is None


def test_embudo_y_disciplina_sin_datos(tmp_path):
    db = tmp_path / "lab.db"
    from tradinglab.db import init_db

    init_db(db)
    estado = funnel(db)
    assert "counts" in estado
    assert estado["counts"]["variantes_probadas"] == 0
    disc = discipline(db)
    assert disc["total_blocked"] == 0


def test_dias_habiles_no_repiten_finde():
    dias = business_days_around(pd.Timestamp("2026-11-11").date(), 3, 3)
    assert len(dias) == len(set(dias))
    assert all(dia.weekday() < 5 for dia in dias)
