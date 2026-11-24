"""Carga y validación de ``config/discovery/engine.yaml``.

Solo lee el YAML: no escribe archivos, no consulta MT5 y no arranca workers.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import ROOT
from .timeframes import TIMEFRAMES, normalize_timeframe

ENGINE_PATH = ROOT / "config" / "discovery" / "engine.yaml"


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    population: int = Field(ge=2, le=10_000)
    generations: int = Field(ge=1, le=10_000)


class GeneticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_rate: float = Field(ge=0.0, le=1.0)
    crossover_rate: float = Field(ge=0.0, le=1.0)
    elite_frac: float = Field(ge=0.0, le=0.5)


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_nodes: int = Field(ge=2, le=200)
    max_depth: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def _depth_fits_nodes(self) -> "LimitsConfig":
        if self.max_depth * 2 > self.max_nodes:
            raise ValueError("max_depth no puede superar max_nodes / 2")
        return self


class TimeframeValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_trades_is: int = Field(ge=1)
    min_trades_fold: int = Field(ge=1)
    folds: int = Field(ge=2, le=24)


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_trades_is: int = Field(ge=1)
    min_trades_fold: int = Field(ge=1)
    folds: int = Field(ge=2, le=24)
    finalists_max: int = Field(ge=1, le=100)
    corr_cluster: float = Field(ge=-1.0, le=1.0)
    # Valores congelados por TF antes de ver resultados. Si falta una TF se
    # usan los tres campos de arriba (compatibilidad con tests y YAML viejos).
    by_timeframe: dict[str, TimeframeValidationConfig] = Field(default_factory=dict)

    @field_validator("by_timeframe")
    @classmethod
    def _known_timeframes(
        cls, value: dict[str, TimeframeValidationConfig]
    ) -> dict[str, TimeframeValidationConfig]:
        clean: dict[str, TimeframeValidationConfig] = {}
        for name, item in value.items():
            key = normalize_timeframe(name)
            if key in clean:
                raise ValueError(f"timeframe repetido en validation.by_timeframe: {key}")
            clean[key] = item
        unknown = set(clean) - set(TIMEFRAMES)
        if unknown:
            raise ValueError(
                "validation.by_timeframe con TF desconocidas: "
                + ", ".join(sorted(unknown))
            )
        return clean

    def for_timeframe(self, timeframe: str) -> TimeframeValidationConfig:
        key = normalize_timeframe(timeframe)
        return self.by_timeframe.get(
            key,
            TimeframeValidationConfig(
                min_trades_is=self.min_trades_is,
                min_trades_fold=self.min_trades_fold,
                folds=self.folds,
            ),
        )


class FitnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_r_max: float = Field(default=0.10, gt=0.0, le=1.0)


class DiscoveryConfig(BaseModel):
    """Reglas de interpretación del coste en discovery."""

    model_config = ConfigDict(extra="forbid")

    # Un swap positivo (crédito) NO se cuenta en discovery: solo el coste
    # negativo. El crédito real se puede mostrar aparte en la capa de empresa.
    swap_credit: bool = False
    # Copia automática de discovery.db tras register/approve/run/confirm/
    # record-informal. La retención mueve a backups/_old, nunca borra.
    backup: bool = True
    # Spread usado por el motor: p75_static (v1), hourly_median o
    # historical_scaled (v2 con ASK; si no, hourly_median).
    spread_model: Literal["p75_static", "hourly_median", "historical_scaled"] = (
        "p75_static"
    )


class AssumedSlippageConfig(BaseModel):
    """Slippage por lado en unidades de precio; ``None`` = Sin datos."""

    model_config = ConfigDict(extra="forbid")

    source: str = "assumption"
    instruments: dict[str, float | None] = Field(default_factory=dict)

    @field_validator("instruments")
    @classmethod
    def _valid_values(
        cls, value: dict[str, float | None]
    ) -> dict[str, float | None]:
        clean: dict[str, float | None] = {}
        for name, item in value.items():
            if item is None:
                clean[str(name).upper()] = None
                continue
            number = float(item)
            if not (number >= 0.0) or number != number:
                raise ValueError(f"slippage asumido inválido para {name}: {item!r}")
            clean[str(name).upper()] = number
        return clean

    def for_instrument(self, symbol: str) -> float | None:
        key = str(symbol or "").strip().upper()
        return self.instruments.get(key)


class RobustnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    random_trials: int = Field(default=1000, ge=10, le=100_000)
    pbo_min_strategies: int = Field(default=8, ge=2, le=100)
    min_trades_oos2: int = Field(default=30, ge=1, le=10_000)
    wf_min_oos_sharpe: float = Field(default=0.0, ge=-5.0, le=5.0)
    wf_min_efficiency: float = Field(default=0.3, ge=0.0, le=5.0)
    wf_train_days: int = Field(default=60, ge=10, le=1000)
    wf_test_days: int = Field(default=20, ge=5, le=500)
    pbo_slices: int = Field(default=16, ge=4, le=64)
    mc_paths: int = Field(default=5000, ge=100, le=100_000)
    bootstrap_paths: int = Field(default=5000, ge=100, le=100_000)
    challenge_paths: int = Field(default=5000, ge=100, le=100_000)
    challenge_accounts: list[str] = Field(
        default_factory=lambda: ["CFD-001", "CFD-006"]
    )


class PerturbConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noise_paths: int = Field(default=500, ge=10, le=10_000)
    noise_scale_atr: float = Field(default=0.10, gt=0.0, le=1.0)
    entry_delays: list[int] = Field(default_factory=lambda: [1, 2])
    exit_delays: list[int] = Field(default_factory=lambda: [1, 2])
    exec_paths: int = Field(default=1000, ge=10, le=100_000)
    exec_skip_frac: float = Field(default=0.05, ge=0.0, le=1.0)
    min_median_ratio: float = Field(default=0.5, gt=0.0, le=2.0)

    @field_validator("entry_delays", "exit_delays")
    @classmethod
    def _positive_delays(cls, value: list[int]) -> list[int]:
        if not value or any(int(day) < 1 for day in value):
            raise ValueError("los retardos deben ser enteros >= 1")
        return [int(day) for day in value]


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    timezone: str = "UTC"
    calendar: str | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"zona inválida: {value}") from exc
        return value


class SessionSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None
    friday_close: str | None = None
    sunday_open: str | None = None
    pause_start: str | None = None
    pause_end: str | None = None
    short_close: str | None = None

    @field_validator(
        "friday_close",
        "sunday_open",
        "pause_start",
        "pause_end",
        "short_close",
    )
    @classmethod
    def _valid_hhmm(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        try:
            hour, minute = (int(part) for part in text.split(":"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"hora inválida: {value}") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"hora inválida: {value}")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("start", "end")
    @classmethod
    def _valid_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            date.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError(f"fecha inválida: {value}") from exc
        return str(value)

    @model_validator(mode="after")
    def _range(self) -> "SessionSegment":
        if self.start and self.end:
            if date.fromisoformat(self.start) > date.fromisoformat(self.end):
                raise ValueError("el tramo de sesión termina antes de empezar")
        return self


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[SessionSegment] = Field(min_length=1)


class DataQualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_factor: float = Field(gt=1.0, le=100.0)
    max_gap_hours: float = Field(gt=0.0, le=168.0)
    scheduled_gap_share: float = Field(ge=0.0, le=1.0)
    warn_if_gaps_gt: int = Field(ge=0)
    fail_if_gap_pct_gt: float = Field(ge=0.0, le=1.0)
    pause_tz: str = "America/New_York"
    session_tz: dict[str, str] = Field(default_factory=lambda: {"default": "America/New_York"})
    default_segments: dict[str, tuple[str | None, str | None]] = Field(
        default_factory=lambda: {
            "is": ("2021-10-01", "2024-06-30"),
            "oos1": ("2024-07-01", "2025-06-30"),
            "oos2": ("2025-07-01", None),
        }
    )
    sources: dict[str, "SourceConfig"] = Field(
        default_factory=lambda: {
            "default": SourceConfig(
                path="data/cache/mt5/{symbol}_{tf}.parquet",
                timezone="UTC",
                calendar=None,
            )
        }
    )
    sessions: dict[str, SessionConfig] | None = None
    usable_from: dict[str, str] | None = None

    @field_validator("pause_tz")
    @classmethod
    def _valid_pause_tz(cls, value: str) -> str:
        try:
            ZoneInfo(str(value))
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"zona de pausa inválida: {value}") from exc
        return str(value)

    @field_validator("session_tz")
    @classmethod
    def _valid_timezones(cls, value: dict[str, str]) -> dict[str, str]:
        for name, tz in value.items():
            try:
                ZoneInfo(str(tz))
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"zona inválida para {name}: {tz}") from exc
        return value

    @field_validator("default_segments")
    @classmethod
    def _required_segments(
        cls, value: dict[str, tuple[str | None, str | None]]
    ) -> dict[str, tuple[str | None, str | None]]:
        missing = {"is", "oos1", "oos2"} - set(value)
        if missing:
            raise ValueError(f"faltan tramos: {', '.join(sorted(missing))}")
        return value

    @field_validator("usable_from")
    @classmethod
    def _valid_usable_from(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        out: dict[str, str] = {}
        for key, text in value.items():
            try:
                day = date.fromisoformat(str(text))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"usable_from inválido para {key}: {text}") from exc
            out[str(key)] = day.isoformat()
        return out

    def tz_for(self, symbol: str) -> str:
        key = str(symbol or "").strip().lower()
        for name, tz in self.session_tz.items():
            if name.lower() == key:
                return tz
        return self.session_tz.get("default", "America/New_York")

    def session_for(
        self, source: str, symbol: str, day: date
    ) -> SessionSegment | None:
        """Tramo de sesión vigente para una fuente, símbolo y fecha."""
        if not self.sessions:
            return None
        key = f"{str(source).strip().lower()}:{str(symbol).strip().lower()}"
        candidates = [
            key,
            f"{str(source).strip().lower()}:{str(symbol).split('.')[0].strip().lower()}",
        ]
        config = None
        for name, value in self.sessions.items():
            if str(name).strip().lower() in candidates:
                config = value
                break
        if config is None:
            return None
        for segment in config.segments:
            if segment.start and day < date.fromisoformat(segment.start):
                continue
            if segment.end and day > date.fromisoformat(segment.end):
                continue
            return segment
        return None

    def usable_from_for(
        self, source: str, symbol: str, timeframe: str
    ) -> date | None:
        """Primera fecha usable declarada para fuente:símbolo:TF, si existe."""
        if not self.usable_from:
            return None
        src = str(source).strip().lower()
        sym = str(symbol).strip().lower()
        tf = str(timeframe).strip().upper()
        candidates = {
            f"{src}:{sym}:{tf}".lower(),
            f"{src}:{sym.split('.')[0]}:{tf}".lower(),
        }
        for name, value in self.usable_from.items():
            if str(name).strip().lower() in candidates:
                return date.fromisoformat(value)
        return None

    def source_for(self, symbol: str) -> "SourceConfig":
        key = str(symbol or "").strip().lower()
        for name, source in self.sources.items():
            if name.lower() == key:
                return source
        return self.sources.get("default") or SourceConfig(
            path="data/cache/mt5/{symbol}_{tf}.parquet", timezone="UTC", calendar=None
        )


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: int = Field(ge=1, le=64)
    ram_limit_gb: float = Field(gt=0.0, le=1024.0)
    profiles: dict[str, ProfileConfig]
    genetics: GeneticsConfig
    limits: LimitsConfig
    validation: ValidationConfig
    fitness: FitnessConfig = Field(default_factory=FitnessConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    assumed_slippage: AssumedSlippageConfig = Field(
        default_factory=AssumedSlippageConfig
    )
    robustness: RobustnessConfig = Field(default_factory=RobustnessConfig)
    perturb: PerturbConfig = Field(default_factory=PerturbConfig)
    data_quality: DataQualityConfig

    @field_validator("profiles")
    @classmethod
    def _required_profiles(cls, value: dict[str, ProfileConfig]) -> dict[str, ProfileConfig]:
        missing = {"small", "medium", "large"} - set(value)
        if missing:
            raise ValueError(f"faltan perfiles: {', '.join(sorted(missing))}")
        return value

    def profile(self, name: str) -> ProfileConfig:
        try:
            return self.profiles[str(name)]
        except KeyError as exc:
            raise KeyError(f"perfil desconocido: {name}") from exc


def load_engine_config(path: str | Path | None = None) -> EngineConfig:
    """Lee el YAML y devuelve la configuración validada."""
    target = Path(path) if path else ENGINE_PATH
    if not target.exists():
        raise FileNotFoundError(f"Sin datos: no existe {target}")
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML inválido en {target}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{target}: la raíz debe ser un objeto")
    engine = raw.get("engine")
    if not isinstance(engine, dict):
        raise ValueError(f"{target}: falta el bloque engine")
    payload = {
        **engine,
        "profiles": raw.get("profiles") or {},
        "genetics": raw.get("genetics") or {},
        "limits": raw.get("limits") or {},
        "validation": raw.get("validation") or {},
        "fitness": raw.get("fitness") or {},
        "discovery": raw.get("discovery") or {},
        "assumed_slippage": raw.get("assumed_slippage") or {},
        "robustness": raw.get("robustness") or {},
        "perturb": raw.get("perturb") or {},
        "data_quality": raw.get("data_quality") or {},
    }
    return EngineConfig.model_validate(payload)


__all__ = [
    "AssumedSlippageConfig",
    "DataQualityConfig",
    "DiscoveryConfig",
    "ENGINE_PATH",
    "EngineConfig",
    "FitnessConfig",
    "GeneticsConfig",
    "LimitsConfig",
    "PerturbConfig",
    "ProfileConfig",
    "RobustnessConfig",
    "SessionConfig",
    "SessionSegment",
    "SourceConfig",
    "TimeframeValidationConfig",
    "ValidationConfig",
    "load_engine_config",
]
