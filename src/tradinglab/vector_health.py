"""Estado de Vector para `lab doctor`: servicio y frescura de all-*.jsonl."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT

VECTOR_PATHS = (
    Path("C:/Program Files/Vector/vector.exe"),
    ROOT / "data" / "vector" / "bin" / "vector.exe",
)
MARKET = ZoneInfo("America/New_York")
STALE_MINUTES = 15


def vector_binary() -> Path | None:
    found = shutil.which("vector")
    if found:
        return Path(found)
    for candidate in VECTOR_PATHS:
        if candidate.exists():
            return candidate
    return None


def service_running() -> bool:
    try:
        result = subprocess.run(
            ["sc", "query", "vector"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    return result.returncode == 0 and "RUNNING" in result.stdout.upper()


def latest_all_file() -> Path | None:
    folder = ROOT / "logs" / "vector"
    if not folder.exists():
        return None
    candidates = [folder / "all.jsonl", *sorted(folder.glob("all-*.jsonl"))]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def market_open(now: datetime) -> bool:
    local = now.astimezone(MARKET)
    if local.weekday() >= 5:
        return False
    return time(9, 30) <= local.time() <= time(16, 0)


def doctor_status(now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    binary = vector_binary()
    installed = binary is not None
    running = service_running() if installed else False
    latest = latest_all_file()
    age_min = (
        (moment.timestamp() - latest.stat().st_mtime) / 60.0 if latest else None
    )
    open_now = market_open(moment)
    stale = bool(open_now and (age_min is None or age_min > STALE_MINUTES))
    warn = bool(installed and (not running or stale))
    if not installed:
        detail = "no instalado (observabilidad opcional)"
    elif not running:
        detail = "instalado pero el servicio no corre"
    elif latest is None:
        detail = "servicio activo; sin all-*.jsonl" if open_now else "servicio activo"
    elif age_min is not None and age_min > STALE_MINUTES:
        detail = (
            f"servicio activo; último all-*.jsonl hace {age_min:.0f} min"
            f"{' (mercado abierto)' if open_now else ' (mercado cerrado)'}"
        )
    else:
        detail = f"servicio activo; último all-*.jsonl hace {age_min:.0f} min"
    return {
        "installed": installed,
        "running": running,
        "binary": str(binary) if binary else None,
        "latest": str(latest) if latest else None,
        "age_min": age_min,
        "market_open": open_now,
        "stale": stale,
        "warn": warn,
        "detail": detail,
    }


__all__ = [
    "STALE_MINUTES",
    "doctor_status",
    "latest_all_file",
    "market_open",
    "service_running",
    "vector_binary",
]
