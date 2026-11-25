"""EDGE-1 X6: exporta EAs a exports/edge1/ (sin desplegar)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery.export_mql5 import export_strategy_id

ROOT = Path(__file__).resolve().parents[1]
CONFIRM = ROOT / "TL3_REPORTS" / "edge1_confirm.json"
OUT = ROOT / "exports" / "edge1"
REPORT = ROOT / "TL3_REPORTS" / "edge1_eas.md"


def main() -> None:
    rows = json.loads(CONFIRM.read_text(encoding="utf-8"))
    selected = [
        row
        for row in rows
        if isinstance(row.get("confirm"), dict)
        or str(row.get("confirm", "")).startswith("a forward")
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EDGE-1 X6 - EAs exportados (sin desplegar)",
        "",
        f"**Generado:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "Los `.mq5` estan en `exports/edge1/`. No se copiaron al terminal, no se compilaron "
        "en MT5 y no se desplegaron. Limites: CFD-001, perdida diaria 5.000 USD, perdida "
        "maxima 10.000 USD.",
        "",
        "| Estrategia | Campana | Activo | TF | EA | sha256 | Magic | Confirmacion |",
        "|---:|---|---|---|---|---|---:|---|",
    ]
    for row in selected:
        strategy_id = int(row["strategy_id"])
        try:
            result = export_strategy_id(
                strategy_id,
                out_dir=OUT,
                account_id="CFD-001",
                daily_loss=5000.0,
                max_loss=10000.0,
            )
            confirm = row.get("confirm")
            if isinstance(confirm, dict):
                confirm_text = f"OOS-2 {confirm.get('oos2_expectancy_r')} · {confirm.get('verdict')}"
            else:
                confirm_text = str(confirm)
            lines.append(
                f"| {strategy_id} | `{row['campaign_id']}` | {row['instrument']} | "
                f"{row['timeframe']} | `{Path(result.mq5_path).name}` | "
                f"`{result.sha256[:16]}` | {result.magic} | {confirm_text} |"
            )
        except Exception as exc:  # noqa: BLE001
            lines.append(
                f"| {strategy_id} | `{row['campaign_id']}` | {row['instrument']} | "
                f"{row['timeframe']} | Sin datos | - | - | bloqueado: {type(exc).__name__}: {exc} |"
            )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Escrito {REPORT}; EAs en {OUT}")


if __name__ == "__main__":
    main()
