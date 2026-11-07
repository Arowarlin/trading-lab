from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from tradinglab.config import RiskSettings
from tradinglab.killswitch import KillSwitchState, allows_order, ensure, evaluate, load_state, reset


def _cfg(**overrides) -> RiskSettings:
    base = {"daily_loss_limit_pct": 0.03, "max_drawdown_pct": 0.50}
    base.update(overrides)
    return RiskSettings(**base)


def test_activa_por_perdida_diaria():
    idx = pd.date_range("2026-11-05 15:00", periods=3, freq="h", tz="UTC")
    eq = pd.Series([100_000, 99_000, 96_000], index=idx)
    ev = evaluate(
        eq,
        _cfg(),
        tz="UTC",
        now=datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc),
    )
    assert ev.active
    assert "diaria" in ev.reason
    assert ev.day_start == pytest.approx(100_000)


def test_activa_por_drawdown():
    ev = evaluate(
        pd.Series([100.0, 110.0, 120.0, 90.0]),
        _cfg(daily_loss_limit_pct=0.5, max_drawdown_pct=0.10),
    )
    assert ev.active
    assert "drawdown" in ev.reason
    assert ev.drawdown == pytest.approx(-0.25)


def test_equity_actual_manda_sobre_ultimo_snapshot():
    eq = pd.Series([100_000.0, 100_000.0, 100_000.0])
    ev = evaluate(eq, _cfg(), current=96_000, tz="UTC")
    assert ev.active
    assert ev.equity == pytest.approx(96_000)


def test_persiste_y_no_se_desactiva_al_recuperar(tmp_path):
    db = tmp_path / "lab.db"
    idx = pd.date_range("2026-11-05 15:00", periods=3, freq="h", tz="UTC")
    eq = pd.Series([100_000, 100_000, 96_000], index=idx)
    state, ev = ensure(
        db,
        eq,
        _cfg(),
        tz="UTC",
        now=datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc),
    )
    assert ev.active
    assert state.active
    assert state.triggered_at

    recuperado = pd.Series([100_000.0, 100_000.0])
    state2, ev2 = ensure(db, recuperado, _cfg(), tz="UTC")
    assert not ev2.active
    assert state2.active
    assert load_state(db).active


def test_permite_cerrar_pero_no_abrir():
    active = KillSwitchState(True, "drawdown")
    assert not allows_order(active, 10)
    assert allows_order(active, -10)
    assert allows_order(active, 0)
    assert allows_order(KillSwitchState(False, "inactivo"), 10)


def test_reset_exige_confirmacion(tmp_path):
    db = tmp_path / "lab.db"
    idx = pd.date_range("2026-11-05 15:00", periods=2, freq="h", tz="UTC")
    ensure(db, pd.Series([100_000, 96_000], index=idx), _cfg(), tz="UTC")

    with pytest.raises(ValueError):
        reset(db, confirm=False)
    assert load_state(db).active

    state = reset(db, confirm=True)
    assert not state.active
    assert state.reset_at
