"""Entidades del modelo multiempresa / multicuenta (Prop Fund).

Se reutilizan los modelos existentes donde ya cubren el caso:

* ``tradinglab.prop.rules.PropRules``      → reglas numéricas por firma/fase (FTMO).
* ``tradinglab.accounts.AccountDefinition`` → identidad de las cuentas legacy.
* ``tradinglab.instruments.Instrument``    → especificaciones de contrato.

Lo nuevo vive aquí y se valida con pydantic al cargar ``config/propfund``.
Ningún modelo de este archivo envía órdenes.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Market(StrEnum):
    CFD = "cfd"
    FUTURES = "futures"


class CfdCategory(StrEnum):
    FOREX = "forex"
    INDEX = "index"
    METAL = "metal"


class FuturesCategory(StrEnum):
    INDEX = "index"
    METAL = "metal"


class AutomationPermission(StrEnum):
    """Matriz de permisos de automatización (sección 4 del prompt maestro)."""

    FULL = "full"                    # automatización completa permitida
    CONDITIONAL = "conditional"      # permitida con condiciones
    SEMI_AUTO = "semi_auto"          # solo ejecución semiautomática
    MANUAL_ONLY = "manual_only"      # ejecución manual exclusivamente
    UNKNOWN = "unknown"              # información insuficiente
    PROHIBITED = "prohibited"        # prohibido

    @property
    def allows_auto_orders(self) -> bool:
        return self in {AutomationPermission.FULL, AutomationPermission.CONDITIONAL}


class VerificationStatus(StrEnum):
    VERIFIED_OFFICIAL = "verified_official"    # leído en la fuente oficial de la firma
    VERIFIED_SECONDARY = "verified_secondary"  # varias fuentes secundarias coinciden
    NEEDS_VERIFICATION = "needs_verification"
    UNKNOWN = "unknown"

    @property
    def is_verified(self) -> bool:
        return self is VerificationStatus.VERIFIED_OFFICIAL


class ConnectionState(StrEnum):
    """Estados de conexión. Toda conexión nueva arranca en DISCONNECTED."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE_LOCKED = "LIVE_LOCKED"
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"

    @property
    def can_route(self) -> bool:
        """Estados donde el router puede preparar una solicitud de ejecución."""
        return self in {ConnectionState.PAPER, ConnectionState.DEMO}


class AccountPhase(StrEnum):
    EVALUATION = "evaluation"
    VERIFICATION = "verification"
    FUNDED = "funded"
    LIVE = "live"


class StrategyLane(StrEnum):
    PROTECTED_FTMO = "protected_ftmo"
    CFD_NEW = "cfd_new"
    FUTURES_NEW = "futures_new"
    RESEARCH = "research"
    PAPER = "paper"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    url: str
    consulted_at: date
    effective_from: date | None = None
    kind: Literal["official", "secondary"] = "official"


class FirmRule(_Strict):
    """Una regla concreta con su procedencia. Si no hay dato: value=None."""

    key: str
    value: float | int | str | bool | None = None
    unit: str = ""
    phase: str = "all"
    platform: str = "all"
    instrument: str = "all"
    status: VerificationStatus = VerificationStatus.NEEDS_VERIFICATION
    source: Source | None = None
    notes: str = ""


class AutomationPolicy(_Strict):
    permission: AutomationPermission = AutomationPermission.UNKNOWN
    status: VerificationStatus = VerificationStatus.UNKNOWN
    conditions: list[str] = Field(default_factory=list)
    allowed_phases: list[str] = Field(default_factory=list)
    exclusive_to_firm: bool = False       # p. ej. Tradeify: el bot no puede usarse en otra firma
    vps_allowed: bool | None = None
    copy_trading: Literal["allowed", "own_accounts", "prohibited", "unknown"] = "unknown"
    sources: list[Source] = Field(default_factory=list)


class Program(_Strict):
    id: str
    name: str
    phases: list[AccountPhase]
    platforms: list[str]
    sizes: list[int] = Field(default_factory=list)
    rules: list[FirmRule] = Field(default_factory=list)
    automation: AutomationPolicy | None = None  # sobrescribe la política de la firma


class Firm(_Strict):
    id: str
    name: str
    market: Market
    priority: int = 99
    enabled: bool = False
    protected: bool = False            # FTMO: implementación existente intocable
    legacy_prop_key: str | None = None  # clave en config/prop.yaml o prop_templates.yaml
    website: str = ""
    platforms: list[str] = Field(default_factory=list)
    execution_providers: list[str] = Field(default_factory=list)
    automation: AutomationPolicy
    programs: list[Program] = Field(default_factory=list)
    rules_version: str = "0"
    notes: str = ""

    def program(self, program_id: str) -> Program | None:
        return next((p for p in self.programs if p.id == program_id), None)

    def automation_for(self, program_id: str | None) -> AutomationPolicy:
        program = self.program(program_id) if program_id else None
        return program.automation if program and program.automation else self.automation


class RiskPolicy(_Strict):
    per_trade_risk_pct: float = 0.005
    daily_risk_pct: float = 0.02
    max_trades_per_day: int = 3
    max_open_positions: int = 2
    buffer_vs_firm_pct: float = 0.20     # colchón respecto al límite de la firma
    max_cost_r: float = 0.20             # coste estimado máximo en múltiplos de R

    @field_validator("per_trade_risk_pct", "daily_risk_pct", "buffer_vs_firm_pct")
    @classmethod
    def _fraction(cls, value: float) -> float:
        if not 0 <= value < 1:
            raise ValueError("debe ser una fracción entre 0 y 1")
        return value


class AccountLimits(_Strict):
    """Límites de la firma para esta cuenta, en USD. None = sin dato verificado."""

    daily_loss: float | None = None
    max_loss: float | None = None
    drawdown_mode: Literal["static", "trailing_eod", "trailing_intraday", "unknown"] = "unknown"
    profit_target: float | None = None
    max_contracts: int | None = None
    max_lots: float | None = None


class PropAccount(_Strict):
    id: str
    firm: str
    program: str
    market: Market
    phase: AccountPhase
    nominal_size: float
    platform: str
    execution_provider: str
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    legacy_account: str | None = None   # id en config/accounts.yaml (solo lectura)
    template: bool = True               # True = ejemplo/plantilla, no una cuenta real
    protected: bool = False
    allowed_instruments: list[str] = Field(default_factory=list)
    limits: AccountLimits = Field(default_factory=AccountLimits)
    risk: RiskPolicy = Field(default_factory=RiskPolicy)
    automation_acknowledged: bool = False  # el operador confirmó las condiciones de la firma
    credentials_ref: str | None = None     # nombre en keyring, nunca el secreto
    notes: str = ""


class Strategy(_Strict):
    id: str
    name: str
    lane: StrategyLane
    market: Market
    instruments: list[str]
    timeframe: str
    version: str = "1"
    status: Literal["research", "paper", "demo", "forward", "evaluation", "funded", "retired"] = "research"
    protected: bool = False
    engine: str = "tradinglab"         # tradinglab | mt5_ea | ai_trader
    owner: str = "operator"
    params_ref: str = ""               # dónde viven los parámetros (no se duplican)
    notes: str = ""


class StrategyAssignment(_Strict):
    id: str
    strategy: str
    account: str
    instruments: list[str]
    enabled: bool = False
    replication_group: str | None = None  # misma señal en varias cuentas: solo si la firma lo permite
    risk_per_trade_r: float = 1.0
    notes: str = ""


__all__ = [
    "AccountLimits",
    "AccountPhase",
    "AutomationPermission",
    "AutomationPolicy",
    "CfdCategory",
    "ConnectionState",
    "Firm",
    "FirmRule",
    "FuturesCategory",
    "Market",
    "Program",
    "PropAccount",
    "RiskPolicy",
    "Source",
    "Strategy",
    "StrategyAssignment",
    "StrategyLane",
    "VerificationStatus",
]
