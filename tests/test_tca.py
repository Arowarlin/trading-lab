from __future__ import annotations

import pytest

from tradinglab.db import init_db
from tradinglab.tca import (
    build_tca,
    classify,
    ewma_last,
    record_fill,
    slippage_bps,
)


def _fill(db, *, bot="bot-a", symbol="SPY", slip=3.0, cost=4.0, side="buy"):
    return record_fill(
        db,
        bot=bot,
        account="paper_main",
        symbol=symbol,
        side=side,
        signal_px=100.0,
        order_px=100.0,
        fill_px=100.0,
        slippage_bps=slip,
        latency_ms=120.0,
        expected_cost_bps=6.0,
        realized_cost_bps=cost,
    )


def test_ewma_da_mas_peso_a_lo_reciente():
    assert ewma_last([0.0] * 10 + [10.0]) > ewma_last([0.0] * 11)
    assert ewma_last([10.0] * 10 + [0.0]) < ewma_last([10.0] * 11)
    assert ewma_last([]) is None


def test_slippage_con_signo_de_la_operacion():
    assert slippage_bps(100.0, 100.1, "buy") == pytest.approx(10.0)
    assert slippage_bps(100.0, 99.9, "sell") == pytest.approx(10.0)


@pytest.mark.parametrize(
    ("side", "signal_px", "fill_px", "expected_bps"),
    [
        ("buy", 100.0, 100.10, 10.0),  # adverso: compró más caro
        ("buy", 100.0, 99.90, -10.0),  # favorable: compró más barato
        ("buy", 100.0, 100.00, 0.0),  # sin deslizamiento
        ("sell", 100.0, 99.90, 10.0),  # adverso: vendió más barato
        ("sell", 100.0, 100.10, -10.0),  # favorable: vendió más caro
        ("sell", 100.0, 100.00, 0.0),  # sin deslizamiento
    ],
)
def test_slippage_adverso_positivo_negativo_y_cero(side, signal_px, fill_px, expected_bps):
    assert slippage_bps(signal_px, fill_px, side) == pytest.approx(expected_bps)


def test_slippage_sin_precios_devuelve_none():
    assert slippage_bps(None, 100.0, "buy") is None
    assert slippage_bps(100.0, None, "buy") is None
    assert slippage_bps(0.0, 100.0, "buy") is None


def test_estados_con_los_umbrales_de_drift():
    assert classify(2, 3.0, 4.0, expected_bps=6.0)[0] == "sin datos"
    assert classify(5, 3.0, 4.0, expected_bps=2.0)[0] == "ok"
    assert classify(5, 8.0, 9.0, expected_bps=2.0)[0] == "vigilar"
    assert classify(5, 12.0, 13.0, expected_bps=2.0)[0] == "deriva"
    assert classify(5, 2.0, 40.0, expected_bps=2.0)[0] == "deriva"


def test_sin_datos_con_menos_de_cinco_fills(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for _ in range(3):
        _fill(db)
    state = build_tca(db, alert=False)
    assert state["rows"][0]["status"] == "sin datos"


def test_tca_calcula_ewma_y_estado(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    for _ in range(6):
        _fill(db, slip=12.0, cost=13.0)
    state = build_tca(db, alert=False)
    row = state["rows"][0]
    assert row["fills"] == 6
    assert row["slippage_ewma_bps"] == pytest.approx(12.0)
    assert row["status"] == "deriva"
    assert row["median_latency_ms"] == pytest.approx(120.0)


def test_la_alerta_solo_cuando_pasa_a_deriva(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    enviados: list[str] = []

    import tradinglab.alerts as alerts_mod

    monkeypatch.setattr(
        alerts_mod, "send", lambda event, message, **kwargs: enviados.append(event)
    )
    for _ in range(6):
        _fill(db, slip=12.0, cost=13.0)
    build_tca(db, alert=True)
    build_tca(db, alert=True)
    assert enviados.count("tca_drift") == 1
