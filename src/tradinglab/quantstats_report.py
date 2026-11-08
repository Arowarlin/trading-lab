"""Informes QuantStats por propuesta frente a SPY. Solo lectura.

No cambia propuestas, criterios ni el estado de ningún bot. Si falta el
artefacto, SPY o QuantStats falla, devuelve Sin datos y no rompe research.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from .datacheck import find_cache

try:
    import quantstats as qs
except Exception:  # pragma: no cover - dependencia declarada
    qs = None


def artifact_returns(path: str | Path) -> pd.Series | None:
    source = Path(path)
    if not source.exists():
        return None
    try:
        frame = pd.read_parquet(source)
    except Exception:
        return None
    if "equity" not in frame.columns:
        return None
    returns = pd.to_numeric(frame["equity"], errors="coerce").pct_change().dropna()
    return returns if len(returns) > 1 else None


def benchmark_returns(
    cache_dir: str | Path,
    index: pd.Index,
    symbol: str = "SPY",
) -> pd.Series | None:
    path = find_cache(cache_dir, symbol)
    if path is None:
        return None
    try:
        frame = pd.read_parquet(path)
        frame.columns = [str(column).lower() for column in frame.columns]
        close = pd.to_numeric(frame["close"], errors="coerce")
    except Exception:
        return None
    returns = close.pct_change().dropna()
    aligned = returns.reindex(index).fillna(0.0)
    return aligned if len(aligned) > 1 else None


def write_reports(
    report: dict,
    out_dir: str | Path,
    cache_dir: str | Path,
    *,
    benchmark: str = "SPY",
) -> dict:
    proposals = report.get("proposals") or []
    if not proposals:
        return {"status": "Sin datos", "reason": "sin propuestas", "reports": []}
    if qs is None:
        return {
            "status": "Sin datos",
            "reason": "QuantStats no disponible",
            "reports": [],
        }
    root = Path(out_dir)
    target_dir = root / "quantstats"
    target_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for proposal in proposals:
        artifact = str(proposal.get("artifact") or "")
        if not artifact:
            continue
        returns = artifact_returns(root / artifact)
        if returns is None:
            continue
        bench = benchmark_returns(cache_dir, returns.index, benchmark)
        if bench is None:
            continue
        digest = hashlib.sha256(
            str(proposal.get("id") or artifact).encode("utf-8")
        ).hexdigest()[:12]
        target = target_dir / f"{digest}.html"
        try:
            qs.reports.html(
                returns,
                benchmark=bench,
                output=str(target),
                title=(
                    f"{proposal.get('symbol', '')} · "
                    f"{proposal.get('strategy', '')} · {proposal.get('params', {})}"
                ),
            )
        except Exception:
            continue
        relative = str(target.relative_to(root)).replace("\\", "/")
        proposal["quantstats_html"] = relative
        rows.append(
            {
                "proposal": proposal.get("id"),
                "symbol": proposal.get("symbol"),
                "path": relative,
                "benchmark": benchmark,
            }
        )
    if not rows:
        return {
            "status": "Sin datos",
            "reason": "sin artefactos/SPY válidos",
            "reports": [],
        }
    return {"status": "ok", "reports": rows}


__all__ = [
    "artifact_returns",
    "benchmark_returns",
    "write_reports",
]
