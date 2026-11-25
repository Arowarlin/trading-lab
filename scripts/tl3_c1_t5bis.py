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
        if abs(float(row["real_exit"]) - float(row["real_tp"])) <= 2 * float(row["spread"]):
            return "TP"
        if abs(float(row["real_exit"]) - float(row["real_sl"])) <= 2 * float(row["spread"]):
            return "SL"
        forced = pd.Timestamp(row["forced"])
        exit_ts = pd.Timestamp(row["real_exit_ts"])
        if abs((exit_ts - forced).total_seconds()) <= 120:
            return "forzoso"
        return "otro"

    def sim_reason(row):
        tp_dist = abs(float(row["real_tp"]) - float(row["real_entry"]))
        if abs(float(row["ia"]) + 1.0) < 0.02:
            return "SL"
        if tp_dist > 0 and abs(float(row["ia"]) - tp_dist / float(row["dist_sl"])) < 0.05:
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
    lines += [
        "",
        f"Coincidencias de motivo: {int(df['reason_match'].sum())}/{len(df)}.",
        f"Posibles no ejecutadas: {int(df['possible_no_exec'].sum())} "
        f"({', '.join('#' + str(int(i)) for i in df.loc[df['possible_no_exec'], 'id']) or 'ninguna'}).",
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
        "El gap se concentra en la **entrada** y en la **salida/resto** (ejecución real",
        "frente a la apertura de la vela siguiente y cierre forzoso). Los costes del",
        "modelo no explican el gap. No se encontró un error en la simulación de T5 y",
        "no se modificó `ai_trader`.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
