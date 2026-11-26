"""ENG-L1 · Comprobaciones de cobertura sobre la caché Dukascopy real (solo lectura).

Responde con datos reales a dos hallazgos de AUDIT_FINDINGS.md:

* C-01: huecos >= ``max_gap_hours`` dentro de la semana que ``data-check`` no
  clasifica en M1-M30. Se listan los del tramo IS de EDGE-2 M15/M30
  (2015-01-02 .. 2019-12-31) y, por separado, los demás años.
* C-02: meses cuya última vela queda antes del último día hábil del mes
  (síntoma de la reanudación que da el mes por completo).

Solo lee el **índice** (marcas de tiempo) de ``data/cache/dukascopy/*_M1.parquet``:
no carga precios, no calcula rendimiento y no escribe en ninguna base de datos.
Escribe un informe Markdown en la ruta que se le pase.

Uso (desde la raíz del repo, en el equipo del operador):

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\eng_l1_data_checks.py ^
        --out docs\\engineering\\WORKER_REPORTS\\L1-data.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

NY = "America/New_York"
IS_START = pd.Timestamp("2015-01-02", tz=NY)
IS_END = pd.Timestamp("2019-12-31 23:59", tz=NY)


REPO = Path(__file__).resolve().parents[3]


def _max_gap_hours() -> float:
    sys.path.insert(0, str(REPO / "src"))
    from tradinglab.discovery.config import load_engine_config

    return float(load_engine_config().data_quality.max_gap_hours)


def load_index(path: Path) -> pd.DatetimeIndex:
    frame = pd.read_parquet(path, columns=[])
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if index.tz is None:
        index = index.tz_localize("UTC")
    return index.tz_convert("UTC").sort_values().unique()


def _is_weekend_gap(start_ny: pd.Timestamp, end_ny: pd.Timestamp) -> bool:
    """Hueco que empieza viernes >= 15:00 NY y termina domingo/lunes: cierre semanal."""

    return (
        start_ny.day_of_week == 4 and start_ny.hour >= 15 and end_ny.day_of_week in (6, 0)
    ) or start_ny.day_of_week in (5, 6)


def weekday_gaps(index: pd.DatetimeIndex, min_hours: float) -> pd.DataFrame:
    if len(index) < 2:
        return pd.DataFrame(columns=["start_ny", "end_ny", "hours", "weekday"])
    prev = index[:-1]
    nxt = index[1:]
    hours = (nxt - prev).total_seconds() / 3600.0
    rows = []
    for a, b, h in zip(prev, nxt, hours):
        if h < min_hours:
            continue
        a_ny, b_ny = a.tz_convert(NY), b.tz_convert(NY)
        if _is_weekend_gap(a_ny, b_ny):
            continue
        rows.append(
            {
                "start_ny": a_ny,
                "end_ny": b_ny,
                "hours": round(float(h), 2),
                "weekday": a_ny.day_name(),
            }
        )
    return pd.DataFrame(rows)


def truncated_months(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Meses cuya última vela cae >= 2 días hábiles antes del fin de mes (excepto el último)."""

    local = index.tz_convert(NY).tz_localize(None)
    months = pd.Series(local, index=local).groupby(local.to_period("M")).max()
    rows = []
    for period, last in list(months.items())[:-1]:
        month_end = period.to_timestamp(how="end").normalize()
        last_bday = pd.bdate_range(period.to_timestamp(), month_end)[-1]
        missing = pd.bdate_range(last.normalize() + pd.Timedelta(days=1), last_bday)
        if len(missing) >= 2:
            rows.append(
                {
                    "month": str(period),
                    "last_bar_ny": last,
                    "missing_bdays": len(missing),
                    "first_missing": missing[0].date(),
                }
            )
    return pd.DataFrame(rows)


def report(root: Path, symbols: list[str] | None) -> str:
    cache = root / "data" / "cache" / "dukascopy"
    lines = [
        "# L1-data · Cobertura real de la caché Dukascopy (ENG-L1)",
        "",
        "Generado por `docs/engineering/tools/eng_l1_data_checks.py` (solo índice; sin precios).",
        "",
    ]
    if not cache.exists():
        return "\n".join(lines + [f"**Sin datos:** no existe `{cache}`.", ""])
    min_hours = _max_gap_hours()
    lines += [f"`max_gap_hours` = {min_hours}", ""]
    paths = sorted(cache.glob("*_M1.parquet"))
    if symbols:
        wanted = {s.upper() for s in symbols}
        paths = [p for p in paths if p.name.split("_M1")[0].upper() in wanted]
    if not paths:
        return "\n".join(lines + ["**Sin datos:** no hay ficheros `*_M1.parquet`.", ""])
    for path in paths:
        symbol = path.name.split("_M1")[0]
        try:
            index = load_index(path)
        except Exception as exc:  # noqa: BLE001
            lines += [f"## {symbol}", "", f"**Sin datos:** {type(exc).__name__}: {exc}", ""]
            continue
        gaps = weekday_gaps(index, min_hours)
        lines += [
            f"## {symbol}",
            "",
            f"- Velas M1: {len(index):,}; desde {index[0].tz_convert(NY)} hasta {index[-1].tz_convert(NY)}",
        ]
        if gaps.empty:
            lines += [f"- C-01: 0 huecos >= {min_hours} h entre semana.", ""]
        else:
            in_is = gaps[(gaps.start_ny >= IS_START) & (gaps.start_ny <= IS_END)]
            by_year = gaps.groupby(gaps.start_ny.map(lambda t: t.year)).size()
            lines += [
                f"- C-01: {len(gaps)} huecos >= {min_hours} h entre semana; "
                f"{len(in_is)} dentro del IS de EDGE-2 M15/M30 (2015-01-02..2019-12-31).",
                "- Por año: " + ", ".join(f"{y}: {n}" for y, n in by_year.items()),
                "",
                "| Inicio (NY) | Fin (NY) | Horas | Día |",
                "|---|---|---:|---|",
            ]
            for row in in_is.head(60).itertuples():
                lines.append(f"| {row.start_ny} | {row.end_ny} | {row.hours} | {row.weekday} |")
            if len(in_is) > 60:
                lines.append(f"| … | … | … | ({len(in_is) - 60} más) |")
            lines.append("")
        months = truncated_months(index)
        if months.empty:
            lines += ["- C-02: ningún mes truncado (>= 2 días hábiles sin datos al final).", ""]
        else:
            lines += [
                f"- C-02: {len(months)} meses con >= 2 días hábiles sin datos al final "
                "(pueden ser festivos o cierres; revisar):",
                "",
                "| Mes | Última vela (NY) | Días hábiles sin datos | Primero |",
                "|---|---|---:|---|",
            ]
            for row in months.itertuples():
                lines.append(
                    f"| {row.month} | {row.last_bar_ny} | {row.missing_bdays} | {row.first_missing} |"
                )
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO), help="raíz con data/cache/dukascopy")
    parser.add_argument("--out", required=True)
    parser.add_argument("--symbols", nargs="*", default=None)
    args = parser.parse_args(argv)
    text = report(Path(args.root), args.symbols)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"Escrito {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
