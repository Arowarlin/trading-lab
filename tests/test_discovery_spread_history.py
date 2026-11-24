"""T11 · Spread histórico por barra: ASK, mediana y escalado al bróker."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt
from tradinglab.discovery.spread_history import (
    choose_spread_model,
    historical_spread_provider,
    local_hour_medians,
    scale_factors,
    spread_bps_from_ask,
)
from tradinglab.propfund.costs import CostProfile
from tradinglab.propfund.models import Market


def _profile() -> CostProfile:
    return CostProfile(
        account="X",
        symbol="EURUSD",
        market=Market.CFD,
        commission_type="zero",
        commission_value=0.0,
        spread_price=0.0002,
        spread_p75_price=0.0005,
        slippage_price=0.0,
    )


def test_ask_sintetico_da_el_spread_exacto():
    index = pd.date_range("2026-01-01 10:00", periods=3, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {
            "close": [100.0, 200.0, 100.0],
            "ask_close": [100.02, 200.04, np.nan],
        },
        index=index,
    )
    spread = spread_bps_from_ask(frame)
    assert spread.iloc[0] == pytest.approx(2.0)
    assert spread.iloc[1] == pytest.approx(2.0)
    assert np.isnan(spread.iloc[2])


def test_sin_ask_se_usa_la_mediana_horaria():
    assert (
        choose_spread_model(
            cost_model_version=2, configured="p75_static", has_ask=False
        )
        == "hourly_median"
    )
    assert (
        choose_spread_model(
            cost_model_version=2, configured="p75_static", has_ask=True
        )
        == "historical_scaled"
    )
    assert (
        choose_spread_model(
            cost_model_version=1, configured="p75_static", has_ask=True
        )
        == "p75_static"
    )


def test_mediana_y_escalado_preservan_la_mediana_del_broker(tmp_path: Path):
    index = pd.date_range("2026-11-16 09:00", periods=180, freq="min", tz="UTC")
    close = np.full(len(index), 100.0)
    # Spread Dukascopy constante de 2 bps.
    ask = close * (1.0 + 2.0 / 10_000.0)
    source = pd.DataFrame({"close": close, "ask_close": ask}, index=index)
    source.to_parquet(tmp_path / "EURUSD_M1.parquet")

    medians = local_hour_medians(spread_bps_from_ask(source), session_tz="UTC")
    assert medians[9] == pytest.approx(2.0)
    assert medians[10] == pytest.approx(2.0)

    factors = scale_factors(medians, {9: 3.0, 10: 3.0})
    assert factors[9] == pytest.approx(1.5)
    assert factors[10] == pytest.approx(1.5)

    provider = historical_spread_provider(
        "EURUSD",
        session_tz="UTC",
        broker_median_by_hour={9: 3.0, 10: 3.0},
        start=index[0].isoformat(),
        end=index[-1].isoformat(),
        directory=tmp_path,
    )
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        index=pd.DatetimeIndex(["2026-11-16 10:30", "2026-11-16 11:30"], tz="UTC"),
    )
    values = provider(bars)
    assert values is not None
    assert values == pytest.approx([3.0, 3.0])


def test_ventana_comun_ausente_es_sin_datos(tmp_path: Path):
    index = pd.date_range("2020-01-01 09:00", periods=60, freq="min", tz="UTC")
    close = np.full(len(index), 100.0)
    source = pd.DataFrame(
        {"close": close, "ask_close": close * 1.0002}, index=index
    )
    source.to_parquet(tmp_path / "EURUSD_M1.parquet")
    provider = historical_spread_provider(
        "EURUSD",
        session_tz="UTC",
        broker_median_by_hour={9: 3.0},
        start="2026-11-16T00:00:00+00:00",
        end="2026-11-17T00:00:00+00:00",
        directory=tmp_path,
    )
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        index=pd.DatetimeIndex(["2020-01-01 09:30"], tz="UTC"),
    )
    assert provider(bars) is None


def test_panel_usa_mediana_y_p75_solo_en_estres():
    cost = fastbt.CfdHourlyMedianCosts(
        _profile(),
        spread_bps_by_local_hour={10: 3.0},
        p75_bps_by_local_hour={10: 5.0},
        session_tz="UTC",
        provider=None,
    )
    bars = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
        index=pd.DatetimeIndex(["2026-11-16 10:30"], tz="UTC"),
    )
    assert cost.panel(bars).spread_bps[0] == pytest.approx(3.0)
    assert cost.p75_panel(bars).spread_bps[0] == pytest.approx(5.0)
