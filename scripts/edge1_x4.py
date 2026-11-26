"""EDGE-1 X4: pasada 2 (perfil medium) segun la regla congelada."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import campaigns, databank, engine

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "TL3_REPORTS" / "edge1_plan.json"
FINALISTS = ROOT / "TL3_REPORTS" / "edge1_finalistas.json"
OUT_MD = ROOT / "TL3_REPORTS" / "edge1_pass2.md"
PROGRESS = ROOT / "TL3_REPORTS" / "edge1_progreso.md"
LOG = ROOT / "TL3_REPORTS" / "edge1_pass2.log"
MAX_PASS2 = 6


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _approve(campaign_id: str) -> None:
    """La aprobación solo entra por el CLI, con su flag explícito."""
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


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def main() -> None:
    payload = json.loads(PLAN.read_text(encoding="utf-8"))
    results = json.loads(FINALISTS.read_text(encoding="utf-8"))
    by_campaign = {item["campaign_id"]: item for item in payload["campaigns"]}
    passed: dict[str, int] = {}
    for row in results:
        if row.get("x3_pass"):
            passed[row["campaign_id"]] = passed.get(row["campaign_id"], 0) + 1
    ordered = sorted(
        passed.items(),
        key=lambda item: (-item[1], by_campaign[item[0]]["cost_r"] if item[0] in by_campaign else 999),
    )[:MAX_PASS2]
    lines = [
        "# EDGE-1 X4 - pasada 2",
        "",
        f"**Generado:** {_now()}",
        "",
        "Regla congelada: campanas con >= 1 finalista que paso X3 completo; maximo 6; "
        "orden por mas finalistas y, a igualdad, menor `cost_r`. Perfil `medium`, "
        "semilla `1000 + indice`.",
        "",
    ]
    if not ordered:
        lines.append("**X4 = `sin pasada 2`.** Ninguna campana tuvo un finalista que pasara X3 completo.")
        OUT_MD.write_text("\n".join(lines), encoding="utf-8")
        print("X4 sin pasada 2")
        return
    lines.append("| # | Campana original | Finalistas X3 | cost_r | Campana pasada 2 | n_total | Estado |")
    lines.append("|---:|---|---:|---:|---|---:|---|")
    for number, (campaign_id, count) in enumerate(ordered, start=1):
        original = by_campaign[campaign_id]
        new_id = f"edge1-p2-{number:02d}-{original['template'].replace('_', '-')[:18]}-{original['instrument'].lower()}-{original['timeframe'].lower()}"
        segments = {
            "is": [original["is_start"], original["is_end"]],
            "oos1": [original["oos1_start"], original["oos1_end"]],
            "oos2": [original["oos2_start"], original["oos2_end"]],
        }
        try:
            campaign = campaigns.register(
                original["instrument"],
                original["timeframe"],
                original["template"],
                "medium",
                segments=segments,
                seed=1000 + int(original["index"]),
                campaign_id=new_id,
                mode=original["mode"],
                data_source=original["data_source"],
                cost_accounts=original["cost_accounts"],
                cost_mode=original["cost_mode"],
                dry_run=False,
            )
            _approve(new_id)
            started = time.monotonic()
            engine.run_campaign(new_id, time_limit=45)
            current = databank.get_campaign(new_id)
            status = str(current["status"])
            elapsed = time.monotonic() - started
            line = (
                f"| {number} | `{campaign_id}` | {count} | {original['cost_r']:.4f} | "
                f"`{new_id}` | {campaign['n_total']} | {status} ({elapsed / 60.0:.1f} min) |"
            )
        except Exception as exc:  # noqa: BLE001
            line = (
                f"| {number} | `{campaign_id}` | {count} | {original['cost_r']:.4f} | "
                f"`{new_id}` | Sin datos | bloqueado: {type(exc).__name__}: {exc} |"
            )
        lines.append(line)
        _append(PROGRESS, line)
        _append(LOG, f"{_now()} {line}")
        print(line, flush=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["git", "add", "--", str(OUT_MD), str(LOG)], cwd=ROOT, check=False)
    subprocess.run(
        ["git", "commit", "-m", "edge1: X4 - pasada 2", "--", str(OUT_MD), str(LOG)],
        cwd=ROOT,
        check=False,
    )


if __name__ == "__main__":
    main()
