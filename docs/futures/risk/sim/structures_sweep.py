"""Barrido MOD-NR / MOD-PR: ratio objetivo/stop (de 0,1 a 3,0) × riesgo por operación × ventaja neta.

Misma ventaja NETA en USD por operación para todas las estructuras, Topstep 50K Combine → XFA Standard,
4.000 caminos, 12 y 24 meses. Las ventajas son HIPOTÉTICAS (no hay estrategia validada).

Uso: python -I docs/futures/risk/sim/structures_sweep.py --out docs/futures/risk/sim/structures_sweep.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("risk_sim", Path(__file__).with_name("risk_sim.py"))
risk_sim = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(risk_sim)

RATIOS = (0.1, 0.2, 0.33, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
RISKS = (250.0, 500.0, 1000.0, 1500.0)
EDGES_USD = (0.0, 20.0, 40.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--budget", type=float, default=1500.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = []
    for edge in EDGES_USD:
        for risk in RISKS:
            for rr in RATIOS:
                res = risk_sim.run({"kind": "fixed", "risk": risk}, 0.0, n=args.paths, seed=args.seed,
                                   budget=args.budget, rr=rr, edge_usd=edge)
                m12, m24 = res["checkpoints"][252], res["checkpoints"][504]
                rows.append({
                    "edge_net_usd": edge, "risk_usd": risk, "rr": rr,
                    "module": "MOD-NR" if rr < 1.0 else "MOD-PR",
                    "win_net_usd": round(rr * risk - risk / risk_sim.STOP_PTS / risk_sim.MNQ_PT * risk_sim.COST_RT, 1),
                    "m12": {k: m12[k] for k in ("ev", "se", "median", "p5", "p95", "p_net_pos",
                                                 "p_one_payout_received", "payouts_received", "accounts_bought")},
                    "m24": {k: m24[k] for k in ("ev", "median", "p5", "p_net_pos", "p_budget_ruin",
                                                 "accounts_bought")},
                })
    Path(args.out).write_text(json.dumps({"config": {"program": "Topstep 50K", "paths": args.paths,
                                                     "seed": args.seed, "budget": args.budget,
                                                     "stop_pts": risk_sim.STOP_PTS, "cost_rt_mnq": risk_sim.COST_RT},
                                          "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
