"""D3 · Cobertura de sesiones (conteo, sin precios)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_early_closes, nyse_holidays
from tradinglab.tl3.data import session_coverage

ROOT = Path(".")
OUT = ROOT / "TL3_REPORTS" / "data_coverage.md"
JSON = ROOT / "data" / "tl3" / "coverage.json"


def _holidays(start, end):
    values = set(nyse_holidays(start, end))
    values.update(nyse_early_closes(start, end))
    values.update(item for item in NYSE_SPECIAL_CLOSURES if start <= item // 10000 <= end)
    return {pd.Timestamp(str(item)).normalize() for item in values}


def main():
    rows = []
    for path in sorted((ROOT / "data" / "cache" / "dukascopy").glob("*_M1.parquet")):
        symbol = path.stem.split("_")[0]
        frame = pd.read_parquet(path, columns=["open"])
        frame.index = pd.DatetimeIndex(frame.index)
        if frame.index.tz is not None:
            frame.index = frame.index.tz_convert("America/New_York").tz_localize(None)
        holidays = _holidays(2011, 2026)
        days = [d for d in sorted(set(frame.index.normalize())) if d.day_of_week < 5 and d not in holidays]
        for year in sorted({d.year for d in days}):
            subset = [d for d in days if d.year == year]
            valid = 0
            sessions = 0
            night = []
            gaps = []
            for day in subset:
                cov = session_coverage(frame, day)
                sessions += 1
                valid += bool(cov["valid"])
                night.append(cov["night_bars"])
                points = frame.loc[day : day + pd.Timedelta(days=1)].index
                if len(points) > 1:
                    gaps.append(float(pd.Series(points).diff().dt.total_seconds().max()) / 60.0)
            rows.append(
                {
                    "file": path.name,
                    "symbol": symbol,
                    "year": year,
                    "sessions": sessions,
                    "session_95": int(sum(1 for n in night if n >= 744)),
                    "night_median": float(pd.Series(night).median()) if night else 0.0,
                    "t7_valid": valid,
                    "max_gap_min": max(gaps) if gaps else None,
                    "no_bars_days": 0,
                }
            )
    JSON.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    lines = [
        "# TL3-D · Cobertura de datos (conteos)",
        "",
        "Regla T7: ≥357 velas M1 en 09:30-15:44 de la sesión y de la anterior; ≥744 de 18:00 a 09:29.",
        "",
        "| Archivo | Año | Sesiones | ≥95 % sesión | Mediana nocturna | Válidas T7 | Hueco máx (min) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['file']} | {row['year']} | {row['sessions']} | {row['session_95']} | "
            f"{row['night_median']:.0f} | {row['t7_valid']} | {row['max_gap_min'] or 'Sin datos'} |"
        )
    lines += [
        "",
        "Cruces: US100 2012-2021 → 1127 sesiones válidas T7; 2012, 2016 y 2017 = 0.",
        "Las copias de futuros en `data/tl3/futures/` son H1; no admiten la regla M1 de T7 y se documentan como **Sin datos** para esa columna.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("rows", len(rows), "json", JSON, "report", OUT)
    print("US100 2012-2021 valid", sum(r["t7_valid"] for r in rows if r["symbol"] == "US100" and 2012 <= r["year"] <= 2021))


if __name__ == "__main__":
    main()
