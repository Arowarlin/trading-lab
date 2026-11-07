"""Interfaz de datos intradía de futuros (Etapa 3).

No descarga barras de pago. ProjectX/TopstepX exige una suscripción y su
endpoint `/api/History/retrieveBars`; hasta entonces se usa ES=F/NQ=F diario
como validación parcial, no como sustituto del intradía.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from . import fetch


class FuturesDataProvider(Protocol):
    name: str

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
        cache_dir: str | Path,
    ) -> pd.DataFrame: ...


class ProjectXFuturesProvider:
    """Stub explícito: no se implementa la descarga de pago."""

    name = "projectx:bars"

    def __init__(self, base_url: str = "https://api.topstepx.com") -> None:
        self.base_url = base_url

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
        cache_dir: str | Path,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "ProjectX /api/History/retrieveBars requiere suscripción de datos; "
            "no se descarga en esta fase."
        )


def daily_proxy(
    symbol: str,
    start: str,
    end: str,
    cache_dir: str | Path,
) -> pd.DataFrame:
    """Validación parcial con ES=F/NQ=F diarios (yfinance/caché existente)."""
    return fetch(symbol, start, end, cache_dir)


__all__ = ["FuturesDataProvider", "ProjectXFuturesProvider", "daily_proxy"]
