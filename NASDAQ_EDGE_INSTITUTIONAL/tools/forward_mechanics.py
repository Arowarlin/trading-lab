"""F3 · mecanica historica del forward (solo conteos, sin desenlaces).

Lee NQ CME 2010-2018 y Dukascopy 2019-2021, aplica las tres variantes
congeladas y cuenta senales, stops, bloqueos de noticias y NO TRADE por tamano.
No calcula P&L, expectativa, PF ni win rate.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ / "tools"))


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, PROJ / "tools" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pb = _load("phase_b", "phase_b.py")
fm = _load("forward_models", "forward_models.py")

DEV = {"NQ": "2018-12-31", "DUK": "2021-12-31"}
START = "2026-11-30"  # primera sesion NYSE completa tras el cierre de Thanks giving
COMMISSION_SIDE_USD = 0.75  # input del operador, 2026-11-25


def dev_rows() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    df = pb.load("NQ")
    rolls = pb.detect_rolls(df)
    excl = pb.roll_window_days(2010, 2026)
    for r in rolls:
        d0 = pd.Timestamp(r)
        for k in range(0, 4):
            excl.add(str((d0 + pd.Timedelta(days=k)).date()))
    out["NQ"] = pb.build(df, DEV["NQ"], excl)

    duk = pb.build(pb.load("DUK"), DEV["DUK"], set())
    out["DUK"] = [r for r in duk if r["day"].year >= 2019]
    return out


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def summarise(rows: list[dict], variant: str, fomc, tier1) -> dict:
    sessions = 0
    days_with: set = set()
    stops: list[float] = []
    counts = {"raw": 0, "fomc": 0, "tier1": 0, "after_news": 0, "after_cap": 0,
              "no_trade": 0, "target_lt": 0, "bad_stop": 0}
    by_year = defaultdict(lambda: {
        "sessions": 0, "days_with": 0, "raw": 0, "fomc": 0, "tier1": 0,
        "after_news": 0, "after_cap": 0, "stops": [], "no_trade": 0,
        "target_lt": 0, "bad_stop": 0,
    })
    for r in rows:
        if r["excluded"]:
            continue
        sessions += 1
        year = r["day"].year
        y = by_year[year]
        y["sessions"] += 1
        t = np.asarray(r["t"])
        kept = []
        for s in fm.signals_for(r, variant):
            counts["raw"] += 1
            y["raw"] += 1
            reason = fm.news_reason(str(r["day"]), s.entry_min, fomc, tier1)
            if reason == "fomc":
                counts["fomc"] += 1
                y["fomc"] += 1
                continue
            if reason is not None:
                counts["tier1"] += 1
                y["tier1"] += 1
                continue
            counts["after_news"] += 1
            y["after_news"] += 1
            j = int(np.searchsorted(t, s.entry_min))
            if j >= len(t):
                continue
            entry = float(r["o"][j])
            stop_pt = abs(entry - s.stop)
            if stop_pt < 2 * fm.TICK:
                counts["bad_stop"] += 1
                y["bad_stop"] += 1
                continue
            if s.target is not None and (s.target - entry) * s.side < stop_pt:
                counts["target_lt"] += 1
                y["target_lt"] += 1
                continue
            if fm.contracts_for_risk(stop_pt, COMMISSION_SIDE_USD) < 1:
                counts["no_trade"] += 1
                y["no_trade"] += 1
                continue
            kept.append((s, stop_pt))
        kept = kept[:3]
        counts["after_cap"] += len(kept)
        y["after_cap"] += len(kept)
        if kept:
            days_with.add(r["day"])
            y["days_with"] += 1
        for _, stop_pt in kept:
            stops.append(stop_pt)
            y["stops"].append(stop_pt)
    stop_arr = np.asarray(stops) if stops else np.asarray([np.nan])
    return {
        "variant": variant,
        "sessions": sessions,
        "days_with_signal": len(days_with),
        "pct_days_with_signal": _pct(len(days_with), sessions),
        "counts": counts,
        "stop_median_pt": round(float(np.nanmedian(stop_arr)), 2) if stops else None,
        "stop_p90_pt": round(float(np.nanpercentile(stop_arr, 90)), 2) if stops else None,
        "stop_median_ticks": round(float(np.nanmedian(stop_arr)) / fm.TICK, 1) if stops else None,
        "stop_p90_ticks": round(float(np.nanpercentile(stop_arr, 90)) / fm.TICK, 1) if stops else None,
        "by_year": {
            int(y): {
                "sessions": v["sessions"],
                "days_with_signal": v["days_with"],
                "pct_days": _pct(v["days_with"], v["sessions"]),
                "raw": v["raw"],
                "fomc": v["fomc"],
                "tier1": v["tier1"],
                "after_news": v["after_news"],
                "after_cap": v["after_cap"],
                "no_trade": v["no_trade"],
                "target_lt": v["target_lt"],
                "bad_stop": v["bad_stop"],
                "stop_median_pt": (
                    round(float(np.median(v["stops"])), 2) if v["stops"] else None
                ),
            }
            for y, v in sorted(by_year.items())
        },
    }


def main() -> None:
    fomc, tier1 = fm.load_news(PROJ)
    rows = dev_rows()
    prepared = {src: fm.prepare_sessions(r) for src, r in rows.items()}
    all_rows = prepared["NQ"] + prepared["DUK"]
    out = {
        "generated": pd.Timestamp.now(tz="UTC").isoformat(),
        "start": START,
        "commission_side_usd": COMMISSION_SIDE_USD,
        "variants": {},
    }
    for v in fm.VARIANTS:
        res = summarise(all_rows, v, fomc, tier1)
        res["estimate_n200_operations"] = _estimate(res)
        out["variants"][v] = res
        print(v, res["counts"], "senales/dia", round(res["counts"]["after_cap"] / res["sessions"], 3))
    (PROJ / "04_FORWARD").mkdir(exist_ok=True)
    (PROJ / "04_FORWARD/mecanica.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8"
    )
    write_report(out, fomc, tier1)


def _estimate(res: dict) -> dict:
    per_session = res["counts"]["after_cap"] / res["sessions"] if res["sessions"] else 0.0
    if per_session <= 0:
        return {"signals_per_session": 0, "sessions_needed": None, "weeks_needed": None, "estimated_date": None}
    sessions_needed = int(math.ceil(200 / per_session))
    weeks = sessions_needed / 5.0
    date = pd.Timestamp(START) + pd.Timedelta(days=int(round(weeks * 7)))
    return {
        "signals_per_session": round(per_session, 3),
        "sessions_needed": sessions_needed,
        "weeks_needed": round(weeks, 1),
        "estimated_date": str(date.date()),
    }


def _table(res: dict) -> list[str]:
    return [
        f"| {y} | {v['sessions']} | {v['days_with_signal']} | {v['pct_days']:.2f} % | "
        f"{v['raw']} | {v['fomc']} | {v['tier1']} | {v['after_news']} | {v['after_cap']} | "
        f"{v['no_trade']} | {v['target_lt']} | {v['bad_stop']} | "
        f"{'' if v['stop_median_pt'] is None else format(v['stop_median_pt'], ',.2f')} |"
        for y, v in res["by_year"].items()
    ]


def write_report(out: dict, fomc, tier1) -> None:
    lines = [
        "# Mecanica historica del forward (F3)",
        "",
        "Solo conteos: no se calculo P&L, expectativa, PF ni win rate. El corte por",
        "2 perdidas o -300 USD/dia necesita desenlaces y **no** se aplica aqui.",
        "",
        "Datos DEV: NQ CME 2010-2018 y Dukascopy 2019-2021. Sesiones completas,",
        "con los rolls de NQ excluidos. Ventana 9:35-11:30 ET; maximas 3 senales/dia.",
        "",
        "## Comision",
        "",
        "**0,75 USD por contrato y lado** (input del operador, 2026-11-25).",
        "La columna `NO TRADE` aplica la formula de contratos con esa comision y",
        "slippage de 1 tick por lado. El corte por 2 perdidas no se aplica (necesita",
        "desenlaces).",
        "",
    ]
    for v, res in out["variants"].items():
        c = res["counts"]
        lines += [
            f"## {v}",
            "",
            f"- Sesiones: {res['sessions']}; dias con senal: {res['days_with_signal']} "
            f"({res['pct_days_with_signal']:.2f} %).",
            f"- Senales brutas: {c['raw']}; bloqueadas por FOMC: {c['fomc']}; "
            f"por Tier 1: {c['tier1']}; tras noticias: {c['after_news']}.",
            f"- Tras el maximo de 3/dia: {c['after_cap']} senales. "
            f"Objetivo invalido (<1R): {c['target_lt']}; stop invalido: {c['bad_stop']}.",
            f"- Stop: mediana {res['stop_median_pt']} pt ({res['stop_median_ticks']} ticks); "
            f"p90 {res['stop_p90_pt']} pt ({res['stop_p90_ticks']} ticks).",
            f"- NO TRADE (comision 0,75): {c['no_trade']} "
            f"({_pct(c['no_trade'], c['after_news'])} % de las senales tras noticias).",
            f"- Estimacion de fecha para n=200 operaciones (tras NO TRADE; sin el corte por perdidas): "
            f"{res['estimate_n200_operations']['sessions_needed']} sesiones, "
            f"~{res['estimate_n200_operations']['weeks_needed']} semanas, "
            f"{res['estimate_n200_operations']['estimated_date']}, desde {START}.",
            "",
            "| Ano | Sesiones | Dias con senal | % dias | Brutas | FOMC | Tier1 | Tras noticias | Tras 3/dia | NO TRADE | <1R | Stop invalido | Stop mediana pt |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            *_table(res),
            "",
        ]
    lines += [
        "## Lectura",
        "",
        "- La fecha estimada es una **cota optimista**: descuenta el NO TRADE, pero no",
        "  el corte por 2 perdidas ni el -300 USD/dia, que necesitan desenlaces.",
        "- No se leyo ningun desenlace ni se calculo ningun resultado.",
        "",
    ]
    (PROJ / "04_FORWARD/mecanica.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
