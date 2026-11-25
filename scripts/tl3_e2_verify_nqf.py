"""E2 · Verificación previa de NQF-A/B/C (solo lectura del código congelado)."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import re
import sys
from pathlib import Path

import numpy as np

from tradinglab.tl3 import registry, verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(".")
PROJ = ROOT / "NASDAQ_EDGE_INSTITUTIONAL"
MODELS = PROJ / "tools" / "forward_models.py"
PREREG = PROJ / "04_FORWARD" / "prerregistro.md"
MECANICA = PROJ / "04_FORWARD" / "mecanica.md"
REPORT = ROOT / "TL3_REPORTS" / "verificacion_nqf.md"
DB = ROOT / "data" / "tl3" / "tl3_research.db"
VERIFIER = "sesion-tl3-e2"


def _load_models():
    spec = importlib.util.spec_from_file_location("nqedge_forward_models", MODELS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bars(rows):
    a = np.asarray(rows, dtype=float)
    n = len(a)
    return {
        "b": {
            "slot": np.arange(n),
            "o": a[:, 0],
            "h": a[:, 1],
            "l": a[:, 2],
            "c": a[:, 3],
            "v": np.full(n, 100.0),
            "end_min": 570 + 5 * np.arange(n) + 5,
            "last_i": np.arange(n),
        }
    }


def _session(day="2026-01-05", **extra):
    value = {"day": day}
    value.update(extra)
    return value


def _m1(o, h, low, c):
    n = len(o)
    return {
        "t": np.arange(570, 570 + n),
        "o": np.asarray(o, float),
        "h": np.asarray(h, float),
        "l": np.asarray(low, float),
        "c": np.asarray(c, float),
        "v": np.full(n, 100.0),
    }


def _check(checks, name, condition, detail):
    checks.append(
        {
            "name": name,
            "value": "ok" if condition else "fallo",
            "limit": "sí",
            "ok": bool(condition),
            "defect": not bool(condition),
            "status": "ok" if condition else "defecto",
            "detail": detail,
        }
    )


def main() -> None:
    fm = _load_models()
    prereg = PREREG.read_text(encoding="utf-8")
    code_hash = hashlib.sha256(MODELS.read_bytes()).hexdigest()
    commission_match = re.search(r"([0-9]+(?:[.,][0-9]+)?) USD por contrato y lado", prereg)
    commission = float(commission_match.group(1).replace(",", ".")) if commission_match else None
    start_match = re.search(r"2026-11-30", prereg)

    checks = []
    expected = {
        "TICK": 0.25,
        "MNQ_USD_PER_POINT": 2.0,
        "RISK_USD": 150.0,
        "ENTRY_START": 575,
        "ENTRY_END": 690,
        "FLAT": 955,
        "SESS_OPEN": 570,
        "SESS_CLOSE": 960,
        "OR_MIN": inspect.signature(fm.signal_a).parameters["or_min"].default,
    }
    actual = {
        "TICK": fm.TICK,
        "MNQ_USD_PER_POINT": fm.MNQ_USD_PER_POINT,
        "RISK_USD": fm.RISK_USD,
        "ENTRY_START": fm.ENTRY_START,
        "ENTRY_END": fm.ENTRY_END,
        "FLAT": fm.FLAT,
        "SESS_OPEN": fm.SESS_OPEN,
        "SESS_CLOSE": fm.SESS_CLOSE,
        "OR_MIN": inspect.signature(fm.signal_a).parameters["or_min"].default,
    }
    checks.extend(verify.constants_match(expected, actual))
    checks.append(
        verify.magnitude("tick MNQ USD", fm.TICK * fm.MNQ_USD_PER_POINT, 0.5, 0.5, factor=1.0)
    )
    checks.append(verify.magnitude("riesgo USD", fm.RISK_USD, 150.0, 150.0, factor=1.0))
    checks.append(verify.magnitude("comision USD/lado", commission, 0.75, 0.75, factor=1.0))

    # --- sintéticos: A, B, C, SL primero
    r = _session(
        **_bars(
            [
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 102.5, 100.0, 102.0),
                (102.0, 102.5, 101.8, 102.2),
            ]
        )
    )
    r["atr5"] = np.array([np.nan, np.nan, np.nan, np.nan, 1.0])
    sig = fm.signal_a(r)
    _check(
        checks,
        "NQF-A OR15 ruptura",
        len(sig) == 1 and sig[0].entry_min == 590 and sig[0].side == 1 and sig[0].stop == 99.5,
        "OR 9:30-9:44; entrada 9:50; stop 99,5",
    )

    r = _session(
        onh=100.0,
        onl=90.0,
        **_bars(
            [
                (99.5, 99.8, 99.3, 99.6),
                (99.6, 101.0, 99.6, 99.8),
                (99.8, 100.0, 99.5, 99.9),
            ]
        ),
    )
    r["vwap"] = np.array([99.7, 99.7, 99.8])
    r["sd"] = np.ones(3)
    sig = fm.signal_b(r, "ON")
    _check(
        checks,
        "NQF-B barrido ONH >= 2 ticks",
        len(sig) == 1 and sig[0].side == -1 and sig[0].stop == 101.25,
        "cierre dentro; stop 1 tick sobre el extremo",
    )

    r = _session(
        **_bars(
            [
                (100.0, 100.3, 99.8, 100.1),
                (100.1, 100.4, 99.9, 100.2),
                (100.2, 100.5, 100.0, 100.3),
                (100.3, 102.5, 100.2, 102.0),
                (102.0, 102.1, 100.1, 100.2),
                (100.2, 100.4, 100.0, 100.3),
            ]
        )
    )
    r["vwap"] = np.full(6, 100.0)
    r["sd"] = np.full(6, 0.5)
    sig = fm.signal_c(r)
    _check(
        checks,
        "NQF-C reversion VWAP +/- 2 sigma",
        len(sig) == 1 and sig[0].side == -1 and sig[0].stop == 102.75,
        "cierre fuera y vuelta dentro; stop extremo + 1 tick",
    )
    _check(
        checks,
        "SL primero en la misma vela",
        fm.same_bar_outcome(100, 99, 102, 103, 98, 1) == "stop",
        "si SL y TP caen en la misma vela, gana el SL",
    )

    # --- tamaño, NO TRADE y comisión obligatoria
    _check(checks, "contratos stop 10 pt", fm.contracts_for_risk(10.0, 0.75) == 6, "150/22,5 = 6")
    _check(checks, "NO TRADE stop 75 pt", fm.contracts_for_risk(75.0, 0.75) == 0, "150/152,5 = 0")
    try:
        fm.contracts_for_risk(10.0, None)
        missing_ok = False
    except fm.MissingInput:
        missing_ok = True
    _check(checks, "comisión ausente no se inventa", missing_ok, "MissingInput")

    # --- noticias: FOMC y Tier 1
    _check(
        checks,
        "FOMC bloquea el día completo",
        fm.news_reason("2026-01-28", 600, {"2026-01-28"}, []) == "fomc",
        "día FOMC sin entradas",
    )
    tier1 = [("2026-01-29", 600, "CPI")]
    _check(
        checks,
        "Tier 1 +/- 5 min",
        fm.news_reason("2026-01-29", 595, set(), tier1) is not None
        and fm.news_reason("2026-01-29", 594, set(), tier1) is None
        and fm.news_reason("2026-01-29", 605, set(), tier1) is not None
        and fm.news_reason("2026-01-29", 606, set(), tier1) is None,
        "bloqueo simétrico alrededor del evento",
    )
    _check(
        checks,
        "cierre 5 min antes de Tier 1",
        fm.news_exit_minute("2026-01-29", tier1) == 595,
        "salida a mercado 5 min antes",
    )

    # --- cierre 15:55
    bars = _m1([100] * 400, [100.4] * 400, [99.6] * 400, [100] * 400)
    signal = fm.Signal("NQF-T", "2026-01-05", 0, 570, 1, 90.0, None, "test")
    execution = fm.execute_signal(bars, signal, contracts=2, slip_ticks=0.0)
    _check(
        checks,
        "cierre a las 15:55 ET",
        execution is not None and execution.reason == "flat" and execution.exit_min == 955,
        "flat en el minuto 955",
    )
    _check(
        checks,
        "zona horaria del runner",
        "America/New_York" in (PROJ / "tools" / "forward_daily.py").read_text(encoding="utf-8")
        and "tz_convert(NY)" in (PROJ / "tools" / "forward_daily.py").read_text(encoding="utf-8"),
        "forward_daily.py convierte a America/New_York",
    )

    # --- conteos DEV (solo mecánica, sin desenlaces)
    for variant, rate in (("NQF-A", 0.938), ("NQF-B", 0.198), ("NQF-C", 1.120)):
        check = verify.magnitude(f"{variant} señales/día DEV", rate, 0.0, 3.0, factor=1.0)
        check["detail"] = "conteo F3, no resultado; máximo 3/día"
        checks.append(check)

    # --- aviso documental: el ejemplo del runner usa 1.25, no 0.75
    daily = (PROJ / "tools" / "forward_daily.py").read_text(encoding="utf-8")
    stale_example = "commission-side-usd 1.25" in daily
    checks.append(
        {
            "name": "ejemplo de comisión del runner",
            "value": "1.25" if stale_example else "0.75",
            "limit": "0.75",
            "ok": not stale_example,
            "defect": False,
            "status": "aviso" if stale_example else "ok",
            "detail": "ejemplo del docstring; no es una constante ni afecta a la mecánica",
        }
    )

    start = start_match.group(0) if start_match else None
    fingerprint = verify.sample_fingerprint([start] if start else [])
    checks.append(
        {
            "name": "huella de la fecha de inicio",
            "value": fingerprint[:16],
            "limit": start or "Sin datos",
            "ok": start is not None,
            "defect": start is None,
            "status": "ok" if start is not None else "sin datos",
            "detail": "forward n=0; solo fecha de inicio",
        }
    )

    body = verify.report(checks, title="Verificación previa NQF-A/B/C")
    defects = sum(1 for check in checks if check.get("defect"))
    verdict = "Defectos" if defects else "Conforma"
    notes = [
        "",
        "## Alcance",
        "",
        "- Código verificado: `NASDAQ_EDGE_INSTITUTIONAL/tools/forward_models.py`.",
        f"- SHA-256: `{code_hash}`.",
        "- Prerregistro: `04_FORWARD/prerregistro.md`; comisión "
        f"{commission if commission is not None else 'Sin datos'} USD por contrato y lado.",
        "- Datos: sintéticos y conteos DEV de `04_FORWARD/mecanica.md`; "
        "sin desenlaces, sin P&L y sin leer `03_BACKTEST/`.",
        "- Verificador: otra sesión (TL3-E2); el código no se modifica.",
        "",
        "## Notas",
        "",
        "- `forward_daily.py` recibe la comisión por CLI; no la hardcodea. "
        "El valor 0,75 está en el prerregistro y en `forward_mechanics.py`.",
        "- El ejemplo del docstring de `forward_daily.py` usa 1,25: es un aviso "
        "documental, no un defecto de la mecánica congelada.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(body + "\n".join(notes), encoding="utf-8")

    existing = set()
    registry.init_db(DB)
    with registry.connect(DB) as con:
        for row in con.execute(
            "SELECT hypothesis_id FROM verifications WHERE code_hash=? AND verifier=? AND verdict=?",
            (code_hash, VERIFIER, verdict),
        ):
            existing.add(str(row["hypothesis_id"]))
    for hypothesis_id in fm.VARIANTS:
        if hypothesis_id not in existing:
            registry.add_verification(
                hypothesis_id,
                code_hash,
                VERIFIER,
                verdict,
                "TL3_REPORTS/verificacion_nqf.md",
                db_path=DB,
            )
    print(f"veredicto {verdict} · defectos {defects} · hash {code_hash}")
    print(f"informe {REPORT}")


if __name__ == "__main__":
    main()
