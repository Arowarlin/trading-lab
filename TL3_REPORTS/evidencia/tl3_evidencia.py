"""TL3 · reproduce las cifras de la auditoría forense (solo lectura).

Copia `data/discovery.db` y `data/lab.db` a un directorio temporal y las abre
en modo `ro`. No escribe en el repositorio, no ejecuta backtests y no suma
pruebas al contador. Uso:

    .\.venv\Scripts\python.exe -X utf8 -I TL3_REPORTS\evidencia\tl3_evidencia.py
"""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import statistics as st
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _copy_dbs() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="tl3_"))
    for name in ("discovery.db", "discovery.db-wal", "discovery.db-shm", "lab.db"):
        src = ROOT / "data" / name
        if src.exists():
            shutil.copy2(src, tmp / name)
    return tmp


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def discovery_tables(db: Path) -> None:
    con = _ro(db)
    print("## Campañas")
    for row in con.execute(
        "SELECT id, instrument, timeframe, template, n_total, n_evaluated, status, "
        "json_extract(config_json,'$.cost_model_version'), "
        "json_extract(config_json,'$.protocol_version') FROM disc_campaigns ORDER BY created_at"
    ):
        print(row)
    print("\n## Niveles por campaña (n, L>=2, L>=3, L>=4)")
    for row in con.execute(
        "SELECT campaign_id, COUNT(*), SUM(level>=2), SUM(level>=3), SUM(level>=4) "
        "FROM disc_strategies GROUP BY 1"
    ):
        print(row)
    print("\nLecturas de holdout (OOS-2):", con.execute(
        "SELECT COUNT(*) FROM disc_holdout_reads").fetchone()[0])
    print("\n## Bruto vs neto (IS, medianas por campaña)")
    rows = con.execute(
        "SELECT s.campaign_id, e.metrics_json FROM disc_evaluations e "
        "JOIN disc_strategies s ON s.id = e.strategy_id WHERE e.segment = 'fitness_is'"
    ).fetchall()
    data: dict[str, list] = defaultdict(list)
    for cid, mj in rows:
        m = json.loads(mj)
        raw = m.get("raw") or {}
        data[cid].append(
            (raw.get("raw_expectancy_r"), m.get("cost_r"),
             m["is"].get("expectancy_r"), m["is"].get("trades"))
        )
    print("campaña | n | bruto | bruto>0 | coste | neto | neto>0 | ops IS | MDE(sigma=1)")
    for cid, items in data.items():
        g = [x[0] for x in items if x[0] is not None]
        c = [x[1] for x in items if x[1] is not None]
        n = [x[2] for x in items if x[2] is not None]
        t = [x[3] for x in items if x[3]]
        mde = 2.49 / math.sqrt(st.median(t)) if t else None
        print(cid, len(items),
              round(st.median(g), 4) if g else "Sin datos", sum(x > 0 for x in g),
              round(st.median(c), 4) if c else "Sin datos",
              round(st.median(n), 4), sum(x > 0 for x in n),
              st.median(t) if t else None, round(mde, 3) if mde else None, sep=" | ")


def ai_trader_tables(db: Path) -> None:
    con = _ro(db)
    rows = con.execute(
        "SELECT side, shadow_side, result_r, shadow_r FROM ai_trades "
        "WHERE result_r IS NOT NULL AND shadow_r IS NOT NULL"
    ).fetchall()
    norm = lambda s: "sell" if s in ("sell", "short") else "buy"  # noqa: E731
    same = [r for r in rows if norm(r[0]) == norm(r[1])]
    diff = [r for r in rows if norm(r[0]) != norm(r[1])]
    print("\n## ai_trader vs gemela")
    print("n", len(rows), "IA media", round(st.mean(r[2] for r in rows), 4),
          "gemela media", round(st.mean(r[3] for r in rows), 4))
    for label, group in (("mismo lado", same), ("lado distinto", diff)):
        print(label, len(group), "IA", round(st.mean(r[2] for r in group), 3),
              "gemela", round(st.mean(r[3] for r in group), 3))
    for side in ("buy", "sell"):
        ai = [r[2] for r in rows if norm(r[0]) == side]
        print("IA", side, len(ai), round(st.mean(ai), 3) if ai else None)
    print("llm_calls por propósito:", con.execute(
        "SELECT purpose, COUNT(*) FROM llm_calls GROUP BY 1").fetchall())


def main() -> int:
    tmp = _copy_dbs()
    try:
        discovery_tables(tmp / "discovery.db")
        ai_trader_tables(tmp / "lab.db")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
