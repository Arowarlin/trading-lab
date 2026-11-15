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
    commission_type: str
    commission_per_lot_usd: float | None
    commission_percent_per_side: float | None
    commission_side: str | None
    contract_size: float | None
    base_currency: str | None
    quote_currency: str | None
    source: str | None
    source_date: str | None
    effective_from: str | None
    source_url: str | None
    slippage_optimistic_bps: float
    slippage_conservative_bps: float
    slippage_assumption: str
    swap_long: float | None = None
    swap_short: float | None = None
    swap_unit: str = "percent_annual"
    swap_triple_weekday: int = 2
    swap_source: str = "Sin datos"
    swap_provisional: bool = True
    spread_bps: float | None = None

    def commission_bps(self, close: pd.Series) -> pd.Series:
        """Comisión por lado en bps para una serie de precios."""
        if not self.verified:
            raise ValueError(
                f"comisión sin verificar para {self.symbol}: no se inventa la cifra"
            )
        index = close.index
        if self.commission_type == "zero":
            return pd.Series(0.0, index=index, dtype=float)
        if self.commission_type == "percent_of_volume":
            if self.commission_percent_per_side is None:
                raise ValueError(f"porcentaje de comisión ausente para {self.symbol}")
            rate = float(self.commission_percent_per_side) / 100.0 * 10_000.0
            return pd.Series(rate, index=index, dtype=float)
        if self.commission_type == "per_lot_usd":
            if self.commission_per_lot_usd is None or self.contract_size is None:
                raise ValueError(f"comisión por lote incompleta para {self.symbol}")
            if self.quote_currency == "USD":
                notional_usd = float(self.contract_size) * pd.to_numeric(
                    close, errors="coerce"
                )
            elif self.base_currency == "USD":
                notional_usd = pd.Series(
                    float(self.contract_size), index=index, dtype=float
                )
            else:
                raise ValueError(
                    f"conversión de comisión no soportada para {self.symbol}"
                )
            if (notional_usd <= 0).any():
                raise ValueError(
                    f"precio inválido para convertir comisión de {self.symbol}"
                )
            return float(self.commission_per_lot_usd) / notional_usd * 10_000.0
        raise ValueError(f"tipo de comisión desconocido para {self.symbol}")


def spread_by_hour(frame: pd.DataFrame, point: float) -> pd.Series:
    """Spread mediano por hora en bps del precio (?ndice 0..23)."""
    if "spread" not in frame.columns:
        return pd.Series(dtype=float)
    close = pd.to_numeric(frame["close"], errors="coerce")
    raw = pd.to_numeric(frame["spread"], errors="coerce").fillna(0.0)
    bps = (
        (raw * float(point) / close * 10_000.0)
        .replace([float("inf"), float("-inf")], pd.NA)
        .dropna()
    )
    bps = bps[bps >= 0.0]
    if bps.empty:
        return pd.Series(dtype=float)
    return bps.groupby(bps.index.hour).median().sort_index()


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
    swap = data.get("swap") or {}
    swap_assets = swap.get("assets") or {}
    swap_item = swap_assets.get(str(symbol).upper()) or item.get("swap") or {}
    defaults = swap.get("defaults") or {}
    verified = bool(item.get("verified"))
    swap_long = (
        float(swap_item["long"])
        if swap_item.get("long") is not None
        else (float(defaults["long"]) if defaults.get("long") is not None else None)
    )
    swap_short = (
        float(swap_item["short"])
        if swap_item.get("short") is not None
        else (float(defaults["short"]) if defaults.get("short") is not None else None)
    )
    return AssetCost(
        symbol=str(symbol).upper(),
        verified=verified,
        commission_type=str(item.get("commission_type") or "per_lot_usd"),
        commission_per_lot_usd=(
            float(item["commission_per_lot_usd"])
            if verified and item.get("commission_per_lot_usd") is not None
            else None
        ),
        commission_percent_per_side=(
            float(item["commission_percent_per_side"])
            if verified and item.get("commission_percent_per_side") is not None
            else None
        ),
        commission_side=item.get("commission_side") if verified else None,
        contract_size=(
            float(item["contract_size"])
            if verified and item.get("contract_size") is not None
            else None
        ),
        base_currency=item.get("base_currency") if verified else None,
        quote_currency=item.get("quote_currency") if verified else None,
        source=item.get("source") if verified else None,
        source_date=item.get("source_date") if verified else None,
        effective_from=item.get("effective_from") if verified else None,
        source_url=item.get("source_url") if verified else None,
        slippage_optimistic_bps=float(
            item.get("slippage_optimistic_bps", slippage.get("optimistic_bps", 0.5))
        ),
        slippage_conservative_bps=float(
            item.get(
                "slippage_conservative_bps", slippage.get("conservative_bps", 2.0)
            )
        ),
        slippage_assumption=str(
            item.get(
                "slippage_assumption",
                slippage.get(
                    "assumption",
                    "Slippage explícito por lado; no se infiere de la comisión.",
                ),
            )
        ).strip(),
        swap_long=swap_long,
        swap_short=swap_short,
        swap_unit=str(swap_item.get("unit") or swap.get("unit") or "percent_annual"),
        swap_triple_weekday=int(
            swap_item.get("triple_swap_weekday", swap.get("triple_swap_weekday", 2))
        ),
        swap_source=str(
            swap_item.get("source") or swap.get("source") or "Sin datos"
        ),
        swap_provisional=swap_long is None or swap_short is None,
        spread_bps=(
            float(item["spread_bps"])
            if item.get("spread_bps") is not None
            else None
        ),
    )


__all__ = ["AssetCost", "asset_costs", "spread_by_hour"]
