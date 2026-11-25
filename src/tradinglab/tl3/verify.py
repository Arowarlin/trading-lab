"""E2 · Verificación de conformidad antes de una prueba que cuenta."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable


def magnitude(
    name: str,
    value: Any,
    lo: float,
    hi: float,
    *,
    factor: float = 3.0,
) -> dict:
    """Comprueba una magnitud contra un rango esperado.

    Fuera del rango por un factor ``factor`` o más es defecto; por menos, aviso.
    """

    lo_f, hi_f = float(lo), float(hi)
    if hi_f < lo_f:
        raise ValueError("rango invertido")
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float("nan")
    if not math.isfinite(number):
        return {
            "name": name,
            "value": value,
            "lo": lo_f,
            "hi": hi_f,
            "factor": None,
            "ok": False,
            "defect": True,
            "status": "sin datos",
        }
    if lo_f <= number <= hi_f:
        ratio, status = 1.0, "ok"
    else:
        if number > hi_f:
            ratio = float("inf") if hi_f <= 0 else number / hi_f
        else:
            ratio = float("inf") if number <= 0 else lo_f / number
        status = "defecto" if ratio >= float(factor) else "aviso"
    return {
        "name": name,
        "value": number,
        "lo": lo_f,
        "hi": hi_f,
        "factor": ratio,
        "ok": status == "ok",
        "defect": status == "defecto",
        "status": status,
    }


def constants_match(prereg: dict, code: dict) -> list[dict]:
    """Tabla línea a línea de constantes del prerregistro frente al código."""

    rows = []
    for key in sorted(set(prereg) | set(code)):
        expected = prereg.get(key)
        actual = code.get(key)
        ok = expected == actual
        rows.append(
            {
                "name": str(key),
                "value": actual,
                "limit": expected,
                "ok": ok,
                "defect": not ok,
                "status": "ok" if ok else "defecto",
                "detail": "constante",
            }
        )
    return rows


def trigger_rate(
    observed: Any,
    expected: Any,
    *,
    low: float = 0.5,
    high: float = 2.0,
) -> dict:
    """Frecuencia observada frente a la esperada; fuera de [low, high] = defecto."""

    obs, exp = float(observed), float(expected)
    if exp <= 0:
        raise ValueError("frecuencia esperada debe ser > 0")
    ratio = obs / exp
    ok = low <= ratio <= high
    return {
        "name": "trigger_rate",
        "value": obs,
        "expected": exp,
        "limit": f"{low:g}x..{high:g}x",
        "factor": ratio,
        "ok": ok,
        "defect": not ok,
        "status": "ok" if ok else "defecto",
    }


def sample_fingerprint(ids: Iterable[Any]) -> str:
    """SHA-256 canónico de ids o fechas (sin ordenar por tipo)."""

    values = sorted({str(value).strip() for value in ids})
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _fmt(value: Any) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, float):
        if math.isnan(value):
            return "Sin datos"
        if math.isinf(value):
            return "∞"
        return f"{value:.4g}"
    return str(value)


def report(checks: Iterable[dict] | dict, *, title: str = "Verificación") -> str:
    """Informe markdown con veredicto Conforma / Defectos."""

    items = [checks] if isinstance(checks, dict) else list(checks)
    lines = [
        f"# {title}",
        "",
        "| Comprobación | Valor | Límite | Factor | Estado | Detalle |",
        "|---|---:|---:|---:|---|---|",
    ]
    defects = 0
    avisos = 0
    for check in items:
        defect = bool(check.get("defect", not check.get("ok", False)))
        status = str(
            check.get("status")
            or ("defecto" if defect else ("ok" if check.get("ok") else "sin datos"))
        )
        if defect:
            defects += 1
        elif status == "aviso":
            avisos += 1
        limit = check.get("limit")
        if limit is None and "lo" in check and "hi" in check:
            limit = f"{_fmt(check['lo'])}..{_fmt(check['hi'])}"
        lines.append(
            f"| {check.get('name', '')} | {_fmt(check.get('value', check.get('code')))} | "
            f"{_fmt(limit)} | {_fmt(check.get('factor'))} | {status} | "
            f"{check.get('detail', '')} |"
        )
    verdict = "Defectos" if defects else "Conforma"
    extra = f" ({avisos} avisos)" if avisos else ""
    lines += [
        "",
        f"**Veredicto: {verdict}** — {len(items)} comprobaciones, "
        f"{defects} defectos{extra}.",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "constants_match",
    "magnitude",
    "report",
    "sample_fingerprint",
    "trigger_rate",
]
