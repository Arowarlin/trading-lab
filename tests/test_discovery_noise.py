"""Prueba de ruido de Fase 6 (lenta): 5 campañas sintéticas.

Criterio no circular (decisión del operador):
* media OOS-1 agregada de TODOS los candidatos pre-selección <= 0;
* Spearman medio (fitness IS vs OOS-1 de candidatos) <= 0,3;
* los finalistas se reportan solo como diagnóstico (Fase 7 exige que ninguno
  llegue a nivel 4 con OOS-2/DSR).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tradinglab.config import ROOT
from tradinglab.discovery import campaigns, databank, dsl, engine
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.learning import count_tests

SEGMENTS = {
    "is": ["2023-01-02", "2023-08-31"],
    "oos1": ["2023-09-01", "2023-10-15"],
    "oos2": ["2023-10-16", None],
}
SEEDS = (1, 2, 3, 4, 5)


@pytest.mark.slow
def test_noise_five_campaigns(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    lab = tmp_path / "lab.db"
    databank.init_databank(db)
    before = count_tests(lab, discovery_db=db)
    rows = []
    for seed in SEEDS:
        frame = synthetic_frame(years=0.9, seed=seed)
        campaign_id = f"noise-{seed}"
        campaigns.register_synthetic(
            frame,
            template="ny_open_vol_filter",
            profile="small",
            segments=SEGMENTS,
            seed=seed,
            campaign_id=campaign_id,
            db_path=db,
        )
        summary = engine.run_campaign(
            campaign_id,
            workers=12,
            synthetic=True,
            db_path=db,
            bars=frame,
        )
        rows.append((seed, summary))
        fitness = summary["frontier_fitness_mean"] or []
        print(
            f"seed={seed} feasible={summary['feasible']} "
            f"frontier={summary['frontier']} "
            f"fitness={[round(value, 5) for value in fitness]} "
            f"candidates={summary['candidates']} "
            f"candidate_oos1={summary['candidates_oos1_mean']} "
            f"spearman={summary['spearman_is_oos1']:.3f} "
            f"finalists={len(summary['finalists'])} "
            f"finalist_oos1={summary['oos1_mean']} "
            f"positive={summary['oos1_positive']}"
        )
    after = count_tests(lab, discovery_db=db)
    assert before == after == 0

    assert all(summary["feasible"] > 0 for _seed, summary in rows)
    total = sum(summary["candidates_oos1_total"] for _seed, summary in rows)
    weighted = sum(
        (summary["candidates_oos1_mean"] or 0.0)
        * summary["candidates_oos1_total"]
        for _seed, summary in rows
    )
    aggregate = weighted / total if total else 0.0
    spearman = float(
        np.mean([summary["spearman_is_oos1"] for _seed, summary in rows])
    )
    print(
        f"aggregate candidate OOS-1={aggregate:.5f} over {total} candidates; "
        f"mean Spearman={spearman:.3f}"
    )
    assert aggregate <= 0.0
    assert spearman <= 0.3


def test_noise_seed2_finalists_fixture() -> None:
    path = ROOT / "tests" / "fixtures" / "discovery_noise_seed2_finalists.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["seed"] == 2
    assert len(payload["finalists"]) == 1
    for item in payload["finalists"]:
        assert dsl.validate(item["dsl"]) == []
        assert item["strategy_hash"] == dsl.strategy_hash(item["dsl"])
    assert payload["note"].lower().startswith("finalistas")

