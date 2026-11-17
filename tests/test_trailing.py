from __future__ import annotations

from tradinglab.trailing import tp_protection_stop


def test_short_be_al_50_y_50pct_del_tp_al_80():
    assert tp_protection_stop(
        side="sell", entry=100.0, tp=80.0, best=90.0, price=90.0,
        current_sl=120.0,
    ) == 100.0
    assert tp_protection_stop(
        side="sell", entry=100.0, tp=80.0, best=84.0, price=84.0,
        current_sl=120.0,
    ) == 90.0


def test_long_be_al_50_y_50pct_del_tp_al_80():
    assert tp_protection_stop(
        side="buy", entry=100.0, tp=120.0, best=110.0, price=110.0,
        current_sl=80.0,
    ) == 100.0
    assert tp_protection_stop(
        side="buy", entry=100.0, tp=120.0, best=116.0, price=116.0,
        current_sl=80.0,
    ) == 110.0


def test_no_aleja_el_stop_ni_lo_deja_del_lado_equivocado():
    # El SL actual ya es mejor que breakeven.
    assert tp_protection_stop(
        side="sell", entry=100.0, tp=80.0, best=90.0, price=90.0,
        current_sl=95.0,
    ) is None
    # A 50 % el precio está demasiado cerca: no se puede poner BE a 2 puntos.
    assert tp_protection_stop(
        side="sell", entry=100.0, tp=80.0, best=90.0, price=99.0,
        current_sl=120.0, min_distance=2.0,
    ) is None


def test_si_el_precio_devuelve_el_80pct_cae_a_breakeven():
    # Llegó al 80 % (best=84) pero ya devolvió hasta 96: el 50 % del TP (90)
    # quedaría por debajo del precio en un corto; al menos deja BE (100).
    assert tp_protection_stop(
        side="sell", entry=100.0, tp=80.0, best=84.0, price=96.0,
        current_sl=120.0,
    ) == 100.0
