"""EDGE1_H1_NY_IMPULSE_CONTINUATION · backtest único y prerregistrado.

Solo lee el tramo IS (2011-09-19 .. 2023-12-31). El OOS 2024-2026 queda
sellado: se descarta antes de calcular señales y no aparece en ninguna
métrica. Aplica el modelo de coste v2 de ``tradinglab.tl3.costs`` y comprueba
las puertas de potencia y coste **antes** de calcular el DSR.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tradinglab.config import ROOT
from tradinglab.discovery.calendars import nyse_early_closes, nyse_holidays
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.costs import build_account_cost
from tradinglab.discovery.resample import resample_session
from tradinglab.indicators import atr
from tradinglab.propfund.instruments import resolve
from tradinglab.stats import dsr_from_returns
from tradinglab.tl3.costs import cost_r_v2
from tradinglab.tl3.gates import cost_r_gate, min_trades_gate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PREREG = ROOT / "configs" / "edge1_h1_ny_impulse.yaml"
REPORT_MD = ROOT / "reports" / "edge1_h1_ny_impulse.md"
REPORT_JSON = ROOT / "reports" / "edge1_h1_ny_impulse.json"
MDE_RULE = 2.49
BOOTSTRAP_N = 10_000
BOOTSTRAP_SEED = 42


# --------------------------------------------------------------------------
# prerregistro
# --------------------------------------------------------------------------


def load_prereg(path: Path = PREREG) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text) or {}
    return payload, hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# datos
# --------------------------------------------------------------------------


def _calendar_exclusions(start_year: int, end_year: int) -> set[date]:
    days = {
        date(int(key) // 10000, int(key) // 100 % 100, int(key) % 100)
        for key in nyse_holidays(start_year, end_year)
    }
    days.update(
        date(int(key) // 10000, int(key) // 100 % 100, int(key) % 100)
        for key in nyse_early_closes(start_year, end_year)
    )
    return days


def _load_h1(symbol: str, prereg: dict) -> tuple[pd.DataFrame, dict]:
    market = prereg["market"]
    windows = prereg["windows"]
    path = ROOT / market["data_paths"][symbol]
    if not path.exists():
        raise FileNotFoundError(f"Sin datos: {path}")

    m1 = pd.read_parquet(path)
    index = pd.DatetimeIndex(m1.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    m1.index = index
    m1 = m1.sort_index()

    is_start = pd.Timestamp(windows["in_sample"]["start"], tz="UTC")
    is_end = pd.Timestamp(windows["in_sample"]["end"], tz="UTC") + pd.Timedelta(days=1)
    seal_start = pd.Timestamp(windows["oos_sealed"]["start"], tz="UTC")
    warmup = pd.Timedelta(days=45)

    sealed_rows = int((m1.index >= seal_start).sum())
    m1 = m1.loc[(m1.index >= is_start - warmup) & (m1.index < seal_start)]
    if len(m1) == 0:
        raise ValueError(f"Sin datos IS para {symbol}")
    if m1.index.max() >= seal_start:
        raise AssertionError(f"{symbol}: el OOS no está sellado")

    frame = resample_session(m1, market["timeframe"], tz=market["session_tz"])
    frame = frame.loc[frame.index < seal_start]
    frame["atr14"] = atr(frame, 14)
    local = frame.index.tz_convert(market["session_tz"])
    frame["local_date"] = local.date
    frame["local_hour"] = local.hour

    meta = {
        "symbol": symbol,
        "m1_rows_used": int(len(m1)),
        "m1_rows_oos_discarded": sealed_rows,
        "h1_bars": int(len(frame)),
        "first_bar_utc": frame.index.min().isoformat() if len(frame) else None,
        "last_bar_utc": frame.index.max().isoformat() if len(frame) else None,
        "is_start": is_start.date().isoformat(),
        "is_end": (is_end - pd.Timedelta(days=1)).date().isoformat(),
        "seal_start": seal_start.date().isoformat(),
    }
    return frame, meta


# --------------------------------------------------------------------------
# costes v2
# --------------------------------------------------------------------------


def _commission_side_bps(profile, price: float) -> float | None:
    kind = profile.commission_type
    if kind in (None, "zero"):
        return 0.0
    side_factor = 0.5 if profile.commission_side == "round_turn" else 1.0
    if kind == "percent_of_volume":
        return float(profile.commission_value or 0.0) * 100.0 * side_factor
    if kind == "per_lot_usd":
        contract = resolve(profile.symbol).contract_size
        if contract is None or contract <= 0:
            return None
        per_lot = float(profile.commission_value or 0.0) * side_factor
        return per_lot / (price * float(contract)) * 10_000.0
    return None


def build_cost_inputs(symbol: str, prereg: dict) -> list[dict]:
    engine = load_engine_config()
    session_tz = prereg["market"]["session_tz"]
    version = int(prereg["costs"]["cost_model_version"])
    out: list[dict] = []
    for account in prereg["costs"]["accounts"]:
        account_cost = build_account_cost(
            account,
            symbol,
            session_tz=session_tz,
            config=engine,
            cost_model_version=version,
        )
        out.append(
            {
                "account": account,
                "spread_by_hour": {
                    int(hour): float(value)
                    for hour, value in account_cost.spread.median_bps.items()
                },
                "slippage_price": float(account_cost.assumed_slippage),
                "profile": account_cost.profile,
            }
        )
    return out


def cost_components(
    inputs: list[dict], *, entry_price: float, local_hour: int
) -> dict | None:
    """Peor cuenta por componente. Devuelve None si falta un dato."""

    spreads: list[float] = []
    slips: list[float] = []
    commissions: list[float] = []
    for item in inputs:
        spread = item["spread_by_hour"].get(int(local_hour))
        if spread is None or not math.isfinite(float(spread)):
            return None
        spreads.append(float(spread))
        slips.append(float(item["slippage_price"]) / entry_price * 10_000.0)
        commission = _commission_side_bps(item["profile"], entry_price)
        if commission is None:
            return None
        commissions.append(float(commission))
    return {
        "spread_bps": max(spreads),
        "slippage_bps": max(slips),
        "commission_bps": max(commissions),
        "accounts": [item["account"] for item in inputs],
    }


# --------------------------------------------------------------------------
# regla
# --------------------------------------------------------------------------


def _signal_side(signal: pd.Series, prior: pd.DataFrame, body_min: float) -> str | None:
    high = float(signal["high"])
    low = float(signal["low"])
    open_ = float(signal["open"])
    close = float(signal["close"])
    span = high - low
    if not math.isfinite(span) or span <= 0:
        return None
    body = abs(close - open_)
    if body / span < float(body_min):
        return None
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    if close > open_ and close > prior_high:
        return "long"
    if close < open_ and close < prior_low:
        return "short"
    return None


def run_backtest(prereg: dict) -> tuple[list[dict], dict]:
    market = prereg["market"]
    rules = prereg["rules"]
    windows = prereg["windows"]
    is_start = date.fromisoformat(windows["in_sample"]["start"])
    is_end = date.fromisoformat(windows["in_sample"]["end"])
    exclusions = _calendar_exclusions(is_start.year - 1, is_end.year + 1)
    body_min = float(rules["body_ratio_min"])
    atr_n = int(rules["stop"]["n"])
    atr_mult = float(rules["stop"]["mult"])
    rr = float(rules["target"]["rr"])
    signal_hour = int(rules["signal_bar_local_hour"])
    entry_hour = int(rules["signal_bar_local_hour"]) + 1
    exit_hour = int(rules["exit"]["exit_bar_local_hour"])
    prior_hours = list(range(signal_hour - 1, signal_hour - 1 - int(rules["prior_bars"]), -1))

    trades: list[dict] = []
    coverage: dict[str, dict] = {}
    for symbol in market["instruments"]:
        frame, meta = _load_h1(symbol, prereg)
        cost_inputs = build_cost_inputs(symbol, prereg)
        symbols = 0
        skipped_calendar = 0
        skipped_bars = 0
        for local_day, group in frame.groupby("local_date", sort=True):
            if not isinstance(local_day, date):
                local_day = pd.Timestamp(local_day).date()
            if local_day < is_start or local_day > is_end:
                continue
            if local_day in exclusions:
                skipped_calendar += 1
                continue
            bars = group.sort_index()
            signal_rows = bars.loc[bars["local_hour"] == signal_hour]
            entry_rows = bars.loc[bars["local_hour"] == entry_hour]
            exit_rows = bars.loc[bars["local_hour"] == exit_hour]
            prior_rows = bars.loc[bars["local_hour"].isin(prior_hours)]
            if (
                len(signal_rows) != 1
                or len(entry_rows) != 1
                or len(exit_rows) != 1
                or len(prior_rows) != int(rules["prior_bars"])
            ):
                skipped_bars += 1
                continue

            signal = signal_rows.iloc[0]
            atr_value = float(signal.get(f"atr{atr_n}"))
            if not math.isfinite(atr_value) or atr_value <= 0:
                skipped_bars += 1
                continue
            side = _signal_side(signal, prior_rows, body_min)
            if side is None:
                continue

            entry_bar = entry_rows.iloc[0]
            entry = float(entry_bar["open"])
            risk = atr_mult * atr_value
            if not math.isfinite(entry) or entry <= 0 or risk <= 0:
                skipped_bars += 1
                continue
            stop = entry - risk if side == "long" else entry + risk
            target = entry + rr * risk if side == "long" else entry - rr * risk

            exit_price: float | None = None
            exit_kind: str | None = None
            exit_ts: pd.Timestamp | None = None
            after = bars.loc[bars.index >= entry_bar.name]
            for stamp, bar in after.iterrows():
                if side == "long":
                    if float(bar["low"]) <= stop:
                        exit_price, exit_kind, exit_ts = stop, "stop", stamp
                        break
                    if float(bar["high"]) >= target:
                        exit_price, exit_kind, exit_ts = target, "target", stamp
                        break
                else:
                    if float(bar["high"]) >= stop:
                        exit_price, exit_kind, exit_ts = stop, "stop", stamp
                        break
                    if float(bar["low"]) <= target:
                        exit_price, exit_kind, exit_ts = target, "target", stamp
                        break
                if int(bar["local_hour"]) == exit_hour:
                    exit_price, exit_kind, exit_ts = float(bar["close"]), "time", stamp
                    break
            if exit_price is None:
                skipped_bars += 1
                continue

            gross = (
                (exit_price - entry) / risk
                if side == "long"
                else (entry - exit_price) / risk
            )
            components = cost_components(
                cost_inputs, entry_price=entry, local_hour=entry_hour
            )
            if components is None:
                cost_payload = None
                net = None
            else:
                cost_payload = cost_r_v2(
                    entry,
                    risk,
                    spread_bps=components["spread_bps"],
                    slippage_bps=components["slippage_bps"],
                    commission_bps=components["commission_bps"],
                    swap_bps=0.0,
                )
                net = gross - float(cost_payload["cost_r"])

            trades.append(
                {
                    "symbol": symbol,
                    "date": local_day.isoformat(),
                    "side": side,
                    "entry_time_utc": entry_bar.name.isoformat(),
                    "exit_time_utc": exit_ts.isoformat() if exit_ts is not None else None,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "risk_price": risk,
                    "atr14": atr_value,
                    "exit": exit_price,
                    "exit_kind": exit_kind,
                    "gross_r": float(gross),
                    "cost_r": None if cost_payload is None else float(cost_payload["cost_r"]),
                    "net_r": None if net is None else float(net),
                    "cost": cost_payload,
                }
            )
            symbols += 1

        meta["trades"] = symbols
        meta["skipped_calendar_days"] = skipped_calendar
        meta["skipped_incomplete_or_no_exit"] = skipped_bars
        coverage[symbol] = meta

    return trades, coverage


# --------------------------------------------------------------------------
# métricas
# --------------------------------------------------------------------------


def _cluster_bootstrap_lcb(trades: list[dict], *, n_boot: int, seed: int) -> float | None:
    by_date: dict[str, list[float]] = {}
    for trade in trades:
        if trade["net_r"] is None:
            continue
        by_date.setdefault(trade["date"], []).append(float(trade["net_r"]))
    keys = list(by_date)
    if len(keys) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        pick = rng.integers(0, len(keys), size=len(keys))
        values = [value for key_index in pick for value in by_date[keys[key_index]]]
        means[index] = float(np.mean(values))
    return float(np.percentile(means, 5.0))


def _metrics(trades: list[dict]) -> dict:
    clean = [trade for trade in trades if trade["net_r"] is not None]
    nets = np.array([float(trade["net_r"]) for trade in clean], dtype=float)
    gross = np.array([float(trade["gross_r"]) for trade in clean], dtype=float)
    costs = np.array([float(trade["cost_r"]) for trade in clean], dtype=float)
    n = int(nets.size)
    if n == 0:
        return {
            "n_trades": 0,
            "net_expectancy_r": None,
            "gross_expectancy_r": None,
            "median_cost_r": None,
            "p90_cost_r": None,
            "win_rate": None,
            "profit_factor": None,
            "lcb95_net_r": None,
            "mde_r": None,
            "daily_r": [],
        }
    std = float(nets.std(ddof=1)) if n > 1 else 0.0
    positives = float(nets[nets > 0].sum())
    negatives = float(nets[nets < 0].sum())
    daily: dict[str, float] = {}
    for trade in clean:
        daily[trade["date"]] = daily.get(trade["date"], 0.0) + float(trade["net_r"])
    return {
        "n_trades": n,
        "net_expectancy_r": float(nets.mean()),
        "gross_expectancy_r": float(gross.mean()),
        "median_cost_r": float(np.median(costs)),
        "p90_cost_r": float(np.percentile(costs, 90)),
        "win_rate": float((nets > 0).mean()),
        "profit_factor": (positives / abs(negatives)) if negatives < 0 else None,
        "lcb95_net_r": _cluster_bootstrap_lcb(
            clean, n_boot=BOOTSTRAP_N, seed=BOOTSTRAP_SEED
        ),
        "mde_r": (MDE_RULE * std / math.sqrt(n)) if n > 1 else None,
        "std_r": std,
        "daily_r": [daily[key] for key in sorted(daily)],
        "daily_dates": sorted(daily),
    }


def _dsr(metrics: dict, prereg: dict) -> dict | None:
    daily = np.asarray(metrics.get("daily_r") or [], dtype=float)
    if daily.size < 3:
        return {
            "status": "Sin datos",
            "dsr": None,
            "reason": f"días con operaciones {daily.size} < 3",
            "kind": "Sin datos",
        }
    payload = dsr_from_returns(
        daily,
        [],
        n_trials=int(prereg.get("metrics", {}).get("dsr", {}).get("n_trials", 1)),
        periods_per_year=float(
            prereg.get("metrics", {}).get("dsr", {}).get("periods_per_year", 252.0)
        ),
        benchmark_sr=0.0,
    )
    payload["kind"] = "psr_sr0_k1"
    payload["note"] = "K=1: PSR frente a SR 0 (convención de discovery/levels.py)"
    payload["daily_days"] = int(daily.size)
    return payload


# --------------------------------------------------------------------------
# informe
# --------------------------------------------------------------------------


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return f"{float(value):.{digits}f}"


def _markdown(
    prereg: dict,
    digest: str,
    coverage: dict,
    trades: list[dict],
    metrics: dict,
    power: dict,
    cost: dict,
    dsr: dict | None,
    verdict: str,
) -> str:
    lines = [
        f"# {prereg['hypothesis_id']} · backtest IS (OOS sellado)",
        "",
        f"- Título: {prereg['title']}",
        "- Prerregistro: `configs/edge1_h1_ny_impulse.yaml`",
        f"- SHA256 del prerregistro: `{digest}`",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Datos: Dukascopy BID M1 -> H1, {', '.join(prereg['market']['instruments'])}",
        f"- IS: {prereg['windows']['in_sample']['start']} .. {prereg['windows']['in_sample']['end']}",
        f"- OOS: {prereg['windows']['oos_sealed']['start']} .. {prereg['windows']['oos_sealed']['end']} **sellado, no leído**",
        "",
        "## 1. Regla ejecutada",
        "",
        "| Campo | Regla |",
        "|---|---|",
        f"| Vela de señal | {prereg['rules']['signal_bar_local_hour']}:00-{int(prereg['rules']['signal_bar_local_hour']) + 1}:00 NY |",
        f"| Impulso | cuerpo / rango >= {prereg['rules']['body_ratio_min']:.2f} |",
        f"| Ruptura | cierre > máximo (o < mínimo) de las {prereg['rules']['prior_bars']} velas H1 previas |",
        f"| Entrada | open de la vela {int(prereg['rules']['signal_bar_local_hour']) + 1}:00 NY |",
        f"| Stop | {prereg['rules']['stop']['mult']:.1f} x ATR({prereg['rules']['stop']['n']}) H1 |",
        f"| Objetivo | {prereg['rules']['target']['rr']:.1f} R |",
        f"| Salida por tiempo | cierre de la vela {prereg['rules']['exit']['exit_bar_local_hour']}:00 NY (16:00) |",
        "| Prioridad intrabar | stop antes que target si ambos se tocan en la misma vela |",
        "| Frecuencia | máximo 1 operación por instrumento y día |",
        "| Costes | v2: spread + 2 x slippage + 2 x comisión; peor de CFD-001/CFD-006 |",
        "",
        "## 2. Cobertura y sello OOS",
        "",
        "| Instrumento | Filas M1 usadas | Filas OOS descartadas | Velas H1 | Primera vela | Última vela | Días sin velas completas |",
        "|---|---:|---:|---:|---|---|---:|",
    ]
    for symbol, meta in coverage.items():
        lines.append(
            f"| {symbol} | {meta['m1_rows_used']:,} | {meta['m1_rows_oos_discarded']:,} | "
            f"{meta['h1_bars']:,} | {meta['first_bar_utc']} | {meta['last_bar_utc']} | "
            f"{meta['skipped_incomplete_or_no_exit']} |"
        )
    lines += [
        "",
        "El OOS se descartó antes de remuestrear y de calcular señales. "
        "Ninguna fila con timestamp >= 2024-01-01T00:00:00Z entra en la regla, "
        "los costes o las métricas.",
        "",
        "## 3. Puertas (antes del DSR)",
        "",
        "| Puerta | Resultado | Detalle |",
        "|---|---|---|",
        f"| power_gate (n >= {power['min_trades']}) | {'PASA' if power['ok'] else 'NO PASA'} | "
        f"n = {_fmt(power.get('n'))} |",
        f"| cost_gate (mediana cost_r <= {cost['max_cost_r']:.2f}) | {'PASA' if cost['ok'] else 'NO PASA'} | "
        f"mediana = {_fmt(cost.get('cost_r'))}; p90 = {_fmt(metrics.get('p90_cost_r'))} |",
        "",
    ]
    if dsr is None:
        lines += [
            "**DSR: no calculado.** Una de las dos puertas no se superó; "
            "calcularlo después sería una mirada no prerregistrada.",
            "",
        ]
    else:
        lines += [
            "Ambas puertas se superaron; el DSR se calcula a continuación.",
            "",
        ]

    lines += [
        "## 4. Resultado IS",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Operaciones | {_fmt(metrics.get('n_trades'))} |",
        f"| Bruto medio | {_fmt(metrics.get('gross_expectancy_r'))} R |",
        f"| Coste mediano | {_fmt(metrics.get('median_cost_r'))} R |",
        f"| Neto medio | {_fmt(metrics.get('net_expectancy_r'))} R |",
        f"| Desviación del neto | {_fmt(metrics.get('std_r'))} R |",
        f"| LCB95 (bootstrap por fecha) | {_fmt(metrics.get('lcb95_net_r'))} R |",
        f"| MDE (2,49 x sigma / sqrt(n)) | {_fmt(metrics.get('mde_r'))} R |",
        f"| Tasa de acierto | {_fmt(metrics.get('win_rate'))} |",
        f"| Profit factor | {_fmt(metrics.get('profit_factor'))} |",
        "",
    ]
    # Desglose por símbolo y año, solo si hay operaciones.
    if trades:
        lines += [
            "### Neto medio por instrumento",
            "",
            "| Instrumento | n | Bruto R | Coste R | Neto R |",
            "|---|---:|---:|---:|---:|",
        ]
        for symbol in prereg["market"]["instruments"]:
            subset = [
                trade
                for trade in trades
                if trade["symbol"] == symbol and trade["net_r"] is not None
            ]
            if not subset:
                lines.append(f"| {symbol} | 0 | Sin datos | Sin datos | Sin datos |")
                continue
            nets = [float(trade["net_r"]) for trade in subset]
            gross = [float(trade["gross_r"]) for trade in subset]
            costs = [float(trade["cost_r"]) for trade in subset]
            lines.append(
                f"| {symbol} | {len(subset)} | {np.mean(gross):+.4f} | "
                f"{np.mean(costs):.4f} | {np.mean(nets):+.4f} |"
            )
        lines += [
            "",
            "### Neto medio por año",
            "",
            "| Año | n | Neto medio R |",
            "|---|---:|---:|",
        ]
        years: dict[str, list[float]] = {}
        for trade in trades:
            if trade["net_r"] is None:
                continue
            years.setdefault(trade["date"][:4], []).append(float(trade["net_r"]))
        for year in sorted(years):
            values = years[year]
            lines.append(f"| {year} | {len(values)} | {np.mean(values):+.4f} |")
        lines.append("")

    lines += ["## 5. DSR", ""]
    if dsr is None:
        lines += [
            "| Campo | Valor |",
            "|---|---|",
            "| Estado | No calculado (puerta fallida) |",
            "",
        ]
    else:
        lines += [
            "| Campo | Valor |",
            "|---|---:|",
            f"| DSR | {_fmt(dsr.get('dsr'))} |",
            f"| Tipo | {dsr.get('kind')} |",
            f"| Sharpe por día | {_fmt(dsr.get('sr_period'))} |",
            f"| SR0 por día | {_fmt(dsr.get('sr0_period'))} |",
            f"| Días con operaciones | {_fmt(dsr.get('daily_days'))} |",
            f"| Mínimo | {prereg['gates']['dsr_min']:.2f} |",
            "",
            "El DSR se calcula sobre el R neto agregado por día (una observación por fecha, "
            "agrupando US100 y US500 del mismo día). Con K=1 la convención del proyecto es "
            "PSR frente a SR 0; por eso se etiqueta `psr_sr0_k1`.",
            "",
        ]
    lines += [
        "## 6. Veredicto",
        "",
        f"**{verdict}**",
        "",
        "## 7. Límites",
        "",
        "- Solo se ejecutó el tramo IS; 2024-2026 sigue sellado y no se ha mirado.",
        "- Dukascopy es BID; el spread se modela con la mediana horaria del bróker y el slippage con el supuesto de `engine.yaml`. No es un fill real.",
        "- US30 queda fuera por falta de spread/comisión en las cuentas; no se inventan costes.",
        "- Un resultado positivo aquí no es una estrategia validada: es un candidato para una lectura OOS única, con su propio registro.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    prereg, digest = load_prereg()
    print(f"{prereg['hypothesis_id']}: prerregistro {digest[:16]}…")

    trades, coverage = run_backtest(prereg)
    metrics = _metrics(trades)

    power = min_trades_gate(
        metrics.get("n_trades"), int(prereg["gates"]["power"]["min_trades"])
    )
    cost = cost_r_gate(
        metrics.get("median_cost_r"), float(prereg["gates"]["cost"]["max_cost_r"])
    )

    dsr = None
    if power["ok"] and cost["ok"]:
        dsr = _dsr(metrics, prereg)

    if not power["ok"]:
        verdict = "rejected: no_power"
    elif not cost["ok"]:
        verdict = "rejected: cost_gate"
    elif (
        metrics.get("net_expectancy_r") is not None
        and float(metrics["net_expectancy_r"]) > 0
        and metrics.get("lcb95_net_r") is not None
        and float(metrics["lcb95_net_r"]) > 0
        and dsr is not None
        and dsr.get("dsr") is not None
        and float(dsr["dsr"]) >= float(prereg["gates"]["dsr_min"])
    ):
        verdict = "candidate_oos_sealed"
    elif metrics.get("net_expectancy_r") is None or float(metrics["net_expectancy_r"]) <= 0:
        verdict = "rejected: no_edge"
    else:
        verdict = "rejected: dsr"

    report = {
        "hypothesis_id": prereg["hypothesis_id"],
        "prereg_sha256": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "windows": prereg["windows"],
        "coverage": coverage,
        "metrics": {key: value for key, value in metrics.items() if key != "daily_r"},
        "power_gate": power,
        "cost_gate": cost,
        "dsr": dsr,
        "verdict": verdict,
        "n_variants": 1,
        "trades": trades,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    REPORT_MD.write_text(
        _markdown(
            prereg,
            digest,
            coverage,
            trades,
            metrics,
            power,
            cost,
            dsr,
            verdict,
        ),
        encoding="utf-8",
    )

    print(f"trades={metrics.get('n_trades')} neto={metrics.get('net_expectancy_r')}")
    print(f"power={power['ok']} cost={cost['ok']} dsr={None if dsr is None else dsr.get('dsr')}")
    print(f"veredicto={verdict}")
    print(f"informe={REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
