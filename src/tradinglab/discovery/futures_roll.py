"""Ajuste de futuros por vencimiento (T31).

Sin `instrument_id` en la caché H1 de Databento, los cambios de contrato se
detectan por un salto >5σ en la barra de las 18:00 ET de un mes de
vencimiento (marzo, junio, septiembre, diciembre). Se generan dos series
back-adjusted (diferencia y ratio) sin tocar la caché original.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import ROOT

DATABENTO = ROOT / "data" / "cache" / "databento"
SNAPSHOTS = ROOT / "data" / "discovery" / "snapshots"
ROLL_MONTHS = (3, 6, 9, 12)
NY = "America/New_York"
SIGMA = 5.0


@dataclass(frozen=True)
class Roll:
    when: pd.Timestamp
    jump: float
    ratio: float
    sigma: float


def detect_rolls(
    frame: pd.DataFrame,
    *,
    sigma: float = SIGMA,
    months: tuple[int, ...] = ROLL_MONTHS,
) -> list[Roll]:
    """Cambios de contrato candidatos: 18:00 ET y salto > sigma·σ."""
    if frame.empty:
        return []
    close = pd.to_numeric(frame["close"], errors="coerce")
    local = close.index.tz_convert(NY)
    hourly_returns = close.pct_change()
    rolling_sigma = hourly_returns.rolling(20, min_periods=10).std().shift(1)
    rolls: list[Roll] = []
    for position in range(1, len(close)):
        stamp = local[position]
        if stamp.hour != 18 or stamp.month not in months:
            continue
        previous = close.iloc[position - 1]
        current = close.iloc[position]
        if not np.isfinite(previous) or previous <= 0 or not np.isfinite(current):
            continue
        jump = float(current - previous)
        ratio = float(current / previous)
        deviation = float(rolling_sigma.iloc[position] or 0.0)
        if deviation <= 0.0:
            continue
        if abs(float(hourly_returns.iloc[position])) <= sigma * deviation:
            continue
        rolls.append(
            Roll(
                when=close.index[position],
                jump=jump,
                ratio=ratio,
                sigma=abs(float(hourly_returns.iloc[position])) / deviation,
            )
        )
    return rolls


def adjust_diff(frame: pd.DataFrame, rolls: list[Roll]) -> pd.DataFrame:
    """Suma el salto a todo lo anterior: la serie antigua se pega a la nueva."""
    adjusted = frame.copy()
    for roll in rolls:
        mask = adjusted.index < roll.when
        for column in ("open", "high", "low", "close"):
            adjusted.loc[mask, column] = (
                pd.to_numeric(adjusted.loc[mask, column], errors="coerce")
                + roll.jump
            )
    return adjusted


def adjust_ratio(frame: pd.DataFrame, rolls: list[Roll]) -> pd.DataFrame:
    """Multiplica todo lo anterior por el ratio del salto."""
    adjusted = frame.copy()
    for roll in rolls:
        mask = adjusted.index < roll.when
        for column in ("open", "high", "low", "close"):
            adjusted.loc[mask, column] = (
                pd.to_numeric(adjusted.loc[mask, column], errors="coerce")
                * roll.ratio
            )
    return adjusted


def residual_jumps(
    adjusted: pd.DataFrame,
    rolls: list[Roll],
    *,
    sigma: float = SIGMA,
) -> dict[str, Any]:
    close = pd.to_numeric(adjusted["close"], errors="coerce")
    returns = close.pct_change()
    values = []
    for roll in rolls:
        try:
            position = close.index.get_loc(roll.when)
        except KeyError:
            continue
        values.append(abs(float(returns.iloc[position])))
    if not values:
        return {"n": 0, "max_abs_return": None, "over_sigma": 0}
    baseline = float(returns.std(ddof=1))
    threshold = sigma * baseline if baseline > 0 else 0.0
    over = sum(1 for value in values if value > threshold)
    return {
        "n": len(values),
        "max_abs_return": max(values),
        "threshold": threshold,
        "over_sigma": int(over),
    }


def build_symbol(
    symbol: str,
    *,
    source: Path = DATABENTO,
    output: Path = SNAPSHOTS,
) -> dict[str, Any]:
    path = source / f"{symbol}_H1.parquet"
    if not path.exists():
        return {"symbol": symbol, "status": "Sin datos"}
    frame = pd.read_parquet(path)
    rolls = detect_rolls(frame)
    diff = adjust_diff(frame, rolls)
    ratio = adjust_ratio(frame, rolls)
    output.mkdir(parents=True, exist_ok=True)
    diff_path = output / f"futuros_{symbol}_H1_diff.parquet"
    ratio_path = output / f"futuros_{symbol}_H1_ratio.parquet"
    diff.to_parquet(diff_path)
    ratio.to_parquet(ratio_path)
    residual_diff = residual_jumps(diff, rolls)
    residual_ratio = residual_jumps(ratio, rolls)
    mean_jump = float(np.mean([roll.jump for roll in rolls])) if rolls else 0.0
    mean_pct = (
        float(np.mean([abs(roll.ratio - 1.0) for roll in rolls])) * 100.0
        if rolls
        else 0.0
    )
    return {
        "symbol": symbol,
        "status": "ok",
        "rows": int(len(frame)),
        "rolls": len(rolls),
        "mean_jump": mean_jump,
        "mean_pct": mean_pct,
        "diff_path": str(diff_path),
        "ratio_path": str(ratio_path),
        "residual_diff": residual_diff,
        "residual_ratio": residual_ratio,
        "jumps": [
            {
                "when": str(roll.when),
                "jump": round(float(roll.jump), 6),
                "ratio": round(float(roll.ratio), 8),
                "sigma": round(float(roll.sigma), 2),
            }
            for roll in rolls
        ],
    }


def build_all(
    *,
    source: Path = DATABENTO,
    output: Path = SNAPSHOTS,
) -> dict[str, Any]:
    symbols = sorted(
        path.stem.replace("_H1", "")
        for path in source.glob("*_H1.parquet")
    )
    return {"symbols": [build_symbol(symbol, source=source, output=output) for symbol in symbols]}


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Futuros · ajuste por vencimiento (T31)",
        "",
        "Detección: salto >5σ en la barra de las 18:00 ET de marzo/junio/",
        "septiembre/diciembre. Series nuevas en `data/discovery/snapshots/`;",
        "la caché original no se toca.",
        "",
        "| Símbolo | Filas | Rolls | Salto medio | Salto medio % | Resid. diff >5σ | Resid. ratio >5σ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in payload["symbols"]:
        if item.get("status") != "ok":
            lines.append(f"| {item['symbol']} | Sin datos | — | — | — | — | — |")
            continue
        lines.append(
            f"| {item['symbol']} | {item['rows']} | {item['rolls']} | "
            f"{item['mean_jump']:.4f} | {item['mean_pct']:.4f}% | "
            f"{item['residual_diff']['over_sigma']} | "
            f"{item['residual_ratio']['over_sigma']} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DATABENTO",
    "ROLL_MONTHS",
    "SNAPSHOTS",
    "adjust_diff",
    "adjust_ratio",
    "build_all",
    "build_symbol",
    "detect_rolls",
    "render_report",
    "residual_jumps",
]
