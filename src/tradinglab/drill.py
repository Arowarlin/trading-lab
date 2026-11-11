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

from .db import init_db


class DrillError(RuntimeError):
    pass


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
        from .telegram import send as send_telegram

        telegram = str(send_telegram(f"Simulacro R8: {cancelled} órdenes, {closed} posiciones"))
    except Exception as exc:
        telegram = f"sin telegram: {str(exc)[:120]}"
    step("aviso telegram", True, telegram)

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

__all__ = ["DrillError", "run_drill"]
