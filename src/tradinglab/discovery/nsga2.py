"""NSGA-II: ordenación no dominada, crowding y torneo binario."""

from __future__ import annotations

import random
from typing import Sequence

Fitness = Sequence[float]


def dominates(left: Fitness, right: Fitness) -> bool:
    no_worse = all(a >= b for a, b in zip(left, right))
    better = any(a > b for a, b in zip(left, right))
    return bool(no_worse and better)


def fast_non_dominated_sort(
    fitness: Sequence[Fitness], feasible: Sequence[bool]
) -> list[list[int]]:
    """Frentes de índices; los no factibles van al último frente."""

    n = len(fitness)
    if n == 0:
        return []
    viable = [index for index in range(n) if feasible[index]]
    dominated_by: dict[int, list[int]] = {index: [] for index in viable}
    count: dict[int, int] = {index: 0 for index in viable}
    fronts: list[list[int]] = []
    current: list[int] = []
    for index in viable:
        for other in viable:
            if index == other:
                continue
            if dominates(fitness[index], fitness[other]):
                dominated_by[index].append(other)
            elif dominates(fitness[other], fitness[index]):
                count[index] += 1
        if count[index] == 0:
            current.append(index)
    while current:
        fronts.append(sorted(current))
        following: list[int] = []
        for index in current:
            for other in dominated_by[index]:
                count[other] -= 1
                if count[other] == 0:
                    following.append(other)
        current = following
    infeasible = [index for index in range(n) if not feasible[index]]
    if infeasible:
        fronts.append(sorted(infeasible))
    return fronts


def crowding_distance(
    fitness: Sequence[Fitness], front: Sequence[int]
) -> dict[int, float]:
    distance = {index: 0.0 for index in front}
    if len(front) <= 2:
        return {index: float("inf") for index in front}
    objectives = len(fitness[front[0]])
    for objective in range(objectives):
        ordered = sorted(front, key=lambda index: fitness[index][objective])
        low = fitness[ordered[0]][objective]
        high = fitness[ordered[-1]][objective]
        distance[ordered[0]] = float("inf")
        distance[ordered[-1]] = float("inf")
        if high == low:
            continue
        for position in range(1, len(ordered) - 1):
            previous = fitness[ordered[position - 1]][objective]
            following = fitness[ordered[position + 1]][objective]
            distance[ordered[position]] += (following - previous) / (high - low)
    return distance


def rank_and_crowding(
    fitness: Sequence[Fitness], feasible: Sequence[bool]
) -> tuple[list[int], dict[int, float], list[list[int]]]:
    fronts = fast_non_dominated_sort(fitness, feasible)
    ranks = [0] * len(fitness)
    crowding: dict[int, float] = {}
    for rank, front in enumerate(fronts):
        for index in front:
            ranks[index] = rank
        crowding.update(crowding_distance(fitness, front))
    return ranks, crowding, fronts


def select(
    population: Sequence[int],
    ranks: Sequence[int],
    crowding: dict[int, float],
    count: int,
    rng: random.Random,
) -> list[int]:
    """Torneo binario: menor rango y, a igualdad, mayor crowding."""

    chosen: list[int] = []
    if not population:
        return chosen
    for _ in range(int(count)):
        left = int(rng.choice(population))
        right = int(rng.choice(population))
        if ranks[left] < ranks[right]:
            chosen.append(left)
        elif ranks[right] < ranks[left]:
            chosen.append(right)
        elif crowding.get(left, 0.0) >= crowding.get(right, 0.0):
            chosen.append(left)
        else:
            chosen.append(right)
    return chosen


def environmental_selection(
    fitness: Sequence[Fitness],
    feasible: Sequence[bool],
    size: int,
) -> tuple[list[int], list[int], dict[int, float]]:
    """Elige ``size`` índices; devuelve seleccionados, rangos y crowding."""

    ranks, crowding, fronts = rank_and_crowding(fitness, feasible)
    selected: list[int] = []
    for front in fronts:
        if len(selected) + len(front) <= size:
            selected.extend(front)
            continue
        remaining = size - len(selected)
        ordered = sorted(
            front, key=lambda index: (-crowding.get(index, 0.0), index)
        )
        selected.extend(ordered[:remaining])
        break
    return selected, ranks, crowding


__all__ = [
    "crowding_distance",
    "dominates",
    "environmental_selection",
    "fast_non_dominated_sort",
    "rank_and_crowding",
    "select",
]
