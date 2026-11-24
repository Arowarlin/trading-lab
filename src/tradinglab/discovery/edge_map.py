"""Edge Map: dónde hay edge, en qué TF y para qué firma.

Lee el Discovery databank en **solo lectura** y combina:

* métricas brutas (coste 0) sobre IS, con mediana de la rejilla o de la
  frontera de rango 1 según el modo de campaña;
* PBO, walk-forward y veredicto ya guardados;
* capa de firma: coste de cada cuenta, restricciones y Monte Carlo del challenge;
* confirmación OOS-2 por cuenta, si existe.

No lee OOS-2, no registra trials, no escribe ``disc_*`` ni modifica el contador
global. La exportación va a ``reports/discovery/``.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..config import ROOT
from ..prop.simulator import monte_carlo
from ..propfund.constraints import check_strategy
from ..propfund.instruments import resolve
from ..propfund.models import ConnectionState, Market
from ..propfund.registry import load_registry
from . import (
    campaigns,
    compiler,
    costs,
    data_sources,
    databank,
    dsl,
    fastbt,
    fitness,
    genetic,
    jobs,
    metrics,
    snapshots,
    specs,
)
from .config import load_engine_config

REPORT_DIR = ROOT / "reports" / "discovery"
STATES = (
    "sin probar",
    "solo viabilidad",
    "inválida",
    "sin edge bruto",
    "edge bruto que el coste elimina",
    "sobreajustada",
    "candidata nivel 3",
    "confirmada nivel 4",
    "no verificable",
)
DUKASCOPY_BLOCKED = "Sin datos (Dukascopy en descarga)"


class EdgeMapError(ValueError):
    pass


@dataclass
class ComboEdge:
    template: str
    template_version: str
    instrument: str
    timeframe: str
    source: str
    state: str
    campaigns: list[str] = field(default_factory=list)
    campaign_status: str | None = None
    raw_median_r: float | None = None
    raw_best_r: float | None = None
    net_median_r: float | None = None
    net_best_r: float | None = None
    cost_r: float | None = None
    strategy_total: int = 0
    positive_folds_count: int = 0
    folds_required: int = 0
    overfit_count: int = 0
    candidate_count: int = 0
    confirmed_count: int = 0
    pbo: float | None = None
    wf_ok: bool | None = None
    best_strategy_id: int | None = None
    best_strategy_hash: str | None = None
    dataset_source: str = "Sin datos"
    dataset_verified: bool | None = None
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FirmEdge:
    strategy_id: int
    campaign_id: str
    template: str
    instrument: str
    timeframe: str
    account: str
    firm: str
    level: int
    verdict: str | None
    pbo: float | None
    wf_ok: bool | None
    net_expectancy_r: float | None
    cost_r: float | None
    trades: int
    pass_rate: float | None
    breach_rate: float | None
    compatible: bool | None
    constraint: str
    automation_allowed: bool
    automation_reason: str
    candidate: bool
    confirm_status: str
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ro_connect(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    if not target.exists():
        raise EdgeMapError(f"Sin datos: no existe {target}")
    uri = f"file:{target.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _campaign_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["config"] = json.loads(data.pop("config_json") or "{}")
    data["quality"] = json.loads(data.pop("quality_json") or "{}")
    return data


def _strategy_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["dsl"] = json.loads(data.pop("dsl_json") or "{}")
    return data


def _canonical(symbol: str) -> str:
    try:
        return str(resolve(symbol).id).upper()
    except Exception:  # noqa: BLE001
        return str(symbol or "").strip().upper()


def template_version(template: str) -> str:
    path = genetic.TEMPLATE_DIR / f"{template}.yaml"
    if not path.exists():
        return "Sin datos"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _validation_map(
    con: sqlite3.Connection,
) -> dict[tuple[int, str], dict[str, Any]]:
    result: dict[tuple[int, str], dict[str, Any]] = {}
    for row in con.execute(
        "SELECT strategy_id, test, result_json, passed FROM disc_validations"
    ):
        try:
            payload = json.loads(row["result_json"] or "{}")
        except ValueError:
            payload = {}
        payload["passed"] = row["passed"]
        result[(int(row["strategy_id"]), str(row["test"]))] = payload
    return result


def _net_metrics(con: sqlite3.Connection, strategy_id: int) -> dict[str, Any]:
    row = con.execute(
        "SELECT metrics_json FROM disc_evaluations"
        " WHERE strategy_id = ? AND segment = 'fitness_is'",
        (int(strategy_id),),
    ).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(row["metrics_json"] or "{}")
    except ValueError:
        return {}


def _frontier_ids(con: sqlite3.Connection, campaign_id: str) -> list[int]:
    rows = con.execute(
        "SELECT DISTINCT s.id FROM disc_strategies s"
        " JOIN disc_lineage l ON l.strategy_id = s.id"
        " WHERE s.campaign_id = ? AND l.final = 1 AND l.rank = 0"
        " ORDER BY s.id",
        (campaign_id,),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _tested_keys(con: sqlite3.Connection) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for row in con.execute(
        "SELECT instrument, timeframe, template, config_json, n_evaluated"
        " FROM disc_campaigns"
    ):
        try:
            config = json.loads(row["config_json"] or "{}")
        except ValueError:
            config = {}
        template = str(row["template"] or "")
        instrument = _canonical(row["instrument"])
        timeframe = str(row["timeframe"] or "").upper()
        source = str(config.get("data_source") or "broker").lower()
        keys.add((template, instrument, timeframe, source))
        if int(row["n_evaluated"] or 0) > 0:
            keys.add((template, instrument, timeframe, "*"))
    return keys


def _resolve_snapshot(path: str, data_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    for root in (data_root, ROOT):
        resolved = root / candidate
        if resolved.exists():
            return resolved
    return data_root / candidate


def _slice_is(frame: pd.DataFrame, campaign: dict[str, Any]) -> pd.DataFrame:
    start = campaigns._start_ts(campaign["is_start"])  # noqa: SLF001
    end = campaigns._end_ts(campaign["is_end"])  # noqa: SLF001
    return frame[(frame.index >= start) & (frame.index <= end)]


def _load_campaign_frame(
    campaign: dict[str, Any],
    *,
    data_root: Path,
    bars_loader,
    allow_dukascopy: bool,
) -> tuple[pd.DataFrame, str, bool, bool]:
    """Devuelve (barras IS, origen, verificado, usa_datos_vivos)."""

    config = campaign.get("config") or {}
    source = str(config.get("data_source") or "broker").lower()
    timeframe = str(campaign["timeframe"]).upper()
    if timeframe in {"H4", "D1"} and source == "dukascopy" and not allow_dukascopy:
        raise EdgeMapError(DUKASCOPY_BLOCKED)
    if campaign.get("snapshot_path"):
        path = _resolve_snapshot(str(campaign["snapshot_path"]), data_root)
        try:
            frame = snapshots.load_snapshot(
                path,
                campaign.get("snapshot_hash") or campaign.get("dataset_hash"),
            )
        except snapshots.SnapshotError as exc:
            raise EdgeMapError(f"snapshot inválido: {exc}") from exc
        return _slice_is(frame, campaign), "snapshot", True, False
    if bars_loader is not None:
        frame = bars_loader(campaign["instrument"], timeframe)
    else:
        frame = data_sources.load_source(
            campaign["instrument"],
            timeframe,
            source=source,
            root=data_root,
        ).frame
    verified = bool(
        campaign.get("dataset_hash")
        and campaigns.dataset_matches(campaign, frame)
    )
    return _slice_is(frame, campaign), "fuente viva", verified, True


def _raw_strategy(
    strategy: dict[str, Any],
    campaign: dict[str, Any],
    bars: pd.DataFrame,
    config,
) -> dict[str, Any]:
    model = dsl.Strategy.model_validate(strategy["dsl"])
    validation_errors = dsl.validate(model)
    signals = compiler.compile(
        model,
        bars,
        _skip_validation_for_archived=bool(validation_errors),
    )
    setup = jobs.QueueSetup.from_campaign(campaign, bars=bars)
    if not (campaign.get("config") or {}).get("cost_model_version"):
        setup = replace(
            setup, cost_model_version=costs.default_cost_model_version()
        )
    limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
    zero = fastbt.cfd_costs_from_bps(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )
    prepared = fastbt.prepare(bars, zero, sessions=(limits,))
    result = fastbt.run(
        signals,
        bars,
        specs.exit_spec_from_strategy(model),
        zero,
        limits,
        prepared=prepared,
        collect_metrics=False,
    )
    gross = [
        float(trade.r_gross)
        for trade in result.trades
        if trade.r_gross is not None and math.isfinite(float(trade.r_gross))
    ]
    validation = config.validation.for_timeframe(strategy["timeframe"])
    folds = int(validation.folds)
    fold_values: list[float | None] = []
    for start, end in fitness.fold_bounds(len(bars), folds):
        values = [
            float(trade.r_gross)
            for trade in result.trades
            if trade.r_gross is not None
            and start <= int(trade.entry_index) <= end
        ]
        fold_values.append(float(np.mean(values)) if values else None)
    positive_folds = sum(
        1 for value in fold_values if value is not None and float(value) > 0.0
    )
    required = max(1, int(math.ceil(0.75 * folds)))
    return {
        "strategy_id": int(strategy["id"]),
        "strategy_hash": strategy.get("strategy_hash"),
        "raw_expectancy_r": float(np.mean(gross)) if gross else None,
        "raw_total_r": float(np.sum(gross)) if gross else 0.0,
        "trades": len(result.trades),
        "fold_expectancy_r": fold_values,
        "positive_folds": positive_folds,
        "folds_required": required,
        "raw_positive_folds": positive_folds >= required,
        "validation_errors": validation_errors,
    }


def _state_from_campaign(
    campaign: dict[str, Any],
    *,
    selected: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    net_rows: list[dict[str, Any]],
    validations: Mapping[tuple[int, str], dict[str, Any]],
    verified: bool,
) -> tuple[str, dict[str, Any]]:
    status = str(campaign.get("status") or "")
    if status in {"invalid", "rejected", "superseded"}:
        return "inválida", {"reasons": [campaign.get("reject_reason") or status]}
    if status in {"draft", "registered"} and int(campaign.get("n_evaluated") or 0) == 0:
        return "solo viabilidad", {"reasons": ["sin evaluaciones"]}
    raw_values = [
        float(row["raw_expectancy_r"])
        for row in raw_rows
        if row.get("raw_expectancy_r") is not None
    ]
    net_values = [
        float(row["net_expectancy_r"])
        for row in net_rows
        if row.get("net_expectancy_r") is not None
    ]
    raw_median = float(statistics.median(raw_values)) if raw_values else None
    net_median = float(statistics.median(net_values)) if net_values else None
    best_raw = max(
        (row for row in raw_rows if row.get("raw_expectancy_r") is not None),
        key=lambda row: float(row["raw_expectancy_r"]),
        default=None,
    )
    best_net = max(
        (row for row in net_rows if row.get("net_expectancy_r") is not None),
        key=lambda row: float(row["net_expectancy_r"]),
        default=None,
    )
    overfit = 0
    candidates = 0
    confirmed = 0
    pbo_values: list[float] = []
    wf_values: list[bool] = []
    for strategy in selected:
        sid = int(strategy["id"])
        pbo_value = (validations.get((sid, "pbo")) or {}).get("pbo")
        wf_value = (validations.get((sid, "wf")) or {}).get("ok")
        if pbo_value is not None:
            pbo_values.append(float(pbo_value))
        if wf_value is not None:
            wf_values.append(bool(wf_value))
        verdict = str(strategy.get("verdict") or "")
        level = int(strategy.get("level") or 1)
        if (
            (pbo_value is not None and float(pbo_value) > 0.5)
            or wf_value is False
            or verdict == "SOBREAJUSTADA"
        ):
            overfit += 1
        if (
            level >= 3
            and verdict not in {"SOBREAJUSTADA", "FRÁGIL"}
            and not (pbo_value is not None and float(pbo_value) > 0.5)
            and wf_value is not False
        ):
            candidates += 1
        for account in _strategy_accounts(validations, sid):
            if account.get("status") == "CONFIRMADA":
                confirmed += 1
    if not verified and not (confirmed or candidates or overfit):
        return "no verificable", {
            "reasons": [
                "dataset_hash del tramo registrado no coincide con la fuente viva; "
                "resultado no verificable"
            ],
        }
    positive_folds = sum(
        1 for row in raw_rows if row.get("raw_positive_folds")
    )
    folds_required = max(
        (int(row.get("folds_required") or 0) for row in raw_rows), default=0
    )
    if confirmed:
        state = "confirmada nivel 4"
    elif candidates:
        state = "candidata nivel 3"
    elif overfit:
        state = "sobreajustada"
    elif raw_median is None or raw_median <= 0.0:
        state = "sin edge bruto"
    elif net_median is None or net_median <= 0.0:
        state = "edge bruto que el coste elimina"
    else:
        state = "sin edge bruto"
    reasons: list[str] = []
    if overfit:
        reasons.append(f"{overfit} estrategias sobreajustadas (PBO>0,5 o WF fallido)")
    if raw_median is None:
        reasons.append("bruto Sin datos")
    return state, {
        "raw_median_r": raw_median,
        "raw_best_r": None if best_raw is None else float(best_raw["raw_expectancy_r"]),
        "net_median_r": net_median,
        "net_best_r": None if best_net is None else float(best_net["net_expectancy_r"]),
        "cost_r": None if best_net is None else best_net.get("cost_r"),
        "best_strategy_id": None if best_raw is None else int(best_raw["strategy_id"]),
        "best_strategy_hash": None if best_raw is None else best_raw.get("strategy_hash"),
        "strategy_total": len(selected),
        "positive_folds_count": positive_folds,
        "folds_required": folds_required,
        "overfit_count": overfit,
        "candidate_count": candidates,
        "confirmed_count": confirmed,
        "pbo": max(pbo_values) if pbo_values else None,
        "wf_ok": all(wf_values) if wf_values else None,
        "raw_rows": raw_rows,
        "reasons": reasons,
    }


def _strategy_accounts(
    validations: Mapping[tuple[int, str], dict[str, Any]], strategy_id: int
) -> list[dict[str, Any]]:
    result = []
    prefix = "firm_confirm:"
    for (sid, test), payload in validations.items():
        if sid == int(strategy_id) and str(test).startswith(prefix):
            item = dict(payload)
            item["account"] = str(test)[len(prefix) :]
            result.append(item)
    return result


def _automation_status(account, firm) -> tuple[bool, str]:
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
    return allowed, "Permitida" if allowed else "; ".join(reasons) or "Sin datos"


def _is_firm_account(account: Any) -> bool:
    return (
        not account.template
        and account.market is Market.CFD
        and account.connection_state is not ConnectionState.DISCONNECTED
    )


def _firm_accounts(registry, account_filter: str | None = None) -> list[Any]:
    """Cuentas CFD reales y conectadas; ``None`` incluye todas (p. ej. CFD-006)."""

    return [
        account
        for account in registry.accounts.values()
        if _is_firm_account(account)
        and (account_filter is None or account.id == account_filter)
    ]


def _disconnected_accounts(registry, account_filter: str | None = None) -> list[dict[str, Any]]:
    """Cuentas CFD reales sin conectar: fuera de la capa de firma."""

    return [
        {
            "id": account.id,
            "firm": account.firm,
            "program": account.program,
            "connection_state": str(account.connection_state),
            "reason": "sin conectar",
        }
        for account in registry.accounts.values()
        if (
            not account.template
            and account.market is Market.CFD
            and account.connection_state is ConnectionState.DISCONNECTED
            and (account_filter is None or account.id == account_filter)
        )
    ]


def _firm_rows(
    con: sqlite3.Connection,
    *,
    campaigns_by_id: Mapping[str, dict[str, Any]],
    strategies: list[dict[str, Any]],
    validations: Mapping[tuple[int, str], dict[str, Any]],
    account_filter: str | None,
    data_root: Path,
    costs_db: str | Path,
    allow_dukascopy: bool,
    n_paths: int,
    registry=None,
) -> list[FirmEdge]:
    registry = registry or load_registry()
    config = load_engine_config()
    accounts = _firm_accounts(registry, account_filter)
    rows: list[FirmEdge] = []
    bars_cache: dict[str, pd.DataFrame] = {}
    for account in accounts:
        firm = registry.firms.get(account.firm)
        if firm is None:
            continue
        program = firm.program(account.program)
        for strategy in strategies:
            if int(strategy.get("level") or 1) < 2:
                continue
            campaign = campaigns_by_id.get(str(strategy["campaign_id"]))
            if campaign is None:
                continue
            canonical = _canonical(str(strategy.get("instrument") or ""))
            if canonical not in account.allowed_instruments:
                continue
            sid = int(strategy["id"])
            pbo_value = (validations.get((sid, "pbo")) or {}).get("pbo")
            wf_value = (validations.get((sid, "wf")) or {}).get("ok")
            verdict = strategy.get("verdict")
            level = int(strategy.get("level") or 1)
            candidate = bool(
                level >= 3 and str(verdict) not in {"SOBREAJUSTADA", "FRÁGIL"}
            )
            automation_allowed, automation_reason = _automation_status(account, firm)
            confirm = _strategy_accounts(validations, sid)
            status = "Sin datos"
            for item in confirm:
                if item["account"] == account.id:
                    status = str(item.get("status") or "Sin datos")
                    break
            base = {
                "strategy_id": sid,
                "campaign_id": str(strategy["campaign_id"]),
                "template": str(campaign.get("template") or ""),
                "instrument": canonical,
                "timeframe": str(strategy.get("timeframe") or ""),
                "account": account.id,
                "firm": firm.id,
                "level": level,
                "verdict": verdict,
                "pbo": None if pbo_value is None else float(pbo_value),
                "wf_ok": None if wf_value is None else bool(wf_value),
                "compatible": None,
                "constraint": "Sin datos",
                "automation_allowed": automation_allowed,
                "automation_reason": automation_reason,
                "candidate": candidate,
                "confirm_status": status,
            }
            try:
                model = dsl.Strategy.model_validate(strategy["dsl"])
                check = check_strategy(
                    model, firm=firm, program=program, account=account
                )
                base["compatible"] = check.compatible
                base["constraint"] = check.label
                if not check.compatible:
                    rows.append(
                        FirmEdge(
                            **base,
                            net_expectancy_r=None,
                            cost_r=None,
                            trades=0,
                            pass_rate=None,
                            breach_rate=None,
                            reasons=["incompatible con la firma"],
                        )
                    )
                    continue
                key = str(campaign["id"])
                if key not in bars_cache:
                    bars_cache[key], _, _, _ = _load_campaign_frame(
                        campaign,
                        data_root=data_root,
                        bars_loader=None,
                        allow_dukascopy=allow_dukascopy,
                    )
                bars = bars_cache[key]
                book = costs.build_cost_book(
                    canonical,
                    accounts=[account.id],
                    mode="target",
                    session_tz=str(model.session.tz or "America/New_York"),
                    db_path=costs_db,
                    config=config,
                    cost_model_version=int(
                        (campaign.get("config") or {}).get(
                            "cost_model_version"
                        )
                        or costs.default_cost_model_version()
                    ),
                )
                setup = jobs.QueueSetup.from_campaign(campaign, bars=bars)
                if not (campaign.get("config") or {}).get("cost_model_version"):
                    setup = replace(
                        setup,
                        cost_model_version=costs.default_cost_model_version(),
                    )
                limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
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
                    _skip_validation_for_archived=bool(dsl.validate(model)),
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
                    result.trades, session_tz=limits.session_tz, point=setup.point
                )
                net = metrics.expectancy_r(applied.trades)
                cost_values = [
                    float(trade.r_cost)
                    for trade in applied.trades
                    if trade.r_cost is not None
                ]
                pass_rate = None
                breach_rate = None
                if (
                    len(applied.daily_r) >= 2
                    and float(account.risk.per_trade_risk_pct) > 0
                ):
                    from ..propfund.snapshots import _rules_from_account

                    simulation = monte_carlo(
                        _rules_from_account(account, {}),
                        pd.to_numeric(applied.daily_r, errors="coerce")
                        .dropna()
                        .to_numpy(dtype=float)
                        * float(account.risk.per_trade_risk_pct),
                        n_paths=int(n_paths),
                        horizon=60,
                        seed=42,
                        block_size=5,
                    )
                    pass_rate = float(simulation["pass_rate"])
                    breach_rate = float(simulation["breach_rate"])
                rows.append(
                    FirmEdge(
                        **base,
                        net_expectancy_r=net,
                        cost_r=(
                            float(np.median(cost_values)) if cost_values else None
                        ),
                        trades=len(applied.trades),
                        pass_rate=pass_rate,
                        breach_rate=breach_rate,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    FirmEdge(
                        **base,
                        net_expectancy_r=None,
                        cost_r=None,
                        trades=0,
                        pass_rate=None,
                        breach_rate=None,
                        reasons=[f"{type(exc).__name__}: {exc}"],
                    )
                )
    return rows


def build(
    discovery_db: str | Path = databank.DEFAULT_DISCOVERY_DB,
    *,
    costs_db: str | Path = databank.LAB_DB,
    data_root: str | Path = ROOT,
    account: str | None = None,
    allow_dukascopy: bool = True,
    n_paths: int | None = None,
    bars_loader=None,
    registry=None,
) -> dict[str, Any]:
    """Construye el mapa determinista; nunca escribe en las bases."""

    config = load_engine_config()
    registry = registry or load_registry()
    paths = int(
        n_paths if n_paths is not None else config.robustness.challenge_paths
    )
    root = Path(data_root)
    con = _ro_connect(discovery_db)
    try:
        campaigns_list = [
            _campaign_row(row)
            for row in con.execute("SELECT * FROM disc_campaigns ORDER BY created_at, id")
        ]
        strategies = [
            _strategy_row(row)
            for row in con.execute("SELECT * FROM disc_strategies ORDER BY id")
        ]
        validations = _validation_map(con)
        campaigns_by_id = {str(item["id"]): item for item in campaigns_list}
        strategies_by_campaign: dict[str, list[dict[str, Any]]] = {}
        for strategy in strategies:
            strategies_by_campaign.setdefault(
                str(strategy["campaign_id"]), []
            ).append(strategy)
        combos: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        blocked: dict[str, str] = {}
        if not allow_dukascopy:
            blocked["H4"] = DUKASCOPY_BLOCKED
            blocked["D1"] = DUKASCOPY_BLOCKED
        for campaign in campaigns_list:
            if str(campaign.get("status")) == "superseded":
                continue
            config_campaign = campaign.get("config") or {}
            template = str(campaign.get("template") or "")
            instrument = _canonical(str(campaign.get("instrument") or ""))
            timeframe = str(campaign.get("timeframe") or "").upper()
            source = str(config_campaign.get("data_source") or "broker").lower()
            if timeframe in {"H4", "D1"} and source == "dukascopy" and not allow_dukascopy:
                blocked[timeframe] = DUKASCOPY_BLOCKED
            mode = str(config_campaign.get("mode") or "ga").lower()
            all_strategies = strategies_by_campaign.get(str(campaign["id"]), [])
            if mode == "grid":
                selected = [
                    item for item in all_strategies if item.get("status") != "generated"
                ]
            else:
                frontier = set(_frontier_ids(con, str(campaign["id"])))
                selected = [item for item in all_strategies if int(item["id"]) in frontier]
                if not selected:
                    selected = [
                        item
                        for item in all_strategies
                        if item.get("status") != "generated"
                    ]
            raw_rows: list[dict[str, Any]] = []
            net_rows: list[dict[str, Any]] = []
            dataset_source = "Sin datos"
            verified: bool | None = None
            if selected and str(campaign.get("status")) not in {
                "invalid",
                "rejected",
                "superseded",
            }:
                try:
                    bars, dataset_source, verified, _live = _load_campaign_frame(
                        campaign,
                        data_root=root,
                        bars_loader=bars_loader,
                        allow_dukascopy=allow_dukascopy,
                    )
                    for strategy in selected:
                        if not verified:
                            net_metrics = _net_metrics(con, int(strategy["id"]))
                            net_rows.append(
                                {
                                    "strategy_id": int(strategy["id"]),
                                    "net_expectancy_r": (
                                        (net_metrics.get("is") or {}).get("expectancy_r")
                                        if isinstance(net_metrics, dict)
                                        else None
                                    ),
                                    "cost_r": (
                                        net_metrics.get("cost_r")
                                        if isinstance(net_metrics, dict)
                                        else None
                                    ),
                                }
                            )
                            continue
                        try:
                            raw_rows.append(
                                _raw_strategy(strategy, campaign, bars, config)
                            )
                        except Exception as exc:  # noqa: BLE001
                            raw_rows.append(
                                {
                                    "strategy_id": int(strategy["id"]),
                                    "strategy_hash": strategy.get("strategy_hash"),
                                    "raw_expectancy_r": None,
                                    "raw_total_r": None,
                                    "trades": 0,
                                    "fold_expectancy_r": [],
                                    "positive_folds": 0,
                                    "folds_required": 0,
                                    "raw_positive_folds": False,
                                    "validation_errors": [str(exc)],
                                }
                            )
                        net_metrics = _net_metrics(con, int(strategy["id"]))
                        net_value = (
                            (net_metrics.get("is") or {}).get("expectancy_r")
                            if isinstance(net_metrics, dict)
                            else None
                        )
                        net_rows.append(
                            {
                                "strategy_id": int(strategy["id"]),
                                "net_expectancy_r": net_value,
                                "cost_r": net_metrics.get("cost_r")
                                if isinstance(net_metrics, dict)
                                else None,
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    dataset_source = "Sin datos"
                    verified = False
                    blocked[timeframe] = str(exc)
                if dataset_source == "fuente viva" and not verified:
                    dataset_source = "fuente viva (no verificable)"
            state, data = _state_from_campaign(
                campaign,
                selected=selected,
                raw_rows=raw_rows,
                net_rows=net_rows,
                validations=validations,
                verified=bool(verified) if verified is not None else False,
            )
            if not selected and str(campaign.get("status")) in {"draft", "registered"}:
                state, data = "solo viabilidad", {"reasons": ["sin evaluaciones"]}
            key = (template, instrument, timeframe, source)
            existing = combos.get(key)
            row = ComboEdge(
                template=template,
                template_version=template_version(template),
                instrument=instrument,
                timeframe=timeframe,
                source=source,
                state=state,
                campaigns=[str(campaign["id"])],
                campaign_status=str(campaign.get("status")),
                raw_median_r=data.get("raw_median_r"),
                raw_best_r=data.get("raw_best_r"),
                net_median_r=data.get("net_median_r"),
                net_best_r=data.get("net_best_r"),
                cost_r=data.get("cost_r"),
                strategy_total=int(data.get("strategy_total") or len(selected)),
                positive_folds_count=int(data.get("positive_folds_count") or 0),
                folds_required=int(data.get("folds_required") or 0),
                overfit_count=int(data.get("overfit_count") or 0),
                candidate_count=int(data.get("candidate_count") or 0),
                confirmed_count=int(data.get("confirmed_count") or 0),
                pbo=data.get("pbo"),
                wf_ok=data.get("wf_ok"),
                best_strategy_id=data.get("best_strategy_id"),
                best_strategy_hash=data.get("best_strategy_hash"),
                dataset_source=dataset_source,
                dataset_verified=verified,
                reasons=list(data.get("reasons") or []),
            )
            if existing is not None:
                existing["campaigns"] = sorted(
                    set(existing.get("campaigns") or []) | {str(campaign["id"])}
                )
                if existing["state"] in {"inválida", "sin probar"}:
                    combos[key] = row.as_dict()
                continue
            combos[key] = row.as_dict()
        firms = _firm_rows(
            con,
            campaigns_by_id=campaigns_by_id,
            strategies=strategies,
            validations=validations,
            account_filter=account,
            data_root=root,
            costs_db=costs_db,
            allow_dukascopy=allow_dukascopy,
            n_paths=paths,
            registry=registry,
        )
        disconnected = _disconnected_accounts(registry, account)
    finally:
        con.close()
    rows = sorted(
        combos.values(),
        key=lambda item: (
            item["instrument"],
            item["timeframe"],
            item["template"],
            item["source"],
        ),
    )
    summary: dict[str, int] = {state: 0 for state in STATES}
    for row in rows:
        summary[row["state"]] = summary.get(row["state"], 0) + 1
    return {
        "combos": rows,
        "firms": [row.as_dict() for row in firms],
        "disconnected_accounts": disconnected,
        "blocked": [
            {"timeframe": timeframe, "reason": reason}
            for timeframe, reason in sorted(blocked.items())
        ],
        "summary": summary,
        "n_combos": len(rows),
        "n_firms": len(firms),
        "source": "discovery.db ro",
    }


def group_by(report: Mapping[str, Any], by: str) -> list[dict[str, Any]]:
    rows = list(report.get("combos") or [])
    if by == "instrumento":
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(f"{row['instrument']} {row['timeframe']}", []).append(row)
        return [
            {"group": key, "rows": value}
            for key, value in sorted(groups.items())
        ]
    if by == "cuenta":
        accounts: dict[str, list[dict[str, Any]]] = {}
        for row in report.get("firms") or []:
            accounts.setdefault(str(row["account"]), []).append(row)
        return [
            {"group": key, "rows": value}
            for key, value in sorted(accounts.items())
        ]
    groups = {}
    for row in rows:
        groups.setdefault(str(row["template"]), []).append(row)
    return [{"group": key, "rows": value} for key, value in sorted(groups.items())]


def render_markdown(report: Mapping[str, Any], *, by: str = "hipotesis") -> str:
    lines = [
        "# Edge Map · TradingLab 2.0",
        "",
        "Solo lectura del databank. Sin OOS-2, sin campañas y sin DSR nuevo.",
        "",
        "## Resumen",
        "",
    ]
    for state, count in (report.get("summary") or {}).items():
        lines.append(f"- {state}: {count}")
    if report.get("blocked"):
        for item in report["blocked"]:
            lines.append(f"- {item['timeframe']}: {item['reason']}")
    lines.extend(["", "## Mapa", ""])
    if by == "cuenta":
        lines.append(
            "| Cuenta | Firma | Estrategia | Nivel | Veredicto | PBO | WF | Neto R | "
            "Cost_R | Ops | P(pasar) | Automatización | Candidata | Confirmación |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for row in report.get("firms") or []:
            lines.append(
                "| "
                + " | ".join(
                    _cell(value)
                    for value in (
                        row["account"],
                        row["firm"],
                        row["strategy_id"],
                        row["level"],
                        row["verdict"],
                        row["pbo"],
                        row["wf_ok"],
                        row["net_expectancy_r"],
                        row["cost_r"],
                        row["trades"],
                        row["pass_rate"],
                        row["automation_allowed"],
                        row["candidate"],
                        row["confirm_status"],
                    )
                )
                + " |"
            )
    else:
        lines.append(
            "| Hipótesis | Instrumento | TF | Fuente | Estado | Bruto mediana | "
            "Bruto mejor | Neto mediana | Cost_R | Ops+ | Candidatas | Confirmadas |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for row in report.get("combos") or []:
            lines.append(
                "| "
                + " | ".join(
                    _cell(value)
                    for value in (
                        row["template"],
                        row["instrument"],
                        row["timeframe"],
                        row["source"],
                        row["state"],
                        row["raw_median_r"],
                        row["raw_best_r"],
                        row["net_median_r"],
                        row.get("cost_r"),
                        (
                            "Sin datos"
                            if row["raw_median_r"] is None
                            else f"{row['positive_folds_count']}/{row['strategy_total']}"
                        ),
                        row["candidate_count"],
                        row["confirmed_count"],
                    )
                )
                + " |"
            )
    lines.append("")
    if report.get("disconnected_accounts"):
        lines.append("## Cuentas sin conectar")
        lines.append("")
        for item in report["disconnected_accounts"]:
            lines.append(
                f"- {item['id']} · {item['firm']} · {item['program']} · "
                f"{item['connection_state']} · fuera de la capa de firma"
            )
        lines.append("")
    lines.append(
        "La etiqueta usa la mediana de la rejilla (grid) o de la frontera de rango 1 (GA). "
        "El mejor valor es informativo y no decide."
    )
    return "\n".join(lines) + "\n"


def _cell(value: Any) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("|", "/")


def export(report: Mapping[str, Any], *, by: str = "hipotesis", out_dir=None) -> dict[str, str]:
    target = Path(out_dir) if out_dir else REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "edge_map.json"
    md_path = target / "edge_map.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report, by=by), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _slice_default_is(frame: pd.DataFrame, config) -> pd.DataFrame:
    start, end = config.data_quality.default_segments["is"]
    begin = pd.Timestamp(start, tz="UTC")
    finish = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(
        nanoseconds=1
    )
    return frame[(frame.index >= begin) & (frame.index <= finish)]


def _trade_cost_r(trades) -> float | None:
    values = [
        float(trade.r_cost)
        for trade in trades
        if trade.r_cost is not None and np.isfinite(float(trade.r_cost))
    ]
    return float(np.median(values)) if values else None


def template_cost_r(
    account_id: str,
    symbol: str,
    timeframe: str,
    **kwargs,
) -> dict[str, Any]:
    """Cost_R compartido con onboarding-mtf (una sola definición)."""
    from ..propfund.onboarding_mtf import cost_r_for

    return cost_r_for(account_id, symbol, timeframe, **kwargs)


def _cost_version(version: int | None) -> int:
    """Versión explícita o la de evaluaciones nuevas."""

    return int(version or costs.default_cost_model_version())


def _base_viability(
    template: str,
    symbol: str,
    timeframe: str,
    source: str,
    account,
    firm,
    program,
    *,
    frame: pd.DataFrame,
    costs_db: str | Path,
    config,
    cost_model_version: int | None = None,
) -> dict[str, Any]:
    model_dict = genetic.configured_template(
        template,
        instrument=symbol,
        timeframe=timeframe,
        session=campaigns.template_session(template, symbol),
    )
    model = dsl.Strategy.model_validate(model_dict)
    check = check_strategy(model, firm=firm, program=program, account=account)
    if not check.compatible:
        return {
            "status": "incompatible",
            "reasons": [check.label],
        }
    book = costs.build_cost_book(
        symbol,
        accounts=[account.id],
        mode="target",
        session_tz=str(model.session.tz or "America/New_York"),
        db_path=costs_db,
        config=config,
        cost_model_version=_cost_version(cost_model_version),
    )
    setup = jobs.QueueSetup(
        instrument=symbol,
        timeframe=timeframe,
        account=account.id,
        firm=firm.id,
        use_p75=True,
        cost_accounts=(account.id,),
        cost_mode="target",
        legacy_cost=False,
        cost_model_version=_cost_version(cost_model_version),
        session_tz=str(model.session.tz or "America/New_York"),
        session_start=model.session.start,
        session_end=model.session.end,
        flat_at=model.session.flat_at,
        weekdays=(0, 1, 2, 3, 4),
    ).validated()
    limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
    trailing = model.exit.trailing or {}
    prepared = fastbt.prepare(
        frame,
        book,
        atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
        sessions=(limits,),
    )
    signals = compiler.compile(model, frame)
    result = fastbt.run(
        signals,
        frame,
        specs.exit_spec_from_strategy(model),
        book,
        limits,
        prepared=prepared,
        collect_metrics=False,
    )
    applied = book.apply(result.trades, session_tz=limits.session_tz, point=0.01)
    cost_r = _trade_cost_r(applied.trades)
    screening = template_cost_r(
        account.id,
        symbol,
        timeframe,
        config=config,
        max_cost_r=float(config.fitness.cost_r_max),
    )
    validation = config.validation.for_timeframe(timeframe)
    fold_trades = []
    for start, end in fitness.fold_bounds(len(frame), int(validation.folds)):
        fold_trades.append(
            sum(
                1
                for trade in applied.trades
                if start <= int(trade.entry_index) <= end
            )
        )
    feasible = (
        len(applied.trades) >= int(validation.min_trades_is)
        and all(count >= int(validation.min_trades_fold) for count in fold_trades)
        and cost_r is not None
        and float(cost_r) <= float(config.fitness.cost_r_max)
    )
    return {
        "status": "ok",
        "feasible": feasible,
        "constraint": check.label,
        "trades_is": len(applied.trades),
        "fold_trades": fold_trades,
        "cost_r": cost_r,
        "cost_r_screening": screening["cost_r"],
        "reasons": [] if feasible else ["no cumple mínimos de viabilidad"],
    }


def suggest(
    account: str | None = None,
    *,
    discovery_db: str | Path = databank.DEFAULT_DISCOVERY_DB,
    costs_db: str | Path = databank.LAB_DB,
    data_root: str | Path = ROOT,
    allow_dukascopy: bool = True,
    bars_loader=None,
    limit: int | None = None,
    registry=None,
    cost_model_version: int | None = None,
) -> dict[str, Any]:
    """Combinaciones no probadas y viables. Etiqueta siempre ``por probar``."""

    config = load_engine_config()
    registry = registry or load_registry()
    root = Path(data_root)
    if Path(discovery_db).exists():
        con = _ro_connect(discovery_db)
        try:
            tested = _tested_keys(con)
        finally:
            con.close()
    else:
        tested = set()
    if account:
        selected_accounts = [
            item
            for item in registry.accounts.values()
            if item.id == str(account).upper() and not item.template
        ]
        if not selected_accounts:
            raise EdgeMapError(f"cuenta no registrada o plantilla: {account}")
    else:
        selected_accounts = [
            item
            for item in registry.accounts.values()
            if not item.template and item.market is Market.CFD
        ]
    templates = sorted(path.stem for path in genetic.TEMPLATE_DIR.glob("*.yaml"))
    rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    blocked: dict[str, str] = {}
    for account_item in selected_accounts:
        firm = registry.firms.get(account_item.firm)
        if firm is None:
            continue
        program = firm.program(account_item.program)
        for template in templates:
            try:
                timeframes = genetic.template_timeframes(template)
            except Exception:
                continue
            for timeframe in timeframes:
                source = "dukascopy" if timeframe in {"H4", "D1"} else "broker"
                if timeframe in {"H4", "D1"} and not allow_dukascopy:
                    blocked[timeframe] = DUKASCOPY_BLOCKED
                    continue
                for symbol in account_item.allowed_instruments:
                    canonical = _canonical(symbol)
                    key = (template, canonical, timeframe, source)
                    if key in tested or (
                        template,
                        canonical,
                        timeframe,
                        "*",
                    ) in tested:
                        continue
                    existing = rows.get(key)
                    if existing is not None and account_item.id in existing["accounts"]:
                        continue
                    try:
                        if bars_loader is not None:
                            frame = bars_loader(symbol, timeframe)
                        else:
                            frame = data_sources.load_source(
                                symbol,
                                timeframe,
                                source=source,
                                root=root,
                            ).frame
                        frame = _slice_default_is(frame, config)
                        if frame.empty:
                            raise EdgeMapError("Sin datos en IS")
                        result = _base_viability(
                            template,
                            canonical,
                            timeframe,
                            source,
                            account_item,
                            firm,
                            program,
                            frame=frame,
                            costs_db=costs_db,
                            config=config,
                            cost_model_version=cost_model_version,
                        )
                    except Exception as exc:  # noqa: BLE001
                        if existing is None:
                            rows[key] = {
                                "template": template,
                                "instrument": canonical,
                                "timeframe": timeframe,
                                "source": source,
                                "session": "",
                                "status": "sin_datos",
                                "label": "por probar",
                                "accounts": [],
                                "trades_is": None,
                                "fold_trades": [],
                                "cost_r": None,
                                "cost_r_screening": None,
                                "feasible": False,
                                "reasons": [f"{type(exc).__name__}: {exc}"],
                            }
                        continue
                    if not result.get("feasible"):
                        continue
                    if existing is None or existing.get("status") != "ok":
                        session = campaigns.template_session(template, symbol)
                        rows[key] = {
                            "template": template,
                            "instrument": canonical,
                            "timeframe": timeframe,
                            "source": source,
                            "session": f"{session['start']}-{session['end']}",
                            "status": "ok",
                            "label": "por probar",
                            "accounts": [account_item.id],
                            "compatible": True,
                            "constraint": result.get("constraint") or "compatible",
                            "trades_is": int(result["trades_is"]),
                            "fold_trades": list(result["fold_trades"]),
                            "cost_r": result["cost_r"],
                            "cost_r_screening": result.get("cost_r_screening"),
                            "feasible": True,
                            "reasons": [],
                        }
                    else:
                        existing["accounts"].append(account_item.id)
                        existing["accounts"] = sorted(set(existing["accounts"]))
    output = sorted(
        (row for row in rows.values() if row.get("status") == "ok"),
        key=lambda item: (
            item["template"],
            item["instrument"],
            item["timeframe"],
            item["source"],
        ),
    )
    if limit is not None:
        output = output[: int(limit)]
    return {
        "rows": output,
        "templates": templates,
        "blocked": [
            {"timeframe": timeframe, "reason": reason}
            for timeframe, reason in sorted(blocked.items())
        ],
        "n_rows": len(output),
        "n_ok": len(output),
        "cost_mode": "target",
        "cost_account": account or "multi",
        "label": "por probar",
    }


__all__ = [
    "ComboEdge",
    "DUKASCOPY_BLOCKED",
    "EdgeMapError",
    "FirmEdge",
    "REPORT_DIR",
    "STATES",
    "build",
    "export",
    "group_by",
    "render_markdown",
    "suggest",
    "template_cost_r",
    "template_version",
]
