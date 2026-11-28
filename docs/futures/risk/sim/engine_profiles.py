"""Seis perfiles de riesgo A-F con el MOTOR REAL (prop_economics) en 3 programas 50K — investigación.

Ventajas HIPOTÉTICAS (pool sintético); no hay estrategia validada. Misma ventaja BRUTA en R para todos los
programas; cada uno descuenta sus comisiones verificadas + 1 tick por lado. Números aleatorios comunes
entre perfiles (misma matriz de días por programa y ventaja).

Uso: python -I docs/futures/risk/sim/engine_profiles.py --paths 4000 --out docs/futures/risk/sim/engine_profiles.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

from tradinglab.config import ROOT
from tradinglab.prop_economics.allocate import evaluate_grid, select
from tradinglab.prop_economics.policies import SizingPolicy
from tradinglab.prop_economics.pools import synthetic_pool
from tradinglab.prop_economics.project import ProjectConfig
from tradinglab.prop_economics.rules import load_program

PROGRAMS = {
    "topstep_50k_combine_xfa": {"cost_rt": 1.22 + 1.0, "assume": (), "processing": 3},
    "myfundedfutures_rapid_50k": {"cost_rt": 1.90 + 1.0,
                                  "assume": (("max_fraction_of_balance", 1.0), ("cap_per_payout", math.inf)),
                                  "processing": None},
    "lucid_flex_50k": {"cost_rt": 1.00 + 1.0, "assume": (("fees.evaluation", 125.0),), "processing": None},
}
EDGES = {"sin_ventaja": 0.0, "debil_+0.08R": 0.08, "moderada_+0.13R": 0.13, "solida_+0.20R": 0.20}
RISK_PER_MNQ = 50.0   # stop de 25 puntos


def profiles(rpc: float) -> list[tuple[str, SizingPolicy]]:
    return [
        ("A_conservador_250", SizingPolicy("fixed", rpc, risk_usd=250.0)),
        ("B_moderado_500", SizingPolicy("fixed", rpc, risk_usd=500.0)),
        ("C_agresivo_750", SizingPolicy("fixed", rpc, risk_usd=750.0)),
        ("D_muy_agresivo_1000", SizingPolicy("fixed", rpc, risk_usd=1000.0)),
        ("E_extremo_1500", SizingPolicy("fixed", rpc, risk_usd=1500.0)),
        ("F_adaptativo_colchon", SizingPolicy("cushion", rpc, kappa=0.3, r_max=1000.0)),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--budget", type=float, default=1500.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = []
    for pid, meta in PROGRAMS.items():
        prog = load_program(ROOT / "config" / "prop_economics" / "programs" / f"{pid}.yaml")
        rpc = RISK_PER_MNQ + meta["cost_rt"]
        cfg = ProjectConfig(contracts_eval=1, contracts_funded=1, budget=args.budget, start_date=date(2027, 1, 4),
                            assume_processing_days=meta["processing"], assume=meta["assume"])
        for edge_name, mu in EDGES.items():
            pool = synthetic_pool(mu_gross_r=mu, rr=1.5, risk_usd=RISK_PER_MNQ, cost_rt=meta["cost_rt"],
                                  n_days=1000, seed=args.seed)
            named = profiles(rpc)
            res = evaluate_grid(prog, pool, [p for _, p in named], cfg, n_paths=args.paths, seed=args.seed,
                                mean_block=1.0)
            for (label, _), r in zip(named, res):
                r.update(program=pid, edge=edge_name, mu_gross_r=mu, profile=label)
                rows.append(r)
            chosen = select(res)
            print(pid, edge_name, "→", None if chosen is None else chosen["policy"], flush=True)
    out = {"config": {"paths": args.paths, "seed": args.seed, "budget": args.budget, "stop_pts": 25, "rr": 1.5,
                      "programs": {k: {"cost_rt": v["cost_rt"], "assume": [list(a) for a in v["assume"]],
                                       "processing": v["processing"]} for k, v in PROGRAMS.items()}},
           "rows": rows}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
