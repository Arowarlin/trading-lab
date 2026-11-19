"""Anclajes y pre-registro de las variantes de sesión del EA US100.

Dos candidatos, mismo símbolo y mismos parámetros que ``us100-ftmo1``:

* ``us100-london`` — apertura de Londres (Europe/London).
* ``us100-asia`` — apertura de Tokio (Asia/Tokyo).

No ejecuta backtests ni envía órdenes. Solo fija los términos que usarán los
documentos y, en su fase, la validación de un solo disparo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import ROOT
from ..ea_us100 import GRID, load_setfile
from . import session_engine
from .candidate import VERDICT_LEVELS, setfile_sha256, validation_thresholds

SYMBOL = "US100.cash"
SOURCE_EA = "us100-ftmo1"
SETFILE = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
OWN_CACHE = ROOT / "data" / "cache" / "ea_lab" / "us100_m5.parquet"
EA_CACHE = ROOT / "data" / "cache" / "ea" / "US100_CASH_M5_NY.parquet"
WINDOW_START = "2021-09-15"
WINDOW_END = "2026-11-13"

NYSE_ANCHORS = dict(
    tz="America/New_York",
    or_start="09:30",
    or_end="09:45",
    rth_start="09:30",
    rth_end="16:00",
    on_start="18:00",
    on_end="09:30",
    on_start_tz="America/New_York",
    on_end_tz="America/New_York",
    pm_start="08:00",
    trade_start="09:35",
    trade_end="11:30",
    flat_at="15:45",
    calendar="nyse",
    min_before_flat=60,
)

LONDON_ANCHORS = dict(
    tz="Europe/London",
    or_start="08:00",
    or_end="08:15",
    rth_start="08:00",
    rth_end="16:30",
    on_start="00:00",
    on_end="07:00",
    on_start_tz="Europe/London",
    on_end_tz="Europe/London",
    pm_start=None,
    trade_start="08:05",
    trade_end="10:00",
    flat_at="14:15",
    calendar="weekdays",
    min_before_flat=60,
)

ASIA_ANCHORS = dict(
    tz="Asia/Tokyo",
    or_start="09:00",
    or_end="09:15",
    rth_start="09:00",
    rth_end="15:00",
    on_start="16:00",
    on_end="09:00",
    on_start_tz="America/New_York",
    on_end_tz="Asia/Tokyo",
    pm_start=None,
    trade_start="09:05",
    trade_end="11:00",
    flat_at="15:15",
    calendar="weekdays",
    min_before_flat=60,
)

CANDIDATES = {
    "us100-london": {
        "anchors": LONDON_ANCHORS,
        "doc": "docs/ea_lab/us100_london.md",
        "report_dir": "reports/research/ea_us100_london",
        "hypothesis": (
            "La apertura de Londres concentra el flujo institucional europeo y la "
            "primera hora de liquidez del CFD US100; la misma confluencia de sweep, "
            "FVG, VWAP, estructura, RVOL y rango de apertura debería capturarla."
        ),
    },
    "us100-asia": {
        "anchors": ASIA_ANCHORS,
        "doc": "docs/ea_lab/us100_asia.md",
        "report_dir": "reports/research/ea_us100_asia",
        "hypothesis": (
            "La apertura de Tokio es la principal ventana de liquidez asiática del "
            "CFD US100; tras el cierre de Nueva York, el rango nocturno y el open de "
            "Tokio deberían reproducir la misma subasta de confluencia."
        ),
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_sha256() -> str:
    return _sha256(Path(session_engine.__file__))


def anchors_for(candidate: str) -> dict:
    if candidate not in CANDIDATES:
        raise KeyError(f"candidato desconocido: {candidate}")
    return dict(CANDIDATES[candidate]["anchors"])


def base_params() -> dict:
    from ..ea_us100 import params_from_set

    return params_from_set(load_setfile(SETFILE))


def pre_registration(candidate: str) -> dict:
    if candidate not in CANDIDATES:
        raise KeyError(f"candidato desconocido: {candidate}")
    meta = CANDIDATES[candidate]
    return {
        "candidate": candidate,
        "source_ea": SOURCE_EA,
        "symbol": SYMBOL,
        "setfile": str(SETFILE.relative_to(ROOT)).replace("\\", "/"),
        "setfile_sha256": setfile_sha256(SETFILE),
        "session_engine": "src/tradinglab/ea_lab/session_engine.py",
        "session_engine_sha256": engine_sha256(),
        "session_engine_version": session_engine.VERSION,
        "window": {"start": WINDOW_START, "end": WINDOW_END, "tz": "America/New_York"},
        "anchors": meta["anchors"],
        "hypothesis": meta["hypothesis"],
        "grid": {key: list(value) for key, value in GRID.items()},
        "rescale": "ninguno: mismo símbolo y mismos parámetros del setfile v3",
        "thresholds": validation_thresholds(),
        "verdict": VERDICT_LEVELS,
        "data": {
            "cache": "data/cache/ea_lab/us100_m5.parquet",
            "source": "AttachOnlyBroker (solo lectura)",
            "ea_cache_read_only": "data/cache/ea/US100_CASH_M5_NY.parquet",
            "window_start": WINDOW_START,
            "window_end": WINDOW_END,
        },
        "cost": {
            "source": "broker_spreads",
            "symbol": "US100.CASH",
            "source_filter": "broker",
            "max_age_days": 7,
            "floor": "max(bar_spread, close * median_bps / 10000)",
            "measure_command": "lab ticks broker-spread US100.cash --days 7",
        },
        "equivalence": {
            "required": "100% de las operaciones idénticas a ea_us100_engine.run",
            "ny_anchors": NYSE_ANCHORS,
        },
        "protocol": {
            "single_shot": True,
            "no_optimization": True,
            "record_family": f"{candidate.replace('-', '_').upper()}_CONFLUENCE",
        },
    }


def pre_registration_hash(candidate: str) -> str:
    payload = json.dumps(
        pre_registration(candidate), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ASIA_ANCHORS",
    "CANDIDATES",
    "EA_CACHE",
    "LONDON_ANCHORS",
    "NYSE_ANCHORS",
    "OWN_CACHE",
    "SETFILE",
    "SYMBOL",
    "WINDOW_END",
    "WINDOW_START",
    "anchors_for",
    "base_params",
    "engine_sha256",
    "pre_registration",
    "pre_registration_hash",
]
