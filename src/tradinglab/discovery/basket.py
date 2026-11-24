"""Cesta multi-símbolo (Q3/N2): una hipótesis, varios símbolos.

La cesta es **una sola campaña**: ``n_total`` cuenta combinaciones de la
rejilla, no combinaciones × símbolos. Cada combinación se evalúa como un
portfolio de piernas hermanas (una por símbolo, mismo genoma); el R diario se
agrega por fecha y los pliegues son fechas globales del IS común.

* ``register``/``preflight``/``check`` antes de aprobar: no calculan
  expectativa, PF ni percentil (solo operaciones, coste y tiempo).
* ``run_campaign`` solo con campaña aprobada: aplica coste y swap por
  símbolo/cuenta (``swap_credit=false``), agrega R, calcula pliegues globales,
  control de deriva por cesta, OOS-1 por cesta y deja OOS-2 sellado.
* Todo rendimiento pasa por ``guard.require_approved``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ..propfund.registry import load_registry
from . import (
    __version__,
    campaigns,
    compiler,
    databank,
    dsl,
    fastbt,
    fitness,
    genetic,
    grid,
    jobs,
    metrics,
    snapshots,
    specs,
)
from .config import load_engine_config
from .costs import assumed_slippage_for, build_cost_book_for_setup
from .data_sources import normalize_source
from .timeframes import normalize_timeframe, timeframe_minutes


class BasketError(ValueError):
    pass


def is_basket_spec(path: str | Path) -> bool:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return bool(data.get("basket"))


def is_basket_campaign(campaign: dict[str, Any] | None) -> bool:
    return bool(((campaign or {}).get("config") or {}).get("basket"))


def load(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    basket = data.get("basket")
    if not isinstance(basket, list) or len(basket) < 2:
        raise BasketError("basket debe ser una lista de >= 2 símbolos")
    symbols = []
    for item in basket:
        symbol = str(item or "").strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if len(symbols) < 2:
        raise BasketError("basket necesita >= 2 símbolos distintos")
    timeframe = normalize_timeframe(str(data.get("timeframe") or "D1"))
    template = str(data.get("template") or "").strip()
    if not template:
        raise BasketError("la spec de cesta no declara template")
    if timeframe not in genetic.template_timeframes(template):
        raise BasketError(f"la plantilla {template} no declara {timeframe}")
    config = load_engine_config()
    start = str((data.get("segments") or {}).get("is", [None])[0] or "")
    if not start:
        raise BasketError("la cesta necesita segments.is")
    start_ts = pd.Timestamp(start)
    cost_map: dict[str, dict[str, Any]] = {}
    registry = load_registry()
    base_account = str(data.get("account") or "CFD-001").upper()
    base_firm = data.get("firm")
    for symbol in symbols:
        limit = config.data_quality.usable_from_for(
            str(data.get("data_source") or "dukascopy"), symbol, timeframe
        )
        if limit is not None and start_ts.date() < limit:
            raise BasketError(
                f"{symbol}: IS empieza antes de usable_from ({start_ts.date()} < {limit})"
            )
        raw = (data.get("basket_costs") or {}).get(symbol) or {}
        account_id = str(raw.get("account") or base_account).upper()
        account = registry.accounts.get(account_id)
        if account is None:
            raise BasketError(f"{symbol}: cuenta no registrada {account_id}")
        if symbol not in account.allowed_instruments:
            raise BasketError(f"{account_id} no permite {symbol}")
        firm = str(raw.get("firm") or base_firm or registry.firm_of(account_id).id)
        accounts = [
            str(item).strip().upper()
            for item in (raw.get("cost_accounts") or [account_id])
            if str(item).strip()
        ]
        mode = str(raw.get("cost_mode") or "best").lower()
        if mode not in {"best", "worst", "target"}:
            raise BasketError(f"{symbol}: cost_mode {mode} inválido")
        if mode == "target" and len(accounts) != 1:
            raise BasketError(f"{symbol}: target exige una cuenta")
        for cost_account in accounts:
            candidate = registry.accounts.get(cost_account)
            if candidate is None:
                raise BasketError(f"{symbol}: cuenta de coste {cost_account} no registrada")
            if symbol not in candidate.allowed_instruments:
                raise BasketError(f"{cost_account} no permite {symbol}")
        cost_map[symbol] = {
            "account": account_id,
            "firm": firm,
            "cost_accounts": accounts,
            "cost_mode": mode,
        }
    mode = str(data.get("mode") or "grid").lower()
    if mode != "grid":
        raise BasketError("la cesta mínima solo soporta mode: grid")
    grid_spec = grid.validate_grid(data.get("grid"), template)
    base = grid.grid_strategies(
        template,
        instrument=symbols[0],
        timeframe=timeframe,
        session=data.get("session"),
        grid_spec=grid_spec,
    )
    return {
        "campaign_id": str(data.get("campaign_id") or target.stem),
        "symbols": symbols,
        "timeframe": timeframe,
        "template": template,
        "profile": str(data.get("profile") or "small").strip().lower(),
        "mode": mode,
        "data_source": normalize_source(str(data.get("data_source") or "dukascopy")),
        "segments": data.get("segments"),
        "seed": int(data.get("seed", 0)),
        "grid": grid_spec,
        "cost": cost_map,
        "strategies": base,
        "session": data.get("session"),
        "spec_path": str(target),
    }


def combine_daily(series: dict[str, pd.Series]) -> pd.Series:
    if not series:
        raise BasketError("Sin datos: cesta vacía")
    frame = pd.concat(
        [value.rename(name) for name, value in series.items()],
        axis=1,
    ).fillna(0.0)
    combined = frame.sum(axis=1).sort_index()
    combined.name = "r"
    return combined


def basket_percentile(
    per_symbol: list[dict[str, Any]],
    *,
    percentile_min: float = 90.0,
    campaign_id: str = "",
    approved: bool = False,
) -> dict[str, Any]:
    """Percentil de la cesta a partir de los drift por símbolo.

    Cada resultado debe traer ``random_means``, ``trades`` y
    ``strategy_expectancy_r``. La media aleatoria de la cesta pondera por el
    número de operaciones de cada símbolo. Es rendimiento: exige campaña
    aprobada o el flag interno de test.
    """

    from .guard import require_approved

    require_approved(campaign_id, approved=approved, action="basket_percentile")

    if not per_symbol or any(
        not item.get("random_means") for item in per_symbol
    ):
        return {"percentile": None, "passed": False, "simulations": 0}
    sizes = [len(item["random_means"]) for item in per_symbol]
    simulations = min(sizes)
    trades = sum(int(item.get("trades") or 0) for item in per_symbol)
    if trades <= 0:
        return {"percentile": None, "passed": False, "simulations": simulations}
    actual = sum(
        float(item.get("strategy_expectancy_r") or 0.0)
        * int(item.get("trades") or 0)
        for item in per_symbol
    ) / trades
    random_basket = np.zeros(simulations, dtype=float)
    for item in per_symbol:
        weight = int(item.get("trades") or 0) / trades
        random_basket += np.asarray(item["random_means"][:simulations]) * weight
    value = 100.0 * float(np.mean(random_basket < actual))
    return {
        "percentile": round(value, 2),
        "passed": value >= float(percentile_min),
        "percentile_min": float(percentile_min),
        "simulations": simulations,
        "trades": trades,
        "basket_expectancy_r": round(actual, 6),
    }


# ---------------------------------------------------------------------------
# Contexto por símbolo: coste, límites y barras preparadas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SymbolContext:
    setup: jobs.QueueSetup
    book: Any
    limits: fastbt.RunLimits
    prepared: fastbt.PreparedBars


def _setup_for(
    campaign_or_spec: dict[str, Any],
    symbol: str,
    strategy: dict[str, Any],
    segment: str = "is",
) -> jobs.QueueSetup:
    cost = campaign_or_spec["cost"][symbol]
    model = dsl.Strategy.model_validate(
        {**strategy, "instrument": symbol, "timeframe": campaign_or_spec["timeframe"]}
    )
    segments = campaign_or_spec["segments"]
    config = load_engine_config()
    return jobs.QueueSetup(
        instrument=symbol,
        timeframe=campaign_or_spec["timeframe"],
        start=segments[segment][0],
        end=segments[segment][1],
        account=cost["account"],
        firm=cost["firm"],
        cost_accounts=tuple(cost["cost_accounts"]),
        cost_mode=cost["cost_mode"],
        legacy_cost=False,
        session_tz=config.data_quality.tz_for(symbol),
        session_start=model.session.start,
        session_end=model.session.end,
        flat_at=model.session.flat_at,
        weekdays=(0, 1, 2, 3, 4),
        data_source=campaign_or_spec["data_source"],
    ).validated()


def _context(
    campaign_or_spec: dict[str, Any],
    symbol: str,
    strategy: dict[str, Any],
    frame: pd.DataFrame,
    segment: str = "is",
) -> _SymbolContext:
    setup = _setup_for(campaign_or_spec, symbol, strategy, segment)
    book = build_cost_book_for_setup(setup)
    model = dsl.Strategy.model_validate(
        {**strategy, "instrument": symbol, "timeframe": campaign_or_spec["timeframe"]}
    )
    limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
    prepared = fastbt.prepare(
        frame,
        book,
        atr_windows=(model.exit.stop.n, setup.trail_n),
        sessions=(limits,),
    )
    return _SymbolContext(setup=setup, book=book, limits=limits, prepared=prepared)


def _run_leg(
    campaign_or_spec: dict[str, Any],
    symbol: str,
    strategy: dict[str, Any],
    frame: pd.DataFrame,
    *,
    segment: str,
    context: _SymbolContext | None = None,
) -> tuple[list[fastbt.Trade], pd.Series, fastbt.FastResult, _SymbolContext]:
    model = dsl.Strategy.model_validate(
        {**strategy, "instrument": symbol, "timeframe": campaign_or_spec["timeframe"]}
    )
    context = context or _context(campaign_or_spec, symbol, strategy, frame, segment)
    signals = compiler.compile(model, frame)
    full = fastbt.run(
        signals,
        frame,
        specs.exit_spec_from_strategy(model),
        context.book,
        context.limits,
        prepared=context.prepared,
    )
    applied = context.book.apply(
        full.trades,
        session_tz=context.limits.session_tz,
        point=context.setup.point,
    )
    trades = [replace(trade, instrument=symbol) for trade in applied.trades]
    return trades, applied.daily_r, full, context, applied.cost_values


def _collect_combo(
    campaign_or_spec: dict[str, Any],
    strategy: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    *,
    segment: str = "is",
    contexts: dict[tuple[str, str], _SymbolContext] | None = None,
) -> tuple[list[fastbt.Trade], dict[str, pd.Series], dict[str, int]]:
    """Operaciones y R diario por símbolo. No calcula expectativa ni PF."""

    trades: list[fastbt.Trade] = []
    daily: dict[str, pd.Series] = {}
    counts: dict[str, int] = {}
    account_values: dict[str, list[float]] = {}
    contexts = contexts if contexts is not None else {}
    for symbol in campaign_or_spec["symbols"]:
        frame = frames[symbol]
        if len(frame) < 100:
            raise BasketError(f"{symbol}: menos de 100 barras {segment}")
        key = (symbol, dsl.strategy_hash(
            {**strategy, "instrument": symbol, "timeframe": campaign_or_spec["timeframe"]}
        ))
        context = contexts.get(key)
        leg_trades, leg_daily, _full, context, leg_costs = _run_leg(
            campaign_or_spec,
            symbol,
            strategy,
            frame,
            segment=segment,
            context=context,
        )
        contexts[key] = context
        trades.extend(leg_trades)
        daily[symbol] = leg_daily
        counts[symbol] = len(leg_trades)
        for account, values in leg_costs.items():
            account_values.setdefault(account, []).extend(values)
    return trades, daily, counts, account_values


def _pool_cost_by_account(
    trades: list[fastbt.Trade],
) -> dict[str, float | None]:
    values: dict[str, list[float]] = {}
    for trade in trades:
        account = getattr(trade, "selected_account", None)
        if account is None:
            account = getattr(trade, "account", None)
        if not account:
            continue
        if trade.r_cost is None:
            continue
        values.setdefault(str(account), []).append(float(trade.r_cost))
    return {
        str(account): (float(np.median(items)) if items else None)
        for account, items in values.items()
    }


def _fold_rows(
    trades: list[fastbt.Trade],
    calendar: pd.DatetimeIndex,
    folds: int,
    *,
    point: float = 0.01,
) -> list[dict[str, Any]]:
    config = load_engine_config()
    rows: list[dict[str, Any]] = []
    for start, end in fitness.fold_bounds(len(calendar), folds):
        dates = set(calendar[start : end + 1].date)
        selected = [
            trade
            for trade in trades
            if trade.exit_time.tz_convert(
                config.data_quality.tz_for(trade.instrument or "")
            ).date()
            in dates
        ]
        daily: dict[Any, float] = {}
        for trade in selected:
            if trade.r_net is None or not np.isfinite(float(trade.r_net)):
                continue
            day = trade.exit_time.tz_convert(
                config.data_quality.tz_for(trade.instrument or "")
            ).date()
            daily[day] = daily.get(day, 0.0) + float(trade.r_net)
        series = pd.Series(daily, dtype=float).sort_index()
        if len(series):
            series.index = pd.to_datetime(series.index)
        payload = metrics.summarize(selected, series, point=point)
        rows.append(
            {
                "start_index": int(start),
                "end_index": int(end),
                "start": calendar[start].isoformat(),
                "end": calendar[end].isoformat(),
                "trades": int(payload.get("trades") or 0),
                "expectancy_r": payload.get("expectancy_r"),
                "profit_factor": payload.get("profit_factor"),
                "max_dd_r": payload.get("max_dd_r"),
            }
        )
    return rows


def _calendar(frames: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    config = load_engine_config()
    dates: set[Any] = set()
    for symbol, frame in frames.items():
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            index = index.tz_localize("UTC")
        dates.update(index.tz_convert(config.data_quality.tz_for(symbol)).date)
    if not dates:
        raise BasketError("Sin datos: cesta vacía")
    return pd.DatetimeIndex(sorted(dates))


def _basket_metrics(
    trades: list[fastbt.Trade],
    daily: pd.Series,
    frames: dict[str, pd.DataFrame],
    strategy: dict[str, Any],
    campaign_or_spec: dict[str, Any],
    *,
    segment: str,
    account_values: dict[str, list[float]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], float | None]:
    config = load_engine_config()
    validation = config.validation.for_timeframe(campaign_or_spec["timeframe"])
    folds = int(validation.folds)
    point = float(campaign_or_spec.get("point", 0.01))
    calendar = _calendar(frames)
    fold_rows = _fold_rows(trades, calendar, folds, point=point)
    fold_expectancy = [row["expectancy_r"] for row in fold_rows]
    clean = [float(value) for value in fold_expectancy if value is not None]
    median_expectancy = float(np.median(clean)) if clean else 0.0
    positive = sum(1 for value in clean if value > 0)
    positive_fraction = positive / len(fold_rows) if fold_rows else 0.0
    dispersion = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    stability = float(positive_fraction - 0.25 * min(dispersion, 2.0))
    worst_dd = max(
        (abs(float(row["max_dd_r"] or 0.0)) for row in fold_rows), default=0.0
    )
    base_model = dsl.Strategy.model_validate(
        {
            **strategy,
            "instrument": campaign_or_spec["symbols"][0],
            "timeframe": campaign_or_spec["timeframe"],
        }
    )
    node_count = fitness.complexity(base_model)
    payload = metrics.summarize(trades, daily, point=point)
    cost_values = [
        float(trade.r_cost)
        for trade in trades
        if trade.r_cost is not None and np.isfinite(float(trade.r_cost))
    ]
    cost_r = float(np.median(cost_values)) if cost_values else None
    costs_by_account = (
        {
            str(account): (float(np.median(values)) if values else None)
            for account, values in account_values.items()
        }
        if account_values
        else _pool_cost_by_account(trades)
    )
    max_cost_r = float(config.fitness.cost_r_max)
    cost_viable = {
        account: (None if value is None else bool(float(value) <= max_cost_r))
        for account, value in costs_by_account.items()
    }
    valid = {k: v for k, v in costs_by_account.items() if v is not None}
    best_account = min(valid, key=lambda name: valid[name]) if valid else None
    worst_account = max(valid, key=lambda name: valid[name]) if valid else None
    selected_counts: dict[str, int] = {}
    for trade in trades:
        account = getattr(trade, "selected_account", None)
        if account:
            selected_counts[str(account)] = selected_counts.get(str(account), 0) + 1
    selected_account = (
        max(selected_counts, key=lambda name: selected_counts[name])
        if selected_counts
        else None
    )
    selected_share = (
        selected_counts[selected_account] / sum(selected_counts.values())
        if selected_account
        else 0.0
    )
    base_expectancy = payload.get("expectancy_r")
    plus, _delta = metrics.cost_sensitivity(trades, point)
    cost_drop = (
        max(0.0, float(base_expectancy) - float(plus))
        if base_expectancy is not None and plus is not None
        else 0.0
    )
    mean_bars = (
        float(np.mean([trade.bars_held for trade in trades])) if trades else 0.0
    )
    max_bars = fitness.max_holding_bars(base_model)
    violations: list[str] = []
    if len(trades) < int(validation.min_trades_is):
        violations.append(
            f"trades IS {len(trades)} < {validation.min_trades_is}"
        )
    for row in fold_rows:
        if int(row["trades"]) < int(validation.min_trades_fold):
            violations.append(
                f"pliegue {row['start']} trades {row['trades']} < "
                f"{validation.min_trades_fold}"
            )
    concentration = payload.get("concentration")
    if concentration is None or float(concentration) > 0.20:
        violations.append(f"concentración {concentration} > 0,20")
    if cost_r is None:
        violations.append("coste_R Sin datos")
    elif cost_r > max_cost_r:
        violations.append(f"coste_R {cost_r:.4f} > {max_cost_r:.4f}")
    if mean_bars > max_bars:
        violations.append(f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}")
    fitness_vector = [
        float(median_expectancy),
        float(stability),
        -float(worst_dd),
        -float(node_count),
        -float(cost_drop),
    ]
    raw = {
        "expectancy_r": median_expectancy,
        "positive_fraction": positive_fraction,
        "dispersion": dispersion,
        "stability": stability,
        "worst_dd_r": worst_dd,
        "complexity": node_count,
        "cost_r": cost_r,
        "cost_drop": cost_drop,
        "mean_bars": mean_bars,
        "concentration": concentration,
        "raw_expectancy_r": payload.get("gross_expectancy_r"),
        "raw_total_r": payload.get("gross_total_r"),
    }
    is_payload = {
        **payload,
        "cost_r": cost_r,
        "cost_by_account": costs_by_account,
        "cost_viable_by_account": cost_viable,
        "cost_accounts": sorted(
            {
                account
                for symbol in campaign_or_spec["symbols"]
                for account in campaign_or_spec["cost"][symbol]["cost_accounts"]
            }
        ),
        "cost_mode": "basket",
        "worst_account": worst_account,
        "best_account": best_account,
        "selected_account": selected_account,
        "selected_share": selected_share,
    }
    metrics_payload = {
        "fitness": fitness_vector,
        "raw": raw,
        "raw_expectancy_r": payload.get("gross_expectancy_r"),
        "raw_total_r": payload.get("gross_total_r"),
        "folds": fold_rows,
        "violations": violations,
        "cost_r": cost_r,
        "complexity": node_count,
        "is": is_payload,
    }
    return (
        {
            "metrics": metrics_payload,
            "fitness": fitness_vector,
            "feasible": not violations,
            "violations": violations,
            "cost_r": cost_r,
            "complexity": node_count,
            "folds": fold_rows,
            "trades_count": len(trades),
            "daily_returns": daily,
        },
        fold_rows,
        cost_r,
    )


# ---------------------------------------------------------------------------
# Registro de una spec de cesta
# ---------------------------------------------------------------------------


def _combined_digest(hashes: dict[str, str]) -> str:
    payload = json.dumps(hashes, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def register(
    path: str | Path,
    *,
    frames: dict[str, pd.DataFrame] | None = None,
    dry_run: bool = False,
    db_path: str | Path | None = None,
    now: Any | None = None,
) -> dict[str, Any]:
    """Registra un borrador de campaña de cesta (no aprueba, no ejecuta)."""

    spec = load(path)
    identifier = str(spec["campaign_id"])
    symbols = spec["symbols"]
    engine = load_engine_config()
    segments = campaigns._normalize_segments(  # noqa: SLF001
        spec["segments"], engine.data_quality.default_segments
    )
    source_frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        if frames is not None:
            if symbol not in frames:
                raise BasketError(f"Sin datos: falta el frame de {symbol}")
            frame = frames[symbol].copy()
        else:
            frame = campaigns._source_frame(  # noqa: SLF001
                symbol, spec["timeframe"], spec["data_source"]
            )
        source_frames[symbol] = snapshots.closed_bars(
            frame, spec["timeframe"], now=now
        )
    ends = []
    for symbol in symbols:
        ends.append(
            campaigns._resolve_oos2_end(  # noqa: SLF001
                source_frames[symbol], segments["oos2"][1]
            )
        )
    common_end = min(ends)
    segments["oos2"][1] = common_end.isoformat()

    reports: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    rows: dict[str, int] = {}
    paths: dict[str, str] = {}
    for symbol in symbols:
        frame = source_frames[symbol]
        report, useful_start = campaigns._quality(  # noqa: SLF001
            frame, symbol, spec["timeframe"], segments, spec["data_source"]
        )
        reports[symbol] = {
            "status": report.status,
            "useful_start": useful_start,
            "issues": list(report.issues),
        }
        sliced = campaigns._hash_range(  # noqa: SLF001
            frame, segments["is"][0], common_end
        )
        from .data_quality import dataset_hash

        hashes[symbol] = dataset_hash(sliced)
        rows[symbol] = int(len(sliced))
        if not dry_run:
            info = snapshots.write_snapshot(
                f"{identifier}__{symbol}", sliced, db_path=db_path, now=now
            )
            paths[symbol] = info.path
        else:
            paths[symbol] = str(
                snapshots.snapshot_path_for(
                    f"{identifier}__{symbol}", db_path
                )
            )
    dataset_digest = _combined_digest(hashes)
    base = symbols[0]
    statuses = [reports[symbol]["status"] for symbol in symbols]
    quality_status = (
        "fail"
        if "fail" in statuses
        else "warn" if "warn" in statuses else "ok"
    )
    issues = [
        f"{symbol}: {issue}"
        for symbol in symbols
        for issue in reports[symbol]["issues"]
    ]
    useful_start = max(
        (str(reports[symbol]["useful_start"]) for symbol in symbols),
        default=None,
    )
    base_cost = spec["cost"][base]
    slippage_value, slippage_source = assumed_slippage_for(base)
    session = dict(spec["strategies"][0].get("session") or {})
    config_payload: dict[str, Any] = {
        "instrument": base,
        "timeframe": spec["timeframe"],
        "timeframe_minutes": timeframe_minutes(spec["timeframe"]),
        "template": spec["template"],
        "profile": spec["profile"],
        "mode": "grid",
        "data_source": spec["data_source"],
        "seed": int(spec["seed"]),
        "engine_profile": spec["profile"],
        "is_start": segments["is"][0],
        "is_end": segments["is"][1],
        "oos1_start": segments["oos1"][0],
        "oos1_end": segments["oos1"][1],
        "oos2_start": segments["oos2"][0],
        "oos2_end": segments["oos2"][1],
        "segments": segments,
        "dataset_hash": dataset_digest,
        "n_total": len(spec["strategies"]),
        "cost": {
            "account": base_cost["account"],
            "firm": base_cost["firm"],
            "use_p75": True,
            "accounts": list(base_cost["cost_accounts"]),
            "mode": base_cost["cost_mode"],
            "assumed_slippage": {
                "value": float(slippage_value),
                "source": str(slippage_source),
            },
        },
        "session": session,
        "point": 0.01,
        "limits": {"weekdays": [0, 1, 2, 3, 4], "stop_n": 14, "trail_n": 14},
        "quality": {
            "status": quality_status,
            "useful_start": useful_start,
            "issues": issues,
            "symbols": reports,
        },
        "engine_version": __version__,
        "grid": spec["grid"],
        "grid_size": len(spec["strategies"]),
        "controls": {
            "test_vs_random_direction": {
                "version": 1,
                "simulations": 1000,
                "percentile_min": 90,
                "scope": "campaigns registered from 2026-11-23",
            }
        },
        "basket": {
            "symbols": symbols,
            "cost": spec["cost"],
            "snapshots": {
                symbol: {
                    "path": paths[symbol],
                    "hash": hashes[symbol],
                    "rows": rows[symbol],
                }
                for symbol in symbols
            },
            "dataset_hash": dataset_digest,
        },
    }
    config_json = json.dumps(config_payload, sort_keys=True, ensure_ascii=False)
    config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    preview = {
        "campaign_id": identifier,
        "status": "draft",
        "approved_at": None,
        "n_total": int(config_payload["n_total"]),
        "dataset_hash": dataset_digest,
        "snapshot_hash": hashes[base],
        "snapshot_path": paths[base],
        "snapshot_rows": rows[base],
        "config_hash": config_hash,
        "config": config_payload,
        "quality": config_payload["quality"],
        "rows": rows[base],
        "oos2_end": common_end.isoformat(),
        "read_at": snapshots.read_time(now).isoformat(),
    }
    if dry_run:
        preview["dry_run"] = True
        return preview
    existing = databank.get_campaign(identifier, db_path=db_path)
    if existing is not None:
        if (
            existing["status"] == "draft"
            and existing["config_hash"] == config_hash
        ):
            existing["campaign_id"] = existing["id"]
            return existing
        raise BasketError(f"la campaña {identifier} ya está registrada")
    databank.add_campaign(
        identifier,
        config_payload,
        instrument=base,
        timeframe=spec["timeframe"],
        template=spec["template"],
        engine_profile=spec["profile"],
        status="draft",
        quality=config_payload["quality"],
        n_total=int(config_payload["n_total"]),
        dataset_hash=dataset_digest,
        snapshot_path=paths[base],
        snapshot_hash=hashes[base],
        snapshot_rows=rows[base],
        snapshot_at=snapshots.read_time(now).isoformat(),
        db_path=db_path,
    )
    campaign = databank.get_campaign(identifier, db_path=db_path)
    if campaign is None:  # pragma: no cover
        raise BasketError("no se pudo registrar la campaña de cesta")
    campaign["campaign_id"] = campaign["id"]
    return campaign


# ---------------------------------------------------------------------------
# Preflight, viabilidad y lectura de segmentos
# ---------------------------------------------------------------------------


def _campaign_spec(campaign: dict[str, Any]) -> dict[str, Any]:
    config = campaign.get("config") or {}
    basket = config.get("basket") or {}
    symbols = list(basket.get("symbols") or [])
    if len(symbols) < 2:
        raise BasketError("la campaña no declara una cesta de >= 2 símbolos")
    return {
        "campaign_id": campaign.get("id") or campaign.get("campaign_id"),
        "symbols": symbols,
        "timeframe": str(campaign.get("timeframe") or config.get("timeframe")),
        "template": str(campaign.get("template") or config.get("template")),
        "mode": "grid",
        "data_source": str(config.get("data_source") or "broker"),
        "segments": {
            "is": [campaign["is_start"], campaign["is_end"]],
            "oos1": [campaign["oos1_start"], campaign["oos1_end"]],
            "oos2": [campaign["oos2_start"], campaign["oos2_end"]],
        },
        "seed": int(config.get("seed", 0)),
        "grid": config.get("grid"),
        "cost": basket.get("cost") or {},
        "snapshots": basket.get("snapshots") or {},
        "session": config.get("session"),
        "point": float(config.get("point", 0.01)),
    }


def _strategies(campaign_or_spec: dict[str, Any]) -> list[dict[str, Any]]:
    return grid.grid_strategies(
        campaign_or_spec["template"],
        instrument=campaign_or_spec["symbols"][0],
        timeframe=campaign_or_spec["timeframe"],
        session=campaign_or_spec.get("session"),
        grid_spec=campaign_or_spec["grid"],
    )


def _segment_frames(
    campaign: dict[str, Any],
    segment: str,
    *,
    frames: dict[str, pd.DataFrame] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    spec = _campaign_spec(campaign)
    start = campaigns._start_ts(spec["segments"][segment][0])  # noqa: SLF001
    end = campaigns._end_ts(spec["segments"][segment][1])  # noqa: SLF001
    out: dict[str, pd.DataFrame] = {}
    for symbol in spec["symbols"]:
        if frames is not None:
            frame = frames[symbol]
        else:
            info = spec["snapshots"].get(symbol) or {}
            if not info.get("path"):
                raise BasketError(f"Sin datos: snapshot de {symbol}")
            try:
                frame = snapshots.load_snapshot(info["path"], info.get("hash"))
            except snapshots.SnapshotError as exc:
                raise BasketError(str(exc)) from exc
        frame = snapshots.closed_bars(frame, spec["timeframe"])
        sliced = frame[(frame.index >= start) & (frame.index <= end)]
        if len(sliced) == 0:
            raise BasketError(f"Sin datos: tramo {segment} de {symbol} vacío")
        out[symbol] = sliced
    return out


def segment_frames(
    campaign: dict[str, Any],
    segment: str,
    *,
    frames: dict[str, pd.DataFrame] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, pd.DataFrame]:
    return _segment_frames(
        campaign, segment, frames=frames, db_path=db_path
    )


def preflight(path_or_campaign: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_campaign, dict):
        return preflight_campaign(path_or_campaign)
    spec = load(path_or_campaign)
    strategies = spec["strategies"]
    return {
        "campaign_id": spec["campaign_id"],
        "status": "draft",
        "instrument": "BASKET",
        "timeframe": spec["timeframe"],
        "template": spec["template"],
        "mode": spec["mode"],
        "seed": spec["seed"],
        "population": len(strategies),
        "generated": len(strategies),
        "valid": len(strategies),
        "rejected": 0,
        "duplicates": 0,
        "reasons": {},
        "last_error": None,
    }


def preflight_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    spec = _campaign_spec(campaign)
    strategies = _strategies(spec)
    reasons: dict[str, int] = {}
    valid = 0
    for strategy in strategies:
        ok = True
        for symbol in spec["symbols"]:
            candidate = {
                **strategy,
                "instrument": symbol,
                "timeframe": spec["timeframe"],
            }
            errors = dsl.validate(candidate)
            if errors:
                for error in errors:
                    reasons[error] = reasons.get(error, 0) + 1
                ok = False
        if ok:
            valid += 1
    return {
        "campaign_id": str(campaign.get("id") or campaign.get("campaign_id")),
        "status": campaign.get("status"),
        "instrument": "BASKET",
        "timeframe": spec["timeframe"],
        "template": spec["template"],
        "mode": "grid",
        "seed": spec["seed"],
        "population": len(strategies),
        "generated": len(strategies),
        "valid": valid,
        "rejected": len(strategies) - valid,
        "duplicates": len(strategies)
        - len({dsl.strategy_hash(strategy) for strategy in strategies}),
        "reasons": reasons,
        "last_error": campaign.get("last_error"),
    }


def check_campaign(
    campaign: dict[str, Any],
    *,
    frames: dict[str, pd.DataFrame] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Viabilidad de una campaña de cesta registrada. Sin PnL ni expectativa."""

    spec = _campaign_spec(campaign)
    source_frames = _segment_frames(
        campaign, "is", frames=frames, db_path=db_path
    )
    return _check_frames(spec, campaign, source_frames)


def check_spec(path: str | Path, *, frames: dict[str, pd.DataFrame] | None = None) -> dict[str, Any]:
    spec = load(path)
    source_frames: dict[str, pd.DataFrame] = {}
    for symbol in spec["symbols"]:
        if frames is not None:
            if symbol not in frames:
                raise BasketError(f"Sin datos: falta el frame de {symbol}")
            frame = frames[symbol].copy()
        else:
            frame = campaigns._source_frame(  # noqa: SLF001
                symbol, spec["timeframe"], spec["data_source"]
            )
        frame = snapshots.closed_bars(frame, spec["timeframe"])
        start = pd.Timestamp(spec["segments"]["is"][0], tz="UTC")
        end = pd.Timestamp(spec["segments"]["is"][1], tz="UTC")
        source_frames[symbol] = frame[
            (frame.index >= start) & (frame.index <= end)
        ]
    return _check_frames(spec, None, source_frames)


def _check_frames(
    spec: dict[str, Any],
    campaign: dict[str, Any] | None,
    frames: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    config = load_engine_config()
    validation = config.validation.for_timeframe(spec["timeframe"])
    folds = int(validation.folds)
    max_cost_r = float(config.fitness.cost_r_max)
    strategies = spec.get("strategies") or _strategies(spec)
    rows: list[dict[str, Any]] = []
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
        try:
            trades, _daily, _counts, account_values = _collect_combo(
                spec, strategy, frames
            )
            trades_is = len(trades)
            costs = [
                float(trade.r_cost)
                for trade in trades
                if trade.r_cost is not None
            ]
            cost_r = float(np.median(costs)) if costs else None
            if trades:
                mean_bars = float(np.mean([trade.bars_held for trade in trades]))
            for start, end in fitness.fold_bounds(len(_calendar(frames)), folds):
                dates = set(_calendar(frames)[start : end + 1].date)
                fold_trades.append(
                    sum(
                        1
                        for trade in trades
                        if trade.exit_time.tz_convert(
                            config.data_quality.tz_for(
                                trade.instrument or spec["symbols"][0]
                            )
                        ).date()
                        in dates
                    )
                )
            cost_by_account = {
                str(account): (float(np.median(values)) if values else None)
                for account, values in account_values.items()
            }
            cost_viable_by_account = {
                name: (
                    None
                    if value is None
                    else bool(float(value) <= max_cost_r)
                )
                for name, value in cost_by_account.items()
            }
            valid = {
                name: value
                for name, value in cost_by_account.items()
                if value is not None
            }
            if valid:
                best_account = min(valid, key=lambda name: valid[name])
                worst_account = max(valid, key=lambda name: valid[name])
            counts: dict[str, int] = {}
            for trade in trades:
                account = getattr(trade, "selected_account", None)
                if account:
                    counts[str(account)] = counts.get(str(account), 0) + 1
            if counts:
                selected_account = max(counts, key=lambda name: counts[name])
                selected_share = counts[selected_account] / sum(counts.values())
            model = dsl.Strategy.model_validate(
                {
                    **strategy,
                    "instrument": spec["symbols"][0],
                    "timeframe": spec["timeframe"],
                }
            )
            max_bars = fitness.max_holding_bars(model)
            if trades_is < int(validation.min_trades_is):
                reasons.append(
                    f"trades IS {trades_is} < {validation.min_trades_is}"
                )
            for fold_index, count in enumerate(fold_trades, 1):
                if count < int(validation.min_trades_fold):
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
        except Exception as exc:  # noqa: BLE001 - se informa la fila
            reasons.append(f"{type(exc).__name__}: {exc}")
        rows.append(
            {
                "index": index,
                "strategy_hash": dsl.strategy_hash(strategy),
                "label": " ".join(
                    f"{name}={value}"
                    for name, value in (
                        ("fast_n", (strategy.get("long_entry") or {}).get("left", {}).get("n")),
                        ("slow_n", (strategy.get("long_entry") or {}).get("right", {}).get("n")),
                        ("stop", (strategy.get("exit") or {}).get("stop", {}).get("mult")),
                    )
                )
                or "cesta",
                "trades_is": trades_is,
                "fold_trades": fold_trades,
                "cost_r": cost_r,
                "mean_bars": mean_bars,
                "mean_minutes": mean_bars
                * timeframe_minutes(spec["timeframe"]),
                "feasible": not reasons,
                "reasons": reasons,
                "cost_by_account": cost_by_account,
                "cost_viable_by_account": cost_viable_by_account,
                "worst_account": worst_account,
                "worst_share": worst_share,
                "best_account": best_account,
                "selected_account": selected_account,
                "selected_share": selected_share,
            }
        )
    feasible = sum(1 for row in rows if row["feasible"])
    pct = 100.0 * feasible / len(rows) if rows else 0.0
    return {
        "campaign_id": str(
            (campaign or {}).get("id")
            or (campaign or {}).get("campaign_id")
            or spec.get("campaign_id")
        ),
        "status": (campaign or {}).get("status"),
        "mode": "grid",
        "template": spec["template"],
        "seed": spec.get("seed", 0),
        "population": len(rows),
        "n_checked": len(rows),
        "n_feasible": feasible,
        "feasible_pct": pct,
        "passes": pct >= 50.0,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Ejecución de la campaña (solo aprobada)
# ---------------------------------------------------------------------------


def _drift_basket(
    campaign: dict[str, Any],
    spec: dict[str, Any],
    strategy: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    contexts: dict[tuple[str, str], _SymbolContext],
) -> dict[str, Any]:
    from . import drift as drift_control

    per_symbol: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for symbol in spec["symbols"]:
        frame = frames[symbol]
        key = (symbol, dsl.strategy_hash(
            {**strategy, "instrument": symbol, "timeframe": spec["timeframe"]}
        ))
        leg_trades, _daily, full, context, _costs = _run_leg(
            spec, symbol, strategy, frame, segment="is", context=contexts.get(key)
        )
        contexts[key] = context
        model = dsl.Strategy.model_validate(
            {**strategy, "instrument": symbol, "timeframe": spec["timeframe"]}
        )
        try:
            info = drift_control.evaluate(
                frame,
                specs.exit_spec_from_strategy(model),
                context.limits,
                full,
                cost=context.book,
                prepared=context.prepared,
                campaign_id=str(campaign["id"]),
                simulations=int(
                    (
                        (campaign.get("config") or {}).get("controls") or {}
                    ).get("test_vs_random_direction", {}).get("simulations", 1000)
                ),
                percentile_min=float(
                    (
                        (campaign.get("config") or {}).get("controls") or {}
                    ).get("test_vs_random_direction", {}).get("percentile_min", 90)
                ),
                approved=True,
                return_means=True,
            )
        except Exception as exc:  # noqa: BLE001 - el control no tumba la campaña
            info = {
                "percentile": None,
                "simulations": 0,
                "percentile_min": 90.0,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        random_means = info.pop("random_means", [])
        per_symbol.append(
            {
                "symbol": symbol,
                "random_means": random_means,
                "trades": len(leg_trades),
                "strategy_expectancy_r": info.get("strategy_expectancy_r"),
            }
        )
        summary[symbol] = {
            key_name: value
            for key_name, value in info.items()
            if key_name
            in {
                "percentile",
                "passed",
                "trades",
                "strategy_expectancy_r",
                "random_expectancy_mean_r",
                "random_percentile_90_r",
                "mean_bars",
                "error",
            }
        }
    result = basket_percentile(
        per_symbol,
        percentile_min=float(
            (
                (campaign.get("config") or {}).get("controls") or {}
            ).get("test_vs_random_direction", {}).get("percentile_min", 90)
        ),
        campaign_id=str(campaign["id"]),
        approved=True,
    )
    result["per_symbol"] = summary
    return result


def _evaluate_combo(
    campaign: dict[str, Any],
    spec: dict[str, Any],
    strategy: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    *,
    segment: str,
    contexts: dict[tuple[str, str], _SymbolContext],
    with_drift: bool,
) -> dict[str, Any]:
    trades: list[fastbt.Trade] = []
    daily: dict[str, pd.Series] = {}
    account_values: dict[str, list[float]] = {}
    for symbol in spec["symbols"]:
        frame = frames[symbol]
        if len(frame) < 100:
            raise BasketError(f"{symbol}: menos de 100 barras {segment}")
        key = (symbol, dsl.strategy_hash(
            {**strategy, "instrument": symbol, "timeframe": spec["timeframe"]}
        ))
        leg_trades, leg_daily, _full, context, leg_costs = _run_leg(
            spec, symbol, strategy, frame, segment=segment,
            context=contexts.get(key),
        )
        contexts[key] = context
        trades.extend(leg_trades)
        daily[symbol] = leg_daily
        for account, values in leg_costs.items():
            account_values.setdefault(account, []).extend(values)
    combined = combine_daily(daily)
    payload, fold_rows, cost_r = _basket_metrics(
        trades,
        combined,
        frames,
        strategy,
        spec,
        segment=segment,
        account_values=account_values,
    )
    base_model = dsl.Strategy.model_validate(
        {
            **strategy,
            "instrument": spec["symbols"][0],
            "timeframe": spec["timeframe"],
        }
    )
    payload["strategy_hash"] = dsl.strategy_hash(base_model)
    drift_info: dict[str, Any] | None = None
    if with_drift:
        drift_info = _drift_basket(campaign, spec, strategy, frames, contexts)
        payload["metrics"]["drift"] = drift_info
        payload["drift"] = drift_info
    payload["returns"] = combined.to_numpy(dtype=float).tolist()
    payload["return_dates"] = [stamp.isoformat() for stamp in combined.index]
    return payload


def _store_result(
    campaign_id: str,
    strategy: dict[str, Any],
    payload: dict[str, Any],
    *,
    cost_profile: str,
    db_path: str | Path | None,
) -> int:
    strategy_id = databank.add_strategy(
        campaign_id,
        strategy,
        family="basket",
        generation=0,
        origin="grid",
        status="evaluated",
        db_path=db_path,
    )
    metrics_payload = dict(payload["metrics"])
    metrics_payload["return_dates"] = payload["return_dates"]
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile=cost_profile,
        metrics=metrics_payload,
        trades_count=int(payload["trades_count"]),
        returns=payload["daily_returns"],
        db_path=db_path,
    )
    return strategy_id


def run_campaign(
    campaign_id: str,
    *,
    workers: int | None = None,
    time_limit: float | None = None,
    db_path: str | Path | None = None,
    frames: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """Ejecuta una campaña de cesta aprobada. Nunca lee OOS-2."""

    from .guard import require_approved_campaign

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise campaigns.CampaignError(f"campaña no registrada: {campaign_id}")
    require_approved_campaign(campaign, action="run_campaign")
    status = str(campaign["status"])
    if status != "registered":
        raise campaigns.CampaignError(
            f"la campaña debe estar registered (está {status})"
        )
    if not campaign.get("approved_at"):
        raise campaigns.CampaignError(
            "la campaña no está aprobada con --approved-by-operator"
        )
    spec = _campaign_spec(campaign)
    strategies = _strategies(spec)
    total_budget = int(campaign.get("n_total") or 0)
    if total_budget <= 0:
        raise campaigns.CampaignError("Sin datos: n_total no válido")
    if len(strategies) != total_budget:
        raise campaigns.CampaignError(
            f"preflight: grid tiene {len(strategies)} combinaciones; "
            f"n_total congelado es {total_budget}"
        )
    is_frames = _segment_frames(
        campaign, "is", frames=frames, db_path=db_path
    )
    config = load_engine_config()
    validation = config.validation.for_timeframe(spec["timeframe"])
    folds = int(validation.folds)
    databank.set_campaign_status(campaign_id, "running", db_path=db_path)
    started = time.monotonic()
    if time_limit is not None:
        # El límite se respeta entre combinaciones; la rejilla es pequeña.
        pass
    contexts: dict[tuple[str, str], _SymbolContext] = {}
    cost_profile = f"basket:{'+'.join(spec['symbols'])}"
    items: list[Any] = []
    errors: list[str] = []
    from . import engine as engine_module

    try:
        for strategy in strategies:
            if (
                time_limit is not None
                and time.monotonic() - started >= float(time_limit) * 60.0
            ):
                break
            try:
                payload = _evaluate_combo(
                    campaign,
                    spec,
                    strategy,
                    is_frames,
                    segment="is",
                    contexts=contexts,
                    with_drift=True,
                )
                strategy_id = _store_result(
                    campaign_id,
                    strategy,
                    payload,
                    cost_profile=cost_profile,
                    db_path=db_path,
                )
            except Exception as exc:  # noqa: BLE001 - una combinación no tumba la cesta
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            item = engine_module.Individual(
                strategy=strategy,
                strategy_hash=str(payload.get("strategy_hash") or dsl.strategy_hash(strategy)),
                generation=0,
                operator="grid",
                origin="grid",
                parents=(None, None),
                strategy_id=strategy_id,
                fitness=list(payload["fitness"]),
                feasible=bool(payload["feasible"]),
                violations=list(payload["violations"]),
                folds=list(payload["folds"]),
                metrics=dict(payload["metrics"]),
                daily_returns=payload["daily_returns"],
                trades=int(payload["trades_count"]),
                cost_r=payload["cost_r"],
                complexity=int(payload["complexity"]),
            )
            items.append(item)
            databank.add_lineage(
                strategy_id,
                parent_a=None,
                parent_b=None,
                operator="grid",
                param_diff={},
                generation=0,
                fitness={
                    "vector": item.fitness,
                    "raw": item.metrics.get("raw"),
                    "folds": item.folds,
                },
                rank=-1,
                crowding=0.0,
                reason="evaluado",
                db_path=db_path,
            )
    except Exception as exc:
        if databank.count_strategies(campaign_id, db_path=db_path) == 0:
            databank.set_campaign_status(
                campaign_id,
                "registered",
                reason=f"{type(exc).__name__}: {exc}",
                db_path=db_path,
            )
        raise
    if not items:
        detail = "; ".join(dict.fromkeys(errors[:3])) or "sin candidatos"
        databank.set_campaign_status(
            campaign_id,
            "registered",
            reason=f"Sin datos: cesta sin combinaciones evaluadas: {detail}",
            db_path=db_path,
        )
        raise campaigns.CampaignError(
            f"Sin datos: cesta sin combinaciones evaluadas ({len(errors)} rechazadas): {detail}"
        )
    engine_module._assign_ranks(items)  # noqa: SLF001
    engine_module._niche(items, float(config.validation.corr_cluster))  # noqa: SLF001
    databank.reset_lineage_final(campaign_id, db_path=db_path)
    for item in items:
        if item.strategy_id is not None:
            databank.set_lineage_rank(
                item.strategy_id,
                item.rank,
                item.crowding,
                final=True,
                db_path=db_path,
            )
    feasible_count = sum(1 for item in items if item.feasible)
    candidates, discarded = engine_module._rank1_candidates(items, folds)  # noqa: SLF001
    campaigns.mark_done(campaign_id, db_path=db_path)
    oos1: dict[int, dict[str, Any]] = {}
    selected: list[Any] = []
    fold_discarded = list(discarded)
    if candidates:
        oos1_frames = _segment_frames(
            campaign, "oos1", frames=frames, db_path=db_path
        )
        oos_contexts: dict[tuple[str, str], _SymbolContext] = {}
        for item in candidates:
            try:
                payload = _evaluate_combo(
                    campaign,
                    spec,
                    item.strategy,
                    oos1_frames,
                    segment="oos1",
                    contexts=oos_contexts,
                    with_drift=False,
                )
            except Exception as exc:  # noqa: BLE001
                oos1[id(item)] = {
                    "error": f"{type(exc).__name__}: {exc}",
                    "metrics": None,
                    "returns": [],
                    "return_dates": [],
                }
                continue
            oos1[id(item)] = {
                "error": None,
                "metrics": payload["metrics"]["is"],
                "returns": payload["returns"],
                "return_dates": payload["return_dates"],
            }
            databank.add_evaluation(
                item.strategy_id,
                segment="oos1",
                cost_profile=cost_profile,
                metrics={
                    **payload["metrics"]["is"],
                    "return_dates": payload["return_dates"],
                },
                trades_count=int(payload["trades_count"]),
                returns=payload["daily_returns"],
                db_path=db_path,
            )
        selected, rejected = engine_module._select_finalists(  # noqa: SLF001
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
            metrics_is = result.get("metrics") or {}
            reason = (
                f"finalista: OOS-1 expectativa "
                f"{metrics_is.get('expectancy_r')} PF {metrics_is.get('profit_factor')}"
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
        [item.daily_returns for item in items],
        threshold=float(config.validation.corr_cluster),
    )
    databank.set_campaign_counts(
        campaign_id,
        n_evaluated=len(items),
        n_effective=int(n_effective),
        n_finalists=len(selected),
        db_path=db_path,
    )
    finalist_rows = []
    for item in selected:
        result = oos1.get(id(item)) or {}
        metrics_is = result.get("metrics") or {}
        finalist_rows.append(
            {
                "strategy_id": item.strategy_id,
                "strategy_hash": item.strategy_hash,
                "oos1_expectancy_r": metrics_is.get("expectancy_r"),
                "oos1_profit_factor": metrics_is.get("profit_factor"),
                "is_expectancy_r": (item.metrics.get("is") or {}).get("expectancy_r"),
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
    from .engine import _spearman  # noqa: PLC0415

    spearman_pairs = []
    for item in candidates:
        result = oos1.get(id(item)) or {}
        value = (result.get("metrics") or {}).get("expectancy_r")
        if value is not None and not result.get("error"):
            spearman_pairs.append((float(item.fitness[0]), float(value)))
    spearman_value = _spearman(spearman_pairs)
    frontier_items = [item for item in items if item.rank == 0 and item.feasible]
    frontier_fitness = (
        np.mean([item.fitness for item in frontier_items], axis=0).tolist()
        if frontier_items
        else None
    )
    return {
        "campaign_id": campaign_id,
        "synthetic": False,
        "n_total": total_budget,
        "n_evaluated": len(items),
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
        "seed": int(spec["seed"]),
        "errors": errors,
        "diagnostics": {
            "mode": "basket",
            "symbols": list(spec["symbols"]),
            "grid": len(strategies),
            "evaluated": len(items),
            "evaluation_errors": len(errors),
            "stop_reason": "time_limit" if len(items) < len(strategies) else "grid",
        },
    }


__all__ = [
    "BasketError",
    "basket_percentile",
    "check_campaign",
    "check_spec",
    "combine_daily",
    "is_basket_campaign",
    "is_basket_spec",
    "load",
    "preflight",
    "preflight_campaign",
    "register",
    "run_campaign",
    "segment_frames",
]
