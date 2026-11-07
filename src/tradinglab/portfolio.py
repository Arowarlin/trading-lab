"""Clústeres de correlación y presupuesto de riesgo por grupo.

Lee la matriz de `reports/research/horizons.json`. No ejecuta ni activa bots.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import ROOT
from .profiles import get_profile

DEFAULT_THRESHOLD = 0.70


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], a: int, b: int) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[rb] = ra


def build_clusters(payload: dict, *, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    corr = payload.get("correlations") or {}
    labels = list(corr.get("labels") or [])
    matrix = corr.get("matrix") or []
    if not labels or len(matrix) != len(labels):
        return []
    parent = list(range(len(labels)))
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            try:
                value = abs(float(matrix[i][j]))
            except (IndexError, TypeError, ValueError):
                continue
            if value > threshold:
                _union(parent, i, j)
    groups: dict[int, list[str]] = {}
    for i, label in enumerate(labels):
        groups.setdefault(_find(parent, i), []).append(label)
    profile = get_profile("swing_equity")
    risk_pct = profile.max_cluster_risk_pct if profile else 0.01
    out = []
    for members in groups.values():
        out.append(
            {
                "members": members,
                "size": len(members),
                "max_risk_pct": risk_pct,
                "note": (
                    "más de un bot del mismo clúster puede duplicar la misma apuesta"
                    if len(members) > 1
                    else "sin correlación alta con el resto"
                ),
            }
        )
    out.sort(key=lambda item: item["size"], reverse=True)
    return out


def load_clusters(
    report_dir: str | Path = ROOT / "reports" / "research",
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    path = Path(report_dir) / "horizons.json"
    if not path.exists():
        return {"threshold": threshold, "clusters": [], "source": str(path), "error": "sin horizons.json"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "threshold": threshold,
        "clusters": build_clusters(payload, threshold=threshold),
        "source": str(path),
        "generated_at": payload.get("generated_at"),
        "error": None,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Clústeres de correlación y presupuesto",
        "",
        f"- Fuente: {report['source']}",
        f"- Umbral: |correlación| > {report['threshold']:.2f}",
        "",
        "> Informativo. El guard de cuenta usa el límite de clúster por perfil; "
        "no activa bots.",
        "",
    ]
    if report.get("error"):
        lines.append(f"**Sin datos:** {report['error']}")
        return "\n".join(lines) + "\n"
    if not report["clusters"]:
        lines.append("Sin clústeres: no hay matriz de correlación.")
        return "\n".join(lines) + "\n"
    lines += [
        "| Clúster | Bots | Riesgo máx. | Nota |",
        "|---|---|---|---|",
    ]
    for i, cluster in enumerate(report["clusters"], 1):
        lines.append(
            f"| {i} | {'; '.join(cluster['members'])} | "
            f"{cluster['max_risk_pct']:.2%} | {cluster['note']} |"
        )
    return "\n".join(lines) + "\n"


def write(report: dict, out_dir: str | Path = ROOT / "reports" / "research") -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "clusters.json"
    md_path = out / "clusters.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


__all__ = [
    "DEFAULT_THRESHOLD",
    "build_clusters",
    "load_clusters",
    "render_markdown",
    "write",
]
