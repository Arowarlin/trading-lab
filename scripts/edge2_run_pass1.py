"""EDGE-2 Y2: aprueba y ejecuta la pasada 1, campana a campana.

Uso:
  python scripts/edge2_run_pass1.py [--start N] [--end N] [--no-commit]

Cada campana: approve --approved-by-operator (via CLI) y run con limite 45 min.
Escribe TL3_REPORTS/edge2_progreso.md y hace commit cada 4 campanas.
No toca produccion, engine.yaml ni fastbt.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import databank, engine

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "TL3_REPORTS" / "edge2_plan.json"
PROGRESS = ROOT / "TL3_REPORTS" / "edge2_progreso.md"
LOG = ROOT / "TL3_REPORTS" / "edge2_pass1.log"
CONSOLE = "http://127.0.0.1:8420/api/discovery/campaigns"


def _approve(campaign_id: str) -> None:
    """La aprobacion solo entra por el CLI, con su flag explicito."""
    subprocess.run(
        [
            str(ROOT / ".venv" / "Scripts" / "lab.exe"),
            "discovery",
            "approve",
            campaign_id,
            "--approved-by-operator",
        ],
        cwd=ROOT,
        check=True,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _console_has(campaign_id: str) -> str:
    try:
        with urllib.request.urlopen(CONSOLE, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = payload if isinstance(payload, list) else payload.get("campaigns", [])
        found = any(str(item.get("id") or item.get("campaign_id")) == campaign_id for item in items)
        return "si" if found else "no"
    except Exception:  # noqa: BLE001
        return "Sin datos"


def _commit(index: int) -> None:
    message = f"edge2: Y2 - campanas {max(1, index - 3)}-{index}"
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
    parser.add_argument("--end", type=int, default=99)
    parser.add_argument("--no-commit", action="store_true")
    args = parser.parse_args()
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    if "| # | Campana" not in PROGRESS.read_text(encoding="utf-8"):
        _append(PROGRESS, "")
        _append(PROGRESS, "## Pasada 1")
        _append(PROGRESS, "")
        _append(
            PROGRESS,
            "| # | Campana | Activo | TF | Plantilla | Eval | Efect | Finalistas | Estado | Consola | Tiempo |",
        )
        _append(PROGRESS, "|---:|---|---|---|---|---:|---:|---:|---|---|---:|")
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
                _approve(campaign_id)
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
        console = _console_has(campaign_id)
        line = (
            f"| {index} | `{campaign_id}` | {item['instrument']} | {item['timeframe']} | "
            f"{item['template']} | {evaluated} | {effective} | {finalists} | "
            f"{status} | {console} | {elapsed / 60.0:.1f} min |"
        )
        _append(PROGRESS, line)
        _append(
            LOG,
            f"{_now()} {campaign_id} status={status} eval={evaluated} "
            f"eff={effective} finalists={finalists} console={console} elapsed={elapsed:.1f}s",
        )
        print(line, flush=True)
        if not args.no_commit and index % 4 == 0:
            _commit(index)
    if not args.no_commit:
        _commit(int(payload["campaigns"][-1]["index"]))


if __name__ == "__main__":
    main()
