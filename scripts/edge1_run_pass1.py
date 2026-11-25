"""EDGE-1 X2: aprueba y ejecuta la pasada 1, campana a campana.

Uso:
  python scripts/edge1_run_pass1.py [--start N] [--end N] [--no-commit]

Cada campana: approve --approved-by-operator (via API) y run con limite 45 min.
Escribe TL3_REPORTS/edge1_progreso.md y hace commit cada 4 campanas.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import campaigns, databank, engine

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "TL3_REPORTS" / "edge1_plan.json"
PROGRESS = ROOT / "TL3_REPORTS" / "edge1_progreso.md"
LOG = ROOT / "TL3_REPORTS" / "edge1_pass1.log"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _commit(index: int) -> None:
    message = f"edge1: X2 - campanas {max(1, index - 3)}-{index}"
    subprocess.run(
        ["git", "add", "--", str(PROGRESS), str(LOG)],
        cwd=ROOT,
        check=False,
    )
    subprocess.run(
        ["git", "commit", "-m", message, "--", str(PROGRESS), str(LOG)],
        cwd=ROOT,
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=28)
    parser.add_argument("--no-commit", action="store_true")
    args = parser.parse_args()
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    if not PROGRESS.exists():
        PROGRESS.write_text(
            "# EDGE-1 - progreso\n\n"
            f"Plan: `{payload['plan_hash']}` · iniciado {_now()}\n\n"
            "| # | Campana | Activo | TF | Plantilla | Eval | Efect | Finalistas | Estado | Tiempo |\n"
            "|---:|---|---|---|---|---:|---:|---:|---|---:|\n",
            encoding="utf-8",
        )
    for item in payload["campaigns"]:
        index = int(item["index"])
        if index < args.start or index > args.end:
            continue
        campaign_id = item["campaign_id"]
        started = time.monotonic()
        status = "Sin datos"
        evaluated = effective = finalists = "Sin datos"
        try:
            current = databank.get_campaign(campaign_id)
            if current is None:
                raise RuntimeError("campana no registrada")
            if current["status"] == "draft":
                campaigns.approve(campaign_id)
                current = databank.get_campaign(campaign_id)
            if current["status"] in {"done", "rejected", "invalid"}:
                status = str(current["status"])
            elif current["status"] == "registered":
                engine.run_campaign(campaign_id, time_limit=45)
                current = databank.get_campaign(campaign_id)
                status = str(current["status"])
            else:
                status = str(current["status"])
            if current is not None:
                evaluated = current.get("n_evaluated", "Sin datos")
                effective = current.get("n_effective", "Sin datos")
                finalists = current.get("n_finalists", "Sin datos")
        except Exception as exc:  # noqa: BLE001
            status = f"bloqueado: {type(exc).__name__}: {exc}"[:300]
        elapsed = time.monotonic() - started
        line = (
            f"| {index} | `{campaign_id}` | {item['instrument']} | {item['timeframe']} | "
            f"{item['template']} | {evaluated} | {effective} | {finalists} | "
            f"{status} | {elapsed / 60.0:.1f} min |"
        )
        _append(PROGRESS, line)
        _append(
            LOG,
            f"{_now()} {campaign_id} status={status} eval={evaluated} "
            f"eff={effective} finalists={finalists} elapsed={elapsed:.1f}s",
        )
        print(line, flush=True)
        if not args.no_commit and index % 4 == 0:
            _commit(index)
    if not args.no_commit:
        _commit(args.end)


if __name__ == "__main__":
    main()
