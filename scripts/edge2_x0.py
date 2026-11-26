"""EDGE-2 Y0: diagnostico de huecos y costes de indices (solo lectura).

Genera TL3_REPORTS/edge2_costes.md y TL3_REPORTS/edge2_data.json.
No registra campanas, no ejecuta backtests y no toca engine.yaml.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery import calendars
from tradinglab.discovery import costs as discovery_costs
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.data_quality import _gap_analysis, check_dataset
from tradinglab.discovery.fetch_dukascopy import load_cache
from tradinglab.discovery.resample import resample_session
from tradinglab.discovery.source_quality import missing_weekdays, quality_config
from tradinglab.indicators import atr
from tradinglab.propfund.instruments import resolve

SYMBOLS = ["US100", "US500", "US30"]
ACCOUNTS = ["CFD-001", "CFD-006"]
TIMEFRAMES = ["M15", "M30", "H1", "H4"]
# Y0 demostro que 2018 tambien tiene huecos nocturnos reales de ~10 h.
DEFAULT_IS = {
    "M15": "2014-01-02",
    "M30": "2014-01-02",
    "H1": "2019-01-02",
    "H4": "2019-01-02",
}
IS_END = {"M15": "2019-12-31", "M30": "2019-12-31", "H1": "2020-12-31", "H4": "2020-12-31"}
OOS1 = ("2021-01-01", "2022-12-31")
SEGMENTS_DEFAULT = {
    "M15": ("2014-01-02", "2019-12-31"),
    "M30": ("2014-01-02", "2019-12-31"),
    "H1": ("2019-01-02", "2020-12-31"),
    "H4": ("2019-01-02", "2020-12-31"),
}
TEMPLATE_DIR = ROOT / "config" / "discovery" / "templates"
OUT_MD = ROOT / "TL3_REPORTS" / "edge2_costes.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "edge2_data.json"
Y1_TEMPLATES = [
    "trend_pullback_mtf",
    "vol_squeeze_breakout",
    "donchian_vol_h4",
    "st_reversal_idx",
]


def _pct(values, q):
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.percentile(clean, q)) if clean else None


def _spread_summary(account_cost):
    median = account_cost.spread.median_bps
    p75 = account_cost.spread.p75_bps
    return {
        "median_bps": _pct(list(median.values()), 50),
        "p75_bps": _pct(list(p75.values()), 50),
        "max_p75_bps": max(p75.values()) if p75 else None,
        "hours": len(p75),
        "by_hour_median_bps": {str(k): v for k, v in sorted(median.items())},
        "by_hour_p75_bps": {str(k): v for k, v in sorted(p75.items())},
    }


def _commission_side(account_cost, price):
    profile = account_cost.profile
    symbol = str(account_cost.instrument).upper()
    if profile.commission_type is None:
        return {"usd": None, "bps": None, "note": "Sin datos"}
    if profile.commission_type == "zero":
        return {"usd": 0.0, "bps": 0.0, "note": "cero"}
    if profile.commission_type != "per_lot_usd":
        return {"usd": None, "bps": None, "note": f"Sin datos ({profile.commission_type})"}
    per_round = float(profile.commission_value or 0.0)
    per_side = per_round * (0.5 if profile.commission_side == "round_turn" else 1.0)
    contract = resolve(symbol).contract_size
    if contract is None:
        return {"usd": per_side, "bps": None, "note": "Sin datos (contract_size)"}
    notional = float(price) * float(contract)
    return {"usd": per_side, "bps": per_side / notional * 10_000.0 if notional else None, "note": profile.commission_side}


def _swap_night(account_cost, price, stop_price):
    spec = account_cost.swap
    if spec is None:
        return {"cost_bps": None, "source": "Sin datos"}
    try:
        from tradinglab.discovery.swap_history import historical_swap_spec

        hist, reason = historical_swap_spec(account_cost.profile)
        entry = pd.Timestamp("2024-06-03 10:00", tz="UTC")
        exit_ = pd.Timestamp("2024-06-04 10:00", tz="UTC")
        long_r, source_long = hist.r_with_source(
            side="long", entry_price=price, risk_price=stop_price,
            entry_time=entry, exit_time=exit_, allow_credit=False,
        )
        short_r, source_short = hist.r_with_source(
            side="short", entry_price=price, risk_price=stop_price,
            entry_time=entry, exit_time=exit_, allow_credit=False,
        )
        cost_r = max(0.0, -min(float(long_r), float(short_r)))
        return {
            "cost_bps": cost_r * (stop_price / price) * 10_000.0,
            "source": source_long if source_long == source_short else "mixed",
            "reason": reason,
        }
    except Exception as exc:  # noqa: BLE001
        return {"cost_bps": None, "source": f"Sin datos ({type(exc).__name__})", "reason": str(exc)[:160]}


def _classify_gap(gap) -> str:
    year = int(gap["start_utc"].year)
    minutes = float(gap["minutes"])
    day = gap["start"].date()
    if year < 2018:
        return "noche Dukascopy pre-2018"
    if year == 2018:
        return "noche Dukascopy 2018"
    if calendars.is_holiday("nyse", day):
        return "festivo"
    if calendars.early_close_hhmm("nyse", day) is not None:
        return "cierre temprano"
    if 60 <= minutes <= 180 and gap["start"].strftime("%H:%M") in {"16:00", "16:15", "17:00"}:
        return "pausa diaria"
    return "hueco real"


def _gap_table(frame, tf, qconfig, symbol):
    minutes = {"M15": 15, "M30": 30, "H1": 60, "H4": 240}[tf]
    _sched, _ns, gaps, _cg, _out = _gap_analysis(
        frame,
        minutes,
        qconfig,
        pause_tz=qconfig.pause_tz,
        calendar="nyse",
        symbol=symbol,
        source="dukascopy",
    )
    per_year = defaultdict(list)
    for gap in gaps:
        per_year[int(gap["start_utc"].year)].append(
            {
                "minutes": float(gap["minutes"]),
                "class": _classify_gap(gap),
                "start": gap["start_utc"].isoformat(),
            }
        )
    rows = []
    for year, items in sorted(per_year.items()):
        classes = Counter(item["class"] for item in items)
        rows.append(
            {
                "year": year,
                "count": len(items),
                "median_minutes": float(np.median([item["minutes"] for item in items])),
                "max_minutes": max(item["minutes"] for item in items),
                "classes": dict(classes),
            }
        )
    return rows, len(gaps)


def main() -> None:
    engine = load_engine_config()
    records = []
    gap_records = []
    for symbol in SYMBOLS:
        print(f"[Y0] {symbol}", flush=True)
        m1 = load_cache(symbol)
        for tf in TIMEFRAMES:
            full_frame = resample_session(m1, tf)
            frame = full_frame
            if tf in {"H1", "H4"}:
                frame = frame[frame.index >= pd.Timestamp("2019-01-01", tz="UTC")]
            qconfig = quality_config(engine.data_quality, symbol, tf, "dukascopy")
            gap_rows, n_gaps = _gap_table(full_frame, tf, qconfig, symbol)
            for row in gap_rows:
                gap_records.append({"symbol": symbol, "timeframe": tf, **row})
            missing, _ = missing_weekdays(frame, tf)
            years = {
                str(int(year)): int(len(group))
                for year, group in frame.groupby(frame.index.year)
            }
            useful = pd.Timestamp(
                "2019-01-01" if tf in {"H1", "H4"} else "2014-01-02", tz="UTC"
            )
            if tf in {"H1", "H4"}:
                start = max(useful, pd.Timestamp("2019-01-02", tz="UTC"))
            else:
                usable = engine.data_quality.usable_from_for("dukascopy", symbol, tf)
                usable_ts = pd.Timestamp(usable, tz="UTC") if usable else useful
                start = max(useful, usable_ts)
            is_end = pd.Timestamp(IS_END[tf], tz="UTC")
            effective = {
                "is": (start.date().isoformat(), IS_END[tf]),
                "oos1": OOS1,
                "oos2": ("2023-01-01", "2026-11-24"),
            }
            report = check_dataset(
                frame, symbol, tf,
                segments={key: tuple(value) for key, value in effective.items()},
                config=qconfig, data_source="dukascopy",
            )
            is_frame = frame[(frame.index >= start) & (frame.index <= is_end)]
            atr_stop = 2.0 * atr(is_frame, 14) if len(is_frame) else pd.Series(dtype=float)
            median_atr = float(atr_stop.median()) if len(atr_stop.dropna()) else None
            median_price = float(is_frame["close"].median()) if len(is_frame) else None
            for account in ACCOUNTS:
                try:
                    account_cost = discovery_costs.build_account_cost(
                        account, symbol,
                        session_tz=engine.data_quality.tz_for(symbol),
                        cost_model_version=2,
                    )
                except Exception as exc:  # noqa: BLE001
                    records.append({
                        "symbol": symbol, "timeframe": tf, "status": report.status,
                        "rows": int(len(frame)), "useful_start": report.granularity.get("useful_start"),
                        "is_start_effective": start.date().isoformat(),
                        "non_scheduled_gaps": int(report.non_scheduled_gaps),
                        "non_scheduled_gaps_full": n_gaps, "missing_weekdays": int(missing),
                        "issues": list(report.issues), "years": years,
                        "median_atr14_is": median_atr, "median_price_is": median_price,
                        "account": account, "gaps": gap_rows,
                        "spread": {"median_bps": None, "p75_bps": None, "max_p75_bps": None},
                        "commission": {"usd": None, "bps": None, "note": str(exc)[:160]},
                        "swap": {"cost_bps": None, "source": "Sin datos"},
                        "components": {
                            "spread_median_bps": None, "spread_p75_bps": None,
                            "spread_max_p75_bps": None, "commission_side_bps": None,
                            "swap_night_bps": None, "slippage_side_bps": None,
                            "slippage_side_price": None, "commission_side_usd": None,
                        },
                    })
                    continue
                spread = _spread_summary(account_cost)
                commission = _commission_side(account_cost, median_price or 1.0)
                swap = _swap_night(account_cost, median_price or 1.0, median_atr or 1.0)
                slip_price = float(account_cost.assumed_slippage)
                slip_bps = slip_price / median_price * 10_000.0 if median_price else None
                records.append({
                    "symbol": symbol, "timeframe": tf, "status": report.status,
                    "rows": int(len(frame)), "useful_start": report.granularity.get("useful_start"),
                    "is_start_effective": start.date().isoformat(),
                    "non_scheduled_gaps": int(report.non_scheduled_gaps),
                    "non_scheduled_gaps_full": n_gaps, "missing_weekdays": int(missing),
                    "issues": list(report.issues), "years": years,
                    "median_atr14_is": median_atr, "median_price_is": median_price,
                    "account": account, "gaps": gap_rows,
                    "spread": spread, "commission": commission, "swap": swap,
                    "components": {
                        "spread_median_bps": spread["median_bps"],
                        "spread_p75_bps": spread["p75_bps"],
                        "spread_max_p75_bps": spread["max_p75_bps"],
                        "commission_side_usd": commission["usd"],
                        "commission_side_bps": commission["bps"],
                        "swap_night_bps": swap["cost_bps"],
                        "slippage_side_price": slip_price,
                        "slippage_side_bps": slip_bps,
                    },
                })
            print(f"  {tf}: {report.status} rows={len(frame)} gaps={n_gaps} start={start.date()}", flush=True)

    # Matriz de viabilidad para las plantillas de Y1.
    by_key = defaultdict(list)
    for item in records:
        by_key[(item["symbol"], item["timeframe"])].append(item)
    matrix = []
    for template in Y1_TEMPLATES:
        import yaml

        meta = yaml.safe_load((TEMPLATE_DIR / f"{template}.yaml").read_text(encoding="utf-8")) or {}
        valid = meta.get("valid_timeframes") or meta.get("timeframes") or []
        stop_mult = float(((meta.get("strategy") or {}).get("exit") or {}).get("stop", {}).get("mult") or 2.0)
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                if tf not in valid:
                    continue
                worst = None
                for item in by_key.get((symbol, tf), []):
                    comp = item["components"]
                    if None in (comp["spread_p75_bps"], comp["commission_side_bps"], comp["slippage_side_bps"]):
                        continue
                    stop = (item["median_atr14_is"] or 0.0) * stop_mult
                    price = item["median_price_is"] or 0.0
                    if stop <= 0 or price <= 0:
                        continue
                    total_bps = (
                        float(comp["spread_p75_bps"])
                        + 2.0 * float(comp["commission_side_bps"])
                        + 2.0 * float(comp["slippage_side_bps"])
                    )
                    cost_r = total_bps / 10_000.0 * price / stop
                    if worst is None or cost_r > worst["cost_r"]:
                        worst = {"account": item["account"], "cost_r": cost_r,
                                 "spread_p75_bps": comp["spread_p75_bps"],
                                 "median_atr14_is": item["median_atr14_is"]}
                if worst:
                    matrix.append({"template": template, "symbol": symbol, "timeframe": tf,
                                   "stop_mult": stop_mult, **worst,
                                   "viable": bool(worst["cost_r"] <= 0.10)})
    matrix.sort(key=lambda row: (not row["viable"], row["cost_r"]))

    OUT_JSON.write_text(json.dumps({"records": records, "gaps": gap_records, "matrix": matrix},
                                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        "# EDGE-2 Y0 - diagnostico de huecos y costes de indices",
        "",
        "Generado por `scripts/edge2_x0.py` (solo lectura). No se toco `engine.yaml`.",
        "",
        "## 1. Huecos H1/H4 frente a M15 (solo no programados)",
        "",
        "| Activo | TF | Ano | Huecos | Duracion mediana (min) | Duracion max (min) | Clases |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in gap_records:
        classes = ", ".join(f"{key}:{value}" for key, value in sorted(row["classes"].items()))
        lines.append(
            f"| {row['symbol']} | {row['timeframe']} | {row['year']} | {row['count']} | "
            f"{row['median_minutes']:.1f} | {row['max_minutes']:.1f} | {classes} |"
        )
    lines += [
        "",
        "**Conclusion literal:** no es un error del control. Los cientos de huecos de H1/H4 en 2015-2018 son",
        "noches sin datos de Dukascopy (~8-10 h); en 2018 persisten. Desde 2019-01-01 quedan 8 huecos en H1",
        "y 1 en H4 (0,017 % y 0,008 %), por debajo del umbral de fallo. Por eso H1/H4 empiezan **2019-01-02**",
        "y no 2018-01-02. M15/M30 empiezan en 2015-01-02 por `usable_from` (US100/US500/US30).",
        "",
        "**Enmienda Y1.1:** `intraday_momentum_close_v2` queda excluida del plan por el fallo de",
        "`fastbt._session_mask` con `flat_at` 15:55 en M15/M30/H1 (la posicion no se cierra en el dia).",
        "No se modifica `fastbt.py` en EDGE-2."
        "",
        "## 2. Costes por activo y TF",
        "",
        "Spread = mediana de medianas horarias y p75 de p75 horarias. Comision por lado. Swap = una noche",
        "con modelo `historical` (peor lado, sin credito). Slippage = supuesto de `engine.yaml`. Stop = 2x ATR(14).",
        "Cota enmendada de swap de indice: entre 0,8 y 7,3 bps/noche (1/3 a 3x la referencia CFD-006 ~2,44).",
        "",
        "| Activo | TF | Cuenta | Spread med (bps) | Spread p75 (bps) | Comision/lado (bps) | Swap/noche (bps) | Slippage/lado (bps) | ATR(14) | Coste R |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    def fmt(v, d=2):
        return "Sin datos" if v is None else f"{float(v):.{d}f}"
    for item in records:
        comp = item["components"]
        stop = (item["median_atr14_is"] or 0.0) * 2.0
        cost_r = "Sin datos"
        if None not in (comp["spread_p75_bps"], comp["commission_side_bps"], comp["slippage_side_bps"]) and stop > 0 and item["median_price_is"]:
            total = float(comp["spread_p75_bps"]) + 2.0 * float(comp["commission_side_bps"]) + 2.0 * float(comp["slippage_side_bps"])
            cost_r = f"{total / 10_000.0 * item['median_price_is'] / stop:.4f}"
        lines.append(
            f"| {item['symbol']} | {item['timeframe']} | {item['account']} | "
            f"{fmt(comp['spread_median_bps'])} | {fmt(comp['spread_p75_bps'])} | "
            f"{fmt(comp['commission_side_bps'])} | {fmt(comp['swap_night_bps'])} | "
            f"{fmt(comp['slippage_side_bps'])} | {fmt(item['median_atr14_is'])} | {cost_r} |"
        )
    lines += ["", "## 3. Cotas y bloqueos", ""]
    for symbol in SYMBOLS:
        values = [item["swap"]["cost_bps"] for item in records if item["symbol"] == symbol and item["swap"].get("cost_bps") is not None]
        if values:
            detail = ", ".join(f"{v:.2f}" for v in values)
            ok = all(0.8 <= float(v) <= 7.3 for v in values)
            lines.append(f"- Swap {symbol}: {'PASA' if ok else 'BLOQUEADO'} ({detail} bps/noche).")
        else:
            lines.append(f"- Swap {symbol}: Sin datos.")
    us100_spreads = [item["components"]["spread_median_bps"] for item in records if item["symbol"] == "US100" and item["components"]["spread_median_bps"] is not None]
    if us100_spreads:
        ok = all(0.3 <= float(v) <= 3.0 for v in us100_spreads)
        lines.append(f"- Spread US100 0,3-3 bps: {'PASA' if ok else 'BLOQUEADO'} ({', '.join(f'{v:.2f}' for v in us100_spreads)}).")
    lines.append("- US30: spread Sin datos en `broker_spreads` y en `costs.measured.yaml`; **Sin datos**, queda fuera.")
    lines += ["", "## 4. Viabilidad Y1 (cost_r <= 0,10)", ""]
    viable = [row for row in matrix if row["viable"]]
    lines.append(f"Combinaciones viables: **{len(viable)}** de **{len(matrix)}**.")
    lines += ["", "| Plantilla | Activo | TF | cost_r | Cuenta peor |", "|---|---|---|---:|---|"]
    for row in matrix[:80]:
        lines.append(f"| {row['template']} | {row['symbol']} | {row['timeframe']} | {row['cost_r']:.4f} | {row['account']} |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Escrito {OUT_MD} y {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
