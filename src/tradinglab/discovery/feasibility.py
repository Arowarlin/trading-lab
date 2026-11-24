"""Preflight de viabilidad de una campaña, sin PnL ni expectativa.

Calcula solo lo que decide si una rejilla o una población inicial puede llegar
a evaluarse: operaciones IS, operaciones por pliegue, mediana de ``cost_R`` y
tiempo medio en mercado. No calcula expectativa, no escribe en ``disc_*``, no
suma al DSR y no abre OOS-1/OOS-2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import (
    campaigns,
    compiler,
    data_sources,
    databank,
    dsl,
    fastbt,
    fitness,
    genetic,
    grid,
    jobs,
    snapshots,
    specs,
)
from .config import load_engine_config
from .engine import candidate_strategies
from .timeframes import timeframe_minutes

MIN_FEASIBLE_PCT = 50.0


@dataclass
class FeasibilityRow:
    index: int
    strategy_hash: str
    label: str
    trades_is: int
    fold_trades: list[int]
    cost_r: float | None
    mean_bars: float
    mean_minutes: float
    feasible: bool
    reasons: list[str]
    cost_by_account: dict[str, float | None] | None = None
    cost_viable_by_account: dict[str, bool | None] | None = None
    worst_account: str | None = None
    worst_share: float | None = None
    best_account: str | None = None
    selected_account: str | None = None
    selected_share: float | None = None


def _walk(node: Any):
    if not isinstance(node, dict):
        return
    yield node
    for item in node.get("args") or []:
        yield from _walk(item)
    for key in ("left", "right", "expr"):
        if isinstance(node.get(key), dict):
            yield from _walk(node[key])


def _label(strategy: dict[str, Any]) -> str:
    entry = strategy.get("long_entry") or {}
    parts: list[str] = []
    for node in _walk(entry):
        if node.get("kind") not in {"gt", "lt", "ge", "le"}:
            continue
        left = node.get("left") or {}
        right = node.get("right") or {}
        if left.get("kind") == "indicator" and left.get("ind") == "session_return":
            params = left.get("params") or {}
            parts.append(f"u={right.get('value')}")
            parts.append(f"fin={params.get('end')}")
        elif left.get("kind") == "indicator":
            parts.append(f"{left.get('ind')}>{right.get('value')}")
    if entry.get("kind") == "and":
        for node in entry.get("args") or []:
            if node.get("kind") == "time_between":
                parts.append(f"entrada={node.get('start')}")
            elif node.get("kind") in {"regime", "pattern"}:
                parts.append(f"filtro={node.get('regime') or node.get('pattern')}")
    stop = ((strategy.get("exit") or {}).get("stop") or {}).get("mult")
    if stop is not None:
        parts.append(f"stop={stop}")
    return " ".join(dict.fromkeys(part for part in parts if part)) or "individuo"


def _context(campaign_id: str, db_path):
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    setup = jobs.QueueSetup.from_campaign(campaign)
    bars = campaigns.load_segment(campaign_id, "is", db_path=db_path)
    book = None
    if setup.legacy_cost:
        from ..propfund.costs import load_profile

        try:
            profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
            cost = fastbt.cost_from_profile(profile, use_p75=setup.use_p75)
        except Exception as exc:  # noqa: BLE001 - coste ausente se informa como Sin datos
            raise campaigns.CampaignError(f"Sin datos: coste {exc}") from exc
    else:
        from .costs import build_cost_book_for_setup

        try:
            book = build_cost_book_for_setup(setup)
            cost = book
        except Exception as exc:  # noqa: BLE001
            raise campaigns.CampaignError(f"Sin datos: coste {exc}") from exc
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
        cost_model_version=setup.cost_model_version,
    )
    prepared = fastbt.prepare(
        bars,
        cost,
        atr_windows=(setup.stop_n, setup.trail_n),
        sessions=(limits,),
    )
    return campaign, setup, bars, cost, prepared, book


def _context_from(campaign, setup, bars):
    book = None
    if setup.legacy_cost:
        from ..propfund.costs import load_profile

        try:
            profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
            cost = fastbt.cost_from_profile(profile, use_p75=setup.use_p75)
        except Exception as exc:  # noqa: BLE001 - coste ausente se informa como Sin datos
            raise campaigns.CampaignError(f"Sin datos: coste {exc}") from exc
    else:
        from .costs import build_cost_book_for_setup

        try:
            book = build_cost_book_for_setup(setup)
            cost = book
        except Exception as exc:  # noqa: BLE001
            raise campaigns.CampaignError(f"Sin datos: coste {exc}") from exc
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
        cost_model_version=setup.cost_model_version,
    )
    prepared = fastbt.prepare(
        bars,
        cost,
        atr_windows=(setup.stop_n, setup.trail_n),
        sessions=(limits,),
    )
    return campaign, setup, bars, cost, prepared, book


def _context(campaign_id: str, db_path):
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    setup = jobs.QueueSetup.from_campaign(campaign)
    bars = campaigns.load_segment(campaign_id, "is", db_path=db_path)
    return _context_from(campaign, setup, bars)


def check(campaign_id: str, *, db_path=None) -> dict[str, Any]:
    """Devuelve la viabilidad de cada combinación/individuo inicial."""

    context = _context(campaign_id, db_path)
    return _check_context(*context, campaign_id=campaign_id)


def _check_context(
    campaign,
    setup,
    bars,
    cost,
    prepared,
    book,
    *,
    campaign_id: str,
) -> dict[str, Any]:
    strategies, population, mode, template, seed = candidate_strategies(campaign)
    config = load_engine_config()
    validation = config.validation.for_timeframe(setup.timeframe)
    folds = int(validation.folds)
    min_trades_is = int(validation.min_trades_is)
    min_trades_fold = int(validation.min_trades_fold)
    max_cost_r = float(config.fitness.cost_r_max)
    rows: list[FeasibilityRow] = []
    for index, strategy in enumerate(strategies):
        trades_is = 0
        fold_trades: list[int] = []
        cost_r: float | None = None
        mean_bars = 0.0
        reasons: list[str] = []
        cost_by_account: dict[str, float | None] | None = None
        cost_viable_by_account: dict[str, bool | None] | None = None
        worst_account: str | None = None
        worst_share: float | None = None
        best_account: str | None = None
        selected_account: str | None = None
        selected_share: float | None = None
        gate = jobs.strategy_gate(strategy, setup)
        if gate:
            reasons.append(gate)
        else:
            try:
                model = dsl.Strategy.model_validate(strategy)
                signals = compiler.compile(model, bars)
                exit_spec = specs.exit_spec_from_strategy(model)
                base_limits = specs.run_limits_from_strategy(
                    model, setup, close_at_end=True
                )
                full = fastbt.run(
                    signals,
                    bars,
                    exit_spec,
                    cost,
                    base_limits,
                    prepared=prepared,
                )
                trades = list(full.trades)
                if book is not None:
                    from .costs import apply_result

                    applied, _metrics = apply_result(
                        book,
                        full,
                        session_tz=base_limits.session_tz,
                        point=setup.point,
                        max_cost_r=max_cost_r,
                    )
                    trades = list(applied.trades)
                    cost_by_account = applied.cost_by_account
                    cost_viable_by_account = {
                        name: (
                            None
                            if value is None
                            else bool(float(value) <= max_cost_r)
                        )
                        for name, value in applied.cost_by_account.items()
                    }
                    worst_account = applied.worst_account
                    worst_share = applied.worst_share
                    best_account = applied.best_account
                    selected_account = applied.selected_account
                    selected_share = applied.selected_share
                trades_is = len(trades)
                costs = [
                    float(trade.r_cost)
                    for trade in trades
                    if trade.r_cost is not None
                ]
                cost_r = float(np.median(costs)) if costs else None
                if book is None:
                    cost_by_account = {setup.account: cost_r}
                    cost_viable_by_account = {
                        setup.account: (
                            None if cost_r is None else bool(cost_r <= max_cost_r)
                        )
                    }
                    worst_account = setup.account
                    worst_share = 1.0 if trades else 0.0
                    best_account = setup.account
                    selected_account = setup.account
                    selected_share = 1.0 if trades else 0.0
                if trades:
                    mean_bars = float(np.mean([trade.bars_held for trade in trades]))
                for start, end in fitness.fold_bounds(len(bars), folds):
                    fold_signals = fastbt.Signals(
                        signals.long_entry,
                        signals.short_entry,
                        max(int(start), int(signals.valid_from)),
                        exit_index=signals.exit_index,
                    )
                    fold_limits = specs.run_limits_from_strategy(
                        model, setup, end_index=end, close_at_end=True
                    )
                    fold_result = fastbt.run(
                        fold_signals,
                        bars,
                        exit_spec,
                        cost,
                        fold_limits,
                        prepared=prepared,
                    )
                    fold_trades.append(len(fold_result.trades))
                max_bars = fitness.max_holding_bars(model)
                if trades_is < min_trades_is:
                    reasons.append(f"trades IS {trades_is} < {min_trades_is}")
                for fold_index, count in enumerate(fold_trades, 1):
                    if count < min_trades_fold:
                        reasons.append(
                            f"pliegue {fold_index} trades {count} < {min_trades_fold}"
                        )
                if cost_r is None:
                    reasons.append("coste_R Sin datos")
                elif cost_r > max_cost_r:
                    reasons.append(f"coste_R {cost_r:.4f} > {max_cost_r:.4f}")
                if mean_bars > max_bars:
                    reasons.append(
                        f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}"
                    )
            except Exception as exc:  # noqa: BLE001 - se informa la fila, no se aborta
                reasons.append(f"{type(exc).__name__}: {exc}")
        rows.append(
            FeasibilityRow(
                index=index,
                strategy_hash=dsl.strategy_hash(strategy),
                label=_label(strategy),
                trades_is=trades_is,
                fold_trades=fold_trades,
                cost_r=cost_r,
                mean_bars=mean_bars,
                mean_minutes=mean_bars * timeframe_minutes(setup.timeframe),
                feasible=not reasons,
                reasons=reasons,
                cost_by_account=cost_by_account,
                cost_viable_by_account=cost_viable_by_account,
                worst_account=worst_account,
                worst_share=worst_share,
                best_account=best_account,
                selected_account=selected_account,
                selected_share=selected_share,
            )
        )
    n_checked = len(rows)
    n_feasible = sum(1 for row in rows if row.feasible)
    feasible_pct = 100.0 * n_feasible / n_checked if n_checked else 0.0
    return {
        "campaign_id": campaign_id,
        "status": campaign.get("status"),
        "mode": mode,
        "template": template,
        "seed": seed,
        "population": population,
        "n_checked": n_checked,
        "n_feasible": n_feasible,
        "feasible_pct": feasible_pct,
        "passes": feasible_pct >= MIN_FEASIBLE_PCT,
        "rows": [asdict(row) for row in rows],
    }


def check_spec(
    spec_path: str | Path,
    *,
    bars: pd.DataFrame | None = None,
    cost_model_version: int | None = None,
) -> dict[str, Any]:
    """Feasibility sobre una especificación, sin registrar campaña."""
    from . import basket
    from .spec import load_spec

    if basket.is_basket_spec(spec_path):
        return basket.check_spec(spec_path)
    campaign = load_spec(spec_path)
    if cost_model_version is not None:
        campaign = {
            **campaign,
            "config": {
                **(campaign.get("config") or {}),
                "cost_model_version": int(cost_model_version),
            },
        }
    setup = jobs.QueueSetup.from_campaign(campaign)
    if bars is None:
        frame = campaigns._source_frame(
            setup.instrument, setup.timeframe, setup.data_source
        )
        frame = snapshots.closed_bars(frame, setup.timeframe)
        start = pd.Timestamp(campaign["is_start"], tz="UTC")
        end = pd.Timestamp(campaign["is_end"], tz="UTC")
        bars = frame[(frame.index >= start) & (frame.index <= end)]
    context = _context_from(campaign, setup, bars)
    return _check_context(
        *context, campaign_id=str(campaign["campaign_id"])
    )


def _scan_strategies(
    template: str,
    symbol: str,
    timeframe: str,
    session: dict[str, Any],
) -> list[dict[str, Any]]:
    """Grid completa si la plantilla la declara; si no, la plantilla base."""

    try:
        grid.load_grid(template)
    except grid.GridError:
        return [
            genetic.configured_template(
                template,
                instrument=symbol,
                timeframe=timeframe,
                session=session,
            )
        ]
    return grid.grid_strategies(
        template,
        instrument=symbol,
        timeframe=timeframe,
        session=session,
    )


def _scan_slice(
    frame: pd.DataFrame,
    is_range: tuple[str, str | None] | list[str | None] | None,
) -> pd.DataFrame:
    if is_range is None:
        return frame
    start, end = is_range
    begin = pd.Timestamp(start, tz="UTC")
    mask = frame.index >= begin
    if end is not None:
        finish = pd.Timestamp(str(end))
        if len(str(end)) <= 10:
            finish = finish + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        if finish.tzinfo is None:
            finish = finish.tz_localize("UTC")
        mask &= frame.index <= finish
    sliced = frame.loc[mask]
    if len(sliced) == 0:
        raise campaigns.CampaignError("Sin datos: el tramo IS de la TF está vacío")
    return sliced


def _median(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return float(np.median(clean)) if clean else None


def _scan_timeframe(
    template: str,
    symbol: str,
    timeframe: str,
    *,
    source: str,
    account: str,
    firm: str | None,
    use_p75: bool,
    frame: pd.DataFrame,
    session: dict[str, Any],
    config,
) -> dict[str, Any]:
    """Solo operaciones y cost_R; no calcula ni devuelve PnL."""

    if timeframe in {"H4", "D1"} and source != "dukascopy":
        return {
            "timeframe": timeframe,
            "status": "blocked",
            "n_strategies": 0,
            "n_feasible": 0,
            "feasible_pct": 0.0,
            "trades_is": None,
            "fold_trades": [],
            "cost_r": None,
            "mean_bars": None,
            "mean_minutes": None,
            "passes": False,
            "reasons": ["H4/D1 exige datos de Dukascopy"],
        }

    from ..propfund.costs import load_profile

    try:
        profile = load_profile(account, symbol, firm=firm)
        cost = fastbt.cost_from_profile(profile, use_p75=use_p75)
    except Exception as exc:  # noqa: BLE001
        return {
            "timeframe": timeframe,
            "status": "sin_datos",
            "n_strategies": 0,
            "n_feasible": 0,
            "feasible_pct": 0.0,
            "trades_is": None,
            "fold_trades": [],
            "cost_r": None,
            "mean_bars": None,
            "mean_minutes": None,
            "passes": False,
            "reasons": [f"Sin datos: coste {exc}"],
        }

    try:
        strategies = _scan_strategies(template, symbol, timeframe, session)
    except Exception as exc:  # noqa: BLE001
        return {
            "timeframe": timeframe,
            "status": "error",
            "n_strategies": 0,
            "n_feasible": 0,
            "feasible_pct": 0.0,
            "trades_is": None,
            "fold_trades": [],
            "cost_r": None,
            "mean_bars": None,
            "mean_minutes": None,
            "passes": False,
            "reasons": [f"{type(exc).__name__}: {exc}"],
        }

    setup = jobs.QueueSetup(
        instrument=symbol,
        timeframe=timeframe,
        account=account,
        firm=firm,
        use_p75=use_p75,
        cost_accounts=(account,),
        cost_mode="target",
        legacy_cost=True,
        session_tz=session["tz"],
        session_start=session["start"],
        session_end=session["end"],
        flat_at=session["flat_at"],
        weekdays=(0, 1, 2, 3, 4),
        bars=frame,
    ).validated()
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
        cost_model_version=setup.cost_model_version,
    )
    prepared = fastbt.prepare(frame, cost, sessions=(limits,))
    validation = config.validation.for_timeframe(timeframe)
    folds = int(validation.folds)
    max_cost_r = float(config.fitness.cost_r_max)
    rows: list[dict[str, Any]] = []
    for index, strategy in enumerate(strategies):
        trades_is = 0
        fold_trades: list[int] = []
        cost_r = None
        mean_bars = 0.0
        reasons: list[str] = []
        gate = jobs.strategy_gate(strategy, setup)
        if gate:
            reasons.append(gate)
        else:
            try:
                model = dsl.Strategy.model_validate(strategy)
                signals = compiler.compile(model, frame)
                exit_spec = specs.exit_spec_from_strategy(model)
                base_limits = specs.run_limits_from_strategy(
                    model, setup, close_at_end=True
                )
                full = fastbt.run(
                    signals,
                    frame,
                    exit_spec,
                    cost,
                    base_limits,
                    prepared=prepared,
                    collect_metrics=False,
                )
                trades_is = len(full.trades)
                costs = [
                    float(trade.r_cost)
                    for trade in full.trades
                    if trade.r_cost is not None
                ]
                cost_r = float(np.median(costs)) if costs else None
                if full.trades:
                    mean_bars = float(
                        np.mean([trade.bars_held for trade in full.trades])
                    )
                for start, end in fitness.fold_bounds(len(frame), folds):
                    fold_signals = fastbt.Signals(
                        signals.long_entry,
                        signals.short_entry,
                        max(int(start), int(signals.valid_from)),
                        exit_index=signals.exit_index,
                    )
                    fold_limits = specs.run_limits_from_strategy(
                        model, setup, end_index=end, close_at_end=True
                    )
                    fold_result = fastbt.run(
                        fold_signals,
                        frame,
                        exit_spec,
                        cost,
                        fold_limits,
                        prepared=prepared,
                        collect_metrics=False,
                    )
                    fold_trades.append(len(fold_result.trades))
                max_bars = fitness.max_holding_bars(model)
                if trades_is < validation.min_trades_is:
                    reasons.append(
                        f"trades IS {trades_is} < {validation.min_trades_is}"
                    )
                for fold_index, count in enumerate(fold_trades, 1):
                    if count < validation.min_trades_fold:
                        reasons.append(
                            f"pliegue {fold_index} trades {count} < "
                            f"{validation.min_trades_fold}"
                        )
                if cost_r is None:
                    reasons.append("coste_R Sin datos")
                elif cost_r > max_cost_r:
                    reasons.append(f"coste_R {cost_r:.4f} > {max_cost_r:.4f}")
                if mean_bars > max_bars:
                    reasons.append(
                        f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}"
                    )
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"{type(exc).__name__}: {exc}")
        rows.append(
            {
                "index": index,
                "strategy_hash": dsl.strategy_hash(strategy),
                "trades_is": trades_is,
                "fold_trades": fold_trades,
                "cost_r": cost_r,
                "mean_bars": mean_bars,
                "mean_minutes": mean_bars * timeframe_minutes(timeframe),
                "feasible": not reasons,
                "reasons": reasons,
            }
        )

    n_checked = len(rows)
    n_feasible = sum(1 for row in rows if row["feasible"])
    feasible_pct = 100.0 * n_feasible / n_checked if n_checked else 0.0
    fold_matrix = [row["fold_trades"] for row in rows if row["fold_trades"]]
    fold_medians = (
        [float(np.median([row[i] for row in fold_matrix])) for i in range(folds)]
        if fold_matrix
        else []
    )
    reasons = list(
        dict.fromkeys(
            reason
            for row in rows
            for reason in row["reasons"]
            if not row["feasible"]
        )
    )
    return {
        "timeframe": timeframe,
        "status": "ok" if n_checked else "sin_datos",
        "n_strategies": n_checked,
        "n_feasible": n_feasible,
        "feasible_pct": feasible_pct,
        "trades_is": _median([row["trades_is"] for row in rows]),
        "fold_trades": fold_medians,
        "cost_r": _median([row["cost_r"] for row in rows if row["cost_r"] is not None]),
        "mean_bars": _median([row["mean_bars"] for row in rows]),
        "mean_minutes": _median([row["mean_minutes"] for row in rows]),
        "passes": bool(n_checked) and feasible_pct >= MIN_FEASIBLE_PCT,
        "reasons": reasons[:5],
        "rows": rows,
    }


def scan(
    template: str,
    symbol: str,
    *,
    source: str = "dukascopy",
    account: str = "CFD-001",
    firm: str | None = "ftmo",
    use_p75: bool = True,
    is_range: tuple[str, str | None] | list[str | None] | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """TF × factibilidad: solo operaciones y ``cost_R``; sin PnL ni DSR.

    No registra campañas, no escribe ``disc_*``, no lee OOS y no suma pruebas.
    ``frames`` existe solo para tests sintéticos; en producción se carga cada
    TF de la fuente declarada.
    """

    source_key = data_sources.normalize_source(source)
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise campaigns.CampaignError("el símbolo es obligatorio")
    config = load_engine_config()
    timeframes = genetic.template_timeframes(template)
    session = campaigns.template_session(template, symbol)
    selected_is = is_range or config.data_quality.default_segments["is"]
    rows: list[dict[str, Any]] = []
    for timeframe in timeframes:
        try:
            if frames is not None and timeframe in frames:
                frame = frames[timeframe].copy()
            else:
                frame = data_sources.load_source(
                    symbol, timeframe, source=source_key
                ).frame
            frame = snapshots.closed_bars(frame, timeframe)
            frame = _scan_slice(frame, selected_is)
            rows.append(
                _scan_timeframe(
                    template,
                    symbol,
                    timeframe,
                    source=source_key,
                    account=account,
                    firm=firm,
                    use_p75=use_p75,
                    frame=frame,
                    session=session,
                    config=config,
                )
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "timeframe": timeframe,
                    "status": "sin_datos",
                    "n_strategies": 0,
                    "n_feasible": 0,
                    "feasible_pct": 0.0,
                    "trades_is": None,
                    "fold_trades": [],
                    "cost_r": None,
                    "mean_bars": None,
                    "mean_minutes": None,
                    "passes": False,
                    "reasons": [f"Sin datos: {exc}"],
                    "rows": [],
                }
            )
    return {
        "template": template,
        "symbol": symbol,
        "source": source_key,
        "account": account,
        "timeframes": rows,
        "n_feasible_timeframes": sum(1 for row in rows if row["passes"]),
        "passes": any(row["passes"] for row in rows),
    }


__all__ = ["FeasibilityRow", "MIN_FEASIBLE_PCT", "check", "scan"]
