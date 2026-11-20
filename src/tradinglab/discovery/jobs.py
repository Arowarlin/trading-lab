"""Cola de trabajos del Discovery Lab (``disc_jobs`` en ``data/discovery.db``).

Diseño:

* **Un solo escritor**: los workers no abren SQLite. Compilan y ejecutan la
  estrategia y devuelven el resultado al proceso principal, que escribe en
  lotes con una transacción por lote.
* **Preparación por worker**: el initializer carga las barras (por
  ``discovery.data_sources`` o sintéticas), corta el tramo, construye el coste
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
from . import databank, dsl, fastbt
from .compiler import compile as compile_strategy
from .config import load_engine_config
from .data_sources import load_source

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
    session_tz: str = "America/New_York"
    session_start: str = "09:35"
    session_end: str = "11:30"
    flat_at: str | None = "15:45"
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    stop_n: int = 14
    trail_n: int = 14
    template: str | None = None
    seed: int = 0
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

    def validated(self) -> "QueueSetup":
        if not str(self.instrument or "").strip():
            raise QueueError("el setup necesita instrument")
        if not str(self.timeframe or "").strip():
            raise QueueError("el setup necesita timeframe")
        if not str(self.account or "").strip():
            raise QueueError("el setup necesita account")
        if self.session_start == self.session_end:
            raise QueueError("la sesión no puede tener start == end (24 h no soportado)")
        return replace(
            self,
            instrument=str(self.instrument).upper(),
            timeframe=str(self.timeframe).upper(),
            weekdays=tuple(int(day) for day in self.weekdays),
        )

    def cost_profile(self) -> str:
        return f"{self.account}:{self.instrument}"


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
            "SELECT id, payload_json, strategy_hash FROM disc_jobs"
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
            " WHERE id = ? AND status IN ('registered', 'running')",
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
        loaded = load_source(setup.instrument, setup.timeframe)
        bars = loaded.frame
    bars = _slice_bars(bars, setup.start, setup.end)
    if len(bars) < 100:
        raise QueueError("Sin datos: menos de 100 barras en el tramo IS")
    profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
    cost = fastbt.cost_from_profile(profile, use_p75=setup.use_p75)
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
    _WORKER = {
        "setup": setup,
        "bars": bars,
        "cost": cost,
        "prepared": prepared,
        "prep_s": time.perf_counter() - started,
    }


def _exit_spec(model: dsl.Strategy) -> fastbt.ExitSpec:
    stop = model.exit.stop
    if stop.type == "atr":
        stop_kwargs = {"stop": "atr", "stop_mult": stop.mult, "stop_n": stop.n}
    elif stop.type == "pct":
        percentage = stop.value if stop.value is not None else stop.mult
        stop_kwargs = {"stop": "pct", "stop_mult": float(percentage)}
    else:
        stop_kwargs = {"stop": "fixed", "stop_price": stop.value}
    target = model.exit.target
    if target.type == "rr":
        target_kwargs = {"target": "rr", "target_rr": target.rr}
    elif target.type == "pct":
        percentage = target.value if target.value is not None else target.rr
        target_kwargs = {"target": "pct", "target_pct": float(percentage)}
    else:
        target_kwargs = {"target": "fixed", "target_price": target.value}
    breakeven = model.exit.breakeven or {}
    trailing = model.exit.trailing or {}
    trail_mult = trailing.get("atr_mult", trailing.get("mult"))
    return fastbt.ExitSpec(
        **stop_kwargs,
        **target_kwargs,
        breakeven_at_r=breakeven.get("at_r"),
        trail_atr_mult=trail_mult,
        trail_n=int(trailing.get("n", 14)),
        time_exit_bars=model.exit.time_exit_bars,
        opposite_signal=model.exit.opposite_signal,
    )


def _run_limits(model: dsl.Strategy, setup: QueueSetup) -> fastbt.RunLimits:
    session = model.session
    return fastbt.RunLimits(
        session_tz=session.tz or setup.session_tz,
        session_start=session.start,
        session_end=session.end,
        flat_at=session.flat_at,
        weekdays=setup.weekdays,
        max_trades_per_day=model.limits.max_trades_per_day,
        cooldown_bars=model.limits.cooldown_bars,
        close_at_end=True,
    )


def _evaluate_job(task: tuple[int, str]) -> dict[str, Any]:
    job_id, payload_json = task
    state = _WORKER
    if not state:
        return {"job_id": job_id, "error": "worker sin preparación", "metrics": None}
    try:
        strategy = json.loads(payload_json)
        errors = dsl.validate(strategy)
        if errors:
            raise QueueError("estrategia inválida: " + "; ".join(errors))
        model = dsl.Strategy.model_validate(strategy)
        setup: QueueSetup = state["setup"]
        if model.instrument.upper() != setup.instrument.upper():
            raise QueueError(
                f"instrumento {model.instrument} != {setup.instrument} de la campaña"
            )
        if model.timeframe.upper() != setup.timeframe.upper():
            raise QueueError(
                f"timeframe {model.timeframe} != {setup.timeframe} de la campaña"
            )
        signals = compile_strategy(model, state["bars"])
        result = fastbt.run(
            signals,
            state["bars"],
            _exit_spec(model),
            state["cost"],
            _run_limits(model, setup),
            prepared=state["prepared"],
        )
        returns = result.daily_r.to_numpy(dtype=float).tolist()
        return {
            "job_id": job_id,
            "strategy_hash": dsl.strategy_hash(model),
            "metrics": result.metrics,
            "trades": len(result.trades),
            "returns": returns,
            "error": None,
            "backend": result.backend,
            "prep_s": float(state.get("prep_s", 0.0)),
        }
    except Exception as exc:  # noqa: BLE001 - el error se guarda por job
        return {
            "job_id": job_id,
            "error": f"{type(exc).__name__}: {exc}",
            "metrics": None,
            "trades": 0,
            "returns": [],
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
                    segment=DEFAULT_SEGMENT,
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


def run_queue(
    campaign_id: str,
    workers: int | None = None,
    *,
    setup: QueueSetup | None = None,
    db_path: str | Path | None = None,
    batch_size: int = 32,
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

    if setup is None:
        row = databank.get_campaign(identifier, db_path=target)
        if row is None:
            raise QueueError(f"Sin datos: campaña {identifier} no registrada")
        setup = QueueSetup.from_dict(row["config"])
    setup = setup.validated()

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
    if counts["queued"]:
        pool_workers = min(workers, max(1, counts["queued"]))
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
                        pool.submit(_evaluate_job, (int(job["id"]), job["payload_json"])): job
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
        **final,
    }


def queue_status(
    campaign_id: str, *, db_path: str | Path | None = None
) -> dict[str, int]:
    target = databank.init_databank(db_path)
    return _counts(target, str(campaign_id))


__all__ = [
    "DEFAULT_SEGMENT",
    "QueueError",
    "QueueSetup",
    "cancel_campaign",
    "enqueue",
    "queue_status",
    "run_queue",
]
