"""Fase 3: validación de un solo disparo del candidato ``us500-nyopen``.

Reutiliza ``ea_us100.validate`` sin editarlo, parcheando en memoria:

* ``params_from_set`` para reescalar el ``slip`` (los otros tres inputs en
  puntos se reescalan en el setfile copiado).
* ``_record_trials`` para registrar las 8 variantes con la familia
  ``US500_NYOPEN_CONFLUENCE`` en lugar de la del US100.

No se ejecuta más de una vez: un marcador en el directorio del informe bloquea
cualquier reintento, incluso si el resultado es malo.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from ..config import DEFAULT_DB
from ..ea_us100 import GRID
from ..learning import count_tests
from ..trials import record_trial
from .candidate import (
    REPORT_DIR,
    SETFILE,
    SLIP_BASE,
    WINDOW_END,
    WINDOW_START,
    load_base_setfile,
    point_values,
    pre_registration_hash,
    scaled_values,
    validation_thresholds,
)

MARKER = REPORT_DIR / ".validated"


class AlreadyValidated(RuntimeError):
    pass


class ApprovalRequired(RuntimeError):
    pass


APPROVAL_PHRASE = "APRUEBO VALIDACION US500"


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _claim(output_dir: Path, *, pre_hash: str, data: dict) -> dict:
    marker = output_dir / ".validated"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.exists():
        raise AlreadyValidated(
            f"Ya existe una validación registrada en {marker}. "
            "No se reintenta con otros parámetros."
        )
    payload = {
        "status": "started",
        "started_at": _now().isoformat(timespec="seconds"),
        "pre_registration_hash": pre_hash,
        "cache_sha256": data.get("cache_sha256"),
        "ratio": data.get("ratio"),
        "window": {"start": WINDOW_START, "end": WINDOW_END},
    }
    marker.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _finish(output_dir: Path, *, pre_hash: str, verdict: str) -> None:
    marker = output_dir / ".validated"
    payload = {}
    if marker.exists():
        try:
            payload = json.loads(marker.read_text(encoding="utf-8")) or {}
        except (TypeError, ValueError):
            payload = {}
    payload.update(
        {
            "status": "completed",
            "finished_at": _now().isoformat(timespec="seconds"),
            "pre_registration_hash": pre_hash,
            "verdict": verdict,
        }
    )
    marker.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def verdict_from_filters(filters: dict) -> tuple[str, list[str]]:
    """Tres niveles del pre-registro a partir de los filtros de ``validate``."""
    dsr = filters.get("dsr") or {}
    dsr_value = dsr.get("value")
    dsr_ok = bool(dsr.get("ok"))
    other = {
        name: item
        for name, item in filters.items()
        if name not in {"dsr", "dsr_local"}
    }
    failed = [name for name, item in other.items() if not item.get("ok")]
    if dsr_value is None:
        return "NO PASA", [*failed, "dsr_sin_datos"]
    if not failed and dsr_ok:
        return "PASA", []
    if not failed and not dsr_ok:
        return "PASA SALVO DSR GLOBAL", ["dsr"]
    return "NO PASA", failed


def _record_us500_trials(
    db_path,
    rows: list[dict],
    *,
    baseline_index: int,
    run_id: str,
    symbol: str,
    srs: list[float] | None = None,
) -> None:
    srs = list(srs or [])
    for position, row in enumerate(rows):
        is_base = int(row["index"]) == baseline_index
        try:
            record_trial(
                db_path,
                family="US500_NYOPEN_CONFLUENCE",
                hypothesis=(
                    "Confluencia NY open US500: misma lógica v3 del EA us100-ftmo1 "
                    "con los cuatro parámetros en puntos reescalados por ATR."
                ),
                symbol="US500.cash",
                params={key: row[key] for key in GRID},
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                result={
                    key: row.get(key)
                    for key in ("n", "win", "pf", "expR", "totR", "maxDD_R")
                },
                outcome="passed" if is_base else "discarded",
                reason=(
                    "base del setfile v3 reescalada por ATR"
                    if is_base
                    else "variante del barrido v3; la base es el setfile v3 reescalado"
                ),
                source="sweep",
                run_id=run_id,
                counted=True,
                sr_period=srs[position] if position < len(srs) else None,
                periods_per_year=252.0,
            )
        except Exception:
            pass


@contextmanager
def _patched_ea_us100(ratio: float):
    import tradinglab.ea_us100 as ea

    original_params = ea.params_from_set
    original_record = ea._record_trials

    def params_from_set(values: dict) -> dict:
        params = original_params(values)
        params["slip"] = round(SLIP_BASE * float(ratio), 6)
        return params

    ea.params_from_set = params_from_set
    ea._record_trials = _record_us500_trials
    try:
        yield ea
    finally:
        ea.params_from_set = original_params
        ea._record_trials = original_record


def _relative_cost(measured_bps: float, last_close: float, atr: float) -> float | None:
    if last_close <= 0 or atr <= 0:
        return None
    return (measured_bps * last_close / 10_000.0) / atr


def validate_candidate(
    frame,
    *,
    ratio: float,
    data: dict,
    db_path=DEFAULT_DB,
    record: bool = True,
    output_dir: Path = REPORT_DIR,
    single_shot: bool = True,
    now: datetime | None = None,
) -> dict:
    """Ejecuta el pipeline completo una vez y escribe los informes de Fase 3."""
    output_dir = Path(output_dir)
    pre_hash = pre_registration_hash()
    if single_shot:
        _claim(output_dir, pre_hash=pre_hash, data=data)

    values = load_base_setfile(SETFILE)
    scaled = scaled_values(values, ratio)
    with _patched_ea_us100(ratio) as ea:
        payload = ea.validate(frame, scaled, ea=None, db_path=db_path, record=record)

    payload["ea"] = "us500-nyopen"
    payload["symbol"] = "US500.cash"
    payload["setfile"] = str(SETFILE)
    payload["candidate"] = "us500-nyopen"
    payload["pre_registration_hash"] = pre_hash
    payload["generated_at"] = (now or _now()).isoformat(timespec="seconds")
    payload["ratio"] = round(float(ratio), 8)
    payload["rescale"] = point_values(values, ratio)
    payload["thresholds"] = validation_thresholds()
    payload["n_trials_after"] = int(count_tests(db_path))

    us500 = data.get("us500") or {}
    us100 = data.get("us100") or {}
    payload["relative_cost"] = {
        "us500": {
            **us500,
            "spread_over_atr": _relative_cost(
                float(us500.get("measured_bps") or 0.0),
                float(us500.get("last_close") or 0.0),
                float(us500.get("atr_median") or 0.0),
            ),
        },
        "us100": {
            **us100,
            "spread_over_atr": _relative_cost(
                float(us100.get("measured_bps") or 0.0),
                float(us100.get("last_close") or 0.0),
                float(us100.get("atr_median") or 0.0),
            ),
        },
    }
    verdict, reasons = verdict_from_filters(payload["filters"])
    payload["verdict"] = verdict
    payload["verdict_reasons"] = reasons
    payload["passed_all_gates"] = bool(payload.get("passed"))
    payload["run_id"] = uuid.uuid4().hex[:12]

    from .report import write_validation_report

    payload["files"] = write_validation_report(payload, out_dir=output_dir)
    if single_shot:
        _finish(output_dir, pre_hash=pre_hash, verdict=verdict)
    return payload


def data_context(report: dict, us500_frame, us100_frame) -> dict:
    """Datos de coste relativo (spread medido / ATR) para el informe."""
    from ..broker_costs import load_spreads
    from .atr import median_rth_atr, ny_naive_index, wilder_atr

    us500 = ny_naive_index(us500_frame).loc[WINDOW_START:WINDOW_END]
    us100 = ny_naive_index(us100_frame).loc[WINDOW_START:WINDOW_END]
    atr500, _ = median_rth_atr(us500, wilder_atr(us500))
    atr100, _ = median_rth_atr(us100, wilder_atr(us100))
    rows100 = load_spreads(symbol="US100.CASH", source="broker")
    measured100 = float(rows100["median_bps"].median()) if len(rows100) else 0.0
    return {
        "us500": {
            "measured_bps": float(report["spread"]["measured"]["median_bps"]),
            "last_close": float(us500["close"].iloc[-1]),
            "atr_median": float(atr500),
        },
        "us100": {
            "measured_bps": measured100,
            "last_close": float(us100["close"].iloc[-1]),
            "atr_median": float(atr100),
        },
    }


__all__ = [
    "APPROVAL_PHRASE",
    "AlreadyValidated",
    "ApprovalRequired",
    "MARKER",
    "data_context",
    "validate_candidate",
    "verdict_from_filters",
]
