"""EDGE-1 X5: una lectura OOS-2 por finalista que pasa las 4 puertas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.discovery import databank, levels

ROOT = Path(__file__).resolve().parents[1]
FINALISTS = ROOT / "TL3_REPORTS" / "edge1_finalistas.json"
OUT_MD = ROOT / "TL3_REPORTS" / "edge1_confirm.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "edge1_confirm.json"
CORR_LIMIT = 0.7
CONTAMINATED = {"ny_open_vol_filter", "session_breakout_htf"}
INDEX_ASSETS = {"US100", "US500", "US30"}


def _returns(strategy_id: int) -> pd.Series | None:
    for row in databank.list_evaluations(strategy_id):
        if row["segment"] != "oos1":
            continue
        metrics = row.get("metrics") or {}
        dates = metrics.get("return_dates") or []
        values = row.get("returns")
        if values is None or len(dates) != len(values):
            continue
        series = pd.Series(values, index=pd.to_datetime(dates))
        return series.sort_index()
    return None


def _cost_r(strategy_id: int) -> float:
    for row in databank.list_evaluations(strategy_id):
        if row["segment"] == "fitness_is":
            value = (row.get("metrics") or {}).get("cost_r")
            if value is not None:
                return float(value)
    return 999.0


def main() -> None:
    rows = json.loads(FINALISTS.read_text(encoding="utf-8"))
    candidates = [row for row in rows if row.get("x3_pass")]
    candidates.sort(key=lambda row: (_cost_r(int(row["strategy_id"])), row["strategy_id"]))
    confirmed: list[dict] = []
    results = []
    for row in candidates:
        strategy_id = int(row["strategy_id"])
        template = str(row.get("template") or "")
        instrument = str(row.get("instrument") or "")
        base = {
            **row,
            "cost_r": _cost_r(strategy_id),
            "gate4": True,
            "gate4_reason": "",
            "confirm": None,
        }
        if databank.get_holdout_read(strategy_id) is not None:
            base["confirm"] = "ya leido: no se repite"
            results.append(base)
            continue
        if template in CONTAMINATED and instrument in INDEX_ASSETS:
            base["confirm"] = "a forward, OOS-2 no valido (plantilla contaminada)"
            results.append(base)
            continue
        series = _returns(strategy_id)
        max_corr = None
        max_id = None
        for item in confirmed:
            other = _returns(int(item["strategy_id"]))
            if series is None or other is None:
                continue
            joined = pd.concat([series, other], axis=1, join="inner").dropna()
            if len(joined) < 30:
                continue
            corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
            if np.isfinite(corr) and (max_corr is None or abs(corr) > abs(max_corr)):
                max_corr = corr
                max_id = item["strategy_id"]
        if max_corr is not None and abs(max_corr) > CORR_LIMIT:
            base["gate4"] = False
            base["gate4_reason"] = f"cluster {max_corr:.3f} con {max_id}"
            base["confirm"] = "no confirmado: puerta 4"
            results.append(base)
            continue
        try:
            verdict = levels.confirm(strategy_id, approved_by_operator=True)
            base["confirm"] = {
                "oos2_expectancy_r": verdict.get("oos2_expectancy_r"),
                "dsr_confirm": verdict.get("dsr_confirm"),
                "level": verdict.get("level"),
                "verdict": verdict.get("verdict"),
                "global_dsr_tests": verdict.get("global_dsr_tests"),
            }
            confirmed.append(base)
        except Exception as exc:  # noqa: BLE001
            base["confirm"] = f"bloqueado: {type(exc).__name__}: {exc}"[:300]
        results.append(base)
        print(f"{strategy_id} {template} {instrument} {row['timeframe']}: {base['confirm']}", flush=True)
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# EDGE-1 X5 - confirmacion OOS-2",
        "",
        f"**Generado:** {datetime.now(timezone.utc).isoformat()}",
        f"**Finalistas con X3 completo:** {len(candidates)} · **confirmados:** {len(confirmed)}",
        "",
        "| Estrategia | Campana | Activo | TF | cost_r | Puerta 4 | Confirmacion |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for item in results:
        confirm = item["confirm"]
        if isinstance(confirm, dict):
            confirm_text = (
                f"OOS-2 {confirm.get('oos2_expectancy_r')} · "
                f"nivel {confirm.get('level')} · {confirm.get('verdict')}"
            )
        else:
            confirm_text = str(confirm)
        gate4 = "si" if item["gate4"] else f"no ({item['gate4_reason']})"
        lines.append(
            f"| {item['strategy_id']} | `{item['campaign_id']}` | {item['instrument']} | "
            f"{item['timeframe']} | {item['cost_r']:.4f} | {gate4} | {confirm_text} |"
        )
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {OUT_MD}: {len(confirmed)} confirmados")


if __name__ == "__main__":
    main()
