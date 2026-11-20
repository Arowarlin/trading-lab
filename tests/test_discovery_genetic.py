"""Operadores genéticos: validez, límites y reproducibilidad."""

from __future__ import annotations

import copy
import random

import pytest

from tradinglab.discovery import dsl, genetic


@pytest.mark.parametrize("operator", genetic.MUTATIONS)
def test_each_mutation_returns_valid_or_none(operator) -> None:
    base = genetic.template_strategy("ny_open_vol_filter")
    for seed in range(12):
        rng = random.Random(seed)
        result = operator(copy.deepcopy(base), rng)
        if result is None:
            continue
        assert dsl.validate(result) == []
        assert dsl.depth(result) <= 4
        assert dsl.count_nodes(result) <= 12


def test_crossovers_return_valid_or_none() -> None:
    rng = random.Random(3)
    left = genetic.random_strategy(rng, "ny_open_vol_filter")
    right = genetic.random_strategy(rng, "ny_open_vol_filter")
    assert left is not None and right is not None
    for operator in (genetic.crossover_subtree, genetic.crossover_exit):
        child = operator(copy.deepcopy(left), copy.deepcopy(right), rng)
        if child is not None:
            assert dsl.validate(child) == []


def test_random_strategy_is_reproducible() -> None:
    first = genetic.random_strategy(random.Random(11), "ny_open_vol_filter")
    second = genetic.random_strategy(random.Random(11), "ny_open_vol_filter")
    assert first is not None and second is not None
    assert dsl.strategy_hash(first) == dsl.strategy_hash(second)


def test_random_strategy_uses_campaign_instrument() -> None:
    session = {
        "tz": "America/New_York",
        "start": "09:35",
        "end": "11:30",
        "flat_at": "15:45",
        "or_minutes": 15,
    }
    strategy = genetic.random_strategy(
        random.Random(7),
        "ny_open_vol_filter",
        instrument="US100.CASH",
        timeframe="M5",
        session=session,
    )
    assert strategy is not None
    assert strategy["instrument"] == "US100.CASH"
    assert strategy["timeframe"] == "M5"
    assert strategy["session"]["tz"] == "America/New_York"
    assert dsl.validate(strategy) == []


def test_diff_detects_changes() -> None:
    base = genetic.template_strategy("ny_open_vol_filter")
    mutated = genetic.random_strategy(random.Random(5), "ny_open_vol_filter")
    assert mutated is not None
    diff = genetic.diff_strategies(base, mutated)
    assert diff


def test_offspring_operator_names() -> None:
    base = genetic.template_strategy("ny_open_vol_filter")
    rng = random.Random(2)
    child, operator = genetic.tournament_offspring(base, None, rng)
    assert operator in {item.__name__ for item in genetic.MUTATIONS}
    if child is not None:
        assert dsl.validate(child) == []


def test_template_symmetry_flags() -> None:
    assert genetic.template_symmetric("ny_open_vol_filter") is True
    assert genetic.template_symmetric("asia_range_reversion") is True
    assert genetic.template_symmetric("session_breakout_htf") is False


def test_mirror_matches_template_short() -> None:
    for name in ("ny_open_vol_filter", "asia_range_reversion"):
        strategy = genetic.template_strategy(name)
        assert (
            genetic.mirror_expr(strategy["long_entry"])
            == strategy["short_entry"]
        )
        assert dsl.validate(strategy) == []


def test_symmetric_random_strategy_keeps_mirror() -> None:
    for seed in range(6):
        strategy = genetic.random_strategy(
            random.Random(seed), "ny_open_vol_filter", symmetric=True
        )
        assert strategy is not None
        assert (
            strategy["short_entry"]
            == genetic.mirror_expr(strategy["long_entry"])
        )
        assert dsl.validate(strategy) == []


def test_symmetric_operators_keep_mirror() -> None:
    base = genetic.template_strategy("ny_open_vol_filter")
    for operator in genetic.MUTATIONS:
        result = operator(copy.deepcopy(base), random.Random(3), symmetric=True)
        if result is None:
            continue
        assert (
            result["short_entry"]
            == genetic.mirror_expr(result["long_entry"])
        )

