"""Kill-switch persistente.

Reglas:
  * se activa por pérdida diaria o drawdown máximo;
  * una vez activo NO se desactiva aunque el equity se recupere;
  * solo un reset manual confirmado lo apaga;
  * bloquear aperturas, pero permitir cierres/reducciones;
  * el estado vive en SQLite y sobrevive a reinicios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .alerts import send as send_alert
from .config import RiskSettings
from .db import connect, init_db, utcnow


@dataclass(frozen=True)
class KillSwitchEvaluation:
    active: bool
    reason: str
    equity: float
    peak: float
    day_start: float
    daily_return: float
    drawdown: float


@dataclass(frozen=True)
class KillSwitchState:
    active: bool
    reason: str
    triggered_at: str | None = None
    reset_at: str | None = None
    equity: float | None = None
    peak: float | None = None
    day_start: float | None = None


def _normalize(series: pd.Series | None, current: float | None) -> pd.Series:
    if series is None:
        series = pd.Series(dtype=float)
    else:
        series = series.astype(float).dropna()
    if current is not None and series.empty:
        series = pd.Series([float(current)])
    return series


def evaluate(
    equity: pd.Series | None,
    cfg: RiskSettings,
    *,
    current: float | None = None,
    tz: str = "America/New_York",
    now: datetime | None = None,
) -> KillSwitchEvaluation:
    """Evalúa el equity actual contra el inicio del día local y el pico."""
    series = _normalize(equity, current)
    if series.empty:
        return KillSwitchEvaluation(False, "sin datos de equity", 0.0, 0.0, 0.0, 0.0, 0.0)

    value = float(current if current is not None else series.iloc[-1])
    peak = max(float(series.max()), value)
    day_start = float(series.iloc[0])

    if isinstance(series.index, pd.DatetimeIndex):
        index = series.index
        if index.tz is None:
            index = index.tz_localize("UTC")
        local = index.tz_convert(tz)
        stamp = pd.Timestamp(now or datetime.now(timezone.utc))
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        today = stamp.tz_convert(tz).date()
        mask = local.date == today
        if not mask.any():
            today = local[-1].date()
            mask = local.date == today
        if mask.any():
            day_start = float(series[mask].iloc[0])
    else:
        # Serie sin timestamps: el primer punto es la base del día.
        day_start = float(series.iloc[0])

    daily = value / day_start - 1.0 if day_start > 0 else 0.0
    drawdown = value / peak - 1.0 if peak > 0 else 0.0
    reasons: list[str] = []
    if daily <= -cfg.daily_loss_limit_pct:
        reasons.append(f"límite de pérdida diaria alcanzado ({daily:.2%})")
    if drawdown <= -cfg.max_drawdown_pct:
        reasons.append(f"drawdown máximo alcanzado ({drawdown:.2%})")

    return KillSwitchEvaluation(
        active=bool(reasons),
        reason="; ".join(reasons) if reasons else "ok",
        equity=value,
        peak=peak,
        day_start=day_start,
        daily_return=daily,
        drawdown=drawdown,
    )


def load_state(db_path: str | Path) -> KillSwitchState:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM killswitch WHERE id = 1").fetchone()
    if row is None:
        return KillSwitchState(False, "inactivo")
    return KillSwitchState(
        active=bool(row["active"]),
        reason=row["reason"] or ("activo" if row["active"] else "inactivo"),
        triggered_at=row["triggered_at"],
        reset_at=row["reset_at"],
        equity=row["equity"],
        peak=row["peak"],
        day_start=row["day_start"],
    )


def _persist(db_path: str | Path, evaluation: KillSwitchEvaluation) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO killswitch"
            "(id, active, reason, triggered_at, reset_at, equity, peak, day_start) "
            "VALUES(1, 1, ?, ?, NULL, ?, ?, ?)",
            (
                evaluation.reason,
                utcnow(),
                evaluation.equity,
                evaluation.peak,
                evaluation.day_start,
            ),
        )
    try:
        send_alert(
            "killswitch_active",
            evaluation.reason,
            severity="critical",
            db_path=db_path,
        )
    except Exception:
        pass


def ensure(
    db_path: str | Path,
    equity: pd.Series | None,
    cfg: RiskSettings,
    *,
    current: float | None = None,
    tz: str = "America/New_York",
    now: datetime | None = None,
) -> tuple[KillSwitchState, KillSwitchEvaluation]:
    """Carga el estado persistido y activa el switch si hace falta.

    Si ya estaba activo, se devuelve activo aunque el equity actual esté bien:
    el reset es siempre manual.
    """
    state = load_state(db_path)
    evaluation = evaluate(equity, cfg, current=current, tz=tz, now=now)
    if state.active:
        return state, evaluation
    if evaluation.active:
        _persist(db_path, evaluation)
        return load_state(db_path), evaluation
    return state, evaluation


def allows_order(state: KillSwitchState, delta: int) -> bool:
    """El kill-switch solo permite reducir/cerrar (delta <= 0)."""
    return (not state.active) or int(delta) <= 0


def reset(db_path: str | Path, *, confirm: bool) -> KillSwitchState:
    if not confirm:
        raise ValueError("el reset del kill-switch requiere confirmación explícita")
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "UPDATE killswitch SET active = 0, reset_at = ? WHERE id = 1",
            (utcnow(),),
        )
    return load_state(db_path)


def activate(
    db_path: str | Path,
    *,
    reason: str = "activación manual desde la consola",
    confirm: bool = False,
) -> KillSwitchState:
    """Activa el kill-switch global; nunca lo desactiva."""
    if not confirm:
        raise ValueError("activar el kill-switch requiere confirmación explícita")
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO killswitch"
            "(id, active, reason, triggered_at, reset_at, equity, peak, day_start) "
            "VALUES(1, 1, ?, ?, NULL, NULL, NULL, NULL)",
            (reason[:240], utcnow()),
        )
    try:
        send_alert("killswitch_active", reason, severity="critical", db_path=db_path)
    except Exception:
        pass
    return load_state(db_path)


__all__ = [
    "KillSwitchEvaluation",
    "KillSwitchState",
    "activate",
    "allows_order",
    "ensure",
    "evaluate",
    "load_state",
    "reset",
]
