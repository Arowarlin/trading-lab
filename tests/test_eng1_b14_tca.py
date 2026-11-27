"""ENG-1 B-14 · regresión de producción: huecos de la TCA v2.

Antes (tag ``tl2-eng1-b14-pre``):
- sin ``signal_price`` el slippage medía tick -> fill y se grababa como si fuera
  decisión -> fill;
- ``expected_cost_bps`` valía siempre 0 en MT5;
- ``bid``/``ask`` eran los del tick de la señal, no los del envío;
- el paper grababa su slippage supuesto sin ``origin`` y entraba en el T12.
Ahora: nulo, nulo, tick del envío y ``origin='paper'`` excluido. El envío de
órdenes no cambia (mismo ``request``). Todo sintético.
"""

from __future__ import annotations

import sqlite3

import pytest
from test_mt5_tca import _broker  # noqa: E402  (mismo FakeMT5)

import tradinglab.tca as tca
from tradinglab.discovery import slippage_measured

TICKS = [{"bid": 100.00, "ask": 100.02}, {"bid": 100.05, "ask": 100.07}]


def test_con_signal_price_mide_y_el_envio_no_cambia(monkeypatch, tmp_path):
    captured: dict = {}
    broker = _broker(monkeypatch, tmp_path, ticks=list(TICKS), fill_price=100.12, captured=captured)
    broker.submit_market("XAUUSD", 0.01, bot="bot", dry_run=False, signal_price=100.00)
    assert captured["slippage_bps"] == pytest.approx(12.0)
    assert captured["bid"] == pytest.approx(100.05) and captured["ask"] == pytest.approx(100.07)
    assert captured["expected_cost_bps"] is None
    request = broker._test_fake.requests[-1]
    assert request["price"] == pytest.approx(100.07) and request["volume"] == pytest.approx(0.01)


def test_sin_signal_price_el_slippage_es_nulo(monkeypatch, tmp_path):
    captured: dict = {}
    broker = _broker(monkeypatch, tmp_path, ticks=list(TICKS), fill_price=100.12, captured=captured)
    broker.submit_market("XAUUSD", 0.01, bot="bot", dry_run=False)
    old = tca.slippage_bps(100.02, 100.12, "buy")  # lo que se grababa antes
    assert old == pytest.approx(9.998, abs=0.001)
    assert captured["slippage_bps"] is None
    assert captured["signal_px"] == pytest.approx(100.02)  # el tick sigue anotado


def test_paper_marca_origin_y_t12_lo_excluye(tmp_path):
    db = tmp_path / "lab.db"
    for origin in ("paper", "paper", "bot", None):
        tca.record_fill(
            db, bot="bot", symbol="XAUUSD", side="buy", signal_px=2000.0,
            order_px=2000.0, fill_px=2000.5 if origin == "paper" else 2000.1,
            origin=origin,
        )
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM tca WHERE origin='paper'").fetchone()[0] == 2
    con.close()
    cells = slippage_measured.measure_slippage(db)
    assert sum(cell.n for cell in cells) == 2
    assert all(cell.median_price == pytest.approx(0.1) for cell in cells)


def test_paper_graba_origin_paper(tmp_path):
    from tradinglab.db import init_db
    from tradinglab.execution.paper import PaperBroker

    db = tmp_path / "lab.db"
    init_db(db)
    PaperBroker(db, starting_cash=10_000, slippage_bps=5).submit_market("SPY", 1, 100.0, bot="b")
    con = sqlite3.connect(db)
    row = con.execute("SELECT origin, slippage_bps FROM tca").fetchone()
    con.close()
    assert row[0] == "paper"  # antes NULL
    assert row[1] == pytest.approx(5.0)  # el supuesto, sin cambios
