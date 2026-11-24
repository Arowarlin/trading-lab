"""C2 · Versión de coste en edge map, optimizador y onboarding."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tradinglab.discovery import edge_map, jobs, optimizer
from tradinglab.discovery.costs import default_cost_model_version
from tradinglab.discovery.fastbt import RunLimits
from tradinglab.propfund import onboarding


def test_default_version_es_dos():
    assert default_cost_model_version() == 2


def test_campana_guardada_conserva_su_version():
    old = {
        "id": "vieja",
        "instrument": "US100",
        "timeframe": "M5",
        "config": {"cost": {"account": "CFD-001"}},
    }
    assert jobs.QueueSetup.from_campaign(old).cost_model_version == 1
    new = {
        "id": "nueva",
        "instrument": "US100",
        "timeframe": "M5",
        "config": {"cost": {"account": "CFD-001"}, "cost_model_version": 2},
    }
    assert jobs.QueueSetup.from_campaign(new).cost_model_version == 2


def test_edge_map_respeta_la_version():
    assert edge_map._cost_version(1) == 1
    assert edge_map._cost_version(2) == 2
    assert edge_map._cost_version(None) == 2


def test_optimizer_usa_default_sin_campana(monkeypatch):
    seen: list[int] = []

    def fake_metrics(strategy, bars, cost, setup, prepared, *, cache):
        seen.append(setup.cost_model_version)
        return {"expectancy_r": 0.1, "profit_factor": 1.2, "max_dd_r": -0.1, "trades": 10}

    monkeypatch.setattr(optimizer, "_metrics", fake_metrics)
    setup = jobs.QueueSetup(instrument="US100", timeframe="M5")
    optimizer.plateau(
        {
            "exit": {
                "stop": {"type": "atr", "mult": 1.0},
                "target": {"type": "rr", "rr": 2.0},
            },
            "session": {"start": "09:00", "end": "17:00"},
            "limits": {},
        },
        pd.DataFrame(),
        cost=None,
        setup=setup,
        prepared=None,
    )
    assert seen and all(version == 2 for version in seen)


def test_optimizer_conserva_version_de_campana(monkeypatch):
    seen: list[int] = []

    def fake_metrics(strategy, bars, cost, setup, prepared, *, cache):
        seen.append(setup.cost_model_version)
        return {"expectancy_r": 0.1, "profit_factor": 1.2, "max_dd_r": -0.1, "trades": 10}

    monkeypatch.setattr(optimizer, "_metrics", fake_metrics)
    setup = jobs.QueueSetup(
        instrument="US100", timeframe="M5", campaign_id="vieja", cost_model_version=1
    )
    optimizer.plateau(
        {
            "exit": {
                "stop": {"type": "atr", "mult": 1.0},
                "target": {"type": "rr", "rr": 2.0},
            },
            "session": {"start": "09:00", "end": "17:00"},
            "limits": {},
        },
        pd.DataFrame(),
        cost=None,
        setup=setup,
        prepared=None,
    )
    assert seen and all(version == 1 for version in seen)


def test_onboarding_respeta_la_version_de_los_limites():
    for version in (1, 2):
        run = {"limits": RunLimits(cost_model_version=version)}
        assert onboarding._run_cost_version(run) == version
    run = {"limits": RunLimits(cost_model_version=0)}
    assert onboarding._run_cost_version(run) == 2


def test_baseline_onboarding_v1_existe():
    path = Path(__file__).parent / "fixtures" / "baselines" / "onboarding_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert set(payload["accounts"]) == {"CFD-001", "CFD-006"}
    assert all(payload["accounts"][account]["rows"] for account in payload["accounts"])
