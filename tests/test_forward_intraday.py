from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
import pytest
from typer.testing import CliRunner

import tradinglab.forward_intraday as fwd
from tradinglab import cli as cli_mod
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow
from tradinglab.instruments import Instrument
from tradinglab.strategies.base import StrategyResult

NOW = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
TOKYO_NOW = datetime(2026, 11, 10, 3, 15, tzinfo=timezone.utc)
HEALTH = {
    "mode": "demo",
    "identity_ok": True,
    "connected": True,
    "trade_allowed": True,
    "require_demo": True,
    "login": 1515220028,
    "expected_login": 1515220028,
    "server": "FTMO-Demo",
    "expected_server": "FTMO-Demo",
    "balance": 100_000.0,
    "equity": 100_000.0,
}
EURUSD_SPEC = {
    "symbol": "EURUSD",
    "digits": 5,
    "point": 0.00001,
    "tick_size": 0.00001,
    "tick_value": 1.0,
    "contract_size": 100_000.0,
    "volume_min": 0.01,
    "volume_max": 100.0,
    "volume_step": 0.01,
    "stops_level": 0,
    "filling_mode": 1,
    "currency_profit": "USD",
    "bid": 1.1000,
    "ask": 1.1002,
}
USDJPY_SPEC = {
    "symbol": "USDJPY",
    "digits": 3,
    "point": 0.001,
    "tick_size": 0.001,
    "tick_value": 0.67,
    "contract_size": 100_000.0,
    "volume_min": 0.01,
    "volume_max": 100.0,
    "volume_step": 0.01,
    "stops_level": 0,
    "filling_mode": 1,
    "currency_profit": "JPY",
    "bid": 150.000,
    "ask": 150.020,
}


def _bars(
    *,
    end: str = "2026-11-10 14:45",
    periods: int = 300,
    start: float = 1.1000,
    step: float = 0.00001,
) -> pd.DataFrame:
    index = pd.date_range(
        end=pd.Timestamp(end, tz="UTC"), periods=periods, freq="15min"
    )
    close = [start + index * step for index in range(periods)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.00020 for value in close],
            "low": [value - 0.00020 for value in close],
            "close": close,
            "volume": [1_000.0] * periods,
        },
        index=index,
    )


def _strategy(target: float):
    def fn(frame: pd.DataFrame, **params):
        return StrategyResult(
            "test", pd.Series(float(target), index=frame.index), dict(params)
        )

    return fn


def _settings() -> Settings:
    return Settings(
        mode="paper",
        mt5={
            "login": 1515220028,
            "server": "FTMO-Demo",
            "require_demo": True,
            "dry_run": True,
        },
    )


def _seed_alias(db, canonical: str = "EURUSD", symbol: str = "EURUSD") -> None:
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT OR REPLACE INTO asset_aliases"
            "(canonical, broker_symbol, asset_class, profile, discovered_at, source) "
            "VALUES(?,?,?,?,?,?)",
            (canonical, symbol, "forex", "intraday_fx", utcnow(), "test"),
        )


def _seed_order(db, bot: fwd.ForwardBot, when: datetime) -> None:
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, order_type, status, bot) "
            "VALUES(?,?,?,?,?,?,?)",
            (when.isoformat(), "EURUSD", "buy", 0.01, "market", "filled", bot.signal_bot),
        )


def _bot(**overrides) -> fwd.ForwardBot:
    data = {
        "id": "eurusd-london-pullback-forward",
        "canonical_symbol": "EURUSD",
        "strategy": "london_pullback",
        "timeframe": "M15",
        "account": "ftmo_demo",
        "params": {
            "fast": 50,
            "slow": 100,
            "pullback_atr": 0.5,
            "max_hold": 16,
        },
        "entry_start": time(7, tzinfo=timezone.utc),
        "entry_end": time(16, tzinfo=timezone.utc),
        "force_exit": time(16, tzinfo=timezone.utc),
        "stop_atr": 2.0,
        "max_trades_per_day": 1,
        "magic": 20261151,
        "enabled": False,
    }
    data.update(overrides)
    return fwd.ForwardBot(**data)


def _tokyo_bot(**overrides) -> fwd.ForwardBot:
    data = {
        "id": "usdjpy-tokyo-breakout-forward",
        "canonical_symbol": "USDJPY",
        "strategy": "tokyo_breakout",
        "timeframe": "M15",
        "account": "ftmo_demo",
        "params": {"range_bars": 8, "buffer_atr": 0.25, "max_hold": 4},
        "entry_start": time(0, tzinfo=timezone.utc),
        "entry_end": time(3, tzinfo=timezone.utc),
        "force_exit": time(4, tzinfo=timezone.utc),
        "stop_atr": 2.0,
        "max_trades_per_day": 1,
        "magic": 20261152,
        "enabled": False,
    }
    data.update(overrides)
    return fwd.ForwardBot(**data)


class FakeBroker:
    def __init__(
        self,
        bars: pd.DataFrame | None = None,
        *,
        spec: dict | None = None,
        quote_ccy: str = "USD",
        positions: list[dict] | None = None,
        health: dict | None = None,
        close_failures: int = 0,
        tick_value: float = 1.0,
        tick_size: float = 0.00001,
        bid: float = 1.1000,
        ask: float = 1.1002,
    ) -> None:
        self.bars = bars if bars is not None else _bars()
        self.spec = dict(spec or EURUSD_SPEC)
        self.quote_ccy = quote_ccy
        self.tick_value = tick_value
        self.tick_size = tick_size
        self.bid = bid
        self.ask = ask
        self._health = dict(health or HEALTH)
        self._positions = [dict(item) for item in (positions or [])]
        self.close_failures = close_failures
        self.submit_calls: list[dict] = []
        self.close_calls: list[dict] = []
        self._ticket = 500

    def health(self) -> dict:
        return dict(self._health)

    def rates(self, symbol: str, timeframe: str = "M15", count: int = 600):
        return self.bars.tail(int(count)).copy()

    def symbol_spec(self, symbol: str) -> dict:
        spec = dict(self.spec)
        spec["symbol"] = symbol
        spec["bid"] = self.bid
        spec["ask"] = self.ask
        return spec

    def instrument(self, symbol: str) -> Instrument:
        return Instrument(
            symbol=symbol,
            asset_class="forex",
            quote_ccy=self.quote_ccy,
            tick_size=self.tick_size,
            tick_value=self.tick_value,
            contract_size=100_000.0,
            min_lot=float(self.spec["volume_min"]),
            lot_step=float(self.spec["volume_step"]),
            max_lot=float(self.spec["volume_max"]),
        )

    def tick(self, symbol: str) -> dict:
        return {"bid": self.bid, "ask": self.ask}

    def positions(self, symbol: str | None = None) -> list[dict]:
        if symbol is None:
            return [dict(item) for item in self._positions]
        return [
            dict(item)
            for item in self._positions
            if str(item.get("symbol") or "").upper() == symbol.upper()
        ]

    def equity_series(self, days: int = 180):
        index = pd.date_range("2026-10-01", periods=30, freq="D", tz="UTC")
        return pd.Series([100_000.0] * 30, index=index)

    def submit_market(self, symbol: str, volume: float, **kwargs) -> dict:
        self.submit_calls.append(
            {"symbol": symbol, "volume": volume, **kwargs}
        )
        if kwargs.get("dry_run"):
            return {
                "ok": True,
                "dry_run": True,
                "symbol": symbol,
                "volume": abs(volume),
                "price": self.ask if volume > 0 else self.bid,
            }
        side = "buy" if volume > 0 else "sell"
        ticket = self._ticket
        self._ticket += 1
        price = self.ask if side == "buy" else self.bid
        self._positions.append(
            {
                "ticket": ticket,
                "symbol": symbol,
                "side": side,
                "volume": abs(volume),
                "price_open": price,
                "price_current": price,
                "sl": float(kwargs.get("sl") or 0.0),
                "tp": 0.0,
                "profit": 0.0,
                "magic": int(kwargs.get("magic") or 0),
                "comment": str(kwargs.get("bot") or ""),
                "time": NOW,
            }
        )
        return {
            "ok": True,
            "dry_run": False,
            "order_id": ticket,
            "deal_id": ticket + 1000,
            "retcode": 10009,
            "symbol": symbol,
            "side": side,
            "volume": abs(volume),
            "price": price,
            "sl": kwargs.get("sl"),
        }

    def close_position(self, ticket: int, volume: float | None = None) -> dict:
        self.close_calls.append({"ticket": ticket, "volume": volume})
        if self.close_failures > 0:
            self.close_failures -= 1
            raise RuntimeError(f"fallo simulado de cierre para {ticket}")
        position = next(
            (item for item in self._positions if int(item["ticket"]) == int(ticket)),
            None,
        )
        if position is None:
            raise RuntimeError(f"no existe la posición {ticket}")
        self._positions.remove(position)
        return {
            "ok": True,
            "ticket": ticket,
            "price": float(position.get("price_current") or 0.0),
        }

    def shutdown(self) -> None:
        return None


@pytest.fixture
def guards(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        fwd,
        "session_block",
        lambda *a, **k: type("S", (), {"blocked": False, "reason": "", "kind": "ok"})(),
    )
    monkeypatch.setattr(
        fwd,
        "calendar_block_for_settings",
        lambda *a, **k: type(
            "C", (), {"blocked": False, "reason": "", "status": "ok"}
        )(),
    )
    monkeypatch.setattr(
        fwd,
        "news_blackout",
        lambda *a, **k: {
            "blocked": False,
            "data_ok": True,
            "reason": "ok",
            "events": [],
        },
    )
    monkeypatch.setattr(
        fwd,
        "ensure_killswitch",
        lambda *a, **k: (type("K", (), {"active": False, "reason": ""})(), None),
    )
    monkeypatch.setattr(
        fwd,
        "evaluate_account",
        lambda *a, **k: type(
            "G",
            (),
            {
                "allowed": True,
                "reason": "ok",
                "breached": False,
                "remaining_usd": 100_000.0,
            },
        )(),
    )
    monkeypatch.setattr(
        fwd, "assess_open", lambda *a, **k: {"allowed": True, "reason": "ok"}
    )
    monkeypatch.setattr(fwd, "flatten_required", lambda *a, **k: False)


def _own_position(
    *,
    symbol: str = "EURUSD",
    magic: int = 20261151,
    side: str = "buy",
    sl: float = 1.0900,
    when: datetime = NOW,
    ticket: int = 700,
) -> dict:
    return {
        "ticket": ticket,
        "symbol": symbol,
        "side": side,
        "volume": 0.01,
        "price_open": 1.1000,
        "price_current": 1.1010,
        "sl": sl,
        "tp": 0.0,
        "profit": 1.0,
        "magic": magic,
        "comment": "forward",
        "time": when,
    }


def test_config_dos_candidatos_fijos() -> None:
    bots = fwd.load_forward_bots()
    assert [bot.id for bot in bots] == [
        "eurusd-london-pullback-forward",
        "usdjpy-tokyo-breakout-forward",
    ]
    assert bots[0].params == {
        "fast": 50,
        "slow": 100,
        "pullback_atr": 0.5,
        "max_hold": 16,
    }
    assert bots[1].params == {
        "range_bars": 8,
        "buffer_atr": 0.25,
        "max_hold": 4,
    }
    assert all(bot.account == "ftmo_demo" for bot in bots)
    assert all(not bot.enabled for bot in bots)
    assert len({bot.magic for bot in bots}) == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("connected", None),
        ("connected", "yes"),
        ("trade_allowed", False),
        ("identity_ok", None),
        ("mode", "real"),
        ("require_demo", None),
        ("expected_login", None),
        ("expected_server", None),
    ],
)
def test_health_fail_closed(
    tmp_path, guards, key: str, value
) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    health = dict(HEALTH)
    if value is None:
        health.pop(key, None)
    else:
        health[key] = value
    broker = FakeBroker(health=health)
    with pytest.raises(fwd.ForwardError):
        fwd.run_forward_bot(
            _bot(),
            broker,
            _settings(),
            db_path=db,
            now=NOW,
            strategy_fn=_strategy(1),
        )
    assert broker.submit_calls == []


def test_dry_run_calcula_stop_y_volumen_minimo(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker()
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        dry_run=True,
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    expected_atr = float(fwd.atr(broker.bars).iloc[-1])
    assert decision.action == "open_long"
    assert decision.volume == 0.01
    assert decision.price == pytest.approx(1.1002)
    assert decision.stop == pytest.approx(1.1002 - 2.0 * expected_atr, abs=1e-5)
    assert broker.submit_calls == []


def test_execute_envia_minimo_y_stop(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker()
    bot = _bot(enabled=True)
    decision = fwd.run_forward_bot(
        bot,
        broker,
        _settings(),
        dry_run=False,
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "opened_long"
    assert len(broker.submit_calls) == 1
    call = broker.submit_calls[0]
    assert call["volume"] == 0.01
    assert call["sl"] == pytest.approx(decision.stop)
    assert call["magic"] == bot.magic
    assert call["bot"] == bot.signal_bot
    assert call["dry_run"] is False


def test_execute_sin_armar_no_envia(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker()
    with pytest.raises(fwd.ForwardError, match="enabled:false"):
        fwd.run_forward_bot(
            _bot(),
            broker,
            _settings(),
            dry_run=False,
            db_path=db,
            now=NOW,
            strategy_fn=_strategy(1),
        )
    assert broker.submit_calls == []


def test_posicion_ajena_bloquea_y_no_cierra(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    foreign = _own_position(magic=123, ticket=999)
    broker = FakeBroker(positions=[foreign])
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "ajena" in decision.reason
    assert broker.submit_calls == []
    assert broker.close_calls == []
    assert any(item["ticket"] == 999 for item in broker.positions())


def test_solo_cierra_posicion_propia(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    ours = _own_position(ticket=700, magic=20261151)
    foreign = _own_position(ticket=701, magic=999)
    broker = FakeBroker(positions=[ours, foreign])
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        dry_run=False,
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(0),
    )
    assert decision.action == "closed"
    assert [call["ticket"] for call in broker.close_calls] == [700]
    assert any(item["ticket"] == 701 for item in broker.positions())


def test_cierre_por_corte_de_sesion(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker(
        positions=[_own_position(when=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc))]
    )
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        dry_run=True,
        db_path=db,
        now=datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc),
        strategy_fn=_strategy(1),
    )
    assert decision.action == "close"
    assert decision.reason == "corte de sesión"
    assert broker.close_calls == []


def test_max_hold_cierra(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db, "USDJPY", "USDJPY")
    position = {
        "ticket": 800,
        "symbol": "USDJPY",
        "side": "buy",
        "volume": 0.01,
        "price_open": 150.000,
        "price_current": 150.100,
        "sl": 149.800,
        "tp": 0.0,
        "profit": 1.0,
        "magic": 20261152,
        "comment": "forward",
        "time": datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc),
    }
    broker = FakeBroker(
        bars=_bars(end="2026-11-10 03:00", start=150.0, step=0.01),
        positions=[position],
        spec=USDJPY_SPEC,
        quote_ccy="JPY",
        tick_value=0.67,
        tick_size=0.001,
        bid=150.000,
        ask=150.020,
    )
    decision = fwd.run_forward_bot(
        _tokyo_bot(),
        broker,
        _settings(),
        dry_run=True,
        db_path=db,
        now=datetime(2026, 11, 10, 3, 15, tzinfo=timezone.utc),
        strategy_fn=_strategy(1),
    )
    assert decision.action == "close"
    assert decision.reason == "max_hold"


def test_max_trades_dia_bloquea(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    bot = _bot()
    _seed_order(db, bot, NOW)
    broker = FakeBroker()
    decision = fwd.run_forward_bot(
        bot,
        broker,
        _settings(),
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "máximo de trades/día" in decision.reason
    assert broker.submit_calls == []


def test_fuera_de_ventana_no_abre(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker(bars=_bars(end="2026-11-10 05:45"))
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc),
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "ventana de entrada" in decision.reason


def test_datos_obsoletos_bloquea(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    broker = FakeBroker(bars=_bars(end="2026-11-10 13:45"))
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=datetime(2026, 11, 10, 15, 45, tzinfo=timezone.utc),
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "datos obsoletos" in decision.reason


def test_noticias_sin_datos_bloquea(tmp_path, guards, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    monkeypatch.setattr(
        fwd,
        "news_blackout",
        lambda *a, **k: {"blocked": False, "data_ok": False, "reason": "sin datos"},
    )
    broker = FakeBroker()
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "noticias sin datos" in decision.reason


def test_killswitch_activo_bloquea_apertura(tmp_path, guards, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    monkeypatch.setattr(
        fwd,
        "ensure_killswitch",
        lambda *a, **k: (type("K", (), {"active": True, "reason": "drawdown"})(), None),
    )
    broker = FakeBroker()
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "kill switch" in decision.reason


def test_killswitch_activo_permite_cierre(tmp_path, guards, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    monkeypatch.setattr(
        fwd,
        "ensure_killswitch",
        lambda *a, **k: (type("K", (), {"active": True, "reason": "drawdown"})(), None),
    )
    broker = FakeBroker(positions=[_own_position()])
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        dry_run=False,
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(0),
    )
    assert decision.action == "closed"
    assert len(broker.close_calls) == 1


def test_guard_cuenta_bloquea(tmp_path, guards, monkeypatch) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    monkeypatch.setattr(
        fwd,
        "evaluate_account",
        lambda *a, **k: type(
            "G",
            (),
            {
                "allowed": False,
                "reason": "límite diario",
                "breached": False,
                "remaining_usd": 0.0,
            },
        )(),
    )
    broker = FakeBroker()
    decision = fwd.run_forward_bot(
        _bot(),
        broker,
        _settings(),
        db_path=db,
        now=NOW,
        strategy_fn=_strategy(1),
    )
    assert decision.action == "bloqueado"
    assert "guard de cuenta" in decision.reason


def test_alias_ausente_falla(tmp_path, guards) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    broker = FakeBroker()
    with pytest.raises(fwd.ForwardError, match="falta alias"):
        fwd.run_forward_bot(
            _bot(),
            broker,
            _settings(),
            db_path=db,
            now=NOW,
            strategy_fn=_strategy(1),
        )
    assert broker.submit_calls == []


def test_cierre_reintenta_y_alerta_si_huerfana(
    tmp_path, guards, monkeypatch
) -> None:
    db = tmp_path / "lab.db"
    _seed_alias(db)
    alerts: list[tuple[str, str, dict]] = []

    def fake_alert(event: str, message: str, **kwargs) -> None:
        alerts.append((event, message, kwargs))

    monkeypatch.setattr(fwd, "send_alert", fake_alert)
    broker = FakeBroker(positions=[_own_position()], close_failures=99)
    with pytest.raises(fwd.ForwardError, match="huérfana"):
        fwd.run_forward_bot(
            _bot(),
            broker,
            _settings(),
            dry_run=False,
            db_path=db,
            now=NOW,
            strategy_fn=_strategy(0),
        )
    assert len(broker.close_calls) == 3
    assert any(item["ticket"] == 700 for item in broker.positions())
    assert alerts
    event, message, kwargs = alerts[0]
    assert event == "intraday_forward_orphan"
    assert kwargs.get("severity") == "error"
    assert "EURUSD" in message and "700" in message


def test_cierre_rechaza_ticket_sin_magic_del_bot(
    tmp_path, guards
) -> None:
    _seed_alias(tmp_path / "lab.db")
    broker = FakeBroker(positions=[_own_position(magic=999)])
    with pytest.raises(fwd.ForwardError, match="magic"):
        fwd._close_with_retries(
            broker,
            "EURUSD",
            700,
            0.01,
            magic=20261151,
            sleep=lambda _: None,
        )
    assert broker.close_calls == []
    assert any(item["ticket"] == 700 for item in broker.positions())


def test_cli_dry_run_no_envia(tmp_path, monkeypatch) -> None:
    broker = FakeBroker()
    decision = fwd.ForwardDecision(
        bot="eurusd-london-pullback-forward",
        symbol="EURUSD",
        signal=1.0,
        action="open_long",
        reason="target=+1",
        price=1.1002,
        atr=0.001,
        stop=1.0982,
        volume=0.01,
        dry_run=True,
    )
    monkeypatch.setattr(cli_mod, "_mt5", lambda settings, dry_run=True: broker)
    monkeypatch.setattr(fwd, "run_forward_all", lambda *a, **k: [decision])
    result = CliRunner().invoke(cli_mod.app, ["intraday", "forward"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    assert "Sin --execute" in result.output
    assert broker.submit_calls == []


def test_cli_execute_exige_confirmacion_y_armado(monkeypatch) -> None:
    calls: list[bool] = []

    def fake_mt5(settings, dry_run=True):
        calls.append(dry_run)
        raise AssertionError("no debe conectar antes de validar")

    monkeypatch.setattr(cli_mod, "_mt5", fake_mt5)

    no_confirm = CliRunner().invoke(
        cli_mod.app, ["intraday", "forward", "--execute"]
    )
    assert no_confirm.exit_code == 2
    assert calls == []

    not_armed = CliRunner().invoke(
        cli_mod.app,
        ["intraday", "forward", "--execute", "--confirm", "FORWARD-DEMO"],
    )
    assert not_armed.exit_code == 2
    assert "enabled:false" in not_armed.output
    assert calls == []


def test_cli_status_muestra_los_dos(monkeypatch) -> None:
    monkeypatch.setenv("COLUMNS", "240")
    result = CliRunner().invoke(cli_mod.app, ["intraday", "status"])
    assert result.exit_code == 0
    assert "eurusd-london-pullback-forward" in result.output
    assert "usdjpy-tokyo-breakout-forward" in result.output
    assert "solo dry-run" in result.output
