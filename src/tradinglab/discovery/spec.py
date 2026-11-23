"""Especificación de campaña para preflight/feasibility en seco (R2k).

No registra nada: construye el mismo diccionario que usa una campaña para que
``engine.candidate_strategies`` y ``feasibility`` puedan trabajar sin ``disc_*``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..propfund.registry import load_registry
from . import campaigns, genetic
from .config import load_engine_config
from .data_sources import DataSourceError, normalize_source
from .timeframes import normalize_timeframe


class SpecError(ValueError):
    pass


def load_spec(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise SpecError(f"Sin datos: no existe la especificación {target}")
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SpecError(f"YAML inválido: {exc}") from exc
    config = load_engine_config()
    instrument = str(data.get("instrument") or "").strip().upper()
    if not instrument:
        raise SpecError("la especificación no declara instrument")
    try:
        timeframe = normalize_timeframe(
            str(data.get("timeframe") or "M5")
        )
    except Exception as exc:  # noqa: BLE001
        raise SpecError(str(exc)) from exc
    template = str(data.get("template") or "").strip()
    if not template:
        raise SpecError("la especificación no declara template")
    valid = genetic.template_timeframes(template)
    if timeframe not in valid:
        raise SpecError(
            f"plantilla {template} no declara {timeframe}; "
            f"válidos: {', '.join(valid)}"
        )
    try:
        source = normalize_source(str(data.get("data_source") or "broker"))
    except DataSourceError as exc:
        raise SpecError(str(exc)) from exc
    source_error = campaigns.timeframe_source_error(timeframe, source)
    if source_error:
        raise SpecError(source_error)
    profile = str(data.get("profile") or "small").strip().lower()
    config.profile(profile)
    mode = str(data.get("mode") or "ga").strip().lower()
    if mode not in {"ga", "grid"}:
        raise SpecError(f"modo desconocido: {mode}")
    seed = int(data.get("seed", 0))
    raw_segments = data.get("segments") or {}
    if not raw_segments:
        raw_segments = {
            key: data[key] for key in ("is", "oos1", "oos2") if key in data
        }
    segments = campaigns._normalize_segments(
        raw_segments, config.data_quality.default_segments
    )
    start = pd.Timestamp(segments["is"][0])
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    limit = config.data_quality.usable_from_for(
        source, instrument, timeframe
    )
    if limit is not None and start.date() < limit:
        raise SpecError(
            f"IS empieza antes de usable_from ({start.date()} < {limit})"
        )
    account_id = str(data.get("account") or "CFD-001").strip().upper()
    registry = load_registry()
    account = registry.accounts.get(account_id)
    if account is None:
        raise SpecError(f"cuenta no registrada: {account_id}")
    if instrument not in account.allowed_instruments:
        raise SpecError(f"{account_id} no permite {instrument}")
    firm = str(data.get("firm") or registry.firm_of(account_id).id).strip().lower()
    session = data.get("session") or campaigns.template_session(
        template, instrument
    )
    cost = data.get("cost") or {
        "account": account_id,
        "firm": firm,
        "use_p75": True,
        "accounts": [account_id],
        "mode": "target",
    }
    config_payload: dict[str, Any] = {
        "instrument": instrument,
        "timeframe": timeframe,
        "template": template,
        "profile": profile,
        "mode": mode,
        "data_source": source,
        "seed": seed,
        "engine_profile": profile,
        "is_start": segments["is"][0],
        "is_end": segments["is"][1],
        "oos1_start": segments["oos1"][0],
        "oos1_end": segments["oos1"][1],
        "oos2_start": segments["oos2"][0],
        "oos2_end": segments["oos2"][1],
        "segments": segments,
        "cost": cost,
        "session": session,
        "point": float(data.get("point", 0.01)),
        "limits": {
            "weekdays": [0, 1, 2, 3, 4],
            "stop_n": 14,
            "trail_n": 14,
        },
    }
    return {
        "campaign_id": f"spec:{target.stem}",
        "status": "draft",
        "instrument": instrument,
        "timeframe": timeframe,
        "template": template,
        "is_start": segments["is"][0],
        "is_end": segments["is"][1],
        "oos1_start": segments["oos1"][0],
        "oos1_end": segments["oos1"][1],
        "oos2_start": segments["oos2"][0],
        "oos2_end": segments["oos2"][1],
        "config": config_payload,
        "spec_path": str(target),
    }


__all__ = ["SpecError", "load_spec"]
