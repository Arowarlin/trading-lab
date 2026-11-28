"""Varias cuentas a la vez: misma estrategia (correladas) frente a estrategias independientes — FUT-O5.

Modelo (risk/02 §2.5): ``k`` cuentas con el presupuesto repartido a partes iguales. Correladas = la misma
secuencia de días en todas (misma estrategia, mismos días: cuentan como UNA apuesta). Independientes =
secuencias distintas (estrategias con P&L diario sin correlación, que hay que medir en forward).
El EV total es el mismo; cambia la dispersión (mediana, P5, P(neto > 0)).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .paths import DayPath
from .project import ProjectConfig, session_offsets, simulate_project
from .rules import Program
from .simulate import mean_block_length, stationary_bootstrap_indices


def simulate_portfolio(program: Program, pool: list[DayPath], cfg: ProjectConfig, *, k: int, correlated: bool,
                       n_paths: int, seed: int, mean_block: float | None = None) -> dict:
    if k < 1:
        raise ValueError("k >= 1")
    if mean_block is None:
        mean_block = mean_block_length(np.asarray([float(d.marks[-1]) for d in pool]))
    sub = replace(cfg, budget=cfg.budget / k)
    n_days = len(session_offsets(cfg.start_date, max(cfg.horizons_days)))
    total: dict[int, np.ndarray] = {}
    for i in range(k):
        idx = stationary_bootstrap_indices(len(pool), n_days, n_paths, mean_block, seed if correlated else seed + 1000 * i)
        res = simulate_project(program, pool, sub, n_paths=n_paths, seed=seed, idx=idx)
        for h, net in res["net_paths"].items():
            total[h] = total.get(h, 0.0) + net
    out = {}
    for h, net in total.items():
        q = np.percentile(net, [5, 25, 50, 75, 95])
        out[h] = {"ev": float(net.mean()), "se": float(net.std(ddof=1) / np.sqrt(net.size)), "sd": float(net.std(ddof=1)),
                  "p5": float(q[0]), "median": float(q[2]), "p95": float(q[4]),
                  "p_net_pos": float((net > 0).mean()), "p_total_loss": float((net <= -cfg.budget * 0.999).mean())}
    return {"k": k, "correlated": correlated, "horizons": out, "net_paths": total}
