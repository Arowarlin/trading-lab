"""E1 · Locks de coordinación entre sesiones.

Un lock es un directorio: ``.orquestador/locks/<resource>.lock``. ``os.mkdir``
es la operación atómica. Dentro vive ``owner.json``. Los locks liberados se
mueven a ``locks/released/``; nunca se borran.
"""

from __future__ import annotations

import json
import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import ROOT

LOCKS_DIR = ROOT / ".orquestador" / "locks"
POLL_S = 10.0
OLD_AFTER_S = 2 * 60 * 60


class LockError(RuntimeError):
    """Error base de los locks."""


class LockBusy(LockError):
    """El recurso ya está tomado."""

    def __init__(self, resource: str, owner: dict | None) -> None:
        self.resource = resource
        self.owner = owner or {}
        who = self.owner.get("owner") or "desconocido"
        super().__init__(f"lock ocupado: {resource} por {who}")


class LockNotOwner(LockError):
    """El solicitante no es el dueño del lock."""


class LockMissing(LockError):
    """El lock no existe."""


def _base(locks_dir: str | Path | None) -> Path:
    return Path(locks_dir) if locks_dir is not None else LOCKS_DIR


def _resource(resource: str) -> str:
    name = str(resource).strip()
    if not name or name in {".", ".."}:
        raise ValueError("recurso vacío")
    if any(char in name for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
        raise ValueError(f"recurso no válido: {resource!r}")
    return name


def _path(resource: str, locks_dir: str | Path | None) -> Path:
    return _base(locks_dir) / f"{_resource(resource)}.lock"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_owner(path: Path) -> dict | None:
    try:
        value = json.loads((path / "owner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_owner(path: Path, owner: str, cola: str | None) -> dict:
    payload = {
        "owner": str(owner),
        "cola": str(cola or ""),
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": _utc_now().isoformat(),
    }
    (path / "owner.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def acquire(
    resource: str,
    owner: str,
    *,
    wait_s: float = 0.0,
    poll_s: float | None = None,
    cola: str | None = None,
    locks_dir: str | Path | None = None,
) -> dict:
    """Toma el lock; reintenta hasta ``wait_s`` y lanza ``LockBusy``."""

    path = _path(resource, locks_dir)
    deadline = time.monotonic() + max(0.0, float(wait_s))
    interval = float(POLL_S if poll_s is None else poll_s)
    while True:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkdir(path)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LockBusy(_resource(resource), _read_owner(path)) from None
            time.sleep(max(0.0, min(interval, deadline - time.monotonic())))
            continue
        except OSError as exc:
            raise LockError(f"no se pudo crear {path}: {exc}") from exc
        try:
            payload = _write_owner(path, owner, cola)
        except Exception:
            try:
                os.rmdir(path)
            except OSError:
                pass
            raise
        return {
            "resource": _resource(resource),
            "owner": payload["owner"],
            "cola": payload["cola"],
            "path": str(path),
            "started_at": payload["started_at"],
        }


def release(
    resource: str,
    owner: str,
    *,
    locks_dir: str | Path | None = None,
) -> dict:
    """Libera solo si ``owner`` coincide; mueve el lock, no lo borra."""

    path = _path(resource, locks_dir)
    payload = _read_owner(path)
    if payload is None:
        raise LockMissing(f"lock inexistente: {_resource(resource)}")
    if str(payload.get("owner")) != str(owner):
        raise LockNotOwner(
            f"lock {_resource(resource)} es de {payload.get('owner')!r}, no de {owner!r}"
        )
    released = _base(locks_dir) / "released"
    released.mkdir(parents=True, exist_ok=True)
    stamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    target = released / f"{_resource(resource)}.{stamp}.lock"
    if target.exists():
        target = released / f"{_resource(resource)}.{stamp}-{os.getpid()}.lock"
    os.replace(path, target)
    return {
        "resource": _resource(resource),
        "owner": str(owner),
        "released": str(target),
    }


def status(*, locks_dir: str | Path | None = None) -> list[dict]:
    """Locks vivos con dueño y antigüedad; ``old`` a partir de 2 h."""

    base = _base(locks_dir)
    if not base.exists():
        return []
    now = _utc_now()
    out: list[dict] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir() or not path.name.endswith(".lock"):
            continue
        payload = _read_owner(path)
        started_at = None
        if payload:
            try:
                started_at = datetime.fromisoformat(str(payload["started_at"]))
            except (KeyError, ValueError):
                started_at = None
            if started_at is not None and started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at is None:
            started_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        age = max(0.0, (now - started_at).total_seconds())
        out.append(
            {
                "resource": path.name[: -len(".lock")],
                "owner": (payload or {}).get("owner", "desconocido"),
                "cola": (payload or {}).get("cola", ""),
                "pid": (payload or {}).get("pid"),
                "host": (payload or {}).get("host"),
                "started_at": started_at.isoformat(),
                "age_s": round(age, 3),
                "old": age > OLD_AFTER_S,
                "path": str(path),
            }
        )
    return out


@contextmanager
def held(
    resource: str,
    owner: str,
    *,
    wait_s: float = 0.0,
    poll_s: float | None = None,
    cola: str | None = None,
    locks_dir: str | Path | None = None,
) -> Iterator[dict]:
    """Context manager: adquiere al entrar y libera al salir, incluso con error."""

    info = acquire(
        resource,
        owner,
        wait_s=wait_s,
        poll_s=poll_s,
        cola=cola,
        locks_dir=locks_dir,
    )
    try:
        yield info
    finally:
        release(resource, owner, locks_dir=locks_dir)


__all__ = [
    "LOCKS_DIR",
    "LockBusy",
    "LockError",
    "LockMissing",
    "LockNotOwner",
    "acquire",
    "held",
    "release",
    "status",
]
