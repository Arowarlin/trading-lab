"""D5 · Plan de seguimiento del EA en el forward (solo conteos)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

from tradinglab import ea_forward
from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_holidays

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(".")
TRADES = ROOT / "TL3_REPORTS" / "ea_trades_v32.parquet"
REPORT = ROOT / "TL3_REPORTS" / "ea_forward_monitor_plan.md"
BOT = "ea:us100-ftmo1"
BACKTEST_R = 0.3104
MDE_Z = 2.49
CHECKPOINTS = (30, 60)


def _nyse_days(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    closures = set(nyse_holidays(start.year, end.year))
    closures.update(NYSE_SPECIAL_CLOSURES)
    return [
        day
        for day in pd.bdate_range(start, end)
        if int(day.strftime("%Y%m%d")) not in closures
    ]


def _date_after(n_more: int, start: pd.Timestamp, rate: float) -> str:
    need = int(math.ceil(n_more / rate))
    days = _nyse_days(start + pd.Timedelta(days=1), start + pd.Timedelta(days=4000))
    return days[need - 1].date().isoformat()


def main() -> None:
    ea = ea_forward._ea_for_bot(BOT)
    closed = ea_forward._closed(ROOT / "data" / "lab.db", ea)
    forward_dates = sorted({str(trade.entry_ts)[:10] for trade in closed})
    forward_n = len(closed)

    frame = pd.read_parquet(TRADES)
    sd = float(frame["r"].std(ddof=1))
    mean = float(frame["r"].mean())
    yearly = frame.groupby("year").size().to_dict()
    first = pd.Timestamp(frame["entry"].min())
    last = pd.Timestamp(frame["entry"].max())
    sessions = _nyse_days(first.normalize(), last.normalize())
    rate = len(frame) / len(sessions)
    today = pd.Timestamp("2026-11-25")

    n_null = int(math.ceil((MDE_Z * sd / BACKTEST_R) ** 2))
    n_010 = int(math.ceil((MDE_Z * sd / (BACKTEST_R - 0.10)) ** 2))
    n_final = max(n_null, n_010)

    checkpoints = sorted({*CHECKPOINTS, n_final})
    dates = {
        n: _date_after(max(0, n - forward_n), today, rate) for n in checkpoints
    }
    date_null = _date_after(max(0, n_null - forward_n), today, rate)

    yearly_text = ", ".join(f"{year}: {count}" for year, count in sorted(yearly.items()))
    dates_text = "\n".join(
        f"| {n} | {dates[n]} |" for n in checkpoints
    )

    lines = [
        "# TL3-D · D5 Plan de seguimiento del EA en el forward",
        "",
        "Solo conteos: no se calcula ningún R, PF ni expectativa del forward. "
        "Nada de este bloque suma al contador.",
        "",
        "## Forward del EA",
        "",
        f"- Operaciones **cerradas**: **{forward_n}**.",
        f"- Fechas de entrada: **{', '.join(forward_dates) if forward_dates else 'Sin datos'}**.",
        "- Fuente: `ea_forward._closed` (sin modificarlo) sobre `data/lab.db`; "
        f"bot `{BOT}`.",
        "",
        "## Referencia del backtest (T6)",
        "",
        f"- Réplica: **{len(frame)} operaciones**, **{mean:+.4f} R** de media, "
        f"sd **{sd:.4f} R**.",
        f"- Frecuencia por año: {yearly_text}.",
        f"- Ventana: {first.date()} a {last.date()}; **{len(sessions)} sesiones NYSE** "
        f"y **{rate:.3f} operaciones por sesión**.",
        "",
        "## Potencia",
        "",
        "| Escenario | n necesario | Fecha estimada |",
        "|---|---:|---|",
        f"| Expectativa real 0, cota superior < +{BACKTEST_R:.4f} R | **{n_null}** | "
        f"{date_null} |",
        f"| Expectativa real 0.10 R, cota superior < +{BACKTEST_R:.4f} R | "
        f"**{n_010}** | {dates[n_final]} |",
        "",
        f"`n = ⌈(2.49 × sd / distancia)²⌉`, con sd = {sd:.4f}. La fecha usa el "
        "ritmo del backtest y el calendario NYSE; es una estimación, no un "
        "compromiso.",
        "",
        "## Regla fijada ahora",
        "",
        f"- El rendimiento del forward se mira **solo** en los puntos de control "
        f"n ∈ {{{', '.join(str(n) for n in checkpoints)}}}. El punto final es "
        f"**N = {n_final}** (el mayor de {n_null} y {n_010}, para cubrir también el "
        "escenario de 0.10 R).",
        "- En cada punto se informan la media de R y su IC95 con **bootstrap "
        "semanal** (semanas ISO remuestreadas con reemplazo, 10.000 réplicas, "
        "semilla 42).",
        "- **Alerta de deriva** si la cota superior del IC95 < +0.10 R.",
        f"- **Compatible con el backtest** si el IC95 contiene +{BACKTEST_R:.4f} R.",
        "- Cualquier otro caso: **indeterminado**.",
        "- Ninguna alerta cambia el EA ni el riesgo: decide el operador.",
        "",
        "Puntos de control y fechas estimadas:",
        "",
        "| n | Fecha estimada |",
        "|---:|---|",
        f"{dates_text}",
        "",
        f"El n = {n_null} (escenario de expectativa 0) queda como hito intermedio "
        "de potencia, pero **no** es un punto de control: no se mira.",
        "",
        "## `drift.py`",
        "",
        "`drift.lane_specs()` incluye el carril `us100-ftmo1` y "
        "`drift.build_lane_drift()` ya compara demo contra el backtest congelado "
        "(operaciones, emparejamiento y slippage) en solo lectura. Es el monitor "
        "operativo existente; **no** implementa estos puntos de control ni el "
        "bootstrap semanal, así que D5 añade solo la regla de potencia y no "
        "duplica el emparejamiento ni el slippage.",
        "",
        "## Límites",
        "",
        "- No se calcula el rendimiento del forward; solo el número y las fechas.",
        "- No se toca el EA, el setfile, `ea_forward.py` ni el forward.",
        "- El plan no suma al contador y no ejecuta ninguna evaluación.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
