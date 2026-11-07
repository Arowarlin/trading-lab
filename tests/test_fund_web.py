from __future__ import annotations

import http.client
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tradinglab import web
from tradinglab.accounts import load_accounts
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.journal import ClosedTrade
from tradinglab.killswitch import load_state
from tradinglab.operator import OperatorService, OperatorSession
from tradinglab.orchestrator import BotSpec
from tradinglab.riskpause import pause_status


def _data(tmp_path: Path) -> web.LabData:
    settings = Settings()
    db_path = tmp_path / "lab.db"
    service = OperatorService(
        settings,
        db_path,
        session=OperatorSession(pin_getter=lambda: "1234"),
    )
    return web.LabData(
        settings,
        root=tmp_path,
        db_path=db_path,
        external=False,
        operator_service=service,
    )


@pytest.fixture()
def server(tmp_path: Path):
    instance = web.DashboardServer(("127.0.0.1", 0), _data(tmp_path))
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def _request(
    server: web.DashboardServer,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_address[1], timeout=5
    )
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if token:
            headers["X-CSRF-Token"] = token
        if payload is not None:
            headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw or b"{}")
    finally:
        connection.close()


def _token(server: web.DashboardServer) -> str:
    status, payload = _request(server, "GET", "/api/session")
    assert status == 200
    return payload["csrf"]


def test_fund_limites_bolsillos_y_clusters(tmp_path: Path) -> None:
    payload = _data(tmp_path).fund()
    accounts = {row["id"]: row for row in payload["accounts"]}
    assert set(accounts) == {
        "paper_main",
        "alpaca_paper",
        "ftmo_demo",
        "topstep_template",
    }

    ftmo = accounts["ftmo_demo"]
    assert ftmo["type"] == "fondeo"
    assert ftmo["firm_limits"]["daily_loss_pct"] == pytest.approx(0.05)
    assert ftmo["effective_limits"]["daily_loss_pct"] == pytest.approx(0.05)
    assert ftmo["usage"]["daily_limit_usd"] == pytest.approx(5000.0)
    assert ftmo["usage"]["available"] is False

    pockets = {row["pocket"]: row for row in payload["pockets"]}
    assert set(pockets) == {"swing_equity", "intraday_fx", "intraday_futures"}
    assert pockets["swing_equity"]["capital"] == pytest.approx(200_000.0)
    assert sum(row["capital"] for row in payload["pockets"]) == pytest.approx(350_000.0)

    clusters = {row["cluster"]: row for row in payload["clusters"]}
    trend = clusters["trend_equity"]
    assert trend["account"] == "paper_main"
    assert trend["reserved_usd"] == pytest.approx(500.0)
    assert trend["budget_usd"] == pytest.approx(1000.0)
    assert trend["over_budget"] is False
    assert payload["exposure"]["note"]


def test_uso_diario_paper_con_curva_sintetica(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    tz = ZoneInfo(Settings().timezone)
    now = datetime.now(tz)
    today = now.replace(hour=10, minute=0, second=0, microsecond=0)
    points = [
        (today - timedelta(days=2), 100_000.0),
        (today.replace(hour=9, minute=30), 100_000.0),
        (today.replace(hour=11, minute=0), 98_500.0),
    ]
    with connect(db) as con:
        for stamp, equity in points:
            con.execute(
                "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
                (stamp.isoformat(), equity, 0.0, equity),
            )

    payload = _data(tmp_path).fund()
    paper = next(row for row in payload["accounts"] if row["id"] == "paper_main")
    usage = paper["usage"]
    assert usage["available"] is True
    assert usage["source"] == "sqlite"
    assert usage["equity"] == pytest.approx(98_500.0)
    assert usage["day_start_equity"] == pytest.approx(100_000.0)
    assert usage["daily_loss_usd"] == pytest.approx(1_500.0)
    assert usage["daily_limit_usd"] == pytest.approx(5_000.0)
    assert usage["daily_used_pct"] == pytest.approx(0.30)
    assert usage["daily_cushion_usd"] == pytest.approx(3_500.0)
    assert usage["drawdown_used_pct"] == pytest.approx(0.15)
    assert usage["drawdown_cushion_usd"] == pytest.approx(8_500.0)


def test_api_limits_apretar_aflojar_y_firma(server) -> None:
    token = _token(server)

    status, _ = _request(
        server,
        "POST",
        "/api/fund/limits",
        body={"account": "paper_main", "changes": {"daily_loss_pct": 0.04}},
    )
    assert status == 403

    status, payload = _request(
        server,
        "POST",
        "/api/fund/limits",
        body={"account": "paper_main", "changes": {"daily_loss_pct": 0.04}},
        token=token,
    )
    assert status == 200, payload
    assert payload["pending"] is False
    fund = _request(server, "GET", "/api/fund")[1]
    paper = next(row for row in fund["accounts"] if row["id"] == "paper_main")
    assert paper["own_limits"]["daily_loss_pct"] == pytest.approx(0.04)
    assert paper["effective_limits"]["daily_loss_pct"] == pytest.approx(0.04)

    status, payload = _request(
        server,
        "POST",
        "/api/fund/limits",
        body={"account": "paper_main", "changes": {"daily_loss_pct": 0.06}},
        token=token,
    )
    assert status == 400
    assert "confirmación" in payload["errors"][0]

    status, payload = _request(
        server,
        "POST",
        "/api/fund/limits",
        body={
            "account": "paper_main",
            "changes": {"daily_loss_pct": 0.06},
            "confirm": True,
        },
        token=token,
    )
    assert status == 200, payload
    assert payload["pending"] is True
    fund = _request(server, "GET", "/api/fund")[1]
    paper = next(row for row in fund["accounts"] if row["id"] == "paper_main")
    assert paper["own_limits"]["daily_loss_pct"] == pytest.approx(0.04)
    assert paper["pending"]

    status, payload = _request(
        server,
        "POST",
        "/api/fund/limits",
        body={
            "account": "ftmo_demo",
            "changes": {"daily_loss_pct": 0.06},
            "confirm": True,
        },
        token=token,
    )
    assert status == 400
    assert "firma" in payload["errors"][0]


def test_killswitch_global_requiere_confirmacion(server, monkeypatch) -> None:
    monkeypatch.setattr("tradinglab.killswitch.send_alert", lambda *a, **k: None)
    token = _token(server)

    status, payload = _request(
        server,
        "POST",
        "/api/fund/killswitch",
        body={"action": "activate", "confirm": False},
        token=token,
    )
    assert status == 403
    assert "confirmación" in payload["error"]

    status, payload = _request(
        server,
        "POST",
        "/api/fund/killswitch",
        body={"action": "activate", "confirm": True},
        token=token,
    )
    assert status == 200, payload
    assert payload["killswitch"]["active"] is True
    assert load_state(server.data.db_path).active is True

    status, payload = _request(
        server,
        "POST",
        "/api/fund/killswitch",
        body={"action": "reset", "confirm": False},
        token=token,
    )
    assert status == 403

    status, payload = _request(
        server,
        "POST",
        "/api/fund/killswitch",
        body={"action": "reset", "confirm": True, "pin": "0000"},
        token=token,
    )
    assert status == 403
    assert "PIN" in payload["error"]

    status, payload = _request(
        server,
        "POST",
        "/api/fund/killswitch",
        body={"action": "reset", "confirm": True, "pin": "1234"},
        token=token,
    )
    assert status == 200, payload
    assert payload["killswitch"]["active"] is False


def test_pausa_de_fondo_se_reanuda_con_confirmacion(server) -> None:
    db = server.data.db_path
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
    assert pause_status(db, "paper_main", trades=trades, tz="UTC")["paused"] is True
    token = _token(server)
    fund = _request(server, "GET", "/api/fund")[1]
    paper = next(row for row in fund["accounts"] if row["id"] == "paper_main")
    assert paper["pause"]["paused"] is True
    status, payload = _request(
        server,
        "POST",
        "/api/fund/pause/resume",
        body={"account": "paper_main", "confirm": True},
        token=token,
    )
    assert status == 200, payload
    assert payload["paused"] is False


def test_cluster_avisa_si_supera_presupuesto(tmp_path: Path, monkeypatch) -> None:
    specs = [
        BotSpec(
            id=f"bot-{index}",
            type="deterministic",
            strategy="trend",
            universe=["SPY"],
            enabled=True,
            profile="swing_equity",
            cluster="trend_equity",
            account="paper_main",
        )
        for index in range(3)
    ]
    monkeypatch.setattr(web, "load_bots", lambda: specs)
    rows = _data(tmp_path)._fund_clusters(load_accounts())
    assert len(rows) == 1
    row = rows[0]
    assert row["reserved_usd"] == pytest.approx(1500.0)
    assert row["budget_usd"] == pytest.approx(1000.0)
    assert row["over_budget"] is True
