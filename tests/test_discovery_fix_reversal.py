"""Fix reversal: horas exactas, DST de Londres/NY y lado fijo (Q2)."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from tradinglab.discovery import compiler, dsl, engine, genetic, grid


def _frame(start: str, periods: int, tz: str = "UTC") -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="h", tz=tz)
    close = 100.0 + np.arange(periods) * 0.01
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
        },
        index=index,
    )


def _campaign(side: str, fix_start: str, fix_end: str, instrument: str) -> dict:
    return {
        "campaign_id": f"q2-{side}-{instrument}",
        "instrument": instrument,
        "timeframe": "H1",
        "template": "fix_reversal",
        "config": {
            "mode": "grid",
            "profile": "small",
            "grid": grid.load_grid("fix_reversal"),
            "side": side,
            "fix_start": fix_start,
            "fix_end": fix_end,
        },
    }


def test_plantilla_y_lado_fijo() -> None:
    assert genetic.template_symmetric("fix_reversal") is False
    assert genetic.template_timeframes("fix_reversal") == ("H1",)
    eur = engine.candidate_strategies(
        _campaign("long", "15:00", "15:59", "EURUSD")
    )[0]
    assert len(eur) == 6
    for strategy in eur:
        assert strategy["long_entry"]["start"] == "15:00"
        assert strategy["long_entry"]["end"] == "15:59"
        assert strategy["short_entry"] is None
        assert dsl.validate(strategy) == []
    jpy = engine.candidate_strategies(
        _campaign("short", "09:00", "09:59", "USDJPY")
    )[0]
    for strategy in jpy:
        assert strategy["short_entry"]["start"] == "09:00"
        assert strategy["short_entry"]["end"] == "09:59"
        assert strategy["long_entry"] is None
        assert dsl.validate(strategy) == []


def test_fix_londres_invierno_y_verano() -> None:
    # 2026-03-10: EE. UU. ya en EDT, Londres sigue en GMT (desfase).
    winter = _frame("2026-03-05", 24 * 10)
    strategy = engine.candidate_strategies(
        _campaign("long", "15:00", "15:59", "EURUSD")
    )[0][0]
    signals = compiler.compile(strategy, winter)
    positions = np.flatnonzero(signals.long_entry)
    assert positions.size
    local = winter.index.tz_convert("Europe/London")
    assert all(local[position].hour == 15 for position in positions)
    # 15:00 Londres en GMT = 15:00 UTC.
    assert winter.index[positions[0]].hour == 15
    # 2026-03-30: Londres ya en BST = 14:00 UTC.
    summer = _frame("2026-03-30", 24 * 10)
    signals = compiler.compile(strategy, summer)
    positions = np.flatnonzero(signals.long_entry)
    assert positions.size
    local = summer.index.tz_convert("Europe/London")
    assert all(local[position].hour == 15 for position in positions)
    assert summer.index[positions[0]].hour == 14


def test_fix_tokio_sin_dst() -> None:
    strategy = engine.candidate_strategies(
        _campaign("short", "09:00", "09:59", "USDJPY")
    )[0][0]
    frame = _frame("2026-01-05", 24 * 10)
    signals = compiler.compile(strategy, frame)
    positions = np.flatnonzero(signals.short_entry)
    assert positions.size
    local = frame.index.tz_convert("Asia/Tokyo")
    assert all(local[position].hour == 9 for position in positions)
    assert all(frame.index[position].hour == 0 for position in positions)


def test_sin_anticipacion_cambiar_el_futuro_no_cambia_las_senales() -> None:
    strategy = engine.candidate_strategies(
        _campaign("long", "15:00", "15:59", "EURUSD")
    )[0][0]
    frame = _frame("2026-01-05", 24 * 10)
    changed = copy.deepcopy(frame)
    changed.loc[changed.index >= changed.index[100], ["open", "high", "low", "close"]] *= 2
    first = compiler.compile(strategy, frame)
    second = compiler.compile(strategy, changed)
    assert np.array_equal(first.long_entry, second.long_entry)
    assert np.array_equal(first.short_entry, second.short_entry)


def test_entrada_al_cierre_de_la_barra_del_fix() -> None:
    from tradinglab.discovery import fastbt
    from tradinglab.discovery.specs import exit_spec_from_strategy, run_limits_from_strategy

    frame = _frame("2026-01-05", 24 * 10)
    strategy = engine.candidate_strategies(
        _campaign("long", "15:00", "15:59", "EURUSD")
    )[0][0]
    model = dsl.Strategy.model_validate(strategy)
    signals = compiler.compile(model, frame)
    cost = fastbt.cfd_costs_from_bps(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )
    setup = type("S", (), {"weekdays": (0, 1, 2, 3, 4), "session_tz": "Europe/London"})()
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    prepared = fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))
    result = fastbt.run(
        signals,
        frame,
        exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
    )
    assert result.trades
    for trade in result.trades:
        assert trade.entry_time.tz_convert("Europe/London").hour == 16
