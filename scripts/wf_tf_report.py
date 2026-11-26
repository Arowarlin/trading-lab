"""Informe WF-TF: combina la evaluacion con las puertas ya calculadas.

Lee ``wf_tf_eval_<queue>.json`` (W1) y ``<queue>_finalistas.json`` (X3/Y3),
sin recalcular PBO, ruido, ejecucion ni costes. La puerta 4 usa retornos
diarios de OOS-1 (nunca OOS-2) y agrupa por correlacion > 0,7.

Escribe/actualiza ``TL3_REPORTS/wf_tf_resultados.md`` y ``.json``. La seccion
de cada cola se conserva al anadir la siguiente.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wf_tf_eval  # noqa: E402

from tradinglab.discovery import databank  # noqa: E402

OUT_MD = ROOT / "TL3_REPORTS" / "wf_tf_resultados.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "wf_tf_resultados.json"
CORR_LIMIT = 0.7
PBO_MAX = 0.30
RATIO_MIN = 0.5

PREREG = {
    "path": "TL3_REPORTS/robust1_wf_windows.md",
    "commit": "ccf27cb",
    "sha256": "f8ad4e9e30c2b4aa3dd26f2831e102163c8001467ae5d6147deb311ac6f75238",
}
DECLARATION = (
    "Esta evaluación es una **segunda oportunidad** para los finalistas de "
    "EDGE-1. La propuesta de ventanas se escribió a partir de la **frecuencia** "
    "de operaciones, no de resultados, pero se aplica sabiendo que tres "
    "finalistas de `edge1-11` (USDJPY H1; 5178, 5309 y 5385) solo fallaban por "
    'un WF "no informativo". Se aplica **igual a los 22**, una sola vez y con '
    "los mismos umbrales. El juez final sigue siendo el OOS-2 (2023-2026), "
    "**sin abrir**, que solo el operador puede autorizar a leer una vez."
)
CANDIDATE_PHRASE = (
    "Candidato a `confirm`: requiere autorización explícita del operador; la "
    "plantilla `trend_pullback_mtf` es de 24 h y mantiene posiciones varios "
    "días (swap y fin de semana; ver COLA-MOTOR-FLAT)"
)

QUEUES = {
    "edge1": {
        "label": "EDGE-1",
        "finalists": ROOT / "TL3_REPORTS" / "edge1_finalistas.json",
        "eval": ROOT / "TL3_REPORTS" / "wf_tf_eval_edge1.json",
    },
    "edge2": {
        "label": "EDGE-2",
        "finalists": ROOT / "TL3_REPORTS" / "edge2_finalistas.json",
        "eval": ROOT / "TL3_REPORTS" / "wf_tf_eval_edge2.json",
    },
}


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _fmt(value: Any, digits: int = 3) -> str:
    number = _num(value)
    return "Sin datos" if number is None else f"{number:.{digits}f}"


def _evals_by_campaign(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["campaign_id"]): item for item in payload.get("results", [])
    }


def _verdict_reason(result: dict[str, Any]) -> str:
    if not result:
        return "Sin datos"
    if result.get("status") == "Sin datos":
        return str(result.get("reason") or "Sin datos")
    thresholds = result.get("thresholds") or {}
    min_sharpe = float(thresholds.get("min_oos_sharpe", 0.0))
    min_eff = float(thresholds.get("min_efficiency", 0.3))
    checks = [
        (
            "stitched_sharpe",
            float(result.get("stitched_sharpe") or 0.0) > min_sharpe,
            f"stitched {_fmt(result.get('stitched_sharpe'))} <= {min_sharpe:.2f}",
        ),
        (
            "frac_positive",
            float(result.get("frac_positive") or 0.0) >= 0.5,
            f"pliegues positivos {_fmt(result.get('frac_positive'))} < 0,500",
        ),
        (
            "efficiency",
            float(result.get("efficiency") or 0.0) >= min_eff,
            f"eficiencia {_fmt(result.get('efficiency'))} < {min_eff:.2f}",
        ),
        (
            "median_rank_pct",
            float(result.get("median_rank_pct") or 0.0) >= 0.5,
            f"rank mediano {_fmt(result.get('median_rank_pct'))} < 0,500",
        ),
        (
            "stability",
            float(result.get("stability") or 0.0) >= 0.3,
            f"estabilidad {_fmt(result.get('stability'))} < 0,300",
        ),
    ]
    for _name, passed, reason in checks:
        if not passed:
            return reason
    return "ok"


def _returns(strategy_id: int, db_path: Path, segment: str = "oos1") -> pd.Series | None:
    with wf_tf_eval.readonly_databank(db_path):
        rows = databank.list_evaluations(strategy_id, db_path=db_path)
    for row in rows:
        if row["segment"] != segment:
            continue
        metrics = row.get("metrics") or {}
        dates = metrics.get("return_dates") or []
        values = row.get("returns")
        if values is None or len(dates) != len(values):
            continue
        return pd.Series(values, index=pd.to_datetime(dates)).sort_index()
    return None


def _correlation_groups(
    candidates: list[dict[str, Any]], db_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Agrupa por |corr| > 0,7 y elige el menor cost_r de cada grupo."""

    ids = [int(item["strategy_id"]) for item in candidates]
    series = {sid: _returns(sid, db_path) for sid in ids}
    parent = {sid: sid for sid in ids}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    edges: list[dict[str, Any]] = []
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            first, second = series.get(left), series.get(right)
            if first is None or second is None:
                continue
            joined = pd.concat([first, second], axis=1, join="inner").dropna()
            if len(joined) < 30:
                continue
            corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
            if np.isfinite(corr) and abs(corr) > CORR_LIMIT:
                union(left, right)
                edges.append(
                    {
                        "a": left,
                        "b": right,
                        "correlation": corr,
                    }
                )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        grouped[find(int(item["strategy_id"]))].append(item)
    groups: list[dict[str, Any]] = []
    for members in grouped.values():
        ordered = sorted(
            members,
            key=lambda item: (
                _num(item.get("cost_r")) is None,
                _num(item.get("cost_r")) or 999.0,
                int(item["strategy_id"]),
            ),
        )
        chosen = ordered[0]
        groups.append(
            {
                "strategy_ids": [int(item["strategy_id"]) for item in ordered],
                "chosen": int(chosen["strategy_id"]),
                "cost_r": {
                    str(item["strategy_id"]): _num(item.get("cost_r"))
                    for item in ordered
                },
            }
        )
    groups.sort(key=lambda item: item["chosen"])
    return groups, edges


def build_queue(queue: str, db_path: Path) -> dict[str, Any]:
    config = QUEUES[queue]
    finalists = json.loads(config["finalists"].read_text(encoding="utf-8"))
    evaluations = _evals_by_campaign(config["eval"])
    items: list[dict[str, Any]] = []
    for row in finalists:
        campaign_id = str(row["campaign_id"])
        result = evaluations.get(campaign_id) or {}
        pbo = _num(row.get("pbo"))
        noise = _num(row.get("noise_ratio"))
        execution = _num(row.get("exec_ratio"))
        spread = _num(row.get("spread_p75_expectancy_r"))
        slip = _num(row.get("slippage_plus_2_expectancy_r"))
        gate1 = bool(row.get("gate1"))
        wf_ok = bool(result.get("ok"))
        pbo_ok = pbo is not None and pbo <= PBO_MAX
        noise_ok = noise is not None and noise >= RATIO_MIN
        exec_ok = execution is not None and execution >= RATIO_MIN
        gate2 = bool(wf_ok and pbo_ok and noise_ok and exec_ok)
        gate3 = bool(
            spread is not None
            and spread > 0.0
            and slip is not None
            and slip > 0.0
        )
        items.append(
            {
                "strategy_id": int(row["strategy_id"]),
                "campaign_id": campaign_id,
                "template": row.get("template"),
                "instrument": row.get("instrument"),
                "timeframe": row.get("timeframe"),
                "folds": result.get("n_folds"),
                "test_trades_median": result.get("test_trades_median"),
                "wf_tf_efficiency": _num(result.get("efficiency")),
                "wf_tf_stitched_sharpe": _num(result.get("stitched_sharpe")),
                "wf_tf_verdict": result.get("verdict", "Sin datos"),
                "wf_tf_reason": _verdict_reason(result),
                "wf_tf_ok": wf_ok,
                "wf_tf_frac_positive": _num(result.get("frac_positive")),
                "wf_tf_median_rank_pct": _num(result.get("median_rank_pct")),
                "wf_tf_stability": _num(result.get("stability")),
                "old_wf_efficiency": _num(row.get("wf_efficiency")),
                "old_wf_label": row.get("wf_label") or "informativo",
                "gate1": gate1,
                "pbo": pbo,
                "noise_ratio": noise,
                "exec_ratio": execution,
                "pbo_ok": pbo_ok,
                "noise_ok": noise_ok,
                "exec_ok": exec_ok,
                "gate2": gate2,
                "spread_p75_expectancy_r": spread,
                "slippage_plus_2_expectancy_r": slip,
                "gate3": gate3,
                "cost_r": _num((row.get("gate1_detail") or {}).get("cost_r")),
                "gate4": None,
                "gate4_reason": "",
                "four_gates": False,
            }
        )

    candidates = [
        item for item in items if item["gate1"] and item["gate2"] and item["gate3"]
    ]
    groups, edges = ([], [])
    if candidates:
        groups, edges = _correlation_groups(candidates, db_path)
        chosen = {group["chosen"] for group in groups}
        for item in candidates:
            if int(item["strategy_id"]) in chosen:
                item["gate4"] = True
                item["four_gates"] = True
            else:
                item["gate4"] = False
                item["gate4_reason"] = "cluster de correlacion > 0,7"
    for item in items:
        if item["gate4"] is None:
            item["gate4"] = False

    passed = [item for item in items if item["four_gates"]]
    return {
        "queue": queue,
        "label": config["label"],
        "generated": datetime.now(timezone.utc).isoformat(),
        "finalists": len(items),
        "campaigns": len({item["campaign_id"] for item in items}),
        "pass_gate1": sum(1 for item in items if item["gate1"]),
        "pass_gate2": sum(1 for item in items if item["gate2"]),
        "pass_gate3": sum(1 for item in items if item["gate3"]),
        "pass_four": len(passed),
        "candidates_four_gate_ids": [item["strategy_id"] for item in passed],
        "candidate": passed[0]["strategy_id"] if passed else None,
        "items": items,
        "groups": groups,
        "correlation_edges": edges,
    }


def _table_wf(items: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Estrategia | Campaña | Activo | TF | Pliegues | Mediana ops/ventana | "
        "WF-TF eff | WF-TF stitched | WF-TF veredicto | Motivo | WF viejo eff | WF viejo etiqueta |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for item in items:
        median = item.get("test_trades_median")
        median_text = "Sin datos" if median is None else f"{float(median):.1f}"
        lines.append(
            f"| {item['strategy_id']} | `{item['campaign_id']}` | "
            f"{item['instrument']} | {item['timeframe']} | "
            f"{item.get('folds') if item.get('folds') is not None else 'Sin datos'} | "
            f"{median_text} | {_fmt(item['wf_tf_efficiency'])} | "
            f"{_fmt(item['wf_tf_stitched_sharpe'])} | "
            f"{item['wf_tf_verdict']} | {item['wf_tf_reason']} | "
            f"{_fmt(item['old_wf_efficiency'])} | {item['old_wf_label']} |"
        )
    return lines


def _table_gates(items: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Estrategia | Campaña | TF | Gate 1 | PBO | Ruido | Ejec | WF-TF | "
        "Gate 2 | Gate 3 | Puerta 4 | 4 puertas |",
        "|---:|---|---|---:|---:|---:|---:|---|---|---|---|---|",
    ]
    for item in items:
        gate4 = "si" if item["gate4"] else "no"
        if item["gate4_reason"]:
            gate4 += f" ({item['gate4_reason']})"
        lines.append(
            f"| {item['strategy_id']} | `{item['campaign_id']}` | "
            f"{item['timeframe']} | {'si' if item['gate1'] else 'no'} | "
            f"{_fmt(item['pbo'])} | {_fmt(item['noise_ratio'])} | "
            f"{_fmt(item['exec_ratio'])} | {'si' if item['wf_tf_ok'] else 'no'} | "
            f"{'si' if item['gate2'] else 'no'} | {'si' if item['gate3'] else 'no'} | "
            f"{gate4} | {'SI' if item['four_gates'] else 'NO'} |"
        )
    return lines


def render_section(payload: dict[str, Any]) -> str:
    items = payload["items"]
    lines = [
        f"<!-- WF-TF:{payload['label']}:START -->",
        f"## {payload['label']} — {payload['finalists']} finalistas, "
        f"{payload['campaigns']} campañas",
        "",
        f"**Generado:** {payload['generated']}",
        f"**Pasan las 4 puertas con WF-TF:** {payload['pass_four']} de "
        f"{payload['finalists']}.",
        "",
        "### WF antiguo (60/20) frente a WF-TF",
        "",
        *_table_wf(items),
        "",
        "### Las 4 puertas",
        "",
        "Gate 1 y Gate 3 salen de la tabla ya calculada; PBO, ruido y ejecución "
        "no se recalculan. Gate 2 exige además WF-TF `ok` (eficiencia ≥ 0,3, "
        "`stitched_sharpe` > 0, ≥ 3 pliegues y el resto del veredicto).",
        "",
        *_table_gates(items),
        "",
        "### Puerta 4 — grupos de correlación",
        "",
    ]
    if not payload["groups"]:
        lines.append(
            "- Sin candidatos que pasen las puertas 1 a 3 con WF-TF: "
            "no hay grupos de correlación."
        )
    else:
        for group in payload["groups"]:
            ids = ", ".join(str(item) for item in group["strategy_ids"])
            lines.append(
                f"- Grupo [{ids}]: elegido **{group['chosen']}** "
                f"(menor `cost_r`; cost_r = {group['cost_r']})."
            )
        if payload["correlation_edges"]:
            lines.append("")
            lines.append("Pares con |correlación| > 0,7:")
            lines.append("")
            for edge in payload["correlation_edges"]:
                lines.append(
                    f"- {edge['a']} ↔ {edge['b']}: {edge['correlation']:.3f}"
                )
    lines.append("")
    if payload["candidate"] is not None:
        lines.append(f"> **{CANDIDATE_PHRASE}**")
        lines.append("")
    lines.append(f"<!-- WF-TF:{payload['label']}:END -->")
    return "\n".join(lines)


def _base_markdown() -> str:
    return (
        "# WF-TF — walk-forward con ventanas por timeframe\n"
        "\n"
        f"**Prerregistro aplicado:** `{PREREG['path']}`, commit "
        f"`{PREREG['commit']}`, SHA-256 `{PREREG['sha256']}` "
        "(comprobado antes de empezar).\n"
        "\n"
        "**Declaración (literal, COLA-WF-TF §1):**\n"
        "\n"
        f"> {DECLARATION}\n"
        "\n"
        "Una sola pasada por finalista, los mismos umbrales y ninguna lectura "
        "del OOS-2 ni llamada a `confirm`. El juez final sigue siendo el OOS-2.\n"
        "\n"
    )


def write_markdown(payload: dict[str, Any]) -> None:
    section = render_section(payload)
    if OUT_MD.exists():
        text = OUT_MD.read_text(encoding="utf-8")
    else:
        text = _base_markdown()
    start = f"<!-- WF-TF:{payload['label']}:START -->"
    end = f"<!-- WF-TF:{payload['label']}:END -->"
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _old, after = rest.split(end, 1)
        text = f"{before}{section}{after}"
    else:
        text = f"{text.rstrip()}\n\n{section}\n"
    OUT_MD.write_text(f"{text.rstrip()}\n", encoding="utf-8")


def write_json(payload: dict[str, Any]) -> None:
    if OUT_JSON.exists():
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    else:
        data = {
            "preregistration": PREREG,
            "declaration": DECLARATION,
            "queues": {},
        }
    data["generated"] = payload["generated"]
    data["queues"][payload["queue"]] = payload
    OUT_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Informe WF-TF")
    parser.add_argument("--queue", choices=sorted(QUEUES), required=True)
    parser.add_argument("--db", default=str(ROOT / "data" / "discovery.db"))
    args = parser.parse_args()
    config = QUEUES[args.queue]
    if not config["finalists"].exists():
        raise SystemExit(f"Sin datos: falta {config['finalists']}")
    if not config["eval"].exists():
        raise SystemExit(f"Sin datos: falta {config['eval']}")
    payload = build_queue(args.queue, Path(args.db))
    write_markdown(payload)
    write_json(payload)
    print(
        f"Escrito {OUT_MD} y {OUT_JSON}: {payload['label']} "
        f"{payload['pass_four']}/{payload['finalists']} pasan las 4 puertas",
        flush=True,
    )


if __name__ == "__main__":
    main()
