"""EDGE-2 Y6: exporta EAs a exports/edge2/ (sin desplegar)."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import databank
from tradinglab.discovery.export_mql5 import export_strategy_id
from tradinglab.propfund.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
CONFIRM = ROOT / "TL3_REPORTS" / "edge2_confirm.json"
OUT = ROOT / "exports" / "edge2"
REPORT = ROOT / "TL3_REPORTS" / "edge2_eas.md"


def _account_for(row: dict) -> str:
    campaign = databank.get_campaign(str(row["campaign_id"])) or {}
    accounts = list((campaign.get("config") or {}).get("cost_accounts") or [])
    if row.get("instrument") == "US500":
        return "CFD-006"
    if "CFD-001" in accounts:
        return "CFD-001"
    return accounts[0] if accounts else "CFD-006"


def main() -> None:
    rows = json.loads(CONFIRM.read_text(encoding="utf-8"))
    selected = [
        row
        for row in rows
        if isinstance(row.get("confirm"), dict)
        or str(row.get("confirm", "")).startswith("a forward")
    ]
    registry = load_registry()
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EDGE-2 Y6 - EAs exportados (sin desplegar)",
        "",
        f"**Generado:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "Los `.mq5` estan en `exports/edge2/`. No se copiaron al terminal, no se compilaron "
        "en MT5 y no se desplegaron. Limites: los de la cuenta (CFD-001 o CFD-006).",
        "",
        "| Estrategia | Campana | Activo | TF | Cuenta | EA | sha256 | Magic | Confirmacion |",
        "|---:|---|---|---|---|---|---|---|---:|",
    ]
    for row in selected:
        strategy_id = int(row["strategy_id"])
        account_id = _account_for(row)
        account = registry.accounts.get(account_id)
        daily_loss = float(account.limits.daily_loss) if account and account.limits.daily_loss else None
        max_loss = float(account.limits.max_loss) if account and account.limits.max_loss else None
        try:
            if daily_loss is None or max_loss is None:
                raise ValueError(f"{account_id}: limites Sin datos")
            result = export_strategy_id(
                strategy_id,
                out_dir=OUT,
                account_id=account_id,
                daily_loss=daily_loss,
                max_loss=max_loss,
            )
            confirm = row.get("confirm")
            if isinstance(confirm, dict):
                confirm_text = f"OOS-2 {confirm.get('oos2_expectancy_r')} - {confirm.get('verdict')}"
            else:
                confirm_text = str(confirm)
            lines.append(
                f"| {strategy_id} | `{row['campaign_id']}` | {row['instrument']} | "
                f"{row['timeframe']} | {account_id} | `{Path(result.mq5_path).name}` | "
                f"`{result.sha256[:16]}` | {result.magic} | {confirm_text} |"
            )
        except Exception as exc:  # noqa: BLE001
            lines.append(
                f"| {strategy_id} | `{row['campaign_id']}` | {row['instrument']} | "
                f"{row['timeframe']} | {account_id} | Sin datos | - | - | "
                f"bloqueado: {type(exc).__name__}: {exc} |"
            )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", str(REPORT)], cwd=ROOT, check=False)
    subprocess.run(
        ["git", "commit", "-m", "edge2: Y6 - EAs", "--", str(REPORT)],
        cwd=ROOT,
        check=False,
    )
    print(f"Escrito {REPORT}; EAs en {OUT}")


if __name__ == "__main__":
    main()
