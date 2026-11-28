"""FUT-B3 · Manifiesto con hash de los datos de futuros que ya existen (solo lectura de datos).

Se ejecuta en el equipo del operador:

    .\\.venv\\Scripts\\python.exe scripts\\futures_manifest.py

Recorre SOLO data/cache/databento/*.parquet, no modifica ni copia nada y escribe
docs/futures/evidencia/manifest_futuros.jsonl y .md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTERNAL_TO_ROOT = {"US100": "NQ", "US500": "ES", "US30": "YM", "XAUUSD": "GC", "EURUSD": "6E", "GBPUSD": "6B",
                    "USDJPY": "6J"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def describe(path: Path) -> dict:
    import pandas as pd

    frame = pd.read_parquet(path)
    ts = None
    for col in ("ts_event", "time", "timestamp", "datetime"):
        if col in frame.columns:
            ts = pd.to_datetime(frame[col], utc=True)
            break
    if ts is None and isinstance(frame.index, pd.DatetimeIndex):
        ts = frame.index.tz_localize("UTC") if frame.index.tz is None else frame.index.tz_convert("UTC")
    m = re.match(r"(?P<sym>[A-Z0-9]+)_(?P<tf>[A-Z0-9]+)\.parquet$", path.name)
    internal = m.group("sym") if m else None
    return {
        "path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path),
        "rows": int(len(frame)),
        "first_utc": None if ts is None or len(ts) == 0 else ts.min().isoformat(),
        "last_utc": None if ts is None or len(ts) == 0 else ts.max().isoformat(),
        "columns": list(map(str, frame.columns)), "has_instrument_id": "instrument_id" in frame.columns,
        "internal_symbol": internal, "databento_root": INTERNAL_TO_ROOT.get(internal or "", "Sin datos"),
        "timeframe": m.group("tf") if m else "Sin datos",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "cache" / "databento"))
    ap.add_argument("--out-dir", default=str(ROOT / "docs" / "futures" / "evidencia"))
    args = ap.parse_args()
    files = sorted(Path(args.data_dir).glob("*.parquet"))
    rows = [describe(p) for p in files]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest_futuros.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    lines = ["# FUT-B3 · Manifiesto de datos de futuros existentes", "",
             "| Fichero | Raíz | TF | Filas | Primera (UTC) | Última (UTC) | instrument_id | SHA-256 (16) |",
             "|---|---|---|---:|---|---|---|---|"]
    lines += [f"| {r['path']} | {r['databento_root']} | {r['timeframe']} | {r['rows']} | {r['first_utc']} | "
              f"{r['last_utc']} | {'sí' if r['has_instrument_id'] else 'no'} | `{r['sha256'][:16]}` |" for r in rows]
    if not rows:
        lines.append("| Sin datos | | | | | | | |")
    (out / "manifest_futuros.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
