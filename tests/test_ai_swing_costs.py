from __future__ import annotations

from datetime import date

import pytest

from tradinglab.ai_trader import _cost_ratio, _swing_holding_nights
from tradinglab.db import connect, init_db

START = date(2026, 11, 16)  # lunes; el viernes es el triple de US100


def _ratio(nights: int) -> float:
    value = _cost_ratio(
        "US100.CASH",
        27_945.73,
        1.0,
        500.0,
        slippage_price=1.0,
        side="buy",
        holding_nights=nights,
        start_day=START,
        value_per_price=1.0,
    )
    assert value is not None
    return value


def test_cinco_noches_con_triple_el_viernes_supera_el_umbral_swing():
    ratio = _ratio(5)
    assert ratio > 0.05
    assert ratio == pytest.approx(0.1007, rel=1e-2)


def test_una_noche_pasa_si_el_r_es_suficiente():
    ratio = _ratio(1)
    assert ratio < 0.05
    assert ratio == pytest.approx(0.0195, rel=1e-2)


def test_holding_nights_por_defecto_es_tres(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    assert _swing_holding_nights(db) == pytest.approx(3.0)


def test_holding_nights_usa_la_mediana_historica(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for entry, exit_at in (
            ("2026-11-02T10:00:00+00:00", "2026-11-04T10:00:00+00:00"),
            ("2026-11-02T10:00:00+00:00", "2026-11-06T10:00:00+00:00"),
        ):
            con.execute(
                "INSERT INTO ai_trades"
                "(ts, symbol, setup, side, status, exit_ts, style, source) "
                "VALUES (?, 'US100.CASH', 'trend_pullback', 'buy', "
                "'closed', ?, 'swing', 'forward')",
                (entry, exit_at),
            )
    assert _swing_holding_nights(db) == pytest.approx(3.0)
