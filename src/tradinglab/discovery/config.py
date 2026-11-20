"""Carga y validación de ``config/discovery/engine.yaml``.

Solo lee el YAML: no escribe archivos, no consulta MT5 y no arranca workers.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import ROOT

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


class ValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_trades_is: int = Field(ge=1)
    min_trades_fold: int = Field(ge=1)
    folds: int = Field(ge=2, le=24)
    finalists_max: int = Field(ge=1, le=100)
    corr_cluster: float = Field(ge=-1.0, le=1.0)


class DataQualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_factor: float = Field(gt=1.0, le=100.0)
    max_gap_hours: float = Field(gt=0.0, le=168.0)
    scheduled_gap_share: float = Field(ge=0.0, le=1.0)
    warn_if_gaps_gt: int = Field(ge=0)
    fail_if_gap_pct_gt: float = Field(ge=0.0, le=1.0)


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: int = Field(ge=1, le=64)
    ram_limit_gb: float = Field(gt=0.0, le=1024.0)
    profiles: dict[str, ProfileConfig]
    genetics: GeneticsConfig
    limits: LimitsConfig
    validation: ValidationConfig
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
        "data_quality": raw.get("data_quality") or {},
    }
    return EngineConfig.model_validate(payload)


__all__ = [
    "DataQualityConfig",
    "ENGINE_PATH",
    "EngineConfig",
    "GeneticsConfig",
    "LimitsConfig",
    "ProfileConfig",
    "ValidationConfig",
    "load_engine_config",
]
