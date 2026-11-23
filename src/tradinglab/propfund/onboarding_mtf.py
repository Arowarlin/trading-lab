"""Onboarding multi-timeframe: coste por operación frente al R típico (R2i-b).

Definiciones:

* ``R típico`` = mediana de ATR(14) del TF en los **últimos 12 meses** de
  Dukascopy (o desde ``usable_from`` si es posterior). No es una señal ni un
  backtest. Se publica también como ATR % del precio.
* ``coste`` = spread p75 del perfil (una vez por operación) + comisión
  (ida y vuelta) + slippage asumido por lado ×2, todo en unidades de precio.
* ``cost_R`` = coste / R típico. Viable si ``cost_R <= 0.10`` y el TF está
  dentro de ``usable_from``.
* Si falta spread, comisión, slippage, contrato o R: ``Sin datos``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ..config import ROOT
from ..discovery.config import load_engine_config
from ..discovery.data_sources import load_source
from ..discovery.resample import resample_session
from ..indicators import atr
from .costs import CostProfile, load_profile
from .instruments import resolve
from .registry import load_registry

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
DEFAULT_ACCOUNTS = ("CFD-001", "CFD-006")
MAX_COST_R = 0.10


def _sides(profile: CostProfile) -> float:
    return 1.0 if profile.commission_side == "round_turn" else 2.0


def commission_price(
    profile: CostProfile,
    *,
    price: float,
    contract_size: float | None,
) -> tuple[float | None, str | None]:
    """Comisión convertida a unidades de precio por operación (ida y vuelta)."""
    if profile.commission_type is None:
        return None, "Sin datos: comisión"
    if profile.commission_type == "zero":
        return 0.0, None
    value = profile.commission_value
    if value is None:
        return None, "Sin datos: comisión"
    sides = _sides(profile)
    if profile.commission_type == "per_lot_usd":
        if contract_size is None or contract_size <= 0:
            return None, "Sin datos: contract_size"
        return float(value) * sides / float(contract_size), None
    if profile.commission_type == "percent_of_volume":
        if price <= 0:
            return None, "Sin datos: precio"
        return float(price) * float(value) / 100.0 * sides, None
    return None, f"Sin datos: comisión {profile.commission_type}"


def operation_cost(
    profile: CostProfile,
    *,
    price: float,
    contract_size: float | None,
    slippage: float | None,
) -> dict[str, Any]:
    """Componentes del coste de una operación en unidades de precio."""
    missing: list[str] = []
    spread = profile.spread_p75_price
    if spread is None:
        missing.append("spread p75")
        spread = None
    commission, commission_error = commission_price(
        profile, price=price, contract_size=contract_size
    )
    if commission_error:
        missing.append(commission_error)
    if slippage is None:
        missing.append("slippage")
        slip = None
    else:
        slip = float(slippage) * 2.0
    total = None
    if spread is not None and commission is not None and slip is not None:
        total = float(spread) + float(commission) + float(slip)
    return {
        "spread": spread,
        "commission": commission,
        "slippage": slip,
        "total": total,
        "missing": missing,
    }


def assess_cost(
    cost: dict[str, Any],
    *,
    r_typical: float | None,
    usable_from: str | None,
    max_cost_r: float = MAX_COST_R,
) -> dict[str, Any]:
    """Aplica el umbral cost_R y la cobertura usable_from."""
    if cost["total"] is None:
        return {
            "cost_r": None,
            "viable": False,
            "reason": "Sin datos: " + "; ".join(cost["missing"]),
        }
    if r_typical is None or r_typical <= 0:
        return {
            "cost_r": None,
            "viable": False,
            "reason": "Sin datos: R típico",
        }
    cost_r = float(cost["total"]) / float(r_typical)
    if usable_from is None:
        return {
            "cost_r": cost_r,
            "viable": False,
            "reason": "fuera de usable_from",
        }
    if cost_r > float(max_cost_r) + 1e-12:
        return {
            "cost_r": cost_r,
            "viable": False,
            "reason": f"cost_R {cost_r:.4f} > {max_cost_r:.2f}",
        }
    return {"cost_r": cost_r, "viable": True, "reason": "OK"}


def median_atr_from_frame(
    frame: pd.DataFrame, start: str | pd.Timestamp | None = None
) -> float | None:
    if frame is None or len(frame) == 0:
        return None
    work = frame
    if start is not None:
        stamp = pd.Timestamp(start)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        work = work.loc[work.index >= stamp]
    if len(work) < 15:
        return None
    values = atr(work, 14).dropna()
    if len(values) == 0:
        return None
    value = float(values.median())
    return value if value > 0 else None


def last_12m_start(
    frame: pd.DataFrame, usable_from: str | None = None
) -> pd.Timestamp | None:
    """Inicio de los últimos 12 meses de datos (o usable_from si es posterior)."""
    if frame is None or len(frame) == 0:
        return None
    cutoff = pd.Timestamp(frame.index.max()) - pd.Timedelta(days=365)
    if usable_from:
        usable = pd.Timestamp(usable_from)
        if usable.tzinfo is None:
            usable = usable.tz_localize("UTC")
        cutoff = max(cutoff, usable)
    return cutoff


_R_CACHE: dict[tuple[str, str, str, str], dict[str, Any]] = {}


def _r_for(
    symbol: str,
    timeframe: str,
    usable_from: str | None,
    root: Path,
) -> dict[str, Any]:
    key = (symbol, timeframe, str(usable_from or ""), str(root))
    if key in _R_CACHE:
        return _R_CACHE[key]
    frame = load_source(symbol, timeframe, source="dukascopy", root=root).frame
    start = last_12m_start(frame, usable_from)
    work = frame if start is None else frame.loc[frame.index >= start]
    r_value = median_atr_from_frame(work)
    price = float(work["close"].median()) if len(work) else None
    result = {
        "r": r_value,
        "price": price,
        "start": start.date().isoformat() if start is not None else None,
        "rows": int(len(work)),
    }
    _R_CACHE[key] = result
    return result


def compute_r_values(
    symbols: tuple[str, ...],
    *,
    root: Path = ROOT,
    usable_from: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """R típico y precio de referencia por símbolo × TF (últimos 12 meses)."""
    usable_from = usable_from or {}
    out: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        m1 = load_source(symbol, "M1", source="dukascopy", root=root).frame
        for timeframe in TIMEFRAMES:
            usable = usable_from.get(f"dukascopy:{symbol}:{timeframe}")
            start = last_12m_start(m1, usable)
            source = m1 if start is None else m1.loc[m1.index >= start]
            frame = source if timeframe == "M1" else resample_session(source, timeframe)
            r_value = median_atr_from_frame(frame)
            price = float(frame["close"].median()) if len(frame) else None
            item = {
                "r": r_value,
                "price": price,
                "start": start.date().isoformat() if start is not None else None,
                "rows": int(len(frame)),
            }
            out[f"{symbol}:{timeframe}"] = item
            _R_CACHE[(symbol, timeframe, str(usable or ""), str(root))] = item
    return out


def cost_r_for(
    account_id: str,
    symbol: str,
    timeframe: str,
    *,
    config: Any = None,
    root: Path = ROOT,
    r_values: dict[str, dict[str, Any]] | None = None,
    max_cost_r: float = MAX_COST_R,
) -> dict[str, Any]:
    """Función única de cost_R usada por onboarding-mtf y discovery suggest."""
    from ..discovery.costs import assumed_slippage_for

    config = config or load_engine_config()
    canonical = resolve(symbol).id
    tf = str(timeframe).strip().upper()
    usable = config.data_quality.usable_from_for("dukascopy", canonical, tf)
    usable_text = usable.isoformat() if usable else None
    key = f"{canonical}:{tf}"
    r_item = (r_values or {}).get(key)
    if r_item is None:
        r_item = _r_for(canonical, tf, usable_text, root)
    row: dict[str, Any] = {
        "account": str(account_id).upper(),
        "symbol": canonical,
        "timeframe": tf,
        "cost_r": None,
        "viable": False,
        "reason": "",
        "cost": {},
        "r": r_item.get("r"),
        "price": r_item.get("price"),
        "atr_pct": None,
        "usable_from": usable_text,
    }
    if r_item.get("r") is not None and r_item.get("price"):
        row["atr_pct"] = 100.0 * float(r_item["r"]) / float(r_item["price"])
    try:
        account = load_registry().accounts[str(account_id).upper()]
        firm = load_registry().firm_of(account.id).id
        profile = load_profile(account.id, canonical, firm=firm)
    except Exception as exc:  # noqa: BLE001
        row["reason"] = f"Sin datos: perfil ({exc})"
        return row
    try:
        slippage, _source = assumed_slippage_for(canonical, config)
    except Exception:
        slippage = None
    cost = operation_cost(
        profile,
        price=float(r_item.get("price") or 0.0),
        contract_size=resolve(canonical).contract_size,
        slippage=slippage,
    )
    verdict = assess_cost(
        cost,
        r_typical=r_item.get("r"),
        usable_from=usable_text,
        max_cost_r=max_cost_r,
    )
    row.update(
        {
            "cost_r": verdict["cost_r"],
            "viable": verdict["viable"],
            "reason": verdict["reason"],
            "cost": cost,
        }
    )
    return row


def build_rows(
    accounts: tuple[str, ...] = DEFAULT_ACCOUNTS,
    *,
    r_values: dict[str, dict[str, Any]],
    config: Any = None,
    max_cost_r: float = MAX_COST_R,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    """Tabla cuenta × símbolo × TF (sin tocar MT5 ni escribir nada)."""
    config = config or load_engine_config()
    registry = load_registry()
    rows: list[dict[str, Any]] = []
    for account_id in accounts:
        account = registry.accounts.get(str(account_id).upper())
        if account is None:
            continue
        for symbol in account.allowed_instruments:
            item = resolve(symbol)
            for timeframe in TIMEFRAMES:
                rows.append(
                    cost_r_for(
                        account.id,
                        item.id,
                        timeframe,
                        config=config,
                        root=root,
                        r_values=r_values,
                        max_cost_r=max_cost_r,
                    )
                )
    return rows


def _fmt(value: float | None, digits: int = 6) -> str:
    if value is None:
        return "Sin datos"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "## Coste por operación frente al R típico",
        "",
        "R típico = mediana de ATR(14) del TF en los últimos 12 meses de "
        "Dukascopy (o desde `usable_from` si es posterior).",
        "Coste = spread p75 + comisión (ida/vuelta) + slippage asumido ×2.",
        "Viable si `cost_R <= 0.10` y el TF está dentro de `usable_from`.",
        "",
        "| Cuenta | Símbolo | TF | usable_from | R típico | ATR % precio | Coste | cost_R | Viable | Motivo |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        cost = row.get("cost") or {}
        lines.append(
            f"| {row['account']} | {row['symbol']} | {row['timeframe']} | "
            f"{row.get('usable_from') or '—'} | "
            f"{_fmt(row.get('r'))} | {_fmt(row.get('atr_pct'), 3)} | "
            f"{_fmt(cost.get('total'))} | "
            f"{_fmt(row.get('cost_r'), 4)} | "
            f"{'SÍ' if row.get('viable') else 'no'} | {row.get('reason') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_ACCOUNTS",
    "MAX_COST_R",
    "TIMEFRAMES",
    "assess_cost",
    "build_rows",
    "commission_price",
    "compute_r_values",
    "cost_r_for",
    "last_12m_start",
    "median_atr_from_frame",
    "operation_cost",
    "render_markdown",
]
