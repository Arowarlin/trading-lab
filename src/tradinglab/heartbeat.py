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
API_KEY_NAME = "HEALTHCHECKS_API_KEY"
TZ = "America/Santo_Domingo"

# Tabla objetivo calculada desde los disparadores reales del Programador de
# tareas. El `pc` es un check de período, no de cron. La ventana de AI-Scalp
# real es 09:25-13:05; el cron 09-13 con 1 h de gracia cubre el cierre.
CHECK_SCHEDULES = {
    "f13": {"mode": "cron", "cron": "20 22 * * 1-5", "tz": TZ, "grace_min": 60},
    "agents": {"mode": "cron", "cron": "45 22 * * 1-5", "tz": TZ, "grace_min": 60},
    "llmcompare": {"mode": "cron", "cron": "30 18 * * 1-5", "tz": TZ, "grace_min": 60},
    "intradayforward": {
        "mode": "cron",
        "cron": "2-57/5 * * 1-5",
        "tz": TZ,
        "grace_min": 60,
    },
    "ai-london": {"mode": "cron", "cron": "5 3 * * 1-5", "tz": TZ, "grace_min": 60},
    "ai-ny": {"mode": "cron", "cron": "35 9,10 * * 1-5", "tz": TZ, "grace_min": 60},
    "ai-daily": {"mode": "cron", "cron": "15 18 * * 1-5", "tz": TZ, "grace_min": 60},
    "ai-scalp": {"mode": "cron", "cron": "* 9-13 * * 1-5", "tz": TZ, "grace_min": 60},
    "ai-manage": {
        "mode": "cron",
        "cron": "*/15 0-17 * * 1-5",
        "tz": TZ,
        "grace_min": 30,
    },
    "drill": {"mode": "cron", "cron": "0 3 * * 0", "tz": TZ, "grace_min": 120},
    "backup": {"mode": "cron", "cron": "0 13,19 * * 1-5", "tz": TZ, "grace_min": 60},
    "pc": {"mode": "period", "period_min": 10, "tz": TZ, "grace_min": 10},
}


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


def mask_to_days(mask: int) -> list[int]:
    """Días de la semana desde el bitmask del Programador (bit 0 = domingo)."""
    return [day for day in range(7) if int(mask) & (1 << day)]


def cron_days(days: list[int]) -> str:
    values = sorted(set(int(day) for day in days))
    if values == list(range(7)):
        return "*"
    if values == [1, 2, 3, 4, 5]:
        return "1-5"
    return ",".join(str(day) for day in values)


def cron_from_times(times: list[str], *, days: list[int] | None = None) -> list[str]:
    """Convierte horas ``HH:MM`` en expresiones cron, agrupando por minuto."""
    groups: dict[int, set[int]] = {}
    for value in times:
        try:
            hour, minute = (int(part) for part in str(value).split(":", 1))
        except (TypeError, ValueError) as exc:
            raise HeartbeatError(f"hora inválida: {value}") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise HeartbeatError(f"hora inválida: {value}")
        groups.setdefault(minute, set()).add(hour)
    dow = cron_days(days if days is not None else list(range(7)))
    return [
        f"{minute} {','.join(str(hour) for hour in sorted(hours))} * * {dow}"
        for minute, hours in sorted(groups.items())
    ]


def cron_from_weekly(days_mask: int, times: list[str]) -> list[str]:
    """Cron de un disparador semanal (p. ej. 62 = lunes a viernes)."""
    return cron_from_times(times, days=mask_to_days(days_mask))


def cron_from_daily(times: list[str]) -> list[str]:
    return cron_from_times(times)


def schedule_summary() -> dict:
    return {
        "timezone": TZ,
        "checks": {
            name: dict(values)
            for name, values in CHECK_SCHEDULES.items()
        },
        "api_key_configured": api_key_configured(),
    }


def setup_api(key: str) -> dict:
    value = str(key or "").strip()
    if not value:
        raise HeartbeatError("la API key no puede estar vacía")
    try:
        _keyring().set_password(KEYRING_SERVICE, API_KEY_NAME, value)
    except Exception as exc:
        raise HeartbeatError(f"no se pudo guardar en keyring: {exc}") from exc
    return {"configured": True}


def api_key_configured() -> bool:
    try:
        return bool(_keyring().get_password(KEYRING_SERVICE, API_KEY_NAME))
    except Exception:
        return False


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
    message: str = "",
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
        if message:
            response = http.post(target, content=str(message)[:1000].encode("utf-8"))
        else:
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
    "API_KEY_NAME",
    "CHECKS",
    "CHECK_SCHEDULES",
    "HeartbeatError",
    "api_key_configured",
    "cron_days",
    "cron_from_daily",
    "cron_from_times",
    "cron_from_weekly",
    "mask_to_days",
    "ping",
    "schedule_summary",
    "setup",
    "setup_api",
    "status",
    "url_for",
]
