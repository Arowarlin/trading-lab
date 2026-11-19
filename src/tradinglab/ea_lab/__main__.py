"""Comandos del laboratorio de EAs: ``python -m tradinglab.ea_lab``.

Fase 2: ``data``. La validación (Fase 3) no se implementa hasta que el operador
escriba ``APRUEBO VALIDACION US500``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .atr import atr_ratio
from .candidate import (
    REPORT_DIR,
    SETFILE,
    WINDOW_END,
    WINDOW_START,
    load_base_setfile,
    point_values,
    pre_registration_hash,
)
from .data import (
    apply_spread_floor,
    build_data_report,
    load_m5_us500,
    load_us100_cache,
    measured_spread,
)
from .report import write_data_report
from .validation import (
    APPROVAL_PHRASE,
    AlreadyValidated,
    ApprovalRequired,
    data_context,
    validate_candidate,
)


def _data_ok(payload: dict) -> bool:
    quality = payload["quality"]
    return all(
        [
            quality["duplicates"] == 0,
            quality["invalid_bars"] == 0,
            quality["spec"]["point_ok"],
            quality["coverage_ok"],
            quality["years_min_300_rth"],
            str(quality["first_rth_time"]).startswith("09:30"),
            str(quality["last_rth_time"]).startswith("15:55"),
            float(payload["atr"]["ratio"]) > 0,
        ]
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_command(approval: str) -> int:
    if approval.strip() != APPROVAL_PHRASE:
        raise ApprovalRequired(f"Se requiere la frase exacta: {APPROVAL_PHRASE}")
    report_path = REPORT_DIR / "data.json"
    if not report_path.exists():
        print(
            "Sin datos: ejecuta antes `python -m tradinglab.ea_lab data`.",
            file=sys.stderr,
        )
        return 2
    data_report = json.loads(report_path.read_text(encoding="utf-8"))
    if not data_report.get("data_ok"):
        print("Sin datos: la Fase 2 no aprobó los datos.", file=sys.stderr)
        return 2
    if data_report.get("pre_registration_hash") != pre_registration_hash():
        print(
            "Sin datos: el hash del pre-registro no coincide con la Fase 2.",
            file=sys.stderr,
        )
        return 2
    bundle = load_m5_us500()
    measured = measured_spread()
    us100 = load_us100_cache()
    prepared, _ = apply_spread_floor(bundle.frame, measured)
    window = prepared.loc[WINDOW_START:WINDOW_END]
    ratio = float(data_report["atr"]["ratio"])
    context = data_context(data_report, bundle.frame, us100)
    payload = validate_candidate(
        window,
        ratio=ratio,
        data={
            "cache_sha256": _sha256(bundle.cache_path),
            "ratio": ratio,
            **context,
        },
        record=True,
        single_shot=True,
    )
    print(
        f"Veredicto: {payload['verdict']} | DSR local {payload.get('dsr_local')} | "
        f"DSR global {payload.get('dsr_global')} | PBO {payload.get('pbo')} | "
        f"WF {payload.get('walk_forward', {}).get('verdict')}"
    )
    print(
        f"Base: {payload['baseline']['n']:.0f} ops · PF {payload['baseline']['pf']:.2f} · "
        f"Exp {payload['baseline']['expR']:+.3f}R · Total {payload['baseline']['totR']:+.1f}R"
    )
    print(f"Informe: {payload['files']['markdown']}")
    print(f"Veredicto: {payload['files']['verdict']}")
    return 0


def data_command(refresh: bool = False, as_json: bool = False) -> int:
    bundle = load_m5_us500(refresh=refresh)
    us100 = load_us100_cache()
    measured = measured_spread()
    ratio = atr_ratio(bundle.frame, us100)
    values = load_base_setfile(SETFILE)
    payload = build_data_report(bundle, us100, measured, ratio)
    payload["pre_registration_hash"] = pre_registration_hash()
    payload["rescale"] = point_values(values, ratio["ratio"])
    payload["data_ok"] = _data_ok(payload)
    files = write_data_report(payload)
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        quality = payload["quality"]
        print(f"US500.cash M5 | {quality['rows']:,} velas | {quality['start']} -> {quality['end']}")
        print(
            f"Ventana {payload['window']['start']} -> {payload['window']['end']} | "
            f"RTH {quality['rth_rows']:,} velas | duplicados {quality['duplicates']} | "
            f"invalidas {quality['invalid_bars']} | faltantes en dias de trading "
            f"{quality['missing_rth_bars_trading_days']:,} "
            f"({quality['missing_rth_bars_pct_trading_days']} %) | "
            f"cierres tempranos {len(quality['early_close_days'])} | "
            f"festivos con datos {len(quality['holiday_days_with_data'])}"
        )
        print(
            f"Punto {quality['spec']['point']} (OK={quality['spec']['point_ok']}) | "
            f"cobertura {'OK' if quality['coverage_ok'] else 'NO'} | "
            f"anos >=300 RTH {'OK' if quality['years_min_300_rth'] else 'NO'} | "
            f"horas RTH {quality['first_rth_time']} / {quality['last_rth_time']}"
        )
        print(
            f"Spread medido {payload['spread']['measured']['median_bps']:.4f} bps | "
            f"barras RTH {payload['spread']['rth_bar_median_points']:.4f} pts"
        )
        print(
            f"ATR mediano US500 {ratio['us500_median_atr']:.4f} | "
            f"US100 {ratio['us100_median_atr']:.4f} | ratio {ratio['ratio']:.8f}"
        )
        for key, row in payload["rescale"].items():
            if key == "ratio":
                continue
            print(f"  {key}: {row['base']} -> {row['scaled']}")
        print(f"Hash pre-registro: {payload['pre_registration_hash']}")
        print(f"Datos validos para Fase 3: {'SI' if payload['data_ok'] else 'NO'}")
        print(f"JSON: {files['json']} | MD: {files['markdown']}")
    return 0 if payload["data_ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tradinglab.ea_lab")
    sub = parser.add_subparsers(dest="command", required=True)
    data = sub.add_parser("data", help="Descarga/valida M5 US500 y calcula el ratio ATR")
    data.add_argument("--refresh", action="store_true", help="Vuelve a leer M5 del terminal")
    data.add_argument("--json", action="store_true", help="Imprime el informe completo")
    validate = sub.add_parser("validate", help="Fase 3: validación de un solo disparo")
    validate.add_argument(
        "--approval",
        required=True,
        help=f"Frase exacta del operador: {APPROVAL_PHRASE}",
    )
    args = parser.parse_args(argv)
    if args.command == "validate":
        try:
            return validate_command(args.approval)
        except (ApprovalRequired, AlreadyValidated) as exc:
            print(f"Sin datos: {exc}", file=sys.stderr)
            return 2
    return data_command(refresh=args.refresh, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
