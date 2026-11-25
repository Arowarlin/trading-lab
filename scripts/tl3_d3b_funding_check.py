"""D3b · Comprobación del límite diario de FundingPips (sin tocar prop/)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(".")
REPORT = ROOT / "TL3_REPORTS" / "propfund_zero_edge.md"
MARKER = "## Aviso · FundingPips (D3b)"
SEED = 42
PATHS = 5_000
HORIZON = 180
RISKS = (0.0025, 0.005, 0.01)


def _d2():
    spec = importlib.util.spec_from_file_location(
        "tl3_d2_zero_edge", ROOT / "scripts" / "tl3_d2_zero_edge.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _check(
    phases,
    daily,
    *,
    legacy: bool,
    seed: int = SEED,
    n_paths: int = PATHS,
    horizon: int = HORIZON,
):
    rng = np.random.default_rng(seed)
    active = np.ones(n_paths, dtype=bool)
    bug = np.zeros(n_paths, dtype=bool)
    daily_any = np.zeros(n_paths, dtype=bool)
    total_any = np.zeros(n_paths, dtype=bool)

    for rules in phases:
        initial = float(rules.account_size)
        eff_daily = rules.effective_daily_limit_usd
        eff_max = rules.effective_max_loss_usd
        target = initial + rules.profit_target_usd
        limit = int(horizon)
        equity = np.full(n_paths, initial, dtype=float)
        breach_at = np.full(n_paths, -1, dtype=int)
        passed_at = np.full(n_paths, -1, dtype=int)
        total_floor = initial - eff_max

        for day in range(limit):
            draws = rng.choice(daily, size=n_paths, replace=True)
            day_start = equity.copy()
            equity = np.where(active, equity * (1.0 + draws), equity)

            if legacy:
                # Versión anterior a TL2-DIARIO 020b41b: balance inicial.
                daily_floor = np.maximum(initial, day_start) - eff_daily
            else:
                # Versión corregida: balance = equidad al inicio del día.
                daily_floor = day_start - eff_daily
            floor = np.maximum(daily_floor, total_floor)
            breached = active & (breach_at < 0) & (equity <= floor)

            # El día pierde menos del 5 % del balance de ese día y el límite
            # total tampoco se rompe: solo el suelo diario mal calculado lo marca.
            bug |= breached & (equity > day_start - eff_daily) & (equity > total_floor)
            daily_any |= breached & (equity <= daily_floor)
            total_any |= breached & (equity <= total_floor)

            breach_at[breached] = day
            hit_target = (
                active
                & (passed_at < 0)
                & (breach_at < 0)
                & (equity >= target)
                & (day + 1 >= int(rules.min_trading_days or 0))
            )
            passed_at[hit_target] = day
            if not active.any():
                break

        active = active & (passed_at >= 0)
        if not active.any():
            break

    return {
        "paths": n_paths,
        "bug": int(bug.sum()),
        "daily": int(daily_any.sum()),
        "total": int(total_any.sum()),
    }


def main() -> None:
    d2 = _d2()
    phases = d2._programs()["FundingPips 2-Step"]
    rows = []
    for b in (1, 2, 3):
        for risk in RISKS:
            daily = d2._returns(b, risk)
            before = _check(phases, daily, legacy=True)
            after = _check(phases, daily, legacy=False)
            rows.append({"b": b, "risk": risk, "before": before, "after": after})
            print(
                f"b={b} risk={risk:.2%} before_bug={before['bug']} "
                f"after_bug={after['bug']} after_daily={after['daily']}"
            )

    total_paths = sum(row["before"]["paths"] for row in rows)
    total_before = sum(row["before"]["bug"] for row in rows)
    total_after = sum(row["after"]["bug"] for row in rows)
    pct = 100.0 * total_before / total_paths
    confirmed = total_before > 0 and total_after == 0

    lines = [
        MARKER,
        "",
        "**Cifras de FundingPips no fiables: las 9 filas de D2 se calcularon con el "
        "error del simulador protegido `max(initial, day_start)`, ya corregido en "
        "TL2-DIARIO `020b41b`; ver COLA-TL3-D D3b y "
        "`TL3_REPORTS/tl2_diario_inventario.md §9`.**",
        "",
        "El código anterior usaba `np.maximum(initial, day_start) - eff_daily`, es "
        "decir, el balance **inicial**. La regla de `firms.yaml` es el mayor de "
        "balance o equidad **al inicio del día**. Así, quedar 5 % por debajo del "
        "balance inicial contaba como rotura diaria aunque la pérdida del día fuera "
        "menor. La versión actual usa `day_start - eff_daily` y no se toca `prop/`.",
        "",
        "Comprobación con los mismos 5.000 caminos y semilla 42 de D2, replicando "
        "el consumo del generador en ambas versiones:",
        "",
        "| b | Riesgo | Caminos afectados (antes) | Rotura diaria (antes) | "
        "Caminos afectados (actual) | Rotura diaria (actual) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['b']} | {row['risk']:.2%} | {row['before']['bug']} | "
            f"{row['before']['daily']} | {row['after']['bug']} | "
            f"{row['after']['daily']} |"
        )
    lines += [
        "",
        f"Agregado: **{total_before} de {total_paths}** caminos ({pct:.1f} %) "
        "rompen el diario en la versión anterior en un día cuya pérdida es menor "
        "que el 5 % del balance de ese día y sin romper el límite total. En la "
        f"versión actual: **{total_after} de {total_paths}**.",
        "",
        (
            "**Confirma el error de la versión anterior del simulador** para "
            "FundingPips; la versión corregida no lo reproduce."
            if confirmed
            else "No se confirma el error con la condición comprobada."
        ),
        "No se modifica `prop/` (Prop Fund protegido) y D2 no se reejecuta en D3b: "
        "su tabla queda como valores anteriores, marcados como no fiables.",
        "",
    ]
    text = REPORT.read_text(encoding="utf-8")
    if MARKER in text:
        text = text.split(MARKER)[0].rstrip() + "\n\n"
    REPORT.write_text(text + "\n".join(lines), encoding="utf-8")
    print(f"agregado antes {total_before}/{total_paths} ({pct:.1f} %) · "
          f"actual {total_after}/{total_paths} · {REPORT}")


if __name__ == "__main__":
    main()
