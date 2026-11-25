"""Calendario histórico de publicaciones macro (fechas de primera publicación).

Uso: .venv\\Scripts\\python.exe NASDAQ_EDGE_INSTITUTIONAL/tools/build_news_calendar.py

Método: ALFRED `series/observations` con `output_type=4` (solo publicación
inicial). La `realtime_start` de cada observación es el día en que ese dato se
publicó por primera vez. Así se descartan las fechas de revisión estacional o
benchmark que `release/dates` mezcla.

FOMC: fechas del archivo `02_DATA/fomc_dates.csv` (leídas de federalreserve.gov).
Solo fecha; la hora histórica del comunicado cambió (12:30 / 14:00 ET).

Escribe 02_DATA/news_calendar_history.csv.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from tradinglab.intel.fred import FredCalendarProvider

DATA = Path(__file__).resolve().parents[1] / "02_DATA"
OUT = DATA / "news_calendar_history.csv"

# serie FRED -> (evento, tier interno, hora ET de la agencia)
SERIES = {
    "CPIAUCSL": ("CPI", 1, "08:30"),
    "PAYEMS": ("NFP", 1, "08:30"),
    "PPIFIS": ("PPI", 1, "08:30"),  # PPI final demand (desde 2014)
    "PPIFGS": ("PPI", 1, "08:30"),  # PPI finished goods (histórico)
    "PCE": ("PCE", 2, "08:30"),
    "GDP": ("GDP", 2, "08:30"),  # publicación inicial = estimación avance
    "RSAFS": ("RetailSales", 2, "08:30"),
    "JTSJOL": ("JOLTS", 2, "10:00"),
}
START, END = date(2010, 1, 1), date(2026, 11, 25)


def first_release_dates(provider: FredCalendarProvider, series_id: str) -> set[str]:
    payload = provider._get(
        "series/observations",
        {
            "series_id": series_id,
            "realtime_start": "2009-06-01",
            "realtime_end": "9999-12-31",
            "observation_start": "2009-01-01",
            "output_type": 4,
            "limit": 100000,
        },
    )
    out = set()
    for obs in payload.get("observations") or []:
        day = str(obs.get("realtime_start") or "")
        if START.isoformat() <= day <= END.isoformat():
            out.add(day)
    return out


def main() -> None:
    provider = FredCalendarProvider("data/lab.db", cache_dir="data/cache/fred")
    rows: dict[tuple[str, str], dict] = {}
    try:
        for series_id, (event, tier, hhmm) in SERIES.items():
            for day in first_release_dates(provider, series_id):
                rows[(day, event)] = {
                    "date": day,
                    "event": event,
                    "tier": tier,
                    "time_et": hhmm,
                    "source": f"alfred:{series_id}:output_type=4",
                }
    finally:
        provider.close()
    fomc = DATA / "fomc_dates.csv"
    if fomc.exists():
        with fomc.open(encoding="utf-8") as fh:
            for rec in csv.DictReader(fh):
                rows[(rec["date"], "FOMC")] = {
                    "date": rec["date"],
                    "event": "FOMC",
                    "tier": 1,
                    "time_et": "",
                    "source": rec["source"],
                }
    ordered = sorted(rows.values(), key=lambda r: (r["date"], r["event"]))
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["date", "event", "tier", "time_et", "source"])
        writer.writeheader()
        writer.writerows(ordered)
    print(f"{len(ordered)} filas -> {OUT}")


if __name__ == "__main__":
    main()
