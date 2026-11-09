"""Offset del servidor MT5 por periodo, inferido de las propias barras.

El servidor cambia entre GMT+2 y GMT+3 con el horario de verano. Un offset
global desplaza todo el histórico. Aquí se detecta el offset de cada semana
comparando la primera/última barra (hora de servidor) con la apertura/cierre
semanal del mercado de EE. UU. (17:00 America/New_York). Después se aplica el
offset de cada barra, no uno global.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

US_EASTERN = ZoneInfo("America/New_York")
BAR_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "W1": 10080,
}


def _bar_delta(timeframe: str) -> pd.Timedelta:
    key = timeframe.upper()
    if key not in BAR_MINUTES:
        raise ValueError(f"timeframe no soportado para offset por periodo: {timeframe}")
    return pd.Timedelta(minutes=BAR_MINUTES[key])


def _week_start(ts: pd.Timestamp) -> date:
    iso = ts.isocalendar()
    return date.fromisocalendar(int(iso.year), int(iso.week), 1)


SESSION_OPEN_HOURS_ET = (17, 18)
SESSION_CLOSE_HOUR_ET = 17


def session_bounds(
    week_start: date,
    *,
    open_hour_et: int = 17,
    close_hour_et: int = SESSION_CLOSE_HOUR_ET,
) -> tuple[datetime, datetime]:
    """Apertura del domingo y cierre del viernes, en UTC, para una semana."""
    sunday = week_start - timedelta(days=1)
    friday = week_start + timedelta(days=4)
    open_utc = datetime.combine(
        sunday, time(int(open_hour_et), 0), tzinfo=US_EASTERN
    ).astimezone(timezone.utc)
    close_utc = datetime.combine(
        friday, time(int(close_hour_et), 0), tzinfo=US_EASTERN
    ).astimezone(timezone.utc)
    return open_utc, close_utc


def _half_hour(value: float) -> float:
    return round(value * 2.0) / 2.0


def _open_candidate(
    first: pd.Timestamp,
    week: date,
    *,
    open_hour_et: int,
    tolerance_hours: float,
) -> float | None:
    if first.weekday() != 0 or first.hour > 2:
        return None
    open_utc, _ = session_bounds(week, open_hour_et=open_hour_et)
    raw = (first.to_pydatetime() - open_utc).total_seconds() / 3600.0
    candidate = _half_hour(raw)
    if 0 <= candidate <= 14 and abs(raw - candidate) <= tolerance_hours:
        return candidate
    return None


def _close_candidate(
    last: pd.Timestamp,
    delta: pd.Timedelta,
    week: date,
    *,
    tolerance_hours: float,
) -> float | None:
    if last.weekday() != 4 or last.hour < 20:
        return None
    _, close_utc = session_bounds(week)
    raw = ((last + delta).to_pydatetime() - close_utc).total_seconds() / 3600.0
    candidate = _half_hour(raw)
    if 0 <= candidate <= 14 and abs(raw - candidate) <= tolerance_hours:
        return candidate
    return None


def infer_bar_offsets(
    server_index: pd.DatetimeIndex,
    timeframe: str = "M15",
    *,
    tolerance_hours: float = 0.25,
) -> pd.Series:
    """Devuelve el offset (horas) de cada barra.

    `server_index` contiene la hora de servidor etiquetada como UTC (lo que
    entrega MT5). Se agrupa por semana ISO y se compara el primer/último bar
    con la apertura/cierre de Nueva York. La apertura puede ser 17:00 o 18:00
    ET según el activo (forex vs metales/índices); se elige la que concuerda
    con el cierre del viernes. Las semanas incompletas o festivas se rellenan
    con la semana detectada más cercana.
    """
    if len(server_index) == 0:
        raise ValueError("sin barras para inferir el offset")
    index = pd.DatetimeIndex(server_index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    delta = _bar_delta(timeframe)
    frame = pd.DataFrame({"server": index})
    frame["week"] = [_week_start(ts) for ts in index]

    weekly_by_open: dict[int, dict[date, float]] = {
        hour: {} for hour in SESSION_OPEN_HOURS_ET
    }
    agreements: dict[int, set[date]] = {
        hour: set() for hour in SESSION_OPEN_HOURS_ET
    }
    for week, group in frame.groupby("week", sort=True):
        first = group["server"].iloc[0]
        last = group["server"].iloc[-1]
        close_offset = _close_candidate(
            last, delta, week, tolerance_hours=tolerance_hours
        )
        for open_hour in SESSION_OPEN_HOURS_ET:
            open_offset = _open_candidate(
                first,
                week,
                open_hour_et=open_hour,
                tolerance_hours=tolerance_hours,
            )
            if open_offset is None:
                continue
            weekly_by_open[open_hour][week] = open_offset
            if close_offset is not None and abs(open_offset - close_offset) <= 0.5:
                agreements[open_hour].add(week)

    candidates = [
        hour
        for hour in SESSION_OPEN_HOURS_ET
        if agreements[hour] and weekly_by_open[hour]
    ]
    if not candidates:
        raise ValueError(
            "no se pudo confirmar el offset por periodo: la apertura semanal "
            "no concuerda con el cierre del viernes"
        )
    best_hour = max(
        candidates,
        key=lambda hour: (
            len(agreements[hour]),
            len(weekly_by_open[hour]),
            -hour,
        ),
    )
    weekly = weekly_by_open[best_hour]
    all_weeks = sorted(set(frame["week"]))
    series = pd.Series(weekly, dtype=float).reindex(all_weeks)
    series = series.ffill().bfill()
    mapping = series.to_dict()
    offsets = pd.Series(
        [mapping[week] for week in frame["week"]],
        index=index,
        dtype=float,
        name="server_offset_hours",
    )
    return offsets


def offset_periods(
    server_index: pd.DatetimeIndex,
    offsets: pd.Series,
) -> list[dict]:
    """Resume los tramos consecutivos con el mismo offset, ya en UTC."""
    frame = pd.DataFrame(
        {"server": pd.DatetimeIndex(server_index), "offset": offsets.to_numpy()}
    )
    frame["utc"] = frame["server"] - pd.to_timedelta(frame["offset"], unit="h")
    changes = (frame["offset"] != frame["offset"].shift()).cumsum()
    periods: list[dict] = []
    for _, group in frame.groupby(changes, sort=False):
        periods.append(
            {
                "start": group["utc"].iloc[0].isoformat(),
                "end": group["utc"].iloc[-1].isoformat(),
                "offset": float(group["offset"].iloc[0]),
            }
        )
    return periods
