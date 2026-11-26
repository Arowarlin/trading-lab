"""Reglas de decisión puras del pipeline de Discovery.

Extraídas de ``engine._rank1_candidates``, ``engine._select_finalists`` y
``levels.evaluate`` sin cambiar su comportamiento. El arnés T01 las reutiliza
con flujos de R sintéticos, de modo que mide exactamente las mismas puertas
que aplica el pipeline real.
"""

from __future__ import annotations

from typing import Any, Iterable

DEFAULT_DRIFT_PERCENTILE = 90.0
MIN_PROFIT_FACTOR = 1.1
DSR_CONFIRM_MIN = 0.90
PBO_MAX = 0.30
RANDOM_OOS2_MIN = 95.0


def drift_check(drift: dict[str, Any] | None) -> tuple[bool, str]:
    """Puerta de deriva. Sin registro de deriva no hay puerta (compatibilidad)."""

    if not drift:
        return True, ""
    minimum = float(drift.get("percentile_min") or DEFAULT_DRIFT_PERCENTILE)
    percentile = drift.get("percentile")
    if percentile is None:
        return False, f"sin datos < {minimum:g}"
    value = float(percentile)
    if value < minimum:
        return False, f"{value:.1f} < {minimum:g}"
    return True, ""


def is_positive(value: Any) -> bool:
    return value is not None and float(value) > 0.0


def positive_folds(folds: Iterable[dict[str, Any]] | None) -> int:
    return sum(
        1
        for row in (folds or [])
        if row.get("expectancy_r") is not None
        and float(row["expectancy_r"]) > 0.0
    )


def folds_ok(positive: int, folds: int) -> bool:
    return int(positive) >= max(1, int(folds) - 1)


def oos1_check(expectancy: Any, profit_factor: Any) -> tuple[bool, str]:
    """OOS-1: expectativa > 0 y PF > 1,1 (PF ausente cuenta como infinito)."""

    if expectancy is None or float(expectancy) <= 0.0:
        return False, f"OOS-1 expectativa {expectancy}"
    pf = float("inf") if profit_factor is None else float(profit_factor)
    if pf <= MIN_PROFIT_FACTOR:
        return False, f"OOS-1 PF {pf} <= 1,1"
    return True, ""


def level3_ok(
    *,
    is_finalist: bool,
    is_expectancy: Any,
    cost_x1_5: Any,
    perturb_noise_ok: bool,
    perturb_delay_ok: bool,
    perturb_execution_ok: bool,
) -> bool:
    return bool(
        is_finalist
        and is_expectancy is not None
        and float(is_expectancy) > 0.0
        and cost_x1_5 is not None
        and float(cost_x1_5) > 0.0
        and perturb_noise_ok
        and perturb_delay_ok
        and perturb_execution_ok
    )


def level4_ok(
    *,
    level3: bool,
    enough_oos2: bool,
    oos2: Any,
    dsr_confirm: Any,
    pbo: Any,
    wf_ok: Any,
    regime_ok: Any,
    slip2: Any,
    challenge_ok: Any,
    random_oos2: Any,
    dsr_threshold: float | None = None,
) -> bool:
    # ENG-1 S1: con puertas v3 el umbral viaja con el resultado (1 - alpha/m);
    # sin él, el de siempre.
    threshold = DSR_CONFIRM_MIN if dsr_threshold is None else float(dsr_threshold)
    return bool(
        level3
        and enough_oos2
        and oos2 is not None
        and float(oos2) > 0.0
        and dsr_confirm is not None
        and float(dsr_confirm) >= threshold
        and pbo is not None
        and float(pbo) <= PBO_MAX
        and wf_ok is True
        and regime_ok is True
        and slip2 is not None
        and float(slip2) > 0.0
        and challenge_ok is True
        and random_oos2 is not None
        and float(random_oos2) >= RANDOM_OOS2_MIN
    )


__all__ = [
    "DEFAULT_DRIFT_PERCENTILE",
    "DSR_CONFIRM_MIN",
    "MIN_PROFIT_FACTOR",
    "PBO_MAX",
    "RANDOM_OOS2_MIN",
    "drift_check",
    "folds_ok",
    "is_positive",
    "level3_ok",
    "level4_ok",
    "oos1_check",
    "positive_folds",
]
