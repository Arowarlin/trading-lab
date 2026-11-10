"""Defensa de equity para cuentas de fondeo.

Implementa, con API propia, cinco conceptos habituales en sistemas de riesgo
para prop firms:

1. Drawdown *trailing* contra el máximo histórico de equity (HWM), que nunca
   baja mientras la cuenta está viva.
2. Zonas de aviso al 70%, 85% y 95% del límite de drawdown.
3. Factor de tamaño por zona: 1.00, 0.75, 0.50, 0.25 y 0 (sin entradas).
4. Circuit breaker diario por pérdida realizada o racha de pérdidas; una vez
   disparado queda latcheado hasta el siguiente día.
5. Cierre por reloj ("flat by") que se ejecuta una sola vez por sesión y es
   idempotente al confirmarse.

Nada de esto abre órdenes: solo decide si se puede abrir, con qué fracción del
tamaño normal y si toca aplanar. Cerrar o reducir nunca se bloquea.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DefenseLevel = Literal["ok", "caution", "alert", "critical", "breach"]

# (nivel, utilización mínima del límite, factor de tamaño)
_ZONES: tuple[tuple[DefenseLevel, float, float], ...] = (
    ("ok", 0.0, 1.0),
    ("caution", 0.70, 0.75),
    ("alert", 0.85, 0.50),
    ("critical", 0.95, 0.25),
)


class DefenseError(ValueError):
    """Configuración o dato inválido para la defensa de equity."""


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise DefenseError(
            f"no encuentro la zona horaria '{name}'. Instala tzdata: uv pip install tzdata"
        ) from exc


def _parse_hhmm(value: str) -> time:
    try:
        hour, minute = value.strip().split(":")
        return time(int(hour), int(minute))
    except Exception as exc:
        raise DefenseError(f"hora inválida {value!r}; usa HH:MM") from exc


def _local(now: datetime | None, tz: str) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_zone(tz))


# --------------------------------------------------------------- trailing DD


@dataclass(frozen=True)
class DrawdownReport:
    equity: float
    hwm: float
    drawdown_pct: float
    utilization: float
    level: DefenseLevel
    size_factor: float
    allowed: bool
    reason: str
    warnings: tuple[str, ...] = ()


class TrailingDrawdown:
    """Drawdown contra el máximo histórico de equity.

    El HWM solo sube. Si la cuenta marca un nuevo máximo, el suelo de
    drawdown sube con ella; si cae, el suelo se queda donde estaba.
    """

    def __init__(
        self,
        max_drawdown_pct: float = 0.05,
        *,
        start_equity: float | None = None,
    ) -> None:
        limit = float(max_drawdown_pct)
        if not 0.0 < limit < 1.0:
            raise DefenseError("max_drawdown_pct debe estar entre 0 y 1")
        if start_equity is not None and float(start_equity) <= 0:
            raise DefenseError("start_equity debe ser positivo")
        self.max_drawdown_pct = limit
        self._hwm = float(start_equity) if start_equity is not None else None

    @property
    def hwm(self) -> float | None:
        return self._hwm

    def floor(self) -> float | None:
        """Equity mínima permitida antes de incumplir (HWM - límite)."""
        if self._hwm is None:
            return None
        return self._hwm * (1.0 - self.max_drawdown_pct)

    def observe(self, equity: float) -> DrawdownReport:
        value = float(equity)
        if value <= 0:
            raise DefenseError("equity debe ser positivo")
        if self._hwm is None or value > self._hwm:
            self._hwm = value
        hwm = float(self._hwm)
        drawdown = max(0.0, (hwm - value) / hwm)
        utilization = drawdown / self.max_drawdown_pct

        level: DefenseLevel = "breach"
        size_factor = 0.0
        if utilization < 1.0:
            for name, threshold, factor in reversed(_ZONES):
                if utilization >= threshold:
                    level = name
                    size_factor = factor
                    break

        warnings: list[str] = []
        if level in {"caution", "alert", "critical"}:
            warnings.append(
                f"drawdown usa {utilization:.0%} del límite; tamaño reducido a {size_factor:g}x"
            )

        allowed = level != "breach"
        if not allowed:
            reason = (
                f"drawdown {drawdown:.2%} tocó el límite {self.max_drawdown_pct:.2%} "
                f"desde HWM {hwm:,.2f}"
            )
        elif level == "ok":
            reason = f"drawdown {drawdown:.2%} dentro del límite"
        else:
            reason = f"zona {level}: drawdown {drawdown:.2%} del límite {self.max_drawdown_pct:.2%}"

        return DrawdownReport(
            equity=value,
            hwm=hwm,
            drawdown_pct=drawdown,
            utilization=utilization,
            level=level,
            size_factor=size_factor,
            allowed=allowed,
            reason=reason,
            warnings=tuple(warnings),
        )


# ------------------------------------------------------------ circuit breaker


@dataclass(frozen=True)
class BreakerReport:
    tripped: bool
    reason: str
    consecutive_losses: int
    daily_pnl: float
    daily_loss_pct: float
    day: date


class DailyCircuitBreaker:
    """Corta nuevas entradas tras una racha o una pérdida diaria excesiva.

    Queda latcheado hasta el cambio de día (zona ``tz``) o un ``reset``
    explícito. Registrar una operación no bloquea el cierre de las que ya
    están abiertas: eso lo decide quien llama.

    Si no se siembra ``day_start_equity``, el primer ``observe`` del día fija
    la base; para medir la pérdida real del día hay que sembrarla con el
    equity de apertura.
    """

    def __init__(
        self,
        *,
        max_daily_loss_pct: float = 0.03,
        max_consecutive_losses: int = 3,
        day_start_equity: float | None = None,
        tz: str = "UTC",
    ) -> None:
        if not 0.0 < float(max_daily_loss_pct) < 1.0:
            raise DefenseError("max_daily_loss_pct debe estar entre 0 y 1")
        if int(max_consecutive_losses) < 1:
            raise DefenseError("max_consecutive_losses debe ser >= 1")
        if day_start_equity is not None and float(day_start_equity) <= 0:
            raise DefenseError("day_start_equity debe ser positivo")
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.tz = tz
        self._day: date | None = None
        self._day_start = float(day_start_equity) if day_start_equity is not None else None
        self._realized = 0.0
        self._streak = 0
        self._latch: str | None = None

    def _roll(self, day: date) -> None:
        if self._day == day:
            return
        if self._day is not None:
            self._day_start = None
            self._realized = 0.0
            self._streak = 0
            self._latch = None
        self._day = day

    def _ensure_day_start(self, equity: float | None) -> None:
        if self._day_start is None:
            if equity is None:
                raise DefenseError("hace falta equity para abrir un nuevo día")
            self._day_start = float(equity)

    def _report(self, equity: float | None) -> BreakerReport:
        assert self._day is not None
        self._ensure_day_start(equity)
        base = float(self._day_start)  # type: ignore[arg-type]
        daily_pnl = self._realized
        daily_loss = max(0.0, -daily_pnl) / base

        if self._latch is None:
            if daily_loss >= self.max_daily_loss_pct:
                self._latch = (
                    f"pérdida diaria {daily_loss:.2%} >= {self.max_daily_loss_pct:.2%}"
                )
            elif self._streak >= self.max_consecutive_losses:
                self._latch = (
                    f"{self._streak} pérdidas seguidas "
                    f">= {self.max_consecutive_losses}"
                )

        return BreakerReport(
            tripped=self._latch is not None,
            reason=self._latch or "circuit breaker en reposo",
            consecutive_losses=self._streak,
            daily_pnl=daily_pnl,
            daily_loss_pct=daily_loss,
            day=self._day,
        )

    def observe(self, equity: float, now: datetime | None = None) -> BreakerReport:
        local = _local(now, self.tz)
        self._roll(local.date())
        self._ensure_day_start(float(equity))
        return self._report(float(equity))

    def record_trade(
        self,
        pnl: float,
        *,
        equity: float | None = None,
        now: datetime | None = None,
    ) -> BreakerReport:
        local = _local(now, self.tz)
        self._roll(local.date())
        self._ensure_day_start(float(equity) if equity is not None else None)
        value = float(pnl)
        self._realized += value
        if value < 0:
            self._streak += 1
        elif value > 0:
            self._streak = 0
        return self._report(float(equity) if equity is not None else None)

    def reset(self, *, day_start_equity: float | None = None) -> None:
        self._day = None
        self._day_start = (
            float(day_start_equity) if day_start_equity is not None else None
        )
        self._realized = 0.0
        self._streak = 0
        self._latch = None


# --------------------------------------------------------------- flatten clock


class FlattenClock:
    """Cierre por reloj, una sola vez por sesión.

    ``due(now)`` devuelve True al cruzar ``flat_by`` hasta que se confirma con
    ``ack(now)``. Confirmar dos veces es inocuo; al día siguiente vuelve a
    dispararse. No bloquea ni ejecuta nada por sí mismo.
    """

    def __init__(
        self,
        flat_by: str = "15:55",
        *,
        tz: str = "America/New_York",
        weekdays_only: bool = True,
    ) -> None:
        self.flat_by = _parse_hhmm(flat_by)
        self.tz = tz
        self.weekdays_only = weekdays_only
        self._fired: date | None = None

    @property
    def fired_on(self) -> date | None:
        return self._fired

    def due(self, now: datetime | None = None) -> bool:
        local = _local(now, self.tz)
        if self.weekdays_only and local.weekday() >= 5:
            return False
        if local.time().replace(tzinfo=None) < self.flat_by:
            return False
        return self._fired != local.date()

    def ack(self, now: datetime | None = None) -> None:
        local = _local(now, self.tz)
        self._fired = local.date()

    def reset(self) -> None:
        self._fired = None


# -------------------------------------------------------------------- facade


@dataclass(frozen=True)
class DefenseReport:
    allowed: bool
    size_factor: float
    reason: str
    drawdown: DrawdownReport
    breaker: BreakerReport
    flatten_due: bool


class EquityDefense:
    """Decisión conjunta: drawdown, circuit breaker y reloj de cierre."""

    def __init__(
        self,
        *,
        max_drawdown_pct: float = 0.05,
        max_daily_loss_pct: float = 0.03,
        max_consecutive_losses: int = 3,
        flat_by: str = "15:55",
        tz: str = "America/New_York",
        start_equity: float | None = None,
    ) -> None:
        self.drawdown = TrailingDrawdown(max_drawdown_pct, start_equity=start_equity)
        self.breaker = DailyCircuitBreaker(
            max_daily_loss_pct=max_daily_loss_pct,
            max_consecutive_losses=max_consecutive_losses,
            day_start_equity=start_equity,
            tz=tz,
        )
        self.clock = FlattenClock(flat_by, tz=tz)

    def evaluate(self, equity: float, now: datetime | None = None) -> DefenseReport:
        dd = self.drawdown.observe(equity)
        breaker = self.breaker.observe(equity, now)
        flatten = self.clock.due(now)

        if not dd.allowed:
            return DefenseReport(False, 0.0, dd.reason, dd, breaker, flatten)
        if breaker.tripped:
            return DefenseReport(False, 0.0, breaker.reason, dd, breaker, flatten)
        if flatten:
            return DefenseReport(
                False,
                0.0,
                f"pasada la hora de cierre ({self.clock.flat_by.strftime('%H:%M')} {self.clock.tz})",
                dd,
                breaker,
                flatten,
            )
        return DefenseReport(True, dd.size_factor, dd.reason, dd, breaker, flatten)

    def record_trade(
        self,
        pnl: float,
        *,
        equity: float | None = None,
        now: datetime | None = None,
    ) -> BreakerReport:
        return self.breaker.record_trade(pnl, equity=equity, now=now)

    def ack_flatten(self, now: datetime | None = None) -> None:
        self.clock.ack(now)


__all__ = [
    "BreakerReport",
    "DailyCircuitBreaker",
    "DefenseError",
    "DefenseLevel",
    "DefenseReport",
    "DrawdownReport",
    "EquityDefense",
    "FlattenClock",
    "TrailingDrawdown",
]
