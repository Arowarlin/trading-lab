"""B-02 (ENG-1): la confirmación por cuenta usa el modelo de coste de la campaña.

Antes ``levels._account_confirmation`` creaba un ``CostBook`` v1 (doble spread y
p75) también en campañas v2. Sin datos de mercado: se intercepta la llamada.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from tradinglab.discovery import costs, dsl, genetic, levels
from tradinglab.propfund.registry import load_registry


def test_confirmacion_por_cuenta_usa_la_version_de_coste_de_la_campana(monkeypatch):
    captured: dict = {}

    def spy(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("spy")

    monkeypatch.setattr(costs, "build_cost_book", spy)
    account = load_registry().accounts["CFD-001"]
    model = dsl.Strategy.model_validate(genetic.template_strategy("trend_pullback_mtf"))
    setup = SimpleNamespace(
        instrument="EURUSD",
        session_tz="America/New_York",
        cost_model_version=2,
        spread_model="hourly_p75",
        account="CFD-001",
    )
    out = levels._account_confirmation(
        account, model, pd.DataFrame(), setup=setup, trial_srs=[], k=1, n_trials=1,
        min_trades=30, random_trials=1, seed=0, costs_db=None,
    )
    assert out["status"] == "NO CONFIRMADA"
    assert captured["cost_model_version"] == 2
    assert captured["spread_model"] == "hourly_p75"
