from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradinglab.ai_setups import plan, supports, validate
from tradinglab.ai_trader import (
    AiTraderError,
    _cost_ratio,
    _validate_payload,
    _volume_for_risk,
    daily_stop_check,
    daily_stop_state,
    lane_magic_map,
    load_config,
    propose,
    session_open,
    skip,
)
from tradinglab.db import connect, init_db


def _loss(db: Path, magic: int, style: str, pnl: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades"
            "(proposal_id, ts, style, symbol, setup, side, status, magic, risk_usd, "
            " pnl, exit_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (f"loss-{magic}-{pnl}", now, style, "XAUUSD", "liquidity_sweep",
             "sell", "closed", magic, 500, pnl, now),
        )


class _Inst:
    quote_ccy = "USD"

    def risk_per_lot(self, stop_distance, price=None, quote_rate=None):
        return float(stop_distance)


class _Broker:
    def instrument(self, symbol):
        return _Inst()

    def symbol_spec(self, symbol):
        return {"volume_step": 0.01, "volume_min": 0.01, "volume_max": 1000.0}


class _StopBroker:
    def health(self):
        return {"mode": "demo", "equity": 100_000.0}

    def positions(self):
        return []


def test_config_tres_estilos_y_global():
    cfg = load_config()
    assert set(cfg["styles"]) == {"scalping", "intraday", "swing"}
    assert cfg["magics"] == [20261191, 20261192, 20261193]
    assert cfg["global"]["daily_stop"] == pytest.approx(0.03)
    assert cfg["global"]["max_open_total"] == 5
    assert cfg["global"]["max_open_per_symbol_per_style"] == 1
    assert cfg["styles"]["scalping"]["timeframes"] == ["M1", "M5"]
    assert cfg["styles"]["scalping"]["risk_per_trade"] == pytest.approx(0.0025)
    assert cfg["styles"]["scalping"]["daily_stop"] == pytest.approx(0.01)
    assert cfg["styles"]["scalping"]["max_trades_per_day"] == 15
    assert cfg["styles"]["scalping"]["max_cost_r"] == pytest.approx(0.15)
    assert cfg["styles"]["scalping"]["slippage_points"] == pytest.approx(1.0)
    assert cfg["styles"]["scalping"]["universe"] == ["US100.cash", "XAUUSD"]
    assert cfg["styles"]["intraday"]["timeframes"] == ["M15", "H1"]
    assert cfg["styles"]["intraday"]["max_cost_r"] == pytest.approx(0.10)
    assert cfg["styles"]["intraday"]["universe"] == cfg["universe"]
    assert cfg["styles"]["swing"]["timeframes"] == ["H4", "D1"]
    assert cfg["styles"]["swing"]["max_open_risk"] == pytest.approx(0.02)
    assert cfg["styles"]["swing"]["max_cost_r"] is None
    assert cfg["styles"]["swing"]["max_trades_per_day"] is None


def test_magics_separados_por_estilo_y_journal():
    from tradinglab.journal import _lab_magics

    cfg = load_config()
    mapping = lane_magic_map(cfg)
    assert mapping == {
        20261191: "ai:scalping",
        20261192: "ai:intraday",
        20261193: "ai:swing",
    }
    magics = _lab_magics()
    assert {20261191, 20261192, 20261193} <= magics
    assert {20261151, 20261152, 20261153} <= magics


def test_stops_por_estilo_y_global(tmp_path):
    db = tmp_path / "lab.db"
    cfg = load_config()
    _loss(db, 20261191, "scalping", -1000)
    _loss(db, 20261192, "intraday", -500)
    state = daily_stop_state(db, cfg, equity=100_000)
    assert state["styles"]["scalping"]["hit"] is True
    assert state["styles"]["intraday"]["hit"] is False
    assert state["styles"]["swing"]["hit"] is False
    assert state["global"]["hit"] is False
    assert state["global"]["pnl"] == pytest.approx(-1500)

    _loss(db, 20261193, "swing", -2500)
    state = daily_stop_state(db, cfg, equity=100_000)
    assert state["global"]["hit"] is True
    assert state["global"]["pnl"] == pytest.approx(-4000)


def test_propose_para_por_stop_de_estilo(tmp_path):
    db = tmp_path / "lab.db"
    _loss(db, 20261192, "intraday", -1000)
    payload = {
        "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
        "timeframe": "H1", "side": "sell", "thesis": "prueba", "confidence": 3,
    }
    with pytest.raises(AiTraderError, match="stop diario del estilo"):
        propose(payload, broker=_StopBroker(), db_path=db)
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip"
    assert "stop diario" in row["reason"]


def test_propose_para_por_stop_global(tmp_path):
    db = tmp_path / "lab.db"
    for magic, style in ((20261191, "scalping"), (20261192, "intraday"),
                         (20261193, "swing")):
        _loss(db, magic, style, -1000)
    payload = {
        "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
        "timeframe": "H1", "side": "sell", "thesis": "prueba", "confidence": 3,
    }
    with pytest.raises(AiTraderError, match="stop diario global"):
        propose(payload, broker=_StopBroker(), db_path=db)


def test_daily_stop_check_igualdad_no_avisa_y_suma_mayor_si():
    cfg = load_config()
    check = daily_stop_check(cfg)
    assert check["warn"] is False and check["sum"] == pytest.approx(0.03)
    altered = copy.deepcopy(cfg)
    for style in altered["styles"].values():
        style["daily_stop"] = 0.02
    check = daily_stop_check(altered)
    assert check["warn"] is True
    assert "0.06" in check["detail"] or "6.00%" in check["detail"]


def test_ventana_scalping_ny():
    cfg = load_config()
    style = cfg["styles"]["scalping"]
    assert session_open(style, datetime(2026, 11, 12, 14, 30, tzinfo=timezone.utc)) is True
    assert session_open(style, datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc)) is False
    assert session_open(style, datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)) is False
    assert session_open(cfg["styles"]["intraday"]) is None


def test_misma_perdida_en_dinero_con_stop_corto_y_largo():
    broker = _Broker()
    short, risk_short, _ = _volume_for_risk(broker, "XAUUSD", 2.0, 250.0)
    long, risk_long, _ = _volume_for_risk(broker, "XAUUSD", 20.0, 250.0)
    assert short == pytest.approx(125.0)
    assert long == pytest.approx(12.5)
    assert risk_short == pytest.approx(250.0)
    assert risk_long == pytest.approx(250.0)


def test_lote_bajo_minimo_se_rechaza_y_maximo_se_respeta():
    broker = _Broker()
    with pytest.raises(AiTraderError, match="mínimo"):
        _volume_for_risk(broker, "XAUUSD", 100_000.0, 250.0)
    lots, risk, _ = _volume_for_risk(broker, "XAUUSD", 1.0, 10_000.0)
    assert lots == pytest.approx(1000.0)
    assert risk == pytest.approx(1000.0)


def test_coste_r_spread_comision_y_slippage():
    # compatibilidad con el supuesto antiguo de 1 bp por lado
    assert _cost_ratio("US100.CASH", 20_000.0, 2.0, 100.0) == pytest.approx(0.04)
    # 1 punto de US100 (0,01) por lado: (2 + 0,01) / 100
    assert _cost_ratio(
        "US100.CASH", 20_000.0, 2.0, 100.0, slippage_points=1.0, point=0.01
    ) == pytest.approx(0.0201)
    # XAUUSD: comisión 0,0007% por lado + spread + 1 punto
    ratio = _cost_ratio(
        "XAUUSD", 4000.0, 0.30, 2.0, slippage_points=1.0, point=0.01
    )
    assert ratio == pytest.approx((0.30 + 4000 * 0.0007 / 100 + 0.01) / 2.0)


def test_payload_valida_estilo_timeframe_y_estrategia():
    cfg = load_config()
    item = _validate_payload({
        "style": "scalping", "symbol": "US100.cash", "strategy": "orb_ny",
        "timeframe": "M5", "side": "buy", "thesis": "ruptura", "confidence": 4,
    }, cfg)
    assert item["symbol"] == "US100.cash"
    assert item["style"] == "scalping"
    with pytest.raises(AiTraderError, match="estrategia desconocida"):
        _validate_payload({
            "style": "scalping", "symbol": "US100.cash", "strategy": "no_existe",
            "timeframe": "M5", "side": "buy", "thesis": "x", "confidence": 3,
        }, cfg)
    with pytest.raises(AiTraderError, match="timeframe no permitido"):
        _validate_payload({
            "style": "scalping", "symbol": "US100.cash", "strategy": "bollinger_squeeze",
            "timeframe": "H1", "side": "buy", "thesis": "x", "confidence": 3,
        }, cfg)
    with pytest.raises(AiTraderError, match="universo de scalping"):
        _validate_payload({
            "style": "scalping", "symbol": "EURUSD", "strategy": "ema_pullback",
            "timeframe": "M5", "side": "buy", "thesis": "x", "confidence": 3,
        }, cfg)
    inferred = _validate_payload({
        "symbol": "US100.cash", "strategy": "orb_ny", "timeframe": "M15",
        "side": "buy", "thesis": "x", "confidence": 3,
    }, cfg)
    assert inferred["style"] == "intraday"


def test_estrategias_soportan_sus_timeframes():
    assert supports("orb_ny", "M5") is True
    assert supports("orb_ny", "D1") is False
    assert supports("bollinger_squeeze", "H4") is True
    assert supports("inside_bar", "H4") is True
    snap = {
        "symbol": "XAUUSD", "price": 102.0, "spread": 0.05, "is_index": False,
        "h4": {
            "atr": 1.0, "ema9": 100, "ema21": 100, "ema50": 100,
            "bb_upper": 101, "bb_mid": 100, "bb_lower": 99, "bb_width": 0.02,
            "bb_squeeze": True, "vwap": 100, "vwap_sigma": 1.0,
            "orb_high": 101, "orb_low": 99, "orb_valid": True,
            "asian_high": 101, "asian_low": 99, "asian_valid": True,
            "prev_high": 102, "prev_low": 98, "prev_mid": 97,
            "sweep_high": True, "sweep_low": False,
            "open": 99, "high": 101, "low": 98, "close": 100,
            "mother_high": 101, "mother_low": 99, "inside_bar": True,
        },
        "d1": {"atr": 2.0, "sma5": 97, "sma20": 100, "sma200": 90, "rsi2": 5,
               "dc20_high": 101, "dc20_low": 99, "dc55_high": 101, "dc55_low": 99,
               "prev_high": 102, "prev_low": 98, "prev_mid": 97,
               "prev_close": 100, "mother_high": 101, "mother_low": 99,
               "inside_bar": True},
    }
    ok, reason = validate("inside_bar", "buy", snap, "H4")
    assert ok is True, reason
    level = plan("inside_bar", "buy", snap, "H4")
    assert level.timeframe == "H4"
    assert level.sl == pytest.approx(99.0)


def test_skip_registra_decision_y_auditoria(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    result = skip({
        "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
        "timeframe": "H1", "reason": "sin barrido del día anterior",
        "confidence": 2, "snapshot": {"spread": 0.2},
    }, db_path=db)
    with connect(db) as con:
        row = dict(con.execute(
            "SELECT * FROM ai_decisions WHERE id=?", (result["id"],)
        ).fetchone())
        audit = con.execute(
            "SELECT action, result FROM console_actions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip"
    assert row["style"] == "intraday"
    assert row["setup_valid"] == 0
    assert row["reason"] == "sin barrido del día anterior"
    assert json.loads(row["snapshot"]) == {"spread": 0.2}
    assert row["playbook_version"] == 1
    assert row["source"] == "forward"
    assert audit["action"] == "ai_trader_skip" and audit["result"] == "skip"

    with pytest.raises(AiTraderError, match="200"):
        skip({
            "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
            "timeframe": "H1", "reason": "x" * 201, "confidence": 2,
        }, db_path=db)


def test_propose_no_setup_registra_decision(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    snap = {
        "symbol": "XAUUSD", "price": 100.0, "spread": 0.2, "is_index": False,
        "h1": {"sweep_high": False, "sweep_low": False,
               "prev_mid": 100.0, "high": 101.0, "low": 99.0},
    }
    monkeypatch.setattr(
        "tradinglab.ai_trader.snapshot_symbol", lambda *args, **kwargs: snap
    )
    payload = {
        "style": "intraday", "strategy": "liquidity_sweep", "symbol": "XAUUSD",
        "timeframe": "H1", "side": "sell", "thesis": "prueba", "confidence": 3,
    }
    with pytest.raises(AiTraderError, match="setup no válido"):
        propose(payload, broker=_StopBroker(), db_path=db)
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, setup_valid, snapshot FROM ai_decisions "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "no_setup"
    assert row["setup_valid"] == 0
    assert json.loads(row["snapshot"])["symbol"] == "XAUUSD"


def test_migracion_aditiva_de_columnas(tmp_path):
    db = tmp_path / "lab.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE ai_trades ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT UNIQUE, "
            "ts TEXT NOT NULL, symbol TEXT NOT NULL, setup TEXT NOT NULL, "
            "side TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed', "
            "magic INTEGER, pnl REAL)"
        )
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, symbol, setup, side, magic, pnl) "
            "VALUES('old', '2026-11-01T00:00:00+00:00', 'XAUUSD', 'liquidity_sweep', "
            "'sell', 20261192, -10)"
        )
    init_db(db)
    with connect(db) as con:
        columns = {row["name"] for row in con.execute("PRAGMA table_info(ai_trades)")}
        decisions = {
            row["name"] for row in con.execute("PRAGMA table_info(ai_decisions)")
        }
        old = con.execute("SELECT proposal_id, pnl FROM ai_trades").fetchone()
    assert {"style", "result_r", "timeframe", "cost_ratio"} <= columns
    assert {
        "decision_date", "session", "style", "symbol", "timeframe", "strategy",
        "setup_valid", "decision", "reason", "confidence", "snapshot",
        "playbook_version", "source", "plan_id",
    } <= decisions
    assert old["proposal_id"] == "old" and old["pnl"] == pytest.approx(-10)
