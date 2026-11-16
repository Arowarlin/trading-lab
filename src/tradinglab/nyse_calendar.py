"""Calendario NYSE 2021-2027: festivos completos y cierres tempranos.

Fuente 2026-2027: https://www.nyse.com/markets/hours-calendars (consultada el
2026-11-16). La página solo publica 2026-2028; 2021-2025 se mantienen del
calendario histórico y quedan marcadas "por verificar" en el informe v3.2.

Este módulo es la **única** fuente de fechas para la réplica y para los inputs
``InpEarlyClose`` / ``InpHolidays`` del EA. Los tests comparan ambos.
"""

from __future__ import annotations

from datetime import date

VERSION = "3.2"

# Cierres completos (mercado cerrado todo el día), 2021-2027.
FULL_HOLIDAYS: dict[int, str] = {
    20210101: "Año Nuevo",
    20210118: "MLK",
    20210215: "Presidents",
    20210402: "Viernes Santo",
    20210531: "Memorial",
    20210705: "4 de julio (observado)",
    20210906: "Labor",
    20211125: "Acción de Gracias",
    20211224: "Navidad (observada)",
    20211231: "Año Nuevo 2022 (observado)",
    20220117: "MLK",
    20220221: "Presidents",
    20220415: "Viernes Santo",
    20220530: "Memorial",
    20220620: "Juneteenth (observado)",
    20220704: "4 de julio",
    20220905: "Labor",
    20221124: "Acción de Gracias",
    20221226: "Navidad (observada)",
    20230102: "Año Nuevo (observado)",
    20230116: "MLK",
    20230220: "Presidents",
    20230407: "Viernes Santo",
    20230529: "Memorial",
    20230619: "Juneteenth",
    20230704: "4 de julio",
    20230904: "Labor",
    20231123: "Acción de Gracias",
    20231225: "Navidad",
    20240101: "Año Nuevo",
    20240115: "MLK",
    20240219: "Presidents",
    20240329: "Viernes Santo",
    20240527: "Memorial",
    20240619: "Juneteenth",
    20240704: "4 de julio",
    20240902: "Labor",
    20241128: "Acción de Gracias",
    20241225: "Navidad",
    20250101: "Año Nuevo",
    20250120: "MLK",
    20250217: "Presidents",
    20250418: "Viernes Santo",
    20250526: "Memorial",
    20250619: "Juneteenth",
    20250704: "4 de julio",
    20250901: "Labor",
    20251127: "Acción de Gracias",
    20251225: "Navidad",
    20260101: "Año Nuevo",
    20260119: "MLK",
    20260216: "Presidents",
    20260403: "Viernes Santo",
    20260525: "Memorial",
    20260619: "Juneteenth",
    20260703: "4 de julio (observado)",
    20260907: "Labor",
    20261126: "Acción de Gracias",
    20261225: "Navidad",
    20270101: "Año Nuevo",
    20270118: "MLK",
    20270215: "Presidents",
    20270326: "Viernes Santo",
    20270531: "Memorial",
    20270618: "Juneteenth (observado)",
    20270705: "4 de julio (observado)",
    20270906: "Labor",
    20271125: "Acción de Gracias",
    20271224: "Navidad (observada)",
}

# Cierres tempranos a las 13:00 NY (HHMM), 2021-2027.
EARLY_CLOSES: dict[int, int] = {
    20211126: 1300,
    20221125: 1300,
    20230703: 1300,
    20231124: 1300,
    20240703: 1300,
    20241129: 1300,
    20241224: 1300,
    20250703: 1300,
    20251128: 1300,
    20251224: 1300,
    20261127: 1300,
    20261224: 1300,
    20271126: 1300,
}


def is_full_holiday(day: int | date) -> bool:
    key = int(day.strftime("%Y%m%d")) if isinstance(day, date) else int(day)
    return key in FULL_HOLIDAYS


def early_close_hhmm(day: int | date) -> int | None:
    key = int(day.strftime("%Y%m%d")) if isinstance(day, date) else int(day)
    return EARLY_CLOSES.get(key)


def effective_flat_min(day: int, flat_at: int, calendar: dict | None = None) -> int:
    """Minuto NY del cierre efectivo: min(flat_at, cierre temprano - 10)."""
    base = (int(flat_at) // 100) * 60 + int(flat_at) % 100
    close = (EARLY_CLOSES if calendar is None else calendar).get(int(day))
    if close is None:
        return base
    close_min = (int(close) // 100) * 60 + int(close) % 100
    return min(base, max(0, close_min - 10))


def holiday_input(start_year: int = 2026, end_year: int = 2027) -> str:
    """Festivos completos en formato YYYYMMDD separados por comas."""
    return ",".join(
        str(day)
        for day in sorted(FULL_HOLIDAYS)
        if start_year <= day // 10000 <= end_year
    )


def early_close_input() -> str:
    """Cierres tempranos en formato YYYYMMDD:HHMM separados por comas."""
    return ",".join(f"{day}:{hhmm:04d}" for day, hhmm in sorted(EARLY_CLOSES.items()))


__all__ = [
    "EARLY_CLOSES",
    "FULL_HOLIDAYS",
    "VERSION",
    "early_close_hhmm",
    "early_close_input",
    "effective_flat_min",
    "holiday_input",
    "is_full_holiday",
]
