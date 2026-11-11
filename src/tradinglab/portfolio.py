"""Clústeres de correlación y presupuesto de riesgo por grupo.

Lee la matriz de `reports/research/horizons.json`. No ejecuta ni activa bots.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .horizons import HORIZONS
from .profiles import get_profile
from .prop.rules import from_yaml
from .prop.simulator import monte_carlo

DEFAULT_THRESHOLD = 0.70
DEFAULT_MAX_PER_CLUSTER = 2
DEFAULT_PER_BOT_RISK_PCT = 0.005


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


def _rank(label: str) -> int | None:
    match = re.match(r"#(\d+)", str(label))
    return int(match.group(1)) if match else None


def _returns_series_for(report_dir: Path, result: dict, exposure: float) -> pd.Series | None:
    artifact = result.get("artifact")
    if not artifact:
        return None
    root = report_dir.resolve()
    path = (root / str(artifact)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    try:
        frame = pd.read_parquet(path)
        equity = pd.to_numeric(frame["equity"], errors="coerce").dropna().astype(float)
    except Exception:
        return None
    if len(equity) < 3:
        return None
    returns = equity.pct_change().dropna() * float(exposure)
    return returns[returns.index.notna()]


def select_portfolio(
    report_dir: str | Path,
    *,
    top: int = 10,
    max_per_cluster: int = DEFAULT_MAX_PER_CLUSTER,
) -> dict:
    """Selecciona variantes respetando el presupuesto por clúster."""
    report_dir = Path(report_dir)
    latest_path = report_dir / "latest.json"
    horizons_path = report_dir / "horizons.json"
    if not latest_path.exists():
        raise FileNotFoundError(f"no existe {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    results = list(latest.get("results") or [])[: max(1, top)]
    if not horizons_path.exists():
        selected = results[: min(len(results), max_per_cluster)]
        return {
            "selected": [
                {"rank": i + 1, "cluster": "sin-correlacion", "result": row}
                for i, row in enumerate(selected)
            ],
            "clusters": [],
            "threshold": DEFAULT_THRESHOLD,
        }
    horizons = json.loads(horizons_path.read_text(encoding="utf-8"))
    clusters = build_clusters(horizons, threshold=DEFAULT_THRESHOLD)
    by_rank = {i + 1: row for i, row in enumerate(results)}
    selected = []
    for cluster in clusters:
        ranks = sorted(
            rank for rank in (_rank(label) for label in cluster["members"]) if rank
        )
        used = 0
        for rank in ranks:
            row = by_rank.get(rank)
            if row is None or not row.get("artifact"):
                continue
            selected.append({"rank": rank, "cluster": cluster["members"], "result": row})
            used += 1
            if used >= max_per_cluster:
                break
    if not selected:
        selected = [
            {"rank": i + 1, "cluster": "sin-correlacion", "result": row}
            for i, row in enumerate(results[:1])
        ]
    selected.sort(key=lambda item: item["rank"])
    return {
        "selected": selected,
        "clusters": clusters,
        "threshold": DEFAULT_THRESHOLD,
    }


def _metrics(returns: pd.Series) -> dict:
    equity = (1.0 + returns).cumprod()
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "sharpe": float(returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "days": int(len(returns)),
    }


def simulate(
    report_dir: str | Path = ROOT / "reports" / "research",
    *,
    top: int = 10,
    paths: int = 2_000,
    max_per_cluster: int = DEFAULT_MAX_PER_CLUSTER,
) -> dict:
    report_dir = Path(report_dir)
    selection = select_portfolio(report_dir, top=top, max_per_cluster=max_per_cluster)
    series = {}
    members = []
    for item in selection["selected"]:
        row = item["result"]
        returns = _returns_series_for(report_dir, row, float(row.get("exposure") or 1.0))
        if returns is None:
            continue
        label = f"#{item['rank']} {row.get('symbol')} {row.get('strategy')}"
        series[label] = returns
        members.append(
            {
                "rank": item["rank"],
                "label": label,
                "symbol": row.get("symbol"),
                "strategy": row.get("strategy"),
                "params": row.get("params") or {},
                "exposure": float(row.get("exposure") or 1.0),
                "num_trades": row.get("num_trades"),
                "cluster": item["cluster"],
                "weight": 1.0 / max(1, len(selection["selected"])),
            }
        )
    if not series:
        raise ValueError("no hay artefactos válidos para la cartera")
    frame = pd.concat(series, axis=1, join="inner").dropna()
    if frame.empty:
        raise ValueError("sin fechas comunes para la cartera")
    portfolio_returns = frame.mean(axis=1)
    weights = {label: 1.0 / len(frame.columns) for label in frame.columns}
    firms = [
        ("ftmo", "FTMO 100k 2-step", from_yaml("ftmo", "challenge", 100_000)),
        ("topstep", "Topstep 50K (plantilla, no activa)", from_yaml("topstep", "challenge", 50_000)),
    ]
    mc = []
    for firm_id, firm_name, rules in firms:
        for horizon in HORIZONS:
            sim = monte_carlo(
                rules,
                portfolio_returns.to_numpy(),
                n_paths=max(50, paths),
                horizon=horizon,
                block_size=5,
                seed=42,
            )
            mc.append(
                {
                    "firm_id": firm_id,
                    "firm": firm_name,
                    "horizon": horizon,
                    "pass_rate": sim["pass_rate"],
                    "breach_rate": sim["breach_rate"],
                    "timeout_rate": sim["timeout_rate"],
                    "median_days_to_pass": sim["median_days_to_pass"],
                }
            )
    single = None
    if series:
        first = next(iter(series))
        single = _metrics(pd.Series(series[first]).dropna())
    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": str(report_dir),
        "top": top,
        "max_per_cluster": max_per_cluster,
        "threshold": selection["threshold"],
        "members": members,
        "weights": weights,
        "portfolio": _metrics(portfolio_returns),
        "single_best": single,
        "monte_carlo": mc,
        "clusters": selection["clusters"],
    }


def render_simulation_markdown(payload: dict) -> str:
    lines = [
        "# Cartera simulada por clúster",
        "",
        f"- Fuente: {payload['source']}",
        f"- Top {payload['top']} · máx. {payload['max_per_cluster']} por clúster · umbral {payload['threshold']:.2f}",
        f"- Miembros: {len(payload['members'])} · equiponderada",
        "",
        "> Informativo. No activa bots ni cambia criterios. Retornos diarios, sin intradía.",
        "",
        "## Miembros",
        "",
        "| # | Variante | Clúster | Escala | Peso | Trades |",
        "|---|---|---|---|---|---|",
    ]
    for member in payload["members"]:
        cluster = member["cluster"]
        cluster_text = "; ".join(cluster) if isinstance(cluster, list) else str(cluster)
        lines.append(
            f"| {member['rank']} | {member['label']} | {cluster_text} | "
            f"{member['exposure']:g}× | {member['weight']:.1%} | {member['num_trades']} |"
        )
    p = payload["portfolio"]
    lines += [
        "",
        "## Cartera",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Retorno total | {p['total_return']:.1%} |",
        f"| Sharpe | {p['sharpe']:.2f} |",
        f"| MaxDD | {p['max_drawdown']:.1%} |",
        f"| Días | {p['days']} |",
        "",
        "## Monte Carlo",
        "",
        "| Firma | Horizonte | Pasa | Revienta | Timeout |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["monte_carlo"]:
        lines.append(
            f"| {row['firm']} | {row['horizon']}d | {row['pass_rate']:.1%} | "
            f"{row['breach_rate']:.1%} | {row['timeout_rate']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_simulation(
    payload: dict,
    out_dir: str | Path = ROOT / "reports" / "research",
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "portfolio.json"
    md_path = out / "portfolio.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(render_simulation_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


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
    "DEFAULT_MAX_PER_CLUSTER",
    "DEFAULT_PER_BOT_RISK_PCT",
    "DEFAULT_THRESHOLD",
    "build_clusters",
    "load_clusters",
    "render_markdown",
    "render_simulation_markdown",
    "select_portfolio",
    "simulate",
    "write",
    "write_simulation",
]


def account_vol_factor(
    returns_by_bot: dict[str, "pd.Series"],
    target_vol_annual: float | None,
    max_leverage: float = 2.0,
) -> float:
    """Segundo factor de cartera: la suma de los bots no supera el objetivo.

    `returns_by_bot` son los retornos diarios ya ponderados por la
    exposición de cada bot. Sin objetivo configurado devuelve 1,0.
    """
    from .vol_target import scale as vol_scale

    if not target_vol_annual:
        return 1.0
    series = [
        pd.Series(value, dtype=float)
        for value in (returns_by_bot or {}).values()
        if value is not None and len(value)
    ]
    if not series:
        return 1.0
    total = pd.concat(series, axis=1).fillna(0.0).sum(axis=1)
    factor = vol_scale(
        total,
        target_vol_annual=float(target_vol_annual),
        max_leverage=float(max_leverage),
        rebalance="W",
    )
    return float(factor.iloc[-1]) if len(factor) else 1.0
