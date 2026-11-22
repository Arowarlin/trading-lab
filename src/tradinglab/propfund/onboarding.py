"""Onboarding de una cuenta Prop Fund (solo lectura, sin campañas).

Genera ``reports/propfund/<ACCOUNT_ID>_onboarding.md`` con:

1. reglas del programa con URL y fecha (lo que falta es ``Sin datos``);
2. símbolos del bróker leídos con ``symbols_get`` y costes de la cuenta
   (spread p75 por hora local NY, comisión citada y slippage asumido);
3. mapa de viabilidad de las plantillas existentes con el coste de ESTA cuenta;
4. restricciones de la firma como reglas comprobables;
5. matriz de las estrategias existentes de nivel >= 3, sin reoptimizar;
6. resumen de coste frente a otras cuentas y combinaciones candidatas.

No ejecuta campañas, no lee OOS-2, no escribe ``disc_*`` y no suma al
``count_tests``. MT5 se usa solo en modo adjunto: no hay login ni shutdown.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

from ..config import ROOT
from .constraints import check_strategy, constraint_rows
from .costs import PROPFUND_COSTS_PATH, load_profile
from .instruments import resolve
from .models import (
    Firm,
    Market,
    Program,
    PropAccount,
    VerificationStatus,
)
from .registry import Registry, load_registry
from .snapshots import _rules_from_account, default_broker_factory

REPORT_DIR = ROOT / "reports" / "propfund"
DEFAULT_COSTS_DB = ROOT / "data" / "lab.db"
DEFAULT_DISCOVERY_DB = ROOT / "data" / "discovery.db"
DEFAULT_CACHE_DIR = ROOT / "data" / "cache" / "mt5"
DEFAULT_AI_TRADER = ROOT / "config" / "ai_trader.yaml"
WEEKDAYS = (0, 1, 2, 3, 4)
RULE_LABELS = {
    "ea_policy": "EAs permitidos",
    "news_trading": "Noticias",
    "weekend_holding": "Fin de semana",
    "overnight_holding": "Overnight",
    "min_trading_days": "Días mínimos",
    "max_daily_loss_pct": "Límite de pérdida diario",
    "max_loss_pct": "Límite de pérdida máximo",
    "profit_target_pct": "Objetivo de beneficio",
    "leverage_forex": "Apalancamiento Forex",
    "leverage_metals": "Apalancamiento metales",
    "leverage_indices": "Apalancamiento índices",
    "leverage_energies": "Apalancamiento energías",
    "leverage_crypto": "Apalancamiento cripto",
    "trial_time_limit_days": "Límite de tiempo",
    "max_lots": "Máximo de lotes",
    "max_trades_per_day": "Máximo de operaciones/día",
}


# --------------------------------------------------------------------------- utilidades


def _utc_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _fmt_value(rule: Any) -> str:
    value = getattr(rule, "value", None)
    key = str(getattr(rule, "key", "") or "")
    if value is None:
        return "Sin datos"
    if isinstance(value, bool):
        return "Permitido" if value else "Prohibido"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if key in {"max_daily_loss_pct", "max_loss_pct", "profit_target_pct"}:
            return f"{float(value):.0%}"
        if key.startswith("leverage_"):
            return f"1:{int(value)}"
        if key in {"max_lots"}:
            return f"{float(value):g}"
        return f"{float(value):g}"
    return str(value)


def _source_of(rules: Iterable[Any]) -> dict[str, Any] | None:
    for rule in rules:
        source = getattr(rule, "source", None)
        if source is None:
            continue
        return {
            "url": source.url,
            "consulted_at": source.consulted_at.isoformat(),
            "kind": source.kind,
        }
    return None


def _verified(rule: Any) -> bool:
    return getattr(rule, "status", None) is VerificationStatus.VERIFIED_OFFICIAL


def _row(
    label: str,
    rules: Iterable[Any],
    *,
    display: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    rules = [rule for rule in rules if getattr(rule, "value", None) is not None]
    if not rules:
        return {
            "label": label,
            "value": None,
            "display": "Sin datos",
            "verification_status": "unverified",
            "source_url": None,
            "consulted_at": None,
            "note": note or "No encontrado en la web oficial.",
        }
    primary = next((rule for rule in rules if _verified(rule)), rules[0])
    source = _source_of([primary])
    return {
        "label": label,
        "value": getattr(primary, "value", None),
        "display": display if display is not None else _fmt_value(primary),
        "verification_status": "verified_official" if _verified(primary) else "unverified",
        "source_url": source.get("url") if source else None,
        "consulted_at": source.get("consulted_at") if source else None,
        "note": note or str(getattr(primary, "notes", "") or ""),
    }


def _join_displays(rules: list[Any]) -> str:
    parts = []
    for rule in rules:
        if getattr(rule, "value", None) is None:
            continue
        text = _fmt_value(rule)
        notes = str(getattr(rule, "notes", "") or "").strip()
        if notes and notes not in text:
            text = f"{text} ({notes})"
        if text not in parts:
            parts.append(text)
    return " · ".join(parts) if parts else "Sin datos"


# --------------------------------------------------------------------------- reglas


def collect_rules(
    account: PropAccount,
    firm: Firm,
    program: Program | None,
) -> dict[str, Any]:
    """Reglas verificadas del programa; lo que no existe queda Sin datos."""

    rules = list(program.rules) if program is not None else []
    constraints = constraint_rows(
        firm, program, phase=account.phase.value
    )
    constraints_by_key = {row["key"]: row for row in constraints}
    rows: list[dict[str, Any]] = []

    policy = firm.automation_for(account.program)
    ea_source = policy.sources[0] if policy.sources else None
    ea_conditions = " · ".join(policy.conditions)
    rows.append(
        {
            "label": "EAs permitidos",
            "value": policy.permission.value,
            "display": f"{policy.permission.value} ({policy.status.value})"
            + (f" · {ea_conditions}" if ea_conditions else ""),
            "verification_status": (
                "verified_official" if policy.status.is_verified else "unverified"
            ),
            "source_url": ea_source.url if ea_source else None,
            "consulted_at": ea_source.consulted_at.isoformat() if ea_source else None,
            "note": "Permiso de automatización de la firma; la cuenta debe confirmarlo.",
        }
    )

    news_rule = next((rule for rule in rules if rule.key == "news_evaluation"), None)
    news_constraint = constraints_by_key.get("news_trading")
    if news_rule is not None:
        notes = str(getattr(news_rule, "notes", "") or "").strip()
        rows.append(
            _row(
                "Noticias",
                [news_rule],
                note=(f"{notes} · " if notes else "")
                + "Restricción comprobable: "
                + (news_constraint["display"] if news_constraint else "Sin datos")
                + ".",
            )
        )
    elif news_constraint and news_constraint["value"] is not None:
        rows.append(
            {
                "label": "Noticias",
                "value": news_constraint["value"],
                "display": news_constraint["display"],
                "verification_status": news_constraint["status"],
                "source_url": news_constraint["source_url"],
                "consulted_at": news_constraint["consulted_at"],
                "note": news_constraint["note"],
            }
        )
    else:
        rows.append(_row("Noticias", []))

    weekend_rule = next(
        (rule for rule in rules if rule.key == "weekend_holding_evaluation"), None
    )
    weekend_constraint = constraints_by_key.get("weekend_holding")
    if weekend_rule is not None:
        notes = str(getattr(weekend_rule, "notes", "") or "").strip()
        rows.append(
            _row(
                "Fin de semana",
                [weekend_rule],
                note=(f"{notes} · " if notes else "")
                + "Restricción comprobable: "
                + (weekend_constraint["display"] if weekend_constraint else "Sin datos")
                + ".",
            )
        )
    elif weekend_constraint and weekend_constraint["value"] is not None:
        rows.append(
            {
                "label": "Fin de semana",
                "value": weekend_constraint["value"],
                "display": weekend_constraint["display"],
                "verification_status": weekend_constraint["status"],
                "source_url": weekend_constraint["source_url"],
                "consulted_at": weekend_constraint["consulted_at"],
                "note": weekend_constraint["note"],
            }
        )
    else:
        rows.append(_row("Fin de semana", []))

    overnight = constraints_by_key.get("overnight_holding")
    if overnight and overnight["value"] is not None:
        rows.append(
            {
                "label": "Overnight",
                "value": overnight["value"],
                "display": overnight["display"],
                "verification_status": overnight["status"],
                "source_url": overnight["source_url"],
                "consulted_at": overnight["consulted_at"],
                "note": overnight["note"],
            }
        )
    else:
        rows.append(_row("Overnight", []))

    min_days = [rule for rule in rules if rule.key == "min_trading_days"]
    rows.append(
        _row(
            "Días mínimos",
            min_days,
            display=_join_displays(min_days) if min_days else None,
            note=(
                f"Cuenta: {account.limits.min_trading_days} días. "
                if account.limits.min_trading_days is not None
                else ""
            )
            + ("El modelo Standard y el Pro difieren; se muestran ambos." if len({_fmt_value(r) for r in min_days}) > 1 else ""),
        )
    )

    loss_rules = [
        rule
        for rule in rules
        if rule.key in {"max_daily_loss_pct", "max_loss_pct", "drawdown_mode"}
    ]
    if loss_rules:
        parts = []
        for rule in loss_rules:
            if rule.key == "drawdown_mode":
                parts.append(f"modo {rule.value}")
            else:
                parts.append(f"{RULE_LABELS.get(rule.key, rule.key)} {_fmt_value(rule)}")
        rows.append(
            _row(
                "Límites de pérdida",
                loss_rules,
                display=" · ".join(parts),
                note=(
                    "Standard y Pro; la cuenta usa los límites conservadores del "
                    "modelo Pro según accounts.yaml."
                ),
            )
        )
    else:
        rows.append(_row("Límites de pérdida", []))

    leverage = [rule for rule in rules if rule.key.startswith("leverage_")]
    if leverage:
        parts = []
        for rule in leverage:
            label = str(rule.key).replace("leverage_", "").capitalize()
            parts.append(f"{label} {_fmt_value(rule)}")
        rows.append(_row("Apalancamiento", leverage, display=" · ".join(parts)))
    else:
        rows.append(_row("Apalancamiento", []))

    time_rules = [
        rule
        for rule in rules
        if rule.key in {"trial_time_limit_days", "time_limit_days", "evaluation_time_limit_days"}
    ]
    rows.append(
        _row(
            "Límite de tiempo",
            time_rules,
            display=(
                " · ".join(f"{_fmt_value(rule)} días naturales por fase" for rule in time_rules)
                if time_rules
                else None
            ),
        )
    )

    max_lots = constraints_by_key.get("max_lots")
    if max_lots and max_lots["value"] is not None:
        rows.append(
            {
                "label": "Máximo de lotes",
                "value": max_lots["value"],
                "display": f"{max_lots['display']} lotes por operación",
                "verification_status": max_lots["status"],
                "source_url": max_lots["source_url"],
                "consulted_at": max_lots["consulted_at"],
                "note": max_lots["note"],
            }
        )
    else:
        rows.append(_row("Máximo de lotes", []))

    max_trades = constraints_by_key.get("max_trades_per_day")
    if max_trades and max_trades["value"] is not None:
        rows.append(
            {
                "label": "Máximo de operaciones/día",
                "value": max_trades["value"],
                "display": max_trades["display"],
                "verification_status": max_trades["status"],
                "source_url": max_trades["source_url"],
                "consulted_at": max_trades["consulted_at"],
                "note": max_trades["note"],
            }
        )
    else:
        rows.append(_row("Máximo de operaciones/día", []))

    return {
        "program": program.id if program is not None else None,
        "program_name": program.name if program is not None else "Sin datos",
        "firm": firm.id,
        "firm_name": firm.name,
        "website": firm.website,
        "rules_version": firm.rules_version,
        "rows": rows,
        "verified": sum(1 for row in rows if row["verification_status"] == "verified_official"),
        "unverified": sum(1 for row in rows if row["verification_status"] != "verified_official"),
    }


# --------------------------------------------------------------------------- bróker


def collect_symbols(
    account: PropAccount,
    *,
    broker: Any | None = None,
    attach: bool = True,
) -> dict[str, Any]:
    """Lee ``symbols_get`` del terminal ya abierto; nunca hace login ni shutdown."""

    result: dict[str, Any] = {
        "status": "Sin datos",
        "identity": None,
        "symbols": [],
        "notes": [],
        "read_only": True,
    }
    if not attach:
        result["notes"].append("Sin datos: MT5 desactivado (--no-mt5)")
        return result
    if account.platform != "mt5":
        result["notes"].append(f"Sin datos: {account.id} no es una cuenta MT5")
        return result
    if broker is None:
        try:
            broker = default_broker_factory(account)
        except Exception as exc:  # noqa: BLE001 - se informa como Sin datos
            result["notes"].append(f"Sin datos: no se pudo preparar el terminal ({exc})")
            return result
    try:
        health = broker.connect() or {}
    except Exception as exc:  # noqa: BLE001
        result["notes"].append(f"Sin datos: MT5 no adjuntado ({exc})")
        return result

    problems: list[str] = []
    login = health.get("login")
    if account.login is not None and int(login or 0) != int(account.login):
        problems.append(f"login esperado {account.login}, terminal {login}")
    server = str(health.get("server") or "").strip()
    if account.server and server.strip().lower() != account.server.strip().lower():
        problems.append(f"servidor esperado {account.server}, terminal {server}")
    mode = str(health.get("mode") or "").strip().lower()
    if mode and mode != "demo":
        problems.append(f"cuenta {mode}; se exige demo")
    if health.get("connected") is False:
        problems.append("terminal desconectado del bróker")

    result["identity"] = {
        "login": login,
        "server": server,
        "mode": mode,
        "connected": health.get("connected"),
        "expected_login": account.login,
        "expected_server": account.server,
        "identity_ok": not problems,
    }
    if problems:
        result["notes"].append("Sin datos: identidad MT5 no verificada: " + "; ".join(problems))
        return result

    try:
        available = broker.symbols() or []
    except Exception as exc:  # noqa: BLE001
        result["notes"].append(f"Sin datos: symbols_get no disponible ({exc})")
        return result
    by_name = {
        str(row.get("symbol") or "").strip().lower(): row
        for row in available
        if row.get("symbol")
    }
    rows = []
    for canonical in account.allowed_instruments:
        declared = (account.broker_symbols or {}).get(canonical)
        expected = declared or canonical
        found = by_name.get(str(expected).strip().lower())
        rows.append(
            {
                "instrument": canonical,
                "expected": expected,
                "declared": bool(declared),
                "found": found is not None,
                "broker_symbol": (found or {}).get("symbol") if found else None,
                "group": (found or {}).get("group") if found else None,
                "digits": (found or {}).get("digits") if found else None,
                "contract_size": (found or {}).get("contract_size") if found else None,
                "volume_min": (found or {}).get("volume_min") if found else None,
            }
        )
    missing = [row["instrument"] for row in rows if not row["found"]]
    result["symbols"] = rows
    result["status"] = "ok" if rows and not missing else "Sin datos"
    if missing:
        result["notes"].append(
            "Sin datos: el bróker no expone " + ", ".join(missing)
        )
    return result


# --------------------------------------------------------------------------- costes


def _commission_text(profile: Any) -> str:
    ctype = getattr(profile, "commission_type", None)
    value = getattr(profile, "commission_value", None)
    side = getattr(profile, "commission_side", None)
    if ctype == "zero":
        return "0 (sin comisión)"
    if ctype == "per_lot_usd":
        return f"{value:g} USD/lote ({side})" if value is not None else "Sin datos"
    if ctype == "percent_of_volume":
        return f"{value:g}% del volumen ({side})" if value is not None else "Sin datos"
    if ctype == "per_contract_usd":
        return f"{value:g} USD/contrato ({side})" if value is not None else "Sin datos"
    return "Sin datos"


def collect_costs(
    account: PropAccount,
    registry: Registry,
    symbols: dict[str, Any],
    *,
    costs_path: str | Path = PROPFUND_COSTS_PATH,
    costs_db: str | Path = DEFAULT_COSTS_DB,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    ai_trader_path: str | Path = DEFAULT_AI_TRADER,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Costes de la cuenta: sync-spreads, hora NY, comisión y slippage asumido."""

    result: dict[str, Any] = {
        "status": "Sin datos",
        "source": "Sin datos",
        "dry_run": True,
        "written": False,
        "identity": symbols.get("identity"),
        "rows": [],
        "hourly": {},
        "notes": [],
        "read_only": True,
    }
    if account.market is not Market.CFD:
        result["notes"].append("Sin datos: motor de costes de futuros pendiente")
        return result

    from ..discovery.config import load_engine_config
    from ..discovery.costs import (
        assumed_slippage_for,
        build_account_cost,
        load_local_hour_spreads,
    )
    from .measure import sync_spreads

    moment = _utc_now(now)
    sync: dict[str, Any] | None = None
    try:
        sync = sync_spreads(
            account.id,
            write=False,
            db_path=costs_db,
            costs_path=Path(costs_path),
            cache_dir=Path(cache_dir),
            ai_trader_path=Path(ai_trader_path),
            now=moment,
            registry=registry,
        )
        result["source"] = str(sync.get("source") or "Sin datos")
    except Exception as exc:  # noqa: BLE001 - se informa como Sin datos
        result["notes"].append(f"sync-spreads Sin datos: {exc}")
    sync_by_symbol = {
        str(row.get("symbol")): row for row in (sync or {}).get("symbols", [])
    }
    config = load_engine_config()
    found = {
        str(row.get("instrument")): row for row in symbols.get("symbols", [])
    }

    for canonical in account.allowed_instruments:
        try:
            item = resolve(canonical)
        except Exception:  # noqa: BLE001
            continue
        try:
            profile = load_profile(
                account.id, canonical, firm=account.firm, path=Path(costs_path)
            )
            commission = _commission_text(profile)
            commission_source = str(
                getattr(profile, "commission_source", None)
                or getattr(profile, "source", None)
                or "Sin datos"
            )
            profile_spread_price = getattr(profile, "spread_price", None)
            profile_spread_p75_price = getattr(profile, "spread_p75_price", None)
        except Exception as exc:  # noqa: BLE001
            commission = "Sin datos"
            commission_source = f"Sin datos: {exc}"
            profile_spread_price = None
            profile_spread_p75_price = None
        try:
            slippage, slippage_source = assumed_slippage_for(canonical, config)
        except Exception as exc:  # noqa: BLE001
            slippage, slippage_source = None, f"Sin datos: {exc}"
        hourly: dict[int, float] = {}
        missing_hours: tuple[int, ...] = ()
        try:
            local = load_local_hour_spreads(
                account.id, canonical, db_path=costs_db
            )
            hourly = dict(local.p75_bps)
            missing_hours = tuple(local.missing_hours)
        except Exception as exc:  # noqa: BLE001
            result["notes"].append(f"{canonical}: hora NY Sin datos ({exc})")
        cost_ok = False
        cost_error = ""
        try:
            build_account_cost(account.id, canonical, db_path=costs_db, config=config)
            cost_ok = True
        except Exception as exc:  # noqa: BLE001
            cost_error = str(exc)

        sync_row = sync_by_symbol.get(item.id) or {}
        symbol_row = found.get(item.id) or {}
        result["rows"].append(
            {
                "instrument": item.id,
                "broker_symbol": symbol_row.get("broker_symbol")
                or (account.broker_symbols or {}).get(item.id)
                or item.id,
                "found": bool(symbol_row.get("found")),
                "p50_bps": sync_row.get("p50_bps"),
                "p75_bps": sync_row.get("p75_bps"),
                "spread_price": sync_row.get("spread_price"),
                "spread_p75_price": sync_row.get("spread_p75_price"),
                "profile_spread_price": profile_spread_price,
                "profile_spread_p75_price": profile_spread_p75_price,
                "measured_at": sync_row.get("measured_at"),
                "sync_status": sync_row.get("status") or "Sin datos",
                "commission": commission,
                "commission_source": commission_source,
                "slippage": slippage,
                "slippage_source": slippage_source,
                "cost_ready": cost_ok,
                "cost_error": cost_error or None,
                "missing_hours": list(missing_hours),
            }
        )
        result["hourly"][item.id] = {
            "hours": {str(hour): value for hour, value in sorted(hourly.items())},
            "missing_hours": list(missing_hours),
        }
    result["status"] = "ok" if any(row["cost_ready"] for row in result["rows"]) else "Sin datos"
    return result


# --------------------------------------------------------------------------- plantillas


def _template_dir() -> Path:
    from ..discovery import genetic

    return genetic.TEMPLATE_DIR


def _default_bars_loader(symbol: str, timeframe: str) -> pd.DataFrame:
    from ..discovery.data_sources import load_source

    source = "dukascopy" if str(timeframe).upper() in {"H4", "D1"} else "broker"
    return load_source(symbol, timeframe, source=source).frame


def _data_symbol(canonical: str, config: Any) -> str:
    item = resolve(canonical)
    keys = {str(name).strip().lower(): str(name) for name in config.data_quality.sources}
    for alias in (item.id, *item.aliases):
        key = str(alias).strip().lower()
        if key in keys:
            return keys[key]
    return item.id


def _is_bounds(config: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = config.data_quality.default_segments["is"]
    return pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)


def _slice_is(frame: pd.DataFrame, config: Any) -> pd.DataFrame:
    start, end = _is_bounds(config)
    index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
    mask = (index >= start) & (index <= end)
    sliced = frame.loc[mask].copy()
    return sliced


def scan_templates(
    account: PropAccount,
    firm: Firm,
    program: Program | None,
    *,
    registry: Registry,
    costs_db: str | Path = DEFAULT_COSTS_DB,
    bars_loader: Callable[[str, str], pd.DataFrame] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mapa de viabilidad: plantillas × instrumento × sesión × TF.

    Solo operaciones IS y ``cost_R``; no calcula PnL, no escribe ``disc_*`` y
    no abre OOS. El coste es siempre el de ESTA cuenta (``cost_mode target``).
    """

    from ..discovery import compiler, dsl, fastbt, genetic, specs
    from ..discovery.config import load_engine_config
    from ..discovery.costs import build_cost_book

    config = load_engine_config()
    loader = bars_loader or _default_bars_loader
    cache: dict[tuple[str, str], pd.DataFrame] = {}
    cache_meta: dict[tuple[str, str], str] = {}
    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    names = sorted(path.stem for path in _template_dir().glob("*.yaml"))

    for template in names:
        try:
            base = genetic.template_strategy(template)
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "template": template,
                    "instrument": "Sin datos",
                    "session": "Sin datos",
                    "timeframe": "Sin datos",
                    "trades_is": 0,
                    "cost_r": None,
                    "compatible": None,
                    "constraint": "Sin datos",
                    "status": "Sin datos",
                    "reasons": [f"plantilla: {exc}"],
                }
            )
            continue
        timeframe = str(base.get("timeframe") or "M5").upper()
        session = dict(base.get("session") or {})
        session_label = f"{session.get('start', 'Sin datos')}-{session.get('end', 'Sin datos')}"
        if session.get("flat_at"):
            session_label += f" · flat {session['flat_at']}"

        for canonical in account.allowed_instruments:
            data_symbol = _data_symbol(canonical, config)
            try:
                model_dict = genetic.configured_template(
                    template,
                    instrument=data_symbol,
                    timeframe=timeframe,
                    session=session,
                )
                model = dsl.Strategy.model_validate(model_dict)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "session": session_label,
                        "timeframe": timeframe,
                        "trades_is": 0,
                        "cost_r": None,
                        "compatible": None,
                        "constraint": "Sin datos",
                        "status": "Sin datos",
                        "reasons": [f"AST: {exc}"],
                    }
                )
                continue
            verdict = check_strategy(
                model, firm=firm, program=program, account=account
            )
            key = (data_symbol, timeframe)
            try:
                if key not in cache:
                    cache[key] = loader(data_symbol, timeframe)
                    cache_meta[key] = data_symbol
                bars = _slice_is(cache[key], config)
                if bars.empty:
                    raise ValueError("Sin datos en IS")
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "session": session_label,
                        "timeframe": timeframe,
                        "trades_is": 0,
                        "cost_r": None,
                        "compatible": verdict.compatible,
                        "constraint": verdict.label,
                        "status": "Sin datos",
                        "reasons": [f"datos: {exc}"],
                    }
                )
                continue
            try:
                book = build_cost_book(
                    canonical,
                    accounts=[account.id],
                    mode="target",
                    session_tz=str(session.get("tz") or "America/New_York"),
                    db_path=costs_db,
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "session": session_label,
                        "timeframe": timeframe,
                        "trades_is": 0,
                        "cost_r": None,
                        "compatible": verdict.compatible,
                        "constraint": verdict.label,
                        "status": "Sin datos",
                        "reasons": [f"coste: {exc}"],
                    }
                )
                continue
            try:
                limits = fastbt.RunLimits(
                    session_tz=str(model.session.tz or "America/New_York"),
                    session_start=model.session.start,
                    session_end=model.session.end,
                    flat_at=model.session.flat_at,
                    weekdays=WEEKDAYS,
                    max_trades_per_day=model.limits.max_trades_per_day,
                    cooldown_bars=specs.cooldown_bars(model),
                    allow_next_day_entry=model.timeframe == "D1",
                )
                trailing = model.exit.trailing or {}
                prepared = fastbt.prepare(
                    bars,
                    book,
                    atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
                    sessions=(limits,),
                )
                signals = compiler.compile(model, bars)
                result = fastbt.run(
                    signals,
                    bars,
                    specs.exit_spec_from_strategy(model),
                    book,
                    limits,
                    prepared=prepared,
                )
                applied = book.apply(
                    result.trades,
                    session_tz=limits.session_tz,
                    point=0.01,
                )
                trades = list(applied.trades)
                costs = [
                    float(trade.r_cost)
                    for trade in trades
                    if trade.r_cost is not None
                ]
                cost_r = float(np.median(costs)) if costs else None
                runs.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "data_symbol": data_symbol,
                        "timeframe": timeframe,
                        "session": session_label,
                        "model": model,
                        "bars": bars,
                        "limits": limits,
                        "signals": signals,
                        "cost_r": cost_r,
                        "trades_is": len(trades),
                    }
                )
                rows.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "session": session_label,
                        "timeframe": timeframe,
                        "trades_is": len(trades),
                        "cost_r": cost_r,
                        "compatible": verdict.compatible,
                        "constraint": verdict.label,
                        "status": "ok",
                        "reasons": [],
                        "dataset": f"live:{data_symbol}",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "template": template,
                        "instrument": canonical,
                        "session": session_label,
                        "timeframe": timeframe,
                        "trades_is": 0,
                        "cost_r": None,
                        "compatible": verdict.compatible,
                        "constraint": verdict.label,
                        "status": "Sin datos",
                        "reasons": [f"{type(exc).__name__}: {exc}"],
                    }
                )
    return {
        "templates": names,
        "rows": rows,
        "runs": runs,
        "bars_cache": cache,
        "cost_mode": "target",
        "cost_account": account.id,
        "n_ok": sum(1 for row in rows if row["status"] == "ok"),
        "n_rows": len(rows),
    }


# --------------------------------------------------------------------------- matriz


def _read_level3(
    discovery_db: str | Path, *, min_level: int = 3
) -> list[dict[str, Any]]:
    path = Path(discovery_db)
    if not path.exists():
        return []
    from ..discovery import databank

    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM disc_strategies WHERE level >= ? ORDER BY id",
                (int(min_level),),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return [databank._strategy_row(row) for row in rows]  # noqa: SLF001


def _read_campaign(discovery_db: str | Path, campaign_id: str) -> dict[str, Any] | None:
    path = Path(discovery_db)
    if not path.exists():
        return None
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT * FROM disc_campaigns WHERE id = ?", (str(campaign_id),)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    import json

    data = dict(row)
    data["config"] = json.loads(data.pop("config_json") or "{}")
    data["quality"] = json.loads(data.pop("quality_json") or "{}")
    return data


def _load_campaign_is(
    campaign: dict[str, Any],
    *,
    bars_loader: Callable[[str, str], pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, str, bool]:
    """Carga IS sin efectos laterales; indica fuente y si el hash coincide."""

    from ..discovery import campaigns, snapshots

    if campaign.get("snapshot_path"):
        try:
            frame = snapshots.load_snapshot(
                str(campaign["snapshot_path"]),
                campaign.get("snapshot_hash") or campaign.get("dataset_hash"),
            )
            start = campaigns._start_ts(campaign["is_start"])  # noqa: SLF001
            end = campaigns._end_ts(campaign["is_end"])  # noqa: SLF001
            return frame[(frame.index >= start) & (frame.index <= end)], "snapshot", True
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"snapshot inválido: {exc}") from exc

    loader = bars_loader or _default_bars_loader
    frame = loader(
        str(campaign["instrument"]),
        str(campaign["timeframe"]),
    )
    source_frame = frame
    matches = campaigns.dataset_matches(campaign, source_frame)
    start = campaigns._start_ts(campaign["is_start"])  # noqa: SLF001
    end = campaigns._end_ts(campaign["is_end"])  # noqa: SLF001
    sliced = frame[(frame.index >= start) & (frame.index <= end)]
    return sliced, "live", bool(matches)


def _automation_status(
    account: PropAccount, firm: Firm, program: Program | None
) -> dict[str, Any]:
    policy = firm.automation_for(account.program)
    allowed = bool(
        policy.permission.allows_auto_orders
        and policy.status.is_verified
        and account.automation_acknowledged
    )
    reasons = []
    if not policy.permission.allows_auto_orders:
        reasons.append(f"permiso {policy.permission.value}")
    if not policy.status.is_verified:
        reasons.append(f"verificación {policy.status.value}")
    if not account.automation_acknowledged:
        reasons.append("la cuenta no tiene automation_acknowledged")
    if policy.exclusive_to_firm:
        reasons.append("bot exclusivo de la firma")
    return {
        "allowed": allowed,
        "permission": policy.permission.value,
        "status": policy.status.value,
        "acknowledged": bool(account.automation_acknowledged),
        "exclusive_to_firm": bool(policy.exclusive_to_firm),
        "reason": "Permitida" if allowed else "; ".join(reasons) or "Sin datos",
    }


def recompute_level3(
    account: PropAccount,
    firm: Firm,
    program: Program | None,
    *,
    registry: Registry,
    discovery_db: str | Path = DEFAULT_DISCOVERY_DB,
    costs_db: str | Path = DEFAULT_COSTS_DB,
    bars_loader: Callable[[str, str], pd.DataFrame] | None = None,
    n_paths: int | None = None,
    now: datetime | None = None,
    min_level: int = 3,
) -> dict[str, Any]:
    """Recalcula estrategias nivel >= ``min_level`` con coste/reglas de cuenta.

    No reoptimiza, no escribe ``disc_*`` y no lee OOS-2. Si el dataset de la
    campaña no coincide con el hash sellado, lo marca y el resultado es
    indicativo.
    """

    from ..discovery import compiler, dsl, fastbt, metrics, specs
    from ..discovery.config import load_engine_config
    from ..discovery.costs import build_cost_book
    from ..prop.simulator import monte_carlo

    strategies = _read_level3(discovery_db, min_level=int(min_level))
    if not strategies:
        return {
            "rows": [],
            "note": "Sin estrategias de nivel ≥ 3 en el databank.",
            "n": 0,
        }
    config = load_engine_config()
    paths = int(n_paths or config.robustness.challenge_paths)
    automation = _automation_status(account, firm, program)
    rows: list[dict[str, Any]] = []

    for strategy in strategies:
        campaign = _read_campaign(discovery_db, str(strategy.get("campaign_id")))
        base = {
            "strategy_id": int(strategy["id"]),
            "campaign_id": str(strategy.get("campaign_id")),
            "instrument": str(strategy.get("instrument") or "Sin datos"),
            "timeframe": str(strategy.get("timeframe") or "Sin datos"),
            "level": int(strategy.get("level") or 1),
            "verdict": strategy.get("verdict"),
            "status": str(strategy.get("status") or "Sin datos"),
        }
        if campaign is None:
            rows.append(
                {
                    **base,
                    "expectancy_r": None,
                    "cost_r": None,
                    "pass_rate": None,
                    "breach_rate": None,
                    "compatible": None,
                    "constraint": "Sin datos: campaña no encontrada",
                    "automation": automation,
                    "dataset": "Sin datos",
                    "status_row": "Sin datos",
                    "reasons": ["campaña no encontrada"],
                }
            )
            continue
        try:
            canonical = resolve(str(strategy.get("instrument"))).id
        except Exception:  # noqa: BLE001
            canonical = str(strategy.get("instrument") or "").upper()
        if canonical not in account.allowed_instruments:
            rows.append(
                {
                    **base,
                    "expectancy_r": None,
                    "cost_r": None,
                    "pass_rate": None,
                    "breach_rate": None,
                    "compatible": False,
                    "constraint": f"incompatible con {firm.id}: la cuenta no permite {canonical}",
                    "automation": automation,
                    "dataset": "Sin datos",
                    "status_row": "No aplicable",
                    "reasons": [f"{canonical} fuera de allowed_instruments"],
                }
            )
            continue
        try:
            model = dsl.Strategy.model_validate(strategy["dsl"])
            validation_errors = dsl.validate(model)
            bars, dataset_source, dataset_match = _load_campaign_is(
                campaign, bars_loader=bars_loader
            )
            if bars.empty:
                raise ValueError("Sin datos en IS")
            book = build_cost_book(
                canonical,
                accounts=[account.id],
                mode="target",
                session_tz=str(model.session.tz or "America/New_York"),
                db_path=costs_db,
                config=config,
            )
            limits = fastbt.RunLimits(
                session_tz=str(model.session.tz or "America/New_York"),
                session_start=model.session.start,
                session_end=model.session.end,
                flat_at=model.session.flat_at,
                weekdays=WEEKDAYS,
                max_trades_per_day=model.limits.max_trades_per_day,
                cooldown_bars=specs.cooldown_bars(model),
                allow_next_day_entry=model.timeframe == "D1",
            )
            trailing = model.exit.trailing or {}
            prepared = fastbt.prepare(
                bars,
                book,
                atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
                sessions=(limits,),
            )
            signals = compiler.compile(
                model,
                bars,
                _skip_validation_for_archived=bool(validation_errors),
            )
            result = fastbt.run(
                signals,
                bars,
                specs.exit_spec_from_strategy(model),
                book,
                limits,
                prepared=prepared,
            )
            applied = book.apply(
                result.trades, session_tz=limits.session_tz, point=0.01
            )
            trades = list(applied.trades)
            cost_r = float(np.median([trade.r_cost for trade in trades if trade.r_cost is not None])) if trades else None
            expectancy = metrics.expectancy_r(trades)
            simulation = None
            if len(applied.daily_r) >= 2 and account.risk.per_trade_risk_pct > 0:
                rules = _rules_from_account(account, {})
                simulation = monte_carlo(
                    rules,
                    pd.to_numeric(applied.daily_r, errors="coerce").dropna().to_numpy(dtype=float)
                    * float(account.risk.per_trade_risk_pct),
                    n_paths=paths,
                    horizon=60,
                    seed=42,
                    block_size=5,
                )
            verdict = check_strategy(
                model, firm=firm, program=program, account=account
            )
            reasons = []
            if validation_errors:
                reasons.append(
                    "validación actual: "
                    + "; ".join(validation_errors)
                    + " (se recalcula el AST existente sin reoptimizar)"
                )
            if not dataset_match:
                reasons.append(
                    "dataset_hash no coincide con el dataset sellado; "
                    "recalculo indicativo sobre la fuente viva"
                )
            rows.append(
                {
                    **base,
                    "expectancy_r": expectancy,
                    "cost_r": cost_r,
                    "pass_rate": None if simulation is None else float(simulation["pass_rate"]),
                    "breach_rate": None if simulation is None else float(simulation["breach_rate"]),
                    "compatible": verdict.compatible,
                    "constraint": verdict.label,
                    "automation": automation,
                    "dataset": dataset_source + (" (hash ok)" if dataset_match else " (hash distinto)"),
                    "dataset_match": dataset_match,
                    "validation_errors": list(validation_errors),
                    "validation_skipped": bool(validation_errors),
                    "trades": len(trades),
                    "status_row": "ok",
                    "reasons": reasons,
                }
            )
        except Exception as exc:  # noqa: BLE001 - se informa la fila
            rows.append(
                {
                    **base,
                    "expectancy_r": None,
                    "cost_r": None,
                    "pass_rate": None,
                    "breach_rate": None,
                    "compatible": None,
                    "constraint": f"Sin datos: {type(exc).__name__}: {exc}",
                    "automation": automation,
                    "dataset": "Sin datos",
                    "status_row": "Sin datos",
                    "reasons": [str(exc)],
                }
            )
    return {
        "rows": rows,
        "note": "" if rows else "Sin estrategias de nivel ≥ 3 en el databank.",
        "n": len(rows),
        "paths": paths,
    }


# --------------------------------------------------------------------------- resumen


def _run_with_cost(
    run: Mapping[str, Any],
    account_id: str,
    *,
    costs_db: str | Path,
) -> float | None:
    from ..discovery import fastbt, specs
    from ..discovery.config import load_engine_config
    from ..discovery.costs import build_cost_book

    config = load_engine_config()
    book = build_cost_book(
        str(run["instrument"]),
        accounts=[account_id],
        mode="target",
        session_tz=str(run["limits"].session_tz),
        db_path=costs_db,
        config=config,
    )
    trailing = run["model"].exit.trailing or {}
    prepared = fastbt.prepare(
        run["bars"],
        book,
        atr_windows=(run["model"].exit.stop.n, int(trailing.get("n", 14))),
        sessions=(run["limits"],),
    )
    result = fastbt.run(
        run["signals"],
        run["bars"],
        specs.exit_spec_from_strategy(run["model"]),
        book,
        run["limits"],
        prepared=prepared,
    )
    applied = book.apply(result.trades, session_tz=run["limits"].session_tz)
    costs = [float(trade.r_cost) for trade in applied.trades if trade.r_cost is not None]
    return float(np.median(costs)) if costs else None


def compare_costs(
    account: PropAccount,
    registry: Registry,
    scan: Mapping[str, Any],
    *,
    costs_db: str | Path = DEFAULT_COSTS_DB,
) -> dict[str, Any]:
    """Compara el coste de esta cuenta con las demás cuentas elegibles."""

    from ..discovery.costs import eligible_cost_accounts

    best: dict[str, dict[str, Any]] = {}
    for run in scan.get("runs", []):
        if run.get("cost_r") is None:
            continue
        current = best.get(str(run["instrument"]))
        if current is None or float(run["cost_r"]) < float(current["cost_r"]):
            best[str(run["instrument"])] = run
    comparisons = []
    for instrument, run in sorted(best.items()):
        try:
            others = [
                candidate
                for candidate in eligible_cost_accounts(instrument)
                if candidate != account.id
            ]
        except Exception:  # noqa: BLE001
            others = []
        for other in others:
            try:
                other_cost = _run_with_cost(run, other, costs_db=costs_db)
            except Exception:  # noqa: BLE001
                other_cost = None
            if other_cost is None:
                continue
            target_cost = float(run["cost_r"])
            comparisons.append(
                {
                    "instrument": instrument,
                    "template": run["template"],
                    "target_account": account.id,
                    "target_cost_r": target_cost,
                    "other_account": other,
                    "other_cost_r": other_cost,
                    "delta": target_cost - other_cost,
                    "target_cheaper": target_cost <= other_cost,
                }
            )
    return {"rows": comparisons, "n": len(comparisons)}


def build_summary(
    account: PropAccount,
    firm: Firm,
    scan: Mapping[str, Any],
    matrix: Mapping[str, Any],
    comparisons: Mapping[str, Any],
    *,
    config: Any,
) -> dict[str, Any]:
    max_cost = float(config.fitness.cost_r_max)
    min_trades = int(config.validation.min_trades_is)
    suggestions = []
    for row in scan.get("rows", []):
        if row.get("status") != "ok":
            continue
        if row.get("compatible") is not True:
            continue
        validation = config.validation.for_timeframe(row.get("timeframe") or "M5")
        if int(row.get("trades_is") or 0) < int(validation.min_trades_is):
            continue
        if row.get("cost_r") is None or float(row["cost_r"]) > max_cost:
            continue
        suggestions.append(
            {
                "template": row["template"],
                "instrument": row["instrument"],
                "session": row["session"],
                "timeframe": row["timeframe"],
                "trades_is": int(row["trades_is"]),
                "cost_r": float(row["cost_r"]),
                "constraint": row["constraint"],
                "label": "por probar",
            }
        )
    suggestions.sort(key=lambda item: (item["cost_r"], -item["trades_is"]))
    cheaper = [row for row in comparisons.get("rows", []) if row["target_cheaper"]]
    return {
        "target_account": account.id,
        "firm": firm.id,
        "cheapest_instruments": [
            {
                "instrument": row["instrument"],
                "target_cost_r": row["target_cost_r"],
                "other_account": row["other_account"],
                "other_cost_r": row["other_cost_r"],
                "delta": row["delta"],
            }
            for row in cheaper
        ],
        "comparisons": list(comparisons.get("rows", [])),
        "suggestions": suggestions[:5],
        "suggestion_note": (
            "Combinaciones por probar; no son candidatas ni se ha registrado "
            "nada. La campaña la decide y aprueba el operador."
        ),
        "matrix_note": matrix.get("note", ""),
        "cost_r_max": max_cost,
        "min_trades_is": min_trades,
    }


# --------------------------------------------------------------------------- markdown


def _cell(value: Any) -> str:
    if value is None:
        return "Sin datos"
    text = str(value).replace("|", "/").replace("\n", " ").strip()
    return text or "Sin datos"


def _num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return _cell(value)


def _pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return _cell(value)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def _fmt_hourly(hourly: Mapping[str, Any]) -> str:
    values = hourly.get("hours") or {}
    if not values:
        return "Sin datos"
    parts = []
    for hour in range(24):
        value = values.get(str(hour))
        parts.append(f"{hour:02d}:{'—' if value is None else f'{float(value):.3f}'}")
    text = " · ".join(parts)
    missing = hourly.get("missing_hours") or []
    if missing:
        text += f" · faltan {', '.join(str(hour).zfill(2) for hour in missing)}"
    return text


def render_markdown(report: Mapping[str, Any]) -> str:
    rules = report.get("rules") or {}
    costs = report.get("costs") or {}
    symbols = report.get("symbols") or {}
    scan = report.get("scan") or {}
    matrix = report.get("matrix") or {}
    constraints = report.get("constraints") or []
    summary = report.get("summary") or {}
    lines: list[str] = []
    lines.append(f"# Onboarding · {report['account']} ({report['firm_name']})")
    lines.append("")
    lines.append(f"- Generado: {report['generated_at']}")
    lines.append(
        f"- Cuenta: `{report['account']}` · firma `{report['firm']}` · programa "
        f"`{report.get('program') or 'Sin datos'}` · fase `{report['phase']}`"
    )
    lines.append(f"- Tamaño nominal: {report['nominal_size']:,.0f} USD · mercado {report['market']}")
    lines.append(
        "- Modo: solo lectura. Sin campañas, sin OOS, sin `count_tests`. "
        "MT5 solo adjunto: sin login ni shutdown."
    )
    if report.get("warnings"):
        lines.append("")
        lines.append("**Avisos:**")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")

    lines.append("## 1. Reglas del programa")
    lines.append("")
    lines.append(
        f"Programa **{rules.get('program_name', 'Sin datos')}** · reglas versión "
        f"`{rules.get('rules_version', 'Sin datos')}` · web {rules.get('website') or 'Sin datos'}"
    )
    lines.append(
        f"Verificadas: {rules.get('verified', 0)} · sin verificar/Sin datos: "
        f"{rules.get('unverified', 0)}"
    )
    lines.append("")
    rule_rows = []
    for row in rules.get("rows", []):
        source = row.get("source_url") or "Sin datos"
        consulted = row.get("consulted_at") or "Sin datos"
        rule_rows.append(
            [
                row["label"],
                row["display"],
                row["verification_status"],
                source,
                consulted,
                row.get("note") or "",
            ]
        )
    lines.extend(
        _table(
            ["Regla", "Valor", "verification_status", "Fuente", "Fecha", "Nota"],
            rule_rows,
        )
    )
    lines.append("")

    lines.append("## 2. Costes de la cuenta")
    lines.append("")
    identity = costs.get("identity") or symbols.get("identity") or {}
    lines.append(
        f"Identidad MT5: login `{identity.get('login')}` · servidor "
        f"`{identity.get('server')}` · modo `{identity.get('mode')}` · "
        f"identidad verificada: `{identity.get('identity_ok')}`"
    )
    lines.append(f"sync-spreads: `{costs.get('source')}` · dry-run: `{costs.get('dry_run')}`")
    lines.append("")
    lines.append("### 2.1 Símbolos del bróker (`symbols_get`)")
    lines.append("")
    lines.extend(
        _table(
            [
                "Instrumento",
                "Esperado",
                "Declarado",
                "Encontrado",
                "Símbolo bróker",
                "Grupo",
                "digits",
                "contract_size",
                "volume_min",
            ],
            [
                [
                    row["instrument"],
                    row["expected"],
                    row["declared"],
                    row["found"],
                    row["broker_symbol"],
                    row["group"],
                    row["digits"],
                    row["contract_size"],
                    row["volume_min"],
                ]
                for row in symbols.get("symbols", [])
            ],
        )
    )
    lines.append("")
    lines.append("### 2.2 Spread p75 por hora local Nueva York")
    lines.append("")
    hourly_rows = []
    for row in costs.get("rows", []):
        hourly_rows.append(
            [
                row["instrument"],
                row["broker_symbol"],
                _fmt_hourly((costs.get("hourly") or {}).get(row["instrument"]) or {}),
            ]
        )
    lines.extend(_table(["Instrumento", "Símbolo", "p75 bps por hora NY"], hourly_rows))
    lines.append("")
    lines.append("### 2.3 Comisión, spread y slippage")
    lines.append("")
    cost_rows = []
    for row in costs.get("rows", []):
        cost_rows.append(
            [
                row["instrument"],
                row["spread_price"],
                row["spread_p75_price"],
                row.get("profile_spread_price"),
                row.get("profile_spread_p75_price"),
                row["commission"],
                row["commission_source"],
                row["slippage"],
                row["slippage_source"],
                row["sync_status"],
                row["cost_ready"],
            ]
        )
    lines.extend(
        _table(
            [
                "Instrumento",
                "Spread p50 sync",
                "Spread p75 sync",
                "Spread p50 perfil",
                "Spread p75 perfil",
                "Comisión citada",
                "Fuente comisión",
                "Slippage",
                "Fuente slippage",
                "sync",
                "Coste listo",
            ],
            cost_rows,
        )
    )
    if costs.get("notes"):
        lines.append("")
        for note in costs["notes"]:
            lines.append(f"- {note}")
    lines.append("")

    lines.append("## 3. Mapa de viabilidad")
    lines.append("")
    lines.append(
        f"Plantillas: {', '.join(scan.get('templates', [])) or 'Sin datos'} · "
        f"coste `{scan.get('cost_mode')}:{scan.get('cost_account')}` · "
        f"filas OK {scan.get('n_ok', 0)}/{scan.get('n_rows', 0)}. "
        "Solo operaciones IS y `cost_R`; sin PnL."
    )
    lines.append("")
    scan_rows = []
    for row in scan.get("rows", []):
        scan_rows.append(
            [
                row["template"],
                row["instrument"],
                row["session"],
                row["timeframe"],
                row["trades_is"],
                _num(row["cost_r"]),
                row.get("constraint") or "Sin datos",
                row["status"],
                "; ".join(row.get("reasons") or []),
            ]
        )
    lines.extend(
        _table(
            [
                "Plantilla",
                "Instrumento",
                "Sesión",
                "TF",
                "Operaciones IS",
                "cost_R",
                "Compatibilidad",
                "Estado",
                "Motivos",
            ],
            scan_rows,
        )
    )
    lines.append("")

    lines.append("## 4. Restricciones de la firma")
    lines.append("")
    lines.extend(
        _table(
            ["Restricción", "Valor", "verification_status", "Fuente", "Fecha", "Nota"],
            [
                [
                    row["label"],
                    row["display"],
                    row["status"],
                    row["source_url"] or "Sin datos",
                    row["consulted_at"] or "Sin datos",
                    row.get("note") or "",
                ]
                for row in constraints
            ],
        )
    )
    lines.append("")

    lines.append("## 5. Matriz de estrategias nivel ≥ 3")
    lines.append("")
    if not matrix.get("rows"):
        lines.append(matrix.get("note") or "Sin estrategias de nivel ≥ 3.")
    else:
        lines.append(
            "DSL congelado, sin reoptimizar, solo IS. P(pasar)/P(romper) con "
            f"`monte_carlo` ({matrix.get('paths', 'Sin datos')} sendas, horizonte "
            "60 días) y las reglas de esta cuenta."
        )
        lines.append("")
        matrix_rows = []
        for row in matrix.get("rows", []):
            automation = row.get("automation") or {}
            matrix_rows.append(
                [
                    row["strategy_id"],
                    row["campaign_id"],
                    row["instrument"],
                    row["timeframe"],
                    row["level"],
                    _num(row["expectancy_r"]),
                    _num(row["cost_r"]),
                    _pct(row["pass_rate"]),
                    _pct(row["breach_rate"]),
                    row.get("constraint"),
                    automation.get("reason"),
                    row.get("dataset"),
                    "; ".join(row.get("reasons") or []),
                ]
            )
        lines.extend(
            _table(
                [
                    "ID",
                    "Campaña",
                    "Instrumento",
                    "TF",
                    "Nivel",
                    "Expectativa neta R",
                    "cost_R",
                    "P(pasar)",
                    "P(romper)",
                    "Compatibilidad",
                    "Automatización",
                    "Dataset",
                    "Avisos",
                ],
                matrix_rows,
            )
        )
    lines.append("")

    lines.append("## 6. Resumen")
    lines.append("")
    if summary.get("comparisons"):
        lines.append("### 6.1 Coste frente a otras cuentas")
        lines.append("")
        lines.extend(
            _table(
                ["Instrumento", "Plantilla", "Cuenta", "cost_R", "Otra cuenta", "cost_R otra", "Delta", "Esta más barata"],
                [
                    [
                        row["instrument"],
                        row["template"],
                        row["target_account"],
                        _num(row["target_cost_r"]),
                        row["other_account"],
                        _num(row["other_cost_r"]),
                        _num(row["delta"]),
                        row["target_cheaper"],
                    ]
                    for row in summary["comparisons"]
                ],
            )
        )
        if summary.get("cheapest_instruments"):
            lines.append("")
            lines.append(
                "Instrumentos donde esta cuenta es más barata: "
                + ", ".join(row["instrument"] for row in summary["cheapest_instruments"])
            )
        else:
            lines.append("")
            lines.append("Sin ventaja de coste demostrada frente a las demás cuentas.")
    else:
        lines.append("Sin datos para comparar el coste con otras cuentas.")
    lines.append("")
    lines.append("### 6.2 Combinaciones por probar")
    lines.append("")
    if summary.get("suggestions"):
        lines.extend(
            _table(
                ["Plantilla", "Instrumento", "Sesión", "TF", "Operaciones IS", "cost_R", "Compatibilidad"],
                [
                    [
                        row["template"],
                        row["instrument"],
                        row["session"],
                        row["timeframe"],
                        row["trades_is"],
                        _num(row["cost_r"]),
                        row["constraint"],
                    ]
                    for row in summary["suggestions"]
                ],
            )
        )
        lines.append("")
        lines.append(summary.get("suggestion_note") or "")
    else:
        lines.append(
            "Sin combinaciones que cumplan a la vez: compatible, "
            f">= {summary.get('min_trades_is', 'Sin datos')} operaciones IS y "
            f"cost_R <= {summary.get('cost_r_max', 'Sin datos')}."
        )
    if summary.get("matrix_note"):
        lines.append("")
        lines.append(f"Matriz: {summary['matrix_note']}")
    lines.append("")
    lines.append(
        "---\n"
        "Informe generado por `lab propfund onboard`. No es una campaña, no lee "
        "OOS y no suma pruebas al DSR."
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- entrada


def onboard(
    account_id: str,
    *,
    registry: Registry | None = None,
    broker: Any | None = None,
    attach: bool = True,
    costs_path: str | Path = PROPFUND_COSTS_PATH,
    costs_db: str | Path = DEFAULT_COSTS_DB,
    discovery_db: str | Path = DEFAULT_DISCOVERY_DB,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    ai_trader_path: str | Path = DEFAULT_AI_TRADER,
    bars_loader: Callable[[str, str], pd.DataFrame] | None = None,
    scan: bool = True,
    matrix: bool = True,
    write: bool = True,
    out: str | Path | None = None,
    now: datetime | None = None,
    n_paths: int | None = None,
) -> dict[str, Any]:
    """Ejecuta el onboarding de una cuenta y escribe el informe markdown."""

    reg = registry or load_registry()
    account = reg.accounts.get(str(account_id).strip().upper())
    if account is None:
        raise ValueError(f"{account_id}: cuenta no registrada en propfund")
    firm = reg.firms.get(account.firm)
    if firm is None:
        raise ValueError(f"{account_id}: firma {account.firm} no registrada")
    program = firm.program(account.program)
    moment = _utc_now(now)
    warnings: list[str] = []

    rules = collect_rules(account, firm, program)
    symbols = collect_symbols(account, broker=broker, attach=attach)
    costs = collect_costs(
        account,
        reg,
        symbols,
        costs_path=costs_path,
        costs_db=costs_db,
        cache_dir=cache_dir,
        ai_trader_path=ai_trader_path,
        now=moment,
    )
    constraints = constraint_rows(firm, program, phase=account.phase.value)
    from ..discovery.config import load_engine_config

    config = load_engine_config()
    scan_payload: dict[str, Any] = {
        "templates": [],
        "rows": [],
        "runs": [],
        "cost_mode": "target",
        "cost_account": account.id,
        "n_ok": 0,
        "n_rows": 0,
    }
    if scan and account.market is Market.CFD and costs.get("status") == "ok":
        from ..discovery import edge_map

        scan_payload = edge_map.suggest(
            account.id,
            discovery_db=discovery_db,
            costs_db=costs_db,
            bars_loader=bars_loader,
            registry=reg,
        )
        scan_payload.update(
            {
                "runs": [],
                "cost_mode": "target",
                "cost_account": account.id,
            }
        )
    elif scan and account.market is Market.CFD:
        warnings.append("Mapa de viabilidad Sin datos: la cuenta no tiene coste completo.")
    matrix_payload: dict[str, Any] = {
        "rows": [],
        "note": "Matriz desactivada.",
        "n": 0,
    }
    if matrix:
        matrix_payload = recompute_level3(
            account,
            firm,
            program,
            registry=reg,
            discovery_db=discovery_db,
            costs_db=costs_db,
            bars_loader=bars_loader,
            n_paths=n_paths,
            now=moment,
        )
    comparisons = (
        compare_costs(account, reg, scan_payload, costs_db=costs_db)
        if scan_payload.get("runs")
        else {"rows": [], "n": 0}
    )
    summary = build_summary(
        account,
        firm,
        scan_payload,
        matrix_payload,
        comparisons,
        config=config,
    )
    if symbols.get("notes"):
        warnings.extend(symbols["notes"])
    if costs.get("notes"):
        warnings.extend(costs["notes"])
    for row in matrix_payload.get("rows", []):
        warnings.extend(
            f"Estrategia {row.get('strategy_id')}: {reason}"
            for reason in row.get("reasons") or []
        )

    report = {
        "account": account.id,
        "firm": firm.id,
        "firm_name": firm.name,
        "program": program.id if program is not None else None,
        "phase": account.phase.value,
        "market": account.market.value,
        "nominal_size": float(account.nominal_size),
        "generated_at": moment.isoformat(timespec="seconds"),
        "read_only": True,
        "count_tests_changed": False,
        "rules": rules,
        "symbols": symbols,
        "costs": costs,
        "constraints": constraints,
        "scan": scan_payload,
        "matrix": matrix_payload,
        "summary": summary,
        "warnings": list(dict.fromkeys(warnings)),
    }
    markdown = render_markdown(report)
    target = Path(out) if out is not None else REPORT_DIR / f"{account.id}_onboarding.md"
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
    report["markdown"] = markdown
    report["path"] = str(target) if write else None
    return report


__all__ = [
    "REPORT_DIR",
    "build_summary",
    "collect_costs",
    "collect_rules",
    "collect_symbols",
    "compare_costs",
    "onboard",
    "recompute_level3",
    "render_markdown",
    "scan_templates",
]
