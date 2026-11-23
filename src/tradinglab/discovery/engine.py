"""Motor genético NSGA-II del Discovery Lab (solo IS; OOS-1 al final).

El GA nunca ve OOS-1 ni OOS-2. Cuando termina, marca la campaña ``done`` y
evalúa una sola vez la frontera de rango 1 en OOS-1 para elegir finalistas.
``read_holdout`` no se llama nunca aquí.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import campaigns, databank, dsl, fitness, genetic, grid, jobs, nsga2
from .config import load_engine_config


@dataclass
class Individual:
    strategy: dict[str, Any]
    strategy_hash: str
    generation: int = 0
    operator: str = "seed"
    origin: str = "template"
    parents: tuple[int | None, int | None] = (None, None)
    strategy_id: int | None = None
    fitness: list[float] = field(default_factory=lambda: [0.0] * 5)
    feasible: bool = False
    violations: list[str] = field(default_factory=list)
    folds: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    daily_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trades: int = 0
    cost_r: float | None = None
    complexity: int = 0
    rank: int = -1
    crowding: float = 0.0
    param_diff: dict[str, Any] = field(default_factory=dict)


def synthetic_frame(
    *,
    years: float = 2.0,
    seed: int = 42,
    price: float = 20_000.0,
    sigma: float = 0.0004,
) -> pd.DataFrame:
    bars = int(365 * 24 * 12 * years)
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-02", periods=bars, freq="5min", tz="UTC")
    close = price * np.exp(np.cumsum(rng.normal(0.0, sigma, bars)))
    open_ = np.r_[close[0], close[:-1]]
    span = np.abs(rng.normal(0.0, sigma / 2.0, bars))
    high = np.maximum(open_, close) * (1.0 + span)
    low = np.minimum(open_, close) * (1.0 - span)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def _series(values: list[float], dates: list[str]) -> pd.Series:
    if dates:
        return pd.Series(values, index=pd.to_datetime(dates), dtype=float)
    return pd.Series(values, dtype=float)


def initial_strategies(
    campaign: dict[str, Any],
    *,
    template: str,
    population: int,
    rng: random.Random,
    stats: dict[str, int] | None = None,
    symmetric: bool | None = None,
) -> list[dict[str, Any]]:
    """Plantilla real + aleatorias, con el instrumento y la sesión de la campaña.

    La plantilla YAML puede decir ``US100``; los individuos deben llevar el
    instrumento y la sesión registrados en la campaña o el worker los rechaza
    antes de evaluar. ``stats`` acumula intentos, inválidos y duplicados.
    """

    config = campaign.get("config") or {}
    instrument = campaign.get("instrument") or config.get("instrument")
    timeframe = campaign.get("timeframe") or config.get("timeframe")
    session = dict(config.get("session") or {})
    if symmetric is None:
        symmetric = genetic.template_symmetric(template)
    strategies: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts = 0
    invalid = 0
    duplicates = 0
    limit = int(population) * 20
    while len(strategies) < int(population) and attempts < limit:
        attempts += 1
        strategy = genetic.random_strategy(
            rng,
            template,
            instrument=instrument,
            timeframe=timeframe,
            session=session,
            symmetric=symmetric,
        )
        if strategy is None:
            invalid += 1
            continue
        digest = dsl.strategy_hash(strategy)
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        strategies.append(strategy)
    if stats is not None:
        stats.update(
            {
                "attempts": attempts,
                "invalid": invalid,
                "duplicates": duplicates,
                "generated": len(strategies),
            }
        )
    return strategies


def candidate_strategies(
    campaign: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, str, str, int]:
    """Lista de candidatos de una campaña, sin barras ni backtests.

    Grid: todas las combinaciones. GA: la población inicial con la semilla de
    la campaña. Es la misma lista para ``preflight`` y ``feasibility``.
    """

    config = load_engine_config()
    campaign_config = campaign.get("config") or {}
    profile = config.profile(str(campaign_config.get("profile") or "small"))
    template = str(
        campaign.get("template")
        or campaign_config.get("template")
        or "ny_open_vol_filter"
    )
    seed = int(campaign_config.get("seed", 0))
    mode = str(campaign_config.get("mode") or "ga")
    if mode == "grid":
        strategies = grid.grid_strategies(
            template,
            instrument=campaign.get("instrument"),
            timeframe=campaign.get("timeframe"),
            session=campaign_config.get("session"),
            grid_spec=campaign_config.get("grid"),
        )
        population = len(strategies)
    else:
        strategies = initial_strategies(
            campaign,
            template=template,
            population=int(profile.population),
            rng=random.Random(seed),
        )
        population = int(profile.population)
    return strategies, population, mode, template, seed


def preflight(campaign_id: str, *, db_path=None) -> dict[str, Any]:
    """Solo inicialización: generados, válidos y rechazos del worker.

    No carga barras, no ejecuta backtests y no lee OOS. Trabaja igual sobre un
    borrador, para poder ejecutarlo antes de aprobar la campaña.
    """

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    return _preflight_campaign(campaign, campaign_id)


def preflight_spec(spec_path: str | Path) -> dict[str, Any]:
    """Preflight sobre una especificación, sin registrar campaña."""
    from .spec import load_spec

    campaign = load_spec(spec_path)
    return _preflight_campaign(
        campaign, str(campaign["campaign_id"])
    )


def _preflight_campaign(
    campaign: dict[str, Any], campaign_id: str
) -> dict[str, Any]:
    strategies, population, mode, template, seed = candidate_strategies(campaign)
    setup = jobs.QueueSetup.from_campaign(campaign)
    reasons: dict[str, int] = {}
    valid = 0
    for strategy in strategies:
        reason = jobs.strategy_gate(strategy, setup)
        if reason is None:
            valid += 1
        else:
            reasons[reason] = reasons.get(reason, 0) + 1
    duplicates = len(strategies) - len(
        {dsl.strategy_hash(strategy) for strategy in strategies}
    )
    return {
        "campaign_id": campaign_id,
        "status": campaign.get("status"),
        "instrument": setup.instrument,
        "timeframe": setup.timeframe,
        "template": template,
        "mode": mode,
        "seed": seed,
        "population": population,
        "generated": len(strategies),
        "valid": valid,
        "rejected": len(strategies) - valid,
        "duplicates": duplicates,
        "reasons": reasons,
        "last_error": campaign.get("last_error"),
    }


def _individual(
    strategy: dict[str, Any],
    result: dict[str, Any],
    *,
    generation: int,
    operator: str,
    origin: str,
    parents: tuple[int | None, int | None],
    param_diff: dict[str, Any] | None = None,
) -> Individual:
    series = _series(result.get("returns") or [], result.get("return_dates") or [])
    return Individual(
        strategy=strategy,
        strategy_hash=str(result.get("strategy_hash") or dsl.strategy_hash(strategy)),
        generation=generation,
        operator=operator,
        origin=origin,
        parents=parents,
        fitness=[float(value) for value in (result.get("fitness") or [0.0] * 5)],
        feasible=bool(result.get("feasible")),
        violations=list(result.get("violations") or []),
        folds=list(result.get("folds") or []),
        metrics=dict(result.get("metrics") or {}),
        daily_returns=series,
        trades=int(result.get("trades") or 0),
        cost_r=result.get("cost_r"),
        complexity=int(result.get("complexity") or 0),
        param_diff=dict(param_diff or {}),
    )


def _assign_ranks(population: list[Individual]) -> None:
    if not population:
        return
    ranks, crowding, _fronts = nsga2.rank_and_crowding(
        [item.fitness for item in population],
        [item.feasible for item in population],
    )
    for index, item in enumerate(population):
        item.rank = int(ranks[index])
        item.crowding = float(crowding.get(index, 0.0))


def _niche(population: list[Individual], threshold: float = 0.9) -> None:
    if len(population) < 2:
        return
    series = [item.daily_returns for item in population]
    try:
        frame = pd.concat(
            [value.rename(index) for index, value in enumerate(series)],
            axis=1,
            sort=False,
        ).fillna(0.0)
        corr = frame.corr().fillna(0.0).to_numpy(dtype=float)
    except Exception:  # noqa: BLE001 - series sin índice común
        return
    for left in range(len(population)):
        for right in range(left + 1, len(population)):
            if abs(float(corr[left, right])) <= threshold:
                continue
            a, b = population[left], population[right]
            worse = a if (a.rank, -a.crowding) > (b.rank, -b.crowding) else b
            worse.crowding = -1.0


def _store(
    campaign_id: str,
    item: Individual,
    setup: jobs.QueueSetup,
    *,
    db_path,
) -> int:
    sid = databank.add_strategy(
        campaign_id,
        item.strategy,
        family=setup.template,
        generation=item.generation,
        origin=item.origin,
        status="evaluated",
        db_path=db_path,
    )
    item.strategy_id = sid
    metrics = dict(item.metrics)
    metrics["return_dates"] = [
        stamp.isoformat() for stamp in item.daily_returns.index
    ]
    databank.add_evaluation(
        sid,
        segment="fitness_is",
        cost_profile=setup.cost_profile(),
        metrics=metrics,
        trades_count=item.trades,
        returns=item.daily_returns,
        db_path=db_path,
    )
    return sid


def _store_lineage(campaign_id: str, item: Individual, db_path) -> None:
    if item.strategy_id is None:
        return
    databank.add_lineage(
        item.strategy_id,
        parent_a=item.parents[0],
        parent_b=item.parents[1],
        operator=item.operator,
        param_diff=item.param_diff,
        generation=item.generation,
        fitness={
            "vector": item.fitness,
            "raw": item.metrics.get("raw"),
            "folds": item.folds,
        },
        rank=item.rank,
        crowding=item.crowding,
        reason="evaluado",
        db_path=db_path,
    )


def _evaluate(
    evaluator: jobs.BatchEvaluator,
    strategies: list[dict[str, Any]],
    *,
    generation: int,
    operators: list[str],
    origin: str,
    parent_items: list[tuple[Individual | None, Individual | None]],
    campaign_id: str,
    setup: jobs.QueueSetup,
    db_path,
    errors: list[str] | None = None,
) -> list[Individual]:
    if not strategies:
        return []
    results = evaluator.evaluate(strategies, kind="fitness")
    individuals: list[Individual] = []
    for index, (strategy, result) in enumerate(zip(strategies, results)):
        if result.get("error"):
            if errors is not None:
                errors.append(str(result["error"]))
            continue
        parent_a, parent_b = parent_items[index]
        diff = (
            genetic.diff_strategies(parent_a.strategy, strategy)
            if parent_a is not None
            else {}
        )
        item = _individual(
            strategy,
            result,
            generation=generation,
            operator=operators[index] if index < len(operators) else "mutation",
            origin=origin,
            parents=(
                parent_a.strategy_id if parent_a else None,
                parent_b.strategy_id if parent_b else None,
            ),
            param_diff=diff,
        )
        _store(campaign_id, item, setup, db_path=db_path)
        individuals.append(item)
    return individuals


def _rank1_candidates(
    population: list[Individual], folds: int
) -> tuple[list[Individual], list[tuple[Individual, str]]]:
    feasible_rank1 = [
        item for item in population if item.rank == 0 and item.feasible
    ]
    candidates: list[Individual] = []
    discarded: list[tuple[Individual, str]] = []
    for item in feasible_rank1:
        full_is = (item.metrics.get("is") or {}).get("expectancy_r")
        if full_is is None or float(full_is) <= 0:
            discarded.append(
                (item, f"descartado: IS completa {full_is} <= 0")
            )
            continue
        positive = sum(
            1
            for row in item.folds
            if row.get("expectancy_r") is not None
            and float(row["expectancy_r"]) > 0
        )
        if positive >= max(1, folds - 1):
            candidates.append(item)
        else:
            discarded.append((item, f"descartado: pliegues positivos {positive}/{folds}"))
    return candidates, discarded


def _spearman(pairs: list[tuple[float, float]]) -> float:
    """Spearman entre expectativa IS y OOS-1 de los candidatos."""

    if len(pairs) < 3:
        return 0.0
    try:
        from scipy.stats import spearmanr

        value = float(
            spearmanr([a for a, _b in pairs], [b for _a, b in pairs]).statistic
        )
    except Exception:  # noqa: BLE001 - sin scipy o datos degenerados
        return 0.0
    return 0.0 if not np.isfinite(value) else value


def _correlation(left: pd.Series, right: pd.Series) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    joined = pd.concat(
        [left.rename("a"), right.rename("b")], axis=1, sort=False
    ).dropna()
    if len(joined) < 2:
        return 0.0
    value = float(joined["a"].corr(joined["b"]))
    return 0.0 if not np.isfinite(value) else value


def _select_finalists(
    candidates: list[Individual],
    oos1: dict[int, dict[str, Any]],
    *,
    finalists_max: int,
    corr_cluster: float,
) -> tuple[list[Individual], list[tuple[Individual, str]]]:
    passing: list[tuple[float, Individual, pd.Series]] = []
    discarded: list[tuple[Individual, str]] = []
    for item in candidates:
        result = oos1.get(id(item))
        if result is None or result.get("error"):
            discarded.append((item, "descartado: OOS-1 con error"))
            continue
        metrics = result.get("metrics") or {}
        expectancy = metrics.get("expectancy_r")
        pf = metrics.get("profit_factor")
        if expectancy is None or float(expectancy) <= 0:
            discarded.append(
                (item, f"descartado: OOS-1 expectativa {expectancy}")
            )
            continue
        if pf is None:
            pf = float("inf")
        if float(pf) <= 1.1:
            discarded.append((item, f"descartado: OOS-1 PF {pf} <= 1,1"))
            continue
        series = _series(result.get("returns") or [], result.get("return_dates") or [])
        score = float(expectancy) - 0.001 * float(item.complexity)
        passing.append((score, item, series))

    passing.sort(key=lambda value: (-value[0], value[1].strategy_hash))
    selected: list[Individual] = []
    selected_series: list[pd.Series] = []
    for _score, item, series in passing:
        if len(selected) >= finalists_max:
            discarded.append((item, "descartado: fuera de K"))
            continue
        correlated = any(
            abs(_correlation(series, chosen)) >= corr_cluster
            for chosen in selected_series
        )
        if correlated:
            discarded.append(
                (item, f"descartado: correlación >= {corr_cluster}")
            )
            continue
        selected.append(item)
        selected_series.append(series)
    return selected, discarded


def _draw_child(
    current: list[Individual],
    ranks: list[int],
    crowding: dict[int, float],
    known: dict[str, Individual],
    pending: set[str],
    rng: random.Random,
    *,
    symmetric: bool,
    max_attempts: int = 10,
) -> dict[str, Any]:
    """Un hueco de la generación, con hasta ``max_attempts`` reintentos.

    Un hijo inválido o con hash ya visto no deja el hueco vacío en el primer
    fallo: se vuelve a sortear el torneo. Tras 10 intentos el hueco queda
    vacío. Devuelve también los contadores para ``diagnostics``.
    """

    attempts = 0
    invalid = 0
    duplicates = 0
    while attempts < max_attempts:
        attempts += 1
        picks = nsga2.select(
            list(range(len(current))), ranks, crowding, 2, rng
        )
        left = current[picks[0]]
        right = current[picks[1]]
        child, operator = genetic.tournament_offspring(
            left.strategy, right.strategy, rng, symmetric=symmetric
        )
        if child is None:
            invalid += 1
            continue
        digest = dsl.strategy_hash(child)
        if digest in known or digest in pending:
            duplicates += 1
            continue
        return {
            "child": child,
            "parents": (left, right),
            "operator": operator,
            "attempts": attempts,
            "invalid": invalid,
            "duplicates": duplicates,
        }
    return {
        "child": None,
        "parents": (None, None),
        "operator": None,
        "attempts": attempts,
        "invalid": invalid,
        "duplicates": duplicates,
    }


def run_campaign(
    campaign_id: str,
    *,
    workers: int | None = None,
    time_limit: float | None = None,
    synthetic: bool = False,
    db_path=None,
    bars: pd.DataFrame | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Ejecuta una campaña. El CLI comprueba la aprobación y el flag."""

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    if not synthetic:
        campaign = campaigns.reopen_empty_running(
            campaign_id, db_path=db_path
        )
    status = str(campaign["status"])
    if synthetic:
        if status not in {"synthetic", "running", "done"}:
            raise campaigns.CampaignError(
                "una campaña real no se ejecuta con --synthetic"
            )
    else:
        if status != "registered":
            raise campaigns.CampaignError(
                f"la campaña debe estar registered (está {status})"
            )
        if not campaign.get("approved_at"):
            raise campaigns.CampaignError(
                "la campaña no está aprobada con --approved-by-operator"
            )
    config = load_engine_config()
    profile = config.profile(str(campaign["config"].get("profile") or "small"))
    total_budget = int(campaign.get("n_total") or 0)
    if total_budget <= 0:
        raise campaigns.CampaignError("Sin datos: n_total no válido")
    template = str(campaign.get("template") or campaign["config"].get("template") or "ny_open_vol_filter")
    campaign_seed = int(seed if seed is not None else campaign["config"].get("seed", 0))
    mode = str(campaign["config"].get("mode") or "ga").strip().lower()
    if mode not in {"ga", "grid"}:
        raise campaigns.CampaignError(f"modo de campaña desconocido: {mode}")
    grid_spec = campaign["config"].get("grid") if mode == "grid" else None
    if mode == "grid":
        if not isinstance(grid_spec, dict) or not grid_spec.get("dimensions"):
            raise campaigns.CampaignError(
                "preflight: campaña grid sin grid resoluble en config.grid"
            )
        try:
            grid.validate_grid(grid_spec, template)
            size = grid.grid_size(template, grid_spec=grid_spec)
        except Exception as exc:  # noqa: BLE001
            raise campaigns.CampaignError(
                f"preflight: grid del spec inválido: {exc}"
            ) from exc
        if size != total_budget:
            raise campaigns.CampaignError(
                f"preflight: grid del spec tiene {size} combinaciones; "
                f"n_total congelado es {total_budget}"
            )
    rng = random.Random(campaign_seed)
    setup = jobs.QueueSetup.from_campaign(campaign, bars=bars)
    is_frame = campaigns.load_segment(campaign_id, "is", frame=bars, db_path=db_path)
    setup = replace(
        setup,
        start=campaign["is_start"],
        end=campaign["is_end"],
        bars=is_frame,
    )
    if not synthetic:
        databank.set_campaign_status(campaign_id, "running", db_path=db_path)
    started = time.monotonic()
    max_workers = int(config.workers)
    requested = max_workers if workers is None else min(int(workers), max_workers)
    requested = max(1, requested)

    known: dict[str, Individual] = {}
    symmetric = genetic.template_symmetric(template)
    init_stats: dict[str, int] = {}
    if mode == "grid":
        initial_candidates = grid.grid_strategies(
            template,
            instrument=campaign.get("instrument"),
            timeframe=campaign.get("timeframe"),
            session=campaign["config"].get("session"),
            grid_spec=grid_spec,
        )
        init_stats = {
            "attempts": len(initial_candidates),
            "invalid": 0,
            "duplicates": 0,
            "generated": len(initial_candidates),
        }
        initial_origin = "grid"
        initial_operators = ["grid"] * len(initial_candidates)
        generations = 0
    else:
        initial_candidates = initial_strategies(
            campaign,
            template=template,
            population=int(profile.population),
            rng=rng,
            stats=init_stats,
            symmetric=symmetric,
        )
        initial_origin = "template"
        initial_operators = ["seed"] * len(initial_candidates)
        generations = int(profile.generations)
    init_errors: list[str] = []
    diagnostics: dict[str, Any] = {
        "mode": mode,
        "symmetric": symmetric,
        "init": dict(init_stats),
        "generations": [],
        "submitted": len(initial_candidates),
        "evaluated": 0,
        "evaluation_errors": 0,
        "attempts": 0,
        "retried": 0,
        "empty_slots": 0,
        "stop_reason": "grid" if mode == "grid" else "generations",
    }

    with jobs.BatchEvaluator(
        setup,
        is_frame,
        workers=requested,
        cache_limit_bytes=None,
    ) as evaluator:
        try:
            initial = _evaluate(
                evaluator,
                initial_candidates,
                generation=0,
                operators=initial_operators,
                origin=initial_origin,
                parent_items=[(None, None) for _ in initial_candidates],
                campaign_id=campaign_id,
                setup=setup,
                db_path=db_path,
                errors=init_errors,
            )
            for item in initial:
                known[item.strategy_hash] = item
            diagnostics["evaluated"] = len(initial)
            diagnostics["evaluation_errors"] = len(init_errors)
            _assign_ranks(initial)
            _niche(initial, float(config.validation.corr_cluster))
            for item in initial:
                _store_lineage(campaign_id, item, db_path)
            current = initial
            if not current:
                detail = "; ".join(dict.fromkeys(init_errors[:3])) or "sin candidatos"
                raise campaigns.CampaignError(
                    "Sin datos: población inicial vacía "
                    f"({len(initial_candidates)} candidatos, "
                    f"{len(init_errors)} rechazados): {detail}"
                )
        except Exception as exc:
            # Nada quedó evaluado: la campaña vuelve a registered con el
            # motivo, sin tocar n_total ni approved_at. El reintento no se
            # bloquea y el DSR sigue contando la campaña una sola vez.
            if (
                not synthetic
                and databank.count_strategies(campaign_id, db_path=db_path) == 0
            ):
                databank.set_campaign_status(
                    campaign_id,
                    "registered",
                    reason=f"{type(exc).__name__}: {exc}",
                    db_path=db_path,
                )
            raise

        for generation in range(1, generations + 1):
            if time_limit is not None and time.monotonic() - started >= float(time_limit) * 60.0:
                diagnostics["stop_reason"] = "time_limit"
                break
            if len(known) >= total_budget:
                diagnostics["stop_reason"] = "budget"
                break
            _assign_ranks(current)
            _niche(current, 0.9)
            ranks = [item.rank for item in current]
            crowding = {index: item.crowding for index, item in enumerate(current)}
            offspring: list[dict[str, Any]] = []
            meta: list[tuple[Individual | None, Individual | None]] = []
            operators: list[str] = []
            pending: set[str] = set()
            gen_stats: dict[str, Any] = {
                "generation": generation,
                "slots": int(profile.population),
                "attempts": 0,
                "retried": 0,
                "invalid": 0,
                "duplicates": 0,
                "empty_slots": 0,
                "submitted": 0,
                "errors": 0,
                "evaluated": 0,
            }
            for _ in range(int(profile.population)):
                draw = _draw_child(
                    current,
                    ranks,
                    crowding,
                    known,
                    pending,
                    rng,
                    symmetric=symmetric,
                )
                gen_stats["attempts"] += int(draw["attempts"])
                gen_stats["retried"] += max(0, int(draw["attempts"]) - 1)
                gen_stats["invalid"] += int(draw["invalid"])
                gen_stats["duplicates"] += int(draw["duplicates"])
                child = draw["child"]
                if child is None:
                    gen_stats["empty_slots"] += 1
                    continue
                pending.add(dsl.strategy_hash(child))
                offspring.append(child)
                meta.append(draw["parents"])
                operators.append(draw["operator"])
            gen_stats["submitted"] = len(offspring)
            diagnostics["submitted"] += len(offspring)
            diagnostics["attempts"] += int(gen_stats["attempts"])
            diagnostics["retried"] += int(gen_stats["retried"])
            diagnostics["empty_slots"] += int(gen_stats["empty_slots"])
            if not offspring:
                diagnostics["generations"].append(gen_stats)
                diagnostics["stop_reason"] = "empty_offspring"
                break
            gen_errors: list[str] = []
            new_items = _evaluate(
                evaluator,
                offspring,
                generation=generation,
                operators=operators,
                origin="random",
                parent_items=meta,
                campaign_id=campaign_id,
                setup=setup,
                db_path=db_path,
                errors=gen_errors,
            )
            gen_stats["errors"] = len(gen_errors)
            gen_stats["evaluated"] = len(new_items)
            diagnostics["evaluation_errors"] += len(gen_errors)
            diagnostics["evaluated"] += len(new_items)
            diagnostics["generations"].append(gen_stats)
            for item in new_items:
                known[item.strategy_hash] = item
            if not new_items:
                continue
            combined = current + new_items
            _assign_ranks(combined)
            _niche(combined, 0.9)
            fronts = nsga2.fast_non_dominated_sort(
                [item.fitness for item in combined],
                [item.feasible for item in combined],
            )
            chosen_indices: list[int] = []
            for front in fronts:
                if len(chosen_indices) + len(front) <= int(profile.population):
                    chosen_indices.extend(front)
                    continue
                remaining = int(profile.population) - len(chosen_indices)
                ordered = sorted(
                    front, key=lambda index: (-combined[index].crowding, index)
                )
                chosen_indices.extend(ordered[:remaining])
                break
            for item in new_items:
                _store_lineage(campaign_id, item, db_path)
            current = [combined[index] for index in chosen_indices]
            if len(known) >= total_budget:
                diagnostics["stop_reason"] = "budget"
                break

    _assign_ranks(current)
    databank.reset_lineage_final(campaign_id, db_path=db_path)
    for item in current:
        if item.strategy_id is not None:
            databank.set_lineage_rank(
                item.strategy_id,
                item.rank,
                item.crowding,
                final=True,
                db_path=db_path,
            )
    feasible_count = sum(1 for item in known.values() if item.feasible)
    folds = int(config.validation.for_timeframe(setup.timeframe).folds)
    candidates, discarded = _rank1_candidates(current, folds)
    campaigns.mark_done(campaign_id, db_path=db_path)
    oos1: dict[int, dict[str, Any]] = {}
    selected: list[Individual] = []
    fold_discarded = list(discarded)
    if candidates:
        oos1_frame = campaigns.load_segment(
            campaign_id, "oos1", frame=bars, db_path=db_path
        )
        oos_setup = replace(
            setup,
            start=campaign["oos1_start"],
            end=campaign["oos1_end"],
            bars=oos1_frame,
        )
        with jobs.BatchEvaluator(oos_setup, oos1_frame, workers=requested) as evaluator:
            results = evaluator.evaluate(
                [item.strategy for item in candidates], kind="backtest_is"
            )
            for item, result in zip(candidates, results):
                oos1[id(item)] = result
                if result.get("error"):
                    continue
                databank.add_evaluation(
                    item.strategy_id,
                    segment="oos1",
                    cost_profile=setup.cost_profile(),
                    metrics={
                        **dict(result.get("metrics") or {}),
                        "return_dates": result.get("return_dates") or [],
                    },
                    trades_count=result.get("trades"),
                    returns=result.get("returns") or (),
                    db_path=db_path,
                )
        selected, rejected = _select_finalists(
            candidates,
            oos1,
            finalists_max=int(config.validation.finalists_max),
            corr_cluster=float(config.validation.corr_cluster),
        )
        discarded.extend(rejected)

    selected_ids = {id(item) for item in selected}
    reasons = {id(item): reason for item, reason in discarded}
    rank1_items = candidates + [item for item, _reason in fold_discarded]
    for item in rank1_items:
        if id(item) in selected_ids:
            result = oos1.get(id(item)) or {}
            metrics = result.get("metrics") or {}
            reason = (
                f"finalista: OOS-1 expectativa "
                f"{metrics.get('expectancy_r')} PF {metrics.get('profit_factor')}"
            )
            databank.set_strategy_selection(
                item.strategy_id, "finalist", reason, db_path=db_path
            )
        else:
            databank.set_strategy_selection(
                item.strategy_id,
                "discarded",
                reasons.get(id(item), "descartado: no seleccionado"),
                db_path=db_path,
            )

    n_effective = fitness.effective_trials(
        [item.daily_returns for item in known.values()],
        threshold=float(config.validation.corr_cluster),
    )
    databank.set_campaign_counts(
        campaign_id,
        n_evaluated=len(known),
        n_effective=int(n_effective),
        n_finalists=len(selected),
        db_path=db_path,
    )
    finalist_rows = []
    for item in selected:
        result = oos1.get(id(item)) or {}
        metrics = result.get("metrics") or {}
        finalist_rows.append(
            {
                "strategy_id": item.strategy_id,
                "strategy_hash": item.strategy_hash,
                "oos1_expectancy_r": metrics.get("expectancy_r"),
                "oos1_profit_factor": metrics.get("profit_factor"),
                "is_expectancy_r": (
                    item.metrics.get("is") or {}
                ).get("expectancy_r"),
                "is_median_expectancy_r": item.metrics.get("raw", {}).get(
                    "expectancy_r"
                ),
                "cost_r": item.cost_r,
            }
        )
    oos_values = [
        row["oos1_expectancy_r"]
        for row in finalist_rows
        if row["oos1_expectancy_r"] is not None
    ]
    candidate_values = [
        (result.get("metrics") or {}).get("expectancy_r")
        for result in oos1.values()
        if not result.get("error")
        and (result.get("metrics") or {}).get("expectancy_r") is not None
    ]
    spearman_pairs = []
    for item in candidates:
        result = oos1.get(id(item)) or {}
        value = (result.get("metrics") or {}).get("expectancy_r")
        if value is not None and not result.get("error"):
            spearman_pairs.append((float(item.fitness[0]), float(value)))
    spearman_value = _spearman(spearman_pairs)
    frontier_items = [
        item for item in current if item.rank == 0 and item.feasible
    ]
    frontier_fitness = (
        np.mean([item.fitness for item in frontier_items], axis=0).tolist()
        if frontier_items
        else None
    )
    return {
        "campaign_id": campaign_id,
        "synthetic": bool(synthetic),
        "n_total": total_budget,
        "n_evaluated": len(known),
        "n_effective": int(n_effective),
        "n_finalists": len(selected),
        "feasible": feasible_count,
        "frontier": len(frontier_items),
        "frontier_fitness_mean": frontier_fitness,
        "candidates": len(candidates),
        "finalists": finalist_rows,
        "oos1_mean": float(np.mean(oos_values)) if oos_values else None,
        "oos1_positive": sum(1 for value in oos_values if value > 0),
        "candidates_oos1_mean": (
            float(np.mean(candidate_values)) if candidate_values else None
        ),
        "candidates_oos1_positive": sum(
            1 for value in candidate_values if value > 0
        ),
        "candidates_oos1_total": len(candidate_values),
        "spearman_is_oos1": float(spearman_value),
        "elapsed_s": time.monotonic() - started,
        "seed": campaign_seed,
        "diagnostics": diagnostics,
    }


__all__ = [
    "Individual",
    "candidate_strategies",
    "initial_strategies",
    "preflight",
    "run_campaign",
    "synthetic_frame",
]
