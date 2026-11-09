"""Costes calibrados por activo para la investigación intradía."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from .config import ROOT

COSTS_PATH = ROOT / "config" / "costs.yaml"


@dataclass(frozen=True)
class AssetCost:
    symbol: str
    verified: bool
    commission_per_lot_usd: float | None
    commission_side: str | None
    contract_size: float | None
    quote_currency: str | None
    source: str | None
    source_date: str | None
    effective_from: str | None
    source_url: str | None
    slippage_optimistic_bps: float
    slippage_conservative_bps: float
    slippage_assumption: str

    def commission_bps(self, close: pd.Series) -> pd.Series:
        """Comisión por lado en bps para una serie de precios."""
        if (
            not self.verified
            or self.commission_per_lot_usd is None
            or self.contract_size is None
            or self.quote_currency != "USD"
        ):
            raise ValueError(
                f"comisión sin verificar para {self.symbol}: no se inventa la cifra"
            )
        notional_usd = float(self.contract_size) * pd.to_numeric(close, errors="coerce")
        if (notional_usd <= 0).any():
            raise ValueError(f"precio inválido para convertir comisión de {self.symbol}")
        return float(self.commission_per_lot_usd) / notional_usd * 10_000.0


def _load(path: Path | None = None) -> dict:
    target = Path(path) if path else COSTS_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"costes inválidos: {target}")
    return data


def asset_costs(symbol: str, path: Path | None = None) -> AssetCost:
    data = _load(path)
    assets = data.get("assets") or {}
    item = assets.get(str(symbol).upper()) or {}
    slippage = data.get("slippage") or {}
    verified = bool(item.get("verified"))
    return AssetCost(
        symbol=str(symbol).upper(),
        verified=verified,
        commission_per_lot_usd=(
            float(item["commission_per_lot_usd"])
            if verified and item.get("commission_per_lot_usd") is not None
            else None
        ),
        commission_side=item.get("commission_side") if verified else None,
        contract_size=(
            float(item["contract_size"])
            if verified and item.get("contract_size") is not None
            else None
        ),
        quote_currency=item.get("quote_currency") if verified else None,
        source=item.get("source") if verified else None,
        source_date=item.get("source_date") if verified else None,
        effective_from=item.get("effective_from") if verified else None,
        source_url=item.get("source_url") if verified else None,
        slippage_optimistic_bps=float(slippage.get("optimistic_bps", 0.5)),
        slippage_conservative_bps=float(slippage.get("conservative_bps", 2.0)),
        slippage_assumption=str(
            slippage.get(
                "assumption",
                "Slippage explícito por lado; no se infiere de la comisión.",
            )
        ).strip(),
    )


__all__ = ["AssetCost", "asset_costs"]
