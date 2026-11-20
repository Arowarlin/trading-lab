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
