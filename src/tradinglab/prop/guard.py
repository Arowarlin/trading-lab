from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .rules import PropRules

Severity = Literal["ok", "warn", "block", "breach"]


class PropError(RuntimeError):
    pass


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:  # Windows sin tzdata
        raise PropError(
            f"No encuentro la zona horaria '{name}'. Instala tzdata: uv pip install tzdata"
        ) from exc


@dataclass
class AccountState:
    """Foto del estado de la cuenta en el momento de evaluar."""

    balance: float
    equity: float
    initial_balance: float
    day_start_balance: float
    day_start_equity: float
    peak_balance: float | None = None
    peak_equity: float | None = None
    closed_pnl_today: float = 0.0
    total_profit: float = 0.0
    trading_days: int = 0
    open_positions: int = 0
    open_lots: float = 0.0
    server_time: datetime | None = None


@dataclass
class GuardReport:
    allowed: bool
    severity: Severity
    reason: str
    daily_floor: float
    max_floor: float
    effective_floor: float
    remaining_usd: float
    daily_used_pct: float
    max_used_pct: float
    profit_progress_pct: float
    target_reached: bool
    consistency_ok: bool | None
    effective_daily_limit: float
    effective_max_loss: float
    warnings: list[str] = field(default_factory=list)

    @property
    def breached(self) -> bool:
        return self.severity == "breach"

    def summary(self) -> str:
        return (
            f"{self.severity.upper()} · {self.reason}\n"
            f"  suelo efectivo: {self.effective_floor:,.2f} "
            f"(diario {self.daily_floor:,.2f} / máximo {self.max_floor:,.2f})\n"
            f"  colchón restante: {self.remaining_usd:,.2f}\n"
            f"  usado: diario {self.daily_used_pct:.1%} · máximo {self.max_used_pct:.1%}\n"
            f"  objetivo: {self.profit_progress_pct:.1%}"
        )


class PropGuard:
    """Evaluador de reglas de fondeo.

    No solo avisa: devuelve `allowed=False` cuando una orden rompería una regla.
    El bot DEBE consultarlo antes de cada orden y respetar la respuesta.
    """

    def __init__(self, rules: PropRules) -> None:
        self.rules = rules

    # ------------------------------------------------------------------ suelos

    def _bases(self, state: AccountState) -> tuple[float, float]:
        """Base del límite diario y del límite máximo, según el modo."""
        rules = self.rules
        daily_base = (
            state.day_start_balance if rules.daily_loss_mode == "balance" else state.day_start_equity
        )
        if rules.max_loss_mode == "static":
            max_base = state.initial_balance
        elif rules.max_loss_mode == "trailing_eod":
            max_base = state.peak_balance or state.initial_balance
        else:
            max_base = state.peak_equity or state.equity
        return daily_base, max_base

    def floors(self, state: AccountState) -> tuple[float, float]:
        rules = self.rules
        daily_base, max_base = self._bases(state)
        daily_floor = daily_base - rules.effective_daily_limit_usd
        max_floor = max_base - rules.effective_max_loss_usd
        return daily_floor, max_floor

    # ----------------------------------------------------------------- evaluar

    def evaluate(
        self,
        state: AccountState,
        *,
        proposed_lots: float = 0.0,
        risk_per_lot: float = 0.0,
        closing: bool = False,
        new_position: bool = True,
    ) -> GuardReport:
        rules = self.rules
        daily_floor, max_floor = self.floors(state)
        effective_floor = max(daily_floor, max_floor)

        warnings: list[str] = []
        equity = float(state.equity)
        daily_base, max_base = self._bases(state)

        used_daily = (daily_base - equity) / max(rules.daily_limit_usd, 1e-9)
        used_max = (max_base - equity) / max(rules.max_loss_usd, 1e-9)
        progress = (
            (equity - state.initial_balance) / rules.profit_target_usd
            if rules.profit_target_usd > 0
            else 0.0
        )

        consistency_ok: bool | None = None
        if rules.consistency_pct and state.total_profit > 0 and state.closed_pnl_today > 0:
            share = state.closed_pnl_today / state.total_profit
            consistency_ok = share <= rules.consistency_pct
            if not consistency_ok:
                warnings.append(
                    f"consistencia: el día de hoy aporta {share:.0%} del beneficio "
                    f"(máximo {rules.consistency_pct:.0%})"
                )

        target_reached = rules.profit_target_usd > 0 and equity >= (
            state.initial_balance + rules.profit_target_usd
        )

        remaining = equity - effective_floor

        def report(
            allowed: bool, severity: Severity, reason: str, *, extra: list[str] | None = None
        ) -> GuardReport:
            return GuardReport(
                allowed=allowed,
                severity=severity,
                reason=reason,
                daily_floor=daily_floor,
                max_floor=max_floor,
                effective_floor=effective_floor,
                remaining_usd=remaining,
                daily_used_pct=used_daily,
                max_used_pct=used_max,
                profit_progress_pct=progress,
                target_reached=target_reached,
                consistency_ok=consistency_ok,
                effective_daily_limit=rules.effective_daily_limit_usd,
                effective_max_loss=rules.effective_max_loss_usd,
                warnings=list(warnings) + list(extra or []),
            )

        if closing:
            return report(True, "ok", "cierre permitido aunque la cuenta esté al límite")

        if equity <= effective_floor:
            return report(
                False,
                "breach",
                f"cuenta fuera de límite: equity {equity:,.2f} <= suelo {effective_floor:,.2f}",
            )

        if target_reached:
            return report(False, "block", "objetivo de beneficio alcanzado: no abrir más riesgo")

        if remaining <= 0.25 * rules.effective_daily_limit_usd:
            warnings.append("colchón bajo: menos del 25% del límite diario disponible")

        if rules.max_lots is not None and proposed_lots > 0:
            if state.open_lots + proposed_lots > rules.max_lots + 1e-9:
                return report(
                    False,
                    "block",
                    f"límite de lotes/contratos: {state.open_lots:g} abiertos + "
                    f"{proposed_lots:g} > {rules.max_lots:g}",
                )

        if new_position and rules.max_positions is not None:
            if state.open_positions >= rules.max_positions:
                return report(
                    False,
                    "block",
                    f"máximo de posiciones abiertas alcanzado ({rules.max_positions})",
                )

        proposed_risk = abs(proposed_lots) * max(risk_per_lot, 0.0)
        if proposed_risk > 0:
            if proposed_risk > remaining:
                return report(
                    False,
                    "block",
                    f"la orden arriesga {proposed_risk:,.2f} y solo quedan "
                    f"{remaining:,.2f} de colchón",
                )
            if proposed_risk > 0.5 * remaining:
                warnings.append(
                    f"la orden usa {proposed_risk / remaining:.0%} del colchón restante"
                )

        if rules.max_open_risk_pct is not None and risk_per_lot > 0:
            open_risk = (state.open_lots + proposed_lots) * risk_per_lot
            cap = rules.account_size * rules.max_open_risk_pct
            if open_risk > cap:
                return report(
                    False,
                    "block",
                    f"riesgo abierto {open_risk:,.2f} > {cap:,.2f} ({rules.max_open_risk_pct:.1%})",
                )

        severity: Severity = "warn" if warnings else "ok"
        reason = "todo dentro de reglas" if not warnings else "avisos activos"
        return report(True, severity, reason)

    # --------------------------------------------------------- desde histórico

    @classmethod
    def state_from_equity(
        cls,
        rules: PropRules,
        equity: pd.Series,
        *,
        initial_balance: float | None = None,
        closed_pnl_today: float = 0.0,
        total_profit: float | None = None,
        open_positions: int = 0,
        open_lots: float = 0.0,
    ) -> AccountState:
        if equity is None or len(equity) == 0:
            raise PropError("hace falta al menos un snapshot de equity")

        series = equity.astype(float).dropna()
        if series.empty:
            raise PropError("la serie de equity está vacía")

        if series.index.tz is None:
            series.index = series.index.tz_localize("UTC")
        local = series.tz_convert(_tz(rules.reset_tz))

        today = local.index[-1].date()
        today_rows = local[local.index.date == today]
        day_start_equity = float(today_rows.iloc[0]) if len(today_rows) else float(local.iloc[-1])

        daily_close = local.groupby(local.index.date).last()
        peak_balance = float(daily_close.max())
        peak_equity = float(local.max())

        initial = float(initial_balance) if initial_balance is not None else float(series.iloc[0])
        last_equity = float(local.iloc[-1])
        profit = (
            float(total_profit) if total_profit is not None else last_equity - initial
        )

        return AccountState(
            balance=last_equity,
            equity=last_equity,
            initial_balance=initial,
            day_start_balance=float(today_rows.iloc[0]) if len(today_rows) else last_equity,
            day_start_equity=day_start_equity,
            peak_balance=peak_balance,
            peak_equity=peak_equity,
            closed_pnl_today=closed_pnl_today,
            total_profit=profit,
            trading_days=int(daily_close.shape[0]),
            open_positions=open_positions,
            open_lots=open_lots,
            server_time=local.index[-1].to_pydatetime(),
        )


__all__ = ["AccountState", "GuardReport", "PropGuard", "PropError"]
