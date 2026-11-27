"""Calendarios de mercado por instrumento (R2j).

NYSE 2003-2030 generado por reglas, con los cierres especiales en un conjunto
aparte para que el calendario regular siga coincidiendo exactamente con
``nyse_calendar`` (2021-2027). Metales/forex: Viernes Santo, Navidad y Año Nuevo
con observados. Los cierres tempranos solo son informativos; la decisión de qué
tramo queda fuera de sesión la toma ``_calendar_gap`` con el horario derivado.
"""

from __future__ import annotations

from datetime import date, timedelta

NYSE = "nyse"
FX_METAL = "fx_metal"
CME = "cme"

# Cierres especiales que no forman parte del calendario regular de NYSE.
NYSE_SPECIAL_CLOSURES: dict[int, str] = {
    20040611: "Cierre especial (Reagan)",
    20070102: "Cierre especial (Ford)",
    20121029: "Cierre especial (Sandy)",
    20121030: "Cierre especial (Sandy)",
    20181205: "Cierre especial (Bush)",
    20250109: "Cierre especial (Carter)",
}


def _easter(year: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _good_friday(year: int) -> date:
    return _easter(year) - timedelta(days=2)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _new_year_observed(year: int) -> date | None:
    """Año Nuevo observado, o None si caería el 31-dic del año anterior (ENG-1 C-07).

    Con el 1-ene en sábado, NYSE, CME y el FX no cierran el viernes 31-dic
    (p. ej. 2010-12-31, 2021-12-31): abren con normalidad.
    """

    observed = _observed(date(year, 1, 1))
    return None if observed.year != year else observed


def _key(day: date) -> int:
    return int(day.strftime("%Y%m%d"))


def _add(out: dict[int, str], day: date, label: str) -> None:
    out[_key(day)] = label


def nyse_holidays(start: int = 2003, end: int = 2030) -> dict[int, str]:
    """Festivos regulares NYSE (sin cierres especiales), con observados."""
    out: dict[int, str] = {}
    for year in range(start - 1, end + 2):
        new_year = date(year, 1, 1)
        observed = _new_year_observed(year)
        if observed is not None and year <= end:
            _add(out, observed, "Año Nuevo" if observed == new_year else "Año Nuevo (observado)")
        _add(out, _nth_weekday(year, 1, 0, 3), "MLK")
        _add(out, _nth_weekday(year, 2, 0, 3), "Presidents")
        _add(out, _good_friday(year), "Viernes Santo")
        _add(out, _last_weekday(year, 5, 0), "Memorial")
        if year >= 2022:
            juneteenth = date(year, 6, 19)
            observed = _observed(juneteenth)
            _add(
                out,
                observed,
                "Juneteenth"
                if observed == juneteenth
                else "Juneteenth (observado)",
            )
        july4 = date(year, 7, 4)
        observed = _observed(july4)
        _add(
            out,
            observed,
            "4 de julio" if observed == july4 else "4 de julio (observado)",
        )
        _add(out, _nth_weekday(year, 9, 0, 1), "Labor")
        _add(out, _nth_weekday(year, 11, 3, 4), "Acción de Gracias")
        christmas = date(year, 12, 25)
        observed = _observed(christmas)
        _add(
            out,
            observed,
            "Navidad" if observed == christmas else "Navidad (observada)",
        )
    return {key: value for key, value in out.items() if start <= key // 10000 <= end}


def nyse_early_closes(start: int = 2003, end: int = 2030) -> dict[int, int]:
    """Cierres tempranos NYSE a las 13:00 (solo informativos)."""
    holidays = nyse_holidays(start, end)
    out: dict[int, int] = {}
    for year in range(start, end + 1):
        july3 = date(year, 7, 3)
        if july3.weekday() < 5 and _key(july3) not in holidays:
            out[_key(july3)] = 1300
        thanksgiving = _nth_weekday(year, 11, 3, 4)
        black_friday = thanksgiving + timedelta(days=1)
        out[_key(black_friday)] = 1300
        dec24 = date(year, 12, 24)
        if dec24.weekday() < 5 and _key(dec24) not in holidays:
            out[_key(dec24)] = 1300
    return out


def fx_metal_holidays(start: int = 2003, end: int = 2030) -> dict[int, str]:
    """Festivos completos de metales/forex."""
    out: dict[int, str] = {}
    for year in range(start - 1, end + 2):
        _add(out, _good_friday(year), "Viernes Santo")
        for day, label in (
            (date(year, 12, 25), "Navidad"),
            (date(year, 1, 1), "Año Nuevo"),
        ):
            if year > end:
                continue
            observed = _new_year_observed(year) if label == "Año Nuevo" else _observed(day)
            if observed is None:
                continue
            _add(
                out,
                observed,
                label if observed == day else f"{label} (observado)",
            )
    return {key: value for key, value in out.items() if start <= key // 10000 <= end}


def is_special_closure(day: date) -> bool:
    return _key(day) in NYSE_SPECIAL_CLOSURES


def cme_holidays(start: int = 2010, end: int = 2030) -> dict[int, str]:
    """Cierres completos de los futuros de índices CME (Globex).

    Reglas para el producto de índice (ES/NQ): Año Nuevo, Viernes Santo,
    Memorial, Juneteenth (desde 2022), 4 de julio, Labor, Acción de Gracias y
    Navidad, con observados. MLK y Presidents no cierran el índice; los
    productos de tipos tienen su propio horario y no se mezclan aquí.
    """

    out: dict[int, str] = {}
    for year in range(start - 1, end + 2):
        for day, label in (
            (date(year, 1, 1), "Año Nuevo"),
            (_good_friday(year), "Viernes Santo"),
            (_last_weekday(year, 5, 0), "Memorial"),
            (date(year, 7, 4), "4 de julio"),
            (_nth_weekday(year, 9, 0, 1), "Labor"),
            (_nth_weekday(year, 11, 3, 4), "Acción de Gracias"),
            (date(year, 12, 25), "Navidad"),
        ):
            if year > end:
                continue
            observed = _new_year_observed(year) if label == "Año Nuevo" else _observed(day)
            if observed is None:
                continue
            _add(
                out,
                observed,
                label if observed == day else f"{label} (observado)",
            )
        if year >= 2022:
            juneteenth = date(year, 6, 19)
            observed = _observed(juneteenth)
            _add(
                out,
                observed,
                "Juneteenth" if observed == juneteenth else "Juneteenth (observado)",
            )
    return {key: value for key, value in out.items() if start <= key // 10000 <= end}


def cme_early_closes(start: int = 2010, end: int = 2030) -> dict[int, int]:
    """Sesiones cortas del índice CME, en hora de Nueva York (HHMM).

    Víspera del 4 de julio y Nochebuena a las 13:00; día después de Acción de
    Gracias a las 13:15. Solo se anotan si son días hábiles y no festivos.
    """

    holidays = cme_holidays(start, end)
    out: dict[int, int] = {}
    for year in range(start, end + 1):
        july3 = date(year, 7, 3)
        if july3.weekday() < 5 and _key(july3) not in holidays:
            out[_key(july3)] = 1300
        christmas_eve = date(year, 12, 24)
        if christmas_eve.weekday() < 5 and _key(christmas_eve) not in holidays:
            out[_key(christmas_eve)] = 1300
        thanksgiving = _nth_weekday(year, 11, 3, 4)
        black_friday = thanksgiving + timedelta(days=1)
        if _key(black_friday) not in holidays:
            out[_key(black_friday)] = 1315
    return out


def is_holiday(calendar: str | None, day: date) -> bool:
    if calendar == NYSE:
        return (
            _key(day) in nyse_holidays(2003, 2030)
            or _key(day) in NYSE_SPECIAL_CLOSURES
        )
    if calendar == FX_METAL:
        return _key(day) in fx_metal_holidays(2003, 2030)
    if calendar == CME:
        return _key(day) in cme_holidays(2010, 2030)
    return False


def holiday_reason(calendar: str | None, day: date) -> str | None:
    key = _key(day)
    if calendar == NYSE:
        if key in NYSE_SPECIAL_CLOSURES:
            return NYSE_SPECIAL_CLOSURES[key]
        return nyse_holidays(2003, 2030).get(key)
    if calendar == FX_METAL:
        return fx_metal_holidays(2003, 2030).get(key)
    if calendar == CME:
        return cme_holidays(2010, 2030).get(key)
    return None


def early_close_hhmm(calendar: str | None, day: date) -> int | None:
    if calendar == NYSE:
        return nyse_early_closes(2003, 2030).get(_key(day))
    if calendar == CME:
        return cme_early_closes(2010, 2030).get(_key(day))
    return None


def is_fx_short_day(day: date) -> bool:
    return (day.month == 12 and day.day == 24) or (
        day.month == 12 and day.day == 31
    )


def nyse_trading_days(year: int, month: int) -> list[date]:
    """Días hábiles NYSE de un mes (sin fines de semana ni festivos)."""

    if not 1 <= int(month) <= 12:
        raise ValueError(f"mes inválido: {month}")
    first = date(int(year), int(month), 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    days: list[date] = []
    day = first
    while day <= last:
        if day.weekday() < 5 and not is_holiday(NYSE, day):
            days.append(day)
        day += timedelta(days=1)
    return days


def month_turn_pairs(
    start: date, end: date, n: int, m: int
) -> list[tuple[date, date]]:
    """Pares (entrada, salida) del efecto cambio de mes.

    Entrada en el cierre del día hábil ``n`` antes de fin de mes (1 = último
    día hábil) y salida en el cierre del día hábil ``m`` del mes siguiente
    (1 = primer día hábil). Solo se devuelven los meses con un mes siguiente
    completamente dentro de ``[start, end]`` para no inventar el cierre.
    """

    n = int(n)
    m = int(m)
    if n < 1 or m < 1:
        raise ValueError("n y m deben ser >= 1")
    out: list[tuple[date, date]] = []
    year = int(start.year)
    month = int(start.month)
    while (year, month) <= (end.year, end.month):
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1
        trading = nyse_trading_days(year, month)
        following = nyse_trading_days(next_year, next_month)
        if len(trading) >= n and len(following) >= m:
            entry = trading[-n]
            exit_day = following[m - 1]
            if start <= entry <= end and start <= exit_day <= end:
                out.append((entry, exit_day))
        year, month = next_year, next_month
    return out


__all__ = [
    "CME",
    "FX_METAL",
    "NYSE",
    "NYSE_SPECIAL_CLOSURES",
    "cme_early_closes",
    "cme_holidays",
    "early_close_hhmm",
    "fx_metal_holidays",
    "holiday_reason",
    "is_fx_short_day",
    "is_holiday",
    "is_special_closure",
    "month_turn_pairs",
    "nyse_early_closes",
    "nyse_holidays",
    "nyse_trading_days",
]
