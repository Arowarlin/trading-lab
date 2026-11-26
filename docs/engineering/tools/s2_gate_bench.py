"""ENG-S2 · Banco sintético de puertas: falsos positivos y potencia, actual frente a propuesta.

Sin datos de mercado, sin bases de datos y sin contador de pruebas: todo son
series sintéticas en memoria. Usa las funciones reales del laboratorio
(``cscv_pbo``, ``walk_forward``, ``dsr_from_returns``) con los umbrales vigentes
de ``engine.yaml`` (WF 60/20, eficiencia >= 0,3, stitched > 0, PBO <= 0,30,
OOS-2 >= 30 operaciones y DSR >= 0,90).

Modelo de una campaña (supuestos declarados, no medidos):
- N = 440 estrategias; cada día hábil operan con probabilidad ``p`` y su R neto
  por operación es Normal(mu, 1). Ruido: mu = -coste. Con ventaja: ``n_edge``
  estrategias con mu = ventaja neta; el resto, ruido.
- IS 5 años, OOS-1 3 años, OOS-2 3 años (252 días por año).
- "GA" = frontier de las K = 40 mejores por expectativa IS.

Cadena ACTUAL (aproximada; no incluye las puertas 1 y 3, ni el baseline aleatorio):
1. Finalistas: del frontier, OOS-1 con expectativa > 0 y PF > 1,1; los 5 mejores.
2. Puerta 2: WF sobre la matriz IS del frontier y PBO sobre el frontier (D-01, D-02).
3. Confirmación OOS-2: >= 30 operaciones, neto > 0 y DSR >= 0,90, con la dispersión
   de los finalistas en IS+OOS-1 y N = k (D-03); con k = 1, PSR contra 0.

Cadena PROPUESTA (STATS_REDESIGN.md):
1. Finalistas como arriba, pero con >= ``n_min`` operaciones en OOS-1 (E-02).
2. Puerta 2: WF y PBO sobre una muestra aleatoria fija de 200 de la población (D-01, D-02),
   con ventanas WF acordes a la frecuencia (por defecto 504/126, las de D1 en el
   prerregistro WF-TF: unas 12 operaciones por ventana de prueba con p = 0,1).
3. Confirmación OOS-2: >= 30 operaciones, neto > 0 y PSR contra 0 >= 1 - 0,05/m
   (Bonferroni sobre las lecturas del OOS-2). Los finalistas se eligieron antes de
   ver el OOS-2, así que se corrige por cuántos se leen ahí (m), no por la población.
   ``propuesta`` usa m = finalistas de la campaña; ``propuesta_m100`` usa m = 100
   (corrección conjunta del programa, más estricta).

Nota: una primera versión usaba el DSR con N = 440 en el OOS-2. Deflactaba de más
(potencia ~0 incluso con 0,3 R) y se descartó.

Mide, por escenario: P(al menos un finalista pasa todo) y, con ventaja, P(pasa uno
que tiene ventaja de verdad).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from tradinglab.stats import dsr_from_returns, period_sharpe  # noqa: E402
from tradinglab.validation import cscv_pbo  # noqa: E402
from tradinglab.walkforward import walk_forward  # noqa: E402

DAYS = 252
N, K, FINALISTS = 440, 40, 5
PBO_MAX, DSR_MIN, MIN_OOS2 = 0.30, 0.90, 30
WF_TRAIN, WF_TEST = 60, 20


def campaign(rng, *, p, cost, edge, n_edge, years=(5, 3, 3)):
    t = [y * DAYS for y in years]
    total = sum(t)
    active = rng.random((total, N)) < p
    mu = np.full(N, -cost)
    edge_idx = np.arange(n_edge)
    mu[edge_idx] = edge
    r = np.where(active, rng.normal(0.0, 1.0, (total, N)) + mu, 0.0)
    a, b = t[0], t[0] + t[1]
    return r[:a], r[a:b], r[b:], active[:a], active[a:b], active[b:], set(edge_idx.tolist())


def _exp_pf(series, act):
    trades = series[act]
    if len(trades) == 0:
        return None, None, 0
    gains = trades[trades > 0].sum()
    losses = -trades[trades < 0].sum()
    pf = float("inf") if losses == 0 else gains / losses
    return float(trades.mean()), pf, int(len(trades))


def _wf_ok(matrix, train=WF_TRAIN, test=WF_TEST):
    try:
        wf = walk_forward(matrix, train_len=train, test_len=test)
    except ValueError:
        return False
    return wf.verdict(min_stitched_sharpe=0.0, min_efficiency=0.3) == "ok"


def _pbo_ok(matrix, seed):
    try:
        return cscv_pbo(matrix, n_slices=16, max_combinations=300, seed=seed).pbo <= PBO_MAX
    except Exception:  # noqa: BLE001
        return False


def evaluate(rng, seed, *, p, cost, edge, n_edge, n_min, wf_windows=(504, 126)):
    is_r, o1_r, o2_r, is_a, o1_a, o2_a, edges = campaign(rng, p=p, cost=cost, edge=edge, n_edge=n_edge)
    is_exp = np.array([(is_r[:, j][is_a[:, j]].mean() if is_a[:, j].any() else -np.inf) for j in range(N)])
    frontier = np.argsort(-is_exp)[:K]
    sample = rng.choice(N, 200, replace=False)

    def finalists(min_trades):
        rows = []
        for j in frontier:
            e, pf, n = _exp_pf(o1_r[:, j], o1_a[:, j])
            if e is None or e <= 0 or pf <= 1.1 or n < min_trades:
                continue
            rows.append((e, j))
        rows.sort(reverse=True)
        return [j for _e, j in rows[:FINALISTS]]

    out = {}
    for chain in ("actual", "propuesta", "propuesta_m100"):
        fin = finalists(0 if chain == "actual" else n_min)
        if chain == "actual":
            gate2 = _wf_ok(is_r[:, frontier]) and _pbo_ok(is_r[:, frontier], seed)
        else:
            gate2 = _wf_ok(is_r[:, sample], *wf_windows) and _pbo_ok(is_r[:, sample], seed)
        passed = []
        if fin and gate2:
            if chain == "actual":
                dev = np.vstack([is_r, o1_r])
                trial_srs = [period_sharpe(dev[:, j]) for j in fin]
                n_trials = len(fin)
            else:
                trial_srs, n_trials = [], 1
                m = len(fin) if chain == "propuesta" else 100
                level = 1.0 - 0.05 / m
            for j in fin:
                e2, _pf2, n2 = _exp_pf(o2_r[:, j], o2_a[:, j])
                if e2 is None or n2 < MIN_OOS2 or e2 <= 0:
                    continue
                if chain != "actual":
                    psr = dsr_from_returns(o2_r[:, j], [], n_trials=1, periods_per_year=252.0, benchmark_sr=0.0)
                    if (psr.get("dsr") or 0.0) >= level:
                        passed.append(j)
                    continue
                if len(fin) == 1:
                    dsr = dsr_from_returns(o2_r[:, j], [], n_trials=1, periods_per_year=252.0, benchmark_sr=0.0)
                else:
                    dsr = dsr_from_returns(o2_r[:, j], trial_srs, n_trials=n_trials, periods_per_year=252.0)
                if (dsr.get("dsr") or 0.0) >= DSR_MIN:
                    passed.append(j)
        out[chain] = {"any": bool(passed), "true": bool(set(passed) & edges)}
    return out


def run(reps, seed, n_min, p, cost, wf_windows=(504, 126)):
    scenarios = [("ruido", 0.0, 0)] + [(f"ventaja {v:.1f} R", v, 5) for v in (0.1, 0.2, 0.3)]
    rng = np.random.default_rng(seed)
    table = {}
    for name, edge, n_edge in scenarios:
        counts = {c: {"any": 0, "true": 0} for c in ("actual", "propuesta", "propuesta_m100")}
        for rep in range(reps):
            res = evaluate(
                rng, seed + rep, p=p, cost=cost, edge=edge, n_edge=n_edge, n_min=n_min,
                wf_windows=wf_windows,
            )
            for c in counts:
                counts[c]["any"] += res[c]["any"]
                counts[c]["true"] += res[c]["true"]
        table[name] = {c: {k: v / reps for k, v in counts[c].items()} for c in counts}
    return table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--n-min", type=int, default=30)
    parser.add_argument("--p", type=float, default=0.10, help="probabilidad de operar cada día")
    parser.add_argument("--cost", type=float, default=0.05, help="coste en R por operación")
    parser.add_argument("--wf-train", type=int, default=504)
    parser.add_argument("--wf-test", type=int, default=126)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    table = run(args.reps, args.seed, args.n_min, args.p, args.cost, (args.wf_train, args.wf_test))
    text = json.dumps({"args": vars(args), "table": table}, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
