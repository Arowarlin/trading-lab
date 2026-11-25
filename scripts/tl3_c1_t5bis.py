"""TL3-C · C1: T5-bis rehecho con el conjunto exacto de T5."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROWS = Path("TL3_REPORTS/ai_trader_t5_rows.json")
OUT = Path("TL3_REPORTS/ai_trader_sim_vs_real.md")
SEED = 7
PATHS = 10_000
POINT = {"US100.cash": 0.01, "XAUUSD": 0.01, "GBPUSD": 1e-5, "USDJPY": 0.001}


def boot(values):
    values = np.asarray(values, float)
    rng = np.random.default_rng(SEED)
    means = np.array(
        [rng.choice(values, size=len(values), replace=True).mean() for _ in range(PATHS)]
    )
    return float(values.mean()), (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def main():
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    t5 = [row for row in rows if int(row["id"]) not in {52, 54}]
    df = pd.DataFrame(t5)
    aggregates = {
        "ia": float(df["ia"].mean()),
        "shadow": float(df["shadow"].mean()),
        "trend": float(df["trend"].mean()),
        "real": float(df["real_r"].mean()),
    }
    expected = {"ia": 0.2953, "shadow": 0.2594, "trend": 0.3179, "real": 0.0479}
    if any(abs(aggregates[key] - expected[key]) > 0.0001 for key in expected):
        raise SystemExit(f"bloqueado: conjunto de T5 no reproducible {aggregates}")

    df["sign"] = np.where(df["side"] == "buy", 1, -1)
    df["dist_sl"] = (df["real_entry"].astype(float) - df["real_sl"].astype(float)).abs()
    df["entry_r"] = (
        df["sign"] * (df["sim_entry"].astype(float) - df["real_entry"].astype(float))
        / df["dist_sl"]
    )
    df["gross_r"] = (
        df["sign"] * (df["real_exit"].astype(float) - df["real_entry"].astype(float))
        / df["dist_sl"]
    )
    df["real_cost"] = df["gross_r"] - df["real_r"].astype(float)
    df["model_cost"] = (
        (df["spread"].astype(float) + 1.0)
        * df["symbol"].map(POINT)
        / df["dist_sl"]
    )
    df["gap"] = df["real_r"].astype(float) - df["ia"].astype(float)
    df["rest"] = df["gap"] - df["entry_r"] - (df["real_cost"] - df["model_cost"])
    df["duration_s"] = (
        pd.to_datetime(df["real_exit_ts"], utc=True)
        - pd.to_datetime(df["ts"], utc=True)
    ).dt.total_seconds()
    df["possible_no_exec"] = (df["duration_s"] <= 5) & (df["pnl"].astype(float) == 0)

    def real_reason(row):
        if row["possible_no_exec"]:
            return "posible no ejecutada"
        point = POINT[row["symbol"]]
        tolerance = 2 * float(row["spread"]) * point
        if abs(float(row["real_exit"]) - float(row["real_tp"])) <= tolerance:
            return "TP"
        if abs(float(row["real_exit"]) - float(row["real_sl"])) <= tolerance:
            return "SL"
        forced = pd.Timestamp(row["forced"])
        exit_ts = pd.Timestamp(row["real_exit_ts"])
        if abs((exit_ts - forced).total_seconds()) <= 120:
            return "forzoso"
        return "otro"

    def sim_reason(row):
        dist_sl = float(row["dist_sl"])
        tp_dist = abs(float(row["real_tp"]) - float(row["real_entry"]))
        model_cost = (
            (float(row["spread"]) + 1.0)
            * POINT[row["symbol"]]
            / dist_sl
        )
        tp_target = tp_dist / dist_sl - model_cost
        sl_target = -1.0 - model_cost
        ia = float(row["ia"])
        if abs(ia - sl_target) <= 0.02:
            return "SL"
        if abs(ia - tp_target) <= 0.02:
            return "TP"
        return "forzoso"

    df["real_reason"] = df.apply(real_reason, axis=1)
    df["sim_reason"] = df.apply(sim_reason, axis=1)
    df["reason_match"] = df["real_reason"] == df["sim_reason"]

    def summary(frame):
        gap_mean, gap_ci = boot(frame["gap"])
        return {
            "n": int(len(frame)),
            "real": float(frame["real_r"].mean()),
            "ia": float(frame["ia"].mean()),
            "gap": gap_mean,
            "ci": gap_ci,
            "entry": float(frame["entry_r"].mean()),
            "cost": float((frame["real_cost"] - frame["model_cost"]).mean()),
            "rest": float(frame["rest"].mean()),
        }

    all_summary = summary(df)
    exec_summary = summary(df[~df["possible_no_exec"]])
    lines = [
        "# TL3-C · T5-bis rehecho: simulación vs ejecución real",
        "",
        "> Rehecho en TL3-C: la versión de 134f7c9 usó otro conjunto de 48;",
        "> ver COLA-TL3-C H-g. Este informe usa las 48 de T5 (todas menos #52 y #54).",
        "> D3b corrige solo la tabla de motivos y la conclusión; las cifras agregadas",
        "> de C1 y T5 no cambian.",
        "",
        f"Agregados de control: IA {aggregates['ia']:.4f}, gemela {aggregates['shadow']:.4f}, "
        f"tendencia {aggregates['trend']:.4f}, real {aggregates['real']:.4f}.",
        "",
        "## Resumen",
        "",
        "| Conjunto | n | R real | R sim | Gap | IC95 gap | Entrada | Costes | Salida/resto |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for label, item in (("Todas", all_summary), ("Sin posibles no ejecutadas", exec_summary)):
        lines.append(
            f"| {label} | {item['n']} | {item['real']:.4f} | {item['ia']:.4f} | "
            f"{item['gap']:+.4f} | [{item['ci'][0]:+.4f}; {item['ci'][1]:+.4f}] | "
            f"{item['entry']:+.4f} | {item['cost']:+.4f} | {item['rest']:+.4f} |"
        )
    lines += [
        "",
        "Las columnas Entrada + Costes + Salida/resto suman el gap.",
        "La definición de R real (`risk_usd`) no se puede aislar por contrato;",
        "queda dentro de Salida/resto.",
        "",
        "## Por símbolo y lado",
        "",
        "| Corte | n | Gap |",
        "|---|---:|---:|",
    ]
    for key in ("symbol", "side"):
        for value, group in df.groupby(key):
            lines.append(f"| {key}={value} | {len(group)} | {group['gap'].mean():+.4f} |")
    lines += ["", "## Motivos de salida", "", "| Real | Simulado | n |", "|---|---|---:|"]
    for (real, sim), group in df.groupby(["real_reason", "sim_reason"]):
        lines.append(f"| {real} | {sim} | {len(group)} |")
    opposite = df[
        df["real_reason"].isin(["TP", "SL"])
        & df["sim_reason"].isin(["TP", "SL"])
        & (df["real_reason"] != df["sim_reason"])
    ]
    lines += [
        "",
        f"Coincidencias de motivo: {int(df['reason_match'].sum())}/{len(df)}.",
        f"Posibles no ejecutadas: {int(df['possible_no_exec'].sum())} "
        f"({', '.join('#' + str(int(i)) for i in df.loc[df['possible_no_exec'], 'id']) or 'ninguna'}).",
        "",
        "## Gestión real y simulación",
        "",
        "La gestión real mueve el stop: `ai_trader.py:44` importa `trailing.next_stop`,",
        "`ai_trader.py:3080` llama a `broker.modify_position` y `execution/mt5.py:881`",
        "envía `TRADE_ACTION_SLTP`. La simulación de T5 usa SL/TP fijos. Las columnas",
        "`ai_trades.sl`/`tp` guardan el nivel **inicial**: se escriben al insertar la",
        "operación (`ai_trader.py:2042-2054`) y no se actualiza al mover el stop en el",
        "bróker, así que no refleja el último nivel.",
        "",
        "## Barreras opuestas real y simulado",
        "",
    ]
    if opposite.empty:
        lines.append("Ninguna.")
    else:
        lines += [
            "| ID | Símbolo | Real | Sim | R real | R sim | Salida | SL | TP |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for row in opposite.itertuples():
            lines.append(
                f"| {row.id} | {row.symbol} | {row.real_reason} | {row.sim_reason} | "
                f"{row.real_r:+.4f} | {row.ia:+.4f} | {row.real_exit:.5f} | "
                f"{row.real_sl:.5f} | {row.real_tp:.5f} |"
            )
    lines += [
        "",
        "## Mayores gaps",
        "",
        "| ID | Símbolo | Lado | Real | Sim | Gap | Entrada | Costes | Resto |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    top = df.reindex(df["gap"].abs().sort_values(ascending=False).index).head(10)
    for row in top.itertuples():
        lines.append(
            f"| {row.id} | {row.symbol} | {row.side} | {row.real_r:+.4f} | {row.ia:+.4f} | "
            f"{row.gap:+.4f} | {row.entry_r:+.4f} | "
            f"{(row.real_cost - row.model_cost):+.4f} | {row.rest:+.4f} |"
        )
    lines += [
        "",
        "## Conclusión",
        "",
        "La entrada es **favorable** (+0.0661 R) y los costes del modelo son pequeños",
        "(-0.0089 R). El gap está en la **salida y la trayectoria** (-0.3047 R), no en",
        "la entrada. La gestión real con stop móvil frente a la simulación con SL/TP",
        "fijos es una explicación estructural candidata, no una descomposición causal.",
        "Las cifras agregadas de C1 y T5 no cambian. No se modificó `ai_trader`.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
