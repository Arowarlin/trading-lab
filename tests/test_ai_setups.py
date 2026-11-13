from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from tradinglab.ai_setups import ALLOWED, allowed_timeframe, plan, validate
from tradinglab.ai_trader import (
    _block_from_bars,
    _daily,
    _donchian_stop,
    _forced_close_reason,
    snapshot_style,
)
from tradinglab.db import connect, init_db


def _frame(*, periods: int = 800, freq: str = "4h", end: pd.Timestamp | None = None,
           low: float = 99.0, high: float = 101.0, close: float = 100.0,
           volume: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(
        end=end or pd.Timestamp.now(tz="UTC").floor("h"),
        periods=periods,
        freq=freq,
    )
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


class _FakeBroker:
    def __init__(self, frames: dict[str, pd.DataFrame], *, equity: float = 100_000.0,
                 positions: list[dict] | None = None):
        self.frames = frames
        self.equity = equity
        self._positions = positions or []
        self.closed: list[int] = []

    def health(self):
        return {"mode": "demo", "equity": self.equity}

    def positions(self):
        return [p for p in self._positions if int(p["ticket"]) not in self.closed]

    def tick(self, symbol: str):
        frame = self.frames["H1"]
        price = float(frame["close"].iloc[-1])
        return {"bid": price - 0.5, "ask": price + 0.5}

    def symbol_spec(self, symbol: str):
        return {
            "point": 0.01, "digits": 2, "stops_level": 10,
            "volume_step": 0.01, "volume_min": 0.01, "volume_max": 1000.0,
        }

    def rates(self, symbol: str, timeframe: str = "H1", count: int = 500):
        return self.frames[timeframe].tail(count)

    def close_position(self, ticket: int, volume: float | None = None):
        self.closed.append(int(ticket))
        return {"ticket": ticket, "closed": True}


def test_asignacion_exacta_por_activo_y_timeframe():
    assert allowed_timeframe("US100.CASH", "orb_ny") == "M15"
    assert allowed_timeframe("US100.CASH", "vwap_reversion") == "M15"
    assert allowed_timeframe("US100.CASH", "bollinger_squeeze") == "H1"
    assert allowed_timeframe("US100.CASH", "rsi2_connors") == "D1"
    assert allowed_timeframe("US100.CASH", "donchian_turtle") == "D1"
    assert allowed_timeframe("US100.CASH", "trend_pullback") == "H4"
    assert allowed_timeframe("XAUUSD", "liquidity_sweep") == "H1"
    assert allowed_timeframe("XAUUSD", "inside_bar") == "D1"
    assert allowed_timeframe("XAUUSD", "trend_pullback") == "H4"
    assert allowed_timeframe("EURUSD", "london_breakout") == "H1"
    assert allowed_timeframe("GBPUSD", "ema_pullback") == "H1"
    assert allowed_timeframe("USDJPY", "donchian_turtle") == "D1"
    assert allowed_timeframe("USDJPY", "trend_pullback") == "H4"
    assert allowed_timeframe("XAUUSD", "orb_ny") is None
    assert set(ALLOWED) == {"US100.CASH", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}


def test_trend_pullback_exige_tendencia_d1_y_retroceso_h4():
    snap = {
        "symbol": "XAUUSD", "price": 100.5, "spread": 0.05, "now": "2026-11-12T15:00:00+00:00",
        "h4": {"atr": 1.0, "sma20": 100.0, "high": 100.4, "low": 99.6, "close": 100.5},
        "d1": {"close": 100.0, "sma200": 90.0},
    }
    ok, reason = validate("trend_pullback", "buy", snap)
    assert ok is True, reason
    level = plan("trend_pullback", "buy", snap)
    assert level.sl == pytest.approx(99.0)
    assert level.tp == pytest.approx(103.5)
    assert level.rr == pytest.approx(2.0)

    # Sin tendencia D1 no hay setup.
    snap["d1"] = {"close": 85.0, "sma200": 90.0}
    ok, reason = validate("trend_pullback", "buy", snap)
    assert ok is False and "tendencia" in reason

    # En corto, el retroceso debe llegar desde arriba.
    snap["d1"] = {"close": 85.0, "sma200": 90.0}
    snap["price"] = 99.5
    snap["h4"]["close"] = 99.5
    ok, reason = validate("trend_pullback", "sell", snap)
    assert ok is True, reason
    level = plan("trend_pullback", "sell", snap)
    assert level.sl == pytest.approx(101.0)
    assert level.tp == pytest.approx(96.5)


def test_ventanas_de_orb_y_londres():
    orb = {
        "symbol": "US100.CASH", "price": 102.0, "spread": 0.1,
        "m15": {"orb_high": 101.0, "orb_low": 99.0, "orb_valid": True},
    }
    orb["now"] = "2026-11-12T15:00:00+00:00"  # 10:00 NY
    assert validate("orb_ny", "buy", orb, "M15")[0] is True
    orb["now"] = "2026-11-12T23:00:00+00:00"  # 18:00 NY
    assert validate("orb_ny", "buy", orb, "M15")[0] is False

    london = {
        "symbol": "EURUSD", "price": 102.0, "spread": 0.1,
        "h1": {"asian_high": 101.0, "asian_low": 99.0, "asian_valid": True},
    }
    london["now"] = "2026-11-12T08:00:00+00:00"
    assert validate("london_breakout", "buy", london, "H1")[0] is True
    london["now"] = "2026-11-12T12:00:00+00:00"
    assert validate("london_breakout", "buy", london, "H1")[0] is False


def test_snapshot_sin_lookahead_truncado_igual_que_completo():
    end = pd.Timestamp.now(tz="UTC").floor("h")
    full = _frame(periods=900, freq="1h", end=end, low=99.0, high=101.0)
    now = full.index[600] + pd.Timedelta(minutes=1)
    truncated = full[full.index <= now]
    h4_full = _frame(periods=900, freq="4h", end=end, low=98.0, high=102.0)
    h4_trunc = h4_full[h4_full.index <= now]

    full_block = _block_from_bars(full, "H1", _daily(h4_full), 100.0, now)
    trunc_block = _block_from_bars(truncated, "H1", _daily(h4_trunc), 100.0, now)
    assert full_block == trunc_block


def test_donchian_trailing_nunca_aleja_el_stop():
    end = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)
    h4 = _frame(periods=240, freq="4h", end=end, low=100.0, high=110.0, close=105.0)
    broker = _FakeBroker({"H4": h4})
    now = datetime.now(timezone.utc)

    # Largo: el canal de 10 días sube el stop, pero nunca lo baja.
    assert _donchian_stop(broker, "XAUUSD", "buy", 105.0, 99.0, 0.2, now, 2) == 100.0
    assert _donchian_stop(broker, "XAUUSD", "buy", 105.0, 100.5, 0.2, now, 2) is None
    # Corto: el canal de 10 días baja el stop, pero nunca lo sube.
    assert _donchian_stop(broker, "XAUUSD", "sell", 105.0, 111.0, 0.2, now, 2) == 110.0
    assert _donchian_stop(broker, "XAUUSD", "sell", 105.0, 109.0, 0.2, now, 2) is None


def test_cierres_forzados_de_sesion():
    opened = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)  # 09:00 NY
    after = datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc)   # 16:00 NY
    assert _forced_close_reason("orb_ny", opened, after) is not None
    assert _forced_close_reason("orb_ny", opened, opened) is None
    noon = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)  # 12:00 NY
    assert _forced_close_reason("orb_5m", opened, noon) is not None
    assert _forced_close_reason(
        "orb_5m", opened, datetime(2026, 11, 12, 16, 59, tzinfo=timezone.utc)
    ) is None
    london_after = datetime(2026, 11, 12, 16, 1, tzinfo=timezone.utc)
    assert _forced_close_reason("london_breakout", opened, london_after) is not None
    assert _forced_close_reason("donchian_turtle", opened, after) is None


def test_snapshot_style_compacto_y_bajo_3000_tokens(tmp_path):
    end = pd.Timestamp.now(tz="UTC").floor("h")
    frames = {
        "M1": _frame(periods=800, freq="1min", end=end),
        "M5": _frame(periods=800, freq="5min", end=end),
        "M15": _frame(periods=800, freq="15min", end=end),
        "H1": _frame(periods=800, freq="1h", end=end),
        "H4": _frame(periods=800, freq="4h", end=end),
    }
    broker = _FakeBroker(frames)
    db = tmp_path / "lab.db"
    init_db(db)
    payload = snapshot_style(broker, "swing", db_path=db)
    assert payload["style"] == "swing"
    assert payload["token_estimate"] <= 3000
    assert set(payload["symbols"]) == {"US100.cash", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}
    assert "setups" in payload["symbols"]["US100.cash"]
    assert "budget" in payload and "events_24h" in payload
    assert payload["symbols"]["US100.cash"]["data"]["trend_d1"] in {"up", "down", "flat", "Sin datos"}


def test_manage_cierra_orb_al_final_de_sesion(tmp_path):
    from tradinglab.ai_trader import manage

    now = datetime.now(timezone.utc)
    opened = now - timedelta(days=1)
    ticket = 777
    position = {
        "ticket": ticket, "symbol": "US100.cash", "side": "buy", "volume": 1.0,
        "price_open": 100.0, "price_current": 101.0, "sl": 99.0, "tp": 0.0,
        "profit": 100.0, "magic": 20261192, "time": opened,
    }
    end = pd.Timestamp.now(tz="UTC").floor("h")
    frames = {
        "M1": _frame(periods=300, freq="1min", end=end),
        "M5": _frame(periods=300, freq="5min", end=end),
        "M15": _frame(periods=300, freq="15min", end=end),
        "H1": _frame(periods=300, freq="1h", end=end),
        "H4": _frame(periods=300, freq="4h", end=end),
    }
    broker = _FakeBroker(frames, positions=[position])
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO ai_trades(proposal_id, ts, style, symbol, setup, side, "
            "status, magic, ticket, risk_usd) VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("p-orb", opened.isoformat(), "intraday", "US100.cash", "orb_ny",
             "buy", "open", 20261192, ticket, 50.0),
        )
    rows = manage(broker=broker, db_path=db)
    assert any(row["ticket"] == ticket and row.get("closed") for row in rows)
    assert ticket in broker.closed
