"""ENG-1 B-03: la validación usa el mismo modelo de coste que la selección.

Con puertas v3 y una campaña con ``cost_accounts`` (no legacy), robustez,
perturbación y confirmación usan el ``CostBook`` de la campaña y aplican el
coste operación a operación, como ``jobs._init_worker``. Con v2 (o una campaña
legacy) nada cambia: el perfil de una cuenta. Todo sintético.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import costs, fastbt, perturb
from tradinglab.discovery.config import load_engine_config


def _config(version: int):
    base = load_engine_config()
    return base.model_copy(
        update={"robustness": base.robustness.model_copy(update={"gates_version": version})}
    )


def _setup(**extra):
    data = dict(
        account="CFD-006", instrument="US100", firm=None, use_p75=False,
        cost_model_version=2, legacy_cost=False, cost_accounts=("CFD-006",),
        cost_mode="best", session_tz="America/New_York", spread_model=None, point=0.01,
    )
    data.update(extra)
    return SimpleNamespace(**data)


@pytest.fixture
def stubs(monkeypatch):
    calls = {"book": 0, "profile": 0}

    def fake_book(setup):
        calls["book"] += 1
        return "BOOK"

    def fake_profile(account, instrument, firm=None):
        calls["profile"] += 1
        return SimpleNamespace(account=account)

    monkeypatch.setattr(costs, "build_cost_book_for_setup", fake_book)
    monkeypatch.setattr(costs, "load_profile", fake_profile)
    monkeypatch.setattr(costs.fastbt, "cost_from_profile", lambda profile, **kw: ("PROFILE", kw))
    return calls


def test_v2_conserva_el_perfil_de_una_cuenta(monkeypatch, stubs):
    monkeypatch.setattr(costs, "load_engine_config", lambda: _config(2))
    out = costs.validation_cost(_setup())
    assert out[0] == "PROFILE" and stubs == {"book": 0, "profile": 1}
    assert out[1] == {"use_p75": False, "cost_model_version": 2}


def test_v3_usa_el_costbook_de_la_campana(monkeypatch, stubs):
    monkeypatch.setattr(costs, "load_engine_config", lambda: _config(3))
    assert costs.validation_cost(_setup()) == "BOOK"
    assert stubs == {"book": 1, "profile": 0}


def test_v3_con_campana_legacy_no_cambia(monkeypatch, stubs):
    monkeypatch.setattr(costs, "load_engine_config", lambda: _config(3))
    out = costs.validation_cost(_setup(legacy_cost=True))
    assert out[0] == "PROFILE" and stubs["book"] == 0


def _fake(account: str, values: list[float]) -> SimpleNamespace:
    array = np.asarray(values, dtype=float)
    panel = fastbt.CostPanel(
        spread_bps=array.copy(), slip_bps=np.zeros_like(array), comm_bps=np.zeros_like(array),
        legacy_entry_bps=array, legacy_stop_bps=array.copy(), legacy_target_bps=np.zeros_like(array),
    )
    return SimpleNamespace(
        account=account, instrument="US100", assumed_slippage=1.0,
        slippage_source="assumption", panel=lambda bars: panel,
        profile=SimpleNamespace(slippage_price=1.5 if account == "A" else 2.5),
    )


def _trade() -> fastbt.Trade:
    return fastbt.Trade(
        side="long", entry_index=0, exit_index=2,
        entry_time=pd.Timestamp("2024-01-10 15:00", tz="UTC"),
        exit_time=pd.Timestamp("2024-01-10 15:30", tz="UTC"),
        entry_price=100.0, exit_price=101.0, stop=99.0, target=None, reason="force_exit",
        bars_held=6, risk_price=1.0, entry_cost_bps=0.0, exit_cost_bps=0.0,
        r_gross=0.5, r_cost=0.0, r_net=0.5,
    )


def test_applied_result_aplica_el_libro_por_operacion():
    # Selección (best) cobra 0,02 R por operación; el panel envolvente de
    # fastbt.run con min por vela no es lo que ve la selección.
    book = costs.CostBook(
        [_fake("A", [20.0, 1.0, 0.0]), _fake("B", [1.0, 1.0, 1.0])], mode="best", session_tz="UTC"
    )
    bars = pd.DataFrame(
        {"open": [100.0] * 3, "high": [101.0] * 3, "low": [99.0] * 3, "close": [100.0] * 3},
        index=pd.date_range("2024-01-10 15:00", periods=3, freq="5min", tz="UTC"),
    )
    book.panel(bars)
    raw = fastbt.FastResult(trades=[_trade()], daily_r=pd.Series(dtype=float), metrics={"x": 1})
    out = costs.applied_result(raw, book, session_tz="UTC", point=0.01)
    assert out.trades[0].r_cost == pytest.approx(0.02)
    assert out.metrics["best_account"] == "B" and "x" not in out.metrics


def test_applied_result_sin_costbook_devuelve_lo_mismo():
    raw = fastbt.FastResult(trades=[_trade()], daily_r=pd.Series(dtype=float), metrics={"x": 1})
    assert costs.applied_result(raw, ("PROFILE", {}), session_tz="UTC", point=0.01) is raw


def test_default_slippage_con_costbook_toma_el_mayor():
    book = costs.CostBook([_fake("A", [1.0]), _fake("B", [1.0])], mode="best", session_tz="UTC")
    assert perturb.default_slippage(book) == pytest.approx(2.5)
    single = SimpleNamespace(profile=SimpleNamespace(slippage_price=1.2))
    assert perturb.default_slippage(single) == pytest.approx(1.2)
