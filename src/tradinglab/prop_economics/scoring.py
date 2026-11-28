"""Ranking ponderado de firmas con evidencia (PFIE; FUT-P4). Un criterio sin verificar no puntúa.

Total = Σ peso·nota sobre los criterios con nota. Si falta alguno, la firma NO entra en el ranking
general: se informa el total parcial, el peso cubierto y el provisional (parcial / peso cubierto).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..config import ROOT

SCORES_PATH = ROOT / "config" / "prop_economics" / "scores_2026-11.yaml"


def score_firms(path: str | Path = SCORES_PATH) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    weights = data["weights"]
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("los pesos deben sumar 1")
    rows = []
    for firm, s in data["firms"].items():
        have = {k: s.get(k) for k in weights if s.get(k) is not None}
        covered = sum(weights[k] for k in have)
        partial = sum(weights[k] * have[k] for k in have)
        rows.append({"firm": firm, "plan": s.get("plan"), "covered_weight": round(covered, 10),
                     "partial": round(partial, 10), "complete": covered >= 1 - 1e-9,
                     "total": round(partial, 10) if covered >= 1 - 1e-9 else None,
                     "provisional": round(partial / covered, 10) if 0.5 <= covered < 1 - 1e-9 else None,
                     "missing": [k for k in weights if s.get(k) is None]})
    ranked = sorted((r for r in rows if r["complete"]), key=lambda r: -r["total"])
    return {"ranking": ranked, "not_ranked": [r for r in rows if not r["complete"]], "source": data.get("source")}
