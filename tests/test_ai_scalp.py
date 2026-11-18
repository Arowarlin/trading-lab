from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.ai_setups import ALLOWED, allowed_timeframe, validate
from tradinglab.ai_setups import plan as setup_plan
from tradinglab.ai_trader import (
    AiTraderError,
    StaleDataError,
    _safe_rates,
    create_plan,
    execute,
    load_config,
    scalp,
)
from tradinglab.config import get_settings
from tradinglab.db import connect, init_db


def scalp_snap(symbol: str = "US100.CASH", **over) -> dict:
    base = {
        "symbol": symbol,
        "price": 100.0,
        "spread": 0.1,
        "now": "2026-11-12T15:00:00+00:00",  # 10:00 Nueva York
        "is_index": symbol.upper().startswith("US100"),
        "m1": {
            "atr": 1.0, "ema8": 101.0, "ema13": 100.0, "ema21": 99.0,
            "high": 102.0, "low": 99.0, "open": 100.0, "close": 101.5,
            "vwap": 100.0, "orb5_high": 101.0, "orb5_low": 99.0,
            "orb5_valid": True, "last_bar": "2026-11-12T14:59:00+00:00",
        },
        "m5": {
            "atr": 2.0, "vwap": 100.0, "high": 101.0, "low": 99.0,
            "open": 99.5, "close": 100.5,
            "orb5_high": 101.0, "orb5_low": 99.0, "orb5_valid": True,
            "last_bar": "2026-11-12T14:55:00+00:00",
        },
        "m15": {"ema9": 101.0, "ema21": 100.0, "ema50": 99.0},
        "d1": {"close": 100.0, "sma200": 90.0},
    }
    for section, values in over.items():
        if isinstance(values, dict) and section in base and isinstance(base[section], dict):
            base[section] = {**base[section], **values}
        else:
            base[section] = values
    return base


def test_asignacion_scalping():
    assert allowed_timeframe("US100.CASH", "orb_5m") == "M5"
    assert allowed_timeframe("US100.CASH", "ema_ribbon_pullback") == "M1"
    assert allowed_timeframe("XAUUSD", "vwap_bounce") == "M5"
    assert allowed_timeframe("XAUUSD", "momentum_burst") == "M1"
    assert allowed_timeframe("EURUSD", "orb_5m") is None
    assert "ema_ribbon_pullback" in ALLOWED["US100.CASH"]


def test_estrategias_scalping_generan_niveles():
    s = scalp_snap("US100.CASH", price=100.8)
    lv = setup_plan("ema_ribbon_pullback", "buy", s)
    assert lv.sl == pytest.approx(99.8)
    assert lv.tp == pytest.approx(102.3)

    s = scalp_snap("US100.CASH", price=100.5)
    lv = setup_plan("vwap_bounce", "buy", s)
    assert lv.sl == pytest.approx(98.5)
    assert lv.tp == pytest.approx(103.5)

    s = scalp_snap("US100.CASH", price=101.5)
    lv = setup_plan("orb_5m", "buy", s)
    assert lv.sl == pytest.approx(99.0)
    assert lv.tp == pytest.approx(105.25)

    s = scalp_snap("US100.CASH", price=101.5)
    lv = setup_plan("momentum_burst", "buy", s)
    assert lv.sl == pytest.approx(99.0)
    assert lv.tp == pytest.approx(104.0)


def test_estrategias_scalping_rechazan_fuera_de_regla():
    # EMA ribbon sin alineación.
    s = scalp_snap("US100.CASH", price=100.8, m1={"ema8": 99.0})
    assert validate("ema_ribbon_pullback", "buy", s)[0] is False
    # VWAP bounce contra la tendencia M15.
    s = scalp_snap("US100.CASH", price=100.5, m15={"ema9": 99.0})
    assert validate("vwap_bounce", "buy", s)[0] is False
    # ORB 5m con el precio dentro del rango.
    s = scalp_snap("US100.CASH", price=100.0)
    assert validate("orb_5m", "buy", s, "M5")[0] is False
    # Momentum sin rango >2 ATR.
    s = scalp_snap("US100.CASH", price=100.0, m1={"atr": 2.0})
    assert validate("momentum_burst", "buy", s)[0] is False


class _ScalpBroker:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def health(self):
        return {"mode": "demo", "equity": 100_000.0}

    def positions(self):
        return []

    def equity_series(self):
        return pd.Series([100_000.0])

    def shutdown(self):
        pass


def _window_now() -> datetime:
    # 15:00 UTC = 10:00 Nueva York en noviembre; en verano, 11:00.
    return datetime.now(timezone.utc).replace(
        hour=15, minute=0, second=0, microsecond=0
    )


def _plan(db, *, setups: list, bias: str = "long",
          forbidden: list | None = None, **extra) -> dict:
    cfg = load_config()
    settings = get_settings()
    return create_plan(
        {
            "symbol": extra.get("symbol", "US100.cash"),
            "setups": setups,
            "bias": bias,
            "forbidden_hours": forbidden or [],
            "reason": extra.get("reason", "plan de prueba"),
        },
        config=cfg,
        settings=settings,
        db_path=db,
    )


def _fresh_snap(now: datetime, *, stale_minutes: int = 0) -> dict:
    snap = scalp_snap("US100.CASH", price=101.5)
    snap["now"] = now.isoformat()
    snap["m5"]["last_bar"] = (
        now - timedelta(minutes=5 + stale_minutes)
    ).isoformat()
    return snap


def test_plan_valida_y_solo_deja_uno_activo(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    first = _plan(db, setups=["orb_5m", "vwap_bounce"])
    second = _plan(db, setups=["momentum_burst"])
    assert first["plan_id"] != second["plan_id"]
    with connect(db) as con:
        rows = con.execute(
            "SELECT plan_id, active FROM ai_plans WHERE symbol='US100.cash' "
            "AND session_date=? ORDER BY id",
            (first["session_date"],),
        ).fetchall()
    assert [(row["plan_id"], row["active"]) for row in rows] == [
        (first["plan_id"], 0),
        (second["plan_id"], 1),
    ]


def test_plan_rechaza_setup_bias_hora_y_motivo(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    cfg = load_config()
    settings = get_settings()
    base = {
        "symbol": "US100.cash", "setups": ["orb_5m"], "bias": "long",
        "forbidden_hours": [], "reason": "ok",
    }
    with pytest.raises(AiTraderError, match="no permitida"):
        create_plan({**base, "setups": ["orb_ny"]}, config=cfg, settings=settings, db_path=db)
    with pytest.raises(AiTraderError, match="bias"):
        create_plan({**base, "bias": "flat"}, config=cfg, settings=settings, db_path=db)
    with pytest.raises(AiTraderError, match="hora prohibida"):
        create_plan({**base, "forbidden_hours": ["25:00-26:00"]},
                    config=cfg, settings=settings, db_path=db)
    with pytest.raises(AiTraderError, match="motivo"):
        create_plan({**base, "reason": "x" * 301}, config=cfg, settings=settings, db_path=db)
    with connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM ai_plans").fetchone()[0] == 0


def test_sin_plan_no_opera(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    calls = []
    monkeypatch.setattr(
        "tradinglab.ai_trader.propose",
        lambda *args, **kwargs: calls.append(args) or {},
    )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=_window_now())
    assert result["status"] == "no_plan"
    assert calls == []


def test_scalp_solo_ejecuta_lo_que_el_plan_permite(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    plan = _plan(db, setups=["orb_5m"], bias="long")
    now = _window_now()
    snap = _fresh_snap(now)
    calls = []
    executed = []

    def fake_propose(payload, **kwargs):
        calls.append((payload, kwargs))
        return {"id": "p1", "snapshot": snap, "order": {"order_id": 7}}

    def fake_execute(proposal_id, **kwargs):
        executed.append(proposal_id)
        return {"order": {"order_id": 7}}

    monkeypatch.setattr("tradinglab.ai_trader.snapshot_symbol", lambda *a, **k: snap)
    monkeypatch.setattr("tradinglab.ai_trader.propose", fake_propose)
    monkeypatch.setattr("tradinglab.ai_trader.execute", fake_execute)
    result = scalp(broker=_ScalpBroker(), db_path=db, now=now)
    assert result["status"] == "ok"
    assert result["executed"] and result["executed"][0]["strategy"] == "orb_5m"
    assert executed == ["p1"]
    assert calls and calls[0][0]["side"] == "buy"
    assert calls[0][1]["plan_id"] == plan["plan_id"]
    assert calls[0][1]["defer_decision"] is True
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, plan_id, strategy FROM ai_decisions "
            "WHERE decision='take' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "take"
    assert row["plan_id"] == plan["plan_id"]
    assert row["strategy"] == "orb_5m"


def test_scalp_hora_prohibida_no_llama_a_propose(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    plan = _plan(db, setups=["orb_5m"], forbidden=["00:00-23:59"])
    calls = []
    monkeypatch.setattr(
        "tradinglab.ai_trader.propose",
        lambda *args, **kwargs: calls.append(args) or {},
    )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=_window_now())
    assert result["status"] == "ok" and result["executed"] == []
    assert calls == []
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason, plan_id FROM ai_decisions "
            "WHERE plan_id=? ORDER BY id DESC LIMIT 1", (plan["plan_id"],)
        ).fetchone()
    assert row["decision"] == "skip"
    assert "hora prohibida" in row["reason"]


def test_scalp_datos_obsoletos_no_opera(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    _plan(db, setups=["orb_5m"])
    now = _window_now()
    snap = _fresh_snap(now, stale_minutes=30)
    calls = []
    monkeypatch.setattr("tradinglab.ai_trader.snapshot_symbol", lambda *a, **k: snap)
    monkeypatch.setattr(
        "tradinglab.ai_trader.propose",
        lambda *args, **kwargs: calls.append(args) or {},
    )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=now)
    assert result["status"] == "ok" and result["executed"] == []
    assert calls == []
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip"
    assert "datos obsoletos" in row["reason"]


def test_scalp_limite_de_estilo_registra_skip(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    _plan(db, setups=["orb_5m"])
    now = _window_now()
    snap = _fresh_snap(now)
    monkeypatch.setattr("tradinglab.ai_trader.snapshot_symbol", lambda *a, **k: snap)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "status, magic, risk_usd, pnl, exit_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("loss-scalp", datetime.now(timezone.utc).isoformat(), "scalping",
             "US100.cash", "orb_5m", "buy", "closed", 20261191, 500, -1001,
             datetime.now(timezone.utc).isoformat()),
        )
    executed = []
    monkeypatch.setattr(
        "tradinglab.ai_trader.execute",
        lambda *args, **kwargs: executed.append(args) or {"order": {}},
    )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=now)
    assert result["status"] == "ok" and result["executed"] == []
    assert executed == []
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip"
    assert "stop diario del estilo" in row["reason"]


def test_scalp_mt5_caido_y_killswitch_registran(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    _plan(db, setups=["orb_5m"])
    now = _window_now()
    result = scalp(broker=None, db_path=db, now=now)
    assert result["status"] == "mt5_down"
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip" and "MT5 no responde" in row["reason"]

    with connect(db) as con:
        con.execute(
            "INSERT OR REPLACE INTO killswitch"
            "(id, active, reason, triggered_at, reset_at, equity, peak, day_start) "
            "VALUES(1, 1, 'prueba', ?, NULL, 100000, 100000, 100000)",
            (datetime.now(timezone.utc).isoformat(),),
        )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=now)
    assert result["status"] == "killswitch"
    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip" and "kill-switch" in row["reason"]


def test_scalp_fuera_de_ventana_no_hace_nada(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    outside = _window_now().replace(hour=23)
    result = scalp(broker=_ScalpBroker(), db_path=db, now=outside)
    assert result["status"] == "outside_window"


def test_safe_rates_closed_only_descarta_la_vela_en_formacion():
    class _Broker:
        def rates(self, symbol, timeframe, count):
            index = pd.date_range("2026-11-12T10:00:00Z", periods=3, freq="1min")
            return pd.DataFrame(
                {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                index=index,
            )

    frame = _safe_rates(
        _Broker(), "US100.cash", "M1", 10,
        now=datetime(2026, 11, 12, 10, 2, 30, tzinfo=timezone.utc),
        closed_only=True,
    )
    assert frame is not None
    assert frame.index[-1].minute == 1

def test_scalp_no_usa_plan_de_dia_anterior(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_plans(plan_id, ts, session_date, symbol, setups, "
            "bias, forbidden_hours, reason, playbook_version, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "old-plan", "2026-01-01T00:00:00+00:00", "2026-01-01",
                "US100.cash", '[{"strategy":"orb_5m","timeframe":"M5"}]',
                "long", "[]", "plan viejo", 1, 1, "2026-01-01T00:00:00+00:00",
            ),
        )
    result = scalp(broker=_ScalpBroker(), db_path=db, now=_window_now())
    assert result["status"] == "no_plan"

def test_sesion_ny_crea_el_plan_del_dia():
    script = Path(__file__).resolve().parents[1] / "scripts" / "ai_trader_session.ps1"
    text = script.read_text(encoding="utf-8")
    assert "ai-trader plans" in text
    assert "ai-trader plan --json-file" in text
    assert "US100.cash" in text and "XAUUSD" in text



class _StaleBroker:
    def health(self):
        return {"mode": "demo", "equity": 100_000.0}

    def rates(self, symbol, timeframe, count):
        idx = pd.date_range("2026-11-10 10:00", periods=100, freq="5min", tz="UTC")
        close = [100.0] * len(idx)
        return pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close},
            index=idx,
        )

    def tick(self, symbol):
        raise AssertionError("no debe pedir tick si los datos son viejos")

    def submit_market(self, *args, **kwargs):
        raise AssertionError("no debe enviar orden con datos viejos")


def test_execute_bloquea_datos_obsoletos_en_cualquier_familia(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, symbol, setup, side, thesis, "
            "confidence, playbook_version, entry, sl, tp, volume, risk_usd, magic, "
            "status, style, timeframe, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "p-stale",
                "2026-11-16T15:00:00+00:00",
                "US100.cash",
                "orb_5m",
                "buy",
                "prueba",
                3,
                1,
                101.0,
                99.0,
                105.0,
                1.0,
                100.0,
                20261191,
                "proposed",
                "scalping",
                "M5",
                "2026-11-16T15:00:00+00:00",
                "2026-11-16T15:00:00+00:00",
            ),
        )
    alerts = []
    monkeypatch.setattr(
        "tradinglab.ai_trader._alert_stale",
        lambda *args, **kwargs: alerts.append(args),
    )

    with pytest.raises(StaleDataError, match="datos obsoletos"):
        execute("p-stale", broker=_StaleBroker(), db_path=db)

    with connect(db) as con:
        row = con.execute(
            "SELECT decision, reason FROM ai_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["decision"] == "skip"
    assert "datos obsoletos" in row["reason"]
    assert alerts and alerts[0][1] == "scalping"


class _DealsBroker:
    def __init__(self, deals):
        self.deals = deals

    def positions(self):
        return []

    def history_deals(self, start, end):
        return list(self.deals)


def _open_sync_trade(db, ticket=777):
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "timeframe, status, magic, ticket, risk_usd) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("p-sync", "2026-11-17T14:00:00+00:00", "scalping", "XAUUSD",
             "vwap_bounce", "sell", "M5", "open", 20261191, ticket, 100.0),
        )


def test_sync_closed_no_cierra_sin_deal_de_salida(tmp_path):
    from tradinglab.ai_trader import sync_closed

    db = tmp_path / "lab.db"
    _open_sync_trade(db)
    entry = {
        "position_id": 777, "magic": 20261191, "entry": 0, "profit": 0.0,
        "price": 100.0, "ts_utc": "2026-11-17T14:00:01+00:00",
        "swap": 0.0, "commission": 0.0,
    }
    assert sync_closed(_DealsBroker([entry]), db_path=db) == 0
    with connect(db) as con:
        row = con.execute(
            "SELECT status FROM ai_trades WHERE proposal_id='p-sync'"
        ).fetchone()
    assert row["status"] == "open"


def test_sync_closed_usa_el_deal_de_salida(tmp_path):
    from tradinglab.ai_trader import sync_closed

    db = tmp_path / "lab.db"
    _open_sync_trade(db)
    entry = {
        "position_id": 777, "magic": 20261191, "entry": 0, "profit": 0.0,
        "price": 100.0, "ts_utc": "2026-11-17T14:00:01+00:00",
        "swap": 0.0, "commission": 0.0,
    }
    exit_deal = {
        "position_id": 777, "magic": 20261105, "entry": 1, "profit": 50.0,
        "price": 90.0, "ts_utc": "2026-11-17T14:30:00+00:00",
        "swap": 0.0, "commission": 0.0,
    }
    # El cierre real puede llevar el magic por defecto de MT5 (20261105).
    assert sync_closed(
        _DealsBroker([entry, exit_deal]), db_path=db
    ) == 1
    with connect(db) as con:
        row = con.execute(
            "SELECT status, pnl, result_r, exit_price, exit_ts "
            "FROM ai_trades WHERE proposal_id='p-sync'"
        ).fetchone()
    assert row["status"] == "closed"
    assert row["pnl"] == 50.0
    assert row["result_r"] == 0.5
    assert row["exit_price"] == 90.0
    assert row["exit_ts"] == "2026-11-17T14:30:00+00:00"
