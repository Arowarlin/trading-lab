"""Candidato ``us500-nyopen``: setfile v3, reescalado y pre-registro.

No ejecuta backtests ni envía órdenes. Solo prepara los parámetros que usará
``validation.py`` y fija por hash el pre-registro del candidato.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import ROOT
from ..ea_us100 import GRID, load_setfile, params_from_set
from ..profiles import get_profile

CANDIDATE_ID = "us500-nyopen"
SOURCE_EA = "us100-ftmo1"
SYMBOL = "US500.cash"
SOURCE_SYMBOL = "US100.cash"
SETFILE = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
US100_CACHE = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
US500_CACHE = ROOT / "data" / "cache" / "ea_lab" / "us500_m5.parquet"
REPORT_DIR = ROOT / "reports" / "research" / "ea_us500_nyopen"

WINDOW_START = "2021-09-15"
WINDOW_END = "2026-11-13"
WINDOW_TZ = "America/New_York"

RISK_PCT = 0.35
BASELINE = {"min_score": 55, "rr": 3.5, "gap_min": 0.7, "max_consec": 1}

#: Inputs del setfile y valor del motor expresado en puntos/precio.
POINT_INPUTS = ("InpSlBufAtr", "InpMinSlPts", "InpMaxSpreadPts")
SLIP_BASE = 0.5

VERDICT_LEVELS = {
    "PASA": "cumple todos los criterios, incluido DSR global >= 0,90; "
            "habilita forward en demo y, si el operador lo decide, challenge",
    "PASA SALVO DSR GLOBAL": "cumple todos los demás criterios y solo falla el "
                             "DSR global; solo autoriza un forward en demo, nunca un challenge",
    "NO PASA": "falla cualquier otro criterio; se archiva sin reintentos",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setfile_sha256(path: Path = SETFILE) -> str:
    return _sha256(path)


def load_base_setfile(path: Path = SETFILE) -> dict:
    return load_setfile(path)


def scaled_values(values: dict, ratio: float) -> dict:
    """Copia el setfile y multiplica solo los inputs en puntos por ``ratio``."""
    out = dict(values)
    for key in POINT_INPUTS:
        out[key] = round(float(values[key]) * float(ratio), 6)
    return out


def scaled_params(values: dict, ratio: float) -> dict:
    """Parámetros del motor con los cuatro valores en puntos reescalados."""
    params = params_from_set(scaled_values(values, ratio))
    params["slip"] = round(SLIP_BASE * float(ratio), 6)
    return params


def point_values(values: dict, ratio: float) -> dict:
    """Comparativa base → escalado de los cuatro parámetros, para el informe."""
    base = params_from_set(values)
    scaled = scaled_params(values, ratio)
    return {
        "ratio": round(float(ratio), 8),
        "sl_buf": {"base": base["sl_buf"], "scaled": scaled["sl_buf"]},
        "min_sl": {"base": base["min_sl"], "scaled": scaled["min_sl"]},
        "max_spread": {"base": base["max_spread"], "scaled": scaled["max_spread"]},
        "slip": {"base": SLIP_BASE, "scaled": scaled["slip"]},
    }


def validation_thresholds() -> dict:
    profile = get_profile("intraday_fx")
    if profile is None:
        raise RuntimeError("falta el perfil intraday_fx en config/profiles.yaml")
    criteria = profile.validation
    return {
        "min_trades": int(criteria.min_trades),
        "min_dsr": float(criteria.min_dsr),
        "max_pbo": float(criteria.max_pbo),
        "walk_forward": {
            "min_folds": 3,
            "min_stitched_sharpe": 0.0,
            "min_frac_positive": 0.5,
            "min_efficiency": 0.3,
            "min_rank_pct": 0.5,
            "min_stability": 0.3,
        },
        "regime": {"years": [2021, 2022, 2023, 2024, 2025, 2026], "min_obs": 20, "min_return": 0.0},
        "pbo": {"blocks": 16, "seed": 0},
        "cost": {"slippage_points": [1.0, 2.0], "require_positive_at_2": True},
        "spread": {"require_positive_median": True},
        "monte_carlo": {
            "rules": "ftmo/challenge/100000",
            "n_paths": 5000,
            "horizon_days": 21,
            "seed": 42,
        },
    }


def pre_registration(path: Path = SETFILE) -> dict:
    """Términos congelados del pre-registro; su hash va en la documentación."""
    return {
        "candidate": CANDIDATE_ID,
        "source_ea": SOURCE_EA,
        "symbol": SYMBOL,
        "source_symbol": SOURCE_SYMBOL,
        "setfile": str(path.relative_to(ROOT)).replace("\\", "/"),
        "setfile_sha256": setfile_sha256(path),
        "window": {"start": WINDOW_START, "end": WINDOW_END, "tz": WINDOW_TZ},
        "grid": {key: list(value) for key, value in GRID.items()},
        "baseline": dict(BASELINE),
        "rescaling": {
            "inputs": list(POINT_INPUTS),
            "slip_base": SLIP_BASE,
            "method": "median_rth_atr14_ratio",
            "atr_len": 14,
            "rth": "09:30-15:59",
            "ratio_formula": "median_atr_us500 / median_atr_us100",
        },
        "cost": {
            "source": "broker_spreads",
            "symbol": SYMBOL,
            "source_filter": "broker",
            "max_age_days": 7,
            "floor": "max(bar_spread, close * median_bps / 10000)",
            "measure_command": "lab ticks broker-spread US500.cash --days 7",
        },
        "verdict": VERDICT_LEVELS,
        "thresholds": validation_thresholds(),
        "protocol": {
            "single_shot": True,
            "record_family": "US500_NYOPEN_CONFLUENCE",
            "risk_pct": RISK_PCT,
        },
    }


def pre_registration_payload() -> str:
    return json.dumps(pre_registration(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def pre_registration_hash() -> str:
    return hashlib.sha256(pre_registration_payload().encode("utf-8")).hexdigest()


__all__ = [
    "BASELINE",
    "CANDIDATE_ID",
    "POINT_INPUTS",
    "REPORT_DIR",
    "SETFILE",
    "SLIP_BASE",
    "SOURCE_EA",
    "SOURCE_SYMBOL",
    "SYMBOL",
    "US100_CACHE",
    "US500_CACHE",
    "VERDICT_LEVELS",
    "WINDOW_END",
    "WINDOW_START",
    "WINDOW_TZ",
    "load_base_setfile",
    "point_values",
    "pre_registration",
    "pre_registration_hash",
    "pre_registration_payload",
    "scaled_params",
    "scaled_values",
    "setfile_sha256",
    "validation_thresholds",
]
