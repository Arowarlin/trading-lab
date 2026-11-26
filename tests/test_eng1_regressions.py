"""Regresiones del programa ENG-1 para defectos del motor (ENG-M1).

Los tests de A-01, B-01 y D-07 se escribieron como ``xfail(strict=True)``
mientras EDGE-2 usaba el motor (commit 1c40a0c): fallaban por el defecto. Con
la corrección (``discovery`` 0.3.0) pasan y se quitó la marca. Ver
docs/engineering/AUDIT_FINDINGS.md.

Todo es sintético: no hay precios, spreads ni swaps de mercado.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt
from tradinglab.discovery.fastbt import ExitSpec, RunLimits, Signals, cfd_costs_from_bps, run

NY = "America/New_York"
ZERO = cfd_costs_from_bps(commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0)


def _signals(n: int, long_pos: tuple[int, ...]) -> Signals:
    longs = np.zeros(n, dtype=bool)
    longs[list(long_pos)] = True
    return Signals(longs, np.zeros(n, dtype=bool), 0)


def test_a01_stop_d1_se_evalua_en_la_sesion_del_lunes():
    # Sesiones D1 de lunes a viernes, etiquetadas a las 17:00 NY del día anterior
    # (como resample_session): la del lunes lleva etiqueta de domingo.
    sessions = pd.bdate_range("2024-03-04", "2024-03-15")
    index = pd.DatetimeIndex(
        [(day - pd.Timedelta(days=1)).replace(hour=17).tz_localize(NY) for day in sessions]
    ).tz_convert("UTC")
    bars = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}, index=index
    )
    monday = 5  # sesión del lunes 11, etiquetada domingo 10 a las 17:00 NY
    bars.iloc[monday, bars.columns.get_loc("low")] = 90.0
    limits = RunLimits(
        session_tz=NY,
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        allow_next_day_entry=True,
        close_at_end=True,
    )
    spec = ExitSpec(stop="pct", stop_mult=2.0, target="pct", target_pct=50.0)
    result = run(_signals(len(bars), (1,)), bars, spec, ZERO, limits)

    assert len(result.trades) == 1
    trade = result.trades[0]
    # El mínimo de 90 de la sesión del lunes perfora el stop de 98.
    assert trade.reason == "stop"
    assert trade.exit_index == monday


def test_b01_comision_usdjpy_en_bps_del_nocional_en_usd():
    from tradinglab.propfund.costs import load_profile

    profile = replace(load_profile("CFD-001", "USDJPY", firm="ftmo"), slippage_price=0.0)
    costs = fastbt.CfdProfileCosts(profile, contract_size=100_000.0, spread_bps_by_hour={0: 0.0})
    side = 0.5 if profile.commission_side == "round_turn" else 1.0
    usd_per_side = float(profile.commission_value) * side
    # USDJPY tiene el USD como base: el nocional de un lote son 100.000 USD
    # sea cual sea el precio (sintético: 150).
    expected_bps = usd_per_side / 100_000.0 * 10_000.0
    got_bps = float(costs._commission_bps(np.array([150.0]))[0])
    assert got_bps == pytest.approx(expected_bps, rel=1e-9)


def test_d07_sharpe_diario_incluye_los_dias_sin_operacion():
    # 60 días hábiles de velas H1 (10:00-15:00 NY) y señales cada 10 días.
    days = pd.bdate_range("2024-01-08", periods=60)
    stamps = [
        pd.Timestamp(day).replace(hour=hour).tz_localize(NY)
        for day in days
        for hour in range(10, 16)
    ]
    index = pd.DatetimeIndex(stamps).tz_convert("UTC")
    n = len(index)
    close = np.full(n, 100.0)
    high = close + 0.5
    low = close - 0.5
    rng = np.random.default_rng(7)
    entries = tuple(range(0, n - 12, 60))
    for pos in entries:
        # La vela siguiente a la señal toca el objetivo o el stop según la semilla.
        if rng.random() < 0.6:
            high[pos + 1] = 103.0
        else:
            low[pos + 1] = 97.0
    bars = pd.DataFrame({"open": close, "high": high, "low": low, "close": close}, index=index)
    limits = RunLimits(session_tz=NY, session_start="10:00", session_end="15:00", flat_at="15:00")
    spec = ExitSpec(stop="pct", stop_mult=2.0, target="pct", target_pct=2.0)
    result = run(_signals(n, entries), bars, spec, ZERO, limits)
    assert len(result.trades) >= 4

    calendar = pd.bdate_range(days[0], days[-1])
    daily = result.daily_r.copy()
    daily.index = pd.DatetimeIndex(daily.index).normalize()
    full = daily.reindex(calendar, fill_value=0.0)
    expected = float(full.mean() / full.std(ddof=1) * math.sqrt(252))
    assert result.metrics["sharpe_daily"] == pytest.approx(expected, rel=1e-9)


def test_a02_stop_de_una_posicion_fuera_de_sesion():
    # Sesión 10:00-15:00 NY con flat_at 15:00 en H1 (legacy): la posición duerme.
    # Una vela nocturna fuera de la sesión perfora el stop: debe cerrarse ahí.
    day1 = [pd.Timestamp(f"2024-03-05 {h:02d}:00").tz_localize(NY) for h in range(10, 24)]
    day2 = [pd.Timestamp(f"2024-03-06 {h:02d}:00").tz_localize(NY) for h in range(0, 16)]
    index = pd.DatetimeIndex(day1 + day2).tz_convert("UTC")
    bars = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}, index=index)
    night = len(day1) + 2  # 02:00 NY del día 2, fuera de la sesión
    bars.iloc[night, bars.columns.get_loc("low")] = 90.0
    limits = RunLimits(session_tz=NY, session_start="10:00", session_end="15:00", flat_at="15:30")
    spec = ExitSpec(stop="pct", stop_mult=2.0, target=None)
    result = run(_signals(len(bars), (0,)), bars, spec, ZERO, limits)
    assert len(result.trades) == 1
    assert result.trades[0].reason == "stop"
    assert result.trades[0].exit_index == night


def test_a04_calendario_el_stop_va_antes_que_la_salida_de_calendario():
    n = 6
    index = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    bars = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}, index=index)
    bars.iloc[3, bars.columns.get_loc("low")] = 90.0  # perfora el stop (98) y cierra en 100
    longs = np.zeros(n, dtype=bool)
    longs[1] = True
    exits = np.full(n, -1, dtype=np.int64)
    exits[1] = 3
    limits = RunLimits(
        session_tz="UTC", session_start="00:00", session_end="23:59", flat_at="23:59",
        weekdays=tuple(range(7)), close_at_end=True, allow_next_day_entry=True,
    )
    signals = Signals(longs, np.zeros(n, dtype=bool), 0, exits)
    result = run(signals, bars, ExitSpec(stop="pct", stop_mult=2.0, target=None), ZERO, limits)
    assert len(result.trades) == 1
    assert result.trades[0].reason == "stop"
    assert result.trades[0].exit_price == pytest.approx(98.0)
