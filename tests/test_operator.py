from __future__ import annotations

import http.client
import json
import socket
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from tradinglab import web
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.f13 import config_hash, freeze
from tradinglab.journal import ClosedTrade
from tradinglab.killswitch import activate as activate_killswitch
from tradinglab.killswitch import load_state
from tradinglab.operator import (
    DEFAULT_WEB_PORT,
    WEB_PORT_ENV,
    OperatorError,
    OperatorService,
    OperatorSession,
    pin_needs_rotation,
    server_session,
    set_pin,
    web_port,
)
from tradinglab.riskpause import pause_status
from tradinglab.runtime import console_actions, get_bot_state


class FakeBroker:
    def __init__(self, positions=None, equity: float = 100_000.0) -> None:
        self.equity = equity
        self.cash = equity
        self._positions = positions or []
        self.orders: list[dict] = []
        self.closed: list[dict] = []

    def positions(self):
        return [dict(item) for item in self._positions]

    def snapshot(self, prices=None):
        prices = prices or {}
        positions = []
        value = 0.0
        for item in self._positions:
            price = float(prices.get(item["ticker"], item.get("last") or item["avg_price"]))
            notional = float(item["qty"]) * price
            value += notional
            positions.append({**item, "value": notional})
        return {
            "equity": self.equity,
            "cash": self.cash,
            "positions": positions,
            "positions_value": value,
        }

    def equity_series(self):
        return pd.Series(
            [self.equity, self.equity],
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )

    def health(self):
        return {"paper": True, "mode": "paper"}

    def submit_market(
        self, ticker, qty, price=None, *, bot="manual", reason="", **kwargs
    ):
        order = {
            "ticker": ticker,
            "qty": qty,
            "price": price,
            "bot": bot,
            "reason": reason,
        }
        self.orders.append(order)
        return order

    def close_position(self, identifier, volume=None, **kwargs):
        item = {"identifier": identifier, "volume": volume, **kwargs}
        self.closed.append(item)
        return item

    def shutdown(self):
        return None


def _service(tmp_path: Path, *, broker=None, now=None, settings=None, pin="1234"):
    settings = settings or Settings()
    db = tmp_path / "lab.db"
    init_db(db)
    session = OperatorSession(
        pin_getter=lambda: pin,
        now=now,
        max_attempts=3,
        lock_seconds=60,
        db_path=db,
    )
    fake = broker or FakeBroker()
    service = OperatorService(
        settings,
        db,
        session=session,
        broker_factory=lambda account: fake,
    )
    return service, fake, db


def _order_params(**overrides):
    params = {
        "account": "paper_main",
        "ticker": "SPY",
        "side": "buy",
        "qty": 1,
        "price": 100.0,
        "sl": 99.0,
    }
    params.update(overrides)
    return params


def test_pin_bloquea_tras_intentos(tmp_path: Path) -> None:
    clock = {"now": datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)}
    session = OperatorSession(
        pin_getter=lambda: "1234",
        now=lambda: clock["now"],
        max_attempts=3,
        lock_seconds=60,
    )
    for _ in range(2):
        with pytest.raises(OperatorError):
            session.arm("0000")
    with pytest.raises(OperatorError) as exc:
        session.arm("0000")
    assert exc.value.status == 429
    assert session.status()["locked"] is True
    with pytest.raises(OperatorError):
        session.arm("1234")
    clock["now"] += timedelta(seconds=61)
    assert session.arm("1234")["armed"] is True


def test_pin_minimo_6_digitos() -> None:
    saved: dict[str, str] = {}
    with pytest.raises(ValueError):
        set_pin("12345", setter=lambda value: saved.setdefault("pin", value))
    assert "pin" not in saved
    set_pin("123456", setter=lambda value: saved.setdefault("pin", value))
    assert saved["pin"] == "123456"


def test_pin_corto_avisa_rotacion() -> None:
    assert pin_needs_rotation(lambda: "1234") is True
    assert pin_needs_rotation(lambda: "123456") is False
    assert pin_needs_rotation(lambda: None) is False


def test_pin_lock_persistente_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    clock = {"now": datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)}
    kwargs = {
        "pin_getter": lambda: "123456",
        "now": lambda: clock["now"],
        "max_attempts": 3,
        "lock_seconds": 60,
        "db_path": db,
    }
    session = OperatorSession(**kwargs)
    with pytest.raises(OperatorError):
        session.arm("000000")
    assert session.status()["attempts_left"] == 2

    # Otra instancia ve el fallo persistido.
    session2 = OperatorSession(**kwargs)
    assert session2.status()["attempts_left"] == 2
    with pytest.raises(OperatorError):
        session2.arm("000000")
    with pytest.raises(OperatorError) as exc:
        session2.arm("000000")
    assert exc.value.status == 429

    # Otra instancia ve el bloqueo persistido.
    session3 = OperatorSession(**kwargs)
    assert session3.status()["locked"] is True
    assert session3.status()["attempts_left"] == 0
    with pytest.raises(OperatorError) as exc:
        session3.arm("123456")
    assert exc.value.status == 429

    clock["now"] += timedelta(seconds=61)
    session4 = OperatorSession(**kwargs)
    assert session4.status()["locked"] is False
    assert session4.arm("123456")["armed"] is True
    with connect(db) as con:
        row = con.execute(
            "SELECT failures, locked_until FROM operator_pin_state WHERE id = 1"
        ).fetchone()
    assert row is not None
    assert row["failures"] == 0
    assert row["locked_until"] is None


def test_preview_y_token_de_un_solo_uso(tmp_path: Path) -> None:
    clock = {"now": datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)}
    service, fake, _ = _service(tmp_path, now=lambda: clock["now"])
    service.arm("1234")
    preview = service.preview("order", _order_params())
    assert preview["summary"]["account"] == "paper_main"
    assert preview["summary"]["symbol"] == "SPY"
    assert preview["summary"]["risk_usd"] == pytest.approx(1.0)
    result = service.execute("order", _order_params(), preview["token"])
    assert result["ok"] is True
    assert len(fake.orders) == 1
    assert fake.orders[0]["qty"] == 1
    with pytest.raises(OperatorError):
        service.execute("order", _order_params(), preview["token"])


def test_token_caduca(tmp_path: Path) -> None:
    clock = {"now": datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)}
    service, fake, _ = _service(tmp_path, now=lambda: clock["now"])
    service.arm("1234")
    preview = service.preview("order", _order_params())
    clock["now"] += timedelta(seconds=61)
    with pytest.raises(OperatorError) as exc:
        service.execute("order", _order_params(), preview["token"])
    assert "caducado" in str(exc.value)
    assert fake.orders == []


def test_orden_fuera_de_limite_rechazada(tmp_path: Path) -> None:
    service, fake, _ = _service(tmp_path)
    service.arm("1234")
    with pytest.raises(OperatorError) as exc:
        service.preview("order", _order_params(qty=150, sl=90.0))
    assert "guard" in str(exc.value)
    assert fake.orders == []


def test_cierre_permitido_con_killswitch_activo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("tradinglab.killswitch.send_alert", lambda *a, **k: None)
    fake = FakeBroker(
        positions=[
            {"ticker": "SPY", "qty": 5.0, "avg_price": 100.0, "last": 101.0}
        ]
    )
    service, fake, db = _service(tmp_path, broker=fake)
    activate_killswitch(db, reason="test", confirm=True)
    assert load_state(db).active is True
    service.arm("1234")
    preview = service.preview(
        "close", {"account": "paper_main", "ticket": "SPY", "price": 101.0}
    )
    result = service.execute(
        "close",
        {"account": "paper_main", "ticket": "SPY", "price": 101.0},
        preview["token"],
    )
    assert result["ok"] is True
    assert fake.orders[-1]["qty"] == -5
    assert fake.orders[-1]["price"] == pytest.approx(101.0)


def test_piloto_bloquea_apertura_de_otro_mercado(tmp_path: Path) -> None:
    from tradinglab.market_pilots import select_pilot

    service, fake, db = _service(tmp_path)
    select_pilot(db, "equity", confirm=True)
    service.arm("1234")
    with pytest.raises(OperatorError) as exc:
        service.preview("order", _order_params(account="ftmo_demo"))
    assert "piloto" in str(exc.value).lower()
    assert fake.orders == []


def test_pausa_bloquea_apertura_pero_no_cierre(tmp_path: Path) -> None:
    fake = FakeBroker(
        positions=[
            {"ticker": "SPY", "qty": 5.0, "avg_price": 100.0, "last": 101.0}
        ]
    )
    service, fake, db = _service(tmp_path, broker=fake)
    service.arm("1234")
    now = datetime(2026, 1, 7, 20, 0, tzinfo=timezone.utc)
    trades = []
    for index in range(3):
        stamp = f"2026-01-0{5 + index}T15:00:00+00:00"
        trades.append(
            ClosedTrade(
                bot="trend-spy",
                account="paper_main",
                profile="swing_equity",
                ticker="SPY",
                qty=1.0,
                entry_price=100.0,
                exit_price=90.0,
                entry_ts=stamp,
                exit_ts=stamp,
                pnl=-10.0,
                fees=0.0,
                return_pct=-0.1,
                holding_hours=1.0,
                day=f"2026-01-0{5 + index}",
                hour=15,
                entry_order_id=index + 1,
                exit_order_id=index + 2,
                exit_fill_id=index + 3,
            )
        )
    paused = pause_status(db, "paper_main", trades=trades, tz="UTC", now=now)
    assert paused["paused"] is True
    with pytest.raises(OperatorError) as exc:
        service.preview("order", _order_params())
    assert "pausa" in str(exc.value).lower()
    preview = service.preview(
        "close", {"account": "paper_main", "ticket": "SPY", "price": 101.0}
    )
    result = service.execute(
        "close",
        {"account": "paper_main", "ticket": "SPY", "price": 101.0},
        preview["token"],
    )
    assert result["ok"] is True
    assert fake.orders[-1]["qty"] == -5


def test_mode_live_y_plantilla_rechazadas(tmp_path: Path) -> None:
    live, _, _ = _service(tmp_path, settings=Settings(mode="live"))
    live.arm("1234")
    with pytest.raises(OperatorError) as exc:
        live.preview("order", _order_params())
    assert exc.value.status == 403

    service, _, _ = _service(tmp_path / "paper")
    service.arm("1234")
    with pytest.raises(OperatorError) as exc:
        service.preview(
            "order", _order_params(account="topstep_template")
        )
    assert exc.value.status == 403


def test_bot_runtime_y_hash_f13(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("tradinglab.orchestrator.DEFAULT_DB", tmp_path / "lab.db")
    from tradinglab.orchestrator import load_bots

    service, _, db = _service(tmp_path)
    before = config_hash()
    service.arm("1234")

    preview = service.preview("bot_disable", {"bot": "trend-spy", "reason": "test"})
    service.execute(
        "bot_disable", {"bot": "trend-spy", "reason": "test"}, preview["token"]
    )
    state = get_bot_state(db, "trend-spy")
    assert state is not None and state["enabled"] == 0
    assert next(bot for bot in load_bots() if bot.id == "trend-spy").enabled is False
    assert config_hash() == before

    preview = service.preview("bot_enable", {"bot": "trend-spy", "reason": "test"})
    service.execute(
        "bot_enable", {"bot": "trend-spy", "reason": "test"}, preview["token"]
    )
    state = get_bot_state(db, "trend-spy")
    assert state is not None and state["enabled"] == 1
    assert next(bot for bot in load_bots() if bot.id == "trend-spy").enabled is True
    assert config_hash() == before


def test_run_bot_reutiliza_orquestador(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("tradinglab.orchestrator.DEFAULT_DB", tmp_path / "lab.db")
    calls: dict = {}

    class Action:
        status = "ejecutado"

    def fake_run_bot(spec, settings, broker, **kwargs):
        calls["bot"] = spec.id
        calls["account"] = kwargs.get("account").id
        return [Action()]

    monkeypatch.setattr("tradinglab.orchestrator.run_bot", fake_run_bot)
    service, fake, _ = _service(tmp_path)
    service.arm("1234")
    preview = service.preview("run_bot", {"bot": "trend-spy"})
    result = service.execute("run_bot", {"bot": "trend-spy"}, preview["token"])
    assert result["ok"] is True
    assert result["result"]["executed"] == 1
    assert calls == {"bot": "trend-spy", "account": "paper_main"}


def test_f13_congelado_no_permite_tocar_su_bot(tmp_path: Path) -> None:
    service, _, db = _service(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    freeze(
        db,
        bot="qqq-trend-f13",
        symbol="QQQ",
        start_date="2026-01-05",
        root=root,
    )
    service.arm("1234")
    with pytest.raises(OperatorError) as exc:
        service.preview("bot_enable", {"bot": "qqq-trend-f13"})
    assert "F13" in str(exc.value)


def test_auditoria_sin_secretos(tmp_path: Path) -> None:
    service, _, db = _service(tmp_path)
    service.arm("1234")
    preview = service.preview("order", _order_params())
    service.execute("order", _order_params(), preview["token"])
    rows = console_actions(db, 10)
    assert any(row["action"] == "order" for row in rows)
    for row in rows:
        text = json.dumps(row, ensure_ascii=False)
        assert "1234" not in text
        assert preview["token"] not in text


def test_f13_status_falla_bloquea_y_audita(tmp_path: Path, monkeypatch) -> None:
    service, _, db = _service(tmp_path)

    def boom(db_path):
        raise RuntimeError("fallo E:\\secreto\\datos")

    monkeypatch.setattr("tradinglab.f13.status", boom)
    assert service._f13_bot_locked("qqq-trend-f13") is True
    rows = console_actions(db, 20)
    row = next(row for row in rows if row["action"] == "f13_status_error")
    assert row["ok"] is False
    assert "<ruta>" in row["detail"]
    assert "secreto" not in row["detail"]


def _http(
    server: web.DashboardServer,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = None,
    operator_client: bool = True,
) -> tuple[int, dict]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=5
    )
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if token:
            headers["X-CSRF-Token"] = token
        if operator_client:
            headers["X-Operator-Client"] = "console"
        if payload is not None:
            headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"{}")
    finally:
        connection.close()


def _csrf(server: web.DashboardServer) -> str:
    status, payload = _http(server, "GET", "/api/session", operator_client=False)
    assert status == 200
    return payload["csrf"]


def test_web_operador_sin_armar_y_dos_pasos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("tradinglab.orchestrator.DEFAULT_DB", tmp_path / "lab.db")
    service, _, db = _service(tmp_path)
    data = web.LabData(
        Settings(),
        root=tmp_path,
        db_path=db,
        external=False,
        operator_service=service,
    )
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        csrf = _csrf(server)
        status, _ = _http(
            server,
            "POST",
            "/api/operator/arm",
            body={"pin": "1234"},
        )
        assert status == 403

        status, _ = _http(
            server,
            "POST",
            "/api/operator/preview",
            body={"action": "bot_disable", "params": {"bot": "trend-spy"}},
            token=csrf,
        )
        assert status == 403

        status, payload = _http(
            server,
            "POST",
            "/api/operator/arm",
            body={"pin": "0000"},
            token=csrf,
        )
        assert status == 403

        status, payload = _http(
            server,
            "POST",
            "/api/operator/arm",
            body={"pin": "1234"},
            token=csrf,
        )
        assert status == 200 and payload["session"]["armed"] is True

        status, _ = _http(
            server,
            "POST",
            "/api/operator/preview",
            body={"action": "bot_disable", "params": {"bot": "trend-spy"}},
            token=csrf,
            operator_client=False,
        )
        assert status == 403

        status, preview = _http(
            server,
            "POST",
            "/api/operator/preview",
            body={"action": "bot_disable", "params": {"bot": "trend-spy"}},
            token=csrf,
        )
        assert status == 200 and preview["token"]

        status, _ = _http(
            server,
            "POST",
            "/api/operator/execute",
            body={
                "action": "bot_disable",
                "params": {"bot": "trend-spy"},
                "token": "inventado",
            },
            token=csrf,
        )
        assert status == 403

        status, result = _http(
            server,
            "POST",
            "/api/operator/execute",
            body={
                "action": "bot_disable",
                "params": {"bot": "trend-spy"},
                "token": preview["token"],
            },
            token=csrf,
        )
        assert status == 200, result
        assert get_bot_state(db, "trend-spy")["enabled"] == 0

        status, operator_payload = _http(
            server, "GET", "/api/operator", operator_client=False
        )
        assert status == 200
        assert any(row["action"] == "bot_disable" for row in operator_payload["audit"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_session_lee_el_armado_del_panel(tmp_path: Path, monkeypatch) -> None:
    """El CLI ve el armado que vive en el proceso web (regresión de `lab drill`)."""
    monkeypatch.setattr("tradinglab.orchestrator.DEFAULT_DB", tmp_path / "lab.db")
    service, _, db = _service(tmp_path)
    data = web.LabData(
        Settings(),
        root=tmp_path,
        db_path=db,
        external=False,
        operator_service=service,
    )
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        session = server_session(port=port, timeout=3.0)
        assert session is not None
        assert session["armed"] is False

        service.session.arm("1234")
        session = server_session(port=port, timeout=3.0)
        assert session is not None
        assert session["armed"] is True
        assert session["seconds_left"] > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_session_sin_panel_es_desarmado() -> None:
    """Sin panel no hay armado visible: el simulacro falla cerrado."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    assert server_session(port=port, timeout=0.5) is None


def test_web_port_precedencia(monkeypatch) -> None:
    monkeypatch.delenv(WEB_PORT_ENV, raising=False)
    assert web_port() == DEFAULT_WEB_PORT
    monkeypatch.setenv(WEB_PORT_ENV, "9100")
    assert web_port() == 9100
    assert web_port(1234) == 1234
    monkeypatch.setenv(WEB_PORT_ENV, "no-es-un-puerto")
    assert web_port() == DEFAULT_WEB_PORT
