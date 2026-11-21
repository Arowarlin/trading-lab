"""Campañas de discovery, segmentos sellados y lectura única de OOS-2.

* La campaña vive en ``data/discovery.db`` (``disc_campaigns``).
* ``n_total`` se guarda al registrar, antes de correr, y es inmutable (trigger
  en SQLite). En modo ``ga`` es ``population × (generations + 1)``; en modo
  ``grid`` es el número de combinaciones declaradas en la plantilla.
* El ``dataset_hash`` se calcula sobre ``[is_start, oos2_end]`` con el final de
  OOS-2 resuelto a la última vela **cerrada**; las velas nuevas posteriores no
  invalidan la campaña.
* Al registrar se escribe un snapshot inmutable en
  ``data/discovery/snapshots/<campaign_id>.parquet`` y la campaña lee siempre
  de él, nunca de la caché viva. ``oos2_end`` excluye la vela en formación.
* ``supersede`` reemplaza una campaña fallida por otra con el mismo
  ``config_hash`` y un snapshot nuevo; la vieja pasa a ``superseded`` y deja de
  sumar en el DSR (sin doble conteo).
* Registrar deja un **borrador**; solo ``approve`` (CLI con flag explícito) lo
  pasa a ``registered`` y lo cuenta en el DSR. Una campaña aprobada cuenta
  aunque luego se cancele o se rechace.
* OOS-1 solo se abre con la campaña ``done``; OOS-2 solo por
  ``read_holdout(strategy_id)``, una vez por estrategia.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..config import ROOT
from ..db import connect
from . import __version__, databank, grid, snapshots
from .config import load_engine_config
from .data_quality import check_dataset, dataset_hash
from .data_sources import load_source

SEGMENTS = ("is", "oos1", "oos2")


class CampaignError(ValueError):
    pass


class HoldoutError(CampaignError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _start_ts(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _end_ts(value: Any) -> pd.Timestamp:
    """Fin inclusivo: una fecha sin hora cubre el día completo."""

    text = str(value)
    stamp = _start_ts(value)
    if len(text) <= 10:
        return stamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return stamp


def _normalize_segments(
    segments: dict[str, Any] | None, engine_segments: dict[str, Any]
) -> dict[str, list[str | None]]:
    source = segments if segments is not None else engine_segments
    normalized: dict[str, list[str | None]] = {}
    for name in SEGMENTS:
        value = source.get(name) if isinstance(source, dict) else None
        if value is None or len(value) != 2:
            raise CampaignError(f"tramo {name}: faltan start/end")
        start, end = value
        if start is None:
            raise CampaignError(f"tramo {name}: falta start")
        if name != "oos2" and end is None:
            raise CampaignError(f"tramo {name}: falta end")
        normalized[name] = [
            str(start),
            None if end is None else str(end),
        ]
    if _start_ts(normalized["is"][0]) >= _end_ts(normalized["is"][1]):
        raise CampaignError("tramo is: start debe ser anterior a end")
    if _start_ts(normalized["oos1"][0]) <= _end_ts(normalized["is"][1]):
        raise CampaignError("oos1 debe empezar después de is")
    if _start_ts(normalized["oos2"][0]) <= _end_ts(normalized["oos1"][1]):
        raise CampaignError("oos2 debe empezar después de oos1")
    return normalized


def _template_session(template: str, instrument: str) -> dict[str, Any]:
    path = ROOT / "config" / "discovery" / "templates" / f"{template}.yaml"
    if not path.exists():
        raise CampaignError(f"Sin datos: no existe la plantilla {template}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    strategy = data.get("strategy") or {}
    session = dict(strategy.get("session") or {})
    engine = load_engine_config().data_quality
    return {
        "tz": session.get("tz") or engine.tz_for(instrument),
        "start": str(session.get("start") or "09:35"),
        "end": str(session.get("end") or "11:30"),
        "flat_at": str(session.get("flat_at") or "15:45"),
        "or_minutes": int(session.get("or_minutes") or 15),
    }


def _source_frame(instrument: str, timeframe: str) -> pd.DataFrame:
    return load_source(instrument, timeframe).frame


def _resolve_oos2_end(frame: pd.DataFrame, requested: str | None) -> pd.Timestamp:
    if requested is None:
        if len(frame) == 0:
            raise CampaignError("Sin datos: no hay barras para OOS-2")
        return frame.index[-1]
    limit = _end_ts(requested)
    eligible = frame.index[frame.index <= limit]
    if len(eligible) == 0:
        raise CampaignError(f"Sin datos: OOS-2 termina antes de {requested}")
    return eligible[-1]


def _quality(
    frame: pd.DataFrame,
    instrument: str,
    timeframe: str,
    segments: dict[str, list[str | None]],
) -> tuple[Any, str]:
    report = check_dataset(
        frame,
        instrument,
        timeframe,
        segments={key: tuple(value) for key, value in segments.items()},
    )
    if report.status == "fail":
        detail = "; ".join(report.issues[:5]) or "sin detalle"
        raise CampaignError(f"calidad de datos fail: {detail}")
    useful = report.granularity.get("useful_start")
    if not useful:
        raise CampaignError("Sin datos: la fuente no tiene inicio útil")
    useful_date = pd.Timestamp(useful).date()
    for name in SEGMENTS:
        start_date = _start_ts(segments[name][0]).date()
        if start_date < useful_date:
            raise CampaignError(
                f"tramo {name} empieza antes del inicio útil "
                f"({start_date} < {useful_date})"
            )
    return report, str(useful)


def _hash_range(
    frame: pd.DataFrame, is_start: str, oos2_end: pd.Timestamp
) -> pd.DataFrame:
    start = _start_ts(is_start)
    sliced = frame[(frame.index >= start) & (frame.index <= oos2_end)]
    if len(sliced) == 0:
        raise CampaignError("Sin datos: el rango de hash está vacío")
    return sliced


def dataset_matches(campaign: dict[str, Any], frame: pd.DataFrame) -> bool:
    """Compara el hash del rango fijo; las velas nuevas no cuentan."""

    if not campaign.get("dataset_hash"):
        return False
    if not campaign.get("oos2_end"):
        return False
    try:
        sliced = _hash_range(
            frame,
            str(campaign["is_start"]),
            _start_ts(campaign["oos2_end"]),
        )
    except CampaignError:
        return False
    return dataset_hash(sliced) == campaign["dataset_hash"]


def register(
    instrument: str,
    timeframe: str,
    template: str,
    profile: str = "small",
    *,
    segments: dict[str, Any] | None = None,
    seed: int = 0,
    campaign_id: str | None = None,
    account: str = "CFD-001",
    firm: str | None = "ftmo",
    use_p75: bool = True,
    mode: str = "ga",
    frame: pd.DataFrame | None = None,
    dry_run: bool = False,
    now: Any | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Registra un borrador (o previsualiza con ``dry_run``)."""

    instrument = str(instrument or "").strip().upper()
    timeframe = str(timeframe or "").strip().upper()
    if not instrument or not timeframe:
        raise CampaignError("instrument y timeframe son obligatorios")
    mode = str(mode or "ga").strip().lower()
    if mode not in {"ga", "grid"}:
        raise CampaignError(f"modo desconocido: {mode}")
    engine = load_engine_config()
    try:
        profile_config = engine.profile(profile)
    except KeyError as exc:
        raise CampaignError(str(exc)) from exc
    session = _template_session(template, instrument)
    grid_spec: dict[str, Any] | None = None
    if mode == "grid":
        try:
            grid_spec = grid.load_grid(template)
            grid_strategies = grid.grid_strategies(
                template,
                instrument=instrument,
                timeframe=timeframe,
                session=session,
            )
        except Exception as exc:  # noqa: BLE001
            raise CampaignError(f"rejilla inválida: {exc}") from exc
        n_total = len(grid_strategies)
    else:
        n_total = int(profile_config.population * (profile_config.generations + 1))

    source = frame if frame is not None else _source_frame(instrument, timeframe)
    source = snapshots.closed_bars(source, timeframe, now=now)
    normalized = _normalize_segments(segments, engine.data_quality.default_segments)
    oos2_end = _resolve_oos2_end(source, normalized["oos2"][1])
    normalized["oos2"][1] = oos2_end.isoformat()
    report, useful_start = _quality(source, instrument, timeframe, normalized)
    if _start_ts(normalized["oos2"][0]) > oos2_end:
        raise CampaignError("oos2: start posterior al final real de OOS-2")

    hashed = _hash_range(source, normalized["is"][0], oos2_end)
    digest = dataset_hash(hashed)
    config_payload: dict[str, Any] = {
        "instrument": instrument,
        "timeframe": timeframe,
        "template": template,
        "profile": profile,
        "mode": mode,
        "seed": int(seed),
        "engine_profile": profile,
        "is_start": normalized["is"][0],
        "is_end": normalized["is"][1],
        "oos1_start": normalized["oos1"][0],
        "oos1_end": normalized["oos1"][1],
        "oos2_start": normalized["oos2"][0],
        "oos2_end": normalized["oos2"][1],
        "segments": normalized,
        "dataset_hash": digest,
        "n_total": n_total,
        "cost": {"account": account, "firm": firm, "use_p75": bool(use_p75)},
        "session": session,
        "point": 0.01,
        "limits": {
            "weekdays": [0, 1, 2, 3, 4],
            "stop_n": 14,
            "trail_n": 14,
        },
        "quality": {
            "status": report.status,
            "useful_start": useful_start,
            "issues": list(report.issues),
            "segments": {
                key: value.as_dict() for key, value in report.segments.items()
            },
        },
        "engine_version": __version__,
    }
    if grid_spec is not None:
        config_payload["grid"] = grid_spec
        config_payload["grid_size"] = n_total
    config_json = json.dumps(config_payload, sort_keys=True, ensure_ascii=False)
    config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()
    identifier = str(campaign_id or "").strip()
    if not identifier:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        identifier = f"disc-{instrument}-{timeframe}-{stamp}-{config_hash[:8]}"

    preview = {
        "campaign_id": identifier,
        "status": "draft",
        "approved_at": None,
        "n_total": n_total,
        "dataset_hash": digest,
        "snapshot_hash": digest,
        "snapshot_path": str(snapshots.snapshot_path_for(identifier, db_path)),
        "snapshot_rows": int(len(hashed)),
        "config_hash": config_hash,
        "config": config_payload,
        "quality": config_payload["quality"],
        "rows": int(len(hashed)),
        "oos2_end": oos2_end.isoformat(),
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
        raise CampaignError(f"la campaña {identifier} ya está registrada")
    snapshot = snapshots.write_snapshot(
        identifier, hashed, db_path=db_path, now=now
    )
    databank.add_campaign(
        identifier,
        config_payload,
        instrument=instrument,
        timeframe=timeframe,
        template=template,
        engine_profile=profile,
        status="draft",
        quality=config_payload["quality"],
        n_total=n_total,
        dataset_hash=digest,
        snapshot_path=snapshot.path,
        snapshot_hash=snapshot.hash,
        snapshot_rows=snapshot.rows,
        snapshot_at=snapshot.created_at,
        db_path=db_path,
    )
    campaign = databank.get_campaign(identifier, db_path=db_path)
    if campaign is None:  # pragma: no cover
        raise CampaignError("no se pudo registrar la campaña")
    campaign["campaign_id"] = campaign["id"]
    return campaign


def register_synthetic(
    frame: pd.DataFrame,
    *,
    instrument: str = "US100",
    timeframe: str = "M5",
    template: str = "ny_open_vol_filter",
    profile: str = "small",
    segments: dict[str, Any] | None = None,
    seed: int = 0,
    campaign_id: str | None = None,
    account: str = "CFD-001",
    firm: str | None = "ftmo",
    mode: str = "ga",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Campaña sintética: nunca se aprueba ni cuenta en el DSR."""

    campaign = register(
        instrument,
        timeframe,
        template,
        profile,
        segments=segments,
        seed=seed,
        campaign_id=campaign_id,
        account=account,
        firm=firm,
        mode=mode,
        frame=frame,
        dry_run=False,
        db_path=db_path,
    )
    identifier = str(campaign["campaign_id"])
    databank.set_campaign_status(identifier, "synthetic", db_path=db_path)
    result = databank.get_campaign(identifier, db_path=db_path)
    if result is None:  # pragma: no cover
        raise CampaignError("no se pudo registrar la campaña sintética")
    result["campaign_id"] = result["id"]
    return result


def approve(
    campaign_id: str,
    *,
    approved_by: str = "operator",
    verify: bool = True,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Aprobación explícita (solo la llama el CLI con su flag).

    Con ``verify=True`` (por defecto) exige preflight limpio y al menos el
    50 % de las combinaciones/individuos iniciales factibles. ``verify=False``
    queda reservado a tests y a ``supersede``.
    """

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if verify and campaign["status"] == "draft":
        from . import engine, feasibility

        preflight = engine.preflight(campaign_id, db_path=db_path)
        if int(preflight["valid"]) < int(preflight["population"]):
            raise CampaignError(
                "preflight: "
                f"{preflight['valid']} válidos < población {preflight['population']}"
            )
        report = feasibility.check(campaign_id, db_path=db_path)
        if not report["passes"]:
            raise CampaignError(
                "feasibility: "
                f"{report['n_feasible']}/{report['n_checked']} factibles "
                f"({report['feasible_pct']:.1f} %) < 50 %"
            )
    result = databank.approve_campaign(
        campaign_id, approved_by=approved_by, db_path=db_path
    )
    result["campaign_id"] = result["id"]
    return result


def invalidate(
    campaign_id: str,
    reason: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Archiva una campaña como inválida sin borrar su cuenta en el DSR."""

    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if campaign["status"] == "superseded":
        raise CampaignError("una campaña superseded ya no cuenta; no se invalida")
    databank.set_campaign_invalid(campaign_id, str(reason), db_path=db_path)
    result = databank.get_campaign(campaign_id, db_path=db_path)
    if result is None:  # pragma: no cover
        raise CampaignError("no se pudo invalidar la campaña")
    result["campaign_id"] = result["id"]
    return result


def mark_done(
    campaign_id: str, *, db_path: str | Path | None = None
) -> dict[str, Any]:
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if campaign["status"] == "draft":
        raise CampaignError("un borrador no se puede marcar done")
    if campaign["status"] not in {"registered", "running", "done", "synthetic"}:
        raise CampaignError(
            f"la campaña está {campaign['status']}; no se puede marcar done"
        )
    databank.set_campaign_status(campaign_id, "done", db_path=db_path)
    result = databank.get_campaign(campaign_id, db_path=db_path)
    if result is None:  # pragma: no cover
        raise CampaignError("no se pudo marcar done")
    return result


def _new_campaign_id(
    old: dict[str, Any],
    config_hash: str,
    *,
    db_path: str | Path | None,
    now: Any | None = None,
) -> str:
    stamp = snapshots.read_time(now).strftime("%Y%m%d%H%M%S")
    base = (
        f"disc-{old['instrument']}-{old['timeframe']}-{stamp}-"
        f"{str(config_hash)[:8]}"
    )
    candidate = base
    suffix = 1
    while databank.get_campaign(candidate, db_path=db_path) is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def supersede(
    campaign_id: str,
    *,
    approved_by: str = "operator",
    db_path: str | Path | None = None,
    now: Any | None = None,
) -> dict[str, Any]:
    """Reemplaza una campaña fallida sin volver a contar sus pruebas.

    Solo se permite sobre una campaña aprobada, con 0 evaluaciones y 0 jobs
    ejecutados, que falló por ``dataset_hash`` o al arrancar. La campaña nueva
    hereda ``config_hash``, plantilla, semilla y modo, y recibe un snapshot
    nuevo. La vieja pasa a ``superseded`` y deja de sumar en ``count_tests``.
    """

    old = databank.get_campaign(campaign_id, db_path=db_path)
    if old is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if old["status"] == "superseded":
        raise CampaignError(
            f"la campaña ya fue reemplazada por {old.get('superseded_by')}"
        )
    if not old.get("approved_at"):
        raise CampaignError("solo se reemplaza una campaña aprobada")
    if old.get("status") not in {"rejected", "registered"}:
        raise CampaignError(
            f"la campaña está {old.get('status')}; no se puede reemplazar"
        )
    if int(old.get("n_evaluated") or 0) > 0 or databank.count_evaluations(
        campaign_id, db_path=db_path
    ) > 0:
        raise CampaignError(
            "la campaña tiene evaluaciones; no se puede reemplazar"
        )
    if databank.count_executed_jobs(campaign_id, db_path=db_path) > 0:
        raise CampaignError(
            "la campaña tiene jobs ejecutados; no se puede reemplazar"
        )
    config_hash = str(old.get("config_hash") or "")
    if not config_hash:
        raise CampaignError("Sin datos: la campaña no tiene config_hash")
    reason = str(old.get("reject_reason") or "")
    last_error = str(old.get("last_error") or "")
    hash_failure = "dataset_hash" in reason.lower() or "dataset_hash" in last_error.lower()
    startup_failure = bool(last_error.strip()) and not hash_failure
    if not (hash_failure or startup_failure):
        raise CampaignError(
            "solo se reemplaza una campaña que falló por hash o al arrancar"
        )
    oos2_end = old.get("oos2_end")
    if not oos2_end:
        raise CampaignError("Sin datos: la campaña no tiene oos2_end")
    config = copy.deepcopy(old.get("config") or {})
    segments = {
        "is": [old["is_start"], old["is_end"]],
        "oos1": [old["oos1_start"], old["oos1_end"]],
        "oos2": [old["oos2_start"], oos2_end],
    }
    source = snapshots.closed_bars(
        _source_frame(old["instrument"], old["timeframe"]),
        old["timeframe"],
        now=now,
    )
    resolved_end = _resolve_oos2_end(source, oos2_end)
    if _start_ts(resolved_end) != _start_ts(oos2_end):
        raise CampaignError(
            "la vela final de la campaña aún no está cerrada; "
            "espera al cierre y vuelve a intentarlo"
        )
    report, useful_start = _quality(
        source, old["instrument"], old["timeframe"], segments
    )
    snapshot_frame = _hash_range(source, old["is_start"], resolved_end)
    digest = dataset_hash(snapshot_frame)
    new_id = _new_campaign_id(
        old, config_hash, db_path=db_path, now=now
    )
    total_before = discovery_tests(db_path)
    snapshot = snapshots.write_snapshot(
        new_id, snapshot_frame, db_path=db_path, now=now
    )
    quality = {
        "status": report.status,
        "useful_start": useful_start,
        "issues": list(report.issues),
        "segments": {
            key: value.as_dict() for key, value in report.segments.items()
        },
    }
    target = databank.init_databank(db_path)
    with connect(target) as con:
        databank.add_campaign(
            new_id,
            config,
            instrument=old["instrument"],
            timeframe=old["timeframe"],
            template=old.get("template") or config.get("template"),
            engine_profile=old.get("engine_profile"),
            status="draft",
            quality=quality,
            n_total=old.get("n_total"),
            dataset_hash=digest,
            config_hash=config_hash,
            snapshot_path=snapshot.path,
            snapshot_hash=snapshot.hash,
            snapshot_rows=snapshot.rows,
            snapshot_at=snapshot.created_at,
            supersedes=campaign_id,
            con=con,
        )
        databank.approve_campaign(
            new_id, approved_by=approved_by, db_path=target, con=con
        )
        databank.set_campaign_superseded(
            campaign_id,
            new_id,
            reason=f"reemplazada por {new_id}",
            db_path=target,
            con=con,
        )
    total_after = discovery_tests(db_path)
    snapshots.append_audit(
        {
            "action": "supersede",
            "old_id": campaign_id,
            "new_id": new_id,
            "operator": str(approved_by),
            "reason": reason or last_error or "fallo de arranque",
            "old_status": old["status"],
            "old_approved_at": old.get("approved_at"),
            "old_dataset_hash": old.get("dataset_hash"),
            "old_snapshot_path": old.get("snapshot_path"),
            "new_snapshot_path": snapshot.path,
            "new_snapshot_hash": snapshot.hash,
            "config_hash": config_hash,
            "n_total": int(old.get("n_total") or 0),
            "count_before": int(total_before.get("total") or 0),
            "count_after": int(total_after.get("total") or 0),
        },
        db_path=db_path,
    )
    result = databank.get_campaign(new_id, db_path=db_path)
    if result is None:  # pragma: no cover
        raise CampaignError("no se pudo crear la campaña de reemplazo")
    result["campaign_id"] = result["id"]
    result["superseded"] = campaign_id
    result["count_before"] = int(total_before.get("total") or 0)
    result["count_after"] = int(total_after.get("total") or 0)
    return result


def _segment_frame(
    frame: pd.DataFrame,
    campaign: dict[str, Any],
    segment: str,
) -> pd.DataFrame:
    start = _start_ts(campaign[f"{segment}_start"])
    end = _end_ts(campaign[f"{segment}_end"])
    sliced = frame[(frame.index >= start) & (frame.index <= end)]
    if len(sliced) == 0:
        raise CampaignError(f"Sin datos en el tramo {segment}")
    return sliced


def campaign_bars(
    campaign: dict[str, Any],
    *,
    frame: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Barras de la campaña: snapshot congelado; caché viva solo si no hay snapshot."""

    campaign_id = str(campaign.get("id") or campaign.get("campaign_id") or "")
    snapshot_path = campaign.get("snapshot_path")
    if snapshot_path:
        expected = campaign.get("snapshot_hash") or campaign.get("dataset_hash")
        try:
            return snapshots.load_snapshot(str(snapshot_path), expected)
        except snapshots.SnapshotError as exc:
            databank.set_campaign_rejected(
                campaign_id,
                f"snapshot inválido: {exc}",
                db_path=db_path,
            )
            raise CampaignError(str(exc)) from exc
    source = frame if frame is not None else _source_frame(
        campaign["instrument"], campaign["timeframe"]
    )
    if not dataset_matches(campaign, source):
        databank.set_campaign_rejected(
            campaign_id,
            "dataset_hash no coincide con el rango fijo de la campaña",
            db_path=db_path,
        )
        raise CampaignError(
            "dataset_hash no coincide: la fuente cambió dentro del rango sellado"
        )
    return source


def load_segment(
    campaign_id: str,
    segment: str,
    *,
    frame: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Devuelve IS/OOS-1 sellado desde el snapshot. OOS-2 solo por ``read_holdout``."""

    name = str(segment or "").strip().lower()
    if name not in {"is", "oos1"}:
        raise HoldoutError(
            "OOS-2 no se lee por load_segment; usa read_holdout(strategy_id)"
        )
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if name == "oos1" and campaign["status"] != "done":
        raise CampaignError(
            "OOS-1 sellado: la campaña debe estar done antes de leerlo"
        )
    source = campaign_bars(campaign, frame=frame, db_path=db_path)
    return _segment_frame(source, campaign, name)


def read_holdout(
    strategy_id: int,
    *,
    frame: pd.DataFrame | None = None,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    """Lectura única de OOS-2 por estrategia; la segunda falla."""

    strategy = databank.get_strategy(strategy_id, db_path=db_path)
    if strategy is None:
        raise CampaignError(f"estrategia no encontrada: {strategy_id}")
    campaign_id = str(strategy["campaign_id"])
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    if campaign["status"] != "done":
        raise CampaignError("el holdout OOS-2 solo se abre con la campaña done")
    if databank.get_holdout_read(strategy_id, db_path=db_path) is not None:
        raise HoldoutError(
            f"la estrategia {strategy_id} ya leyó OOS-2; segunda lectura prohibida"
        )
    source = campaign_bars(campaign, frame=frame, db_path=db_path)
    start = _start_ts(campaign["oos2_start"])
    end = _start_ts(campaign["oos2_end"])
    sealed = source[(source.index >= start) & (source.index <= end)]
    if len(sealed) == 0:
        raise CampaignError("Sin datos en OOS-2")
    try:
        databank.add_holdout_read(
            int(strategy_id),
            campaign_id,
            dataset_hash=campaign.get("snapshot_hash") or campaign["dataset_hash"],
            rows=int(len(sealed)),
            db_path=db_path,
        )
    except sqlite3.IntegrityError as exc:
        raise HoldoutError(
            f"la estrategia {strategy_id} ya leyó OOS-2; segunda lectura prohibida"
        ) from exc
    return sealed


def discovery_tests(
    discovery_db: str | Path | None = None,
) -> dict[str, int]:
    """Suma DSR de discovery en solo lectura; nunca crea ni escribe."""

    path = Path(discovery_db) if discovery_db else databank.DEFAULT_DISCOVERY_DB
    if not path.exists():
        return {"campaigns": 0, "holdout_reads": 0, "total": 0}
    uri = f"file:{path.as_posix()}?mode=ro"
    campaigns = 0
    reads = 0
    con = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        try:
            row = con.execute(
                "SELECT COALESCE(SUM(n_total), 0) AS n FROM disc_campaigns"
                " WHERE approved_at IS NOT NULL"
                " AND COALESCE(status, '') != 'superseded'"
            ).fetchone()
            campaigns = int(row[0] or 0)
        except sqlite3.OperationalError:
            campaigns = 0
        try:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM disc_holdout_reads r"
                " JOIN disc_campaigns c ON c.id = r.campaign_id"
                " WHERE c.approved_at IS NOT NULL"
                " AND COALESCE(c.status, '') != 'superseded'"
            ).fetchone()
            reads = int(row[0] or 0)
        except sqlite3.OperationalError:
            reads = 0
    finally:
        con.close()
    return {
        "campaigns": campaigns,
        "holdout_reads": reads,
        "total": campaigns + reads,
    }


def total_tests(discovery_db: str | Path | None = None) -> dict[str, int]:
    return discovery_tests(discovery_db)


__all__ = [
    "CampaignError",
    "HoldoutError",
    "approve",
    "campaign_bars",
    "dataset_matches",
    "discovery_tests",
    "invalidate",
    "load_segment",
    "mark_done",
    "read_holdout",
    "register",
    "register_synthetic",
    "supersede",
    "total_tests",
]
