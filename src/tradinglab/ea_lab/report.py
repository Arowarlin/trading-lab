"""Informes de la Fase 2 del candidato ``us500-nyopen``."""

from __future__ import annotations

import json
from pathlib import Path

from .candidate import REPORT_DIR


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


def render_data_report(payload: dict) -> str:
    quality = payload["quality"]
    spread = payload["spread"]
    atr = payload["atr"]
    rescale = payload.get("rescale") or {}
    data_ok = payload.get("data_ok")
    lines = [
        "# Datos · EA candidato `us500-nyopen` (Fase 2)",
        "",
        f"Generado: {payload['generated_at']} · solo lectura · **sin backtests**",
        "",
        f"- Ventana pre-registrada: **{payload['window']['start']} → {payload['window']['end']}** "
        f"({payload['window']['tz']})",
        f"- Caché propia: `{payload['cache']}`",
        f"- Origen: `{payload['source']}`",
        f"- Hash del pre-registro: `{payload.get('pre_registration_hash', 'Sin datos')}`",
        f"- Datos válidos para la Fase 3: **{'SÍ' if data_ok else 'NO'}**",
        "",
        "## Calidad de las velas",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Velas totales | {quality['rows']:,} |",
        f"| Velas en la ventana | {quality['window_rows']:,} |",
        f"| Velas RTH | {quality['rth_rows']:,} |",
        f"| Inicio / fin real | {quality['start']} → {quality['end']} |",
        f"| Duplicados | {quality['duplicates']} |",
        f"| Velas OHLC inválidas | {quality['invalid_bars']} |",
        f"| Velas fuera de RTH | {quality['bars_outside_rth']:,} |",
        f"| Días RTH | {quality['rth_days']:,} |",
        f"| Días de trading (sin festivos NYSE) | {quality['trading_days']:,} |",
        f"| Velas RTH faltantes | {quality['missing_rth_bars']:,} "
        f"({_fmt(quality['missing_rth_bars_pct'], 3)} %) |",
        f"| Faltantes en días de trading | {quality['missing_rth_bars_trading_days']:,} "
        f"({_fmt(quality['missing_rth_bars_pct_trading_days'], 3)} %) |",
        f"| Cierres tempranos detectados | {len(quality['early_close_days'])} |",
        f"| Festivos NYSE con datos | {len(quality['holiday_days_with_data'])} |",
        f"| Hueco intradía máximo (sin festivos) | {_fmt(quality['max_intraday_gap_min'], 1)} min |",
        f"| Primera / última hora RTH | {quality['first_rth_time']} / {quality['last_rth_time']} |",
        f"| Punto del símbolo | {_fmt(quality['spec']['point'], 4)} "
        f"(OK: {'sí' if quality['spec']['point_ok'] else 'no'}) |",
        f"| Cobertura de la ventana | {'sí' if quality['coverage_ok'] else 'no'} |",
        f"| Cada año con ≥300 velas RTH | {'sí' if quality['years_min_300_rth'] else 'no'} |",
        "",
        "### Por año",
        "",
        "| Año | Velas | Velas RTH | Días | RTH faltantes |",
        "|---:|---:|---:|---:|---:|",
    ]
    for year, row in sorted(quality["years"].items()):
        lines.append(
            f"| {year} | {row['bars']:,} | {row['rth_bars']:,} | {row['days']:,} | "
            f"{row['missing_rth_bars']:,} |"
        )
    lines += [
        "",
        f"> Cierres tempranos detectados: {len(quality['early_close_days'])} días "
        f"(36 velas RTH menos, cierre a las 13:00). El motor aplica el cierre efectivo "
        f"de `nyse_calendar`; no se rellenan velas.",
        f"> Festivos NYSE con datos: {len(quality['holiday_days_with_data'])} "
        f"(el motor bloquea entradas esos días).",
        "",
        "### Mayores huecos intradía",
        "",
        "| Día | Hueco máx. (min) | Velas |",
        "|---|---:|---:|",
    ]
    for gap in quality["worst_gaps"]:
        lines.append(f"| {gap['day']} | {_fmt(gap['max_gap_min'], 1)} | {gap['bars']} |")
    if not quality["worst_gaps"]:
        lines.append("| — | 0 | — |")
    lines += [
        "",
        "## Coste",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Spread medido (`broker_spreads`) | {_fmt(spread['measured']['median_bps'], 4)} bps |",
        f"| p75 medido | {_fmt(spread['measured']['p75_bps'], 4)} bps |",
        f"| Filas / horas medidas | {spread['measured']['rows']} / "
        f"{len(spread['measured']['hours'])} |",
        f"| Medición desde / hasta | {spread['measured']['from_ts']} → "
        f"{spread['measured']['to_ts']} |",
        f"| Antigüedad | {_fmt(spread['measured']['age_hours'], 1)} h |",
        f"| Spread de barra RTH (mediana) | {_fmt(spread['rth_bar_median_points'], 4)} pts "
        f"({_fmt(spread['rth_bar_median_price'], 4)} precio) |",
        f"| Spread de barra RTH (p75) | {_fmt(spread['rth_bar_p75_points'], 4)} pts |",
        f"| Barras con suelo medido | {spread['floor']['bars_with_measured_floor']:,} / "
        f"{spread['floor']['bars_total']:,} |",
        f"| Mediana tras el suelo | {_fmt(spread['floor']['floored_median_points'], 4)} pts |",
        "",
        "## ATR y reescalado",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| ATR mediano US500 (RTH) | {_fmt(atr['us500_median_atr'], 4)} |",
        f"| ATR mediano US100 (RTH) | {_fmt(atr['us100_median_atr'], 4)} |",
        f"| Ratio US500/US100 | **{_fmt(atr['ratio'], 6)}** |",
        f"| Velas ATR usadas | US500 {atr['us500_bars']:,} · US100 {atr['us100_bars']:,} |",
        "",
        "| Parámetro | Base | Escalado |",
        "|---|---:|---:|",
    ]
    for key in ("sl_buf", "min_sl", "max_spread", "slip"):
        row = rescale.get(key) or {}
        lines.append(
            f"| {key} | {_fmt(row.get('base'), 6)} | {_fmt(row.get('scaled'), 6)} |"
        )
    lines += [
        "",
        "> Fase 2: no se ha ejecutado ningún backtest. El ratio queda congelado para la Fase 3.",
        "",
    ]
    return "\n".join(lines)


def write_data_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir) if out_dir else REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "data.json"
    md_path = target / "data.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    md_path.write_text(render_data_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


VERDICT_TEXT = {
    "PASA": "Cumple todos los criterios pre-registrados, incluido el DSR global ≥ 0,90. "
            "Habilita un forward en demo y, solo si el operador lo decide después, un challenge.",
    "PASA SALVO DSR GLOBAL": "Cumple todos los criterios salvo el DSR global. "
                             "Solo autoriza un forward en demo; nunca un challenge.",
    "NO PASA": "Falla al menos un criterio distinto del DSR global, o el DSR global "
               "está Sin datos. Se archiva sin reintentos.",
}


def _criteria(payload: dict) -> list[dict]:
    filters = payload["filters"]
    thresholds = payload.get("thresholds") or {}
    min_trades = int(thresholds.get("min_trades", 100))
    min_dsr = float(thresholds.get("min_dsr", 0.90))
    max_pbo = float(thresholds.get("max_pbo", 0.30))
    rows = [
        ("Operaciones", filters["trades"], f"≥ {min_trades}", "gate"),
        ("DSR local", filters["dsr_local"], f"≥ {min_dsr:.2f}", "info"),
        ("DSR global", filters["dsr"], f"≥ {min_dsr:.2f}", "gate"),
        ("PBO", filters["pbo"], f"≤ {max_pbo:.2f}", "gate"),
        ("Walk-forward", filters["walk_forward"], "veredicto `ok`", "gate"),
        ("Regímenes 2021–2026", filters["regimen"], "todos > 0", "gate"),
        ("Spread mediano", filters["spread"], "> 0", "gate"),
        ("Coste con +2 puntos", filters["coste_2pts"], "> 0", "gate"),
    ]
    out = []
    for name, item, threshold, kind in rows:
        value = item.get("value")
        ok = bool(item.get("ok"))
        if name == "DSR local":
            status = "INFO" if value is not None else "SIN DATOS"
        elif value is None:
            status = "FALLO (Sin datos)"
        else:
            status = "OK" if ok else "FALLO"
        out.append(
            {
                "criterio": name,
                "valor": value,
                "umbral": threshold,
                "tipo": kind,
                "estado": status,
                "ok": ok,
            }
        )
    return out


def render_validation_report(payload: dict) -> str:
    baseline = payload["baseline"]
    dsr_local = payload.get("dsr_local_meta") or {}
    dsr_global = payload.get("dsr_global_meta") or {}
    wf = payload.get("walk_forward") or {}
    regime = payload.get("regime") or {}
    mc = payload.get("monte_carlo") or {}
    dynamic = payload.get("dynamic_risk") or {}
    costs = payload.get("costs") or {}
    relative = payload.get("relative_cost") or {}
    verdict = payload.get("verdict") or "NO PASA"
    lines = [
        "# Validación · EA candidato `us500-nyopen` (Fase 3)",
        "",
        f"Generado: {payload['generated_at']} · una sola ejecución · sin órdenes",
        "",
        f"- Setfile base: `{payload['setfile']}`",
        f"- Hash del pre-registro: `{payload.get('pre_registration_hash', 'Sin datos')}`",
        f"- Ventana: **{payload['bars']['start']} → {payload['bars']['end']}** "
        f"({payload['bars']['rows']:,} velas)",
        f"- Ratio ATR US500/US100: **{payload.get('ratio')}**",
        f"- Veredicto: **{verdict}**",
        "",
        "## Base",
        "",
        "| Ops | Win % | PF | Expectativa R | Total R | DD máx. R |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {baseline['n']:.0f} | {baseline['win']:.1f} | {baseline['pf']:.2f} | "
        f"{baseline['expR']:+.3f} | {baseline['totR']:+.1f} | {baseline['maxDD_R']:.1f} |",
        "",
        "## Criterios pre-registrados",
        "",
        "| Criterio | Valor | Umbral | Estado |",
        "|---|---:|---:|---:|",
    ]
    for row in _criteria(payload):
        lines.append(
            f"| {row['criterio']} | {_fmt(row['valor'], 4)} | {row['umbral']} | "
            f"{row['estado']} |"
        )
    lines += [
        "",
        "## DSR, PBO y walk-forward",
        "",
        f"- DSR local (N={payload.get('n_trials_local')}): "
        f"{_fmt(payload.get('dsr_local'), 6)} · {dsr_local.get('metric_version', '')}",
        f"- DSR global (N={payload.get('n_trials')}): "
        f"{_fmt(payload.get('dsr_global'), 6)} · "
        f"{dsr_global.get('n_series')} series · {dsr_global.get('frequency')}",
        f"- PBO: {_fmt(payload.get('pbo'), 4)}",
        f"- Walk-forward: {wf.get('verdict')} · Sharpe OOS "
        f"{_fmt(wf.get('stitched_sharpe'), 3)} · eficiencia {_fmt(wf.get('efficiency'), 3)} · "
        f"folds {wf.get('n_folds')}",
        "",
        "## Regímenes por año",
        "",
        "| Año | Retorno | Sharpe | DD máx. |",
        "|---:|---:|---:|---:|",
    ]
    for year, row in sorted((regime.get("years") or {}).items()):
        lines.append(
            f"| {year} | {_fmt(row.get('total_return'), 4)} | "
            f"{_fmt(row.get('sharpe'), 3)} | {_fmt(row.get('max_drawdown'), 4)} |"
        )
    if not regime.get("years"):
        lines.append("| — | Sin datos | Sin datos | Sin datos |")
    lines += [
        "",
        "## Monte Carlo FTMO (21 días)",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| P(pasar +10 %) | {_fmt(mc.get('pass_rate'), 4)} |",
        f"| P(tocar −5 %) | {_fmt(mc.get('breach_rate'), 4)} |",
        f"| P(timeout) | {_fmt(mc.get('timeout_rate'), 4)} |",
        f"| Días medianos para pasar | {_fmt(mc.get('median_days_to_pass'), 1)} |",
        f"| DD mediano | {_fmt(mc.get('median_max_drawdown'), 4)} |",
        f"| Peor DD | {_fmt(mc.get('worst_max_drawdown'), 4)} |",
        "",
        "## Riesgo dinámico v3",
        "",
        f"- Retorno simulado: {_fmt(dynamic.get('return'), 4)}",
        f"- Equity final: {_fmt(dynamic.get('equity'), 2)}",
        f"- DD máximo: {_fmt(dynamic.get('max_drawdown'), 4)}",
        f"- Kill switch 8 %: {'sí' if dynamic.get('killed') else 'no'}",
        "",
        "## Sensibilidad a costes",
        "",
        "| Slippage (puntos) | Expectativa R | PF | Total R |",
        "|---:|---:|---:|---:|",
    ]
    for slip, row in sorted(costs.items(), key=lambda item: float(item[0])):
        lines.append(
            f"| {slip} | {_fmt(row.get('expR'), 4)} | {_fmt(row.get('pf'), 3)} | "
            f"{_fmt(row.get('totR'), 2)} |"
        )
    lines += [
        "",
        "## Coste relativo (spread medido / ATR)",
        "",
        "| Símbolo | Spread medido | Cierre | ATR | Spread / ATR |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in (("US500", relative.get("us500") or {}), ("US100", relative.get("us100") or {})):
        lines.append(
            f"| {name} | {_fmt(row.get('measured_bps'), 4)} bps | "
            f"{_fmt(row.get('last_close'), 2)} | {_fmt(row.get('atr_median'), 4)} | "
            f"{_fmt(row.get('spread_over_atr'), 4)} |"
        )
    lines += [
        "",
        "> Coste relativo = (spread medido en bps × cierre / 10.000) / ATR mediano. "
        "La referencia del pre-registro era ≈ 0,099 en US500 frente a ≈ 0,078 en US100. "
        "Con el spread medido y el cierre del 2026-11-13 sale 0,1209 en US500 y 0,0803 en US100: "
        "el S&P 500 es relativamente más caro y el veredicto no cambia.",
        "",
        "## Las 8 variantes",
        "",
        "| # | score | RR | gap | consec | Ops | Exp. R | PF | Total R | DD R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("rows", []):
        lines.append(
            f"| {row['index']} | {row['min_score']} | {row['rr']} | {row['gap_min']} | "
            f"{row['max_consec']} | {row['n']:.0f} | {row['expR']:+.3f} | "
            f"{row['pf']:.2f} | {row['totR']:+.1f} | {row['maxDD_R']:.1f} |"
        )
    lines += [
        "",
        "> La base es la variante 6 del setfile. Las variantes 0–4 tienen total positivo, "
        "pero se miraron después del barrido: elegirlas sería una selección post-hoc y el "
        "pre-registro lo prohíbe. El veredicto se calcula solo sobre la base.",
        "",
        f"> Veredicto: **{verdict}** — {VERDICT_TEXT[verdict]}",
        "",
        "> Una sola ejecución. No se reintenta con otros parámetros.",
        "",
    ]
    return "\n".join(lines)


def render_verdict(payload: dict) -> str:
    verdict = payload.get("verdict") or "NO PASA"
    relative = payload.get("relative_cost") or {}
    lines = [
        "# Veredicto · `us500-nyopen` (Fase 4)",
        "",
        f"**{verdict}**",
        "",
        VERDICT_TEXT[verdict],
        "",
        "## Tabla frente al pre-registro",
        "",
        "| Criterio | Valor | Umbral | Estado |",
        "|---|---:|---:|---:|",
    ]
    for row in _criteria(payload):
        lines.append(
            f"| {row['criterio']} | {_fmt(row['valor'], 4)} | {row['umbral']} | "
            f"{row['estado']} |"
        )
    lines += [
        "",
        "## Lectura de la rejilla",
        "",
        "La base del setfile (variante 6) es la que decide: 401 operaciones, PF 0,99 y "
        "**−3,6R**. Las variantes 0–4 tienen total positivo, pero se miraron después del "
        "barrido; elegirlas sería una selección post-hoc y el pre-registro lo prohíbe.",
        "",
        "## Coste relativo",
        "",
        f"- US500: spread/ATR = **{_fmt((relative.get('us500') or {}).get('spread_over_atr'), 4)}**",
        f"- US100: spread/ATR = **{_fmt((relative.get('us100') or {}).get('spread_over_atr'), 4)}**",
        "",
        "La referencia del pre-registro era ~0,099 en US500 frente a ~0,078 en US100. "
        "Con el spread medido y el cierre del 2026-11-13 sale 0,1209 frente a 0,0803: "
        "el coste relativo del S&P 500 es aún mayor. La desventaja ya está dentro del "
        "resultado y el veredicto no cambia.",
        "",
        "## Decisión",
        "",
    ]
    if verdict == "PASA":
        lines.append("Autoriza forward en demo y, solo con decisión explícita posterior, challenge.")
    elif verdict == "PASA SALVO DSR GLOBAL":
        lines.append("Solo autoriza forward en demo. No autoriza challenge.")
    else:
        lines.append("Se archiva. No se reintenta ni se prueban otras variantes.")
    lines += [
        "",
        f"Hash del pre-registro: `{payload.get('pre_registration_hash', 'Sin datos')}`",
        "",
    ]
    return "\n".join(lines)


def write_validation_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir) if out_dir else REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "validation.json"
    md_path = target / "validation.md"
    verdict_path = target / "verdict.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    md_path.write_text(render_validation_report(payload), encoding="utf-8")
    verdict_path.write_text(render_verdict(payload), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "verdict": str(verdict_path),
    }


def render_session_data_report(payload: dict) -> str:
    quality = payload["quality"]
    spread = payload["spread"]
    session = spread["session"]
    ny = spread["ny"]
    comparison = spread["comparison"]
    coverage = spread["coverage"]
    lines = [
        f"# Datos · `{payload['candidate']}` (Fase 2)",
        "",
        f"Generado: {payload['generated_at']} · solo lectura · **sin backtests**",
        "",
        f"- Ventana: **{payload['window']['start']} → {payload['window']['end']}** "
        f"({payload['window']['tz']})",
        f"- Caché propia: `{payload['cache']}`",
        f"- Origen: `{payload['source']}`",
        f"- Datos válidos para la Fase 3: **{'SÍ' if payload['data_ok'] else 'NO'}**",
        "",
        "## Calidad de las velas",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Velas totales | {quality['rows']:,} |",
        f"| Velas en la ventana | {quality['window_rows']:,} |",
        f"| Velas RTH (NY) | {quality['rth_rows']:,} |",
        f"| Inicio / fin real | {quality['start']} → {quality['end']} |",
        f"| Duplicados | {quality['duplicates']} |",
        f"| Velas OHLC inválidas | {quality['invalid_bars']} |",
        f"| Días RTH | {quality['rth_days']:,} |",
        f"| Faltantes en días de trading | {quality['missing_rth_bars_trading_days']:,} "
        f"({_fmt(quality['missing_rth_bars_pct_trading_days'], 3)} %) |",
        f"| Cierres tempranos detectados | {len(quality['early_close_days'])} |",
        f"| Festivos NYSE con datos | {len(quality['holiday_days_with_data'])} |",
        f"| Hueco intradía máximo (sin festivos) | {_fmt(quality['max_intraday_gap_min'], 1)} min |",
        f"| Primera / última hora RTH | {quality['first_rth_time']} / {quality['last_rth_time']} |",
        f"| Punto del símbolo | {_fmt(quality['spec']['point'], 4)} "
        f"(OK: {'sí' if quality['spec']['point_ok'] else 'no'}) |",
        f"| Cobertura de la ventana | {'sí' if quality['coverage_ok'] else 'no'} |",
        f"| Cada año con ≥300 velas RTH | {'sí' if quality['years_min_300_rth'] else 'no'} |",
        "",
        "### Por año",
        "",
        "| Año | Velas | Velas RTH | Días | RTH faltantes |",
        "|---:|---:|---:|---:|---:|",
    ]
    for year, row in sorted(quality["years"].items()):
        lines.append(
            f"| {year} | {row['bars']:,} | {row['rth_bars']:,} | {row['days']:,} | "
            f"{row['missing_rth_bars']:,} |"
        )
    lines += [
        "",
        "## Spread en la ventana de entradas",
        "",
        "| Sesión | Ventana | Zona | Velas | Días | Mediana pts | p75 pts | Mediana bruta pts |",
        "|---|---|---|---:|---:|---:|---:|---:|",
        f"| {session['label']} | {session['window']} | {session['tz']} | "
        f"{session['bars']:,} | {session['days']:,} | {_fmt(session['median_points'], 4)} | "
        f"{_fmt(session['p75_points'], 4)} | {_fmt(session['raw_median_points'], 4)} |",
        f"| Nueva York | {ny['window']} | {ny['tz']} | {ny['bars']:,} | {ny['days']:,} | "
        f"{_fmt(ny['median_points'], 4)} | {_fmt(ny['p75_points'], 4)} | "
        f"{_fmt(ny['raw_median_points'], 4)} |",
        "",
        f"- Ratio {session['label']} / NY: **{_fmt(comparison['ratio_vs_ny'], 4)}** "
        f"({_fmt(comparison['difference_points'], 4)} pts de diferencia).",
        f"- Medición `broker_spreads` US100.CASH: {_fmt(spread['measured']['median_bps'], 4)} bps, "
        f"{spread['measured']['rows']} horas, antigüedad {_fmt(spread['measured']['age_hours'], 2)} h.",
        f"- Cobertura de la ventana: {coverage['days_with_data']:,} días con datos de "
        f"{coverage['weekdays_in_window']:,} días hábiles ({_fmt(coverage['coverage_pct'], 2)} %).",
        "",
        "## Viabilidad de costes previa (no es un backtest)",
        "",
        "| Sesión | Ventana | ATR Wilder 14 | Spread medio | Spread / ATR | Cociente vs NY |",
        "|---|---|---:|---:|---:|---:|",
        f"| {session['label']} | {session['window']} | "
        f"{_fmt(payload['viability']['session']['median_atr'], 4)} | "
        f"{_fmt(payload['viability']['session']['spread_price'], 4)} | "
        f"**{_fmt(payload['viability']['session']['spread_over_atr'], 6)}** | "
        f"**{_fmt(payload['viability']['ratio_vs_ny'], 4)}** |",
        f"| Nueva York | {ny['window']} | "
        f"{_fmt(payload['viability']['ny']['median_atr'], 4)} | "
        f"{_fmt(payload['viability']['ny']['spread_price'], 4)} | "
        f"**{_fmt(payload['viability']['ny']['spread_over_atr'], 6)}** | 1,0000 |",
        "",
        "> No es un backtest: no se ejecutó el motor, no se miraron retornos y no se "
        "registraron trials. Solo mide ATR y spread en la ventana de entradas.",
        "",
        "### Spread por hora local",
        "",
        "| Hora local | Velas | Mediana pts | p75 pts |",
        "|---:|---:|---:|---:|",
    ]
    for row in session["hourly"]:
        lines.append(
            f"| {row['hour_local']:02d}:00 | {row['bars']:,} | "
            f"{_fmt(row['median_points'], 4)} | {_fmt(row['p75_points'], 4)} |"
        )
    lines += [
        "",
        "> Fase 2: no se ha ejecutado ningún backtest de Londres ni de Asia. "
        "El spread usa el suelo horario de `broker_spreads`; la ventana NY "
        "09:35–11:30 es la referencia.",
        "",
    ]
    return "\n".join(lines)


def write_session_data_report(payload: dict, out_dir: str | Path | None = None) -> dict:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "data.json"
    md_path = target / "data.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    md_path.write_text(render_session_data_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "render_data_report",
    "render_session_data_report",
    "render_validation_report",
    "render_verdict",
    "write_data_report",
    "write_session_data_report",
    "write_validation_report",
]
