"""E1 · Paridad motor vs MT5 con historial sintético."""

from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.ea_parity import Trade, match_trades


def _trade(
    side: str,
    entry: str,
    entry_price: float,
    exit_: str,
    exit_price: float,
    *,
    source: str = "engine",
) -> Trade:
    return Trade(
        side=side,
        entry_time=pd.Timestamp(entry, tz="UTC"),
        entry_price=entry_price,
        exit_time=pd.Timestamp(exit_, tz="UTC"),
        exit_price=exit_price,
        source=source,
    )


def test_empareja_por_lado_y_hora_y_calcula_diferencias_exactas():
    engine = [
        _trade("long", "2026-11-24 10:00", 100.0, "2026-11-24 11:00", 101.0)
    ]
    real = [
        _trade(
            "long",
            "2026-11-24 10:05",
            100.5,
            "2026-11-24 11:05",
            101.2,
            source="mt5",
        )
    ]

    matches, engine_only, real_only = match_trades(engine, real)

    assert len(matches) == 1
    assert not engine_only and not real_only
    engine_trade, real_trade = matches[0]
    assert engine_trade.side == "long"
    assert (real_trade.entry_price - engine_trade.entry_price) / 0.01 == pytest.approx(
        50.0
    )
    assert (real_trade.exit_price - engine_trade.exit_price) / 0.01 == pytest.approx(
        20.0
    )
    assert real_trade.result_points() - engine_trade.result_points() == pytest.approx(
        -30.0
    )


def test_detecta_huerfanos_y_no_empareja_lados_distintos():
    engine = [
        _trade("long", "2026-11-24 10:00", 100.0, "2026-11-24 11:00", 101.0),
        _trade("long", "2026-11-24 12:00", 102.0, "2026-11-24 13:00", 103.0),
    ]
    real = [
        _trade(
            "short",
            "2026-11-24 10:00",
            100.0,
            "2026-11-24 11:00",
            99.0,
            source="mt5",
        ),
        _trade(
            "long",
            "2026-11-24 12:03",
            102.1,
            "2026-11-24 13:03",
            103.1,
            source="mt5",
        ),
        _trade(
            "long",
            "2026-11-24 15:00",
            104.0,
            "2026-11-24 16:00",
            105.0,
            source="mt5",
        ),
    ]

    matches, engine_only, real_only = match_trades(engine, real)

    assert len(matches) == 1
    assert matches[0][0].entry_time == pd.Timestamp("2026-11-24 12:00", tz="UTC")
    assert len(engine_only) == 1
    assert engine_only[0].entry_time == pd.Timestamp("2026-11-24 10:00", tz="UTC")
    assert len(real_only) == 2


def test_tolerancia_de_una_vela_no_empareja_seis_minutos():
    engine = [
        _trade("long", "2026-11-24 10:00", 100.0, "2026-11-24 11:00", 101.0)
    ]
    real = [
        _trade(
            "long",
            "2026-11-24 10:06",
            100.0,
            "2026-11-24 11:06",
            101.0,
            source="mt5",
        )
    ]

    matches, engine_only, real_only = match_trades(engine, real)

    assert not matches
    assert len(engine_only) == 1
    assert len(real_only) == 1
