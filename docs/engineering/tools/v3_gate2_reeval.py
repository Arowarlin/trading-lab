"""ENG-1 · Puerta 2 (WF y PBO) de EDGE-1/EDGE-2 con puertas v2 y v3, sobre una COPIA de discovery.db.

No ejecuta campañas, no suma pruebas al contador, no lee el OOS-2 y no toca la
base de datos original: la copia a una carpeta temporal y trabaja ahí. Solo usa
las series IS que la campaña ya guardó (``fitness_is``).

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\v3_gate2_reeval.py ^
        --db E:\\trading-lab\\data\\discovery.db --prefix edge1- --prefix edge2- ^
        --out docs\\engineering\\WORKER_REPORTS\\V3-gate2.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))


def _campaign_ids(db: Path, prefixes: list[str]) -> list[str]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id FROM disc_campaigns WHERE status = 'done' ORDER BY id"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows if any(str(r[0]).startswith(p) for p in prefixes)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--prefix", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from tradinglab.discovery import robustness
    from tradinglab.discovery.config import load_engine_config

    source = Path(args.db)
    if not source.exists():
        Path(args.out).write_text(f"Sin datos: no existe {source}\n", encoding="utf-8")
        return 1
    workdir = Path(tempfile.mkdtemp(prefix="v3-reeval-"))
    copy = workdir / "discovery.db"
    shutil.copy2(source, copy)

    base = load_engine_config()

    def config(version: int):
        return base.model_copy(
            update={"robustness": base.robustness.model_copy(update={"gates_version": version})}
        )

    rows = []
    for campaign_id in _campaign_ids(copy, args.prefix or ["edge1-", "edge2-"]):
        entry = {"campaign": campaign_id}
        for version in (2, 3):
            robustness.load_engine_config = lambda v=version: config(v)
            try:
                pbo, wf = robustness._pbo_wf(campaign_id, copy)
                entry[f"v{version}"] = {
                    "pbo": pbo.get("pbo"),
                    "pbo_ok": pbo.get("pbo") is not None and float(pbo["pbo"]) <= 0.30,
                    "wf_ok": bool(wf.get("ok")),
                    "wf_eff": wf.get("efficiency"),
                    "wf_stitched": wf.get("stitched_sharpe"),
                    "wf_folds": wf.get("n_folds"),
                    "wf_windows": wf.get("wf_windows"),
                    "n_matrix": pbo.get("n_variants_matrix"),
                    "matrix": pbo.get("matrix"),
                }
            except Exception as exc:  # noqa: BLE001
                entry[f"v{version}"] = {"error": f"{type(exc).__name__}: {exc}"}
        rows.append(entry)

    def cell(v, key):
        value = v.get(key)
        return "—" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))

    lines = [
        "# V3-gate2 · Puerta 2 de EDGE-1/EDGE-2 con puertas v2 y v3",
        "",
        "Generado por `docs/engineering/tools/v3_gate2_reeval.py` sobre una **copia** de discovery.db.",
        "Sin campañas, sin contador, sin OOS-2. Puerta 2 = PBO <= 0,30 **y** WF ok.",
        "",
        "| Campaña | v2 PBO | v2 WF | v3 PBO | v3 WF ok | v3 eff | v3 stitched | v3 pliegues | v3 n | v3 puerta 2 |",
        "|---|---:|---|---:|---|---:|---:|---:|---:|---|",
    ]
    passes = 0
    for row in rows:
        v2, v3 = row.get("v2", {}), row.get("v3", {})
        gate = bool(v3.get("pbo_ok") and v3.get("wf_ok"))
        passes += gate
        lines.append(
            f"| `{row['campaign']}` | {cell(v2, 'pbo')} | {'ok' if v2.get('wf_ok') else 'no'} | "
            f"{cell(v3, 'pbo')} | {'ok' if v3.get('wf_ok') else 'no'} | {cell(v3, 'wf_eff')} | "
            f"{cell(v3, 'wf_stitched')} | {cell(v3, 'wf_folds')} | {cell(v3, 'n_matrix')} | "
            f"{'**PASA**' if gate else 'no'} |"
        )
    lines += ["", f"Campañas que pasan la puerta 2 con v3: **{passes} de {len(rows)}**.", ""]
    lines += ["```json", json.dumps(rows, indent=1, default=str), "```", ""]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {out}: {passes} de {len(rows)} pasan la puerta 2 con v3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
