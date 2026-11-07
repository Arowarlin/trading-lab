from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import yaml

from ..config import CONFIG_DIR

Phase = Literal["challenge", "verification", "funded"]
LossMode = Literal["static", "trailing_eod", "trailing_intraday"]
DailyBase = Literal["balance", "equity"]


@dataclass(frozen=True)
class PropRules:
    """Reglas de una cuenta de fondeo, parametrizadas por firma y fase.

    Los valores por defecto son FTMO 100k (2-Step). SIEMPRE hay que verificarlos
    contra el contrato vigente de la firma: cambian sin aviso.
    """

    firm: str = "FTMO"
    program: str = "2-step"
    phase: Phase = "challenge"
    account_size: float = 100_000.0

    profit_target_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    max_loss_pct: float = 0.10

    max_loss_mode: LossMode = "static"
    daily_loss_mode: DailyBase = "equity"

    min_trading_days: int = 4
    consistency_pct: float | None = None

    max_lots: float | None = None
    max_positions: int | None = None
    max_open_risk_pct: float | None = None

    weekend_holding: bool = True
    news_blackout_min: int = 0
    # Hora local de la firma (reset_tz, p. ej. Europe/Prague) para el corte del
    # viernes. Si es None se usa friday_close_utc (compatibilidad).
    friday_cutoff_hour: int | None = None
    friday_close_utc: str = "20:00"
    rollover_utc: str = "21:00"
    rollover_blackout_min: int = 0

    buffer_pct: float = 0.10
    reset_time: str = "00:00"
    reset_tz: str = "Europe/Prague"

    verify_against_contract: bool = True
    notes: str = ""

    # ------------------------------------------------------------------ importes

    @property
    def profit_target_usd(self) -> float:
        return self.account_size * self.profit_target_pct

    @property
    def daily_limit_usd(self) -> float:
        return self.account_size * self.max_daily_loss_pct

    @property
    def max_loss_usd(self) -> float:
        return self.account_size * self.max_loss_pct

    @property
    def effective_daily_limit_usd(self) -> float:
        """Límite diario que el bot se permite usar (deja el colchón intacto)."""
        return self.daily_limit_usd * (1.0 - self.buffer_pct)

    @property
    def effective_max_loss_usd(self) -> float:
        return self.max_loss_usd * (1.0 - self.buffer_pct)

    def with_phase(self, phase: Phase, **overrides) -> "PropRules":
        return replace(self, phase=phase, **overrides)

    def describe(self) -> str:
        target = f"{self.profit_target_pct:.1%}" if self.profit_target_pct else "sin objetivo"
        return (
            f"{self.firm} {self.program} · {self.phase} · ${self.account_size:,.0f} · "
            f"objetivo {target} · diario {self.max_daily_loss_pct:.1%} · "
            f"máximo {self.max_loss_pct:.1%} ({self.max_loss_mode}) · "
            f"colchón {self.buffer_pct:.0%}"
        )


# --------------------------------------------------------------------- presets

def _load_yaml(path: Path | None = None) -> dict:
    path = path or CONFIG_DIR / "prop.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def from_yaml(
    firm: str,
    phase: Phase,
    account_size: float = 100_000.0,
    *,
    path: Path | None = None,
    buffer_pct: float | None = None,
) -> PropRules:
    """Carga una firma desde config/prop.yaml y aplica los valores de la fase."""
    data = _load_yaml(path)
    firms = data.get("firms") or {}
    entry = firms.get(firm.lower()) or firms.get(firm)
    if not entry:
        raise KeyError(f"Firma '{firm}' no está en config/prop.yaml")

    phases = entry.get("phases") or {}
    phase_data = phases.get(phase)
    if phase_data is None:
        raise KeyError(f"Fase '{phase}' no definida para {firm}")

    merged = dict(entry.get("defaults") or {})
    merged.update(phase_data)
    merged.pop("phases", None)
    merged.pop("defaults", None)

    merged.setdefault("program", entry.get("program", "2-step"))
    merged["firm"] = entry.get("display_name", firm.upper())
    merged["phase"] = phase
    merged["account_size"] = float(account_size)
    if buffer_pct is not None:
        merged["buffer_pct"] = float(buffer_pct)

    allowed = {f.name for f in PropRules.__dataclass_fields__.values()}
    merged = {k: v for k, v in merged.items() if k in allowed}
    return PropRules(**merged)


def ftmo(account_size: float = 100_000.0, phase: Phase = "challenge", **overrides) -> PropRules:
    """Atajo sin YAML para FTMO 2-Step."""
    targets = {"challenge": 0.10, "verification": 0.05, "funded": 0.0}
    defaults = {
        "firm": "FTMO",
        "program": "2-step",
        "phase": phase,
        "account_size": account_size,
        "profit_target_pct": targets[phase],
        "max_daily_loss_pct": 0.05,
        "max_loss_pct": 0.10,
        "max_loss_mode": "static",
        "daily_loss_mode": "equity",
        "buffer_pct": 0.10,
        "min_trading_days": 4 if phase != "funded" else 0,
    }
    defaults.update(overrides)
    return PropRules(**defaults)


__all__ = ["Phase", "LossMode", "DailyBase", "PropRules", "from_yaml", "ftmo"]
