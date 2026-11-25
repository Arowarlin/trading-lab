"""T22 · Protocolo v2: LCB, holdout y arnés."""

from __future__ import annotations

from datetime import date

import numpy as np

from tradinglab.discovery import harness, protocol_v2


def test_lcb_desarrollo_positivo_y_nulo():
    rng = np.random.default_rng(11)
    positive = protocol_v2.lcb_dev(rng.normal(0.1, 1.0, 5000))
    assert positive["lcb"] > 0
    null = protocol_v2.lcb_dev(rng.normal(0.0, 1.0, 5000))
    assert null["lcb"] < 0


def test_holdout_aprueba_con_ventaja_y_rechaza_nulo():
    dev = protocol_v2.lcb_dev(np.full(5000, 0.1))
    approved = protocol_v2.holdout_decision(
        np.random.default_rng(11).normal(0.1, 1.0, 5000), dev["lcb"]
    )
    assert approved["approved"] is True
    rejected = protocol_v2.holdout_decision(
        np.random.default_rng(7).normal(0.0, 1.0, 5000), dev["lcb"]
    )
    assert rejected["approved"] is False


def test_holdout_exige_consistencia_con_el_lcb():
    dev = protocol_v2.lcb_dev(np.full(1000, 0.3))
    # Media positiva y t alto, pero muy por debajo del LCB de desarrollo.
    values = np.random.default_rng(3).normal(0.05, 0.01, 500)
    verdict = protocol_v2.holdout_decision(values, dev["lcb"])
    assert verdict["approved"] is False
    assert "LCB_dev" in verdict["reason"]


def test_arnes_v2_nulo_y_potencia():
    years = harness.segment_years(today=date(2026, 11, 24))
    null = harness.simulate_gates(
        frequency=1000, edge=0.0, simulations=1000, seed=7,
        years=years, protocol="v2",
    )
    assert null.p_approve < 0.05
    v1 = harness.simulate_gates(
        frequency=1000, edge=0.1, simulations=1000, seed=7,
        years=years, protocol="v1",
    )
    v2 = harness.simulate_gates(
        frequency=1000, edge=0.1, simulations=1000, seed=7,
        years=years, protocol="v2",
    )
    assert v2.p_approve > v1.p_approve


def test_campana_nueva_guarda_holdout_start(tmp_path):
    from tradinglab.discovery import campaigns, engine

    frame = engine.synthetic_frame(years=0.5, seed=17)
    preview = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments={
            "is": ["2023-01-02", "2023-04-30"],
            "oos1": ["2023-05-01", "2023-05-31"],
            "oos2": ["2023-06-01", None],
        },
        frame=frame,
        campaign_id="v2",
        dry_run=True,
        db_path=tmp_path / "discovery.db",
    )
    assert preview["config"]["protocol_version"] == 2
    assert preview["config"]["holdout_start"] == "2025-07-01"


def test_register_con_protocol_version_none_es_coherente(tmp_path):
    from tradinglab.discovery import campaigns, engine

    frame = engine.synthetic_frame(years=0.5, seed=17)
    segments = {
        "is": ["2023-01-02", "2023-04-30"],
        "oos1": ["2023-05-01", "2023-05-31"],
        "oos2": ["2023-06-01", None],
    }
    preview = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=segments,
        frame=frame,
        campaign_id="v2-none",
        dry_run=True,
        primary={"stop": 2.0},
        db_path=tmp_path / "discovery.db",
    )
    config = preview["config"]
    assert config["protocol_version"] == 2
    assert config["primary"] == {"stop": 2.0}
    assert config["plateau_n"] == config["n_total"] - 1
    assert config["decision_n_total"] == 1

    v1 = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=segments,
        frame=frame,
        campaign_id="v1-none",
        dry_run=True,
        primary={"stop": 2.0},
        protocol_version=1,
        db_path=tmp_path / "discovery.db",
    )
    assert v1["config"]["protocol_version"] == 1
    assert v1["config"]["plateau_n"] == 0
    assert v1["config"]["decision_n_total"] is None
