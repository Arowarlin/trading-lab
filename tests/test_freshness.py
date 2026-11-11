from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

import tradinglab.orchestrator as orch
from tradinglab import clock as clock_mod
from tradinglab.config import Settings
from tradinglab.db import init_db
from tradinglab.freshness import (
    STATUS_AVISO,
    STATUS_FALLA,
    STATUS_OK,
    check,
    record,
    thresholds,
)
from tradinglab.orchestrator import BotSpec, run_bot
from tradinglab.strategies.base import StrategyResult

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def _record_fresh(db, *, symbol="SPY", timeframe="1d", age_s=60.0):
    record(
        symbol,
        timeframe,
        last_bar_utc=NOW - timedelta(days=1),
        fetched_at_utc=NOW - timedelta(seconds=age_s),
        source="yahoo",
        db_path=db,
    )


def test_frescura_ok_aviso_y_falla(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)

    # umbrales por defecto de "1d": aviso 24 h, falla 48 h
    _record_fresh(db, symbol="OK", age_s=60.0)
    _record_fresh(db, symbol="AVISO", age_s=30 * 3600.0)
    _record_fresh(db, symbol="VIEJO", age_s=72 * 3600.0)

    assert check("OK", "1d", NOW, db_path=db)["status"] == STATUS_OK
    assert check("AVISO", "1d", NOW, db_path=db)["status"] == STATUS_AVISO
    assert check("VIEJO", "1d", NOW, db_path=db)["status"] == STATUS_FALLA


def test_sin_datos_es_falla(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    result = check("NUNCA", "1d", NOW, db_path=db)
    assert result["status"] == STATUS_FALLA
    assert "sin datos" in result["reason"]


def test_umbrales_desde_lab_yaml(tmp_path):
    lab = tmp_path / "lab.yaml"
    lab.write_text(
        yaml.safe_dump(
            {
                "freshness": {
                    "M15": {"aviso_s": 300, "falla_s": 900},
                    "1d": {"aviso_s": 60, "falla_s": 120},
                }
            }
        ),
        encoding="utf-8",
    )
    limits = thresholds(lab)
    assert limits["M15"] == (300.0, 900.0)
    assert limits["1d"] == (60.0, 120.0)
    assert "default" in limits


def test_reloj_desviado_avisa_y_falla(monkeypatch):
    monkeypatch.setattr(clock_mod, "ntp_offset_s", lambda *a, **k: 3.0)
    monkeypatch.setattr(clock_mod, "mt5_offset_s", lambda *a, **k: None)
    assert clock_mod.check_clock(now=NOW)["status"] == clock_mod.STATUS_AVISO

    monkeypatch.setattr(clock_mod, "ntp_offset_s", lambda *a, **k: 30.0)
    result = clock_mod.check_clock(now=NOW)
    assert result["status"] == clock_mod.STATUS_FALLA
    assert result["skew_s"] == pytest.approx(30.0)


def test_reloj_sin_fuentes_no_es_fallo(monkeypatch):
    monkeypatch.setattr(clock_mod, "ntp_offset_s", lambda *a, **k: None)
    monkeypatch.setattr(clock_mod, "mt5_offset_s", lambda *a, **k: None)
    result = clock_mod.check_clock(now=NOW)
    assert result["status"] == clock_mod.STATUS_SIN_DATOS


# ------------------------------------------------------------------ gate


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


def _frame() -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-01", periods=200)
    close = [100 + index * 0.5 for index in range(len(idx))]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 0.4 for value in close],
            "low": [value - 0.4 for value in close],
            "close": close,
            "volume": [1_000_000.0] * len(idx),
        },
        index=idx,
    )


def _prepare(monkeypatch, tmp_path, *, target: float = 1.0, held: float = 0.0):
    db = tmp_path / "lab.db"
    init_db(db)

    def strategy(df, **params):
        return StrategyResult("trend", pd.Series(float(target), index=df.index), {})

    monkeypatch.setattr(orch, "DEFAULT_DB", db)
    monkeypatch.setattr(orch, "STRATEGIES", {"trend": strategy})
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
        orch,
        "session_block",
        lambda *a, **k: SimpleNamespace(blocked=False, reason="", kind="ok"),
    )
    monkeypatch.setattr(orch, "allows_order", lambda *a, **k: True)
    monkeypatch.setattr(
        orch,
        "check_clock",
        lambda *a, **k: {
            "status": "ok",
            "reason": "reloj sincronizado",
            "skew_s": 0.1,
            "sources": {},
        },
    )
    monkeypatch.setattr(
        orch,
        "check_freshness",
        lambda symbol, timeframe, *a, **k: check(symbol, timeframe, NOW, db_path=db),
    )
    return db, held


def _spec() -> BotSpec:
    return BotSpec(
        id="gate-test",
        type="deterministic",
        strategy="trend",
        universe=["SPY"],
        timeframe="1d",
        enabled=True,
        profile=None,
        account="paper_main",
        params={},
        exposure=1.0,
    )


def test_apertura_bloqueada_por_datos_viejos(monkeypatch, tmp_path):
    db, _ = _prepare(monkeypatch, tmp_path)
    _record_fresh(db, symbol="SPY", age_s=5 * 24 * 3600.0)
    broker = FakeBroker()
    actions = run_bot(
        _spec(),
        Settings(mode="paper", execution={"broker": "alpaca"}),
        broker,
        dry_run=False,
    )
    assert actions[0].status == "bloqueado"
    assert "datos" in actions[0].detail
    assert broker.submitted == 0


def test_cierre_permitido_con_datos_viejos(monkeypatch, tmp_path):
    db, _ = _prepare(monkeypatch, tmp_path, target=0.0, held=100.0)
    _record_fresh(db, symbol="SPY", age_s=5 * 24 * 3600.0)
    broker = FakeBroker(positions=[{"ticker": "SPY", "qty": 100.0, "value": 10_000.0}])
    actions = run_bot(
        _spec(),
        Settings(mode="paper", execution={"broker": "alpaca"}),
        broker,
        dry_run=False,
    )
    assert actions[0].status != "bloqueado"
    assert "datos" not in actions[0].detail


def test_apertura_bloqueada_por_reloj(monkeypatch, tmp_path):
    db, _ = _prepare(monkeypatch, tmp_path)
    _record_fresh(db, symbol="SPY", age_s=60.0)
    monkeypatch.setattr(
        orch,
        "check_clock",
        lambda *a, **k: {
            "status": "falla",
            "reason": "reloj desviado 30.0 s",
            "skew_s": 30.0,
            "sources": {},
        },
    )
    broker = FakeBroker()
    actions = run_bot(
        _spec(),
        Settings(mode="paper", execution={"broker": "alpaca"}),
        broker,
        dry_run=False,
    )
    assert actions[0].status == "bloqueado"
    assert "reloj" in actions[0].detail
    assert broker.submitted == 0
