"""Regresión de producción · TCA de MT5 separa señal, envío y fill.

El comportamiento anterior registraba `signal_px == order_px == price` (el
tick de la petición) y, si el bróker devolvía 0, sustituía el fill por ese
mismo precio. Estos tests fijan el comportamiento nuevo y dejan explícito el
valor que producía el anterior.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import tradinglab.tca as tca
from tradinglab.execution.mt5 import MT5Broker


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_INVALID_FILL = 10030
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_FOK = 2
    ORDER_FILLING_RETURN = 3

    def __init__(self, fill_price: float) -> None:
        self.fill_price = fill_price

    def order_send(self, request):
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            price=self.fill_price,
            order=123,
            deal=456,
            comment="ok",
        )


def _broker(monkeypatch, tmp_path, *, ticks, fill_price, captured):
    def fake_record(db_path, **kwargs):
        captured.update(kwargs)
        return 1

    monkeypatch.setattr(tca, "record_fill", fake_record)
    broker = MT5Broker(
        path="fake",
        login=1,
        server="Fake",
        dry_run=False,
        db_path=tmp_path / "lab.db",
    )
    fake = FakeMT5(fill_price)
    monkeypatch.setattr(broker, "_require", lambda: fake)
    monkeypatch.setattr(broker, "_assert_can_trade", lambda mt5: None)
    monkeypatch.setattr(broker, "_require_identity", lambda: None)
    monkeypatch.setattr(
        broker,
        "symbol_spec",
        lambda symbol: {
            "symbol": "XAUUSD",
            "digits": 2,
            "point": 0.01,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "filling_mode": 1,
            "stops_level": 0,
        },
    )
    iterator = iter(ticks)
    monkeypatch.setattr(broker, "tick", lambda symbol: next(iterator))
    monkeypatch.setattr(broker, "_record", lambda **kwargs: {"ok": True})
    return broker


def test_separa_senal_envio_y_fill_frente_al_registro_antiguo(monkeypatch, tmp_path):
    captured: dict = {}
    broker = _broker(
        monkeypatch,
        tmp_path,
        ticks=[
            {"bid": 100.00, "ask": 100.02},  # instante de la señal
            {"bid": 100.05, "ask": 100.07},  # instante de order_send
        ],
        fill_price=100.12,
        captured=captured,
    )

    result = broker.submit_market("XAUUSD", 0.01, bot="bot", dry_run=False)

    # Nuevo: tres precios distintos.
    assert result["ok"] is True
    assert captured["signal_px"] == pytest.approx(100.02)
    assert captured["order_px"] == pytest.approx(100.07)
    assert captured["fill_px"] == pytest.approx(100.12)
    assert captured["requested_price"] == pytest.approx(100.07)
    assert captured["slippage_bps"] == pytest.approx(9.998, abs=0.001)

    # Antiguo: señal y envío compartían el tick de la petición.
    old_signal_px = old_order_px = 100.02
    old_fill_px = 100.12
    old_slippage_bps = 9.998
    assert old_signal_px == pytest.approx(captured["signal_px"])
    assert old_order_px != pytest.approx(captured["order_px"])
    assert old_fill_px == pytest.approx(captured["fill_px"])
    assert old_slippage_bps == pytest.approx(captured["slippage_bps"], abs=0.001)


def test_fill_cero_no_se_sustituye_por_el_precio_pedido(monkeypatch, tmp_path):
    captured: dict = {}
    broker = _broker(
        monkeypatch,
        tmp_path,
        ticks=[
            {"bid": 100.00, "ask": 100.02},
            {"bid": 100.05, "ask": 100.07},
        ],
        fill_price=0.0,
        captured=captured,
    )

    broker.submit_market("XAUUSD", 0.01, bot="bot", dry_run=False)

    assert captured["fill_px"] is None
    assert captured["slippage_bps"] is None
    assert captured["realized_cost_bps"] is None
    # Antiguo: `result.price or price` convertía el 0 en 100.02 y slippage 0.
    old_fill_px = 100.02
    assert old_fill_px != captured["fill_px"]


def test_signal_price_del_webhook_manda_sobre_el_tick_de_entrada(monkeypatch, tmp_path):
    captured: dict = {}
    broker = _broker(
        monkeypatch,
        tmp_path,
        ticks=[
            {"bid": 100.00, "ask": 100.02},
            {"bid": 100.05, "ask": 100.07},
        ],
        fill_price=100.12,
        captured=captured,
    )

    broker.submit_market(
        "XAUUSD",
        0.01,
        bot="bot",
        dry_run=False,
        signal_price=99.90,
    )

    assert captured["signal_px"] == pytest.approx(99.90)
    assert captured["order_px"] == pytest.approx(100.07)
    assert captured["fill_px"] == pytest.approx(100.12)
    assert captured["slippage_bps"] == pytest.approx(22.022, abs=0.001)


@pytest.mark.parametrize(
    ("side", "signal_px", "fill_px", "expected_bps"),
    [
        ("buy", 100.00, 100.10, 10.0),   # adverso
        ("buy", 100.00, 99.90, -10.0),  # favorable
        ("buy", 100.00, 100.00, 0.0),   # cero
        ("sell", 100.00, 99.90, 10.0),  # adverso
        ("sell", 100.00, 100.10, -10.0),  # favorable
        ("sell", 100.00, 100.00, 0.0),  # cero
    ],
)
def test_firmas_de_slippage_en_el_registro(
    monkeypatch, tmp_path, side, signal_px, fill_px, expected_bps
):
    captured: dict = {}
    volume = 0.01 if side == "buy" else -0.01
    broker = _broker(
        monkeypatch,
        tmp_path,
        ticks=[
            {"bid": 100.00, "ask": 100.05},
            {"bid": 100.00, "ask": 100.05},
        ],
        fill_price=fill_px,
        captured=captured,
    )

    broker.submit_market(
        "XAUUSD",
        volume,
        bot="bot",
        dry_run=False,
        signal_price=signal_px,
    )

    assert captured["signal_px"] == pytest.approx(signal_px)
    assert captured["fill_px"] == pytest.approx(fill_px)
    assert captured["slippage_bps"] == pytest.approx(expected_bps)
