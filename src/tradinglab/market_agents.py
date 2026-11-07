"""Agentes por mercado y coordinador determinista.

No ejecuta órdenes ni activa bots. Enruta el análisis al agente existente y
combina señales con topes por símbolo/mercado; el resto queda en cash.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .agents.bridge import RATING_TO_TARGET
from .config import ROOT, Settings
from .instruments import get_instrument, list_instruments
from .profiles import load_profiles

MARKETS_FILE = ROOT / "config" / "market_agents.yaml"
DEFAULT_MAX_GROSS = 0.90
DEFAULT_MAX_PER_SYMBOL = 0.25
RATINGS = RATING_TO_TARGET


class MarketAgentError(ValueError):
    pass


@dataclass(frozen=True)
class MarketSpec:
    market: str
    label: str
    profile: str
    analysts: tuple[str, ...]
    max_weight: float
    description: str


def load_markets(path: str | Path | None = None) -> dict[str, MarketSpec]:
    path = Path(path) if path else MARKETS_FILE
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for market, item in (raw.get("markets") or {}).items():
        data = item or {}
        out[str(market)] = MarketSpec(
            market=str(market),
            label=str(data.get("label") or market),
            profile=str(data.get("profile") or ""),
            analysts=tuple(str(x) for x in (data.get("analysts") or [])),
            max_weight=float(data.get("max_weight") or 0.25),
            description=str(data.get("description") or ""),
        )
    return out


def market_for_symbol(symbol: str) -> str:
    try:
        instrument = get_instrument(symbol)
    except Exception as exc:
        raise MarketAgentError(str(exc)) from exc
    return instrument.asset_class


def run_market_agent(
    market: str,
    ticker: str,
    settings: Settings,
    *,
    mode: str = "lite",
    client=None,
    analysis_date: str | None = None,
) -> dict:
    """Enruta al agente existente tras validar que el símbolo es del mercado."""
    specs = load_markets()
    spec = specs.get(market)
    if spec is None:
        raise MarketAgentError(f"mercado desconocido: {market}")
    actual = market_for_symbol(ticker)
    if actual != market:
        raise MarketAgentError(
            f"{ticker} pertenece a {actual}, no a {market}"
        )
    if mode == "lite":
        from .agents.lite import run_lite_agent

        return run_lite_agent(
            ticker, analysis_date, settings, client=client
        )
    if mode == "deep":
        from .agents.bridge import run_tradingagents

        return run_tradingagents(
            ticker,
            analysis_date,
            analysts=",".join(spec.analysts) or "market,news",
        )
    raise MarketAgentError("mode debe ser lite o deep")


def coordinate(
    signals: list[dict],
    *,
    markets: dict[str, MarketSpec] | None = None,
    max_gross: float = DEFAULT_MAX_GROSS,
    max_per_symbol: float = DEFAULT_MAX_PER_SYMBOL,
) -> dict:
    """Combina señales de forma determinista, con topes y cash residual."""
    specs = markets if markets is not None else load_markets()
    if max_gross <= 0:
        raise MarketAgentError("max_gross debe ser > 0")
    allocations: dict[tuple[str, str], dict] = {}
    skipped: list[dict] = []
    for raw in signals or []:
        signal = dict(raw or {})
        symbol = str(signal.get("symbol") or "").strip().upper()
        rating = str(signal.get("rating") or "Hold")
        try:
            confidence = min(max(float(signal.get("confidence") or 0.0), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            market = str(signal.get("market") or market_for_symbol(symbol))
        except Exception as exc:
            skipped.append({"symbol": symbol, "reason": str(exc)})
            continue
        if market not in specs:
            skipped.append({"symbol": symbol, "reason": f"mercado {market} sin config"})
            continue
        if rating not in RATINGS:
            skipped.append({"symbol": symbol, "reason": f"rating inválido {rating}"})
            continue
        target = RATINGS[rating]
        if target is None or target <= 0 or confidence <= 0:
            skipped.append(
                {
                    "symbol": symbol,
                    "rating": rating,
                    "reason": "Hold/REVIEW, sin señal o confianza 0",
                }
            )
            continue
        weight = min(target * confidence, max_per_symbol)
        if weight <= 1e-12:
            continue
        key = (market, symbol)
        current = allocations.get(key)
        if current is None or weight > current["weight"]:
            allocations[key] = {
                "market": market,
                "symbol": symbol,
                "rating": rating,
                "confidence": round(confidence, 6),
                "weight": weight,
            }

    by_market: dict[str, float] = {}
    for (market, _symbol), item in allocations.items():
        by_market[market] = by_market.get(market, 0.0) + item["weight"]
    for market, total in list(by_market.items()):
        cap = float(specs[market].max_weight)
        if total > cap > 0:
            scale = cap / total
            for (item_market, _symbol), item in allocations.items():
                if item_market == market:
                    item["weight"] *= scale
            by_market[market] = cap

    gross = sum(item["weight"] for item in allocations.values())
    if gross > max_gross:
        scale = max_gross / gross
        for item in allocations.values():
            item["weight"] *= scale
        gross = max_gross

    rows = sorted(
        (
            {
                **item,
                "weight": round(float(item["weight"]), 6),
            }
            for item in allocations.values()
            if item["weight"] > 1e-12
        ),
        key=lambda item: (item["market"], item["symbol"]),
    )
    gross = sum(item["weight"] for item in rows)
    market_totals: dict[str, float] = {}
    for item in rows:
        market_totals[item["market"]] = (
            market_totals.get(item["market"], 0.0) + item["weight"]
        )
    return {
        "allocations": rows,
        "cash_weight": round(max(0.0, 1.0 - gross), 6),
        "gross_weight": round(gross, 6),
        "by_market": {
            key: round(value, 6) for key, value in sorted(market_totals.items())
        },
        "skipped": skipped,
        "inputs": len(signals or []),
        "max_gross": max_gross,
        "max_per_symbol": max_per_symbol,
    }


def market_payload() -> dict:
    """Resumen para la consola: specs + instrumentos por mercado."""
    specs = load_markets()
    profiles = load_profiles()
    instruments = list_instruments()
    rows = []
    for market, spec in sorted(specs.items()):
        symbols = [item.symbol for item in instruments if item.asset_class == market]
        profile = profiles.get(spec.profile)
        rows.append(
            {
                "market": market,
                "label": spec.label,
                "profile": spec.profile,
                "profile_found": profile is not None,
                "analysts": list(spec.analysts),
                "max_weight": spec.max_weight,
                "description": spec.description,
                "symbols": symbols,
                "count": len(symbols),
            }
        )
    return {
        "markets": rows,
        "count": len(rows),
        "max_gross": DEFAULT_MAX_GROSS,
        "max_per_symbol": DEFAULT_MAX_PER_SYMBOL,
    }


__all__ = [
    "MARKETS_FILE",
    "MarketAgentError",
    "MarketSpec",
    "coordinate",
    "load_markets",
    "market_for_symbol",
    "market_payload",
    "run_market_agent",
]
