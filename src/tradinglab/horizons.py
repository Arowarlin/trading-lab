"""Matriz Monte Carlo por horizonte/exposición para el top de research.

No modifica criterios de propuesta: lee `latest.json` y los artefactos de
equity, ejecuta el simulador existente y escribe `horizons.json`/`horizons.md`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .prop.rules import PropRules, from_yaml
from .prop.simulator import monte_carlo

HORIZONS = (22, 44, 120)
EXPOSURES = (0.5, 1.0, 2.0)
DEFAULT_PATHS = 2_000
BLOCK_SIZE = 5
REQUIRED_HORIZON = 22
REQUIRED_PASS_RATE = 0.50
REQUIRED_MAX_BREACH = 0.15


def _firms() -> list[tuple[str, str, PropRules]]:
    return [
        (
            "ftmo",
            "FTMO 100k 2-step",
            from_yaml("ftmo", "challenge", 100_000),
        ),
        (
            "topstep",
            "Topstep 50K (plantilla, no activa)",
            from_yaml("topstep", "challenge", 50_000),
        ),
    ]


def load_top(report_dir: str | Path, top: int = 10) -> list[dict]:
    path = Path(report_dir) / "latest.json"
    if not path.exists():
        raise FileNotFoundError(f"no existe {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    return list(report.get("results") or [])[: max(1, top)]


def _returns_for(report_dir: Path, result: dict, exposure: float) -> np.ndarray | None:
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
    if len(equity) < 23:
        return None
    returns = equity.pct_change().dropna().to_numpy()
    returns = returns[np.isfinite(returns)]
    if returns.size == 0:
        return None
    return returns * exposure


def _returns_series(report_dir: Path, result: dict) -> pd.Series | None:
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
    return equity.pct_change().dropna()


def correlations(report_dir: str | Path, results: list[dict], *, threshold: float = 0.7) -> dict:
    """Matriz de correlación diaria entre variantes únicas (sin duplicar escalas)."""
    report_dir = Path(report_dir)
    series: dict[str, pd.Series] = {}
    seen: set[str] = set()
    for rank, result in enumerate(results, 1):
        key = json.dumps(
            [result.get("symbol"), result.get("strategy"), result.get("params")],
            sort_keys=True,
            ensure_ascii=False,
        )
        if key in seen:
            continue
        seen.add(key)
        values = _returns_series(report_dir, result)
        if values is None:
            continue
        label = f"#{rank} {result.get('symbol')} {result.get('strategy')} x{result.get('exposure', 1):g}"
        series[label] = values
    if len(series) < 2:
        return {"labels": [], "matrix": [], "high_pairs": [], "threshold": threshold}
    frame = pd.concat(series, axis=1, join="inner").dropna()
    if frame.empty:
        return {"labels": [], "matrix": [], "high_pairs": [], "threshold": threshold}
    matrix = frame.corr()
    labels = list(matrix.columns)
    high_pairs = []
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            value = float(matrix.loc[left, right])
            if abs(value) > threshold:
                high_pairs.append({"a": left, "b": right, "corr": value})
    high_pairs.sort(key=lambda item: abs(item["corr"]), reverse=True)
    return {
        "labels": labels,
        "matrix": [[round(float(value), 4) for value in row] for row in matrix.to_numpy()],
        "high_pairs": high_pairs,
        "threshold": threshold,
    }


def _row(result: dict, *, rank: int, exposure: float, horizon: int, mc: dict | None) -> dict:
    base = {
        "rank": rank,
        "id": result.get("id"),
        "symbol": result.get("symbol"),
        "strategy": result.get("strategy"),
        "params": result.get("params") or {},
        "exposure": exposure,
        "horizon": horizon,
        "num_trades": result.get("num_trades"),
        "status": "ok" if mc else "sin datos",
    }
    if mc:
        base.update(
            {
                "pass_rate": mc["pass_rate"],
                "breach_rate": mc["breach_rate"],
                "timeout_rate": mc["timeout_rate"],
                "median_days_to_pass": mc["median_days_to_pass"],
                "median_max_drawdown": mc["median_max_drawdown"],
                "mean_daily_return": mc["mean_daily_return"],
                "daily_volatility": mc["daily_volatility"],
            }
        )
    return base


def matrix(
    report_dir: str | Path = ROOT / "reports" / "research",
    *,
    top: int = 10,
    paths: int = DEFAULT_PATHS,
    horizons: tuple[int, ...] = HORIZONS,
    exposures: tuple[float, ...] = EXPOSURES,
    block_size: int = BLOCK_SIZE,
    seed: int = 42,
    include_required: bool = True,
) -> dict:
    report_dir = Path(report_dir)
    results = load_top(report_dir, top)
    firms = []
    for firm_id, firm_name, rules in _firms():
        variants = []
        for rank, result in enumerate(results, 1):
            item = {
                "rank": rank,
                "id": result.get("id"),
                "symbol": result.get("symbol"),
                "strategy": result.get("strategy"),
                "params": result.get("params") or {},
                "num_trades": result.get("num_trades"),
                "exposures": {},
            }
            for exposure in exposures:
                returns = _returns_for(report_dir, result, exposure)
                cells = {}
                for horizon in horizons:
                    if returns is None:
                        rows = [_row(result, rank=rank, exposure=exposure, horizon=horizon, mc=None)]
                        cells[str(horizon)] = rows[0]
                        continue
                    mc = monte_carlo(
                        rules,
                        returns,
                        n_paths=max(1, paths),
                        horizon=horizon,
                        block_size=block_size,
                        seed=seed,
                    )
                    cells[str(horizon)] = _row(
                        result,
                        rank=rank,
                        exposure=exposure,
                        horizon=horizon,
                        mc=mc,
                    )
                item["exposures"][f"{exposure:g}"] = cells
            variants.append(item)
        firms.append(
            {
                "id": firm_id,
                "name": firm_name,
                "rules": rules.describe(),
                "variants": variants,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top": len(results),
        "paths": paths,
        "block_size": block_size,
        "horizons": list(horizons),
        "exposures": list(exposures),
        "firms": firms,
        "correlations": correlations(report_dir, results),
        "required_22d": required_22d(report_dir, paths=max(2_000, paths))
        if include_required
        else {},
    }


def _required_for(
    rules: PropRules,
    *,
    paths: int,
    horizon: int = REQUIRED_HORIZON,
) -> list[dict]:
    sigma_grid = (0.005, 0.0075, 0.01, 0.015, 0.02, 0.03)
    mu_grid = tuple(round(x, 4) for x in np.arange(0.001, 0.0201, 0.001))
    rows = []
    for sigma in sigma_grid:
        selected = None
        for mu in mu_grid:
            sample = np.random.default_rng(42).normal(mu, sigma, size=6_000)
            mc = monte_carlo(
                rules,
                sample,
                n_paths=paths,
                horizon=horizon,
                block_size=1,
                seed=42,
            )
            if mc["pass_rate"] >= REQUIRED_PASS_RATE and mc["breach_rate"] < REQUIRED_MAX_BREACH:
                selected = {
                    "daily_return": float(mu),
                    "pass_rate": mc["pass_rate"],
                    "breach_rate": mc["breach_rate"],
                    "median_days_to_pass": mc["median_days_to_pass"],
                }
                break
        rows.append(
            {
                "daily_volatility": float(sigma),
                "daily_return": selected["daily_return"] if selected else None,
                "pass_rate": selected["pass_rate"] if selected else None,
                "breach_rate": selected["breach_rate"] if selected else None,
                "median_days_to_pass": selected["median_days_to_pass"] if selected else None,
            }
        )
    return rows


def required_22d(report_dir: str | Path, *, paths: int = 2_000) -> dict:
    return {
        "horizon": REQUIRED_HORIZON,
        "min_pass_rate": REQUIRED_PASS_RATE,
        "max_breach_rate": REQUIRED_MAX_BREACH,
        "assumption": (
            "retornos diarios iid normales, sin costes ni intradía; "
            "bootstrapping del simulador existente"
        ),
        "firms": [
            {
                "id": firm_id,
                "name": firm_name,
                "rules": rules.describe(),
                "rows": _required_for(rules, paths=paths),
            }
            for firm_id, firm_name, rules in _firms()
        ],
    }


def _pct(value) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def render_markdown(payload: dict) -> str:
    lines = [
        "# Monte Carlo por horizonte y exposición",
        "",
        f"- Generado: {payload['generated_at']}",
        f"- Top: {payload['top']} variantes por ranking",
        f"- Paths: {payload['paths']:,} · bloque {payload['block_size']} · "
        f"horizontes {', '.join(str(h) for h in payload['horizons'])} días",
        f"- Exposiciones: {', '.join(f'{x:g}×' for x in payload['exposures'])}",
        "",
        "> Solo informativo. No cambia criterios de propuesta ni activa bots. "
        "Aproximación con retornos diarios: el riesgo intradía real es mayor.",
        "",
    ]
    for firm in payload["firms"]:
        lines += [f"## {firm['name']}", "", f"Reglas: {firm['rules']}", ""]
        for exposure in payload["exposures"]:
            exp = f"{exposure:g}"
            headers = ["#", "Variante"] + [
                f"{horizon}d pasa / revienta" for horizon in payload["horizons"]
            ] + ["Trades"]
            lines += [
                f"### Exposición {exp}×",
                "",
                "| " + " | ".join(headers) + " |",
                "|" + "---|" * len(headers),
            ]
            for variant in firm["variants"]:
                label = (
                    f"{variant['symbol']} · {variant['strategy']} · "
                    f"{json.dumps(variant['params'], ensure_ascii=False, sort_keys=True)}"
                )
                cells = []
                for horizon in payload["horizons"]:
                    cell = variant["exposures"][exp][str(horizon)]
                    if cell["status"] != "ok":
                        cells.append("sin datos")
                    else:
                        cells.append(
                            f"{_pct(cell['pass_rate'])} / {_pct(cell['breach_rate'])}"
                        )
                lines.append(
                    f"| {variant['rank']} | {label} | " + " | ".join(cells)
                    + f" | {variant['num_trades']} |"
                )
            lines.append("")

    required = payload.get("required_22d") or {}
    corr = payload.get("correlations") or {}
    if corr.get("labels"):
        lines += [
            "## Correlación entre bots",
            "",
            f"Umbral de aviso: |correlación| > {corr.get('threshold', 0.7):.1f}.",
            "",
        ]
        if corr.get("high_pairs"):
            lines += ["| Bot A | Bot B | Correlación |", "|---|---|---|"]
            for pair in corr["high_pairs"]:
                lines.append(f"| {pair['a']} | {pair['b']} | {pair['corr']:.3f} |")
        else:
            lines.append("Ningún par supera el umbral de 0,7.")
        lines.append("")
    if required:
        lines += [
            "## Requerido para pasar en 22 días",
            "",
            f"Supuesto: pass ≥ {required['min_pass_rate']:.0%} y breach < "
            f"{required['max_breach_rate']:.0%}; {required['assumption']}.",
            "",
        ]
        for firm in required["firms"]:
            lines += [
                f"### {firm['name']}",
                "",
                "| Volatilidad diaria | Retorno diario mínimo | Retorno 22d aprox. | Pasa | Revienta | Días medianos |",
                "|---|---|---|---|---|---|",
            ]
            for row in firm["rows"]:
                mu = row["daily_return"]
                median = (
                    "—"
                    if row["median_days_to_pass"] is None
                    else f"{row['median_days_to_pass']:.0f}"
                )
                lines.append(
                    f"| {_pct(row['daily_volatility'])} | {_pct(mu)} | "
                    f"{_pct(None if mu is None else (1 + mu) ** 22 - 1)} | "
                    f"{_pct(row['pass_rate'])} | {_pct(row['breach_rate'])} | "
                    f"{median} |"
                )
    lines.append("")
    return "\n".join(lines)


def write(payload: dict, report_dir: str | Path) -> dict[str, str]:
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "horizons.json"
    md_path = out / "horizons.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


__all__ = [
    "DEFAULT_PATHS",
    "EXPOSURES",
    "HORIZONS",
    "load_top",
    "matrix",
    "required_22d",
    "render_markdown",
    "write",
]
