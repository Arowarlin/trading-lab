from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tradinglab import broker_costs, clock
from tradinglab.execution.mt5 import MT5Broker


def _info() -> SimpleNamespace:
    return SimpleNamespace(
        name="US100.cash",
        swap_long=-676.55,
        swap_short=1.75,
        swap_mode=1,
        digits=2,
        point=0.01,
        trade_tick_size=0.01,
        trade_tick_value=0.01,
        trade_contract_size=1.0,
        volume_min=0.1,
        volume_max=100.0,
        volume_step=0.1,
        trade_stops_level=0,
        filling_mode=0,
        spread=10,
        currency_base="USD",
        currency_profit="USD",
        bid=27_945.0,
        ask=27_946.0,
        trade_mode=4,
        visible=True,
    )


def _fake_mt5(info, calls: list[str]) -> types.ModuleType:
    fake = types.ModuleType("MetaTrader5")
    fake.initialize = lambda: True
    fake.symbols_get = lambda: [SimpleNamespace(name="US100.cash")]
    fake.symbol_info = lambda name: (
        calls.append(str(name)) or (info if str(name) == "US100.cash" else None)
    )
    fake.symbol_select = lambda name, enable=True: (
        calls.append(f"select:{name}") or True
    )
    return fake


def test_broker_costs_mt5_swap_resuelve_mayusculas(monkeypatch):
    calls: list[str] = []
    fake = _fake_mt5(_info(), calls)
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)

    result = broker_costs.mt5_swap("US100.CASH")

    assert result["status"] == "ok"
    assert result["broker_symbol"] == "US100.cash"
    assert "US100.cash" in calls
    assert "US100.CASH" not in calls


def test_symbol_spec_resuelve_mayusculas(monkeypatch):
    calls: list[str] = []
    fake = _fake_mt5(_info(), calls)
    broker = MT5Broker(dry_run=True)
    monkeypatch.setattr(broker, "_require", lambda: fake)

    spec = broker.symbol_spec("US100.CASH")

    assert spec["symbol"] == "US100.cash"
    assert "select:US100.cash" in calls
    assert "US100.cash" in calls


def test_clock_mt5_offset_resuelve_mayusculas(monkeypatch):
    calls: list[str] = []
    fake = types.ModuleType("MetaTrader5")
    fake.initialize = lambda: True
    fake.symbols_get = lambda: [SimpleNamespace(name="US100.cash")]
    fake.symbol_info_tick = lambda name: (
        calls.append(str(name))
        or SimpleNamespace(time=1_000.0)
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(clock, "_utc_now", lambda: 1_000.0)

    import tradinglab.execution.mt5 as mt5_mod

    monkeypatch.setattr(
        mt5_mod, "server_offset_from_tick", lambda tick_time, now: 0.0
    )

    assert clock.mt5_offset_s("US100.CASH") == pytest.approx(0.0)
    assert calls == ["US100.cash"]
