"""D3 · Cobertura de sesiones (solo conteos, sin precios)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_holidays
from tradinglab.tl3.data import session_coverage

ROOT = Path(".")
OUT = ROOT / "TL3_REPORTS" / "data_coverage.md"
JSON = ROOT / "data" / "tl3" / "coverage.json"
MANIFEST_REPORT = ROOT / "TL3_REPORTS" / "data_manifest.md"
MANIFEST_LINE = (
    "- Cobertura de datos: [data_coverage.md](data_coverage.md) "
    "(D3, solo conteos de velas)."
)
SESSION_MIN = 357
NIGHT_MIN = 744


def _nyse_days(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    if start > end:
        return []
    closures = set(nyse_holidays(start.year, end.year))
    closures.update(NYSE_SPECIAL_CLOSURES)
    days = pd.bdate_range(start, end)
    return [
        day
        for day in days
        if int(day.strftime("%Y%m%d")) not in closures
    ]


def _load_index(path: Path) -> pd.DatetimeIndex:
    frame = pd.read_parquet(path, columns=[])
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    if not index.is_monotonic_increasing:
        index = index.sort_values()
    return index


def _timeframe(path: Path) -> str:
    stem = path.stem.upper()
    for key in ("M1", "H1"):
        if stem.endswith(key) or f"_{key}" in stem:
            return key
    return ""


def _intraday_gap(index: pd.DatetimeIndex, day: pd.Timestamp) -> float | None:
    start = day + pd.Timedelta(hours=9, minutes=30)
    end = day + pd.Timedelta(hours=15, minutes=44)
    left = int(index.searchsorted(start, side="left"))
    right = int(index.searchsorted(end, side="right"))
    stamps = index[left:right]
    if len(stamps) < 2:
        return 0.0 if len(stamps) == 1 else None
    return float(np.diff(stamps.asi8).max() / 60_000_000_000)


def _file_rows(path: Path, label: str) -> list[dict]:
    index = _load_index(path)
    if len(index) == 0:
        return []
    timeframe = _timeframe(path)
    first = index[0].normalize()
    last = index[-1].normalize()
    day_values = pd.DatetimeIndex(index.normalize()).unique()
    day_set = set(day_values)
    rows = []

    for year in range(first.year, last.year + 1):
        year_start = max(first, pd.Timestamp(year=year, month=1, day=1))
        year_end = min(last, pd.Timestamp(year=year, month=12, day=31))
        days = _nyse_days(year_start, year_end)
        if not days:
            continue

        no_bars = sum(1 for day in days if day not in day_set)
        gaps = [
            gap
            for day in days
            if (gap := _intraday_gap(index, day)) is not None
        ]
        row = {
            "file": path.name,
            "copy": label,
            "symbol": path.stem.split("_")[0],
            "timeframe": timeframe,
            "year": year,
            "sessions": len(days),
            "no_bars_days": int(no_bars),
            "max_gap_min": max(gaps) if gaps else None,
        }

        if timeframe == "M1":
            coverage = [session_coverage(index, day) for day in days]
            night = [item["night_bars"] for item in coverage]
            row.update(
                {
                    "session_95": int(
                        sum(1 for item in coverage if item["session_bars"] >= SESSION_MIN)
                    ),
                    "night_median": float(np.median(night)) if night else None,
                    "night80_pct": float(
                        100.0 * sum(1 for value in night if value >= NIGHT_MIN) / len(night)
                    )
                    if night
                    else None,
                    "t7_valid": int(sum(1 for item in coverage if item["valid"])),
                }
            )
        else:
            row.update(
                {
                    "session_95": None,
                    "night_median": None,
                    "night80_pct": None,
                    "t7_valid": None,
                }
            )
        rows.append(row)
    return rows


def _format(value, digits: int = 0) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def main() -> None:
    rows: list[dict] = []
    for path in sorted((ROOT / "data" / "cache" / "dukascopy").glob("*_M1.parquet")):
        rows.extend(_file_rows(path, "dukascopy"))
    for path in sorted((ROOT / "data" / "tl3" / "futures").glob("*.parquet")):
        rows.extend(_file_rows(path, "futures"))

    JSON.parent.mkdir(parents=True, exist_ok=True)
    JSON.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# TL3-D · Cobertura de datos (conteos)",
        "",
        "Regla T7: ≥357 velas M1 en 09:30-15:44 de la sesión y de la anterior; "
        "≥744 de 18:00 a 09:29.",
        "Las copias H1 de `data/tl3/futures/` no admiten la regla M1 y se marcan "
        "**Sin datos** en esas columnas.",
        "",
        "| Copia | Archivo | Año | Sesiones NYSE | Días sin velas | ≥95 % sesión | "
        "Mediana nocturna | ≥80 % nocturno | Válidas T7 | Hueco máx (min) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['copy']} | {row['file']} | {row['year']} | {row['sessions']} | "
            f"{row['no_bars_days']} | {_format(row['session_95'])} | "
            f"{_format(row['night_median'])} | "
            f"{_format(row['night80_pct'], 1) if row['night80_pct'] is not None else 'Sin datos'} | "
            f"{_format(row['t7_valid'])} | {_format(row['max_gap_min'], 1)} |"
        )

    us100_index = _load_index(ROOT / "data" / "cache" / "dukascopy" / "US100_M1.parquet")
    us100_window = _nyse_days(
        pd.Timestamp("2012-01-01"), pd.Timestamp("2021-08-31")
    )
    window_valid = [
        day for day in us100_window if session_coverage(us100_index, day)["valid"]
    ]
    total_valid = len(window_valid)
    zeros = sorted({day.year for day in us100_window} - {day.year for day in window_valid})
    zero_text = ", ".join(str(year) for year in zeros) if zeros else "ninguno"
    reference = 1128
    lines += [
        "",
        "## Comprobación cruzada · US100 2012-2021",
        "",
        f"- Ventana de T7 (hasta 2021-08-31): sesiones válidas con la regla "
        f"prerregistrada: **{total_valid}**.",
        f"- Referencia de la revisión de Claude: ~**{reference}**; diferencia: "
        f"**{total_valid - reference:+d}**. C2 contó 1127.",
        f"- Años con 0 sesiones válidas: **{zero_text}**.",
        "- La diferencia con C2 procede de la sesión anterior: esta función exige la "
        "sesión NYSE anterior completa y no sustituye una sesión ausente por la última "
        "disponible. No se ajusta la función para forzar la referencia.",
        "",
        "## Lectura",
        "",
        "La cobertura efectiva depende de la fuente: Dukascopy US100 no tiene velas "
        "nocturnas suficientes antes de 2018, y las copias H1 solo permiten contar "
        "sesiones y huecos.",
        "En la tabla, «Sesiones NYSE» cuenta todos los días de bolsa del rango del "
        "fichero (incluidos los días sin velas); C2 contaba solo los días con velas.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")

    manifest = MANIFEST_REPORT.read_text(encoding="utf-8")
    kept = [
        line for line in manifest.splitlines() if "data_coverage.md" not in line
    ]
    kept.append(MANIFEST_LINE)
    MANIFEST_REPORT.write_text("\n".join(kept) + "\n", encoding="utf-8")

    print(f"rows {len(rows)} · json {JSON} · report {OUT}")
    print(f"US100 2012-2021 valid {total_valid} (ref {reference}, diff {total_valid - reference:+d})")
    print(f"zeros: {zero_text}")


if __name__ == "__main__":
    main()
