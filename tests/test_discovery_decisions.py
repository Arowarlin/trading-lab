"""T01 · Equivalencia del refactor de decisiones con el baseline previo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradinglab.discovery import decisions, engine

FIXTURE = Path(__file__).parent / "fixtures" / "decisions_baseline.json"


def _baseline() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _individual(row: dict) -> engine.Individual:
    return engine.Individual(
        strategy={},
        strategy_hash=str(row["id"]),
        rank=int(row.get("rank", 0)),
        feasible=bool(row.get("feasible", True)),
        metrics={
            "is": {"expectancy_r": row.get("is")},
            "drift": row.get("drift") or {},
        },
        folds=[{"expectancy_r": value} for value in row.get("folds") or []],
        complexity=0,
    )


def test_rank1_candidates_identico_al_baseline():
    data = _baseline()
    population = [_individual(row) for row in data["population"]]
    candidates, discarded = engine._rank1_candidates(population, int(data["folds"]))
    assert [item.strategy_hash for item in candidates] == data["baseline"]["candidates"]
    assert [[item.strategy_hash, reason] for item, reason in discarded] == data[
        "baseline"
    ]["discarded"]


def test_select_finalists_identico_al_baseline():
    data = _baseline()
    by_id = {row["id"]: _individual(row) for row in data["population"]}
    by_id.update(
        {
            name: _individual(
                {
                    "id": name,
                    "rank": 0,
                    "feasible": True,
                    "is": 0.2,
                    "drift": {"percentile": 95.0, "percentile_min": 90.0},
                    "folds": [0.1, 0.1, 0.1, 0.1],
                }
            )
            for name in data["select_candidates"]
        }
    )
    selected_input = [by_id[name] for name in data["select_candidates"]]
    oos1 = {id(item): data["oos1"][item.strategy_hash] for item in selected_input}
    selected, discarded = engine._select_finalists(
        selected_input,
        oos1,
        finalists_max=int(data["finalists_max"]),
        corr_cluster=float(data["corr_cluster"]),
    )
    assert [item.strategy_hash for item in selected] == data["baseline"]["selected"]
    assert [[item.strategy_hash, reason] for item, reason in discarded] == data[
        "baseline"
    ]["select_discarded"]


def _old_level3(
    *,
    is_finalist,
    is_expectancy,
    cost_x1_5,
    perturb_noise_ok,
    perturb_delay_ok,
    perturb_execution_ok,
) -> bool:
    return bool(
        is_finalist
        and is_expectancy is not None
        and float(is_expectancy) > 0.0
        and cost_x1_5 is not None
        and float(cost_x1_5) > 0.0
        and perturb_noise_ok
        and perturb_delay_ok
        and perturb_execution_ok
    )


def _old_level4(
    *,
    level3,
    enough_oos2,
    oos2,
    dsr_confirm,
    pbo,
    wf_ok,
    regime_ok,
    slip2,
    challenge_ok,
    random_oos2,
) -> bool:
    return bool(
        level3
        and enough_oos2
        and oos2 is not None
        and float(oos2) > 0.0
        and dsr_confirm is not None
        and float(dsr_confirm) >= 0.90
        and pbo is not None
        and float(pbo) <= 0.30
        and wf_ok is True
        and regime_ok is True
        and slip2 is not None
        and float(slip2) > 0.0
        and challenge_ok is True
        and random_oos2 is not None
        and float(random_oos2) >= 95.0
    )


@pytest.mark.parametrize("is_finalist", [False, True])
@pytest.mark.parametrize("is_expectancy", [None, -0.1, 0.2])
@pytest.mark.parametrize("cost_x1_5", [None, -0.1, 0.1])
@pytest.mark.parametrize("perturb_ok", [False, True])
def test_level3_equivale_a_la_expresion_anterior(
    is_finalist, is_expectancy, cost_x1_5, perturb_ok
):
    kwargs = {
        "is_finalist": is_finalist,
        "is_expectancy": is_expectancy,
        "cost_x1_5": cost_x1_5,
        "perturb_noise_ok": perturb_ok,
        "perturb_delay_ok": perturb_ok,
        "perturb_execution_ok": perturb_ok,
    }
    assert decisions.level3_ok(**kwargs) == _old_level3(**kwargs)


_LEVEL4_CASES = [
    {
        "level3": False, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": False, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": -0.1, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.89,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.31, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": False, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": False, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": -0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": False, "random_oos2": 96.0,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 94.9,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": None,
    },
    {
        "level3": True, "enough_oos2": True, "oos2": 0.2, "dsr_confirm": 0.95,
        "pbo": 0.1, "wf_ok": True, "regime_ok": True, "slip2": 0.1,
        "challenge_ok": True, "random_oos2": 96.0,
    },
]


@pytest.mark.parametrize("kwargs", _LEVEL4_CASES)
def test_level4_equivale_a_la_expresion_anterior(kwargs):
    assert decisions.level4_ok(**kwargs) == _old_level4(**kwargs)
