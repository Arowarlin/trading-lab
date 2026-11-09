"""Contratos continuos de futuros mediante unión ajustada por rollover.

No descarga datos ni envía órdenes. Recibe contratos ordenados del más antiguo
al más nuevo y una fecha de roll por cada transición. El ajuste elimina el
salto artificial entre contratos sin cambiar la forma de los retornos.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close")


class ContinuousError(ValueError):
    pass


def _as_timestamp(value: date | str | pd.Timestamp) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp


def _slice_contract(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ContinuousError("el contrato debe tener índice DatetimeIndex")
    index = frame.index
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
        frame = frame.copy()
        frame.index = index
    mask = pd.Series(True, index=frame.index)
    if start is not None:
        mask &= frame.index >= start
    if end is not None:
        mask &= frame.index < end
    return frame.loc[mask].copy()


def stitch_continuous(
    contracts: list[tuple[str, pd.DataFrame]],
    roll_dates: Iterable[date | str | pd.Timestamp],
    *,
    method: str = "ratio",
    price_columns: tuple[str, ...] = PRICE_COLUMNS,
) -> pd.DataFrame:
    """Une contratos y ajusta precios para que el roll no cree un salto.

    `roll_dates[i]` es la fecha en la que el contrato i deja paso al i+1.
    `method="ratio"` multiplica el contrato antiguo por el cociente de precios;
    `method="difference"` lo desplaza por la diferencia. El volumen no se ajusta.
    """
    if len(contracts) < 2:
        raise ContinuousError("se necesitan al menos dos contratos")
    rolls = [_as_timestamp(value) for value in roll_dates]
    if len(rolls) != len(contracts) - 1:
        raise ContinuousError("roll_dates debe tener len(contracts)-1 fechas")
    if method not in {"ratio", "difference"}:
        raise ContinuousError("method debe ser ratio o difference")

    segments: list[tuple[str, pd.DataFrame]] = []
    for index, (name, frame) in enumerate(contracts):
        missing = [column for column in price_columns if column not in frame.columns]
        if missing:
            raise ContinuousError(f"{name}: faltan columnas {missing}")
        start = rolls[index - 1] if index > 0 else None
        end = rolls[index] if index < len(rolls) else None
        segment = _slice_contract(frame, start=start, end=end)
        if segment.empty:
            raise ContinuousError(f"{name}: segmento vacío con los rolls indicados")
        segment["contract"] = name
        segments.append((name, segment))

    adjusted: list[pd.DataFrame] = []
    next_frame: pd.DataFrame | None = None
    for position in range(len(segments) - 1, -1, -1):
        name, frame = segments[position]
        frame = frame.copy()
        if next_frame is not None:
            roll = rolls[position]
            current_at = frame[frame.index <= roll]
            next_at = next_frame[next_frame.index >= roll]
            if current_at.empty or next_at.empty:
                raise ContinuousError(
                    f"{name}: no hay precios en el roll {roll.date().isoformat()}"
                )
            current_price = float(current_at["close"].iloc[-1])
            next_price = float(next_at["open"].iloc[0])
            if current_price <= 0 or next_price <= 0:
                raise ContinuousError("precio no positivo en el roll")
            if method == "ratio":
                factor = next_price / current_price
                for column in price_columns:
                    frame[column] = frame[column].astype(float) * factor
            else:
                shift = next_price - current_price
                for column in price_columns:
                    frame[column] = frame[column].astype(float) + shift
        adjusted.append(frame)
        next_frame = adjusted[-1]

    out = pd.concat(list(reversed(adjusted))).sort_index()
    if out.index.has_duplicates:
        raise ContinuousError("los contratos se solapan en las fechas de roll")
    return out


__all__ = [
    "ContinuousError",
    "PRICE_COLUMNS",
    "stitch_continuous",
]
