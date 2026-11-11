"""Objetivo de volatilidad: escala la exposición a un objetivo anual.

La volatilidad se estima con una **EWMA de retornos diarios** (halflife de 30
días por defecto) y el factor es `min(apalancamiento_max, objetivo / vol)`.

Sin lookahead: la volatilidad del día `t` se estima **solo con datos hasta
`t-1`**, y con rebalance semanal el factor se fija el lunes y se mantiene
durante la semana.

El perfil decide si la técnica se aplica: `vol_target.enabled: false` por
defecto en `config/profiles.yaml`.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import CONFIG_DIR, ROOT

PROFILES_FILE = ROOT / "config" / "profiles.yaml"
TRADING_DAYS = 252


def ewma_volatility(
    returns: pd.Series, halflife_days: int = 30, *, annualize: bool = True
) -> pd.Series:
    """EWMA de la volatilidad de `returns` (media de retornos al cuadrado)."""
    series = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    alpha = 1.0 - 0.5 ** (1.0 / max(1, int(halflife_days)))
    variance = series.pow(2).ewm(alpha=alpha, adjust=False).mean()
    vol = np.sqrt(variance.clip(lower=0.0))
    if annualize:
        vol = vol * math.sqrt(TRADING_DAYS)
    return vol.rename("ewma_vol")


def scale(
    returns: pd.Series,
    target_vol_annual: float,
    halflife_days: int = 30,
    max_leverage: float = 2.0,
    rebalance: str = "W",
) -> pd.Series:
    """Factor de escala por objetivo de volatilidad.

    - `returns`: retornos diarios (o por barra) del activo o de la cartera.
    - `target_vol_annual`: volatilidad anual objetivo (0,08 = 8 %).
    - `max_leverage`: tope del factor (2,0 = nunca más del doble).
    - `rebalance`: `W` (semanal, lunes) o `D` (diaria).

    Devuelve un factor >= 0 con la misma índice que `returns`. Donde no hay
    datos suficiente el factor es 1,0 (no se inventa exposición).
    """
    series = pd.Series(returns, dtype=float)
    if series.empty:
        return pd.Series(dtype=float, name="vol_factor")
    target = float(target_vol_annual)
    if target <= 0:
        raise ValueError("target_vol_annual debe ser > 0")
    cap = float(max_leverage)
    if cap <= 0:
        raise ValueError("max_leverage debe ser > 0")

    # la volatilidad del día t usa solo datos hasta t-1
    vol = ewma_volatility(series, halflife_days).shift(1)
    factor = (target / vol.replace(0.0, np.nan)).clip(lower=0.0, upper=cap)
    factor = factor.fillna(1.0)

    mode = str(rebalance or "W").upper()
    if mode == "W" and len(factor):
        weeks = pd.Series(series.index, index=factor.index).dt.to_period("W")
        # el lunes de cada semana fija el factor de toda la semana
        factor = factor.groupby(weeks).transform("first")
    elif mode not in {"W", "D"}:
        raise ValueError("rebalance debe ser W o D")
    return factor.rename("vol_factor")


def profile_vol_config(
    profile_id: str, path: Path | None = None
) -> dict:
    """`target_vol` y `vol_target.enabled` de un perfil (config/profiles.yaml)."""
    target: float | None = None
    enabled = False
    file_path = Path(path) if path else PROFILES_FILE
    if file_path.exists():
        try:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        section = (raw.get("profiles") or {}).get(str(profile_id)) or {}
        value = section.get("target_vol")
        if value is not None:
            try:
                target = float(value)
            except (TypeError, ValueError):
                target = None
        block = section.get("vol_target") or {}
        enabled = bool(block.get("enabled", False))
    return {"target_vol": target, "enabled": enabled}


def account_vol_config(account_id: str, path: Path | None = None) -> dict:
    """`target_vol` opcional de una cuenta (config/accounts.yaml)."""
    target: float | None = None
    file_path = Path(path) if path else CONFIG_DIR / "accounts.yaml"
    if file_path.exists():
        try:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        section = (raw.get("accounts") or {}).get(str(account_id)) or {}
        value = section.get("target_vol")
        if value is not None:
            try:
                target = float(value)
            except (TypeError, ValueError):
                target = None
    return {"target_vol": target}


__all__ = [
    "PROFILES_FILE",
    "TRADING_DAYS",
    "account_vol_config",
    "ewma_volatility",
    "profile_vol_config",
    "scale",
]
