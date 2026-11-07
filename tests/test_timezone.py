from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from tradinglab.execution.mt5 import MT5Broker, server_offset_from_tick
from tradinglab.prop import PropGuard, ftmo


def _state(values: list[float], start: str, reset_tz: str):
    index = pd.date_range(start=start, periods=len(values), freq="h", tz="UTC")
    equity = pd.Series(values, index=index)
    rules = ftmo(100_000, reset_tz=reset_tz)
    return PropGuard.state_from_equity(rules, equity, initial_balance=100_000)


def test_offset_invierno_y_verano():
    winter = datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp()
    summer = datetime(2026, 7, 15, 12, tzinfo=timezone.utc).timestamp()
    assert server_offset_from_tick(winter + 2 * 3600, winter) == pytest.approx(2.0)
    assert server_offset_from_tick(summer + 3 * 3600, summer) == pytest.approx(3.0)
    assert server_offset_from_tick(summer + 2.5 * 3600, summer) == pytest.approx(2.5)


def test_offset_rechaza_tick_viejo_o_irregular():
    now = datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp()
    # Mercado cerrado: el tick es anterior a "now"; antes producía offset negativo.
    assert server_offset_from_tick(now - 3 * 3600, now) is None
    # Residuo grande: no es un tick fresco.
    assert server_offset_from_tick(now + 2 * 3600 + 1200, now) is None
    # Servidor UTC (offset 0) es válido.
    assert server_offset_from_tick(now + 30, now) == pytest.approx(0.0)


def test_to_utc_aplica_offset_del_servidor():
    ts = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc).timestamp()
    invierno = MT5Broker(server_utc_offset_hours=2, dry_run=True)
    verano = MT5Broker(server_utc_offset_hours=3, dry_run=True)
    assert invierno._to_utc(ts) == datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert verano._to_utc(ts) == datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)


def test_reset_diario_praga_cambio_primavera():
    # 2026-03-29: CET (UTC+1) -> CEST (UTC+2) a las 01:00 UTC.
    values = [100_000 + 100 * i for i in range(26)]
    state = _state(values, "2026-03-28 20:00", "Europe/Prague")
    # El día local 29 empieza a las 23:00 UTC del 28 (índice 3).
    assert state.day_start_equity == pytest.approx(100_300)
    assert state.equity == pytest.approx(102_500)


def test_reset_diario_praga_cambio_otono():
    # 2026-10-25: CEST (UTC+2) -> CET (UTC+1) a las 01:00 UTC.
    values = [100_000 + 100 * i for i in range(27)]
    state = _state(values, "2026-10-24 20:00", "Europe/Prague")
    # El día local 25 empieza a las 22:00 UTC del 24 (índice 2).
    assert state.day_start_equity == pytest.approx(100_200)
    assert state.equity == pytest.approx(102_600)


def test_reset_diario_nueva_york_cambio_primavera():
    # 2026-03-08: EST (UTC-5) -> EDT (UTC-4) a las 07:00 UTC.
    values = [100_000 + 100 * i for i in range(25)]
    state = _state(values, "2026-03-08 03:00", "America/New_York")
    # El día local 8 empieza a las 05:00 UTC (índice 2).
    assert state.day_start_equity == pytest.approx(100_200)
    assert state.equity == pytest.approx(102_400)


def test_reset_diario_nueva_york_cambio_otono():
    # 2026-11-01: EDT (UTC-4) -> EST (UTC-5) a las 06:00 UTC.
    values = [100_000 + 100 * i for i in range(27)]
    state = _state(values, "2026-11-01 02:00", "America/New_York")
    # El día local 1 empieza a las 04:00 UTC (índice 2).
    assert state.day_start_equity == pytest.approx(100_200)
    assert state.equity == pytest.approx(102_600)
