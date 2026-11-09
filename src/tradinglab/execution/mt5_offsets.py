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


def session_bounds(week_start: date) -> tuple[datetime, datetime]:
    """Apertura del domingo y cierre del viernes, en UTC, para una semana."""
    sunday = week_start - timedelta(days=1)
    friday = week_start + timedelta(days=4)
    open_utc = datetime.combine(
        sunday, time(17, 0), tzinfo=US_EASTERN
    ).astimezone(timezone.utc)
    close_utc = datetime.combine(
        friday, time(17, 0), tzinfo=US_EASTERN
    ).astimezone(timezone.utc)
    return open_utc, close_utc


def _half_hour(value: float) -> float:
    return round(value * 2.0) / 2.0


def infer_bar_offsets(
    server_index: pd.DatetimeIndex,
    timeframe: str = "M15",
    *,
    tolerance_hours: float = 0.25,
) -> pd.Series:
    """Devuelve el offset (horas) de cada barra.

    `server_index` contiene la hora de servidor etiquetada como UTC (lo que
    entrega MT5). Se agrupa por semana ISO y se compara el primer/último bar
    con la apertura/cierre de Nueva York. Las semanas incompletas o festivas
    se rellenan con la semana detectada más cercana.
    """
    if len(server_index) == 0:
        raise ValueError("sin barras para inferir el offset")
    index = pd.DatetimeIndex(server_index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    delta = _bar_delta(timeframe)
    frame = pd.DataFrame({"server": index})
    frame["week"] = [_week_start(ts) for ts in index]

    weekly: dict[date, float] = {}
    for week, group in frame.groupby("week", sort=True):
        first = group["server"].iloc[0]
        last = group["server"].iloc[-1]
        open_utc, close_utc = session_bounds(week)
        candidates: list[float] = []

        if first.weekday() == 0 and first.hour <= 2:
            raw = (first.to_pydatetime() - open_utc).total_seconds() / 3600.0
            candidate = _half_hour(raw)
            if 0 <= candidate <= 14 and abs(raw - candidate) <= tolerance_hours:
                candidates.append(candidate)

        if last.weekday() == 4 and last.hour >= 20:
            raw = (
                (last + delta).to_pydatetime() - close_utc
            ).total_seconds() / 3600.0
            candidate = _half_hour(raw)
            if 0 <= candidate <= 14 and abs(raw - candidate) <= tolerance_hours:
                candidates.append(candidate)

        if not candidates:
            continue
        if len(candidates) >= 2 and abs(candidates[0] - candidates[1]) > 0.5:
            continue
        weekly[week] = candidates[0]

    if not weekly:
        raise ValueError(
            "no se pudo inferir el offset por periodo: faltan bordes semanales "
            "válidos (apertura domingo / cierre viernes)"
        )

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
