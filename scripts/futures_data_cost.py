"""FUT-B1 · Coste exacto de datos de futuros en Databento (SOLO metadatos: gratis, sin descargar nada).

Se ejecuta en el equipo del operador (la clave sale de Windows Credential Manager y no se imprime):

    .\\.venv\\Scripts\\python.exe scripts\\futures_data_cost.py

Escribe docs/futures/evidencia/databento_costes_2026-11.json y .md. Nunca llama a timeseries.get_range.
No recomienda compras: decide el operador (OP-4).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROWS: list[tuple[str, tuple[str, ...], str, str, str]] = [
    # (esquema, raíces, inicio, fin, para qué)
    ("ohlcv-1m", ("NQ", "MNQ", "ES", "MES", "GC", "MGC"), "2019-01-01", "2026-11-27", "base"),
    ("definition", ("NQ", "MNQ", "ES", "MES", "GC", "MGC"), "2019-01-01", "2026-11-27", "rolls"),
    ("trades", ("NQ", "MNQ", "ES", "MES", "GC", "MGC"), "2019-01-01", "2026-11-27", "Research A"),
    ("tbbo", ("NQ", "MNQ", "ES", "MES"), "2019-01-01", "2026-11-27", "Research A (fills)"),
    ("mbp-1", ("NQ", "MNQ"), "2025-11-27", "2026-11-27", "muestra"),
    ("mbp-10", ("NQ", "MNQ"), "2026-10-27", "2026-11-27", "muestra"),
    ("mbo", ("NQ", "MNQ"), "2026-11-16", "2026-11-23", "muestra"),
    ("ohlcv-1m", ("ES", "GC"), "2010-06-06", "2018-12-31", "Research B (RB_spec §2)"),
    ("definition", ("ES", "GC"), "2010-06-06", "2018-12-31", "Research B"),
    ("trades", ("NQ",), "2017-01-01", "2018-12-31", "Research A, opción (RA_spec §2)"),
    ("tbbo", ("NQ",), "2017-01-01", "2018-12-31", "Research A, opción"),
]
OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "futures" / "evidencia"


def cost_rows(client: Any, get_json, metadata_params, dataset: str = "GLBX.MDP3") -> list[dict]:
    """Una fila por esquema y raíz. Un fallo deja "Sin datos: <error>" y sigue con la siguiente."""
    out = []
    for schema, roots, start, end, purpose in ROWS:
        for root in roots:
            symbol = f"{root}.v.0"
            row = {"schema": schema, "root": root, "symbol": symbol, "start": start, "end": end, "purpose": purpose,
                   "records": None, "billable_bytes": None, "cost_usd": None, "error": None}
            params = metadata_params(dataset=dataset, schema=schema, row_symbol=symbol, start=start, end=end)
            try:
                row["records"] = int(get_json(client, "metadata.get_record_count", params))
                row["billable_bytes"] = int(get_json(client, "metadata.get_billable_size", params))
                row["cost_usd"] = float(get_json(client, "metadata.get_cost", params))
            except Exception as exc:  # noqa: BLE001 - se registra literal y se sigue
                row["error"] = f"Sin datos: {exc}"
            out.append(row)
    return out


def to_markdown(rows: list[dict]) -> str:
    lines = ["# FUT-B1 · Coste de datos Databento (solo metadatos)", "",
             "| Esquema | Raíz | Inicio | Fin | Para | Registros | Bytes facturables | Coste USD | Error |",
             "|---|---|---|---|---|---:|---:|---:|---|"]
    totals: dict[str, float] = {}
    for r in rows:
        cost = "" if r["cost_usd"] is None else f"{r['cost_usd']:.2f}"
        lines.append(f"| {r['schema']} | {r['root']} | {r['start']} | {r['end']} | {r['purpose']} | "
                     f"{r['records'] or ''} | {r['billable_bytes'] or ''} | {cost} | {r['error'] or ''} |")
        if r["cost_usd"] is not None:
            key = f"{r['schema']} ({r['purpose']})"
            totals[key] = totals.get(key, 0.0) + r["cost_usd"]
    lines += ["", "| Total por esquema y uso | USD |", "|---|---:|"]
    lines += [f"| {k} | {v:.2f} |" for k, v in sorted(totals.items())]
    lines += ["", "No es una recomendación de compra: decide el operador (OP-4)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    from tradinglab.discovery.fetch_databento import _client, _get_json, _metadata_params

    with _client() as client:
        rows = cost_rows(client, _get_json, _metadata_params)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "databento_costes_2026-11.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (out / "databento_costes_2026-11.md").write_text(to_markdown(rows), encoding="utf-8")
    print(to_markdown(rows))


if __name__ == "__main__":
    main()
