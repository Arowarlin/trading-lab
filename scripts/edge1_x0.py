"""EDGE-1 X0: cobertura de datos y tabla de costes (solo lectura).

Genera TL3_REPORTS/edge1_costes.md y TL3_REPORTS/edge1_data.json.
No registra campanas, no ejecuta backtests y no toca engine.yaml.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.config import ROOT
from tradinglab.discovery import costs as discovery_costs
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.data_quality import check_dataset
from tradinglab.discovery.fetch_dukascopy import load_cache
from tradinglab.discovery.resample import resample_session
from tradinglab.discovery.source_quality import missing_weekdays, quality_config
from tradinglab.indicators import atr
from tradinglab.propfund.costs import load_profile
from tradinglab.propfund.instruments import resolve

SYMBOLS = ["US100", "US500", "US30", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
ACCOUNTS = ["CFD-001", "CFD-006"]
TIMEFRAMES = ["M15", "M30", "H1", "H4"]
IS_START = pd.Timestamp("2012-01-01", tz="UTC")
IS_END = pd.Timestamp("2019-12-31 23:59:59", tz="UTC")
SEGMENTS = {
    "is": ("2012-01-01", "2019-12-31"),
    "oos1": ("2020-01-01", "2022-12-31"),
    "oos2": ("2023-01-01", "2026-11-24"),
}
TEMPLATE_DIR = ROOT / "config" / "discovery" / "templates"
OUT_MD = ROOT / "TL3_REPORTS" / "edge1_costes.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "edge1_data.json"


def _pct(values: list[float], q: float) -> float | None:
    clean = [float(value) for value in values if value is not None and np.isfinite(value)]
    return float(np.percentile(clean, q)) if clean else None


def _spread_summary(account_cost) -> dict:
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


def _commission_side(account_cost, price: float) -> dict:
    profile = account_cost.profile
    symbol = str(account_cost.instrument).upper()
    if profile.commission_type is None:
        return {"usd": None, "bps": None, "note": "Sin datos (tipo de comision)"}
    if profile.commission_type == "zero":
        return {"usd": 0.0, "bps": 0.0, "note": "cero"}
    if profile.commission_type != "per_lot_usd":
        return {
            "usd": None,
            "bps": None,
            "note": f"Sin datos (tipo {profile.commission_type})",
        }
    per_round = float(profile.commission_value or 0.0)
    per_side = per_round * (0.5 if profile.commission_side == "round_turn" else 1.0)
    contract = resolve(symbol).contract_size
    if contract is None:
        return {
            "usd": per_side,
            "bps": None,
            "note": "Sin datos (contract_size de indice)",
        }
    notional = float(price) * float(contract)
    return {
        "usd": per_side,
        "bps": (per_side / notional * 10_000.0) if notional > 0 else None,
        "note": profile.commission_side,
    }


def _swap_night(account_cost, price: float, stop_price: float) -> dict:
    spec = account_cost.swap
    if spec is None:
        return {"long_r": None, "short_r": None, "cost_bps": None, "source": "Sin datos"}
    try:
        from tradinglab.discovery.swap_history import historical_swap_spec

        hist, reason = historical_swap_spec(account_cost.profile)
        entry = pd.Timestamp("2024-06-03 10:00", tz="UTC")
        exit_ = pd.Timestamp("2024-06-04 10:00", tz="UTC")
        long_r, source_long = hist.r_with_source(
            side="long",
            entry_price=price,
            risk_price=stop_price,
            entry_time=entry,
            exit_time=exit_,
            allow_credit=False,
        )
        short_r, source_short = hist.r_with_source(
            side="short",
            entry_price=price,
            risk_price=stop_price,
            entry_time=entry,
            exit_time=exit_,
            allow_credit=False,
        )
        values = [float(long_r), float(short_r)]
        cost_r = max(0.0, -min(values))
        return {
            "long_r": long_r,
            "short_r": short_r,
            "cost_bps": cost_r * (stop_price / price) * 10_000.0,
            "source": source_long if source_long == source_short else "mixed",
            "reason": reason,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "long_r": None,
            "short_r": None,
            "cost_bps": None,
            "source": f"Sin datos ({type(exc).__name__})",
            "reason": str(exc)[:160],
        }


def _template_stop(template: str) -> float:
    import yaml

    data = yaml.safe_load(
        (TEMPLATE_DIR / f"{template}.yaml").read_text(encoding="utf-8")
    ) or {}
    stop = ((data.get("strategy") or {}).get("exit") or {}).get("stop") or {}
    return float(stop.get("mult") or 2.0)


def main() -> None:
    engine = load_engine_config()
    records: list[dict] = []
    for symbol in SYMBOLS:
        print(f"[data] {symbol}", flush=True)
        m1 = load_cache(symbol)
        for tf in TIMEFRAMES:
            frame = resample_session(m1, tf)
            qconfig = quality_config(engine.data_quality, symbol, tf, "dukascopy")
            probe = check_dataset(
                frame,
                symbol,
                tf,
                segments={key: tuple(value) for key, value in SEGMENTS.items()},
                config=qconfig,
                data_source="dukascopy",
            )
            useful = pd.Timestamp(
                probe.granularity.get("useful_start") or "2012-01-01", tz="UTC"
            )
            usable = engine.data_quality.usable_from_for("dukascopy", symbol, tf)
            usable_ts = (
                pd.Timestamp(usable, tz="UTC") if usable is not None else IS_START
            )
            start = max(IS_START, useful, usable_ts)
            effective = dict(SEGMENTS)
            effective["is"] = (start.date().isoformat(), "2019-12-31")
            report = check_dataset(
                frame,
                symbol,
                tf,
                segments={key: tuple(value) for key, value in effective.items()},
                config=qconfig,
                data_source="dukascopy",
            )
            missing, _sample = missing_weekdays(frame, tf)
            years = {}
            if len(frame):
                for year, group in frame.groupby(frame.index.year):
                    years[str(int(year))] = int(len(group))
            is_frame = frame[(frame.index >= start) & (frame.index <= IS_END)]
            stop_mult = 2.0
            atr_values = atr(is_frame, 14) * stop_mult if len(is_frame) else pd.Series(dtype=float)
            median_atr = float(atr_values.median()) if len(atr_values.dropna()) else None
            median_price = float(is_frame["close"].median()) if len(is_frame) else None
            cost = {"stop_mult": stop_mult, "median_atr_stop": median_atr,
                    "median_price": median_price}
            for account in ACCOUNTS:
                try:
                    account_cost = discovery_costs.build_account_cost(
                        account,
                        symbol,
                        session_tz=engine.data_quality.tz_for(symbol),
                        cost_model_version=2,
                    )
                except Exception as exc:  # noqa: BLE001
                    records.append(
                        {
                            "symbol": symbol,
                            "timeframe": tf,
                            "status": report.status,
                            "rows": int(len(frame)),
                            "raw_rows": int(len(m1)),
                            "useful_start": report.granularity.get("useful_start"),
                            "is_start_effective": start.date().isoformat(),
                            "non_scheduled_gaps": int(report.non_scheduled_gaps),
                            "missing_weekdays": int(missing),
                            "calendar_gaps": len(report.calendar_gaps),
                            "issues": list(report.issues),
                            "segments": {k: v.as_dict() for k, v in report.segments.items()},
                            "years": years,
                            "median_atr14_is": median_atr,
                            "median_price_is": median_price,
                            "account": account,
                            "spread": {"median_bps": None, "p75_bps": None, "max_p75_bps": None},
                            "commission": {"usd": None, "bps": None, "note": str(exc)[:160]},
                            "swap": {"long_r": None, "short_r": None, "cost_bps": None, "source": "Sin datos"},
                            "components": {
                                "spread_median_bps": None,
                                "spread_p75_bps": None,
                                "spread_max_p75_bps": None,
                                "commission_side_usd": None,
                                "commission_side_bps": None,
                                "swap_night_bps": None,
                                "swap_night_r": None,
                                "slippage_side_price": None,
                                "slippage_side_bps": None,
                            },
                        }
                    )
                    continue
                spread = _spread_summary(account_cost)
                commission = _commission_side(account_cost, median_price or 1.0)
                swap = _swap_night(
                    account_cost,
                    median_price or 1.0,
                    median_atr or 1.0,
                )
                slippage_price = float(account_cost.assumed_slippage)
                slippage_bps = (
                    slippage_price / median_price * 10_000.0
                    if median_price
                    else None
                )
                components = {
                    "spread_median_bps": spread["median_bps"],
                    "spread_p75_bps": spread["p75_bps"],
                    "spread_max_p75_bps": spread["max_p75_bps"],
                    "commission_side_usd": commission["usd"],
                    "commission_side_bps": commission["bps"],
                    "swap_night_bps": swap["cost_bps"],
                    "swap_night_r": None
                    if swap["cost_bps"] is None or median_atr is None or median_price is None
                    else swap["cost_bps"] / 10_000.0 * median_price / median_atr,
                    "slippage_side_price": slippage_price,
                    "slippage_side_bps": slippage_bps,
                }
                records.append(
                    {
                        "symbol": symbol,
                        "timeframe": tf,
                        "status": report.status,
                        "rows": int(len(frame)),
                        "raw_rows": int(len(m1)),
                        "useful_start": report.granularity.get("useful_start"),
                        "is_start_effective": start.date().isoformat(),
                        "non_scheduled_gaps": int(report.non_scheduled_gaps),
                        "missing_weekdays": int(missing),
                        "calendar_gaps": len(report.calendar_gaps),
                        "issues": list(report.issues),
                        "segments": {k: v.as_dict() for k, v in report.segments.items()},
                        "years": years,
                        "median_atr14_is": median_atr,
                        "median_price_is": median_price,
                        "account": account,
                        "spread": spread,
                        "commission": commission,
                        "swap": swap,
                        "components": components,
                    }
                )
            print(
                f"  {tf}: {report.status} rows={len(frame)} gaps={report.non_scheduled_gaps} "
                f"useful={report.granularity.get('useful_start')} is_from={start.date()}",
                flush=True,
            )

    # Coste en R por plantilla x activo x TF (peor de las dos cuentas).
    templates = sorted(path.stem for path in TEMPLATE_DIR.glob("*.yaml"))
    by_key: dict[tuple, list[dict]] = {}
    for item in records:
        by_key.setdefault((item["symbol"], item["timeframe"]), []).append(item)
    matrix = []
    for template in templates:
        stop_mult = _template_stop(template)
        import yaml

        meta = yaml.safe_load(
            (TEMPLATE_DIR / f"{template}.yaml").read_text(encoding="utf-8")
        ) or {}
        valid = meta.get("valid_timeframes") or meta.get("timeframes") or []
        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                if tf not in valid:
                    continue
                items = by_key.get((symbol, tf)) or []
                if not items:
                    continue
                worst = None
                for item in items:
                    comp = item["components"]
                    if None in (
                        comp["spread_p75_bps"],
                        comp["commission_side_bps"],
                        comp["slippage_side_bps"],
                    ):
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
                        worst = {
                            "account": item["account"],
                            "cost_r": cost_r,
                            "spread_p75_bps": comp["spread_p75_bps"],
                            "commission_side_bps": comp["commission_side_bps"],
                            "slippage_side_bps": comp["slippage_side_bps"],
                            "median_atr14_is": item["median_atr14_is"],
                        }
                if worst is None:
                    continue
                matrix.append(
                    {
                        "template": template,
                        "symbol": symbol,
                        "timeframe": tf,
                        "stop_mult": stop_mult,
                        **worst,
                        "viable": bool(worst["cost_r"] <= 0.10),
                    }
                )
    matrix.sort(key=lambda row: (not row["viable"], row["cost_r"]))

    OUT_JSON.write_text(
        json.dumps(
            {"records": records, "matrix": matrix, "segments": SEGMENTS},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append("# EDGE-1 X0 - cobertura de datos y costes")
    lines.append("")
    lines.append("Generado por `scripts/edge1_x0.py` (solo lectura). No se toco `engine.yaml`.")
    lines.append("")
    lines.append("## 1. Cobertura Dukascopy (M1 -> TF)")
    lines.append("")
    lines.append("| Activo | TF | Estado | Velas | Inicio util | IS desde | Huecos no prog. | Sesiones sin datos | Anos (velas) |")
    lines.append("|---|---|---|---:|---|---|---:|---:|---|")
    seen_cov = set()
    for item in records:
        key = (item["symbol"], item["timeframe"])
        if key in seen_cov:
            continue
        seen_cov.add(key)
        years = item["years"]
        year_text = ", ".join(f"{year}:{rows}" for year, rows in years.items())
        lines.append(
            f"| {item['symbol']} | {item['timeframe']} | {item['status']} | "
            f"{item['rows']:,} | {item['useful_start'] or 'Sin datos'} | "
            f"{item.get('is_start_effective') or '2012-01-01'} | "
            f"{item['non_scheduled_gaps']} | {item['missing_weekdays']} | {year_text} |"
        )
    lines.append("")
    lines.append("## 2. Costes por activo y TF")
    lines.append("")
    lines.append(
        "Spread = mediana de las medianas horarias del broker y p75 = mediana de los p75 "
        "horarios (hora local de sesion). Comision = por lado. Swap = una noche con el "
        "modelo `historical` (peor lado, sin credito). Slippage = supuesto de `engine.yaml`. "
        "Stop = 2,0 x ATR(14) mediano en IS. R = coste / stop."
    )
    lines.append("")
    lines.append(
        "| Activo | TF | Cuenta | Spread med (bps) | Spread p75 (bps) | Comision/lado (bps) | "
        "Swap/noche (bps) | Slippage/lado (bps) | ATR(14) | Stop 2xATR | Coste R (p75+2slip+2com) |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for item in records:
        comp = item["components"]
        atr_value = item["median_atr14_is"]
        stop = (atr_value or 0.0) * 2.0
        if None not in (
            comp["spread_p75_bps"],
            comp["commission_side_bps"],
            comp["slippage_side_bps"],
        ) and stop > 0 and item["median_price_is"]:
            total = (
                float(comp["spread_p75_bps"])
                + 2.0 * float(comp["commission_side_bps"])
                + 2.0 * float(comp["slippage_side_bps"])
            )
            cost_r = f"{total / 10_000.0 * item['median_price_is'] / stop:.4f}"
        else:
            cost_r = "Sin datos"
        def fmt(value, digits=2):
            return "Sin datos" if value is None else f"{float(value):.{digits}f}"
        lines.append(
            f"| {item['symbol']} | {item['timeframe']} | {item['account']} | "
            f"{fmt(comp['spread_median_bps'])} | {fmt(comp['spread_p75_bps'])} | "
            f"{fmt(comp['commission_side_bps'])} | {fmt(comp['swap_night_bps'])} | "
            f"{fmt(comp['slippage_side_bps'])} | {fmt(atr_value)} | {fmt(stop)} | {cost_r} |"
        )
    lines.append("")
    lines.append("## 3. Comprobacion de magnitudes y decisiones")
    lines.append("")
    lines.append("| Comprobacion | Resultado |")
    lines.append("|---|---|")
    for symbol in ["US100", "US500", "US30"]:
        per_account = {}
        for item in records:
            if item["symbol"] != symbol:
                continue
            value = item["swap"].get("cost_bps")
            if value is not None:
                per_account[item["account"]] = float(value)
        if per_account:
            detail = ", ".join(
                f"{account} {value:.2f}" for account, value in sorted(per_account.items())
            )
            ok = all(0.5 <= value <= 5.0 for value in per_account.values())
            lines.append(
                f"| Swap de indice {symbol} entre 0,5 y 5 bps/noche | "
                f"{'PASA' if ok else 'BLOQUEADO'} ({detail} bps) |"
            )
        else:
            lines.append(f"| Swap de indice {symbol} entre 0,5 y 5 bps/noche | Sin datos |")
    us100 = [
        item for item in records if item["symbol"] == "US100" and item["timeframe"] == "M15"
    ]
    for item in us100:
        value = item["components"]["spread_median_bps"]
        ok = value is not None and 0.3 <= float(value) <= 3.0
        lines.append(
            f"| Spread US100 entre 0,3 y 3 bps ({item['account']}) | "
            f"{'PASA' if ok else 'BLOQUEADO'} ({value:.2f} bps) |"
        )
    for item in records:
        if item["symbol"] != "US30":
            continue
        note = item["commission"].get("note") or ""
        value = item["commission"].get("bps")
        if "broker_spreads" in note:
            result = "Sin datos (sin spread; comision de indice 0)"
        elif value is None:
            result = f"Sin datos ({note})"
        else:
            result = f"{float(value):.4f} bps/lado"
        lines.append(f"| Comision US30 ({item['account']}) | {result} |")
    lines.append("")
    lines.append("**Decisiones X0 (antes de X1):**")
    lines.append("")
    lines.append("- **US100 bloqueado**: swap CFD-001 6,24 bps/noche > 5 bps/noche. Con `cost-mode worst` el coste entra en todas las campanas; no se usa.")
    lines.append("- **US30 bloqueado**: spread Sin datos en CFD-001 y CFD-006; sin coste no hay viabilidad.")
    lines.append("- **US500 H1/H4 sin datos validos**: `data-check` FAIL por huecos (813/791 no programados). Solo M15/M30.")
    lines.append("- **US100/US500/US30 H1/H4**: ademas del bloqueo, H1/H4 de indices fallan calidad; no se registran.")
    lines.append("- **`st_reversal_idx`**: la plantilla es valida, pero su mejor combinacion (US500 M30) da cost_r 0,1088 > 0,10; se queda sin campanas en la pasada 1.")
    lines.append("- **IS desde**: `max(2012-01-01, inicio util, usable_from)` por activo/TF. Excepcion congelada aqui; OOS-1 y OOS-2 no cambian.")
    lines.append("")
    lines.append("## 4. Viabilidad por coste (cost_r <= 0,10)")
    lines.append("")
    viable = [row for row in matrix if row["viable"]]
    lines.append(f"Combinaciones viables: **{len(viable)}** de **{len(matrix)}**.")
    lines.append("")
    lines.append("| # | Plantilla | Activo | TF | cost_r | Cuenta peor |")
    lines.append("|---:|---|---|---|---:|---|")
    for index, row in enumerate(matrix[:60], start=1):
        lines.append(
            f"| {index} | {row['template']} | {row['symbol']} | {row['timeframe']} | "
            f"{row['cost_r']:.4f} | {row['account']} |"
        )
    if len(matrix) > 60:
        lines.append(f"| ... | ({len(matrix) - 60} mas en edge1_data.json) | | | | |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Escrito {OUT_MD} y {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
