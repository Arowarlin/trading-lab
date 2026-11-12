from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradinglab.ai_setups import ALLOWED, allowed_timeframe, plan, validate
from tradinglab.ai_trader import (
    AiTraderError,
    _cell_status,
    _cost_ratio,
    _lane_pnl_today,
    _pause_cells,
    _volume_for_risk,
    load_config,
    resume_cell,
)
from tradinglab.db import connect, init_db


def snap(symbol: str = "XAUUSD", **over) -> dict:
    base = {
        "symbol": symbol,
        "price": 100.0,
        "spread": 0.05,
        "is_index": symbol.upper().startswith("US100"),
        "m15": {"atr": 1.0, "ema9": 100, "ema21": 100, "ema50": 100, "vwap": 100,
                "vwap_sigma": 1.0, "orb_high": 101, "orb_low": 99, "orb_valid": True, "close": 100},
        "h1": {"atr": 1.0, "ema9": 101, "ema21": 100, "ema50": 99, "bb_upper": 101,
               "bb_mid": 100, "bb_lower": 99, "bb_width": 0.02, "bb_squeeze": True,
               "asian_high": 101, "asian_low": 99, "asian_valid": True,
               "prev_high": 102, "prev_low": 98, "prev_mid": 97, "sweep_high": True,
               "sweep_low": False, "open": 99, "high": 101, "low": 98, "close": 100},
        "d1": {"atr": 2.0, "sma5": 97, "sma20": 100, "sma200": 90, "rsi2": 5,
               "dc20_high": 101, "dc20_low": 99, "dc55_high": 101, "dc55_low": 99,
               "prev_high": 102, "prev_low": 98, "prev_close": 100,
               "mother_high": 101, "mother_low": 99, "inside_bar": True},
    }
    for section, values in over.items():
        if isinstance(values, dict):
            base[section] = {**base[section], **values}
        else:
            base[section] = values
    return base


def test_asignacion_por_activo():
    assert allowed_timeframe("XAUUSD", "liquidity_sweep") == "H1"
    assert allowed_timeframe("XAUUSD", "orb_ny") is None
    assert allowed_timeframe("US100.CASH", "donchian_turtle") == "D1"
    assert set(ALLOWED) == {"US100.CASH", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}


def test_cada_estrategia_genera_niveles_validos():
    # orb_ny
    s = snap("US100.CASH", price=102.0)
    lv = plan("orb_ny", "buy", s)
    assert lv.sl == pytest.approx(99.0) and lv.tp == pytest.approx(108.0)
    # vwap_reversion
    s = snap("US100.CASH", price=97.0)
    lv = plan("vwap_reversion", "buy", s)
    assert lv.sl == pytest.approx(96.0) and lv.tp == pytest.approx(100.0)
    # bollinger_squeeze
    s = snap("US100.CASH", price=102.0, h1={"close": 102.0})
    lv = plan("bollinger_squeeze", "buy", s)
    assert lv.sl == pytest.approx(100.0) and lv.tp == pytest.approx(106.0)
    # liquidity_sweep
    s = snap("XAUUSD", price=100.0)
    lv = plan("liquidity_sweep", "sell", s)
    assert lv.sl == pytest.approx(101.0) and lv.tp == pytest.approx(98.0)
    # london_breakout
    s = snap("EURUSD", price=102.0)
    lv = plan("london_breakout", "buy", s)
    assert lv.sl == pytest.approx(100.0) and lv.tp == pytest.approx(105.0)
    # ema_pullback
    s = snap("EURUSD", price=100.5, h1={"close": 100.5})
    lv = plan("ema_pullback", "buy", s)
    assert lv.sl == pytest.approx(98.0)
    # rsi2_connors
    s = snap("US100.CASH", price=95.0)
    lv = plan("rsi2_connors", "buy", s)
    assert lv.sl == pytest.approx(91.0) and lv.tp == pytest.approx(97.0)
    # donchian_turtle
    s = snap("XAUUSD", price=103.0)
    lv = plan("donchian_turtle", "buy", s)
    assert lv.sl == pytest.approx(99.0) and lv.tp is None
    # inside_bar
    s = snap("XAUUSD", price=102.0)
    lv = plan("inside_bar", "buy", s)
    assert lv.sl == pytest.approx(99.0) and lv.tp == pytest.approx(108.0)


def test_validaciones_rechazan_fuera_de_regla():
    assert validate("orb_ny", "buy", snap("US100.CASH", price=100.0))[0] is False
    assert validate("ema_pullback", "buy", snap("EURUSD", h1={"ema9": 99}))[0] is False
    assert validate("rsi2_connors", "sell", snap("US100.CASH", price=95.0))[0] is False
    assert validate("inside_bar", "buy", snap("XAUUSD", d1={"inside_bar": False}))[0] is False
    assert validate("vwap_reversion", "buy", snap("US100.CASH", price=100.0))[0] is False


class _Inst:
    quote_ccy = "USD"

    def risk_per_lot(self, stop_distance, price=None, quote_rate=None):
        return float(stop_distance)


class _Spec:
    volume_step = 0.01
    volume_min = 0.01
    volume_max = 1000.0


class _Broker:
    def instrument(self, symbol):
        return _Inst()

    def symbol_spec(self, symbol):
        return {"volume_step": 0.01, "volume_min": 0.01, "volume_max": 1000.0}


def test_lote_por_riesgo_misma_perdida_con_stop_corto_y_largo():
    broker = _Broker()
    lots_short, risk_short, _ = _volume_for_risk(broker, "XAUUSD", 1.0, 500.0)
    lots_long, risk_long, _ = _volume_for_risk(broker, "XAUUSD", 10.0, 500.0)
    assert lots_short == pytest.approx(500.0)
    assert lots_long == pytest.approx(50.0)
    assert risk_short == pytest.approx(500.0)
    assert risk_long == pytest.approx(500.0)


def test_lote_rechaza_si_el_minimo_arriesga_mas():
    broker = _Broker()
    with pytest.raises(AiTraderError, match="mínimo"):
        _volume_for_risk(broker, "XAUUSD", 100_000.0, 500.0)


def test_filtro_coste_r():
    # US100: comisión 0, spread 2, slippage 1 bps, stop 100 -> 0,04
    assert _cost_ratio("US100.CASH", 20_000.0, 2.0, 100.0) == pytest.approx(0.04)
    # stop 10 -> 0,4 > 0,10
    assert _cost_ratio("US100.CASH", 20_000.0, 2.0, 10.0) > 0.10


def test_stop_diario_y_pausa_de_celda(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    now = datetime.now(timezone.utc).isoformat()
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, status, magic, risk_usd, pnl, exit_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("p1", now, "scalping", "XAUUSD", "liquidity_sweep", "sell", "closed",
             20261191, 500, -2001, now),
        )
    cfg = load_config()
    assert cfg["daily_stop"] == pytest.approx(0.03)
    assert cfg["styles"]["scalping"]["risk_per_trade"] == pytest.approx(0.0025)
    assert cfg["styles"]["scalping"]["max_trades_per_day"] == 15
    assert cfg["styles"]["intraday"]["max_trades_per_day"] == 3
    assert cfg["global"]["max_open_total"] == 5
    assert _lane_pnl_today(db, 20261191) == pytest.approx(-2001)
    assert _lane_pnl_today(db, 20261191) <= -100_000 * cfg["styles"]["scalping"]["daily_stop"]

    _pause_cells([{"strategy": "x", "symbol": "y", "timeframe": "H1", "n": 30,
                   "expectancy_r": 0.1, "shadow_expectancy_r": 0.2}], db)
    assert _cell_status(db, "x", "y", "H1") == "paused"
    resume_cell("x", "y", "H1", db_path=db)
    assert _cell_status(db, "x", "y", "H1") == "active"


def test_config_rechaza_live(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "account: live\nmagic: 1\nuniverse: [XAUUSD]\nrisk_per_trade: 0.005\n"
        "max_trades_per_day: 6\nmax_open_per_symbol: 1\nmax_open_total: 3\n"
        "daily_stop: 0.02\ntimeframes: [H1]\nplaybook_version: 1\nenabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(AiTraderError, match="ftmo_demo"):
        load_config(path)
