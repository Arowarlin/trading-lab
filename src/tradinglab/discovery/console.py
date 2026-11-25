"""Payloads de solo lectura para la consola Discovery Lab.

Todo se lee con conexiones SQLite ``mode=ro``. No se llama a ``read_holdout``,
no se exponen métricas OOS-2, no se escribe en ``disc_*`` ni se registran
pruebas. La consola es una vista del databank, no un ejecutor.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..config import ROOT
from ..trials import budget_config
from . import campaigns, dsl, edge_map

DISCOVERY_STATES = edge_map.STATES
_HIDDEN_TESTS = {"oos2", "dsr_confirm", "test_vs_random_oos2"}
_SERIES_KEYS = {"returns", "return_dates", "equity_curve"}


def _ro(path: str | Path) -> sqlite3.Connection | None:
    target = Path(path)
    if not target.exists():
        return None
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _table(con: sqlite3.Connection, name: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(name),),
        ).fetchone()
        is not None
    )


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "null")
    except (TypeError, ValueError):
        return default


def _strip_series(value: Any) -> Any:
    """Quita series largas (retornos/fechas) de los payloads de la consola."""

    if isinstance(value, dict):
        return {
            key: _strip_series(item)
            for key, item in value.items()
            if key not in _SERIES_KEYS
        }
    if isinstance(value, list):
        return [_strip_series(item) for item in value]
    return value


def _scrub_oos2(value: Any) -> Any:
    """Elimina cualquier clave de configuración OOS-2 de los payloads."""

    if isinstance(value, dict):
        return {
            key: _scrub_oos2(item)
            for key, item in value.items()
            if "oos2" not in str(key).lower()
        }
    if isinstance(value, list):
        return [_scrub_oos2(item) for item in value]
    return value


def count_tests_readonly(
    lab_db: str | Path,
    discovery_db: str | Path | None = None,
) -> dict[str, int]:
    """Mismo contador que `learning.count_tests` sin abrir la base en escritura."""

    breakdown = {
        "lessons": 0,
        "optimization_trials": 0,
        "holdout_reads": 0,
        "strategy_trials": 0,
        "incubated": 0,
        "campaign_registry": 0,
        "discovery": 0,
    }
    con = _ro(lab_db)
    if con is not None:
        try:
            for key, table, where in (
                ("lessons", "lesson_tests", ""),
                ("optimization_trials", "optimization_trials", ""),
                ("holdout_reads", "holdout_reads", ""),
                (
                    "strategy_trials",
                    "strategy_trials",
                    " WHERE counted = 1",
                ),
                (
                    "incubated",
                    "lifecycle_bots",
                    " WHERE frozen_at IS NOT NULL",
                ),
            ):
                if _table(con, table):
                    row = con.execute(f"SELECT COUNT(*) AS n FROM {table}{where}").fetchone()
                    breakdown[key] = int(row["n"] or 0)
            if _table(con, "campaign_registry"):
                row = con.execute(
                    "SELECT COALESCE(SUM(n_total), 0) AS n FROM campaign_registry"
                ).fetchone()
                breakdown["campaign_registry"] = int(row["n"] or 0)
        finally:
            con.close()
    if discovery_db:
        try:
            breakdown["discovery"] = int(
                campaigns.discovery_tests(discovery_db).get("total") or 0
            )
        except Exception:  # noqa: BLE001
            breakdown["discovery"] = 0
    breakdown["total"] = sum(breakdown.values())
    return breakdown


def _week_bounds(now: datetime | None = None) -> tuple[str, str]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    iso = moment.isocalendar()
    start = datetime.fromisocalendar(int(iso.year), int(iso.week), 1).date()
    end = start.fromordinal(start.toordinal() + 7)
    return start.isoformat(), end.isoformat()


def budget_readonly(
    lab_db: str | Path,
    symbols: list[str],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    config = budget_config()
    start, end = _week_bounds(now)
    result = []
    con = _ro(lab_db)
    try:
        for symbol in sorted({str(item).upper() for item in symbols if str(item).strip()}):
            limit = int(config["assets"].get(symbol, config["default"]))
            used = 0
            if con is not None and _table(con, "strategy_trials"):
                row = con.execute(
                    "SELECT COUNT(DISTINCT run_id) AS n FROM strategy_trials"
                    " WHERE symbol = ? AND ts >= ? AND ts < ?"
                    " AND run_id IS NOT NULL",
                    (symbol, start, end),
                ).fetchone()
                used = int(row["n"] or 0)
            result.append(
                {
                    "symbol": symbol,
                    "week": f"{start}/{end}",
                    "limit": limit,
                    "used": used,
                    "remaining": max(0, limit - used),
                    "exceeded": used >= limit,
                }
            )
    finally:
        if con is not None:
            con.close()
    return result


def _campaign_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = []
    for row in con.execute(
        "SELECT * FROM disc_campaigns ORDER BY created_at DESC, id DESC"
    ):
        data = dict(row)
        config = _json(data.pop("config_json", "{}"), {})
        quality = _json(data.pop("quality_json", "{}"), {})
        data["config"] = _scrub_oos2(config)
        data["quality"] = quality
        data["data_source"] = str(config.get("data_source") or "broker")
        data["mode"] = str(config.get("mode") or "ga")
        data["cost_mode"] = str((config.get("cost") or {}).get("mode") or "legacy")
        rows.append(_scrub_oos2(data))
    return rows


def _metrics(con: sqlite3.Connection, strategy_id: int) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in con.execute(
            "SELECT segment, cost_profile, metrics_json, trades_count, computed_at"
            " FROM disc_evaluations WHERE strategy_id = ?"
            " AND segment != 'oos2' ORDER BY id",
            (int(strategy_id),),
        )
    ]
    for row in rows:
        row["metrics"] = _strip_series(_json(row.pop("metrics_json", "{}"), {}))
    return {"rows": rows}


def _validations(con: sqlite3.Connection, strategy_id: int) -> dict[str, Any]:
    result = {}
    for row in con.execute(
        "SELECT test, result_json, passed, computed_at FROM disc_validations"
        " WHERE strategy_id = ? ORDER BY id",
        (int(strategy_id),),
    ):
        test = str(row["test"])
        if test in _HIDDEN_TESTS:
            continue
        result[test] = {
            "result": _strip_series(_json(row["result_json"], {})),
            "passed": None if row["passed"] is None else bool(row["passed"]),
            "computed_at": row["computed_at"],
        }
    return result


def _costs_by_account(instrument: str) -> list[dict[str, Any]]:
    """Perfil de coste configurado por cuenta real (sin calcular nada nuevo)."""

    try:
        from ..propfund.costs import load_profile
        from ..propfund.models import ConnectionState, Market
        from ..propfund.registry import load_registry
    except Exception:  # noqa: BLE001
        return []
    try:
        registry = load_registry()
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for account in registry.accounts.values():
        if account.template or account.market is not Market.CFD:
            continue
        profile = load_profile(account.id, instrument, firm=account.firm)
        rows.append(
            {
                "account": account.id,
                "firm": account.firm,
                "connection_state": str(account.connection_state),
                "connected": account.connection_state is not ConnectionState.DISCONNECTED,
                "spread_price": profile.spread_price,
                "spread_p75_price": profile.spread_p75_price,
                "commission_type": profile.commission_type,
                "commission_value": profile.commission_value,
                "slippage_price": profile.slippage_price,
                "swap_long": profile.swap_long,
                "swap_short": profile.swap_short,
                "swap_long_per_lot": profile.swap_long_per_lot,
                "swap_short_per_lot": profile.swap_short_per_lot,
                "swap_mode": profile.swap_mode,
                "swap_rollover3days": profile.swap_rollover3days,
                "swap_source": profile.swap_source or "Sin datos",
                "source": profile.source or "Sin datos",
                "verified": profile.verified,
            }
        )
    return rows


def _verdict_chip(verdict: Any, validations: Mapping[str, Any]) -> str:
    """Etiqueta de presentación a partir de PBO/WF/estrés ya guardados."""

    stored = str(verdict or "").strip().upper()
    if stored in {"ROBUSTA", "MODERADA", "FRÁGIL", "SOBREAJUSTADA"}:
        return stored
    pbo = (validations.get("pbo") or {}).get("result") or {}
    wf = (validations.get("wf") or {}).get("result") or {}
    pbo_value = pbo.get("pbo")
    if pbo_value is not None and float(pbo_value) > 0.5:
        return "SOBREAJUSTADA"
    if wf.get("ok") is False:
        return "FRÁGIL"
    stress = (validations.get("retest") or {}).get("result") or {}
    perturb_failed = any(
        (validations.get(name) or {}).get("result", {}).get("passed") is False
        for name in ("perturb_noise", "perturb_delay", "perturb_execution")
    )
    if stress.get("stress_cost_x1_5_ok") is False or perturb_failed:
        return "FRÁGIL"
    if pbo_value is None or wf.get("ok") is None:
        return "Sin datos"
    return "ROBUSTA" if float(pbo_value) <= 0.25 else "MODERADA"


def _strategy_payload(con: sqlite3.Connection, strategy_id: int) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT * FROM disc_strategies WHERE id = ?", (int(strategy_id),)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["dsl"] = _json(data.pop("dsl_json", "{}"), {})
    model = None
    errors: list[str] = []
    try:
        model = dsl.Strategy.model_validate(data["dsl"])
        errors = dsl.validate(model)
    except Exception as exc:  # noqa: BLE001
        errors = [f"{type(exc).__name__}: {exc}"]
    metrics = _metrics(con, int(strategy_id))
    validations = _validations(con, int(strategy_id))
    by_segment = {str(item["segment"]): item for item in metrics["rows"]}
    challenge = (validations.get("challenge") or {}).get("result") or {}
    return {
        "strategy": {
            "id": int(data["id"]),
            "campaign_id": data["campaign_id"],
            "strategy_hash": data["strategy_hash"],
            "family": data["family"],
            "instrument": data["instrument"],
            "timeframe": data["timeframe"],
            "generation": int(data["generation"] or 0),
            "origin": data["origin"],
            "level": int(data["level"] or 1),
            "status": data["status"],
            "verdict": data["verdict"],
            "verdict_chip": _verdict_chip(data["verdict"], validations),
            "selection_reason": data["selection_reason"],
            "reject_reason": data["reject_reason"],
            "created_at": data["created_at"],
        },
        "rules": rule_lines(model) if model is not None else [],
        "rule_dsl": data["dsl"],
        "validation_errors": errors,
        "metrics": {
            **metrics,
            "is": (by_segment.get("fitness_is") or {}).get("metrics"),
            "is_full": (by_segment.get("is_full") or {}).get("metrics"),
            "oos1": (by_segment.get("oos1") or {}).get("metrics"),
        },
        "validations": validations,
        "cost_stress": (validations.get("retest") or {}).get("result"),
        "perturbations": {
            name: (validations.get(name) or {}).get("result")
            for name in ("perturb_noise", "perturb_delay", "perturb_execution")
        },
        "pbo": (validations.get("pbo") or {}).get("result"),
        "wf": (validations.get("wf") or {}).get("result"),
        "plateau": (validations.get("optimizer_plateau") or {}).get("result"),
        "hour_weekday": (validations.get("hour_weekday") or {}).get("result"),
        "streaks": (validations.get("streaks") or {}).get("result"),
        "challenge_accounts": challenge.get("accounts") or {},
        "costs_by_account": _costs_by_account(str(data["instrument"] or "")),
        "read_only": True,
    }


def _campaign_payload(con: sqlite3.Connection, campaign_id: str) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT * FROM disc_campaigns WHERE id = ?", (str(campaign_id),)
    ).fetchone()
    if row is None:
        return None
    campaign = dict(row)
    campaign["config"] = _scrub_oos2(_json(campaign.pop("config_json", "{}"), {}))
    campaign["quality"] = _json(campaign.pop("quality_json", "{}"), {})
    campaign = _scrub_oos2(campaign)
    is_metrics: dict[int, dict[str, Any]] = {}
    for row in con.execute(
        "SELECT e.strategy_id, e.metrics_json, e.trades_count"
        " FROM disc_evaluations e JOIN disc_strategies s ON s.id = e.strategy_id"
        " WHERE s.campaign_id = ? AND e.segment = 'fitness_is'",
        (str(campaign_id),),
    ):
        metrics = _strip_series(_json(row["metrics_json"], {}))
        is_metrics[int(row["strategy_id"])] = {
            "expectancy_r": (metrics.get("is") or {}).get("expectancy_r"),
            "trades": row["trades_count"],
        }
    strategies = []
    for item in con.execute(
        "SELECT id, strategy_hash, family, instrument, timeframe, generation, origin,"
        " level, status, verdict, selection_reason FROM disc_strategies"
        " WHERE campaign_id = ? ORDER BY generation, id",
        (str(campaign_id),),
    ):
        data = dict(item)
        is_row = is_metrics.get(int(data["id"])) or {}
        data["is_expectancy_r"] = is_row.get("expectancy_r")
        data["trades_is"] = is_row.get("trades")
        strategies.append(data)
    lineage = [
        dict(row)
        for row in con.execute(
            "SELECT l.* FROM disc_lineage l JOIN disc_strategies s"
            " ON s.id = l.strategy_id WHERE s.campaign_id = ? ORDER BY l.id",
            (str(campaign_id),),
        )
    ]
    for row in lineage:
        row["param_diff"] = _json(row.pop("param_diff_json", "{}"), {})
        row["fitness"] = _strip_series(_json(row.pop("fitness_json", "{}"), {}))
    final = {}
    for row in lineage:
        if row.get("final"):
            final[int(row["strategy_id"])] = row
    frontier = []
    frontier_ids = set()
    for strategy in strategies:
        row = final.get(int(strategy["id"]))
        if row is None or row.get("rank") is None or int(row["rank"]) != 0:
            continue
        frontier_ids.add(int(strategy["id"]))
        frontier.append(
            {
                **strategy,
                "rank": row.get("rank"),
                "crowding": row.get("crowding"),
            }
        )
    generations: dict[int, list[dict[str, Any]]] = {}
    for strategy in strategies:
        generations.setdefault(int(strategy["generation"] or 0), []).append(strategy)
    generation_rows = []
    for generation, items in sorted(generations.items()):
        values = [
            float(item["is_expectancy_r"])
            for item in items
            if item.get("is_expectancy_r") is not None
        ]
        generation_rows.append(
            {
                "generation": generation,
                "strategies": len(items),
                "best_is_expectancy_r": max(values) if values else None,
                "frontier": sum(1 for item in items if int(item["id"]) in frontier_ids),
            }
        )
    status_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    origin_counts: dict[str, int] = {}
    for strategy in strategies:
        status_counts[str(strategy["status"])] = status_counts.get(str(strategy["status"]), 0) + 1
        level_counts[str(strategy["level"])] = level_counts.get(str(strategy["level"]), 0) + 1
        origin_counts[str(strategy["origin"])] = origin_counts.get(str(strategy["origin"]), 0) + 1
    return {
        "campaign": campaign,
        "strategies": strategies,
        "costs_by_account": _costs_by_account(str(campaign.get("instrument") or "")),
        "frontier": frontier,
        "generations": generation_rows,
        "lineage": lineage[-500:],
        "diagnostics": {
            "status_counts": status_counts,
            "level_counts": level_counts,
            "origin_counts": origin_counts,
            "n_strategies": len(strategies),
            "n_frontier": len(frontier),
            "n_finalists": int(campaign.get("n_finalists") or 0),
            "last_error": campaign.get("last_error"),
            "reject_reason": campaign.get("reject_reason"),
        },
    }


def summary(
    discovery_db: str | Path,
    lab_db: str | Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    con = _ro(discovery_db)
    campaigns_rows = _campaign_rows(con) if con is not None else []
    if con is not None:
        con.close()
    status_counts: dict[str, int] = {}
    for row in campaigns_rows:
        key = str(row.get("status") or "Sin datos")
        status_counts[key] = status_counts.get(key, 0) + 1
    symbols = sorted(
        {
            str(row.get("instrument") or "").upper()
            for row in campaigns_rows
            if row.get("instrument")
        }
    )
    campaigns_total = sum(int(row.get("n_total") or 0) for row in campaigns_rows)
    campaigns_evaluated = sum(int(row.get("n_evaluated") or 0) for row in campaigns_rows)
    campaigns_effective = sum(int(row.get("n_effective") or 0) for row in campaigns_rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count_tests": count_tests_readonly(lab_db, discovery_db),
        "campaigns": {
            "total": len(campaigns_rows),
            "by_status": status_counts,
            "n_total": campaigns_total,
            "n_evaluated": campaigns_evaluated,
            "n_effective": campaigns_effective,
            "n_finalists": sum(int(row.get("n_finalists") or 0) for row in campaigns_rows),
        },
        "budget": budget_readonly(lab_db, symbols, now=now),
        "campaigns_detail": campaigns_rows,
        "read_only": True,
    }


def campaigns_payload(discovery_db: str | Path) -> dict[str, Any]:
    con = _ro(discovery_db)
    try:
        if con is None:
            rows: list[dict[str, Any]] = []
            strategies: list[dict[str, Any]] = []
        else:
            rows = _campaign_rows(con)
            strategies = [
                dict(row)
                for row in con.execute(
                    "SELECT id, campaign_id, family, instrument, timeframe, generation,"
                    " origin, level, status, verdict FROM disc_strategies"
                    " WHERE level >= 2 ORDER BY level DESC, id"
                )
            ]
    finally:
        if con is not None:
            con.close()
    return {
        "campaigns": rows,
        "strategies": strategies,
        "n": len(rows),
        "status": "ok" if rows else "Sin datos",
    }


def campaign_detail(discovery_db: str | Path, campaign_id: str) -> dict[str, Any] | None:
    con = _ro(discovery_db)
    if con is None:
        return None
    try:
        return _campaign_payload(con, campaign_id)
    finally:
        con.close()


def strategy_detail(discovery_db: str | Path, strategy_id: int) -> dict[str, Any] | None:
    con = _ro(discovery_db)
    if con is None:
        return None
    try:
        return _strategy_payload(con, strategy_id)
    finally:
        con.close()


def edge_map_payload(
    discovery_db: str | Path,
    costs_db: str | Path,
    *,
    data_root: str | Path = ROOT,
    by: str = "hipotesis",
    account: str | None = None,
) -> dict[str, Any]:
    report = edge_map.build(
        discovery_db,
        costs_db=costs_db,
        data_root=data_root,
        account=account,
        allow_dukascopy=False,
    )
    return {
        "report": report,
        "by": edge_map.group_by(report, by),
        "view": by,
        "account": account,
        "read_only": True,
    }


def suggest_payload(
    discovery_db: str | Path,
    costs_db: str | Path,
    *,
    data_root: str | Path = ROOT,
    account: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    return edge_map.suggest(
        account,
        discovery_db=discovery_db,
        costs_db=costs_db,
        data_root=data_root,
        allow_dukascopy=False,
        limit=limit,
    )


# --------------------------------------------------------------------- reglas
_PRICE = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "range": "rango",
    "body": "cuerpo",
}
_OPS = {"gt": ">", "lt": "<", "ge": "≥", "le": "≤"}
_LEVELS = {
    "prev_session_high": "máximo de la sesión anterior",
    "prev_session_low": "mínimo de la sesión anterior",
    "opening_range_high": "máximo del rango de apertura",
    "opening_range_low": "mínimo del rango de apertura",
    "prev_day_high": "máximo del día anterior",
    "prev_day_low": "mínimo del día anterior",
    "donchian_high": "máximo Donchian",
    "donchian_low": "mínimo Donchian",
}


def _fmt_params(params: Mapping[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value is not None}
    if not clean:
        return ""
    return "(" + ", ".join(f"{key}={value}" for key, value in sorted(clean.items())) + ")"


def rule_text(expr: Any) -> str:
    if not isinstance(expr, dict):
        return "Sin datos"
    kind = str(expr.get("kind") or "")
    if kind in {"and", "or"}:
        parts = [rule_text(item) for item in expr.get("args") or []]
        return (" y " if kind == "and" else " o ").join(f"({part})" for part in parts)
    if kind == "not":
        args = expr.get("args") or []
        return f"no ({rule_text(args[0]) if args else 'Sin datos'})"
    if kind == "price":
        return _PRICE.get(str(expr.get("price")), str(expr.get("price")))
    if kind == "const":
        return str(expr.get("value"))
    if kind == "level":
        return _LEVELS.get(str(expr.get("level")), str(expr.get("level")))
    if kind == "indicator":
        name = str(expr.get("ind") or "indicador")
        params = dict(expr.get("params") or {})
        if expr.get("n") is not None:
            params["n"] = expr.get("n")
        if expr.get("lookback") is not None:
            params["lookback"] = expr.get("lookback")
        if expr.get("src"):
            params["src"] = expr.get("src")
        return f"{name}{_fmt_params(params)}"
    if kind in {"pattern", "regime"}:
        name = str(expr.get("pattern") or expr.get("regime") or kind)
        params = dict(expr.get("params") or {})
        if expr.get("n") is not None:
            params["n"] = expr.get("n")
        if expr.get("lookback") is not None:
            params["lookback"] = expr.get("lookback")
        return f"{name}{_fmt_params(params)}"
    if kind in _OPS:
        return f"{rule_text(expr.get('left'))} {_OPS[kind]} {rule_text(expr.get('right'))}"
    if kind == "between":
        return (
            f"{rule_text(expr.get('left'))} entre "
            f"{expr.get('low')} y {expr.get('high')}"
        )
    if kind in {"cross_up", "cross_down"}:
        arrow = "cruza al alza" if kind == "cross_up" else "cruza a la baja"
        return f"{rule_text(expr.get('left'))} {arrow} {rule_text(expr.get('right'))}"
    if kind == "htf":
        return f"en {expr.get('tf')}: {rule_text(expr.get('expr'))}"
    if kind == "time_between":
        return f"entre {expr.get('start')} y {expr.get('end')}"
    if kind == "weekday_in":
        return "días " + ", ".join(str(day) for day in expr.get("days") or [])
    if kind == "held_for":
        args = expr.get("args") or []
        return f"durante {expr.get('n')} velas: {rule_text(args[0]) if args else 'Sin datos'}"
    if kind == "within_bars":
        args = expr.get("args") or []
        return f"en las últimas {expr.get('n')} velas: {rule_text(args[0]) if args else 'Sin datos'}"
    return kind or "Sin datos"


def rule_lines(strategy: Any) -> list[str]:
    try:
        model = (
            strategy
            if isinstance(strategy, dsl.Strategy)
            else dsl.Strategy.model_validate(strategy)
        )
    except Exception:  # noqa: BLE001
        return []
    lines = []
    if model.long_entry is not None:
        lines.append("Largo: " + rule_text(model.long_entry.model_dump(mode="json")))
    if model.short_entry is not None:
        lines.append("Corto: " + rule_text(model.short_entry.model_dump(mode="json")))
    session = model.session
    lines.append(
        f"Sesión: {session.start}-{session.end} · flat {session.flat_at}"
    )
    lines.append(
        f"Límites: máximo {model.limits.max_trades_per_day} operaciones/día"
    )
    return lines


__all__ = [
    "budget_readonly",
    "campaign_detail",
    "campaigns_payload",
    "count_tests_readonly",
    "edge_map_payload",
    "rule_lines",
    "rule_text",
    "strategy_detail",
    "suggest_payload",
    "summary",
]
