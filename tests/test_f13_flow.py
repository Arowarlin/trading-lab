from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

import tradinglab.execution as execution
import tradinglab.orchestrator as orch
from tradinglab.config import Settings
from tradinglab.intel.calendar import BlackoutResult, CalendarStatus
from tradinglab.session import SessionBlock


def _frame(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = [100 + i * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [x + 0.4 for x in close],
            "low": [x - 0.4 for x in close],
            "close": close,
            "volume": [1_000_000.0] * n,
        },
        index=idx,
    )


class FakeBroker:
    def __init__(self) -> None:
        self.submitted = 0

    def snapshot(self, prices=None):
        return {
            "cash": 100_000.0,
            "equity": 100_000.0,
            "positions_value": 0.0,
            "positions": [],
        }

    def equity_series(self):
        idx = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
        return pd.Series([100_000.0] * 30, index=idx)

    def submit_market(self, *args, **kwargs):
        self.submitted += 1
        raise AssertionError("dry-run no debe enviar órdenes")


def _settings() -> Settings:
    return Settings(
        mode="paper",
        execution={"broker": "alpaca"},
        risk={"max_position_pct": 0.35},
    )


def test_broker_alpaca_paper_selecciona_adaptador(monkeypatch, tmp_path):
    class FakeAlpaca:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(execution, "AlpacaBroker", FakeAlpaca)
    broker = execution.get_broker(_settings(), tmp_path / "lab.db")
    assert isinstance(broker, FakeAlpaca)
    assert broker.kwargs["paper"] is True


def test_f13_dry_run_alpaca_evalua_filtros_y_no_envia(monkeypatch, tmp_path):
    settings = _settings()
    assert settings.mode == "paper"
    assert settings.execution.broker == "alpaca"
    broker = FakeBroker()
    calls = {"ks": 0, "blackout": 0, "session": 0, "guard": 0}

    monkeypatch.setattr(orch, "fetch", lambda *a, **k: _frame())
    monkeypatch.setattr(orch, "_trades_today", lambda *a, **k: 0)
    monkeypatch.setattr(
        orch,
        "ensure_killswitch",
        lambda *a, **k: (
            calls.__setitem__("ks", calls["ks"] + 1)
            or (SimpleNamespace(active=False, reason=""), False)
        ),
    )
    monkeypatch.setattr(orch, "allows_order", lambda *a, **k: True)

    def fake_blackout(*args, **kwargs):
        calls["blackout"] += 1
        return BlackoutResult(False, CalendarStatus.OK, "ok")

    def fake_session(*args, **kwargs):
        calls["session"] += 1
        return SessionBlock(False, "ok")

    def fake_guard(**kwargs):
        calls["guard"] += 1
        return SimpleNamespace(approved=True, qty=kwargs["qty"], reason="")

    monkeypatch.setattr(orch, "calendar_block_for_settings", fake_blackout)
    monkeypatch.setattr(orch, "session_block", fake_session)
    monkeypatch.setattr(orch, "check_order", fake_guard)

    # El bot deshabilitado no debe ejecutarse por defecto.
    assert (
        orch.run_all(
            settings,
            broker,
            only="qqq-trend-f13",
            dry_run=True,
        )
        == []
    )

    actions = orch.run_all(
        settings,
        broker,
        only="qqq-trend-f13",
        dry_run=True,
        include_disabled=True,
        now=datetime(2026, 11, 9, 22, 20, tzinfo=timezone.utc),
    )
    assert len(actions) == 1
    action = actions[0]
    assert action.status == "dry_run"
    assert broker.submitted == 0
    assert calls["ks"] >= 2  # inicial + antes de la apertura
    assert calls["blackout"] == 1
    assert calls["session"] >= 2
    assert calls["guard"] == 1
    assert action.delta > 0
