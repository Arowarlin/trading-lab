"""Alertas operativas y latido (dead-man's switch).

Canales soportados:
  * ntfy (recomendado): sin bot, solo un topic; opcional token.
  * Telegram: bot token + chat id.

Nunca imprime ni registra tokens. Si no hay canal configurado, el evento se
guarda en SQLite pero no se envía nada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .config import DEFAULT_DB
from .db import connect, init_db, utcnow


@dataclass(frozen=True)
class AlertConfig:
    enabled: bool
    channel: str
    ntfy_url: str
    ntfy_topic: str
    ntfy_token: str
    telegram_token: str
    telegram_chat: str
    cooldown_s: int
    heartbeat_url: str

    @classmethod
    def from_env(cls) -> "AlertConfig":
        # El CLI de alertas debe funcionar sin depender de que otro comando
        # haya cargado .env/keyring antes.
        try:
            from .config import load_secrets

            load_secrets()
        except Exception:
            pass
        channel = (os.getenv("ALERT_CHANNEL") or "ntfy").strip().lower()
        enabled = (os.getenv("ALERTS_ENABLED") or "1").strip().lower() not in {"0", "false", "no"}
        return cls(
            enabled=enabled,
            channel=channel,
            ntfy_url=(os.getenv("NTFY_URL") or "https://ntfy.sh").rstrip("/"),
            ntfy_topic=os.getenv("NTFY_TOPIC") or "",
            ntfy_token=os.getenv("NTFY_TOKEN") or "",
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN") or "",
            telegram_chat=os.getenv("TELEGRAM_CHAT_ID") or "",
            cooldown_s=int(os.getenv("ALERT_COOLDOWN_S") or "300"),
            heartbeat_url=os.getenv("HEALTHCHECKS_URL") or "",
        )

    @property
    def configured(self) -> bool:
        if not self.enabled:
            return False
        if self.channel == "ntfy":
            return bool(self.ntfy_topic)
        if self.channel == "telegram":
            return bool(self.telegram_token and self.telegram_chat)
        return False


@dataclass(frozen=True)
class AlertResult:
    ok: bool
    channel: str
    event: str
    skipped: bool = False
    error: str = ""


def _last_sent(db_path: str | Path, event: str) -> datetime | None:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT ts FROM alerts WHERE event = ? AND ok = 1 ORDER BY id DESC LIMIT 1",
            (event,),
        ).fetchone()
    if not row:
        return None
    try:
        return datetime.fromisoformat(row["ts"])
    except ValueError:
        return None


def _record(
    db_path: str | Path,
    *,
    event: str,
    severity: str,
    channel: str,
    ok: bool,
    error: str,
    message: str,
) -> None:
    try:
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO alerts(ts, event, severity, channel, ok, error, message) "
                "VALUES(?,?,?,?,?,?,?)",
                (utcnow(), event, severity, channel, 1 if ok else 0, error[:500], message[:1000]),
            )
    except Exception:
        pass


def send(
    event: str,
    message: str,
    *,
    severity: str = "warning",
    config: AlertConfig | None = None,
    db_path: str | Path = DEFAULT_DB,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> AlertResult:
    """Envía una alerta con deduplicación por evento y cooldown."""
    cfg = config or AlertConfig.from_env()
    init_db(db_path)
    message = message.strip()[:1000]
    now = now or datetime.now(timezone.utc)

    if not cfg.configured:
        _record(
            db_path,
            event=event,
            severity=severity,
            channel="none",
            ok=False,
            error="canal no configurado",
            message=message,
        )
        return AlertResult(False, "none", event, skipped=True, error="canal no configurado")

    last = _last_sent(db_path, event)
    if last and cfg.cooldown_s > 0:
        if (now - last).total_seconds() < cfg.cooldown_s:
            return AlertResult(True, cfg.channel, event, skipped=True)

    own_client = client is None
    http = client or httpx.Client(timeout=10)
    error = ""
    ok = False
    try:
        if cfg.channel == "ntfy":
            headers = {
                "Title": f"TradingLab {severity}",
                "Priority": "high" if severity in {"error", "critical"} else "default",
                "Tags": "warning" if severity == "warning" else "rotating_light",
            }
            if cfg.ntfy_token:
                headers["Authorization"] = f"Bearer {cfg.ntfy_token}"
            response = http.post(
                f"{cfg.ntfy_url}/{cfg.ntfy_topic}",
                content=message.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
            ok = True
        elif cfg.channel == "telegram":
            response = http.post(
                f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
                json={
                    "chat_id": cfg.telegram_chat,
                    "text": f"[TradingLab · {severity}] {event}\n{message}",
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
            ok = True
        else:
            error = f"canal desconocido: {cfg.channel}"
    except Exception as exc:
        # No incluir URLs ni tokens en el error (Telegram lleva el token en la URL).
        error = f"{type(exc).__name__}: fallo de envío"
    finally:
        if own_client:
            http.close()

    _record(
        db_path,
        event=event,
        severity=severity,
        channel=cfg.channel,
        ok=ok,
        error=error,
        message=message,
    )
    return AlertResult(ok, cfg.channel, event, error=error)


def heartbeat(
    *,
    config: AlertConfig | None = None,
    client: httpx.Client | None = None,
    db_path: str | Path = DEFAULT_DB,
) -> AlertResult:
    """Ping de latido; si no hay URL configurada es un no-op exitoso."""
    cfg = config or AlertConfig.from_env()
    if not cfg.heartbeat_url:
        return AlertResult(True, "heartbeat", "heartbeat", skipped=True)
    own_client = client is None
    http = client or httpx.Client(timeout=10)
    ok = False
    try:
        response = http.get(cfg.heartbeat_url)
        response.raise_for_status()
        ok = True
    except Exception:
        ok = False
    finally:
        if own_client:
            http.close()
    try:
        init_db(db_path)
        _record(
            db_path,
            event="heartbeat",
            severity="info",
            channel="healthchecks",
            ok=ok,
            error="" if ok else "heartbeat falló",
            message="ping",
        )
    except Exception:
        pass
    return AlertResult(ok, "heartbeat", "heartbeat", error="" if ok else "heartbeat falló")


def last_heartbeat(db_path: str | Path = DEFAULT_DB) -> str | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT ts FROM alerts WHERE event = 'heartbeat' AND ok = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row["ts"] if row else None


def last_alerts(limit: int = 10, db_path: str | Path = DEFAULT_DB) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT ts, event, severity, channel, ok, error FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


__all__ = ["AlertConfig", "AlertResult", "heartbeat", "last_alerts", "last_heartbeat", "send"]
