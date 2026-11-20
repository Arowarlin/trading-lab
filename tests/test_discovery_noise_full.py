"""Prueba de ruido completa de Fase 7 (slow): fixtures + pipeline + OOS-2.

Regenera las campañas sintéticas con su semilla para usar la frontera final
completa (PBO ≥ 8 estrategias) y pasa los finalistas de los fixtures por
retest/robustness/levels/confirm. NINGUNO puede llegar a nivel 4.
"""

from __future__ import annotations

import json

import pytest

from tradinglab.config import ROOT
from tradinglab.discovery import (
    campaigns,
    databank,
    engine,
    levels,
    robustness,
)
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.engine import synthetic_frame

FIXTURES = {
    "1y": {
        "path": ROOT / "tests" / "fixtures" / "discovery_noise_seed2_finalists.json",
        "years": 1.0,
        "segments": {
            "is": ["2023-01-02", "2023-09-30"],
            "oos1": ["2023-10-01", "2023-11-30"],
            "oos2": ["2023-12-01", None],
        },
    },
    "09y": {
        "path": ROOT
        / "tests"
        / "fixtures"
        / "discovery_noise_09y_seed2_finalists.json",
        "years": 0.9,
        "segments": {
            "is": ["2023-01-02", "2023-08-31"],
            "oos1": ["2023-09-01", "2023-10-15"],
            "oos2": ["2023-10-16", None],
        },
    },
}


@pytest.mark.slow
def test_full_noise_pipeline_never_level4(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    rows = []
    for label, spec in FIXTURES.items():
        payload = json.loads(spec["path"].read_text(encoding="utf-8"))
        fixture_hashes = {
            item["strategy_hash"] for item in payload["finalists"]
        }
        frame = synthetic_frame(years=spec["years"], seed=2)
        campaign_id = f"noise-full-{label}"
        campaigns.register_synthetic(
            frame,
            template="ny_open_vol_filter",
            profile="small",
            segments=spec["segments"],
            seed=2,
            campaign_id=campaign_id,
            db_path=db,
        )
        engine.run_campaign(
            campaign_id,
            workers=12,
            synthetic=True,
            db_path=db,
            bars=frame,
        )
        for item in payload["finalists"]:
            strategy_id = databank.add_strategy(
                campaign_id,
                item["dsl"],
                family="ny_open_vol_filter",
                generation=0,
                origin="template",
                status="finalist",
                db_path=db,
            )
            databank.set_strategy_selection(
                strategy_id,
                "finalist",
                item.get("selection_reason") or "finalista (fixture)",
                db_path=db,
            )
        databank.set_campaign_counts(
            campaign_id,
            n_finalists=len(payload["finalists"]),
            db_path=db,
        )
        for strategy in databank.list_strategies(
            campaign_id=campaign_id, limit=None, db_path=db
        ):
            if (
                strategy["status"] == "finalist"
                and strategy["strategy_hash"] not in fixture_hashes
            ):
                databank.set_strategy_selection(
                    strategy["id"],
                    "discarded",
                    "fuera del fixture de ruido de Fase 7",
                    db_path=db,
                )
        finalists = {
            row["strategy_hash"]: row
            for row in databank.list_strategies(
                campaign_id=campaign_id,
                status="finalist",
                limit=None,
                db_path=db,
            )
        }
        robust = {}
        evaluations = {}
        for item in payload["finalists"]:
            row = finalists[item["strategy_hash"]]
            robust[item["strategy_hash"]] = robustness.run(
                row["id"], frame=frame, db_path=db
            )
            evaluations[item["strategy_hash"]] = levels.evaluate(
                row["id"], db_path=db
            )
        # Confirmar solo después de que TODOS los finalistas tengan sus series
        # IS+OOS-1 guardadas: el DSR de confirmación usa K fijo y no depende
        # del orden de lectura.
        for item in payload["finalists"]:
            row = finalists[item["strategy_hash"]]
            result = robust[item["strategy_hash"]]
            evaluation = evaluations[item["strategy_hash"]]
            oos2 = None
            dsr = None
            level = evaluation["level"]
            verdict = evaluation["verdict"]
            if level >= 3:
                confirmed = levels.confirm(
                    row["id"],
                    approved_by_operator=True,
                    frame=frame,
                    db_path=db,
                    learning_db=tmp_path / "lab.db",
                )
                oos2 = confirmed["oos2_expectancy_r"]
                dsr = confirmed["dsr_confirm"].get("dsr")
                level = confirmed["level"]
                verdict = confirmed["verdict"]
            rows.append(
                {
                    "label": label,
                    "hash": item["strategy_hash"][:12],
                    "random": result["validations"]["test_vs_random"].get(
                        "percentile"
                    ),
                    "oos2": oos2,
                    "dsr": dsr,
                    "pbo": result["validations"]["pbo"].get("pbo"),
                    "level": level,
                    "verdict": verdict,
                    "k": len(payload["finalists"]),
                }
            )
    print(
        "finalista | test_vs_random | OOS-2 | DSR confirm | PBO | nivel | veredicto"
    )
    for row in rows:
        print(
            f"{row['label']} {row['hash']} | "
            f"{row['random']} | "
            f"{row['oos2'] if row['oos2'] is not None else 'no leído'} | "
            f"{row['dsr'] if row['dsr'] is not None else 'Sin datos'} | "
            f"{row['pbo']} | {row['level']} | {row['verdict']}"
        )
    config = load_engine_config().robustness
    assert rows
    assert all(row["pbo"] is not None for row in rows)
    assert all(row["level"] < 4 for row in rows)
    assert all(row["verdict"] != "ROBUSTA" for row in rows)
    assert any(row["level"] >= 3 for row in rows)
    assert any(row["oos2"] is not None for row in rows)
    assert any(row["dsr"] is not None for row in rows)
    assert config.pbo_min_strategies == 8
    # Las lecturas de OOS-2 sintéticas no cuentan: campañas sin approved_at.
    assert campaigns.discovery_tests(db)["total"] == 0
