"""Cola de trabajos del Discovery Lab (``disc_jobs`` en ``data/discovery.db``).

Diseño:

* **Un solo escritor**: los workers no abren SQLite. Compilan y ejecutan la
  estrategia y devuelven el resultado al proceso principal, que escribe en
  lotes con una transacción por lote.
* **Preparación por worker**: el initializer carga las barras del snapshot de
  la campaña (o ``discovery.data_sources``/sintéticas si no hay snapshot),
  corta el tramo, construye el coste
  con ``propfund.costs`` y llama a ``fastbt.prepare``. Cada job solo lleva el
  JSON de la estrategia.
* **Reanudación**: los ``running`` huérfanos vuelven a ``queued`` al arrancar.
  Un job terminado no se repite; uno pendiente no se pierde.
* **Límites**: ``workers`` se recorta a ``engine.workers``. Sin ``psutil`` no
  se fuerza prioridad (fallback avisado), nunca se añade la dependencia.
"""

from __future__ import annotations

import json
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ..db import connect
from ..propfund.costs import load_profile
from . import campaigns, databank, dsl, fastbt
from .compiler import compile as compile_strategy
from .config import load_engine_config
from .data_sources import load_source
from .indicator_cache import IndicatorCache
from .specs import exit_spec_from_strategy, run_limits_from_strategy

DEFAULT_SEGMENT = "is_full"
_QUEUE_STATES = ("queued", "running", "done", "failed", "cancelled")
_PRIORITY_WARNED = False
_WORKER: dict[str, Any] = {}


class QueueError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class QueueSetup:
    """Configuración de campaña que el worker prepara una sola vez."""

    instrument: str = "US100"
    timeframe: str = "M5"
    start: str | None = None
    end: str | None = None
    account: str = "CFD-001"
    firm: str | None = "ftmo"
    use_p75: bool = True
    cost_accounts: tuple[str, ...] = ()
    cost_mode: str = "target"
    legacy_cost: bool = True
    cost_model_version: int = 1
    spread_model: str = "p75_static"
    session_tz: str = "America/New_York"
    session_start: str = "09:35"
    session_end: str = "11:30"
    flat_at: str | None = "15:45"
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    stop_n: int = 14
    trail_n: int = 14
    template: str | None = None
    seed: int = 0
    point: float = 0.01
    data_source: str = "broker"
    cache_limit_bytes: int = 0
    campaign_id: str = ""
    drift_simulations: int = 0
    drift_percentile_min: float = 0.0
    approved: bool = False
    bars: pd.DataFrame | None = None  # solo tests/benchmark sintéticos

    def as_dict(self, *, include_bars: bool = False) -> dict[str, Any]:
        data = {item.name: getattr(self, item.name) for item in fields(self)}
        if not include_bars:
            data.pop("bars", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueSetup":
        allowed = {field for field in cls.__dataclass_fields__}
        payload = {key: value for key, value in dict(data or {}).items() if key in allowed}
        if "weekdays" in payload:
            payload["weekdays"] = tuple(int(day) for day in payload["weekdays"])
        return cls(**payload)

    @classmethod
    def from_campaign(
        cls, campaign: dict[str, Any], *, bars: pd.DataFrame | None = None
    ) -> "QueueSetup":
        """Construye el setup desde ``disc_campaigns``; sin fechas libres."""

        config = campaign.get("config") or {}
        cost = config.get("cost") or {}
        session = config.get("session") or {}
        limits = config.get("limits") or {}
        controls = config.get("controls") or {}
        random_control = controls.get("test_vs_random_direction") or {}
        configured_accounts = tuple(
            str(account).strip().upper()
            for account in (cost.get("accounts") or ())
            if str(account).strip()
        )
        legacy_cost = not bool(configured_accounts)
        if legacy_cost:
            configured_accounts = (str(cost.get("account") or "CFD-001").upper(),)
            configured_mode = "target"
        else:
            configured_mode = str(cost.get("mode") or "best").lower()
        return cls(
            instrument=campaign.get("instrument") or "",
            timeframe=campaign.get("timeframe") or "",
            start=campaign.get("is_start"),
            end=campaign.get("is_end"),
            account=str(cost.get("account") or configured_accounts[0]),
            firm=cost.get("firm", "ftmo"),
            use_p75=bool(cost.get("use_p75", True)),
            cost_accounts=configured_accounts,
            cost_mode=configured_mode,
            legacy_cost=legacy_cost,
            cost_model_version=int(config.get("cost_model_version", 1) or 1),
            spread_model=str(cost.get("spread_model") or "p75_static"),
            session_tz=str(session.get("tz") or "America/New_York"),
            session_start=str(session.get("start") or "09:35"),
            session_end=str(session.get("end") or "11:30"),
            flat_at=session.get("flat_at", "15:45"),
            weekdays=tuple(int(day) for day in limits.get("weekdays", (0, 1, 2, 3, 4))),
            stop_n=int(limits.get("stop_n", 14)),
            trail_n=int(limits.get("trail_n", 14)),
            template=campaign.get("template") or config.get("template"),
            seed=int(config.get("seed", 0)),
            point=float(config.get("point", 0.01)),
            data_source=str(config.get("data_source") or "broker"),
            cache_limit_bytes=int(config.get("cache_limit_bytes", 0)),
            campaign_id=str(campaign.get("id") or ""),
            drift_simulations=int(random_control.get("simulations") or 0),
            drift_percentile_min=float(
                random_control.get("percentile_min") or 0.0
            ),
            approved=bool(campaign.get("approved_at"))
            or str(campaign.get("status") or "").lower() == "synthetic",
            bars=bars,
        ).validated()

    def validated(self) -> "QueueSetup":
        if not str(self.instrument or "").strip():
            raise QueueError("el setup necesita instrument")
        if not str(self.timeframe or "").strip():
            raise QueueError("el setup necesita timeframe")
        if self.data_source not in {"broker", "dukascopy", "databento"}:
            raise QueueError(f"fuente no soportada: {self.data_source!r}")
        if not str(self.account or "").strip():
            raise QueueError("el setup necesita account")
        if self.session_start == self.session_end:
            raise QueueError("la sesión no puede tener start == end (24 h no soportado)")
        if self.cost_mode not in {"worst", "best", "target"}:
            raise QueueError(f"cost_mode desconocido: {self.cost_mode}")
        if not self.cost_accounts:
            raise QueueError("Sin datos: cost_accounts vacío")
        if self.cost_mode == "target" and len(self.cost_accounts) != 1:
            raise QueueError("cost_mode target exige exactamente una cuenta")
        if int(self.cost_model_version) not in {1, 2}:
            raise QueueError(
                f"cost_model_version inválida: {self.cost_model_version}"
            )
        if self.spread_model not in {
            "p75_static",
            "hourly_median",
            "historical_scaled",
        }:
            raise QueueError(f"spread_model inválido: {self.spread_model!r}")
        if int(self.drift_simulations) < 0:
            raise QueueError("drift_simulations no puede ser negativo")
        if int(self.drift_simulations) > 0 and not (
            0.0 < float(self.drift_percentile_min) <= 100.0
        ):
            raise QueueError("drift_percentile_min debe estar en (0, 100]")
        return replace(
            self,
            instrument=str(self.instrument).upper(),
            timeframe=str(self.timeframe).upper(),
            weekdays=tuple(int(day) for day in self.weekdays),
            cost_accounts=tuple(str(account).upper() for account in self.cost_accounts),
            cost_mode=str(self.cost_mode).lower(),
        )

    def cost_profile(self) -> str:
        if self.legacy_cost:
            return f"{self.account}:{self.instrument}"
        return f"{self.cost_mode}:{'+'.join(self.cost_accounts)}:{self.instrument}"


def _set_priority() -> str:
    """Baja prioridad solo si ``psutil`` ya está instalado (no se añade)."""

    global _PRIORITY_WARNED
    try:
        import psutil  # noqa: PLC0415 - opcional, no dependencia
    except ImportError:
        if not _PRIORITY_WARNED:
            warnings.warn(
                "psutil no está instalado: la cola corre sin prioridad below normal",
                RuntimeWarning,
                stacklevel=2,
            )
            _PRIORITY_WARNED = True
        return "sin psutil"
    try:
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        return "below_normal"
    except Exception:  # noqa: BLE001 - Windows puede rechazarlo
        return "sin prioridad"


def _connection(db_path: str | Path, con: Any | None):
    from contextlib import nullcontext

    if con is not None:
        return nullcontext(con)
    return connect(db_path)


def _target(db_path: str | Path | None, con: Any | None) -> Path:
    if con is None:
        return databank.init_databank(db_path)
    return Path(db_path) if db_path else databank.DEFAULT_DISCOVERY_DB


def enqueue(
    campaign_id: str,
    strategies: Iterable[dict[str, Any] | dsl.Strategy],
    *,
    kind: str = "backtest_is",
    db_path: str | Path | None = None,
    con: Any | None = None,
) -> int:
    """Encola estrategias validas; dedupe por hash dentro de la campana."""

    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise QueueError("la cola necesita campaign_id")
    target = _target(db_path, con)
    added = 0
    with _connection(target, con) as opened:
        for strategy in strategies:
            errors = dsl.validate(strategy)
            if errors:
                raise QueueError("estrategia inválida: " + "; ".join(errors))
            payload = dsl.canonical_json(strategy)
            digest = dsl.strategy_hash(strategy)
            cursor = opened.execute(
                "INSERT OR IGNORE INTO disc_jobs"
                "(campaign_id, kind, payload_json, strategy_hash, state, attempts) "
                "VALUES(?,?,?,?,'queued',0)",
                (identifier, str(kind), payload, digest),
            )
            added += int(cursor.rowcount or 0)
    return added


def _claim(target: Path, campaign_id: str, limit: int) -> list[dict[str, Any]]:
    claimed: list[dict[str, Any]] = []
    with connect(target) as con:
        rows = con.execute(
            "SELECT id, payload_json, strategy_hash, kind FROM disc_jobs"
            " WHERE campaign_id = ? AND state = 'queued' ORDER BY id LIMIT ?",
            (campaign_id, int(limit)),
        ).fetchall()
        for row in rows:
            cursor = con.execute(
                "UPDATE disc_jobs SET state = 'running', attempts = attempts + 1,"
                " started_at = ? WHERE id = ? AND state = 'queued'",
                (_now(), row["id"]),
            )
            if cursor.rowcount:
                claimed.append(dict(row))
    return claimed


def _counts(target: Path, campaign_id: str) -> dict[str, int]:
    with connect(target) as con:
        rows = con.execute(
            "SELECT state, COUNT(*) AS n FROM disc_jobs"
            " WHERE campaign_id = ? GROUP BY state",
            (campaign_id,),
        ).fetchall()
    counts = {state: 0 for state in _QUEUE_STATES}
    for row in rows:
        counts[str(row["state"])] = int(row["n"])
    return counts


def _campaign_cancelled(target: Path, campaign_id: str) -> bool:
    with connect(target) as con:
        row = con.execute(
            "SELECT status FROM disc_campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
    return bool(row and str(row["status"]).lower() == "cancelled")


def cancel_campaign(
    campaign_id: str,
    *,
    db_path: str | Path | None = None,
    con: Any | None = None,
) -> int:
    """Cancela los ``queued``. Los ``running`` terminan y se registran."""

    target = _target(db_path, con)
    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise QueueError("la cancelación necesita campaign_id")
    with _connection(target, con) as opened:
        cursor = opened.execute(
            "UPDATE disc_jobs SET state = 'cancelled', finished_at = ?"
            " WHERE campaign_id = ? AND state = 'queued'",
            (_now(), identifier),
        )
        opened.execute(
            "UPDATE disc_campaigns SET status = 'cancelled'"
            " WHERE id = ? AND status IN ('registered', 'running', 'done')",
            (identifier,),
        )
        return int(cursor.rowcount or 0)


def _slice_bars(
    bars: pd.DataFrame, start: str | None, end: str | None
) -> pd.DataFrame:
    mask = np.ones(len(bars), dtype=bool)
    if start:
        mask &= bars.index >= pd.Timestamp(start, tz="UTC")
    if end:
        mask &= bars.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    sliced = bars.loc[mask]
    if len(sliced) == 0:
        raise QueueError(
            f"Sin datos: el tramo {start or '-'} .. {end or '-'} no tiene barras"
        )
    return sliced


def _init_worker(payload: dict[str, Any]) -> None:
    global _WORKER
    started = time.perf_counter()
    setup = QueueSetup.from_dict(payload).validated()
    if setup.bars is not None:
        bars = setup.bars.copy()
    else:
        loaded = load_source(
            setup.instrument,
            setup.timeframe,
            source=setup.data_source,
        )
        bars = loaded.frame
    bars = _slice_bars(bars, setup.start, setup.end)
    if len(bars) < 100:
        raise QueueError("Sin datos: menos de 100 barras en el tramo IS")
    if setup.legacy_cost:
        profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
        cost = fastbt.cost_from_profile(profile, use_p75=setup.use_p75)
        book = None
    else:
        from .costs import build_cost_book_for_setup

        book = build_cost_book_for_setup(setup)
        cost = book
    limits = fastbt.RunLimits(
        session_tz=setup.session_tz,
        session_start=setup.session_start,
        session_end=setup.session_end,
        flat_at=setup.flat_at,
        weekdays=setup.weekdays,
    )
    prepared = fastbt.prepare(
        bars,
        cost,
        atr_windows=(setup.stop_n, setup.trail_n),
        sessions=(limits,),
    )
    cache = IndicatorCache(setup.cache_limit_bytes, dataset_token=id(bars))
    _WORKER = {
        "setup": setup,
        "bars": bars,
        "cost": cost,
        "cost_book": book,
        "prepared": prepared,
        "cache": cache,
        "prep_s": time.perf_counter() - started,
    }


def strategy_gate(strategy: dict[str, Any], setup: QueueSetup) -> str | None:
    """Motivo por el que el worker rechazaría la estrategia, o ``None``.

    Es la misma puerta que aplica ``_evaluate_job`` antes de preparar barras:
    AST válido, instrumento y timeframe de la campaña.
    """

    try:
        errors = dsl.validate(strategy)
        if errors:
            return "estrategia inválida: " + "; ".join(errors)
        model = dsl.Strategy.model_validate(strategy)
    except Exception as exc:  # noqa: BLE001 - se informa tal cual
        return f"{type(exc).__name__}: {exc}"
    if model.instrument.upper() != setup.instrument.upper():
        return f"instrumento {model.instrument} != {setup.instrument} de la campaña"
    if model.timeframe.upper() != setup.timeframe.upper():
        return f"timeframe {model.timeframe} != {setup.timeframe} de la campaña"
    return None


def _evaluate_job(task: tuple[int, str, str]) -> dict[str, Any]:
    job_id, payload_json, kind = task
    state = _WORKER
    if not state:
        return {"job_id": job_id, "error": "worker sin preparación", "metrics": None}
    try:
        strategy = json.loads(payload_json)
        setup: QueueSetup = state["setup"]
        reason = strategy_gate(strategy, setup)
        if reason:
            raise QueueError(reason)
        model = dsl.Strategy.model_validate(strategy)
        cache = state.get("cache")
        if kind == "fitness":
            from .fitness import evaluate as fitness_evaluate

            fit = fitness_evaluate(
                model,
                state["bars"],
                state["cost"],
                setup,
                state["prepared"],
                cache=cache,
                cost_book=state.get("cost_book"),
                campaign_id=setup.campaign_id,
                drift_simulations=setup.drift_simulations,
                drift_percentile_min=setup.drift_percentile_min,
                approved=setup.approved,
            )
            series = fit["daily_returns"]
            return {
                "job_id": job_id,
                "strategy_hash": dsl.strategy_hash(model),
                "metrics": fit["metrics"],
                "trades": fit["trades_count"],
                "returns": series.to_numpy(dtype=float).tolist(),
                "return_dates": [stamp.isoformat() for stamp in series.index],
                "error": None,
                "fitness": fit["fitness"],
                "feasible": fit["feasible"],
                "violations": fit["violations"],
                "drift": fit.get("drift"),
                "cost_r": fit["cost_r"],
                "complexity": fit["complexity"],
                "folds": fit["folds"],
                "backend": fastbt.backend(),
                "prep_s": float(state.get("prep_s", 0.0)),
                "cache": cache.stats() if cache is not None else {},
            }
        signals = compile_strategy(model, state["bars"], cache=cache)
        result = fastbt.run(
            signals,
            state["bars"],
            exit_spec_from_strategy(model),
            state["cost"],
            run_limits_from_strategy(model, setup),
            prepared=state["prepared"],
        )
        book = state.get("cost_book")
        if book is not None:
            from .costs import apply_result

            applied, metrics = apply_result(
                book,
                result,
                session_tz=setup.session_tz,
                point=setup.point,
                max_cost_r=float(load_engine_config().fitness.cost_r_max),
            )
            returns = applied.daily_r
            return {
                "job_id": job_id,
                "strategy_hash": dsl.strategy_hash(model),
                "metrics": metrics,
                "trades": len(applied.trades),
                "returns": returns.to_numpy(dtype=float).tolist(),
                "return_dates": [stamp.isoformat() for stamp in returns.index],
                "error": None,
                "backend": result.backend,
                "prep_s": float(state.get("prep_s", 0.0)),
                "cache": cache.stats() if cache is not None else {},
            }
        returns = result.daily_r
        return {
            "job_id": job_id,
            "strategy_hash": dsl.strategy_hash(model),
            "metrics": result.metrics,
            "trades": len(result.trades),
            "returns": returns.to_numpy(dtype=float).tolist(),
            "return_dates": [stamp.isoformat() for stamp in returns.index],
            "error": None,
            "backend": result.backend,
            "prep_s": float(state.get("prep_s", 0.0)),
            "cache": cache.stats() if cache is not None else {},
        }
    except Exception as exc:  # noqa: BLE001 - el error se guarda por job
        return {
            "job_id": job_id,
            "error": f"{type(exc).__name__}: {exc}",
            "metrics": None,
            "trades": 0,
            "returns": [],
            "return_dates": [],
            "backend": fastbt.backend(),
            "prep_s": float(state.get("prep_s", 0.0)),
        }


def _flush(
    target: Path,
    campaign_id: str,
    results: list[dict[str, Any]],
    jobs: dict[int, dict[str, Any]],
    setup: QueueSetup,
) -> None:
    with connect(target) as con:
        for result in results:
            con.execute("SAVEPOINT disc_job")
            job = jobs[int(result["job_id"])]
            try:
                if result.get("error"):
                    raise QueueError(str(result["error"]))
                strategy = json.loads(job["payload_json"])
                strategy_id = databank.add_strategy(
                    campaign_id,
                    strategy,
                    family=setup.template,
                    db_path=target,
                    con=con,
                )
                databank.add_evaluation(
                    strategy_id,
                    segment=(
                        "fitness_is"
                        if str(job.get("kind")) == "fitness"
                        else DEFAULT_SEGMENT
                    ),
                    cost_profile=setup.cost_profile(),
                    metrics=result.get("metrics"),
                    trades_count=result.get("trades"),
                    returns=result.get("returns") or (),
                    db_path=target,
                    con=con,
                )
                databank.set_status(
                    strategy_id, "evaluated", db_path=target, con=con
                )
                con.execute(
                    "UPDATE disc_jobs SET state = 'done', error = NULL,"
                    " finished_at = ? WHERE id = ?",
                    (_now(), int(result["job_id"])),
                )
                con.execute("RELEASE SAVEPOINT disc_job")
            except Exception as exc:  # noqa: BLE001 - un job malo no tumba el lote
                con.execute("ROLLBACK TO SAVEPOINT disc_job")
                con.execute("RELEASE SAVEPOINT disc_job")
                con.execute(
                    "UPDATE disc_jobs SET state = 'failed', error = ?,"
                    " finished_at = ? WHERE id = ?",
                    (f"{type(exc).__name__}: {exc}"[:2000], _now(), int(result["job_id"])),
                )


def _cache_limit(workers: int, override: int | None) -> int:
    if override is not None:
        return max(0, int(override))
    engine = load_engine_config()
    return int(engine.ram_limit_gb * 1024 ** 3 / max(1, int(workers)))


class BatchEvaluator:
    """Pool persistente con preparación y caché de indicadores por worker."""

    def __init__(
        self,
        setup: QueueSetup,
        frame: pd.DataFrame,
        *,
        workers: int = 1,
        cache_limit_bytes: int | None = None,
    ) -> None:
        configured = int(load_engine_config().workers)
        self.workers = max(1, min(int(workers), configured))
        self.setup = replace(
            setup,
            bars=frame,
            cache_limit_bytes=_cache_limit(self.workers, cache_limit_bytes),
        )
        self.pool = ProcessPoolExecutor(
            max_workers=self.workers,
            initializer=_init_worker,
            initargs=(self.setup.as_dict(include_bars=True),),
        )
        self._next = 0

    def evaluate(
        self, strategies: Iterable[dict[str, Any]], kind: str = "fitness"
    ) -> list[dict[str, Any]]:
        futures: dict[Any, int] = {}
        for strategy in strategies:
            payload = json.dumps(strategy, sort_keys=True, ensure_ascii=False)
            self._next += 1
            task_id = self._next
            futures[
                self.pool.submit(_evaluate_job, (task_id, payload, kind))
            ] = task_id
        results: dict[int, dict[str, Any]] = {}
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                results[task_id] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[task_id] = {
                    "job_id": task_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "metrics": None,
                    "trades": 0,
                    "returns": [],
                }
        return [results[key] for key in sorted(results)]

    def close(self) -> None:
        self.pool.shutdown(wait=True)

    def __enter__(self) -> "BatchEvaluator":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def evaluate_batch(
    strategies: Iterable[dict[str, Any]],
    *,
    setup: QueueSetup,
    frame: pd.DataFrame,
    workers: int = 1,
    kind: str = "fitness",
    cache_limit_bytes: int | None = None,
) -> list[dict[str, Any]]:
    with BatchEvaluator(
        setup,
        frame,
        workers=workers,
        cache_limit_bytes=cache_limit_bytes,
    ) as evaluator:
        return evaluator.evaluate(strategies, kind)


def run_queue(
    campaign_id: str,
    workers: int | None = None,
    *,
    bars: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
    batch_size: int = 32,
    cache_limit_bytes: int | None = None,
) -> dict[str, Any]:
    """Ejecuta los jobs ``queued`` de una campaña. Devuelve el recuento."""

    identifier = str(campaign_id or "").strip()
    if not identifier:
        raise QueueError("la cola necesita campaign_id")
    target = databank.init_databank(db_path)
    engine = load_engine_config()
    limit = int(engine.workers)
    if workers is None:
        workers = limit
    if int(workers) > limit:
        warnings.warn(
            f"workers {workers} > engine.workers {limit}: se usan {limit}",
            RuntimeWarning,
            stacklevel=2,
        )
        workers = limit
    workers = max(1, int(workers))
    priority = _set_priority()

    campaign_row = databank.get_campaign(identifier, db_path=target)
    if campaign_row is None:
        raise QueueError(f"Sin datos: campaña {identifier} no registrada")
    status = str(campaign_row["status"])
    if status == "draft":
        raise QueueError(
            "campaña en borrador: usa 'lab discovery approve "
            f"{identifier} --approved-by-operator' antes de ejecutar"
        )
    if status == "rejected":
        raise QueueError(f"campaña rechazada: {campaign_row.get('reject_reason')}")
    if status == "superseded":
        raise QueueError(
            f"campaña reemplazada por {campaign_row.get('superseded_by')}"
        )
    from .guard import require_approved_campaign

    require_approved_campaign(
        campaign_row,
        action="run_queue",
        allow_synthetic=status == "synthetic",
    )
    setup = QueueSetup.from_campaign(campaign_row, bars=bars)
    source = campaigns.campaign_bars(campaign_row, frame=bars, db_path=target)
    setup = replace(setup, bars=source)

    with connect(target) as con:
        con.execute(
            "UPDATE disc_jobs SET state = 'queued', started_at = NULL"
            " WHERE campaign_id = ? AND state = 'running'",
            (identifier,),
        )
    campaign_row = databank.get_campaign(identifier, db_path=target)
    if campaign_row and campaign_row["status"] in {"registered", "running"}:
        databank.set_campaign_status(identifier, "running", db_path=target)
    counts = _counts(target, identifier)
    if not any(counts[state] for state in _QUEUE_STATES):
        raise QueueError(f"Sin datos: la campaña {identifier} no tiene jobs")

    prep_max = 0.0
    backend = fastbt.backend()
    cache_hits = 0
    cache_misses = 0
    cache_bytes = 0
    if counts["queued"]:
        pool_workers = min(workers, max(1, counts["queued"]))
        setup = replace(
            setup,
            cache_limit_bytes=_cache_limit(pool_workers, cache_limit_bytes),
        )
        try:
            with ProcessPoolExecutor(
                max_workers=pool_workers,
                initializer=_init_worker,
                initargs=(setup.as_dict(include_bars=True),),
            ) as pool:
                while True:
                    if _campaign_cancelled(target, identifier):
                        cancel_campaign(identifier, db_path=target)
                        break
                    claimed = _claim(target, identifier, max(1, int(batch_size)))
                    if not claimed:
                        break
                    jobs = {int(job["id"]): job for job in claimed}
                    futures = {
                        pool.submit(
                            _evaluate_job,
                            (
                                int(job["id"]),
                                job["payload_json"],
                                str(job.get("kind") or "backtest_is"),
                            ),
                        ): job
                        for job in claimed
                    }
                    results: list[dict[str, Any]] = []
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                        except Exception as exc:  # noqa: BLE001
                            job = futures[future]
                            result = {
                                "job_id": int(job["id"]),
                                "error": f"{type(exc).__name__}: {exc}",
                                "metrics": None,
                                "trades": 0,
                                "returns": [],
                            }
                        results.append(result)
                        prep_max = max(prep_max, float(result.get("prep_s", 0.0)))
                        backend = str(result.get("backend") or backend)
                        stats = result.get("cache") or {}
                        cache_hits += int(stats.get("hits") or 0)
                        cache_misses += int(stats.get("misses") or 0)
                        cache_bytes = max(cache_bytes, int(stats.get("bytes") or 0))
                    _flush(target, identifier, results, jobs, setup)
        except Exception as exc:  # noqa: BLE001 - pool caído: no perder estados
            raise QueueError(f"cola abortada: {type(exc).__name__}: {exc}") from exc

    final = _counts(target, identifier)
    if final["queued"] == 0 and final["running"] == 0:
        campaign_row = databank.get_campaign(identifier, db_path=target)
        if campaign_row and campaign_row["status"] != "cancelled":
            databank.set_campaign_status(identifier, "done", db_path=target)
    return {
        "campaign_id": identifier,
        "workers": workers,
        "priority": priority,
        "backend": backend,
        "prep_max_s": prep_max,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "cache_bytes": cache_bytes,
        **final,
    }


def queue_status(
    campaign_id: str, *, db_path: str | Path | None = None
) -> dict[str, int]:
    target = databank.init_databank(db_path)
    return _counts(target, str(campaign_id))


__all__ = [
    "BatchEvaluator",
    "DEFAULT_SEGMENT",
    "QueueError",
    "QueueSetup",
    "cancel_campaign",
    "enqueue",
    "evaluate_batch",
    "queue_status",
    "run_queue",
    "strategy_gate",
]
