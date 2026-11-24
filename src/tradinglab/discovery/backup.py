"""Copia automática de ``discovery.db`` tras operaciones que la modifican.

* Se usa ``sqlite3.Connection.backup`` (copia consistente con WAL).
* Destino: ``<carpeta de discovery.db>/backups/discovery_<UTC>.db``; para la
  base canónica eso es ``data/backups/``.
* Retención: las 30 últimas más la primera de cada mes. **No se borra nada**:
  las copias retiradas se mueven a ``backups/_old/``.
* Se desactiva con ``discovery.backup: false`` en
  ``config/discovery/engine.yaml``.

El hook nunca tumba la operación principal: si la copia falla, deja un aviso en
el log y sigue.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load_engine_config
from .databank import DEFAULT_DISCOVERY_DB

log = logging.getLogger(__name__)

BACKUP_DIRNAME = "backups"
OLD_DIRNAME = "_old"
KEEP_RECENT = 30
_NAME = re.compile(r"^discovery_(\d{8}T\d{6}Z)\.db$")


def backup_dir(db_path: str | Path | None = None) -> Path:
    """Carpeta de copias: hermana de la base de datos."""
    source = Path(db_path) if db_path else DEFAULT_DISCOVERY_DB
    return source.parent / BACKUP_DIRNAME


def backup_enabled() -> bool:
    """Lee ``discovery.backup`` del YAML; si no se puede leer, copia igual."""
    try:
        return bool(load_engine_config().discovery.backup)
    except Exception as exc:  # noqa: BLE001 - el respaldo no debe romper nada
        log.warning("no se pudo leer discovery.backup (%s); se copia igual", exc)
        return True


def _stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _free_name(directory: Path, now: datetime | None = None) -> Path:
    """Nombre libre con el formato canónico; si choca, avanza un segundo."""
    moment = now or datetime.now(timezone.utc)
    for _ in range(120):
        candidate = directory / f"discovery_{_stamp(moment)}.db"
        if not candidate.exists():
            return candidate
        moment = moment + timedelta(seconds=1)
    raise RuntimeError(f"no hay nombre libre para la copia en {directory}")


def backup_discovery(
    db_path: str | Path | None = None,
    *,
    now: datetime | None = None,
    keep_recent: int = KEEP_RECENT,
) -> Path | None:
    """Copia ``discovery.db`` y devuelve la ruta; ``None`` si no existe."""
    source = Path(db_path) if db_path else DEFAULT_DISCOVERY_DB
    if not source.exists():
        return None
    directory = backup_dir(source)
    directory.mkdir(parents=True, exist_ok=True)
    destination = _free_name(directory, now)
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.commit()
        check = dst.execute("PRAGMA integrity_check").fetchone()
    finally:
        dst.close()
        src.close()
    if not check or str(check[0]).lower() != "ok":
        raise RuntimeError(f"copia corrupta: {destination} ({check})")
    apply_retention(directory, keep_recent=keep_recent)
    return destination


def _first_of_each_month(files: list[Path]) -> set[Path]:
    first: dict[str, Path] = {}
    for path in files:  # ordenados por nombre = orden temporal
        month = path.name[10:16]
        first.setdefault(month, path)
    return set(first.values())


def apply_retention(directory: Path, *, keep_recent: int = KEEP_RECENT) -> list[Path]:
    """Mueve a ``_old`` lo que no sea de las últimas N ni la primera del mes."""
    files = sorted(
        (path for path in directory.glob("discovery_*.db") if _NAME.match(path.name)),
        key=lambda path: path.name,
    )
    keep = set(files[-keep_recent:]) | _first_of_each_month(files)
    old_dir = directory / OLD_DIRNAME
    moved: list[Path] = []
    for path in files:
        if path in keep:
            continue
        old_dir.mkdir(parents=True, exist_ok=True)
        target = old_dir / path.name
        if target.exists():
            index = 1
            while (old_dir / f"{path.stem}-{index}{path.suffix}").exists():
                index += 1
            target = old_dir / f"{path.stem}-{index}{path.suffix}"
        path.replace(target)
        moved.append(target)
    return moved


def backup_after_action(db_path: str | Path | None = None) -> Path | None:
    """Hook seguro: copia si está activado y no propaga errores."""
    if not backup_enabled():
        return None
    try:
        return backup_discovery(db_path)
    except Exception as exc:  # noqa: BLE001 - nunca bloquea la operación
        log.warning("no se pudo copiar discovery.db: %s", exc)
        return None


__all__ = [
    "BACKUP_DIRNAME",
    "KEEP_RECENT",
    "OLD_DIRNAME",
    "apply_retention",
    "backup_after_action",
    "backup_dir",
    "backup_discovery",
    "backup_enabled",
]
