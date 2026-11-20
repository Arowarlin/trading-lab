from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import tradinglab.execution as execution
import tradinglab.orchestrator as orch
from tradinglab.config import Settings
from tradinglab.db import connect, init_db, utcnow


class FakeBroker:
    def __init__(self, label: str) -> None:
        self.label = label

    def snapshot(self, prices=None):
        return {
            "cash": 100_000.0,
            "equity": 100_000.0,
            "positions_value": 0.0,
            "positions": [],
        }


def test_get_broker_for_account_enruta_por_plataforma(monkeypatch):
    calls = {}

    class FakeAlpaca:
        def __init__(self, **kwargs):
            calls["alpaca"] = kwargs

    class FakePaper:
        def __init__(self, *args, **kwargs):
            calls["paper"] = kwargs

    monkeypatch.setattr(execution, "AlpacaBroker", FakeAlpaca)
    monkeypatch.setattr(execution, "PaperBroker", FakePaper)
    settings = Settings(mode="paper")

    alpaca = SimpleNamespace(id="alpaca_paper", platform="alpaca", status="active")
    paper = SimpleNamespace(id="paper_main", platform="internal", status="active")

    assert isinstance(execution.get_broker_for_account(settings, alpaca), FakeAlpaca)
    assert calls["alpaca"]["paper"] is True
    assert calls["alpaca"]["account"] == "alpaca_paper"

    assert isinstance(execution.get_broker_for_account(settings, paper), FakePaper)


def test_get_broker_for_account_rechaza_live():
    settings = Settings(mode="paper")
    live = SimpleNamespace(id="alpaca_live", platform="alpaca", status="live")
    with pytest.raises(ValueError, match="no paper"):
        execution.get_broker_for_account(settings, live)
    with pytest.raises(ValueError, match="live"):
        execution.get_broker_for_account(
            Settings(mode="live"),
            SimpleNamespace(id="alpaca_paper", platform="alpaca", status="active"),
        )


def test_run_all_usa_un_broker_por_cuenta(monkeypatch):
    used: dict[str, str] = {}

    def factory(account):
        used[account.id] = "alpaca" if account.platform == "alpaca" else "paper"
        return FakeBroker(used[account.id])

    def fake_run_bot(spec, settings, broker, **kwargs):
        used[spec.id] = broker.label
        return [
            orch.BotAction(
                spec.id,
                spec.universe[0],
                1.0,
                100.0,
                0.0,
                1,
                1,
                "dry_run",
            )
        ]

    specs = [
        orch.BotSpec(
            id="qqq-trend-f13",
            type="deterministic",
            strategy="trend",
            universe=["QQQ"],
            account="alpaca_paper",
            profile="swing_equity",
            cluster="trend_equity",
            enabled=True,
        ),
        orch.BotSpec(
            id="trend-spy",
            type="deterministic",
            strategy="trend",
            universe=["SPY"],
            account="paper_main",
            profile="swing_equity",
            cluster="trend_equity",
            enabled=True,
        ),
    ]
    monkeypatch.setattr(orch, "load_bots", lambda: specs)
    monkeypatch.setattr(orch, "load_clusters", lambda: {"clusters": []})
    monkeypatch.setattr(orch, "run_bot", fake_run_bot)
    monkeypatch.setattr(
        "tradinglab.market_pilots.active_market", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "tradinglab.market_pilots.market_for_bot", lambda *args, **kwargs: None
    )

    actions = orch.run_all(
        Settings(mode="paper"),
        broker_factory=factory,
        dry_run=True,
        now=datetime(2026, 11, 13, 22, 20, tzinfo=timezone.utc),
    )

    assert len(actions) == 2
    assert used["qqq-trend-f13"] == "alpaca"
    assert used["trend-spy"] == "paper"


def test_trades_today_no_cuenta_la_orden_de_otra_cuenta(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        cur = con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, status, bot) "
            "VALUES(?,?,?,?,?,?)",
            (utcnow(), "QQQ", "sell", 5, "filled", "qqq-trend-f13"),
        )
        con.execute(
            "INSERT INTO order_accounts(order_id, account_id, created_at) "
            "VALUES(?,?,?)",
            (cur.lastrowid, "paper_main", utcnow()),
        )
    monkeypatch.setattr(orch, "DEFAULT_DB", db)

    assert orch._trades_today("qqq-trend-f13", "paper_main") == 1
    assert orch._trades_today("qqq-trend-f13", "alpaca_paper") == 0
