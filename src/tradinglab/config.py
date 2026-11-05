from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DEFAULT_DB = ROOT / "data" / "lab.db"


class LLMSettings(BaseModel):
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "qwen3.8-27b"
    api_key: str = "lm-studio"
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout_s: float = 600.0


class RiskSettings(BaseModel):
    max_position_pct: float = 0.10
    max_gross_exposure: float = 0.90
    max_positions: int = 8
    daily_loss_limit_pct: float = 0.03
    max_drawdown_pct: float = 0.15
    per_trade_risk_pct: float = 0.01
    atr_stop_mult: float = 2.0


class ExecutionSettings(BaseModel):
    broker: Literal["paper", "alpaca"] = "paper"
    commission_bps: float = 1.0
    slippage_bps: float = 5.0


class DataSettings(BaseModel):
    provider: Literal["yahoo", "alpaca"] = "yahoo"
    cache_dir: Path = Path("data/cache")


class Settings(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    timezone: str = "America/New_York"
    starting_cash: float = 100_000.0
    currency: str = "USD"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    data: DataSettings = Field(default_factory=DataSettings)

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        if not self.data.cache_dir.is_absolute():
            self.data.cache_dir = ROOT / self.data.cache_dir
        self.data.cache_dir.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        load_dotenv(ROOT / ".env")
        path = path or CONFIG_DIR / "lab.yaml"
        raw: dict = {}
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        settings = cls(**raw)

        # Variables de entorno con prioridad sobre el YAML
        if v := os.getenv("LAB_MODE"):
            settings.mode = v  # type: ignore[assignment]
        if v := os.getenv("LAB_LLM_BASE_URL"):
            settings.llm.base_url = v
        if v := os.getenv("LAB_LLM_MODEL"):
            settings.llm.model = v
        return settings


def get_settings(path: Path | None = None) -> Settings:
    return Settings.load(path)
