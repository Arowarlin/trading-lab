"""Snapshots congelados por campaña (R2d).

Cada campaña guarda, al registrarse, las barras de ``[is_start, oos2_end]`` en
``data/discovery/snapshots/<campaign_id>.parquet``. A partir de ese momento la
campaña lee **siempre** de ese archivo, nunca de la caché viva. El hash
``sha256`` del snapshot queda en ``disc_campaigns.snapshot_hash`` y se verifica
en cada lectura.

``oos2_end`` se resuelve con la última vela **cerrada**: una barra solo entra
si su cierre (``índice + timeframe``) es anterior o igual a ``ahora - 1 minuto``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT
from .data_quality import dataset_hash

DEFAULT_DISCOVERY_DB = ROOT / "data" / "discovery.db"
SNAPSHOT_ROOT = ROOT / "data" / "discovery" / "snapshots"
AUDIT_ROOT = ROOT / "data" / "discovery" / "audit.log"

_UNIT_MINUTES = {
    "M": 1,
    "H": 60,
    "D": 24 * 60,
    "W": 7 * 24 * 60,
}


class SnapshotError(ValueError):
    """Snapshot ausente, corrupto o con un hash distinto al registrado."""


@dataclass(frozen=True)
class SnapshotInfo:
    path: str
    hash: str
    rows: int
    created_at: str


def timeframe_minutes(timeframe: str) -> int:
    """Minutos de una vela ``M5``, ``M15``, ``H1``, ``H4``, ``D1`` o ``W1``."""

    text = str(timeframe or "").strip().upper()
    match = re.fullmatch(r"([MHDW])(\d+)", text)
    if match is None:
        raise SnapshotError(f"timeframe desconocido: {timeframe!r}")
    unit, amount = match.group(1), int(match.group(2))
    if amount <= 0:
        raise SnapshotError(f"timeframe inválido: {timeframe!r}")
    return _UNIT_MINUTES[unit] * amount


def read_time(now: Any | None = None) -> pd.Timestamp:
    """Hora de lectura en UTC (inyectable en tests)."""

    stamp = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def closed_bars(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    now: Any | None = None,
) -> pd.DataFrame:
    """Descarta las velas cuyo cierre aún no ha ocurrido (margen 1 minuto)."""

    if len(frame) == 0:
        return frame
    cutoff = read_time(now) - pd.Timedelta(minutes=1)
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    closes = index + pd.Timedelta(minutes=timeframe_minutes(timeframe))
    return frame.loc[closes <= cutoff]


def _target_db(db_path: str | Path | None) -> Path:
    target = Path(db_path) if db_path else DEFAULT_DISCOVERY_DB
    return target.expanduser().resolve()


def snapshot_dir(db_path: str | Path | None = None) -> Path:
    """Directorio de snapshots; en tests sigue a la ``discovery.db`` temporal."""

    target = _target_db(db_path)
    if target == DEFAULT_DISCOVERY_DB.resolve():
        return SNAPSHOT_ROOT
    return target.parent / "snapshots"


def audit_path(db_path: str | Path | None = None) -> Path:
    target = _target_db(db_path)
    if target == DEFAULT_DISCOVERY_DB.resolve():
        return AUDIT_ROOT
    return target.parent / "audit.log"


def _safe_name(campaign_id: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(campaign_id or "").strip())
    if not text:
        raise SnapshotError("la campaña necesita id para su snapshot")
    return text


def snapshot_path_for(campaign_id: str, db_path: str | Path | None = None) -> Path:
    return snapshot_dir(db_path) / f"{_safe_name(campaign_id)}.parquet"


def _stored_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(result.index))
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    result.index = index
    result.index.name = "ts"
    return result.sort_index()


def write_snapshot(
    campaign_id: str,
    frame: pd.DataFrame,
    *,
    db_path: str | Path | None = None,
    now: Any | None = None,
) -> SnapshotInfo:
    """Escribe el snapshot una sola vez; si ya existe exige el mismo hash."""

    if len(frame) == 0:
        raise SnapshotError("Sin datos: el snapshot está vacío")
    normalized = _normalize(frame)
    digest = dataset_hash(normalized)
    path = snapshot_path_for(campaign_id, db_path)
    if path.exists():
        existing = _normalize(pd.read_parquet(path))
        if dataset_hash(existing) != digest:
            raise SnapshotError(
                f"el snapshot {path.name} ya existe con otro hash; "
                "no se sobrescribe"
            )
        return SnapshotInfo(
            path=_stored_path(path),
            hash=digest,
            rows=int(len(existing)),
            created_at=datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    normalized.to_parquet(temporary)
    temporary.replace(path)
    return SnapshotInfo(
        path=_stored_path(path),
        hash=digest,
        rows=int(len(normalized)),
        created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    )


def load_snapshot(path: str | Path, expected_hash: str | None = None) -> pd.DataFrame:
    """Lee el snapshot y verifica su hash; nunca toca la caché viva."""

    target = resolve_path(path)
    if not target.exists():
        raise SnapshotError(f"Sin datos: falta el snapshot {target}")
    try:
        frame = _normalize(pd.read_parquet(target))
    except Exception as exc:  # noqa: BLE001
        raise SnapshotError(
            f"snapshot ilegible {target.name}: {type(exc).__name__}: {exc}"
        ) from exc
    if expected_hash:
        actual = dataset_hash(frame)
        if actual != expected_hash:
            raise SnapshotError(
                f"snapshot corrupto {target.name}: hash {actual[:16]}… "
                f"!= {str(expected_hash)[:16]}…"
            )
    return frame


def append_audit(
    payload: dict[str, Any],
    *,
    db_path: str | Path | None = None,
) -> Path:
    """Añade una línea JSON al log de auditoría de discovery."""

    target = audit_path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        **payload,
    }
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return target


__all__ = [
    "AUDIT_ROOT",
    "SNAPSHOT_ROOT",
    "SnapshotError",
    "SnapshotInfo",
    "append_audit",
    "audit_path",
    "closed_bars",
    "load_snapshot",
    "read_time",
    "resolve_path",
    "snapshot_dir",
    "snapshot_path_for",
    "timeframe_minutes",
    "write_snapshot",
]
