"""Latidos externos Healthchecks.io, sin coste y sin imprimir URLs.

Cada check vive en keyring como ``HEALTHCHECKS_<CHECK>_URL``. Si falta, el
ping se omite y `lab doctor` lo avisa; nunca falla la tarea por un latido.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from .config import KEYRING_SERVICE

CHECKS = (
    "f13",
    "agents",
    "llmcompare",
    "intradayforward",
    "ai-london",
    "ai-ny",
    "ai-daily",
    "ai-scalp",
    "ai-manage",
    "drill",
    "backup",
    "pc",
)
STATUSES = {"ok", "start", "fail"}


class HeartbeatError(ValueError):
    pass


def _check_name(check: str) -> str:
    name = str(check or "").strip().lower().replace("_", "-")
    if name not in CHECKS:
        raise HeartbeatError(
            f"check desconocido: {check}; usa uno de: {', '.join(CHECKS)}"
        )
    return name


def _url_key(check: str) -> str:
    return "HEALTHCHECKS_" + _check_name(check).upper().replace("-", "_") + "_URL"


def _keyring():
    try:
        import keyring

        return keyring
    except Exception as exc:  # pragma: no cover - entorno sin keyring
        raise HeartbeatError(f"keyring no disponible: {exc}") from exc


def url_for(check: str) -> str | None:
    key = _url_key(check)
    try:
        return _keyring().get_password(KEYRING_SERVICE, key) or None
    except Exception:
        return None


def setup(check: str, url: str) -> dict:
    name = _check_name(check)
    value = str(url or "").strip()
    if not re.match(r"^https?://", value):
        raise HeartbeatError("la URL debe empezar por http:// o https://")
    try:
        _keyring().set_password(KEYRING_SERVICE, _url_key(name), value)
    except Exception as exc:
        raise HeartbeatError(f"no se pudo guardar en keyring: {exc}") from exc
    return {"check": name, "configured": True}


def status() -> dict:
    configured = {name: bool(url_for(name)) for name in CHECKS}
    return {
        "checks": configured,
        "configured": [name for name, ok in configured.items() if ok],
        "missing": [name for name, ok in configured.items() if not ok],
    }


def ping(
    check: str,
    status: str = "ok",
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> dict:
    name = _check_name(check)
    state = str(status or "").strip().lower()
    if state not in STATUSES:
        raise HeartbeatError(f"status inválido: {status}")
    url = url_for(name)
    if not url:
        return {
            "check": name,
            "status": state,
            "ok": True,
            "skipped": True,
            "reason": "URL no configurada",
            "ts": (now or datetime.now(timezone.utc)).isoformat(),
        }
    target = url.rstrip("/")
    if state == "start":
        target += "/start"
    elif state == "fail":
        target += "/fail"
    own = client is None
    http = client or httpx.Client(timeout=8)
    error = ""
    ok = False
    try:
        response = http.get(target)
        response.raise_for_status()
        ok = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        if own:
            http.close()
    return {
        "check": name,
        "status": state,
        "ok": ok,
        "skipped": False,
        "error": error,
        "ts": (now or datetime.now(timezone.utc)).isoformat(),
    }


__all__ = [
    "CHECKS",
    "HeartbeatError",
    "ping",
    "setup",
    "status",
    "url_for",
]
