"""NSGA-II: dominancia, frentes, crowding y torneo."""

from __future__ import annotations

import random

from tradinglab.discovery import nsga2


def test_dominates() -> None:
    assert nsga2.dominates((2.0, 2.0), (1.0, 2.0))
    assert not nsga2.dominates((2.0, 2.0), (2.0, 2.0))
    assert not nsga2.dominates((1.0, 2.0), (2.0, 2.0))


def test_fast_non_dominated_sort_known_fronts() -> None:
    fitness = [(3.0, 1.0), (2.0, 2.0), (1.0, 3.0), (0.0, 0.0)]
    fronts = nsga2.fast_non_dominated_sort(fitness, [True] * 4)
    assert fronts[0] == [0, 1, 2]
    assert fronts[1] == [3]


def test_infeasible_goes_last() -> None:
    fitness = [(3.0, 3.0), (2.0, 2.0)]
    fronts = nsga2.fast_non_dominated_sort(fitness, [False, True])
    assert fronts[-1] == [0]


def test_crowding_boundaries_and_middle() -> None:
    fitness = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.5)]
    distance = nsga2.crowding_distance(fitness, [0, 1, 2])
    assert distance[0] == float("inf")
    assert distance[1] > 0.0
    assert distance[2] == float("inf")


def test_tournament_is_deterministic() -> None:
    ranks = [0, 1, 0, 2]
    crowding = {0: 1.0, 1: 0.0, 2: 2.0, 3: 0.0}
    first = nsga2.select([0, 1, 2, 3], ranks, crowding, 10, random.Random(7))
    second = nsga2.select([0, 1, 2, 3], ranks, crowding, 10, random.Random(7))
    assert first == second
    assert all(item in {0, 1, 2, 3} for item in first)


def test_environmental_selection_fills_size() -> None:
    fitness = [(3.0, 1.0), (2.0, 2.0), (1.0, 3.0), (0.0, 0.0)]
    selected, ranks, _crowding = nsga2.environmental_selection(
        fitness, [True] * 4, 2
    )
    assert len(selected) == 2
    assert set(selected) <= {0, 1, 2, 3}
    assert len(ranks) == 4
