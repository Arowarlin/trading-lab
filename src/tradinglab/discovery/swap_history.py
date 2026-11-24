"""Swap histórico: tipos de referencia diarios de FRED y calibración (T13).

Series: DFF (EE. UU.), €STR/EONIA (zona euro), SONIA (Reino Unido) y call
money de Japón. Si no hay caché ni clave de FRED, todo queda **Sin datos**.
No se inventan tipos ni se descargan datos de pago.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

from ..config import ROOT, load_secrets
from ..propfund.costs import SwapSpec, load_profile
from ..propfund.instruments import resolve
from ..propfund.models import Market
from ..propfund.registry import load_registry

FRED_BASE = "https://api.stlouisfed.org/fred"
FRED_CACHE = ROOT / "data" / "cache" / "fred"
SERIES = {
    "USD": "DFF",
    "EUR": "ECBESTRVOLWGTTRMDMNRT",
    "EUR_LEGACY": "EONIARATE",
    "GBP": "IUDSOIA",
    "JPY": "IRSTCI01JPM156N",
}
START = "2003-01-01"
_SERIES_CACHE: dict[str, pd.Series | None] = {}
_PRICE_CACHE: dict[str, float | None] = {}


def _api_key() -> str | None:
    load_secrets()
    return os.getenv("FRED_API_KEY")


def _parse(payload: dict[str, Any]) -> pd.Series:
    observations = payload.get("observations") or []
    index: list[pd.Timestamp] = []
    values: list[float] = []
    for row in observations:
        raw = row.get("value")
        if raw in {None, ".", ""}:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue
        index.append(pd.Timestamp(row["date"]))
        values.append(value)
    if not index:
        return pd.Series(dtype=float)
    return pd.Series(values, index=pd.DatetimeIndex(index), dtype=float).sort_index()


def _cached(series_id: str, cache_dir: Path) -> pd.Series | None:
    files = sorted(
        cache_dir.glob(f"{series_id}_*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    for path in reversed(files):
        try:
            series = _parse(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if not series.empty:
            return series
    return None


def load_rate(
    series_id: str,
    *,
    cache_dir: Path = FRED_CACHE,
    allow_fetch: bool = True,
) -> pd.Series | None:
    """Serie diaria en % o ``None`` (Sin datos). Usa caché antes que red."""

    if series_id in _SERIES_CACHE:
        return _SERIES_CACHE[series_id]
    cached = _cached(series_id, cache_dir)
    needs_full_history = (
        series_id == "DFF"
        and cached is not None
        and cached.index.min() > pd.Timestamp(START) + pd.Timedelta(days=30)
    )
    if cached is not None and not needs_full_history:
        _SERIES_CACHE[series_id] = cached
        return cached
    if not allow_fetch:
        _SERIES_CACHE[series_id] = None
        return None
    key = _api_key()
    if not key:
        _SERIES_CACHE[series_id] = None
        return None
    try:
        response = httpx.get(
            f"{FRED_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": START,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        _SERIES_CACHE[series_id] = None
        return None
    series = _parse(payload)
    if series.empty:
        _SERIES_CACHE[series_id] = None
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{series_id}_t13_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    _SERIES_CACHE[series_id] = series
    return series


def _eur_series() -> pd.Series | None:
    estr = load_rate(SERIES["EUR"])
    eonia = load_rate(SERIES["EUR_LEGACY"])
    if estr is None:
        return eonia
    if eonia is None:
        return estr
    combined = pd.concat([eonia.rename("eonia"), estr.rename("estr")], axis=1)
    combined = combined.sort_index()
    values = combined["estr"].combine_first(combined["eonia"])
    return values.dropna()


def reference_series(symbol: str) -> pd.Series | None:
    """Tipo de referencia diario del símbolo, en % anual.

    FX: diferencial base − cotizada. Índices y oro: tipo USD.
    """

    canonical = resolve(symbol).id
    usd = load_rate(SERIES["USD"])
    eur = _eur_series()
    gbp = load_rate(SERIES["GBP"])
    jpy = load_rate(SERIES["JPY"])
    if canonical in {"EURUSD"}:
        if usd is None or eur is None:
            return None
        series = eur - usd
    elif canonical in {"GBPUSD"}:
        if usd is None or gbp is None:
            return None
        series = gbp - usd
    elif canonical in {"USDJPY"}:
        if usd is None or jpy is None:
            return None
        series = usd - jpy
    else:
        if usd is None:
            return None
        series = usd
    series = series.dropna().sort_index()
    if series.empty:
        return None
    full = pd.date_range(series.index.min(), max(series.index.max(), pd.Timestamp.today().normalize()), freq="D")
    return series.reindex(full).ffill().dropna()


def current_price(symbol: str, *, root: Path = ROOT) -> float | None:
    """Último cierre disponible en la caché; ``None`` si no hay datos."""

    canonical = resolve(symbol).id
    if canonical in _PRICE_CACHE:
        return _PRICE_CACHE[canonical]
    candidates = [
        root / "data" / "cache" / "discovery" / f"{canonical}_M5.parquet",
        root / "data" / "cache" / "mt5" / f"{canonical}_H1.parquet",
        root / "data" / "cache" / "dukascopy" / f"{canonical}_M1.parquet",
    ]
    value: float | None = None
    for path in candidates:
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path, columns=["close"])
        except Exception:  # noqa: BLE001
            continue
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if not closes.empty:
            value = float(closes.iloc[-1])
            break
    _PRICE_CACHE[canonical] = value
    return value


def historical_swap_spec(
    profile,
    *,
    as_of: datetime | str | None = None,
    root: Path = ROOT,
) -> tuple[SwapSpec | None, str]:
    """Devuelve (spec histórico, motivo). Sin datos si falta algo."""

    spec = SwapSpec.from_profile(profile)
    if spec is None:
        return None, "Sin datos: el perfil no tiene swap medido"
    series = reference_series(profile.symbol)
    if series is None:
        return None, "Sin datos: tipos de referencia FRED"
    price = current_price(profile.symbol, root=root)
    if price is None or price <= 0.0:
        return None, "Sin datos: precio de referencia"
    moment = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if moment.tzinfo is None:
        moment = moment.tz_localize("UTC")
    lookup = moment.normalize()
    if series.index.tz is None:
        lookup = lookup.tz_localize(None)
    rate = series.asof(lookup)
    if rate is None or not np.isfinite(float(rate)):
        return None, "Sin datos: tipo de referencia en la fecha"
    try:
        canonical = resolve(profile.symbol).id
        long_sign = 1 if canonical in {"EURUSD", "GBPUSD", "USDJPY"} else -1
        short_sign = -1 if long_sign == 1 else 1
        return (
            spec.with_historical(
                series,
                reference_price=price,
                reference_rate=float(rate),
                long_sign=long_sign,
                short_sign=short_sign,
            ),
            "OK",
        )
    except ValueError as exc:
        return None, f"Sin datos: {exc}"


def annual_swap_table(*, root: Path = ROOT) -> list[dict[str, Any]]:
    """Swap medio anual por año, cuenta, símbolo y lado (USD por lote)."""

    registry = load_registry()
    rows: list[dict[str, Any]] = []
    for account_id, account in sorted(registry.accounts.items()):
        if account.market is not Market.CFD or account.template:
            continue
        for symbol in ("US100", "US500", "US30", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"):
            if symbol not in account.allowed_instruments:
                continue
            try:
                profile = load_profile(account_id, symbol, firm=account.firm)
            except Exception:  # noqa: BLE001
                continue
            spec, reason = historical_swap_spec(profile, root=root)
            price = current_price(symbol, root=root)
            contract = resolve(symbol).contract_size or 1.0
            if spec is None or price is None or contract is None:
                rows.append(
                    {
                        "account": account_id,
                        "symbol": symbol,
                        "side": "long",
                        "year": "Sin datos",
                        "rate_pct": None,
                        "swap_usd": None,
                        "reason": reason,
                    }
                )
                continue
            series = spec.historical_rates
            assert series is not None
            # La columna USD convierte la divisa cotizada: USDJPY cotiza en JPY
            # y su nocional en USD es el tamaño de contrato (100.000 USD), no
            # precio × contrato (que daría yenes).
            notional_usd = (
                float(contract)
                if symbol == "USDJPY"
                else float(price) * float(contract)
            )
            for year in range(2003, datetime.now(timezone.utc).year + 1):
                window = series.loc[f"{year}-01-01" : f"{year}-12-31"]
                if window.empty:
                    continue
                for side, markup in (
                    ("long", spec.markup_long),
                    ("short", spec.markup_short),
                ):
                    sign = spec.long_sign if side == "long" else spec.short_sign
                    rate = sign * float(window.mean()) + float(markup)
                    swap_usd = rate / 100.0 * notional_usd
                    rows.append(
                        {
                            "account": account_id,
                            "symbol": symbol,
                            "side": side,
                            "year": year,
                            "rate_pct": round(rate, 4),
                            "swap_usd": round(swap_usd, 2),
                            "reason": "OK",
                        }
                    )
    return rows


def historical_swap_report(*, root: Path = ROOT) -> str:
    lines = [
        "# Swap histórico (T13)",
        "",
        "Fuente: tipos diarios de FRED (DFF, €STR/EONIA, SONIA, call money JP).",
        "`swap_t = (tipo_ref_t + markup_lado) · nocional · noches / 360`; el",
        "markup se calibra para reproducir el swap medido el 2026-11-23.",
        "El crédito sigue contando 0 en Discovery (`swap_credit: false`).",
        "",
        "- Índices/oro: largo `s=-1` (paga financiación), corto `s=+1`.",
        "- FX: largo `s=+1` sobre el diferencial base−cotizada, corto `s=-1`.",
        "- Si una fecha es anterior a la serie FRED, el trade usa el swap",
        "  estático medido y queda marcado `swap_source=static_fallback`.",
        "- CFD-006 US100/US500/US30 comparten `-7,33/-1,33` en `swap.yaml`;",
        "  por eso su tasa histórica es idéntica. No es un error de cálculo.",
        "",
        "| Cuenta | Símbolo | Lado | Año | Tipo % | Swap USD/lote/año |",
        "|---|---|---|---:|---:|---:|",
    ]
    rows = annual_swap_table(root=root)
    for row in rows:
        rate = "Sin datos" if row["rate_pct"] is None else f"{row['rate_pct']:.4f}"
        swap = "Sin datos" if row["swap_usd"] is None else f"{row['swap_usd']:.2f}"
        lines.append(
            f"| {row['account']} | {row['symbol']} | {row['side']} | {row['year']} | "
            f"{rate} | {swap} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "FRED_CACHE",
    "SERIES",
    "START",
    "annual_swap_table",
    "current_price",
    "historical_swap_report",
    "historical_swap_spec",
    "load_rate",
    "reference_series",
]
