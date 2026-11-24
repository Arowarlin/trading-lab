"""Cesta multi-símbolo mínima (Q3): una hipótesis, varios símbolos.

No crea campañas ni escribe en ``disc_*``. Agrega R por fecha, aplica coste y
swap por símbolo/cuenta y calcula pliegues globales. El `run` de campañas de
cesta queda pendiente de cablear en el motor; preflight/feasibility sí están
disponibles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ..propfund.registry import load_registry
from . import (
    campaigns,
    compiler,
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
from .costs import build_cost_book_for_setup
from .data_sources import normalize_source
from .timeframes import normalize_timeframe, timeframe_minutes


class BasketError(ValueError):
    pass


def is_basket_spec(path: str | Path) -> bool:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return bool(data.get("basket"))


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
        "mode": mode,
        "data_source": normalize_source(str(data.get("data_source") or "dukascopy")),
        "segments": data.get("segments"),
        "seed": int(data.get("seed", 0)),
        "grid": grid_spec,
        "cost": cost_map,
        "strategies": base,
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


def _setup(spec: dict[str, Any], symbol: str, strategy: dict[str, Any]) -> jobs.QueueSetup:
    cost = spec["cost"][symbol]
    model = dsl.Strategy.model_validate(
        {**strategy, "instrument": symbol, "timeframe": spec["timeframe"]}
    )
    config = load_engine_config()
    return jobs.QueueSetup(
        instrument=symbol,
        timeframe=spec["timeframe"],
        start=spec["segments"]["is"][0],
        end=spec["segments"]["is"][1],
        account=cost["account"],
        firm=cost["firm"],
        cost_accounts=tuple(cost["cost_accounts"]),
        cost_mode=cost["cost_mode"],
        cost_model_version=int(spec.get("cost_model_version", 1) or 1),
        spread_model=str(
            spec.get("spread_model")
            or (cost.get("spread_model") if isinstance(cost, dict) else None)
            or "p75_static"
        ),
        session_tz=config.data_quality.tz_for(symbol),
        session_start=model.session.start,
        session_end=model.session.end,
        flat_at=model.session.flat_at,
        weekdays=(0, 1, 2, 3, 4),
        data_source=spec["data_source"],
    ).validated()


def _bars(spec: dict[str, Any], symbol: str) -> pd.DataFrame:
    frame = campaigns._source_frame(symbol, spec["timeframe"], spec["data_source"])
    frame = snapshots.closed_bars(frame, spec["timeframe"])
    start = pd.Timestamp(spec["segments"]["is"][0], tz="UTC")
    end = pd.Timestamp(spec["segments"]["is"][1], tz="UTC")
    return frame[(frame.index >= start) & (frame.index <= end)]


def _run_combo(
    spec: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    config = load_engine_config()
    validation = config.validation.for_timeframe(spec["timeframe"])
    trades: list[fastbt.Trade] = []
    daily: dict[str, pd.Series] = {}
    for symbol in spec["symbols"]:
        base = _setup(spec, symbol, strategy)
        frame = _bars(spec, symbol)
        if len(frame) < 100:
            raise BasketError(f"{symbol}: menos de 100 barras IS")
        book = build_cost_book_for_setup(base)
        model = dsl.Strategy.model_validate(
            {**strategy, "instrument": symbol, "timeframe": spec["timeframe"]}
        )
        signals = compiler.compile(model, frame)
        limits = specs.run_limits_from_strategy(model, base, close_at_end=True)
        prepared = fastbt.prepare(
            frame,
            book,
            atr_windows=(model.exit.stop.n, 14),
            sessions=(limits,),
        )
        full = fastbt.run(
            signals,
            frame,
            specs.exit_spec_from_strategy(model),
            book,
            limits,
            prepared=prepared,
            collect_metrics=False,
        )
        applied = book.apply(
            full.trades,
            session_tz=limits.session_tz,
            point=base.point,
        )
        trades.extend(applied.trades)
        daily[symbol] = applied.daily_r
    combined = combine_daily(daily)
    folds = int(validation.folds)
    fold_trades: list[int] = []
    for start, end in fitness.fold_bounds(len(combined), folds):
        dates = set(combined.index[start : end + 1].date)
        selected = [
            trade
            for trade in trades
            if trade.exit_time.tz_convert("UTC").date() in dates
        ]
        fold_trades.append(len(selected))
    mean_bars = (
        float(np.mean([trade.bars_held for trade in trades])) if trades else 0.0
    )
    costs = [
        float(trade.r_cost)
        for trade in trades
        if trade.r_cost is not None and np.isfinite(float(trade.r_cost))
    ]
    cost_r = float(np.median(costs)) if costs else None
    reasons: list[str] = []
    if len(trades) < int(validation.min_trades_is):
        reasons.append(f"trades IS {len(trades)} < {validation.min_trades_is}")
    for index, count in enumerate(fold_trades, 1):
        if count < int(validation.min_trades_fold):
            reasons.append(
                f"pliegue {index} trades {count} < {validation.min_trades_fold}"
            )
    if cost_r is None:
        reasons.append("coste_R Sin datos")
    elif cost_r > float(config.fitness.cost_r_max):
        reasons.append(f"coste_R {cost_r:.4f} > {config.fitness.cost_r_max:.4f}")
    max_bars = fitness.max_holding_bars(
        dsl.Strategy.model_validate(
            {**strategy, "instrument": spec["symbols"][0], "timeframe": spec["timeframe"]}
        )
    )
    if mean_bars > max_bars:
        reasons.append(f"tiempo medio {mean_bars:.1f} velas > {max_bars:.0f}")
    return {
        "trades_is": len(trades),
        "fold_trades": fold_trades,
        "cost_r": cost_r,
        "mean_bars": mean_bars,
        "mean_minutes": mean_bars * timeframe_minutes(spec["timeframe"]),
        "feasible": not reasons,
        "reasons": reasons,
    }


def preflight(path: str | Path) -> dict[str, Any]:
    spec = load(path)
    return {
        "campaign_id": spec["campaign_id"],
        "status": "draft",
        "instrument": "BASKET",
        "timeframe": spec["timeframe"],
        "template": spec["template"],
        "mode": spec["mode"],
        "seed": spec["seed"],
        "population": len(spec["strategies"]),
        "generated": len(spec["strategies"]),
        "valid": len(spec["strategies"]),
        "rejected": 0,
        "duplicates": 0,
        "reasons": {},
        "last_error": None,
    }


def check_spec(path: str | Path) -> dict[str, Any]:
    spec = load(path)
    rows: list[dict[str, Any]] = []
    for index, strategy in enumerate(spec["strategies"]):
        try:
            result = _run_combo(spec, strategy)
            reasons = result["reasons"]
            row = {
                "index": index,
                "strategy_hash": dsl.strategy_hash(strategy),
                "label": " ".join(
                    f"{name}={value}"
                    for name, value in (
                        ("fast_n", strategy["long_entry"]["left"].get("n")),
                        ("slow_n", strategy["long_entry"]["right"].get("n")),
                        ("stop", strategy["exit"]["stop"].get("mult")),
                    )
                ),
                "trades_is": result["trades_is"],
                "fold_trades": result["fold_trades"],
                "cost_r": result["cost_r"],
                "mean_bars": result["mean_bars"],
                "mean_minutes": result["mean_minutes"],
                "feasible": result["feasible"],
                "reasons": reasons,
                "cost_by_account": None,
                "cost_viable_by_account": None,
                "worst_account": None,
                "worst_share": None,
                "best_account": None,
                "selected_account": None,
                "selected_share": None,
            }
        except Exception as exc:  # noqa: BLE001
            row = {
                "index": index,
                "strategy_hash": dsl.strategy_hash(strategy),
                "label": "cesta",
                "trades_is": 0,
                "fold_trades": [],
                "cost_r": None,
                "mean_bars": 0.0,
                "mean_minutes": 0.0,
                "feasible": False,
                "reasons": [f"{type(exc).__name__}: {exc}"],
                "cost_by_account": None,
                "cost_viable_by_account": None,
                "worst_account": None,
                "worst_share": None,
                "best_account": None,
                "selected_account": None,
                "selected_share": None,
            }
        rows.append(row)
    feasible = sum(1 for row in rows if row["feasible"])
    pct = 100.0 * feasible / len(rows) if rows else 0.0
    return {
        "campaign_id": spec["campaign_id"],
        "n_checked": len(rows),
        "n_feasible": feasible,
        "feasible_pct": pct,
        "passes": pct >= 50.0,
        "rows": rows,
    }


__all__ = [
    "BasketError",
    "basket_percentile",
    "check_spec",
    "combine_daily",
    "is_basket_spec",
    "load",
    "preflight",
]
