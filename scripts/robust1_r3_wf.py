"""ROBUST-1 R3: operaciones por ventana de prueba del WF en los 22 finalistas.

Solo lectura (IS). No escribe campañas, validaciones ni OOS-2. Recalcula PBO/WF
con la matriz diaria ordenada y usa la variante elegida por el WF en cada
pliegue, no la estrategia finalista.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import robustness

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "TL3_REPORTS" / "robust1_wf.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "robust1_wf.json"


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    con = sqlite3.connect(ROOT / "data" / "discovery.db")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select * from disc_strategies where campaign_id like 'edge1-%' "
        "and status = 'finalist' order by campaign_id, id"
    ).fetchall()
    campaigns = sorted({str(row["campaign_id"]) for row in rows})
    corrected: dict[str, dict] = {}
    corrected_pbo: dict[str, dict] = {}
    for campaign_id in campaigns:
        times = robustness.variant_trade_times(campaign_id)
        pbo, wf = robustness._pbo_wf(
            campaign_id, None, trade_times_by_strategy=times
        )
        corrected[campaign_id] = wf
        corrected_pbo[campaign_id] = pbo
        print(
            f"[R3] {campaign_id} eff={wf.get('efficiency')} "
            f"median={wf.get('test_trades_median')} "
            f"label={wf.get('wf_label')} pbo={pbo.get('pbo')}",
            flush=True,
        )
    results = []
    for strategy in rows:
        strategy_id = int(strategy["id"])
        campaign_id = str(strategy["campaign_id"])
        wf = corrected.get(campaign_id) or {}
        freq = wf
        results.append(
            {
                "strategy_id": strategy_id,
                "campaign_id": campaign_id,
                "instrument": str(strategy["instrument"]),
                "timeframe": str(strategy["timeframe"]),
                "wf_efficiency": _num(wf.get("efficiency")),
                "n_folds": int(wf.get("n_folds") or 0),
                "test_trades_per_fold": freq.get("test_trades_per_fold", []),
                "test_trades_median": freq.get("test_trades_median"),
                "wf_informative": freq.get("wf_informative"),
                "wf_label": freq.get("wf_label"),
                "pbo": _num((corrected_pbo.get(campaign_id) or {}).get("pbo")),
            }
        )
    OUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    low = sum(1 for item in results if item["wf_informative"] is False)
    lines = [
        "# ROBUST-1 R3 - Walk-forward en baja frecuencia",
        "",
        f"**Generado:** {datetime.now(timezone.utc).isoformat()}",
        f"**Finalistas:** {len(results)} · **WF no informativo:** {low}",
        "",
        "Ventanas actuales: `train=60` días, `test=20` días "
        "(`engine.yaml::robustness`), sin cambios. Matriz diaria ordenada "
        "(R2). Se cuentan los **cierres de la variante elegida por el WF en "
        "cada pliegue**, que es la que el walk-forward evalúa; el detalle por "
        "pliegue queda en `robust1_wf.json`.",
        "",
        "| Estrategia | Campaña | Activo | TF | WF eff | Pliegues | Mediana ops/pliegue | Rango ops | Etiqueta |",
        "|---:|---|---|---|---:|---:|---:|---|---|",
    ]
    for item in results:
        counts = item["test_trades_per_fold"]
        if counts:
            counts_text = f"{min(counts)}-{max(counts)}"
        else:
            counts_text = "Sin datos"
        median = item["test_trades_median"]
        median_text = "Sin datos" if median is None else f"{median:.1f}"
        eff = item["wf_efficiency"]
        eff_text = "Sin datos" if eff is None else f"{eff:.3f}"
        if item["wf_informative"] is None:
            label = "Sin datos"
        else:
            label = item["wf_label"] or "informativo"
        lines.append(
            f"| {item['strategy_id']} | `{item['campaign_id']}` | "
            f"{item['instrument']} | {item['timeframe']} | {eff_text} | "
            f"{item['n_folds']} | {median_text} | {counts_text} | {label} |"
        )
    lines += [
        "",
        "## Lectura",
        "",
        "- La puerta WF **sigue sin pasar** cuando la eficiencia es < 0,3; la",
        "  etiqueta solo explica que la ventana de 20 días no contiene",
        "  operaciones suficientes para medirla.",
        "- No se tocaron `wf_train_days`/`wf_test_days` ni ningún umbral.",
        "- Propuesta de ventanas por TF para una cola futura, prerregistrada en",
        "  `TL3_REPORTS/robust1_wf_windows.md`; no se aplica en esta cola.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {OUT_MD}: {len(results)} finalistas, {low} no informativos")


if __name__ == "__main__":
    main()
