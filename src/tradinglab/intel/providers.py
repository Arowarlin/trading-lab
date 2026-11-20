"""Estado comprobable de las fuentes de información continua.

Nunca imprime valores de claves. Sirve para distinguir "no configurado" de
"configurado pero no verificado" y para no inventar proveedores disponibles.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import httpx
import yaml

from ..config import ROOT, load_secrets

INTEL_CONFIG = ROOT / "config" / "intel.yaml"
FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"


def _feed_status(path: str | Path | None = None) -> dict:
    target = Path(path) if path else INTEL_CONFIG
    if not target.exists():
        return {"configured": 0, "enabled": 0, "feeds": []}
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    feeds = (raw or {}).get("feeds", {}) or {}
    rows = [
        {"name": str(name), "enabled": bool(cfg.get("enabled", True))}
        for name, cfg in feeds.items()
        if isinstance(cfg, dict)
    ]
    return {
        "configured": len(rows),
        "enabled": sum(1 for row in rows if row["enabled"]),
        "feeds": rows,
    }


def verify_finnhub(
    api_key: str | None,
    *,
    symbol: str = "EURUSD",
    client: httpx.Client | None = None,
) -> dict:
    """Comprueba la clave con una lectura de cotización; no revela la clave."""
    if not api_key:
        return {"ok": False, "status": "missing", "message": "falta FINNHUB_API_KEY"}
    own = client is None
    http = client or httpx.Client(timeout=10)
    try:
        response = http.get(
            FINNHUB_QUOTE,
            params={"symbol": symbol.upper(), "token": api_key},
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "status": "error", "message": type(exc).__name__}
    finally:
        if own:
            http.close()
    if response.status_code in {401, 403}:
        return {
            "ok": False,
            "status": "unauthorized",
            "message": f"HTTP {response.status_code}",
        }
    if response.status_code >= 400:
        return {
            "ok": False,
            "status": "error",
            "message": f"HTTP {response.status_code}",
        }
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "status": "error", "message": "respuesta no JSON"}
    current = payload.get("c") if isinstance(payload, dict) else None
    return {
        "ok": bool(current),
        "status": "ok" if current else "empty",
        "message": "cotización recibida" if current else "sin cotización",
    }


def provider_status(
    *,
    secrets: dict[str, str] | None = None,
    feeds_path: str | Path | None = None,
    finnhub_key: str | None = None,
    check_finnhub: bool = False,
    client: httpx.Client | None = None,
) -> dict:
    """Estado de RSS, FRED, Finnhub y OpenBB sin exponer secretos."""
    sources = secrets if secrets is not None else load_secrets()
    configured = {
        key: sources.get(key) not in (None, "missing")
        for key in ("FRED_API_KEY", "FINNHUB_API_KEY")
    }
    key = finnhub_key
    if key is None and configured["FINNHUB_API_KEY"]:
        key = os.getenv("FINNHUB_API_KEY")
    finnhub = {
        "configured": configured["FINNHUB_API_KEY"],
        "verified": None,
        "status": "not_checked" if configured["FINNHUB_API_KEY"] else "missing",
        "message": "",
    }
    if check_finnhub:
        result = verify_finnhub(key, client=client)
        finnhub.update(
            {
                "verified": bool(result["ok"]),
                "status": result["status"],
                "message": result["message"],
            }
        )
    openbb = importlib.util.find_spec("openbb") is not None
    return {
        "rss": _feed_status(feeds_path),
        "fred": {
            "configured": configured["FRED_API_KEY"],
            "status": "configured" if configured["FRED_API_KEY"] else "missing",
        },
        "finnhub": finnhub,
        "openbb": {
            "installed": openbb,
            "status": "installed" if openbb else "not_installed",
        },
    }


__all__ = ["INTEL_CONFIG", "provider_status", "verify_finnhub"]
