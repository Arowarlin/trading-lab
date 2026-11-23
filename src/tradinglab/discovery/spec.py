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
from . import campaigns, genetic, grid
from .config import load_engine_config
from .data_sources import DataSourceError, normalize_source
from .dsl import HHMM
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
    confirmation_only = bool(data.get("confirmation_only", False))
    if (
        source_error
        and confirmation_only
        and source == "databento"
        and timeframe == "D1"
    ):
        # Espejo de confirmación: el registro real sigue bloqueado en
        # campaigns.timeframe_source_error; esta excepción solo vive en la spec.
        source_error = None
    if source_error:
        raise SpecError(source_error)
    profile = str(data.get("profile") or "small").strip().lower()
    config.profile(profile)
    mode = str(data.get("mode") or "ga").strip().lower()
    if mode not in {"ga", "grid"}:
        raise SpecError(f"modo desconocido: {mode}")
    side = str(data.get("side") or "").strip().lower()
    if side not in {"", "long", "short"}:
        raise SpecError(f"lado desconocido: {side}")
    fix_start = str(data.get("fix_start") or "").strip() or None
    fix_end = str(data.get("fix_end") or "").strip() or None
    for name, value in (("fix_start", fix_start), ("fix_end", fix_end)):
        if value is not None and not HHMM.match(value):
            raise SpecError(f"{name} inválido: {value}")
    grid_spec = data.get("grid")
    if mode == "grid":
        try:
            grid_spec = grid.validate_grid(grid_spec, template)
        except grid.GridError as exc:
            raise SpecError(f"grid inválido: {exc}") from exc
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
    cost_accounts = [
        str(item).strip().upper()
        for item in (data.get("cost_accounts") or [account_id])
        if str(item).strip()
    ]
    cost_mode = str(data.get("cost_mode") or "target").strip().lower()
    if cost_mode not in {"best", "worst", "target"}:
        raise SpecError(f"cost_mode desconocido: {cost_mode}")
    if cost_mode == "target" and len(cost_accounts) != 1:
        raise SpecError("cost_mode target exige una sola cuenta")
    for cost_account in cost_accounts:
        candidate = registry.accounts.get(cost_account)
        if candidate is None:
            raise SpecError(f"cuenta de coste no registrada: {cost_account}")
        if instrument not in candidate.allowed_instruments:
            raise SpecError(f"{cost_account} no permite {instrument}")
    session = data.get("session") or campaigns.template_session(
        template, instrument
    )
    cost = data.get("cost") or {
        "account": cost_accounts[0],
        "firm": firm,
        "use_p75": bool(data.get("use_p75", True)),
        "accounts": cost_accounts,
        "mode": cost_mode,
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
        "confirmation_only": confirmation_only,
    }
    if side:
        config_payload["side"] = side
    if fix_start:
        config_payload["fix_start"] = fix_start
    if fix_end:
        config_payload["fix_end"] = fix_end
    if grid_spec is not None:
        config_payload["grid"] = grid_spec
    campaign_id = str(
        data.get("campaign_id") or f"spec-{target.stem}"
    ).strip()
    return {
        "campaign_id": campaign_id,
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
        "confirmation_only": confirmation_only,
    }


__all__ = ["SpecError", "load_spec"]
