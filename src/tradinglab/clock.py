"""Desviación de reloj: local, servidor MT5 y NTP público (UDP, solo stdlib).

Si el reloj local se desvía, las marcas de tiempo de las órdenes y de los
datos dejan de ser comparables con las del bróker. Umbrales:

- más de 2 s: **aviso**
- más de 10 s: **falla** (bloquea aperturas)

Un servidor NTP que no conteste no es un fallo: se informa "sin datos" y se
sigue con las demás fuentes.
"""

from __future__ import annotations

import socket
import struct
import time
from datetime import datetime, timezone

NTP_SERVERS = ("pool.ntp.org", "time.windows.com", "time.cloudflare.com")
NTP_PORT = 123
NTP_EPOCH_OFFSET = 2_208_988_800  # 1900-01-01 -> 1970-01-01

AVISO_S = 2.0
FALLA_S = 10.0

STATUS_OK = "ok"
STATUS_AVISO = "aviso"
STATUS_FALLA = "falla"
STATUS_SIN_DATOS = "sin_datos"


def _utc_now() -> float:
    return time.time()


def ntp_offset_s(
    server: str = NTP_SERVERS[0], *, timeout: float = 2.0
) -> float | None:
    """Desviación del reloj local frente a un servidor NTP, en segundos."""
    try:
        packet = bytearray(48)
        packet[0] = 0x23  # LI = 0, VN = 4, Mode = 3 (cliente)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sent = _utc_now()
            sock.sendto(bytes(packet), (server, NTP_PORT))
            data, _ = sock.recvfrom(1024)
            received = _utc_now()
        if len(data) < 48:
            return None
        seconds = struct.unpack("!I", data[40:44])[0]
        fraction = struct.unpack("!I", data[44:48])[0]
        ntp_time = seconds - NTP_EPOCH_OFFSET + fraction / 2**32
        # el reloj del servidor se compara con el instante de recepción
        return ntp_time - ((sent + received) / 2.0)
    except (OSError, struct.error, ValueError):
        return None


def mt5_offset_s(symbol: str = "EURUSD") -> float | None:
    """Desviación del reloj local frente al servidor MT5 (en horas)."""
    try:
        import MetaTrader5 as mt5

        if not mt5.initialize():
            return None
        # OJO: no se hace shutdown: el proceso puede tener la conexión MT5
        # en uso (el broker del forward). Solo se lee un tick.
        tick = mt5.symbol_info_tick(symbol)
    except Exception:
        return None
    if tick is None or not getattr(tick, "time", None):
        return None
    try:
        from .execution.mt5 import server_offset_from_tick

        offset_h = server_offset_from_tick(float(tick.time), _utc_now())
    except Exception:
        return None
    if offset_h is None:
        return None
    return float(offset_h) * 3600.0


def check_clock(*, now: datetime | None = None, symbol: str = "EURUSD") -> dict:
    """Estado del reloj: `ok`, `aviso`, `falla` o `sin_datos`."""
    sources: dict[str, float | None] = {}
    try:
        sources["ntp"] = ntp_offset_s()
    except Exception:
        sources["ntp"] = None
    try:
        sources["mt5"] = mt5_offset_s(symbol)
    except Exception:
        sources["mt5"] = None

    values = [value for value in sources.values() if value is not None]
    skew = max((abs(value) for value in values), default=None)
    result = {
        "checked_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "skew_s": skew,
        "sources": sources,
        "aviso_s": AVISO_S,
        "falla_s": FALLA_S,
        "status": STATUS_SIN_DATOS,
        "reason": "sin datos: no hay NTP ni terminal MT5 para comparar",
    }
    if skew is None:
        return result
    if skew > FALLA_S:
        result.update(
            {
                "status": STATUS_FALLA,
                "reason": f"reloj desviado {skew:.1f} s (bloquea aperturas a partir de {FALLA_S:.0f} s)",
            }
        )
        return result
    if skew > AVISO_S:
        result.update(
            {
                "status": STATUS_AVISO,
                "reason": f"reloj desviado {skew:.1f} s (aviso a partir de {AVISO_S:.0f} s)",
            }
        )
        return result
    result.update({"status": STATUS_OK, "reason": f"reloj sincronizado ({skew:.2f} s)"})
    return result


__all__ = [
    "AVISO_S",
    "FALLA_S",
    "NTP_SERVERS",
    "STATUS_AVISO",
    "STATUS_FALLA",
    "STATUS_OK",
    "STATUS_SIN_DATOS",
    "check_clock",
    "mt5_offset_s",
    "ntp_offset_s",
]
