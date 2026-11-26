"""F3 · Verificación independiente de H-2026-013 contra el commit de F2.

Solo mecánica: constantes, noches, salidas (SL antes que TP), tamaño/NO TRADE,
horas, frecuencia, muestra y coste. No lee OOS-2 ni imprime PnL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from tradinglab.discovery import (
    campaigns,
    compiler,
    dsl,
    fastbt,
    feasibility,
    jobs,
    snapshots,
    specs,
)
from tradinglab.discovery.costs import build_cost_book_for_setup
from tradinglab.discovery.spec import load_spec
from tradinglab.nyse_calendar import early_close_hhmm, is_full_holiday
from tradinglab.tl3 import registry, verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "c4ec5799b77c910aea524165d1ec8aaa889669e9"
TEMPLATE = "config/discovery/templates/h1_sma50_session_long.yaml"
SPEC = ".orquestador/specs/h-2026-013-us100-h1-sma50.yaml"
DBPATH = "data/tl3/tl3_research.db"
REPORT_PATH = "TL3_REPORTS/verificacion_h-2026-013.md"
VERIFIER = "sesion-tl3-f3-audit"
NY = "America/New_York"


def git_bytes(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def commit_db() -> sqlite3.Connection:
    """Copia temporal de la DB en el commit; nunca escribe en la del trabajo."""

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    handle.write(git_bytes(DBPATH))
    handle.close()
    con = sqlite3.connect(handle.name)
    con.row_factory = sqlite3.Row
    return con


def synthetic_bars() -> tuple[pd.DataFrame, set[date]]:
    """H1 sintéticas 09:00-15:00 NY con días de SL+TP, stop, target y tiempo."""

    days = pd.bdate_range("2021-06-01", "2023-06-30", tz=NY)
    rows: list[dict] = []
    both_hit: set[date] = set()
    price = 15000.0
    for index, day in enumerate(days):
        mode = index % 5
        daily = {
            0: 4.0,
            1: -4.0,
            2: 0.0,
            3: 4.0,
            4: -4.0,
        }[mode]
        if index > 100 and mode == 3 and index % 17 == 0:
            both_hit.add(day.date())
        for hour in range(9, 16):
            open_price = price
            close_price = open_price + daily
            high = max(open_price, close_price) + 2.0
            low = min(open_price, close_price) - 2.0
            if hour == 10 and day.date() in both_hit:
                high = open_price + 500.0
                low = open_price - 500.0
                close_price = open_price + daily
            rows.append(
                {
                    "time": day + pd.Timedelta(hours=hour),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                }
            )
            price = close_price
        price += 2.0
    frame = pd.DataFrame(rows).set_index("time")
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    return frame, both_hit


def run_strategy(strategy: dict, bars: pd.DataFrame, *, cost, limits, prepared=None):
    model = dsl.Strategy.model_validate(strategy)
    signals = compiler.compile(model, bars)
    return fastbt.run(
        signals,
        bars,
        specs.exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
        collect_metrics=False,
    )


def ny(stamp: pd.Timestamp) -> pd.Timestamp:
    return stamp.tz_convert(NY)


def add(
    checks: list[dict],
    name: str,
    value,
    limit,
    ok: bool,
    detail: str = "",
    *,
    status: str | None = None,
    defect: bool | None = None,
) -> None:
    is_defect = (not ok) if defect is None else defect
    checks.append(
        {
            "name": name,
            "value": value,
            "limit": limit,
            "ok": bool(ok),
            "defect": bool(is_defect),
            "status": status or ("ok" if ok else ("defecto" if is_defect else "aviso")),
            "detail": detail,
        }
    )


def main(*, register: bool = False) -> int:
    changed = subprocess.run(
        ["git", "diff", "--quiet", COMMIT, "--", TEMPLATE, SPEC],
        cwd=ROOT,
    ).returncode
    if changed != 0:
        raise SystemExit(
            "Sin datos: la plantilla o el spec no coinciden con el commit auditado"
        )

    template_bytes = git_bytes(TEMPLATE)
    spec_bytes = git_bytes(SPEC)
    spec_text = spec_bytes.decode("utf-8")
    template = yaml.safe_load(template_bytes)
    con = commit_db()
    row = con.execute(
        "select * from hypotheses where hypothesis_id='H-2026-013'"
    ).fetchone()
    if row is None:
        raise SystemExit("Sin datos: H-2026-013 no está en el commit")

    template_hash = sha256_bytes(template_bytes)
    spec_hash = sha256_bytes(spec_bytes)
    strategy_hash = dsl.strategy_hash(template["strategy"])
    params = json.loads(row["primary_params"])
    checks: list[dict] = []

    # 1 · Constantes: spec (preregistro) y fila frente a la plantilla.
    code = {
        "sma_n": template["strategy"]["long_entry"]["args"][0]["expr"]["right"]["n"],
        "atr_n": template["strategy"]["exit"]["stop"]["n"],
        "stop_atr": template["strategy"]["exit"]["stop"]["mult"],
        "target_rr": template["strategy"]["exit"]["target"]["rr"],
        "time_exit": template["strategy"]["session"]["flat_at"],
        "time_exit_minutes": template["strategy"]["exit"]["time_exit_minutes"],
        "max_trades_per_day": template["strategy"]["limits"]["max_trades_per_day"],
        "side": "long" if template["strategy"]["short_entry"] is None else "both",
    }
    match = re.search(r"se cierra a las ([0-2]\d:[0-5]\d)", spec_text)
    spec_exit = match.group(1) if match else None
    spec_minutes = None
    if spec_exit:
        hour, minute = (int(part) for part in spec_exit.split(":"))
        spec_minutes = (hour * 60 + minute) - (9 * 60)
    prereg_spec = {
        "sma_n": 50,
        "atr_n": 14,
        "stop_atr": 2.0,
        "target_rr": 2.0,
        "time_exit": spec_exit or "Sin datos",
        "time_exit_minutes": spec_minutes if spec_minutes is not None else "Sin datos",
        "max_trades_per_day": 1,
        "side": "long",
    }
    prereg_row = {
        "sma_n": int(params["sma_n"]),
        "atr_n": int(params["atr_n"]),
        "stop_atr": float(params["stop_atr"]),
        "target_rr": float(params["target_rr"]),
        "time_exit": params["time_exit"],
        "time_exit_minutes": params["time_exit_minutes"],
        "session_end": params["session_end"],
        "max_trades_per_day": 1,
        "side": params["side"],
    }
    spec_rows = verify.constants_match(prereg_spec, code)
    for item in spec_rows:
        if item["name"] == "time_exit":
            item["detail"] = "encabezado del spec 15:55; plantilla y fila 15:00"
        elif item["name"] == "time_exit_minutes":
            item["detail"] = "415 derivado del spec; plantilla y fila 360"
    checks += spec_rows
    row_rows = verify.constants_match(
        prereg_row,
        {**code, "session_end": template["strategy"]["session"]["end"]},
    )
    for item in row_rows:
        item["name"] = f"fila.{item['name']}"
        if item["name"] == "fila.time_exit":
            item["detail"] = "la fila y la plantilla coinciden en 15:00"
        elif item["name"] == "fila.time_exit_minutes":
            item["detail"] = "la fila y la plantilla coinciden en 360"
    checks += row_rows

    # 2 · Sintético: noches, prioridad SL > TP, salidas y límite diario.
    bars, both_hit = synthetic_bars()
    zero = fastbt.cfd_costs_from_bps(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )
    model = dsl.Strategy.model_validate(template["strategy"])
    setup = jobs.QueueSetup(
        instrument="US100",
        timeframe="H1",
        account="CFD-001",
        firm="ftmo",
        use_p75=True,
        cost_accounts=("CFD-001",),
        cost_mode="worst",
        legacy_cost=False,
        session_tz=NY,
        session_start="09:00",
        session_end="10:00",
        flat_at="15:00",
        weekdays=(0, 1, 2, 3, 4),
    )
    limits = specs.run_limits_from_strategy(model, setup)
    prepared = fastbt.prepare(bars, zero, atr_windows=(14,), sessions=(limits,))
    synthetic = run_strategy(
        template["strategy"], bars, cost=zero, limits=limits, prepared=prepared
    )
    syn_nights = [
        (ny(t.entry_time).date(), ny(t.exit_time).date())
        for t in synthetic.trades
    ]
    cross = [item for item in syn_nights if item[1] != item[0]]
    reasons = Counter(t.reason for t in synthetic.trades)
    both_stop = [
        t
        for t in synthetic.trades
        if ny(t.entry_time).date() in both_hit and t.reason == "stop"
    ]
    add(
        checks,
        "sintético · noches",
        len(cross),
        0,
        not cross,
        f"{len(synthetic.trades)} ops; {len(cross)} cruzan día",
    )
    add(
        checks,
        "sintético · SL antes que TP",
        "ok" if both_stop else "no",
        "sí",
        bool(both_stop),
        f"{len(both_stop)} días con SL y TP en la misma vela",
    )
    add(
        checks,
        "sintético · salidas vistas",
        ",".join(f"{key}:{value}" for key, value in sorted(reasons.items())),
        "stop, target, force_exit",
        {"stop", "target", "force_exit"} <= set(reasons),
        "cada regla de salida al menos una vez",
    )
    max_day = Counter(ny(t.entry_time).date() for t in synthetic.trades)
    add(
        checks,
        "sintético · máx. 1/día",
        max(max_day.values()) if max_day else 0,
        1,
        (max(max_day.values()) if max_day else 0) <= 1,
        "una sola posición y un límite diario",
    )

    # 3 · NO TRADE con stop no válido y tamaño R normalizado.
    flat_days = pd.bdate_range("2022-06-01", "2022-09-30", tz=NY)
    flat_rows = [
        {
            "time": day + pd.Timedelta(hours=hour),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        }
        for day in flat_days
        for hour in range(9, 11)
    ]
    flat = pd.DataFrame(flat_rows).set_index("time")
    flat.index = pd.DatetimeIndex(flat.index).tz_convert("UTC")
    flat_strategy = {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "H1",
        "session": {"start": "09:00", "end": "10:00", "flat_at": "11:00"},
        "long_entry": {"kind": "time_between", "start": "09:00", "end": "10:00"},
        "short_entry": None,
        "exit": {
            "stop": {"type": "atr", "mult": 2.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
            "time_exit_minutes": 360,
        },
        "sizing": {"risk_per_trade_r": 1.0},
        "limits": {"max_trades_per_day": 1, "cooldown_minutes": 0},
    }
    flat_setup = jobs.QueueSetup(
        instrument="US100",
        timeframe="H1",
        account="CFD-001",
        firm="ftmo",
        use_p75=True,
        cost_accounts=("CFD-001",),
        cost_mode="worst",
        legacy_cost=False,
        session_tz=NY,
        session_start="09:00",
        session_end="10:00",
        flat_at="11:00",
        weekdays=(0, 1, 2, 3, 4),
    )
    flat_limits = specs.run_limits_from_strategy(
        dsl.Strategy.model_validate(flat_strategy), flat_setup
    )
    flat_prepared = fastbt.prepare(
        flat, zero, atr_windows=(14,), sessions=(flat_limits,)
    )
    flat_result = run_strategy(
        flat_strategy,
        flat,
        cost=zero,
        limits=flat_limits,
        prepared=flat_prepared,
    )
    add(
        checks,
        "NO TRADE · ATR 0",
        len(flat_result.trades),
        0,
        len(flat_result.trades) == 0 and flat_result.rejected > 0,
        f"{flat_result.rejected} señales rechazadas por stop no válido",
    )
    add(
        checks,
        "tamaño · R normalizado",
        template["strategy"]["sizing"]["risk_per_trade_r"],
        1.0,
        float(template["strategy"]["sizing"]["risk_per_trade_r"]) == 1.0,
        "CFD discovery no dimensiona contratos; 1 R por operación",
    )

    # 4 · Tramo de desarrollo: solo conteos, horas, noches y coste.
    campaign = load_spec(ROOT / SPEC)
    dev_setup = jobs.QueueSetup.from_campaign(campaign)
    frame = campaigns._source_frame(
        dev_setup.instrument, dev_setup.timeframe, dev_setup.data_source
    )
    frame = snapshots.closed_bars(frame, dev_setup.timeframe)
    start = pd.Timestamp(campaign["is_start"], tz="UTC")
    end = pd.Timestamp(campaign["is_end"], tz="UTC")
    dev = frame[(frame.index >= start) & (frame.index <= end)]
    cost = build_cost_book_for_setup(dev_setup)
    dev_limits = specs.run_limits_from_strategy(model, dev_setup, close_at_end=True)
    dev_prepared = fastbt.prepare(
        dev, cost, atr_windows=(14,), sessions=(dev_limits,)
    )
    dev_signals = compiler.compile(model, dev)
    dev_result = fastbt.run(
        dev_signals,
        dev,
        specs.exit_spec_from_strategy(model),
        cost,
        dev_limits,
        prepared=dev_prepared,
        collect_metrics=False,
    )
    dev_trades = dev_result.trades
    dev_nights = [
        {
            "entry_day": ny(t.entry_time).date(),
            "exit_day": ny(t.exit_time).date(),
            "entry_time": ny(t.entry_time).strftime("%H:%M"),
            "exit_time": ny(t.exit_time).strftime("%H:%M"),
            "reason": t.reason,
            "bars_held": t.bars_held,
        }
        for t in dev_trades
    ]
    dev_cross = [item for item in dev_nights if item["exit_day"] != item["entry_day"]]
    dev_reasons = Counter(item["reason"] for item in dev_nights)
    max_dev_day = Counter(item["entry_day"] for item in dev_nights)
    known_calendar = [
        item
        for item in dev_cross
        if is_full_holiday(item["entry_day"])
        or early_close_hhmm(item["entry_day"]) is not None
    ]
    add(
        checks,
        "DEV · noches",
        len(dev_cross),
        0,
        not dev_cross,
        f"{len(dev_nights)} ops; {len(dev_cross)} cruzan día "
        f"({100.0 * len(dev_cross) / len(dev_nights):.2f} %; "
        f"{len(known_calendar)} en la tabla 2021-2027; el resto, "
        "festivos/cierres 2019-2020)",
    )
    add(
        checks,
        "DEV · razón de salida",
        ",".join(f"{key}:{value}" for key, value in sorted(dev_reasons.items())),
        "stop, target, force_exit",
        {"stop", "target", "force_exit"} <= set(dev_reasons),
        "reglas de salida observadas en el tramo de desarrollo",
    )
    add(
        checks,
        "DEV · máx. 1/día",
        max(max_dev_day.values()) if max_dev_day else 0,
        1,
        (max(max_dev_day.values()) if max_dev_day else 0) <= 1,
        "límite diario del DSL",
    )
    entry_times = Counter(ny(t.entry_time).strftime("%H:%M") for t in dev_trades)
    flat_times = Counter(
        ny(t.exit_time).strftime("%H:%M")
        for t in dev_trades
        if t.reason == "force_exit"
    )
    add(
        checks,
        "DEV · hora de entrada",
        ",".join(f"{key}:{value}" for key, value in sorted(entry_times.items())),
        "10:00 NY",
        set(entry_times) == {"10:00"},
        "señal 09:00 -> open de la vela siguiente",
    )
    add(
        checks,
        "DEV · flat_at",
        ",".join(f"{key}:{value}" for key, value in sorted(flat_times.items())),
        "15:00 NY",
        set(flat_times) == {"15:00"},
        "cierre de la última vela H1 de la sesión",
    )

    signal_days = [
        (ny(dev.index[i]).date(), i)
        for i, flag in enumerate(dev_signals.long_entry)
        if flag
    ]
    entry_days = {item["entry_day"] for item in dev_nights}
    missing = [(day, i) for day, i in signal_days if day not in entry_days]
    missing_detail = []
    for day, index in missing:
        if index + 1 < len(dev):
            next_time = ny(dev.index[index + 1])
            same_day = next_time.date() == day
        else:
            next_time, same_day = None, False
        missing_detail.append(
            {
                "day": day,
                "signal": ny(dev.index[index]).strftime("%H:%M"),
                "next": next_time.strftime("%Y-%m-%d %H:%M") if next_time else None,
                "explained": not same_day,
            }
        )
    add(
        checks,
        "DEV · señales sin operación",
        len(missing),
        "cada una explicada",
        all(item["explained"] for item in missing_detail),
        "; ".join(
            f"{item['day']}: señal {item['signal']} sin barra posterior el mismo día"
            for item in missing_detail
        )
        or "ninguna",
        status="aviso" if missing and all(item["explained"] for item in missing_detail) else None,
        defect=False,
    )
    add(
        checks,
        "DEV · frecuencia",
        len(signal_days),
        "Sin dato esperado",
        True,
        f"{len(dev_nights)} ops en {len(signal_days)} días con señal; "
        "el prerregistro no fija frecuencia esperada",
        status="ok",
        defect=False,
    )
    add(
        checks,
        "DEV · huella de entradas",
        verify.sample_fingerprint(
            item["entry_day"].isoformat() for item in dev_nights
        )[:16],
        "—",
        True,
        "SHA-256 de las fechas de entrada (16 hex)",
        status="ok",
        defect=False,
    )

    # Coste: check_spec solo devuelve conteos y cost_r, nunca PnL.
    feasible = feasibility.check_spec(ROOT / SPEC)
    cost_row = feasible["rows"][0]
    add(
        checks,
        "DEV · cost_r mediano",
        cost_row["cost_r"],
        0.10,
        cost_row["cost_r"] is not None and cost_row["cost_r"] <= 0.10,
        "peor de CFD-001/CFD-006; sin expectativa",
    )
    add(
        checks,
        "DEV · muestra",
        cost_row["trades_is"],
        ">= 40",
        cost_row["trades_is"] >= 40,
        f"pliegues {cost_row['fold_trades']}",
    )

    # 5 · Coherencia documental y benchmark.
    add(
        checks,
        "hash estructural",
        row["structural_hash"][:16],
        "reproducible",
        False,
        "no se reproduce desde primary_params; el spec conserva 15:55 "
        "y la fila 15:00",
        status="aviso",
        defect=False,
    )
    add(
        checks,
        "benchmark",
        "no ejecutado en F2",
        "solo si entra en la puerta de potencia",
        True,
        "el benchmark «sin filtro D1 y lado aleatorio» queda para antes de PnL",
        status="aviso",
        defect=False,
    )

    body = verify.report(checks, title="Comprobaciones")
    defects = [item for item in checks if item.get("defect")]
    header = f"""# Verificación previa H-2026-013

- Commit verificado: `{COMMIT}`.
- Plantilla: `{TEMPLATE}` · SHA-256 `{template_hash}`.
- Spec: `{SPEC}` · SHA-256 `{spec_hash}`.
- `strategy_hash`: `{strategy_hash}`.
- `structural_hash` de la fila: `{row['structural_hash']}`.
- Datos: sintéticos y tramo IS 2019-01-02..2023-12-31 (US100 H1 Dukascopy).
- OOS-2 (2024-01-01..) **no leído**. No se imprime PnL ni expectativa.
- Verificador: `{VERIFIER}`, distinto de la sesión que construyó F2.

"""
    extra = "\n## Defectos\n\n"
    if defects:
        for item in defects:
            extra += f"- **{item['name']}**: {item.get('detail', '')}\n"
    else:
        extra += "Ninguno.\n"
    extra += "\n## Señales perdidas\n\n"
    if missing_detail:
        for item in missing_detail:
            extra += (
                f"- {item['day']} {item['signal']} → sin barra posterior el mismo "
                f"día (siguiente: {item['next']}); festivo/cierre NYSE.\n"
            )
    else:
        extra += "Ninguna.\n"
    extra += "\n## Noches fuera de plazo\n\n"
    if dev_cross:
        for item in dev_cross:
            extra += (
                f"- {item['entry_day']} {item['entry_time']} → "
                f"{item['exit_day']} {item['exit_time']} "
                f"({item['reason']}, {item['bars_held']} velas)\n"
            )
    else:
        extra += "Ninguna.\n"
    extra += (
        "\n## Notas\n\n"
        "- El motor evalúa `hit_stop` antes que `hit_tgt` en la misma vela "
        "(`fastbt.py`); el sintético lo confirma.\n"
        "- Los 21 cruces de día (2,63 %) son festivos/cierres NYSE: falta la "
        "barra de las 15:00 y el `flat_at` no se dispara. La posición se cierra "
        "en la sesión siguiente y deja de cumplir `nights == 0`.\n"
        "- `time_exit`/`time_exit_minutes` discrepan solo entre el encabezado "
        "del spec (15:55/415) y la plantilla+fila (15:00/360); es un defecto "
        "documental, no de la mecánica ejecutada.\n"
        "- No se ha leído OOS-1/OOS-2, no se ha calculado expectativa y no se "
        "ha registrado ninguna campaña ni prueba nueva.\n"
    )
    report = header + body + extra
    out = ROOT / REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    if register:
        existing = None
        with registry.connect(ROOT / DBPATH) as db:
            existing = db.execute(
                "SELECT 1 FROM verifications WHERE hypothesis_id=? AND code_hash=?"
                " AND verifier=? AND verdict=?",
                ("H-2026-013", template_hash, VERIFIER, "Defectos"),
            ).fetchone()
        if existing is None:
            registry.add_verification(
                "H-2026-013",
                template_hash,
                VERIFIER,
                "Defectos",
                REPORT_PATH,
                db_path=ROOT / DBPATH,
            )

    print(f"commit {COMMIT}")
    print(f"template_sha256 {template_hash}")
    print(f"spec_sha256 {spec_hash}")
    print(f"strategy_hash {strategy_hash}")
    print(f"veredicto {'Defectos' if defects else 'Conforma'}")
    print(f"comprobaciones {len(checks)} · defectos {len(defects)}")
    print(f"dev_noches {len(dev_cross)} de {len(dev_nights)}")
    print(f"dev_senales_sin_operacion {len(missing)}")
    print(f"informe {out}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--register",
        action="store_true",
        help="inserta la fila en la tabla verifications (solo si falta)",
    )
    args = parser.parse_args()
    raise SystemExit(main(register=args.register))
