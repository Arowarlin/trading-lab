"""Gestor de riesgo multicuenta: nivel cuenta + nivel global.

* Nivel cuenta: límites de la firma (con colchón) + política de riesgo propia.
* Nivel global: exposición nocional por **subyacente** (NQ + MNQ + US100 CFD
  suman al mismo Nasdaq-100; GC + MGC + XAUUSD al mismo oro), concentración
  por firma y por estrategia.

El gestor global **no** toca los componentes protegidos: sus posiciones entran
como datos de solo lectura y, como mucho, bloquea nuevas asignaciones del
Prop Fund y emite alertas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import ROOT
from .instruments import notional_usd, resolve
from .models import PropAccount

RISK_PATH = ROOT / "config" / "propfund" / "risk.yaml"


@dataclass(frozen=True)
class PositionView:
    account: str
    firm: str
    strategy: str
    symbol: str
    quantity: float        # + largo / - corto, en lotes o contratos
    price: float
    contract_size: float | None = None
    risk_usd: float | None = None


@dataclass
class AccountSnapshot:
    account: str
    balance: float
    equity: float
    day_start_equity: float
    peak_equity: float
    trades_today: int = 0
    open_positions: int = 0
    open_risk_usd: float = 0.0


@dataclass
class RiskCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reasons": list(self.reasons), "metrics": self.metrics}


@dataclass(frozen=True)
class GlobalLimits:
    max_notional_per_underlying_usd: float = 400_000.0
    max_accounts_per_underlying: int = 3
    max_open_risk_per_firm_usd: float = 5_000.0
    max_open_risk_per_strategy_usd: float = 4_000.0
    max_total_open_risk_usd: float = 10_000.0


def load_global_limits(path: Path = RISK_PATH) -> GlobalLimits:
    if not path.exists():
        return GlobalLimits()
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("global") or {}
    return GlobalLimits(**{k: v for k, v in data.items() if k in GlobalLimits.__dataclass_fields__})


def check_account(acc: PropAccount, snap: AccountSnapshot | None, *, new_risk_usd: float) -> RiskCheck:
    """¿Puede esta cuenta asumir una operación con ``new_risk_usd`` de riesgo?"""
    reasons: list[str] = []
    metrics: dict = {}
    if snap is None:
        return RiskCheck(False, ["Sin datos: no hay snapshot de la cuenta"], metrics)

    pol = acc.risk
    per_trade_cap = snap.equity * pol.per_trade_risk_pct
    metrics["per_trade_cap_usd"] = round(per_trade_cap, 2)
    if new_risk_usd > per_trade_cap + 1e-9:
        reasons.append(f"riesgo {new_risk_usd:.2f} > tope por operación {per_trade_cap:.2f}")

    if snap.trades_today >= pol.max_trades_per_day:
        reasons.append(f"operaciones hoy {snap.trades_today} ≥ {pol.max_trades_per_day}")
    if snap.open_positions >= pol.max_open_positions:
        reasons.append(f"posiciones abiertas {snap.open_positions} ≥ {pol.max_open_positions}")

    day_loss = max(0.0, snap.day_start_equity - snap.equity)
    own_daily = snap.day_start_equity * pol.daily_risk_pct
    metrics["day_loss_usd"] = round(day_loss, 2)
    if day_loss + snap.open_risk_usd + new_risk_usd > own_daily + 1e-9:
        reasons.append("superaría el riesgo diario propio de la cuenta")

    lim = acc.limits
    buffer = 1.0 - pol.buffer_vs_firm_pct
    if lim.daily_loss is None or lim.max_loss is None:
        reasons.append("Sin datos: límites de la firma no verificados para esta cuenta")
    else:
        if day_loss + snap.open_risk_usd + new_risk_usd > lim.daily_loss * buffer:
            reasons.append("superaría el límite diario de la firma (con colchón)")
        if lim.drawdown_mode == "static":
            floor = acc.nominal_size - lim.max_loss
        elif lim.drawdown_mode in {"trailing_eod", "trailing_intraday"}:
            floor = snap.peak_equity - lim.max_loss
        else:
            floor = None
            reasons.append("Sin datos: modo de drawdown desconocido")
        if floor is not None:
            room = (snap.equity - floor) * buffer
            metrics["room_to_max_loss_usd"] = round(room, 2)
            if snap.open_risk_usd + new_risk_usd > room:
                reasons.append("superaría la pérdida máxima de la firma (con colchón)")
    return RiskCheck(not reasons, reasons, metrics)


def exposure_by_underlying(positions: list[PositionView]) -> dict[str, dict]:
    """Agrega nocional USD y cuentas por subyacente. Lo no medible queda en 'sin_datos'."""
    out: dict[str, dict] = defaultdict(lambda: {
        "net_notional_usd": 0.0, "gross_notional_usd": 0.0, "accounts": set(),
        "instruments": set(), "markets": set(), "sin_datos": [],
    })
    for pos in positions:
        item = resolve(pos.symbol)
        row = out[item.underlying]
        notional = notional_usd(pos.symbol, pos.quantity, pos.price, contract_size=pos.contract_size)
        row["accounts"].add(pos.account)
        row["instruments"].add(item.id)
        row["markets"].add(item.market.value)
        if notional is None:
            row["sin_datos"].append(f"{pos.account}:{item.id}")
            continue
        row["net_notional_usd"] += notional
        row["gross_notional_usd"] += abs(notional)
    return {
        key: {
            **{k: v for k, v in row.items() if k not in {"accounts", "instruments", "markets"}},
            "accounts": sorted(row["accounts"]),
            "instruments": sorted(row["instruments"]),
            "markets": sorted(row["markets"]),
            "cross_market": len(row["markets"]) > 1,
        }
        for key, row in out.items()
    }


def check_global(positions: list[PositionView], *, account: str, firm: str, strategy: str,
                 symbol: str, quantity: float, price: float, risk_usd: float,
                 contract_size: float | None = None,
                 limits: GlobalLimits | None = None) -> RiskCheck:
    """¿La nueva operación rompe algún límite consolidado?"""
    limits = limits or load_global_limits()
    candidate = PositionView(account, firm, strategy, symbol, quantity, price, contract_size, risk_usd)
    expo = exposure_by_underlying([*positions, candidate])
    item = resolve(symbol)
    row = expo[item.underlying]
    reasons: list[str] = []

    # Hedging cruzado: posición contraria en el mismo subyacente en otra cuenta.
    for pos in positions:
        if resolve(pos.symbol).underlying == item.underlying and pos.account != account:
            if pos.quantity * quantity < 0:
                reasons.append(
                    f"hedging entre cuentas: {pos.account} tiene {item.underlying} en sentido contrario"
                )
                break

    if row["gross_notional_usd"] > limits.max_notional_per_underlying_usd:
        reasons.append(
            f"exposición {item.underlying} {row['gross_notional_usd']:.0f} USD > "
            f"{limits.max_notional_per_underlying_usd:.0f}"
        )
    if len(row["accounts"]) > limits.max_accounts_per_underlying:
        reasons.append(f"{item.underlying} abierto en {len(row['accounts'])} cuentas")
    if row["sin_datos"]:
        reasons.append(f"Sin datos de tamaño de contrato: {', '.join(row['sin_datos'])}")

    by_firm: dict[str, float] = defaultdict(float)
    by_strategy: dict[str, float] = defaultdict(float)
    total = 0.0
    for pos in [*positions, candidate]:
        r = pos.risk_usd or 0.0
        by_firm[pos.firm] += r
        by_strategy[pos.strategy] += r
        total += r
    if by_firm[firm] > limits.max_open_risk_per_firm_usd:
        reasons.append(f"riesgo abierto en {firm} {by_firm[firm]:.0f} USD > {limits.max_open_risk_per_firm_usd:.0f}")
    if by_strategy[strategy] > limits.max_open_risk_per_strategy_usd:
        reasons.append(f"riesgo de la estrategia {strategy} {by_strategy[strategy]:.0f} USD excede el tope")
    if total > limits.max_total_open_risk_usd:
        reasons.append(f"riesgo total abierto {total:.0f} USD > {limits.max_total_open_risk_usd:.0f}")
    return RiskCheck(not reasons, reasons, {
        "underlying": item.underlying,
        "exposure": row,
        "risk_by_firm": dict(by_firm),
        "risk_by_strategy": dict(by_strategy),
        "total_open_risk_usd": total,
    })


__all__ = [
    "AccountSnapshot",
    "GlobalLimits",
    "PositionView",
    "RiskCheck",
    "check_account",
    "check_global",
    "exposure_by_underlying",
    "load_global_limits",
]
