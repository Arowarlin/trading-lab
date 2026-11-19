from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from tradinglab.config import Settings
from tradinglab.execution.mt5 import MT5Error
from tradinglab.propfund import snapshots
from tradinglab.propfund.console import payload
from tradinglab.propfund.registry import load_registry
from tradinglab.propfund.snapshots import (
    CACHE_TTL_SECONDS,
    AttachOnlyBroker,
    clear_cache,
    collect_account,
    collect_exposure,
    default_broker_factory,
    magic_lanes,
)

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _account():
    return load_registry().accounts["CFD-001"]


# ------------------------------------------------------------------ MT5 simulado


class _FakeAccount:
    login = 3000123456
    server = "FTMO-Server"
    trade_mode = 0
    name = "FTMO demo"
    company = "FTMO"
    currency = "USD"
    leverage = 100
    balance = 100_000.0
    equity = 101_000.0
    margin = 1_000.0
    margin_free = 100_000.0
    margin_level = 10_100.0
    profit = 1_000.0


class _FakeTerminal:
    connected = True
    trade_allowed = False
    path = "C:/FTMO/terminal64.exe"
    build = 4000


class _FakeMT5:
    POSITION_TYPE_BUY = 0

    def __init__(self, account=None):
        self.account = account or _FakeAccount()
        self.initialize_kwargs = None
        self.shutdown_called = False

    def initialize(self, **kwargs):
        self.initialize_kwargs = dict(kwargs)
        return True

    def last_error(self):
        return 0, "ok"

    def account_info(self):
        return self.account

    def terminal_info(self):
        return _FakeTerminal()

    def symbol_info_tick(self, symbol):
        return None

    def shutdown(self):
        self.shutdown_called = True


@pytest.fixture
def fake_mt5(monkeypatch):
    fake = _FakeMT5()
    monkeypatch.setattr(snapshots, "_mt5_module", lambda: fake)
    monkeypatch.setattr("tradinglab.execution.mt5._mt5", lambda: fake)
    monkeypatch.setattr(snapshots, "_terminal_running", lambda: True)
    return fake


# ------------------------------------------------------------- conexión adjunta


def test_attach_sin_credenciales_y_sin_shutdown(fake_mt5):
    broker = AttachOnlyBroker(
        expected_login=3000123456,
        expected_server="FTMO-Server",
        timeout_ms=1234,
        server_utc_offset_hours=2,
    )
    health = broker.connect()

    assert fake_mt5.initialize_kwargs == {"timeout": 1234}
    assert "login" not in fake_mt5.initialize_kwargs
    assert "password" not in fake_mt5.initialize_kwargs
    assert "server" not in fake_mt5.initialize_kwargs
    assert fake_mt5.shutdown_called is False
    assert health["login"] == 3000123456
    assert health["server"] == "FTMO-Server"
    assert health["mode"] == "demo"


def test_attach_no_arranca_mt5_si_no_esta_abierto(monkeypatch):
    fake = _FakeMT5()
    monkeypatch.setattr(snapshots, "_mt5_module", lambda: fake)
    monkeypatch.setattr(snapshots, "_terminal_running", lambda: False)
    broker = AttachOnlyBroker(expected_login=1, expected_server="FTMO-Server")
    with pytest.raises(MT5Error, match="MT5 no está abierto"):
        broker.connect()
    assert fake.initialize_kwargs is None
    assert fake.shutdown_called is False


def test_attach_rechaza_login_o_servidor_distinto(fake_mt5):
    broker = AttachOnlyBroker(expected_login=111, expected_server="FTMO-Server")
    with pytest.raises(MT5Error, match="login esperado"):
        broker.connect()
    assert fake_mt5.shutdown_called is False

    broker = AttachOnlyBroker(expected_login=3000123456, expected_server="Otro-Server")
    with pytest.raises(MT5Error, match="servidor esperado"):
        broker.connect()


def test_attach_rechaza_cuenta_real(fake_mt5):
    fake_mt5.account.trade_mode = 2
    broker = AttachOnlyBroker(expected_login=3000123456, expected_server="FTMO-Server")
    with pytest.raises(MT5Error, match="se exige demo"):
        broker.connect()


def test_sin_login_configurado_es_sin_datos():
    with pytest.raises(MT5Error, match="MT5_LOGIN"):
        default_broker_factory(_account(), settings=Settings())


# -------------------------------------------------------------------- broker falso


class FakeBroker:
    """Solo implementa los métodos de lectura que usa ``snapshots``."""

    def __init__(self):
        self.calls: list[str] = []
        self.submitted = False

    def connect(self):
        self.calls.append("connect")
        return {
            "login": 3000123456,
            "server": "FTMO-Server",
            "mode": "demo",
            "connected": True,
            "balance": 100_000.0,
            "equity": 101_000.0,
        }

    def positions(self):
        self.calls.append("positions")
        return [
            {
                "ticket": 1, "symbol": "US100.cash", "side": "buy", "volume": 2.0,
                "price_open": 20_950.0, "price_current": 21_000.0, "sl": 20_900.0,
                "tp": 21_200.0, "profit": 100.0, "swap": 0.0, "commission": -1.0,
                "magic": 93010001, "comment": "ea",
            },
            {
                "ticket": 2, "symbol": "XAUUSD", "side": "sell", "volume": 0.5,
                "price_open": 1_995.0, "price_current": 2_000.0, "sl": 2_010.0,
                "tp": 1_950.0, "profit": -50.0, "swap": 0.0, "commission": -2.0,
                "magic": 20261191, "comment": "ai",
            },
            {
                "ticket": 3, "symbol": "EURUSD", "side": "buy", "volume": 1.0,
                "price_open": 1.0990, "price_current": 1.10, "sl": 1.09,
                "tp": 1.12, "profit": 100.0, "swap": 0.0, "commission": -5.0,
                "magic": 20261151, "comment": "forward",
            },
            {
                "ticket": 4, "symbol": "US100.cash", "side": "buy", "volume": 1.0,
                "price_open": 20_900.0, "price_current": 21_000.0, "sl": 0.0,
                "tp": 0.0, "profit": 100.0, "swap": 0.0, "commission": 0.0,
                "magic": 777, "comment": "manual",
            },
        ]

    def symbol_spec(self, symbol):
        self.calls.append(f"symbol_spec:{symbol}")
        sizes = {"US100.cash": 1.0, "XAUUSD": 100.0, "EURUSD": 100_000.0}
        return {"symbol": symbol, "contract_size": sizes.get(symbol)}

    def equity_series(self, days=180):
        self.calls.append("equity_series")
        index = pd.DatetimeIndex(
            [pd.Timestamp("2026-11-19 08:00", tz="UTC"), pd.Timestamp("2026-11-19 10:00", tz="UTC")]
        )
        return pd.Series([100_000.0, 101_000.0], index=index)

    def history_deals(self, start, end):
        self.calls.append("history_deals")
        return [
            {"entry": 0, "ts_utc": "2026-11-19T08:00:00+00:00"},
            {"entry": 1, "ts_utc": "2026-11-19T09:00:00+00:00"},
        ]

    def submit_market(self, *args, **kwargs):  # pragma: no cover - debe no llamarse
        self.submitted = True
        raise AssertionError("no se puede enviar una orden desde snapshots")

    def close_position(self, *args, **kwargs):  # pragma: no cover - debe no llamarse
        self.submitted = True
        raise AssertionError("no se puede cerrar una posición desde snapshots")


# ------------------------------------------------------------------ snapshot


def test_snapshot_y_posiciones_por_magic():
    broker = FakeBroker()
    bundle = collect_account(_account(), broker=broker, now=NOW)

    assert bundle.ok and bundle.status == "ok"
    assert bundle.identity["login"] == 3000123456
    assert bundle.snapshot is not None
    snap = bundle.snapshot
    assert snap.account == "CFD-001"
    assert snap.equity == 101_000.0
    assert snap.day_start_equity == 100_000.0
    assert snap.peak_equity == 101_000.0
    assert snap.trades_today == 1
    assert snap.open_positions == 4
    assert snap.open_risk_usd == 200.0 + 500.0 + 1_000.0  # el magic 777 no tiene SL

    by_magic = {item.magic: item for item in bundle.positions}
    ea = by_magic[93010001]
    assert ea.lane == "ea" and ea.position.strategy == "ea:us100-ftmo1"
    assert ea.position.quantity == 2.0
    assert ea.position.contract_size == 1.0
    assert ea.position.risk_usd == 200.0
    assert ea.as_dict()["notional_usd"] == 42_000.0

    ai = by_magic[20261191]
    assert ai.lane == "ai_trader" and ai.position.strategy.startswith("ai:")
    assert ai.position.quantity == -0.5
    assert ai.position.risk_usd == 500.0

    forward = by_magic[20261151]
    assert forward.lane == "forward"
    assert forward.position.quantity == 1.0
    assert forward.position.risk_usd == 1_000.0

    unknown = by_magic[777]
    assert unknown.lane == "desconocida"
    assert unknown.position.strategy == "desconocido:777"
    assert unknown.position.risk_usd is None

    assert broker.submitted is False
    assert set(broker.calls) == {
        "connect", "positions", "symbol_spec:US100.cash", "symbol_spec:XAUUSD",
        "symbol_spec:EURUSD", "equity_series", "history_deals",
    }


def test_lanes_reales_de_ftmo_demo():
    lanes = magic_lanes("ftmo_demo")
    assert lanes[93010001] == ("ea:us100-ftmo1", "ea")
    assert lanes[93020001] == ("ea:us100-ftmo1", "ea")
    assert lanes[20261191][1] == "ai_trader"
    assert lanes[20261152][1] == "forward"


def test_exposure_agrega_por_subyacente():
    clear_cache()
    data = collect_exposure(
        now=NOW, broker_factory=lambda account: FakeBroker(), ttl_seconds=0
    )
    assert data["ok"] and data["status"] == "ok"
    assert data["read_only"] is True
    assert [a["account"] for a in data["accounts"]] == ["CFD-001"]
    nasdaq = data["by_underlying"]["NASDAQ100"]
    assert nasdaq["gross_notional_usd"] == 63_000.0
    assert nasdaq["net_notional_usd"] == 63_000.0
    assert data["by_underlying"]["GOLD"]["gross_notional_usd"] == 100_000.0
    assert data["totals"]["gross_notional_usd"] == 273_000.0
    assert len(data["positions"]) == 4


def test_exposure_sin_mt5_devuelve_sin_datos():
    def broken(account):
        raise MT5Error("MT5 no está abierto")

    data = collect_exposure(now=NOW, broker_factory=broken, ttl_seconds=0)
    assert data["ok"] is False
    assert data["status"] == "Sin datos"
    assert data["positions"] == [] and data["by_underlying"] == {}
    assert any("MT5 no está abierto" in note for note in data["notes"])


def test_cache_de_60_segundos(monkeypatch, tmp_path):
    assert CACHE_TTL_SECONDS == 60.0
    clear_cache()
    calls = {"n": 0}

    def build(**kwargs):
        calls["n"] += 1
        return {"ok": True, "status": "ok", "generated_at": NOW.isoformat(), "n": calls["n"]}

    monkeypatch.setattr(snapshots, "_build_exposure", build)
    first = collect_exposure(config_dir=tmp_path, now=NOW)
    second = collect_exposure(config_dir=tmp_path, now=NOW)
    assert calls["n"] == 1
    assert first == second and first is not second
    collect_exposure(config_dir=tmp_path, now=NOW, ttl_seconds=0)
    assert calls["n"] == 2
    clear_cache()


# ------------------------------------------------------------------- endpoint


def test_payload_incluye_exposure_solo_si_se_pide():
    fake = {"ok": False, "status": "Sin datos", "notes": ["MT5 no está abierto"]}
    data = payload(include_exposure=True, exposure=fake)
    assert data["exposure"] == fake
    assert "exposure" not in payload()


def test_exposure_json_serializable():
    import json

    data = collect_exposure(now=NOW, broker_factory=lambda account: FakeBroker(), ttl_seconds=0)
    text = json.dumps(data, default=str)
    assert "NASDAQ100" in text
    assert "93010001" in text
