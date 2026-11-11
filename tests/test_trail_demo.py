from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from trail_demo_positions import next_stop  # noqa: E402


def test_mt5_devuelve_sell_y_se_trata_como_corto():
    """El bróker usa 'sell'/'buy'; no se puede confundir un corto con un largo."""
    stop = next_stop(
        side="sell",
        entry=100.0,
        best=99.0,
        atr_value=1.0,
        current_sl=102.0,
        profit_r=1.2,
        trail_r=1.0,
    )
    assert stop == 100.0
    assert (
        next_stop(
            side="buy",
            entry=100.0,
            best=101.0,
            atr_value=1.0,
            current_sl=98.0,
            profit_r=1.2,
            trail_r=1.0,
        )
        == 100.0
    )


def test_breakeven_cuando_llega_a_media_r():
    stop = next_stop(
        side="short",
        entry=100.0,
        best=99.9,
        atr_value=1.0,
        current_sl=102.0,
        profit_r=0.6,
        be_r=0.5,
        trail_r=1.0,
    )
    assert stop == 100.0


def test_trailing_una_atr_tras_una_r():
    stop = next_stop(
        side="short",
        entry=100.0,
        best=98.0,
        atr_value=1.0,
        current_sl=101.0,
        profit_r=1.2,
        be_r=0.5,
        trail_r=1.0,
        atr_mult=1.0,
    )
    assert stop == 99.0


def test_nunca_aleja_el_stop():
    # el SL actual ya está mejor que el candidato -> no se toca
    assert (
        next_stop(
            side="short",
            entry=100.0,
            best=98.0,
            atr_value=1.0,
            current_sl=98.5,
            profit_r=1.2,
            trail_r=1.0,
        )
        is None
    )
    assert (
        next_stop(
            side="long",
            entry=100.0,
            best=102.0,
            atr_value=1.0,
            current_sl=101.5,
            profit_r=1.2,
            trail_r=1.0,
        )
        is None
    )


def test_antes_de_media_r_no_hace_nada():
    assert (
        next_stop(
            side="short",
            entry=100.0,
            best=99.8,
            atr_value=1.0,
            current_sl=102.0,
            profit_r=0.2,
            be_r=0.5,
            trail_r=1.0,
        )
        is None
    )


def test_respeta_la_distancia_minima_del_broker():
    # el candidato cae dentro de la distancia mínima al precio -> None
    assert (
        next_stop(
            side="short",
            entry=100.0,
            best=98.0,
            atr_value=1.0,
            current_sl=101.0,
            profit_r=1.2,
            trail_r=1.0,
            atr_mult=0.0,
            min_distance=0.5,
        )
        is None
    )
