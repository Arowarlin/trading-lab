"""OP-4 · Descarga de un paquete APROBADO de Databento y normalización de sus barras M1.

Se ejecuta en el equipo del operador (la clave sale de Windows Credential Manager y no se imprime):

    .\\.venv\\Scripts\\python.exe scripts\\futures_data_download.py --package rb --max-usd 45 --approved-by-operator

1. Cotiza el paquete con ``metadata.get_cost`` (gratis). Si pasa de ``--max-usd``, para sin descargar nada.
2. Descarga cada trozo a ``data/futures/raw/...`` (inmutable, sha256 en ``data/futures/catalog/manifest.jsonl``).
3. Une las barras ``ohlcv-1m`` de cada raíz en ``data/futures/norm/ohlcv-1m/<RAÍZ>.parquet``.
4. Escribe ``docs/futures/evidencia/descarga_<paquete>_2026-11.md`` con filas, rangos e ``instrument_id``.

Paquetes: ``tradinglab.futures.data_download.PACKAGES`` (solo los que el operador aprobó en OP-4).
Necesita el extra ``futdata`` (``zstandard``) para leer los ``.csv.zst``.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "docs" / "futures" / "evidencia"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_package(name: str, out_root: Path) -> dict[str, Path]:
    """Une los trozos ``ohlcv-1m`` de cada raíz del paquete en un parquet por raíz."""
    from tradinglab.futures import data_download as dd

    written: dict[str, Path] = {}
    for schema, roots, _start, _end in dd.PACKAGES[name]:
        if schema != "ohlcv-1m":
            continue
        for root in roots:
            parts = sorted((out_root / "raw" / dd.PROVIDER / dd.DATASET / schema / root).glob("*.csv.zst"))
            if not parts:
                raise SystemExit(f"Sin datos: no hay trozos de {schema} {root}")
            frame = dd.build_ohlcv(parts)
            target = out_root / "norm" / schema / f"{root}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(target, index=False)
            written[root] = target
    return written


def summary_md(name: str, result: dict, written: dict[str, Path]) -> str:
    lines = [f"# Descarga del paquete `{name}` (OP-4)", "",
             f"- Coste cotizado antes de descargar: **{result['quoted_usd']:.2f} USD** "
             f"(tope {result['max_usd']:.2f} USD).",
             f"- Trozos: {result['jobs']} (crudo inmutable y manifiesto con sha256).", "",
             "| Raíz | Filas | Primera vela (UTC) | Última vela (UTC) | instrument_id distintos | SHA-256 (16) |",
             "|---|---:|---|---|---:|---|"]
    for root, path in sorted(written.items()):
        frame = pd.read_parquet(path)
        first = frame["ts_event"].min().isoformat() if len(frame) else "Sin datos"
        last = frame["ts_event"].max().isoformat() if len(frame) else "Sin datos"
        lines.append(f"| {root} | {len(frame)} | {first} | {last} | {frame['instrument_id'].nunique()} | "
                     f"`{sha256(path)[:16]}` |")
    lines += ["", "Solo datos: no se ha calculado ningún desenlace. El conteo sin desenlaces es FUT-D2."]
    return "\n".join(lines) + "\n"


def main() -> None:
    from tradinglab.futures import data_download as dd

    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, choices=sorted(dd.PACKAGES))
    ap.add_argument("--max-usd", required=True, type=float)
    ap.add_argument("--approved-by-operator", action="store_true")
    ap.add_argument("--out-root", default=str(dd.DEFAULT_OUT_ROOT))
    args = ap.parse_args()
    if not args.approved_by_operator:
        raise SystemExit("OP-4 sin aprobar: falta --approved-by-operator")
    from tradinglab.discovery.fetch_databento import _client, _get_json, _metadata_params

    out_root = Path(args.out_root)
    with _client() as client:
        result = dd.run_package(args.package, client, out_root, approved_by_operator=True, max_usd=args.max_usd,
                                get_json=_get_json, metadata_params=_metadata_params)
    written = normalize_package(args.package, out_root)
    EVID.mkdir(parents=True, exist_ok=True)
    md = summary_md(args.package, result, written)
    (EVID / f"descarga_{args.package}_2026-11.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
