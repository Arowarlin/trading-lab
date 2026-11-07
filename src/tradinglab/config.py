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


class MT5Settings(BaseModel):
    terminal_path: str | None = None
    login: int | None = None
    server: str | None = None
    magic: int = 20261105
    deviation: int = 20
    default_symbol: str = "EURUSD"
    dry_run: bool = True  # el orquestador NO envía órdenes a MT5 salvo --execute
    require_demo: bool = True  # el guard de identidad rechaza cuentas reales
    server_utc_offset_hours: float | None = None  # None = autodetectar


class ProjectXSettings(BaseModel):
    base_url: str = "https://api.topstepx.com"
    username: str | None = None
    account_id: int | None = None
    dry_run: bool = True  # el laboratorio NO envía órdenes salvo --execute
    require_simulated: bool = True  # el guard rechaza cuentas reales


class PropSettings(BaseModel):
    enabled: bool = False
    firm: str = "FTMO"
    phase: Literal["challenge", "verification", "funded"] = "challenge"
    account_size: float = 100_000.0
    buffer_pct: float = 0.10
    reset_tz: str = "Europe/Prague"


class Settings(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    timezone: str = "America/New_York"
    starting_cash: float = 100_000.0
    currency: str = "USD"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    mt5: MT5Settings = Field(default_factory=MT5Settings)
    projectx: ProjectXSettings = Field(default_factory=ProjectXSettings)
    prop: PropSettings = Field(default_factory=PropSettings)

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

        # MetaTrader 5 y cuentas de fondeo
        if v := os.getenv("MT5_PATH"):
            settings.mt5.terminal_path = v
        if v := os.getenv("MT5_LOGIN"):
            settings.mt5.login = int(v)
        if v := os.getenv("MT5_SERVER"):
            settings.mt5.server = v
        if v := os.getenv("MT5_REQUIRE_DEMO"):
            settings.mt5.require_demo = v.strip().lower() not in {"0", "false", "no"}
        # ProjectX / TopstepX (futuros)
        if v := os.getenv("PROJECTX_BASE_URL"):
            settings.projectx.base_url = v
        if v := os.getenv("PROJECTX_USERNAME"):
            settings.projectx.username = v
        if v := os.getenv("PROJECTX_ACCOUNT_ID"):
            settings.projectx.account_id = int(v)
        if v := os.getenv("PROJECTX_REQUIRE_SIMULATED"):
            settings.projectx.require_simulated = v.strip().lower() not in {"0", "false", "no"}
        if v := os.getenv("PROP_FIRM"):
            settings.prop.firm = v
        if v := os.getenv("PROP_PHASE"):
            settings.prop.phase = v  # type: ignore[assignment]
        if v := os.getenv("PROP_ACCOUNT_SIZE"):
            settings.prop.account_size = float(v)
        return settings


def get_settings(path: Path | None = None) -> Settings:
    return Settings.load(path)
