"""Rejilla de políticas, selección con restricciones y escalera de evidencia (ORPAE §2.3-2.6) — FUT-O4.

Regla de decisión (risk/01 §5, sin cambios): maximizar el EV a 12 meses SUJETO A mediana > 0,
P(ruina del presupuesto a 24 m) ≤ ε y P(neto > 0) ≥ 60 %, con la ventaja en su COTA INFERIOR.
Empate → menor capital requerido (P95). Si nada cumple: no comprar.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .paths import DayPath, shift
from .policies import SizingPolicy
from .project import ProjectConfig, session_offsets, simulate_project
from .rules import Program
from .simulate import mean_block_length, stationary_bootstrap_indices

H12, H24 = 365, 730

# Escalera de evidencia (risk/01 §5): umbral de la cota inferior de la ventaja neta en R → peldaño.
LADDER = (
    (0.25, "E: riesgo de 1.000 USD si el escalado lo permite"),
    (0.15, "D: 500 USD por operación (E solo con más presupuesto)"),
    (0.08, "D: 500 USD por operación (25 % del MLL)"),
    (0.03, "no comprar todavía"),
)


def ladder_step(mu_lcb_r: float) -> str:
    """Peldaño de la escalera para una cota inferior de la ventaja neta en R."""
    if mu_lcb_r <= 0:
        return "no comprar evaluaciones (solo paper/forward)"
    for threshold, step in LADDER:
        if mu_lcb_r >= threshold:
            return step
    return "no comprar todavía"


def select(rows: list[dict], *, ruin_max: float = 0.10, p_pos_min: float = 0.60) -> dict | None:
    """Elige la política con mayor EV a 12 m que cumpla las restricciones; None = no comprar."""
    ok = [r for r in rows if r["median12"] > 0 and r["ruin24"] <= ruin_max and r["p_pos12"] >= p_pos_min]
    if not ok:
        return None
    return sorted(ok, key=lambda r: (-r["ev12"], r["cap_p95"]))[0]


def evaluate_grid(program: Program, pool: list[DayPath], policies: list[SizingPolicy], cfg: ProjectConfig, *,
                  n_paths: int, seed: int, delta: float = 0.0, mean_block: float | None = None) -> list[dict]:
    """Simula cada política con números aleatorios comunes (misma matriz de días) a 12 y 24 meses."""
    shifted = [shift(d, delta) for d in pool] if delta else list(pool)
    if mean_block is None:
        mean_block = mean_block_length(np.asarray([float(d.marks[-1]) for d in pool]))
    base_cfg = replace(cfg, horizons_days=(182, H12, H24))
    n_days = len(session_offsets(base_cfg.start_date, H24))
    idx = stationary_bootstrap_indices(len(pool), n_days, n_paths, mean_block, seed)
    rows = []
    for pol in policies:
        res = simulate_project(program, shifted, replace(base_cfg, sizing=pol), n_paths=n_paths, seed=seed, idx=idx)
        h6, h12, h24 = (res["horizons"][h] for h in (182, H12, H24))
        rows.append({"policy": pol.name, "ev6": h6["ev"], "ev12": h12["ev"], "se12": h12["se"],
                     "median12": h12["median"], "p5_12": h12["p5"], "p95_12": h12["p95"],
                     "p_pos12": h12["p_net_pos"], "p_payout12": h12["p_one_payout_received"],
                     "ev24": h24["ev"], "median24": h24["median"], "ruin24": h24["p_ruin"],
                     "accounts24": h24["accounts_bought"], "cap_p95": h24["capital_required_p95"]})
    return rows
