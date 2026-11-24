"""T13 · Swap histórico: calibración, tipo 0 y triple rollover."""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.discovery.swap_history import (
    annual_swap_table,
    historical_swap_report,
    reference_series,
)
from tradinglab.propfund.costs import CostProfile, SwapSpec
from tradinglab.propfund.models import Market


def _profile(
    *,
    account: str = "CFD-006",
    symbol: str = "US100",
    swap_long: float = -7.33,
    swap_short: float = -1.33,
    mode: int = 5,
    point: float | None = None,
    triple: int = 5,
) -> CostProfile:
    return CostProfile(
        account=account,
        symbol=symbol,
        market=Market.CFD,
        swap_long=swap_long,
        swap_short=swap_short,
        swap_mode=mode,
        swap_rollover3days=triple,
        swap_rollover_hour="17:00",
        swap_rollover_tz="America/New_York",
        point=point,
    )


def _times(entry: str, exit_: str):
    return (
        pd.Timestamp(entry, tz="America/New_York"),
        pd.Timestamp(exit_, tz="America/New_York"),
    )


def test_tipo_historico_igual_al_de_hoy_reproduce_el_swap_medido():
    profile = _profile()
    base = SwapSpec.from_profile(profile)
    assert base is not None
    rates = pd.Series(
        [4.0], index=pd.DatetimeIndex(["2026-11-23"]), dtype=float
    )
    historical = base.with_historical(
        rates, reference_price=20_000.0, reference_rate=4.0
    )
    entry, exit_ = _times("2026-11-23 16:00", "2026-11-23 18:00")
    value = historical.r(
        side="long",
        entry_price=20_000.0,
        risk_price=100.0,
        entry_time=entry,
        exit_time=exit_,
    )
    expected = 20_000.0 * (-7.33 / 100.0 / 360.0) / 100.0
    assert value == pytest.approx(expected)
    assert historical.markup_long == pytest.approx(-7.33 - 4.0)


def test_tipo_cero_deja_solo_el_markup():
    profile = _profile(swap_long=2.0, swap_short=-1.0)
    base = SwapSpec.from_profile(profile)
    assert base is not None
    rates = pd.Series([0.0], index=pd.DatetimeIndex(["2026-11-23"]), dtype=float)
    historical = base.with_historical(
        rates, reference_price=20_000.0, reference_rate=0.0
    )
    entry, exit_ = _times("2026-11-23 16:00", "2026-11-23 18:00")
    value = historical.r(
        side="long",
        entry_price=20_000.0,
        risk_price=100.0,
        entry_time=entry,
        exit_time=exit_,
        allow_credit=False,
    )
    assert value == 0.0  # crédito desactivado en Discovery
    cost = historical.r(
        side="short",
        entry_price=20_000.0,
        risk_price=100.0,
        entry_time=entry,
        exit_time=exit_,
    )
    assert cost == pytest.approx(20_000.0 * (-1.0 / 100.0 / 360.0) / 100.0)


def test_triple_rollover_se_mantiene():
    profile = _profile(triple=5)
    spec = SwapSpec.from_profile(profile)
    assert spec is not None
    # Jueves 17:00 NY = viernes 00:00 del servidor (triple).
    entry, exit_ = _times("2026-11-19 16:00", "2026-11-19 18:00")
    assert spec.units(entry, exit_) == 3
    rates = pd.Series([4.0], index=pd.DatetimeIndex(["2026-11-19"]), dtype=float)
    historical = spec.with_historical(
        rates, reference_price=20_000.0, reference_rate=4.0
    )
    value = historical.r(
        side="long",
        entry_price=20_000.0,
        risk_price=100.0,
        entry_time=entry,
        exit_time=exit_,
    )
    assert value == pytest.approx(
        3 * 20_000.0 * (-7.33 / 100.0 / 360.0) / 100.0
    )


def test_modo_points_se_calibra_con_el_precio_de_hoy():
    profile = _profile(
        account="CFD-001",
        swap_long=1076.28,
        swap_short=-1677.49,
        mode=1,
        point=0.01,
        triple=5,
    )
    spec = SwapSpec.from_profile(profile)
    assert spec is not None
    rate = 1076.28 * 0.01 / 20_000.0 * 360.0 * 100.0
    historical = spec.with_historical(
        pd.Series([4.0], index=pd.DatetimeIndex(["2026-11-23"])),
        reference_price=20_000.0,
        reference_rate=4.0,
    )
    assert historical.markup_long == pytest.approx(rate - 4.0)
    entry, exit_ = _times("2026-11-23 16:00", "2026-11-23 18:00")
    value = historical.r(
        side="long",
        entry_price=20_000.0,
        risk_price=100.0,
        entry_time=entry,
        exit_time=exit_,
    )
    assert value == pytest.approx(1076.28 * 0.01 / 100.0)


def test_referencia_fx_usa_el_diferencial():
    series = reference_series("EURUSD")
    if series is None:
        pytest.skip("Sin datos: FRED no disponible")
    assert series.index.tz is None
    assert series.notna().all()


def test_reporte_y_tabla_anual():
    rows = annual_swap_table()
    assert rows
    report = historical_swap_report()
    assert "Swap histórico" in report
    assert "| Cuenta | Símbolo | Lado | Año |" in report
