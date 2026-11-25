"""D4 · Plan de potencia de ai_trader (no suma, no mira operaciones nuevas)."""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from tradinglab.discovery.calendars import NYSE_SPECIAL_CLOSURES, nyse_holidays
from tradinglab.tl3 import registry

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(".")
ROWS = ROOT / "TL3_REPORTS" / "ai_trader_t5_rows.json"
REPORT = ROOT / "TL3_REPORTS" / "ai_trader_power_plan.md"
DB = ROOT / "data" / "tl3" / "tl3_research.db"
MDE = 0.10
Z = 2.49
EVAL_ID = "H-2026-012"


def _nyse_days(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    closures = set(nyse_holidays(start.year, end.year))
    closures.update(NYSE_SPECIAL_CLOSURES)
    return [
        day
        for day in pd.bdate_range(start, end)
        if int(day.strftime("%Y%m%d")) not in closures
    ]


def _n_for(sd: float, mde: float = MDE) -> int:
    return int(math.ceil((Z * sd / mde) ** 2))


def _date_for(n: int, start: pd.Timestamp, rate: float) -> str:
    need = int(math.ceil((n - 48) / rate))
    days = _nyse_days(start + pd.Timedelta(days=1), start + pd.Timedelta(days=800))
    return days[need - 1].date().isoformat()


def _version_info(ids: list[int]) -> dict:
    con = sqlite3.connect(f"file:{ROOT / 'data' / 'lab.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in ids)
    playbooks = [
        dict(row)
        for row in con.execute(
            f"SELECT playbook_version, COUNT(*) AS n FROM ai_trades"
            f" WHERE id IN ({placeholders}) GROUP BY playbook_version",
            ids,
        )
    ]
    models = [
        dict(row)
        for row in con.execute(
            "SELECT model, COUNT(*) AS n FROM ai_decisions GROUP BY model"
        )
    ]
    registry_rows = [
        dict(row)
        for row in con.execute(
            "SELECT name, version, kind, symbol, status FROM model_registry"
            " ORDER BY id"
        )
    ]
    con.close()
    return {
        "playbooks": playbooks,
        "models": models,
        "model_registry": registry_rows,
    }


def _insert_hypothesis(stats: dict, dates: dict) -> str:
    with registry.connect(DB) as con:
        existing = con.execute(
            "SELECT created_at FROM hypotheses WHERE hypothesis_id=?", (EVAL_ID,)
        ).fetchone()
    if existing is not None:
        return str(existing["created_at"])
    structural = registry.structural_hash(
        "ai_trader_vs_trend",
        "cfd",
        "M5",
        {
            "n_eval": stats["n_eval"],
            "mde": MDE,
            "criterion": "delta>=0.10 & ci95>0",
            "bootstrap_seed": 7,
        },
    )
    registry.add_hypothesis(
        EVAL_ID,
        economic_rationale=(
            "La IA discrecional puede batir a la regla de tendencia; la evaluación "
            "única se fija antes de mirar más operaciones."
        ),
        behavior=(
            "Comparar ai_trader frente a la regla de tendencia con el script de T5, "
            "el criterio de TL3_AI_TRADER_AUDIT §5 y bootstrap semilla 7."
        ),
        refs="TL3_REPORTS/ai_trader_power_plan.md; TL3_AI_TRADER_AUDIT; COLA-TL3-D D4",
        market="cfd",
        instrument_class="cfd",
        timeframe="M5",
        entry="Operaciones cerradas de ai_trader en el forward, como las lee T5.",
        exit_rule="Cierre real de ai_trader (TP/SL/trailing/forzoso).",
        benchmark="Regla de tendencia de T5 (sesión anterior, 15:55 vs 09:30).",
        primary_metric="delta_ia_minus_trend_r",
        rejection_rule=(
            "La IA solo aporta si delta >= 0.10 R con IC95 > 0; n = "
            f"{stats['n_eval']}; bootstrap semilla 7."
        ),
        dev_window={"start": "2026-11-13", "end": "2026-11-25"},
        holdout_window={"start": "2026-11-26", "end": dates["n_eval"]},
        holdout_kind="out_of_period",
        structural=structural,
        status="draft",
        primary_params={
            "n_eval": stats["n_eval"],
            "n_delta_t": stats["n_dt"],
            "n_delta_g": stats["n_dg"],
            "n_real_r": stats["n_real"],
            "mde": MDE,
        },
        sigma=stats["sd_dt"],
        mde=MDE,
        db_path=DB,
    )
    with registry.connect(DB) as con:
        row = con.execute(
            "SELECT created_at FROM hypotheses WHERE hypothesis_id=?", (EVAL_ID,)
        ).fetchone()
    return str(row["created_at"])


def main() -> None:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    rows = [row for row in rows if int(row["id"]) not in {52, 54}]
    df = pd.DataFrame(rows)
    df["dt"] = df["ia"].astype(float) - df["trend"].astype(float)
    df["dg"] = df["ia"].astype(float) - df["shadow"].astype(float)
    df["dr"] = df["real_r"].astype(float) - df["ia"].astype(float)

    stats = {
        "n": len(df),
        "sd_dt": float(df["dt"].std(ddof=1)),
        "sd_dg": float(df["dg"].std(ddof=1)),
        "sd_dr": float(df["dr"].std(ddof=1)),
        "sd_real": float(df["real_r"].astype(float).std(ddof=1)),
        "mean_dt": float(df["dt"].mean()),
        "mean_dg": float(df["dg"].mean()),
        "mean_dr": float(df["dr"].mean()),
        "mean_real": float(df["real_r"].astype(float).mean()),
    }
    stats["n_dt"] = _n_for(stats["sd_dt"])
    stats["n_dg"] = _n_for(stats["sd_dg"])
    stats["n_real"] = _n_for(stats["sd_real"])
    stats["n_eval"] = int(math.ceil(stats["n_dt"] / 10.0) * 10)

    first = pd.Timestamp(df["ts"].min())
    last = pd.Timestamp(df["ts"].max())
    business_days = len(pd.bdate_range(first.normalize(), last.normalize()))
    rate = stats["n"] / business_days
    dates = {
        "n_dg": _date_for(stats["n_dg"], last, rate),
        "n_dt": _date_for(stats["n_dt"], last, rate),
        "n_eval": _date_for(stats["n_eval"], last, rate),
        "n_real": _date_for(stats["n_real"], last, rate),
    }

    versions = _version_info([int(row["id"]) for row in rows])
    created_at = _insert_hypothesis(stats, dates)

    playbook_text = ", ".join(
        f"{row['playbook_version']} ({row['n']} ops)" for row in versions["playbooks"]
    )
    model_text = ", ".join(
        f"{row['model'] or 'NULL'} ({row['n']})" for row in versions["models"]
    )
    registry_text = ", ".join(
        f"{row['name']} v{row['version']} ({row['kind']}, {row['symbol']})"
        for row in versions["model_registry"]
    )

    lines = [
        "# TL3-D · D4 Plan de potencia de `ai_trader`",
        "",
        "Fuente: las **48 operaciones de T5** (`ai_trader_t5_rows.json` sin los `id` "
        "52 y 54). No se miran operaciones nuevas y nada de este bloque suma al "
        "contador.",
        "",
        "## Series",
        "",
        "| Serie | Media | sd | n para MDE 0.10 R |",
        "|---|---:|---:|---:|",
        f"| Δ_t = IA − tendencia | {stats['mean_dt']:+.4f} | {stats['sd_dt']:.4f} | "
        f"**{stats['n_dt']}** |",
        f"| Δ_g = IA − gemela | {stats['mean_dg']:+.4f} | {stats['sd_dg']:.4f} | "
        f"**{stats['n_dg']}** |",
        f"| real − simulado (IA) | {stats['mean_dr']:+.4f} | {stats['sd_dr']:.4f} | "
        f"descriptivo |",
        f"| R real (frente a 0) | {stats['mean_real']:+.4f} | {stats['sd_real']:.4f} | "
        f"**{stats['n_real']}** |",
        "",
        "`n = ⌈(2.49 × sd / 0.10)²⌉`. La serie real − simulado se informa porque "
        "D3b la descompone; su n no se usa para la regla de evaluación.",
        "",
        "## Ritmo y fechas",
        "",
        f"- 48 operaciones entre **{first.date()}** y **{last.date()}**; "
        f"**{business_days} días hábiles** entre ambas fechas y **{rate:.2f} "
        "operaciones cerradas por día hábil**.",
        "- Solo 7 fechas tuvieron operaciones; el denominador de ritmo es el "
        "intervalo completo de días hábiles, como pide D4.",
        "",
        "| n | Motivo | Fecha estimada |",
        "|---:|---|---|",
        f"| {stats['n_dg']} | Δ_g | {dates['n_dg']} |",
        f"| {stats['n_dt']} | Δ_t | {dates['n_dt']} |",
        f"| {stats['n_eval']} | Δ_t redondeado a múltiplo de 10 | {dates['n_eval']} |",
        f"| {stats['n_real']} | R real frente a 0 | {dates['n_real']} |",
        "",
        "Fechas con el calendario NYSE (sin festivos) y el ritmo observado; son "
        "estimaciones, no un compromiso.",
        "",
        "## Versiones",
        "",
        f"- **Playbook:** {playbook_text}. Una sola versión en las 48.",
        f"- **Modelo/prompt:** **Sin datos**. `ai_trades` no guarda modelo ni prompt; "
        f"`ai_decisions.model` tiene {model_text}, pero no hay clave "
        "`proposal_id` que lo una a las 48 y el emparejamiento por hora/símbolo/"
        "entrada no encontró ninguna coincidencia.",
        f"- `model_registry` contiene {registry_text}: modelos ridge de acciones, "
        "no el modelo de `ai_trader`.",
        "- **Mezcla:** no hay mezcla de playbook; la del modelo no se puede "
        "estratificar. La evaluación única debe declarar esta limitación.",
        "",
        "## Regla fijada ahora",
        "",
        f"- La próxima evaluación de `ai_trader` se hace **una sola vez**, cuando el "
        f"número de operaciones cerradas alcance **{stats['n_eval']}** (n de Δ_t = "
        f"{stats['n_dt']}, redondeado hacia arriba a múltiplo de 10).",
        "- Se usan el script de T5 (`scripts/tl3_ai_counterfactual.py`), el criterio "
        "de `TL3_AI_TRADER_AUDIT` §5 (Δ ≥ 0.10 R con IC95 > 0) y el bootstrap con "
        "semilla 7.",
        "- Antes de ese n **no se mira**. La evaluación necesitará aprobación del "
        "operador y registro en el contador; no se ejecuta en esta cola.",
        "- Ninguna alerta cambia el EA, `ai_trader` ni el riesgo.",
        "",
        "## Hipótesis registrada",
        "",
        f"- `{EVAL_ID}` — «ai_trader frente a regla de tendencia, evaluación única "
        f"a n = {stats['n_eval']}», estado `draft`, `created_at` {created_at}.",
        "- `dev_window`: 2026-11-13 a 2026-11-25 (las 48). "
        f"`holdout_window`: 2026-11-26 a {dates['n_eval']} (estimada).",
        "- `sigma` = sd de Δ_t; `mde` = 0.10 R. No se calcula ningún resultado "
        "nuevo ni se toca `ai_trader`.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
