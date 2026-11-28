"""Entrada del motor: trayectoria de P&L de un día de sesión para 1 contrato (04 §2) — FUT-A2."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np


@dataclass(frozen=True)
class TradeSpec:
    """Una operación de 1 contrato: P&L neto, excursiones favorable y adversa (>= 0) y coste."""

    pnl_net: float
    mfe: float
    mae: float
    cost: float

    def __post_init__(self) -> None:
        if self.mfe < 0 or self.mae < 0 or self.cost < 0:
            raise ValueError("mfe, mae y cost deben ser >= 0")
        if not (-self.mae <= self.pnl_net <= self.mfe):
            raise ValueError("pnl_net debe estar entre -mae y mfe")


@dataclass(frozen=True)
class DayPath:
    session_date: date
    marks: np.ndarray
    n_trades: int
    exit_idx: tuple[int, ...]
    gross_pnl: float
    cost: float
    risk_usd: float | None = None
    flags: frozenset[str] = field(default_factory=frozenset)
    source: str = "synthetic"

    def validate(self) -> None:
        marks = np.asarray(self.marks, dtype=np.float64)
        if marks.ndim != 1 or marks.size == 0 or marks[0] != 0.0:
            raise ValueError("marks[0] debe ser 0")
        if not np.all(np.isfinite(marks)):
            raise ValueError("marks con valores no finitos")
        if self.cost < 0:
            raise ValueError("cost < 0")
        if abs(float(marks[-1]) - (self.gross_pnl - self.cost)) >= 1e-9:
            raise ValueError("marks[-1] != gross_pnl - cost")


def from_trades(session_date: date, trades: list[TradeSpec], *, risk_usd: float | None = None,
                flags: frozenset[str] = frozenset(), source: str = "synthetic") -> DayPath:
    """Construye el día: por operación, con acumulado c, añade c+mfe, c-mae, c+pnl_net (pico → valle)."""
    marks = [0.0]
    exits: list[int] = []
    c = 0.0
    for t in trades:
        marks.extend([c + t.mfe, c - t.mae, c + t.pnl_net])
        c += t.pnl_net
        exits.append(len(marks) - 1)
    gross = float(sum(t.pnl_net + t.cost for t in trades))
    cost = float(sum(t.cost for t in trades))
    return DayPath(session_date, np.asarray(marks, dtype=np.float64), len(trades), tuple(exits), gross, cost,
                   risk_usd, frozenset(flags), source)


def shift(day: DayPath, delta: float) -> DayPath:
    """Desplaza el P&L de cada operación en ``delta``: tras la salida de la operación k, todo suma k·delta."""
    marks = np.array(day.marks, dtype=np.float64, copy=True)
    for k, idx in enumerate(day.exit_idx, start=1):
        nxt = day.exit_idx[k] if k < len(day.exit_idx) else marks.size
        marks[idx:nxt] += k * delta
    return replace(day, marks=marks, gross_pnl=day.gross_pnl + day.n_trades * delta)
