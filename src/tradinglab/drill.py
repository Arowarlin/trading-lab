"""Simulacro de emergencia (R8): solo paper/demo y con confirmación.

El simulacro cancela órdenes pendientes, cierra posiciones de los magics del
laboratorio, avisa por ntfy **y** Telegram, activa el kill-switch y lo
resetea con confirmación. Deja el resultado en `console_actions` con actor
`drill` y mide los tiempos.

Rechaza `mode=live` siempre.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .backup_check import verify_latest_backup
from .db import connect, init_db


class DrillError(RuntimeError):
    pass


OPEN_STATUSES = ("pending", "submitted", "accepted", "new", "partially_filled")


def simulate_drill(
    db_path: str | Path,
    settings,
    *,
    magics: tuple[int, ...] = (),
    check_backup: bool = False,
) -> dict:
    """Simulación **sin tocar nada**: qué haría el simulacro y con qué canales.

    Es la versión segura para la tarea programada mensual: no cancela órdenes,
    no cierra posiciones, no activa el kill-switch y no envía avisos. Solo
    informa y deja rastro en `console_actions` con actor `drill`.
    """
    if str(getattr(settings, "mode", "paper")).lower() == "live":
        raise DrillError("el simulacro no se ejecuta en live")

    init_db(db_path)
    started = time.time()
    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append(
            {
                "step": name,
                "ok": bool(ok),
                "detail": detail[:200],
                "elapsed_s": round(time.time() - started, 2),
            }
        )

    pending = 0
    positions = 0
    try:
        with connect(db_path) as con:
            marks = ", ".join("?" for _ in OPEN_STATUSES)
            pending = int(
                con.execute(
                    f"SELECT COUNT(*) FROM orders WHERE status IN ({marks})",
                    OPEN_STATUSES,
                ).fetchone()[0]
            )
            positions = int(
                con.execute("SELECT COUNT(*) FROM positions WHERE qty != 0").fetchone()[0]
            )
        step("inventario", True, f"{pending} órdenes abiertas, {positions} posiciones")
    except Exception as exc:
        step("inventario", False, str(exc))

    killswitch = False
    try:
        with connect(db_path) as con:
            row = con.execute(
                "SELECT active FROM killswitch ORDER BY id DESC LIMIT 1"
            ).fetchone()
        killswitch = bool(row["active"]) if row is not None else False
        step("kill-switch", True, "activo" if killswitch else "inactivo")
    except Exception as exc:
        step("kill-switch", False, str(exc))

    ntfy = False
    telegram = False
    try:
        from .alerts import AlertConfig

        cfg = AlertConfig.from_env()
        ntfy = bool(cfg.ntfy_topic)
        telegram = bool(cfg.telegram_token and cfg.telegram_chat)
        step(
            "canales",
            True,
            f"ntfy {'sí' if ntfy else 'no'} · telegram {'sí' if telegram else 'no'}",
        )
    except Exception as exc:
        step("canales", False, str(exc))

    backup_ok = True
    backup_report = None
    if check_backup:
        try:
            backup_report = verify_latest_backup(db_path)
            backup_ok = bool(backup_report.get("ok"))
            detail = str(backup_report.get("detail") or "")
        except Exception as exc:
            backup_ok = False
            detail = f"backup: {exc}"
            backup_report = {"ok": False, "detail": detail}
        step("backup", backup_ok, detail)

    result = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": str(getattr(settings, "mode", "paper")),
        "pending_orders": pending,
        "positions": positions,
        "killswitch_active": killswitch,
        "ntfy_configured": ntfy,
        "telegram_configured": telegram,
        "magics": list(magics),
        "elapsed_s": round(time.time() - started, 2),
        "backup_ok": backup_ok,
        "backup": backup_report,
        "steps": steps,
    }
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="drill_simulacion",
            params={"pending": pending, "positions": positions},
            result=f"simulación en {result['elapsed_s']}s",
            ok=True,
            actor="drill",
            detail=json.dumps(result, ensure_ascii=False)[:900],
        )
    except Exception:
        pass
    return result


def run_drill(
    db_path: str | Path,
    settings,
    *,
    broker=None,
    confirm: bool = False,
    armed: bool = False,
    magics: tuple[int, ...] = (),
    reset_killswitch: bool = True,
) -> dict:
    """Ejecuta el simulacro. Requiere operador armado y confirmación."""
    if str(getattr(settings, "mode", "paper")).lower() == "live":
        raise DrillError("el simulacro no se ejecuta en live")
    if not armed:
        raise DrillError("el simulacro exige el operador armado")
    if not confirm:
        raise DrillError("el simulacro exige confirmación explícita")

    init_db(db_path)
    started = time.time()
    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append(
            {"step": name, "ok": bool(ok), "detail": detail[:200], "elapsed_s": round(time.time() - started, 2)}
        )

    cancelled = 0
    closed = 0
    if broker is not None:
        try:
            for order in broker.open_orders() or []:
                broker.cancel_order(order["id"])
                cancelled += 1
        except Exception as exc:
            step("cancelar órdenes", False, str(exc))
        try:
            for position in broker.positions() or []:
                if not magics or int(position.get("magic") or 0) in set(magics):
                    broker.close_position(position["ticker"])
                    closed += 1
        except Exception as exc:
            step("cerrar posiciones", False, str(exc))
    step("cancelar órdenes", True, f"{cancelled} canceladas")
    step("cerrar posiciones", True, f"{closed} cerradas")

    from .alerts import send as send_alert

    try:
        send_alert("drill", f"Simulacro R8: {cancelled} órdenes, {closed} posiciones", severity="warning")
    except Exception as exc:
        step("aviso ntfy", False, str(exc))
    step("aviso ntfy", True)

    telegram = ""
    try:
        # `send_configured` envía al chat autorizado; antes se importaba un
        # `send` que no existe y el aviso de Telegram nunca salía.
        from .telegram import send_configured as send_telegram

        send_telegram(f"Simulacro R8: {cancelled} órdenes, {closed} posiciones")
        telegram = "enviado"
    except Exception as exc:
        telegram = f"sin telegram: {str(exc)[:120]}"
    step("aviso telegram", telegram == "enviado", telegram)

    killswitch = False
    try:
        from .killswitch import ensure as ensure_killswitch

        state, _ = ensure_killswitch(
            db_path,
            [],
            settings.risk,
            current=0.0,
            tz=settings.timezone,
        )
        killswitch = bool(state.active)
    except Exception as exc:
        step("kill-switch", False, str(exc))
    step("kill-switch", killswitch, "activado" if killswitch else "sin cambios")

    if reset_killswitch:
        try:
            from .killswitch import reset as reset_killswitch

            reset_killswitch(db_path, confirm=True)
        except Exception as exc:
            step("reset kill-switch", False, str(exc))
        step("reset kill-switch", True)

    result = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cancelled_orders": cancelled,
        "closed_positions": closed,
        "elapsed_s": round(time.time() - started, 2),
        "steps": steps,
    }
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="drill",
            params={"cancelled": cancelled, "closed": closed},
            result=f"simulacro en {result['elapsed_s']}s",
            ok=True,
            actor="drill",
            detail=json.dumps(result, ensure_ascii=False)[:900],
        )
    except Exception:
        pass
    return result


import json  # noqa: E402  (usado en el detalle del simulacro)

__all__ = ["DrillError", "run_drill", "simulate_drill"]
