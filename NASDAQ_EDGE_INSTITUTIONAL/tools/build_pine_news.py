r"""Genera el bloque de calendario de noticias del indicador Pine.

Uso: .venv\Scripts\python.exe -I NASDAQ_EDGE_INSTITUTIONAL/tools/build_pine_news.py [--valid-until 2027-11-30]

Lee 02_DATA/future_events.csv (fechas oficiales BLS/BEA/Census/Fed verificadas)
y reescribe el bloque entre los marcadores `// <NEWS-BEGIN>` y `// <NEWS-END>`
de 04_PINE_SCRIPT/Nasdaq_Edge_Indicator.pine. No inventa eventos: solo copia el CSV.
`valid_until` debe ser <= la última fecha con calendario completo de las cuatro
fuentes (FOMC de diciembre de 2027 aún no publicado → 2027-11-30).
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJ = Path(__file__).resolve().parents[1]
CSV = PROJ / "02_DATA" / "future_events.csv"
PINE = PROJ / "04_PINE_SCRIPT" / "Nasdaq_Edge_Indicator.pine"
BEGIN, END = "// <NEWS-BEGIN>", "// <NEWS-END>"


def render(rows: list[dict], valid_until: date, generated: date) -> str:
    ts = [
        'timestamp("America/New_York", {}, {}, {}, {}, {})'.format(
            int(r["date"][:4]), int(r["date"][5:7]), int(r["date"][8:10]), int(r["time_et"][:2]), int(r["time_et"][3:5])
        )
        for r in rows
    ]
    lines = [
        BEGIN,
        f"// GENERADO {generated.isoformat()} por tools/build_pine_news.py · {len(rows)} eventos · fuentes: BLS, BEA, Census, Federal Reserve",
        f'CAL_GENERATED = "{generated.isoformat()}"',
        f'CAL_VALID_UNTIL = timestamp("America/New_York", {valid_until.year}, {valid_until.month}, {valid_until.day}, 23, 59)',
        "var array<int> EV_T = array.from(" + ", ".join(ts) + ")",
        "var array<int> EV_TIER = array.from(" + ", ".join(r["tier"] for r in rows) + ")",
        "var array<string> EV_NAME = array.from(" + ", ".join(f'"{r["event"]}"' for r in rows) + ")",
        END,
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--valid-until", default="2027-11-30")
    args = ap.parse_args()
    with CSV.open(encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: (r["date"], r["time_et"]))
    valid = date.fromisoformat(args.valid_until)
    if rows and date.fromisoformat(rows[-1]["date"]) < valid.replace(day=1):
        raise SystemExit("valid_until posterior al último evento del CSV: el calendario no cubre ese tramo")
    text = PINE.read_text(encoding="utf-8")
    a, b = text.index(BEGIN), text.index(END) + len(END)
    PINE.write_text(text[:a] + render(rows, valid, datetime.now(ZoneInfo("America/New_York")).date()) + text[b:], encoding="utf-8")
    print(f"{len(rows)} eventos -> {PINE}")


if __name__ == "__main__":
    main()
