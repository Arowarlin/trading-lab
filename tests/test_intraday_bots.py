from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

import tradinglab.orchestrator as orch
from tradinglab.asset_aliases import discover
from tradinglab.config import Settings
from tradinglab.db import init_db
from tradinglab.operator import OperatorError, OperatorService
from tradinglab.orchestrator import BotSpec, load_bots, run_bot
from tradinglab.strategies.base import StrategyResult

INTRADAY_IDS = {
    "nasdaq-orb-ny",
    "nasdaq-trend-intraday",
    "gold-asian-rev",
    "gold-overlap-breakout",
    "eurusd-range-reversal",
    "eurusd-london-pullback",
    "usdjpy-session-trend",
    "usdjpy-tokyo-breakout",
}
ALLOWED_SYMBOLS = {"US100.cash", "XAUUSD", "EURUSD", "USDJPY"}


class FakeSpecBroker:
    def symbol_spec(self, symbol: str) -> dict:
        if symbol in ALLOWED_SYMBOLS:
            return {"symbol": symbol.upper()}
        raise ValueError(f"no existe {symbol}")


def _frame(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = [100 + index * 0.5 for index in range(n)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.4 for value in close],
            "low": [value - 0.4 for value in close],
            "close": close,
            "volume": [1_000_000.0] * n,
        },
        index=idx,
    )


class FakeBroker:
    def __init__(self, positions: list[dict] | None = None) -> None:
        self.positions = positions or []
        self.submitted = 0

    def snapshot(self, prices=None):
        return {
            "cash": 100_000.0,
            "equity": 100_000.0,
            "positions_value": 0.0,
            "positions": self.positions,
        }

    def equity_series(self):
        idx = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
        return pd.Series([100_000.0] * 30, index=idx)

    def submit_market(self, *args, **kwargs):
        self.submitted += 1
        return {"id": self.submitted}


def _make_strategy(target: float):
    def fn(df, **params):
        return StrategyResult("trend", pd.Series(float(target), index=df.index), {})

    return fn


def _settings() -> Settings:
    return Settings(
        mode="paper",
        execution={"broker": "alpaca"},
        risk={"max_position_pct": 0.35},
    )


def _prepare(monkeypatch, tmp_path, target: float) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    discover(db, FakeSpecBroker())
    from tradinglab.asset_aliases import symbol_allowed as real

    monkeypatch.setattr(orch, "symbol_allowed", lambda path, sym: real(db, sym))
    monkeypatch.setattr(orch, "STRATEGIES", {"trend": _make_strategy(target)})
    monkeypatch.setattr(orch, "fetch", lambda *a, **k: _frame())
    monkeypatch.setattr(orch, "_trades_today", lambda *a, **k: 0)
    monkeypatch.setattr(
        orch,
        "ensure_killswitch",
        lambda *a, **k: (SimpleNamespace(active=False, reason=""), False),
    )
    monkeypatch.setattr(
        orch,
        "calendar_block_for_settings",
        lambda *a, **k: SimpleNamespace(blocked=False, reason=""),
    )
    monkeypatch.setattr(
        orch, "session_block", lambda *a, **k: SimpleNamespace(
            blocked=False, reason="", kind="ok"
        )
    )
    monkeypatch.setattr(orch, "allows_order", lambda *a, **k: True)


def test_load_bots_incluye_intraday_sin_tocar_bots_yaml():
    specs = load_bots()
    intra = [spec for spec in specs if spec.profile == "intraday_fx"]
    assert len(intra) == 8
    assert INTRADAY_IDS <= {spec.id for spec in intra}
    assert all(not spec.enabled for spec in intra)
    assert all(spec.yaml_enabled is False for spec in intra)
    assert any(spec.id == "trend-spy" for spec in specs)
    for spec in intra:
        assert spec.timeframe == "M15"
        assert spec.family
        assert spec.grid
        assert spec.universe and all(t in ALLOWED_SYMBOLS for t in spec.universe)
    # Los parámetros no se comparten entre activos.
    assert len({json.dumps(spec.grid, sort_keys=True) for spec in intra}) == 8


def test_guard_bloquea_apertura_fuera_del_universo(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, target=1.0)
    spec = BotSpec(
        id="intra-x",
        type="deterministic",
        strategy="trend",
        universe=["BTCUSD"],
        timeframe="M15",
        enabled=True,
        profile="intraday_fx",
        account="paper_main",
        params={},
        family="orb_ny",
        grid={"range_bars": [4, 8]},
    )
    broker = FakeBroker()
    actions = run_bot(
        spec,
        _settings(),
        broker,
        dry_run=True,
        profile=SimpleNamespace(max_risk_pct=0.35, max_trades_per_day=3),
    )
    assert actions[0].status == "bloqueado"
    assert "universo intraday_fx" in actions[0].detail
    assert broker.submitted == 0


def test_guard_nunca_bloquea_cierre(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, target=0.0)
    spec = BotSpec(
        id="intra-x",
        type="deterministic",
        strategy="trend",
        universe=["BTCUSD"],
        timeframe="M15",
        enabled=True,
        profile="intraday_fx",
        account="paper_main",
        params={},
        family="orb_ny",
        grid={"range_bars": [4, 8]},
    )
    broker = FakeBroker(positions=[{"ticker": "BTCUSD", "qty": 10}])
    actions = run_bot(
        spec,
        _settings(),
        broker,
        dry_run=True,
        profile=SimpleNamespace(max_risk_pct=0.35, max_trades_per_day=3),
    )
    assert actions[0].status == "dry_run"
    assert "universo" not in actions[0].detail


def test_guard_presupuesto_y_noticias_bloquean_apertura(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path, target=1.0)
    spec = BotSpec(
        id="intra-xau",
        type="deterministic",
        strategy="trend",
        universe=["XAUUSD"],
        timeframe="M15",
        enabled=True,
        profile="intraday_fx",
        account="paper_main",
        params={},
        family="overlap_breakout",
        grid={"range_bars": [4, 8]},
    )
    monkeypatch.setattr(
        orch,
        "assess_open",
        lambda *a, **k: {"allowed": False, "reason": "presupuesto test"},
    )
    actions = run_bot(
        spec,
        _settings(),
        FakeBroker(),
        dry_run=True,
        profile=SimpleNamespace(max_risk_pct=0.35, max_trades_per_day=3),
    )
    assert actions[0].status == "bloqueado"
    assert "presupuesto" in actions[0].detail

    monkeypatch.setattr(
        orch,
        "assess_open",
        lambda *a, **k: {"allowed": True, "reason": "ok"},
    )
    monkeypatch.setattr(
        orch,
        "news_blackout",
        lambda *a, **k: {"blocked": True, "reason": "CPI"},
    )
    actions = run_bot(
        spec,
        _settings(),
        FakeBroker(),
        dry_run=True,
        profile=SimpleNamespace(max_risk_pct=0.35, max_trades_per_day=3),
    )
    assert actions[0].status == "bloqueado"
    assert "noticias" in actions[0].detail


def test_operador_rechaza_orden_fuera_del_universo_intraday(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    discover(db, FakeSpecBroker())
    monkeypatch.setattr(
        "tradinglab.market_pilots.allows_market",
        lambda *a, **k: (True, None),
    )
    service = OperatorService(Settings(mode="paper"), db)
    monkeypatch.setattr(
        service,
        "_account_for",
        lambda account_id: SimpleNamespace(
            id="ftmo_demo", pocket="intraday_fx", platform="mt5"
        ),
    )
    with pytest.raises(OperatorError) as info:
        service._plan_order(
            {
                "account": "ftmo_demo",
                "ticker": "BTCUSD",
                "side": "buy",
                "qty": 1.0,
                "price": 90000.0,
                "sl": 89000.0,
            }
        )
    assert "intraday_fx" in str(info.value)
