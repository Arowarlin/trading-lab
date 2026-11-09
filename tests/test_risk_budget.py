from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradinglab.db import init_db
from tradinglab.intel.calendar import add_calendar_event
from tradinglab.risk_budget import (
    RiskBudgetError,
    assess_open,
    asset_entry,
    effective_slice,
    load_budget,
    net_risk_by_asset,
    news_blackout,
    revert_slice,
    set_bot_slice,
    slice_history,
    usd_cluster_state,
)


def _position(symbol: str, qty: float, risk: float) -> dict:
    return {"ticker": symbol, "qty": qty, "risk_usd": risk, "value": 0.0}


def test_budget_por_activo_y_alias():
    budget = load_budget()
    assert budget["assets"]["NASDAQ"]["symbol"] == "US100.cash"
    assert asset_entry("US100.cash")["canonical"] == "NASDAQ"
    assert asset_entry("EURUSD")["canonical"] == "EURUSD"
    assert asset_entry("BTCUSD") is None


def test_neto_por_activo_compensa_largos_y_cortos():
    positions = [
        _position("EURUSD", 1, 1_000.0),
        _position("EURUSD", -1, 400.0),
        _position("XAUUSD", 1, 500.0),
    ]
    net = net_risk_by_asset(positions)
    assert net["EURUSD"] == pytest.approx(600.0)
    assert net["XAUUSD"] == pytest.approx(500.0)


def test_presupuesto_activo_bloquea_apertura():
    equity = 100_000.0
    result = assess_open(
        "unused.db",
        symbol="EURUSD",
        side="buy",
        proposed_risk_usd=300.0,
        equity=equity,
        positions=[_position("EURUSD", 1, 800.0)],
    )
    assert result["allowed"] is False
    assert "presupuesto" in result["reason"]
    # El corto compensa y sí cabe.
    result = assess_open(
        "unused.db",
        symbol="EURUSD",
        side="sell",
        proposed_risk_usd=300.0,
        equity=equity,
        positions=[_position("EURUSD", 1, 800.0)],
    )
    assert result["allowed"] is True
    assert result["net_after"] == pytest.approx(500.0)


def test_rebanada_por_bot_bloquea(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    # initial 0.25% de 100k = 250; 300 > 250.
    result = assess_open(
        db,
        symbol="EURUSD",
        side="buy",
        proposed_risk_usd=300.0,
        equity=100_000.0,
        positions=[],
        bot="eurusd-range-reversal",
    )
    assert result["allowed"] is False
    assert "rebanada" in result["reason"]
    result = assess_open(
        db,
        symbol="EURUSD",
        side="buy",
        proposed_risk_usd=200.0,
        equity=100_000.0,
        positions=[],
        bot="eurusd-range-reversal",
    )
    assert result["allowed"] is True


def test_tope_total_y_cluster_usd():
    equity = 100_000.0
    # Dos activos con 900 de riesgo neto + 300 propuesto = 2100 > 2% (2000).
    positions = [
        _position("XAUUSD", 1, 900.0),
        _position("US100.cash", 1, 900.0),
    ]
    result = assess_open(
        "unused.db",
        symbol="EURUSD",
        side="buy",
        proposed_risk_usd=300.0,
        equity=equity,
        positions=positions,
    )
    assert result["allowed"] is False
    assert "total" in result["reason"]
    # Clúster USD: EURUSD largo 900 y USDJPY corto 900 = 1800 de peor caso;
    # 100 más supera el tope 1,5% (1500).
    cluster_positions = [
        _position("EURUSD", 1, 900.0),
        _position("USDJPY", -1, 900.0),
    ]
    state = usd_cluster_state(cluster_positions)
    assert state["worst_risk_usd"] == pytest.approx(1_800.0)
    result = assess_open(
        "unused.db",
        symbol="EURUSD",
        side="buy",
        proposed_risk_usd=100.0,
        equity=equity,
        positions=cluster_positions,
    )
    assert result["allowed"] is False
    assert "cluster" in result["reason"]


def test_rebanada_subir_bajar_historial_y_reversion(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    lower = set_bot_slice(
        db,
        asset="EURUSD",
        bot="eurusd-range-reversal",
        slice_pct=0.001,
        reason="arranque",
    )
    assert lower["action"] == "lower"
    assert effective_slice(db, "EURUSD", "eurusd-range-reversal")["pct"] == pytest.approx(
        0.001
    )
    with pytest.raises(RiskBudgetError, match="armado"):
        set_bot_slice(
            db,
            asset="EURUSD",
            bot="eurusd-range-reversal",
            slice_pct=0.002,
            confirm=True,
        )
    raised = set_bot_slice(
        db,
        asset="EURUSD",
        bot="eurusd-range-reversal",
        slice_pct=0.002,
        armed=True,
        confirm=True,
    )
    assert raised["action"] == "raise"
    reverted = revert_slice(db, raised["id"])
    assert effective_slice(db, "EURUSD", "eurusd-range-reversal")["pct"] == pytest.approx(
        0.001
    )
    assert any(row["action"] == "revert" for row in slice_history(db))
    assert reverted["history_id"]


def test_rebanada_rechaza_f13_congelado(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr(
        "tradinglab.f13.status",
        lambda path: {"bot": "qqq-trend-f13"},
    )
    with pytest.raises(RiskBudgetError, match="F13"):
        set_bot_slice(
            db,
            asset="EURUSD",
            bot="qqq-trend-f13",
            slice_pct=0.004,
            armed=True,
            confirm=True,
        )


def test_apagon_noticias_por_evento(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    now = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)
    add_calendar_event(
        db,
        event="US CPI",
        ts_utc=now + timedelta(minutes=10),
        importance="high",
        source="test",
    )
    result = news_blackout(db, "EURUSD", now=now)
    assert result["blocked"] is True
    assert "CPI" in result["reason"]
    result = news_blackout(db, "USDJPY", now=now)
    assert result["blocked"] is True
    # Fuera de la ventana no bloquea.
    assert news_blackout(db, "EURUSD", now=now + timedelta(hours=3))["blocked"] is False


def test_apagon_sin_datos_es_sin_datos(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    result = news_blackout(db, "EURUSD", now=datetime.now(timezone.utc))
    assert result["blocked"] is False
    assert result["data_ok"] is False
