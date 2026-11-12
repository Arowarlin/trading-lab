"""Preflight y candado de las sesiones programadas del carril IA.

La lógica vive en Python para poder probar las ventanas con y sin horario de
verano. Los scripts de PowerShell solo orquestan: candado, preflight, LLM o
comando, log y resumen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DEFAULT_DB, Settings, get_settings
from .db import connect, init_db

SESSIONS = ("london", "ny", "daily", "scalp", "manage")
SANTO_DOMINGO = ZoneInfo("America/Santo_Domingo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")

REFERENCES = {
    "london": ("EURUSD", "GBPUSD", "XAUUSD", "USDJPY"),
    "ny": ("US100.cash", "XAUUSD"),
    "daily": ("EURUSD", "XAUUSD"),
    "scalp": ("US100.cash", "XAUUSD"),
    "manage": ("EURUSD", "XAUUSD"),
}


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _zone(session: str) -> ZoneInfo:
    if session in {"daily", "ny", "scalp"}:
        return NEW_YORK
    if session == "london":
        return LONDON
    if session == "manage":
        return SANTO_DOMINGO
    raise ValueError(f"sesión desconocida: {session}")


def session_window(session: str, now: datetime | None = None) -> tuple[bool, str]:
    """Ventana local de la sesión; devuelve (ok, detalle legible)."""
    if session not in SESSIONS:
        return False, f"sesión desconocida: {session}"
    moment = _as_utc(now)
    zone = _zone(session)
    local = moment.astimezone(zone)
    current = local.time()
    weekday = local.weekday()
    if session == "london":
        ok = weekday < 5 and time(7, 0) <= current < time(10, 0)
        detail = f"London {local:%H:%M} ({zone.key}); ventana 07:00-10:00 L-V"
    elif session == "ny":
        ok = weekday < 5 and time(9, 30) <= current < time(10, 0)
        detail = f"NY {local:%H:%M} ({zone.key}); ventana 09:30-10:00 L-V"
    elif session == "daily":
        ok = weekday < 5 and time(16, 0) <= current < time(23, 0)
        detail = f"NY {local:%H:%M} ({zone.key}); ventana 16:00-23:00 L-V"
    elif session == "scalp":
        ok = weekday < 5 and time(9, 30) <= current < time(12, 0)
        detail = f"NY {local:%H:%M} ({zone.key}); ventana 09:30-12:00 L-V"
    else:  # manage: domingo 17:00 -> viernes 18:00 en República Dominicana
        if weekday == 5:
            ok = False
        elif weekday == 6:
            ok = current >= time(17, 0)
        elif weekday == 4:
            ok = current < time(18, 0)
        else:
            ok = True
        detail = (
            f"Santo Domingo {local:%H:%M} ({zone.key}); "
            "ventana domingo 17:00 -> viernes 18:00"
        )
    return ok, detail


def preflight(
    session: str,
    *,
    now: datetime | None = None,
    db_path: str | Path = DEFAULT_DB,
    settings: Settings | None = None,
    broker=None,
    connect: bool = True,
) -> dict:
    """Comprueba ventana, kill-switch, demo, MT5, stop global y mercado."""
    if session not in SESSIONS:
        return {"ok": False, "stage": "session", "reason": f"sesión desconocida: {session}"}
    moment = _as_utc(now)
    settings = settings or get_settings()
    window_ok, window_detail = session_window(session, moment)
    base = {
        "session": session,
        "now_utc": moment.isoformat(),
        "window": window_detail,
    }
    if not window_ok:
        return {**base, "ok": False, "stage": "window", "reason": window_detail}
    init_db(db_path)
    try:
        from .killswitch import load_state

        state = load_state(db_path)
        if state.active:
            return {
                **base, "ok": False, "stage": "killswitch",
                "reason": f"kill-switch activo: {state.reason}",
            }
    except Exception as exc:
        return {**base, "ok": False, "stage": "killswitch", "reason": str(exc)}

    created = False
    if broker is None:
        if not connect:
            return {**base, "ok": False, "stage": "mt5", "reason": "MT5 no disponible"}
        try:
            from .execution import get_mt5_broker

            broker = get_mt5_broker(settings, dry_run=True)
            broker.connect()
            created = True
        except Exception as exc:
            return {
                **base, "ok": False, "stage": "mt5",
                "reason": f"MT5 no responde: {exc}",
            }
    try:
        health = broker.health()
        if str(health.get("mode")) != "demo":
            return {
                **base, "ok": False, "stage": "demo",
                "reason": "la cuenta no es demo",
            }
        equity = float(health.get("equity") or 0)
        from .ai_trader import _daily_state, load_config

        cfg = load_config()
        daily = _daily_state(db_path, cfg, equity, broker=broker, settings=settings)
        if daily["global"]["hit"]:
            return {
                **base, "ok": False, "stage": "global_stop",
                "reason": "stop diario global tocado",
            }
        from .campaign import require_live_data

        market = require_live_data(
            broker, references=REFERENCES[session],
            max_age_minutes=15.0, now=moment,
        )
        return {
            **base, "ok": True, "stage": "ok", "reason": "ok",
            "equity": round(equity, 2), "market": market,
        }
    except Exception as exc:
        return {
            **base, "ok": False, "stage": "market",
            "reason": f"mercado cerrado o sin datos: {exc}",
        }
    finally:
        if created:
            try:
                broker.shutdown()
            except Exception:
                pass


def lock_acquire(path: str | Path, *, pid: int | None = None,
                 now: datetime | None = None, session: str | None = None,
                 max_age_hours: float = 12.0) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    moment = _as_utc(now)
    if target.exists():
        data: dict = {}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        stale = False
        try:
            stamp = datetime.fromisoformat(str(data.get("ts")))
            stale = (moment - _as_utc(stamp)).total_seconds() > max_age_hours * 3600
        except Exception:
            stale = False
        if not stale:
            return {
                "ok": False,
                "reason": f"lock activo PID {data.get('pid')}",
                "lock": data,
            }
        try:
            target.unlink()
        except Exception:
            return {"ok": False, "reason": "lock obsoleto no se pudo borrar"}
    data = {
        "pid": int(pid or os.getpid()),
        "ts": moment.isoformat(),
        "session": session,
    }
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "reason": "lock adquirido", "lock": data}


def lock_release(path: str | Path, *, pid: int | None = None) -> dict:
    target = Path(path)
    if not target.exists():
        return {"ok": True, "reason": "sin lock"}
    data: dict = {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if pid is not None and int(data.get("pid") or 0) not in (0, int(pid)):
        return {"ok": False, "reason": f"lock de otro PID {data.get('pid')}"}
    try:
        target.unlink()
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": True, "reason": "lock liberado"}


def recent_decisions(db_path: str | Path = DEFAULT_DB, limit: int = 8) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT ts, style, symbol, strategy, timeframe, decision, reason "
            "FROM ai_decisions WHERE source='forward' ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight y lock del carril IA")
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--session", required=True, choices=SESSIONS)
    pre.add_argument("--db", default=str(DEFAULT_DB))
    lock = sub.add_parser("lock-acquire")
    lock.add_argument("--path", required=True)
    lock.add_argument("--session", default=None)
    lock.add_argument("--pid", type=int, default=None)
    release = sub.add_parser("lock-release")
    release.add_argument("--path", required=True)
    release.add_argument("--pid", type=int, default=None)
    decisions = sub.add_parser("decisions")
    decisions.add_argument("--db", default=str(DEFAULT_DB))
    decisions.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        if args.command == "decisions":
            _print(recent_decisions(args.db, args.limit))
            return 0
        if args.command == "preflight":
            data = preflight(args.session, db_path=args.db)
        elif args.command == "lock-acquire":
            data = lock_acquire(args.path, pid=args.pid, session=args.session)
        else:
            data = lock_release(args.path, pid=args.pid)
    except Exception as exc:
        data = {"ok": False, "reason": str(exc)}
    _print(data)
    return 0 if data.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
