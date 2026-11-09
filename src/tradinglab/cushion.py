"""Colchón de riesgo con semáforo, solo informativo.

Calcula la distancia que queda hasta el límite de pérdida diaria y hasta el
drawdown máximo usando exactamente la misma evaluación de equity que el
kill-switch (``killswitch.evaluate``). No activa, persiste ni bloquea nada:
el kill-switch y el guard de cuenta siguen siendo los únicos que deciden.

Los umbrales del semáforo viven en ``config/cushion.yaml`` y se expresan como
fracción del límite ya consumida (0.5 = 50 % del límite).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .config import DEFAULT_DB, ROOT, RiskSettings, get_settings
from .db import connect
from .killswitch import evaluate as evaluate_killswitch

CUSHION_FILE = ROOT / "config" / "cushion.yaml"
DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "daily": {"amber_at_used": 0.50, "red_at_used": 0.80},
    "drawdown": {"amber_at_used": 0.50, "red_at_used": 0.80},
}
STATE_LABELS = {
    "green": "verde",
    "amber": "ámbar",
    "red": "rojo",
    "no_data": "sin datos",
}
STYLE_BY_STATE = {
    "green": "green",
    "amber": "yellow",
    "red": "red",
    "no_data": "dim",
}
_SEVERITY = {"green": 0, "amber": 1, "red": 2}
_SECTIONS = ("daily", "drawdown")


@dataclass(frozen=True)
class CushionBand:
    """Un límite con su uso, su colchón restante y su estado."""

    key: str
    label: str
    state: str
    limit_pct: float
    used_pct: float
    used_fraction: float
    remaining_pct: float
    remaining_usd: float
    base_equity: float

    @property
    def state_label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "state": self.state,
            "state_label": self.state_label,
            "limit_pct": self.limit_pct,
            "used_pct": self.used_pct,
            "used_fraction": self.used_fraction,
            "remaining_pct": self.remaining_pct,
            "remaining_usd": self.remaining_usd,
            "base_equity": self.base_equity,
        }


@dataclass(frozen=True)
class CushionReport:
    """Resultado del semáforo; nunca bloquea por sí mismo."""

    state: str
    daily: CushionBand
    drawdown: CushionBand
    equity: float
    day_start: float
    peak: float
    as_of: str
    informative: bool = True
    warning: str | None = None
    thresholds: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def state_label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "state_label": self.state_label,
            "informative": self.informative,
            "warning": self.warning,
            "equity": self.equity,
            "day_start": self.day_start,
            "peak": self.peak,
            "as_of": self.as_of,
            "thresholds": self.thresholds,
            "daily": self.daily.to_dict(),
            "drawdown": self.drawdown.to_dict(),
        }


def _defaults() -> dict[str, dict[str, float]]:
    return {section: dict(values) for section, values in DEFAULT_THRESHOLDS.items()}


def _parse_section(raw: dict[str, Any], defaults: dict[str, float]) -> dict[str, float]:
    amber = float(raw.get("amber_at_used", raw.get("amber", defaults["amber_at_used"])))
    red = float(raw.get("red_at_used", raw.get("red", defaults["red_at_used"])))
    if not (0.0 <= amber < red <= 1.0):
        raise ValueError(
            f"umbrales inválidos: amber_at_used={amber} red_at_used={red}; "
            "debe cumplirse 0 <= amber < red <= 1"
        )
    return {"amber_at_used": amber, "red_at_used": red}


def load_thresholds(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """Carga los umbrales del archivo nuevo; si no existe, usa los defaults."""
    target = Path(path) if path is not None else CUSHION_FILE
    if not target.exists():
        return _defaults()
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("cushion.yaml debe ser un mapa")
    out: dict[str, dict[str, float]] = {}
    top_level = {
        key: data[key]
        for key in ("amber_at_used", "red_at_used", "amber", "red")
        if key in data
    }
    for section in _SECTIONS:
        raw = data.get(section) or {}
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError(f"cushion.yaml: {section} debe ser un mapa")
        if not raw and top_level:
            raw = top_level
        out[section] = _parse_section(raw, DEFAULT_THRESHOLDS[section])
    return out


def _normalize_thresholds(
    thresholds: dict[str, dict[str, float]] | None,
) -> dict[str, dict[str, float]]:
    out = _defaults()
    if thresholds:
        for section in _SECTIONS:
            raw = thresholds.get(section)
            if isinstance(raw, dict):
                out[section] = _parse_section(raw, out[section])
    return out


def _state_for(used_fraction: float, thresholds: dict[str, float]) -> str:
    if used_fraction >= float(thresholds["red_at_used"]):
        return "red"
    if used_fraction >= float(thresholds["amber_at_used"]):
        return "amber"
    return "green"


def _overall_state(*states: str) -> str:
    known = [state for state in states if state in _SEVERITY]
    if not known:
        return "no_data"
    return max(known, key=lambda state: _SEVERITY[state])


def _band(
    *,
    key: str,
    label: str,
    base_equity: float,
    loss_pct: float,
    limit_pct: float,
    thresholds: dict[str, float],
) -> CushionBand:
    if base_equity <= 0 or limit_pct <= 0:
        return CushionBand(
            key=key,
            label=label,
            state="no_data",
            limit_pct=max(0.0, limit_pct),
            used_pct=max(0.0, loss_pct),
            used_fraction=0.0,
            remaining_pct=0.0,
            remaining_usd=0.0,
            base_equity=max(0.0, base_equity),
        )
    used = max(0.0, float(loss_pct))
    used_fraction = used / limit_pct
    remaining_pct = max(0.0, limit_pct - used)
    return CushionBand(
        key=key,
        label=label,
        state=_state_for(used_fraction, thresholds),
        limit_pct=limit_pct,
        used_pct=used,
        used_fraction=used_fraction,
        remaining_pct=remaining_pct,
        remaining_usd=base_equity * remaining_pct,
        base_equity=base_equity,
    )


def evaluate(
    equity: pd.Series | None,
    cfg: RiskSettings,
    *,
    current: float | None = None,
    tz: str = "America/New_York",
    now: datetime | None = None,
    thresholds: dict[str, dict[str, float]] | None = None,
    daily_loss_limit_pct: float | None = None,
    max_drawdown_pct: float | None = None,
) -> CushionReport:
    """Evalúa el colchón contra los límites del kill-switch o unos explícitos."""
    warning = None
    if thresholds is None:
        try:
            thresholds = load_thresholds()
        except Exception as exc:  # un YAML roto no debe romper el estado
            thresholds = _defaults()
            warning = f"cushion.yaml inválido: {exc}; se usan los defaults"
    thresholds = _normalize_thresholds(thresholds)

    base = evaluate_killswitch(equity, cfg, current=current, tz=tz, now=now)
    limit_daily = float(
        daily_loss_limit_pct
        if daily_loss_limit_pct is not None
        else cfg.daily_loss_limit_pct
    )
    limit_drawdown = float(
        max_drawdown_pct
        if max_drawdown_pct is not None
        else cfg.max_drawdown_pct
    )
    daily = _band(
        key="daily",
        label="Pérdida diaria",
        base_equity=base.day_start,
        loss_pct=max(0.0, -float(base.daily_return)),
        limit_pct=limit_daily,
        thresholds=thresholds["daily"],
    )
    drawdown = _band(
        key="drawdown",
        label="Drawdown máximo",
        base_equity=base.peak,
        loss_pct=max(0.0, -float(base.drawdown)),
        limit_pct=limit_drawdown,
        thresholds=thresholds["drawdown"],
    )
    as_of = pd.Timestamp(now or datetime.now(timezone.utc)).isoformat()
    return CushionReport(
        state=_overall_state(daily.state, drawdown.state),
        daily=daily,
        drawdown=drawdown,
        equity=float(base.equity),
        day_start=float(base.day_start),
        peak=float(base.peak),
        as_of=as_of,
        warning=warning,
        thresholds=thresholds,
    )


def evaluate_from_db(
    db_path: str | Path = DEFAULT_DB,
    *,
    now: datetime | None = None,
    thresholds: dict[str, dict[str, float]] | None = None,
) -> CushionReport:
    """Lee la curva de equity de SQLite sin crear ni modificar nada."""
    settings = get_settings()
    path = Path(db_path)
    series = pd.Series(dtype=float)
    if path.exists():
        with connect(path) as con:
            rows = con.execute(
                "SELECT ts, equity FROM equity ORDER BY ts"
            ).fetchall()
        if rows:
            index = pd.to_datetime([row["ts"] for row in rows], utc=True)
            series = pd.Series(
                [float(row["equity"]) for row in rows],
                index=index,
                dtype=float,
            )
    # Sin historial se devuelve "sin datos"; no se inventa un equity verde.
    current = float(series.iloc[-1]) if not series.empty else None
    return evaluate(
        series,
        settings.risk,
        current=current,
        tz=settings.timezone,
        now=now,
        thresholds=thresholds,
    )


def summary_line(report: CushionReport) -> str:
    """Línea compacta para Telegram."""
    if report.state == "no_data":
        return "Colchón riesgo: sin datos"

    def part(band: CushionBand) -> str:
        if band.state == "no_data":
            return f"{band.label.lower()} sin datos"
        return (
            f"{band.label.lower()} {band.state_label} "
            f"({band.used_fraction:.0%} usado, resta {band.remaining_pct:.2%})"
        )

    return (
        f"Colchón riesgo: {report.state_label} · "
        f"{part(report.daily)} · {part(report.drawdown)}"
    )


__all__ = [
    "CUSHION_FILE",
    "DEFAULT_THRESHOLDS",
    "STATE_LABELS",
    "STYLE_BY_STATE",
    "CushionBand",
    "CushionReport",
    "evaluate",
    "evaluate_from_db",
    "load_thresholds",
    "summary_line",
]
