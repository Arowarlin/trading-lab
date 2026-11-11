"""Barrido de exposición de una variante ya validada (sin reoptimizar).

Lee los retornos diarios del artefacto del research (`swing_cfd/artifacts/`),
escala por `k` y simula el challenge FTMO 100k con `prop/simulator.monte_carlo`
en dos horizontes: 120 días y sin límite (750 días como máximo). Calcula el EV
neto con la cuota del challenge, el split y el beneficio esperado del primer mes
fondeado a esa misma `k`.

No recalcula el backtest, no cambia la estrategia y no activa nada.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import ROOT
from .intraday import load_bars
from .prop.rules import PropRules
from .prop.simulator import monte_carlo

PROP_CONFIG = ROOT / "config" / "prop.yaml"
VBT_PYTHON = ROOT / ".venv-vbt" / "Scripts" / "python.exe"
K_VALUES = (0.25, 0.35, 0.5, 0.75, 1.0)
PATHS = 2_000
SEED = 42
BLOCK = 5
HORIZON_120 = 120
HORIZON_MAX = 750
MONTH_DAYS = 21
DEFAULT_FEE_EUR = 540.0
DEFAULT_SPLIT = 0.80
# FTMO 2-Step: la cuota se devuelve con la primera retirada de Reward.
# Fuente: FTMO FAQ "Is the entry fee refunded?" (actualizada 2026-10-06)
# https://ftmo.com/en/faq/is-the-entry-fee-refunded/
FEE_REFUND_DEFAULT = True
FEE_REFUND_SOURCE = (
    "FTMO FAQ 'Is the entry fee refunded?' (2-Step: se devuelve con la primera "
    "retirada de Reward; 1-Step/Instant no) · "
    "https://ftmo.com/en/faq/is-the-entry-fee-refunded/ · consultado 2026-11-11"
)


class SweepError(RuntimeError):
    """Falta el artefacto o la variante no es simulable."""


def _economics(
    fee_eur: float | None,
    split: float | None,
    fee_refund_on_pass: bool | None = None,
) -> dict:
    """Cuota, split y reembolso: `prop.yaml -> economics` o parámetros."""
    data: dict = {}
    if PROP_CONFIG.exists():
        raw = yaml.safe_load(PROP_CONFIG.read_text(encoding="utf-8")) or {}
        data = raw.get("economics") or {}
    fee = fee_eur if fee_eur is not None else data.get("challenge_fee_eur")
    share = split if split is not None else data.get("profit_split")
    refund = data.get("fee_refund_on_pass") if fee_refund_on_pass is None else fee_refund_on_pass
    if fee is None:
        fee = DEFAULT_FEE_EUR
    if share is None:
        share = DEFAULT_SPLIT
    if refund is None:
        refund = FEE_REFUND_DEFAULT
    return {
        "fee_eur": float(fee),
        "profit_split": float(share),
        "fee_refund_on_pass": bool(refund),
        "refund_source": FEE_REFUND_SOURCE,
        "source": (
            "config/prop.yaml:economics"
            if data
            else "parametro (prop.yaml no tiene economics)"
        ),
    }


def eurusd_rate(cache_dir: str | Path) -> dict:
    """EURUSD del cierre más reciente de la caché MT5 (para pasar USD a EUR)."""
    for timeframe in ("H1", "M15"):
        try:
            frame = load_bars(cache_dir, "EURUSD", timeframe)
        except FileNotFoundError:
            continue
        if len(frame) == 0:
            continue
        return {
            "rate": float(frame["close"].iloc[-1]),
            "timeframe": timeframe,
            "as_of": str(frame.index[-1]),
            "source": "caché MT5",
        }
    return {"rate": None, "timeframe": None, "as_of": None, "source": "Sin datos"}


def artifact_file(out_dir: str | Path, bot: str) -> Path:
    return Path(out_dir) / "artifacts" / f"{bot}.parquet"


def load_artifact(
    bot: str,
    out_dir: str | Path,
    path: str | Path | None = None,
) -> dict:
    """Carga los retornos diarios del artefacto y su metadata (si existe)."""
    target = Path(path) if path else artifact_file(out_dir, bot)
    if not target.exists():
        raise SweepError(
            f"falta el artefacto de {bot}: {target}. "
            "El research debe guardarlo en `artifacts/<bot>.parquet`."
        )
    frame = pd.read_parquet(target)
    if "returns" not in frame.columns:
        raise SweepError(f"{target}: falta la columna returns")
    returns = pd.to_numeric(frame["returns"], errors="coerce").dropna().astype(float)
    if len(returns) < 120:
        raise SweepError(f"{target}: muestra insuficiente ({len(returns)} días)")
    if returns.index.tz is None:
        returns.index = pd.DatetimeIndex(returns.index).tz_localize("UTC")
    meta_path = target.with_suffix(".json")
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    return {"returns": returns, "path": str(target), "meta": meta}


def save_artifact(
    bot: str,
    out_dir: str | Path,
    returns: pd.Series,
    *,
    meta: dict,
) -> dict:
    """Guarda el artefacto del bot (parquet + sidecar JSON con la procedencia)."""
    target = artifact_file(out_dir, bot)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"returns": returns.astype(float)})
    frame.index.name = "date"
    frame.to_parquet(target)
    target.with_suffix(".json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return {"path": str(target), "meta": str(target.with_suffix(".json"))}


def _horizon_blocks(days: int, block: int) -> int:
    """`monte_carlo` avanza un bloque por iteración: convierte días a bloques.

    El motor cuenta `horizon` iteraciones y cada una compone `block_size` días,
    así que para simular H días se pasan ceil(H / bloque) iteraciones. Con
    bloque 5, 120 días son 24 bloques y 750 días, 150.
    """
    block = max(1, int(block))
    return max(1, (int(days) + block - 1) // block)


def funded_month_payout(
    returns: pd.Series,
    *,
    k: float,
    account: float,
    split: float,
    rules: PropRules,
    paths: int = PATHS,
    block: int = BLOCK,
    seed: int = SEED,
) -> dict:
    """Pago esperado del primer mes fondeado a exposición `k`.

    Bootstrap por bloques de exactamente 21 días desde una cuenta fondeada (sin
    objetivo): si el path revienta el diario o el total, el pago es 0. Si no,
    paga `split × max(0, beneficio)`.
    """
    r = np.clip(np.asarray(returns, dtype=float) * float(k), -0.95, 1.0)
    r = r[np.isfinite(r)]
    if r.size == 0:
        raise ValueError("sin retornos para el mes fondeado")
    rng = np.random.default_rng(seed)
    equity = np.full(int(paths), float(account))
    breached = np.zeros(int(paths), dtype=bool)
    daily_limit = float(rules.max_daily_loss_pct)
    total_limit = float(rules.max_loss_pct)
    size = max(1, int(block))
    remaining = MONTH_DAYS
    while remaining > 0:
        step = min(size, remaining)
        starts = rng.integers(0, max(1, r.size - step + 1), size=int(paths))
        idx = (starts[:, None] + np.arange(step)[None, :]) % r.size
        draws = (1.0 + r[idx]).prod(axis=1) - 1.0
        day_start = equity.copy()
        equity = equity * (1.0 + draws)
        floor = np.maximum(
            day_start * (1.0 - daily_limit),
            float(account) * (1.0 - total_limit),
        )
        breached |= equity <= floor
        remaining -= step
    profit = np.where(breached, 0.0, np.maximum(0.0, equity - float(account)))
    return {
        "expected_payout_usd": float(split) * float(profit.mean()),
        "expected_profit_usd": float(np.maximum(0.0, equity - float(account)).mean()),
        "breach_rate": float(breached.mean()),
    }


def bootstrap_ci(
    returns: pd.Series,
    rules: PropRules,
    *,
    k: float,
    resamples: int = 200,
    paths: int = 500,
    block: int = BLOCK,
    seed: int = SEED,
) -> dict:
    """IC 90 % de P(pasar) remuestreando los retornos (bootstrap por bloques).

    Cada remuestreo reordenar los retornos en bloques del mismo tamaño que la
    muestra original y corre el MC sin límite con `paths` simulaciones. Devuelve
    los percentiles 5/95 de la distribución de P(pasar).
    """
    r = np.asarray(returns, dtype=float) * float(k)
    r = r[np.isfinite(r)]
    count = int(resamples)
    if count <= 0 or r.size == 0:
        return {"low": None, "high": None, "resamples": 0, "paths": int(paths)}
    rng = np.random.default_rng(seed)
    size = r.size
    block_size = max(1, int(block))
    values: list[float] = []
    for index in range(count):
        sample = np.empty(size, dtype=float)
        filled = 0
        while filled < size:
            start = int(rng.integers(0, max(1, size - block_size + 1)))
            take = min(block_size, size - filled)
            sample[filled : filled + take] = r[start : start + take][:take]
            filled += take
        result = monte_carlo(
            rules,
            sample,
            n_paths=int(paths),
            horizon=_horizon_blocks(HORIZON_MAX, block_size),
            block_size=block_size,
            seed=int(seed) + index,
        )
        values.append(float(result["pass_rate"]))
    low, high = np.percentile(values, [5, 95])
    return {
        "low": float(low),
        "high": float(high),
        "resamples": count,
        "paths": int(paths),
        "median": float(np.median(values)),
    }


def sweep(
    returns: pd.Series,
    rules: PropRules,
    *,
    k_values: tuple[float, ...] = K_VALUES,
    paths: int = PATHS,
    seed: int = SEED,
    block: int = BLOCK,
    fee_eur: float | None = None,
    split: float | None = None,
    fee_refund_on_pass: bool | None = None,
    eurusd: float | None = None,
    oracle: bool = True,
    bootstrap: int = 0,
    bootstrap_paths: int = 500,
) -> dict:
    """Barrido completo: MC por k, EV (con y sin reembolso) y oráculo."""
    economics = _economics(fee_eur, split, fee_refund_on_pass)
    rate = float(eurusd) if eurusd else None
    fee_usd = economics["fee_eur"] * rate if rate else None
    refund_eur = economics["fee_eur"] if economics["fee_refund_on_pass"] else 0.0
    rows: list[dict] = []
    for k in k_values:
        scaled = returns * float(k)
        mc120 = monte_carlo(
            rules,
            scaled,
            n_paths=int(paths),
            horizon=_horizon_blocks(HORIZON_120, block),
            block_size=int(block),
            seed=int(seed),
        )
        mcmax = monte_carlo(
            rules,
            scaled,
            n_paths=int(paths),
            horizon=_horizon_blocks(HORIZON_MAX, block),
            block_size=int(block),
            seed=int(seed),
        )
        month = funded_month_payout(
            returns,
            k=float(k),
            account=float(rules.account_size),
            split=economics["profit_split"],
            rules=rules,
            paths=int(paths),
            block=int(block),
            seed=int(seed),
        )
        payout_eur = month["expected_payout_usd"] / rate if rate else None
        ev_eur = (
            float(mcmax["pass_rate"]) * (payout_eur + refund_eur) - economics["fee_eur"]
            if payout_eur is not None
            else None
        )
        ev_no_refund = (
            float(mcmax["pass_rate"]) * payout_eur - economics["fee_eur"]
            if payout_eur is not None
            else None
        )
        ci90 = (
            bootstrap_ci(
                returns,
                rules,
                k=float(k),
                resamples=int(bootstrap),
                paths=int(bootstrap_paths),
                block=int(block),
                seed=int(seed),
            )
            if bootstrap
            else None
        )
        oracle_payout_eur = (
            float(mcmax["pass_rate"])
            * float(rules.profit_target_pct)
            * float(rules.account_size)
            * economics["profit_split"]
            / rate
            if rate
            else None
        )
        oracle_ev_eur = (
            oracle_payout_eur - economics["fee_eur"]
            if oracle_payout_eur is not None
            else None
        )
        rows.append(
            {
                "k": float(k),
                "horizon_120": {
                    "pass_rate": mc120["pass_rate"],
                    "pass_ci95": list(mc120["pass_ci95"]),
                    "breach_rate": mc120["breach_rate"],
                    "timeout_rate": mc120["timeout_rate"],
                    "median_days_to_pass": mc120["median_days_to_pass"],
                    "median_max_drawdown": mc120["median_max_drawdown"],
                    "p5_max_drawdown": mc120["p5_max_drawdown"],
                    "worst_max_drawdown": mc120["worst_max_drawdown"],
                },
                "sin_limite": {
                    "pass_rate": mcmax["pass_rate"],
                    "pass_ci95": list(mcmax["pass_ci95"]),
                    "breach_rate": mcmax["breach_rate"],
                    "timeout_rate": mcmax["timeout_rate"],
                    "median_days_to_pass": mcmax["median_days_to_pass"],
                    "median_max_drawdown": mcmax["median_max_drawdown"],
                    "p5_max_drawdown": mcmax["p5_max_drawdown"],
                    "worst_max_drawdown": mcmax["worst_max_drawdown"],
                },
                "ci90": ci90,
                "funded_month": month,
                "payout_eur": payout_eur,
                "ev_eur": ev_eur,
                "ev_no_refund_eur": ev_no_refund,
                "oracle_payout_eur": oracle_payout_eur,
                "oracle_ev_eur": oracle_ev_eur,
            }
        )
    return {
        "economics": economics,
        "eurusd": {"rate": rate},
        "fee_usd": fee_usd,
        "rows": rows,
        "paths": int(paths),
        "seed": int(seed),
        "block_size": int(block),
        "k_values": list(k_values),
        "horizon_120": HORIZON_120,
        "horizon_max": HORIZON_MAX,
        "horizon_120_blocks": _horizon_blocks(HORIZON_120, block),
        "horizon_max_blocks": _horizon_blocks(HORIZON_MAX, block),
        "bootstrap": {
            "resamples": int(bootstrap),
            "paths": int(bootstrap_paths) if bootstrap else 0,
            "method": "bootstrap por bloques de los retornos; MC sin límite",
        },
        "oracle": _oracle(returns, rules, k_values) if oracle else None,
    }


ORACLE_CHILD = """
import json, sys
from propev import Firm, simulate

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
firm = Firm(**payload["firm"])
out = {}
for k, item in payload["variants"].items():
    out[k] = simulate(
        firm,
        item["edge_bps"],
        item["std_bps"],
        payload["trades_per_day"],
        n_sims=payload["n_sims"],
        seed=payload["seed"],
    )
import propev
print(json.dumps({"pass": out, "version": propev.__version__}))
"""


def _oracle(
    returns: pd.Series,
    rules: PropRules,
    k_values: tuple[float, ...],
    *,
    n_sims: int = 20_000,
    seed: int = 42,
) -> dict | None:
    """Oráculo prop-ev en `.venv-vbt`; None si no está disponible."""
    if not Path(VBT_PYTHON).exists():
        return None
    mean_daily = float(returns.mean())
    std_daily = float(returns.std(ddof=1))
    if not np.isfinite(mean_daily) or not np.isfinite(std_daily) or std_daily <= 0:
        return None
    variants = {
        f"{k:g}": {
            "edge_bps": mean_daily * float(k) * 10_000.0,
            "std_bps": std_daily * float(k) * 10_000.0,
        }
        for k in k_values
    }
    payload = {
        "firm": {
            "name": rules.firm,
            "account": float(rules.account_size),
            "target": float(rules.profit_target_pct),
            "daily_dd": float(rules.max_daily_loss_pct),
            "total_dd": float(rules.max_loss_pct),
            "min_days": int(rules.min_trading_days),
            "phases": 1,
            "consistency": rules.consistency_pct,
            "trailing": rules.max_loss_mode != "static",
            "fee": 0.0,
            "profit_split": 0.8,
            "max_days": HORIZON_MAX,
        },
        "variants": variants,
        "trades_per_day": 1,
        "n_sims": int(n_sims),
        "seed": int(seed),
    }
    with tempfile.TemporaryDirectory() as folder:
        payload_path = Path(folder) / "payload.json"
        child_path = Path(folder) / "child.py"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        child_path.write_text(ORACLE_CHILD, encoding="utf-8")
        try:
            completed = subprocess.run(
                [str(VBT_PYTHON), str(child_path), str(payload_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError):
            return None
    if completed.returncode != 0:
        return None
    try:
        data = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return {
        "version": data.get("version"),
        "n_sims": int(n_sims),
        "pass": {str(key): float(value) for key, value in (data.get("pass") or {}).items()},
        "convention": "un objetivo de beneficio (target × account × split)",
    }


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _signed(value, digits: int = 0) -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value):+.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def recommendation(payload: dict) -> dict:
    """k óptima por EV neto, o 'no es EV positivo' si ninguna lo es."""
    best = None
    for row in payload["rows"]:
        ev = row.get("ev_eur")
        if ev is None:
            continue
        if best is None or ev > best["ev_eur"]:
            best = {"k": row["k"], "ev_eur": ev}
    if best is None:
        return {"k": None, "ev_eur": None, "positive": False, "text": "Sin datos"}
    if best["ev_eur"] <= 0:
        return {
            "k": None,
            "ev_eur": best["ev_eur"],
            "positive": False,
            "best_k": best["k"],
            "text": "no es EV positivo a ninguna k",
        }
    return {
        "k": best["k"],
        "ev_eur": best["ev_eur"],
        "positive": True,
        "best_k": best["k"],
        "text": f"k óptima: {best['k']:g}",
    }


def render_report(payload: dict) -> str:
    bot = payload["bot"]
    variant = payload.get("variant") or {}
    rows = payload["rows"]
    rec = payload["recommendation"]
    lines = [
        f"# Barrido de exposición · {bot}",
        "",
        f"- Generado: {payload['generated_at']}",
        f"- Bot: `{bot}` · activo `{payload.get('symbol')}` · "
        f"variante {variant.get('fast')}/{variant.get('slow')} ATR "
        f"{variant.get('stop_atr')}",
        f"- Artefacto: `{payload['artifact']}`",
        f"- Procedencia: {payload.get('artifact_source') or 'artefacto del research'}",
    ]
    verified = payload.get("artifact_verified") or {}
    if verified:
        lines.append(
            "- Verificación contra el run: Sharpe "
            f"{verified.get('sharpe', 0):.3f} · CAGR "
            f"{verified.get('cagr', 0) * 100:.2f}% · MaxDD "
            f"{verified.get('max_drawdown', 0) * 100:.2f}% · "
            f"{verified.get('num_trades', 0)} trades · P(pasar) "
            f"{verified.get('pass_rate', 0):.1%} · "
            f"{verified.get('sample_days', 0)} días"
        )
    lines += [
        f"- Origen: run `{payload.get('run_id')}` · {payload.get('sample_days')} días "
        f"({payload.get('start')} → {payload.get('end')})",
        f"- Muestra: {payload.get('num_trades') if payload.get('num_trades') is not None else 'Sin datos'} "
        f"operaciones · {payload.get('sample_days')} días",
        f"- Reglas: {payload['rules']}",
        f"- MC: {payload['paths']} paths · bloques de {payload['block_size']} · "
        f"seed {payload['seed']}",
        f"- Horizontes: {payload['horizon_120']} días "
        f"({payload['horizon_120_blocks']} bloques de {payload['block_size']}) y "
        f"sin límite (máximo {payload['horizon_max']} días = "
        f"{payload['horizon_max_blocks']} bloques)",
        f"- Economía: cuota {_fmt(payload['economics']['fee_eur'], 0)} EUR · "
        f"split {payload['economics']['profit_split']:.0%} · "
        f"reembolso al pasar: "
        f"{'sí' if payload['economics']['fee_refund_on_pass'] else 'no'} · "
        f"EURUSD {_fmt((payload.get('eurusd') or {}).get('rate'), 5)}",
        f"- Fuente EURUSD: {(payload.get('eurusd') or {}).get('source')} "
        f"({(payload.get('eurusd') or {}).get('as_of')})",
        f"- Fuente reembolso: {payload['economics'].get('refund_source')}",
        "",
        "## Challenge FTMO 100k",
        "",
        "| k | Horizonte | P(pasar) | IC 90 % | P(breach) | Sin resolver | Mediana días | MaxDD mediano | Peor 5 % |",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        ci = row.get("ci90") or {}
        ci_text = (
            f"{ci['low']:.1%} – {ci['high']:.1%}"
            if ci.get("low") is not None and ci.get("high") is not None
            else "—"
        )
        for label, key in (("120 d", "horizon_120"), ("sin límite", "sin_limite")):
            block = row[key]
            lines.append(
                f"| {row['k']:g} | {label} | {block['pass_rate']:.1%} | "
                f"{ci_text if key == 'sin_limite' else '—'} | "
                f"{block['breach_rate']:.1%} | "
                f"{block['timeout_rate']:.1%} | "
                f"{_fmt(block['median_days_to_pass'], 0)} | "
                f"{_fmt(block['median_max_drawdown'] * 100, 1, '%')} | "
                f"{_fmt(block['p5_max_drawdown'] * 100, 1, '%')} |"
            )
    lines += [
        "",
        "## Valor esperado",
        "",
        "| k | P(pasar) sin límite | Pago mes 1 (EUR) | EV neto (EUR) | "
        "EV sin reembolso (EUR) | EV oráculo (EUR) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['k']:g} | {row['sin_limite']['pass_rate']:.1%} | "
            f"{_fmt(row['payout_eur'], 0)} | {_signed(row['ev_eur'], 0)} | "
            f"{_signed(row.get('ev_no_refund_eur'), 0)} | "
            f"{_signed(row['oracle_ev_eur'], 0)} |"
        )
    lines += [
        "",
        "El motor de Monte Carlo avanza un bloque de `block_size` días por",
        "iteración; el horizonte se pasa ya convertido a bloques (120 días =",
        "24 bloques de 5; 750 días = 150 bloques).",
        "",
        "El **pago del mes 1** es el bootstrap de 21 días desde una cuenta ya",
        "fondeada: si el path revienta el diario (5 %) o el total (10 %), paga 0.",
        "El **EV neto** suma la devolución de la cuota cuando se pasa (2-Step:",
        "se devuelve con la primera retirada); **sin reembolso** es la fórmula",
        "anterior, para comparar. El **EV oráculo** usa la convención de prop-ev",
        "(un objetivo de beneficio completo, 10 % × cuenta × split); se muestra",
        "como contraste, no como criterio de decisión.",
        "",
    ]
    oracle = payload.get("oracle")
    if oracle:
        lines += [
            f"## Oráculo prop-ev {oracle.get('version')}",
            "",
            "| k | P(pasar) propio | P(pasar) prop-ev | Diferencia |",
            "|---:|---:|---:|---:|",
        ]
        for row in rows:
            key = f"{row['k']:g}"
            other = (oracle.get("pass") or {}).get(key)
            if other is None:
                continue
            lines.append(
                f"| {row['k']:g} | {row['sin_limite']['pass_rate']:.1%} | "
                f"{other:.1%} | {(row['sin_limite']['pass_rate'] - other) * 100:+.1f} pp |"
            )
        lines += [
            "",
            f"prop-ev simula {oracle.get('n_sims'):,} paths con retornos normales",
            "(edge/std diarios, una operación al día); el motor propio usa",
            "bootstrap por bloques de los retornos reales.",
            "",
        ]
    else:
        lines += ["## Oráculo", "", "Sin oráculo (prop-ev no disponible).", ""]
    comparisons = payload.get("comparison") or []
    conclusion = payload.get("comparison_conclusion") or {}
    if comparisons:
        other = comparisons[0]
        lines += [
            f"## Comparación con `{other.get('bot')}`",
            "",
            f"- {other.get('bot')}: {other.get('num_trades')} operaciones · "
            f"{other.get('sample_days')} días",
            f"- {bot}: {payload.get('num_trades')} operaciones · "
            f"{payload.get('sample_days')} días",
            "",
            f"| k | P(pasar) {other.get('bot')} | IC 90 % | P(pasar) {bot} | IC 90 % |",
            "|---:|---:|---|---:|---|",
        ]
        by_k = {row.get("k"): row for row in (other.get("rows") or [])}
        for row in rows:
            previous = by_k.get(row["k"]) or {}
            prev_ci = previous.get("ci90") or {}
            now_ci = row.get("ci90") or {}
            lines.append(
                f"| {row['k']:g} | "
                f"{(previous.get('pass_rate') or 0):.1%} | "
                f"{prev_ci.get('low', 0):.1%} – {prev_ci.get('high', 0):.1%} | "
                f"{row['sin_limite']['pass_rate']:.1%} | "
                f"{now_ci.get('low', 0):.1%} – {now_ci.get('high', 0):.1%} |"
            )
        lines.append("")
    lines += [
        "## Conclusión",
        "",
        f"**{rec['text']}**"
        + (
            f" · EV {rec['ev_eur']:+.0f} EUR por intento"
            if rec.get("ev_eur") is not None
            else ""
        ),
        "",
    ]
    if conclusion:
        k_before = conclusion.get("k_before")
        k_now = conclusion.get("k_now")
        ratio = conclusion.get("ci_ratio")
        width_now = conclusion.get("ci_width_now")
        width_before = conclusion.get("ci_width_before")
        lines += [
            f"- k óptima con la muestra larga: **{k_now:g}**"
            if k_now is not None
            else "- k óptima con la muestra larga: Sin datos",
            f"- k óptima con la muestra corta: **{k_before:g}**"
            if k_before is not None
            else "- k óptima con la muestra corta: Sin datos",
            (
                f"- IC 90 % mediano: {width_before * 100:.1f} pp → "
                f"{width_now * 100:.1f} pp (factor {ratio:.2f})"
                if width_now is not None and width_before
                else "- IC 90 %: Sin datos"
            ),
            f"- Operaciones: {conclusion.get('trades_before')} → "
            f"{conclusion.get('trades_now')} · días: "
            f"{conclusion.get('days_before')} → {conclusion.get('days_now')}",
            "",
        ]
        if (
            k_now is not None
            and k_before is not None
            and abs(float(k_now) - float(k_before)) > 1e-9
        ):
            lines.append(
                f"La k cambia de {k_before:g} a {k_now:g} con la muestra larga."
            )
        elif k_now is not None:
            lines.append("La k **no cambia** con la muestra larga: se mantiene.")
        lines.append("")
    adopted = payload.get("adopted_k")
    if adopted is not None:
        adopted_row = next(
            (row for row in rows if abs(float(row["k"]) - float(adopted)) < 1e-9),
            None,
        )
        if adopted_row is not None:
            breach = adopted_row["sin_limite"]["breach_rate"]
            lines += [
                f"- Decisión adoptada: **k={adopted:g}** · óptima: "
                f"**{rec.get('best_k') if rec.get('best_k') is not None else 'Sin datos'}**"
                + (
                    " (no coincide; el óptimo de EV no es la elección de riesgo)"
                    if rec.get("best_k") is not None
                    and abs(float(rec["best_k"]) - float(adopted)) > 1e-9
                    else " (coincide)"
                ),
                f"- En k={adopted:g}: EV {_signed(adopted_row.get('ev_eur'), 0)} EUR · "
                f"breach {breach:.1%} · peor 5 % MaxDD "
                f"{adopted_row['sin_limite']['p5_max_drawdown'] * 100:.1f}%",
                "",
            ]
    if not rec.get("positive"):
        lines += [
            "Con la cuota de 540 EUR y el beneficio del primer mes fondeado, el",
            "challenge no tiene EV positivo a ninguna exposición: la probabilidad",
            "de pasar no compensa la cuota. No se activa nada y no se sube la",
            "exposición para 'compensar'.",
            "",
        ]
    else:
        lines += [
            "El óptimo es plano y el EV depende del modelo del mes 1. Subir k",
            "mejora el EV pero también el breach y el peor 5 % de MaxDD. Esto es",
            "un estudio: no se cambia la exposición de ningún bot ni se activa",
            "nada.",
            "",
        ]
    lines += [
        "> Solo lectura: no envía órdenes, no activa bots y no cambia la",
        "> estrategia. El artefacto es el del research (reconstruido y",
        "> verificado si el run no lo guardó).",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict, out_dir: Path, name: str = "exposure_sweep") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{name}.json"
    md_path = out_dir / f"{name}.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _report_name(bot: str) -> str:
    if bot == "us100-trend-d1":
        return "exposure_sweep"
    return f"exposure_sweep_{bot.replace('-', '_')}"


def _load_comparison(bot: str, out: Path) -> dict | None:
    """Payload de un barrido anterior para la comparación lado a lado."""
    path = out / f"{_report_name(bot)}.json"
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return {
        "bot": bot,
        "num_trades": doc.get("num_trades"),
        "sample_days": doc.get("sample_days"),
        "recommendation": doc.get("recommendation"),
        "rows": [
            {
                "k": row.get("k"),
                "pass_rate": (row.get("sin_limite") or {}).get("pass_rate"),
                "ci90": row.get("ci90"),
                "ev_eur": row.get("ev_eur"),
                "ev_no_refund_eur": row.get("ev_no_refund_eur"),
            }
            for row in (doc.get("rows") or [])
        ],
    }


def _ci_width(rows: list[dict]) -> float | None:
    widths = [
        float(row["ci90"]["high"]) - float(row["ci90"]["low"])
        for row in rows
        if row.get("ci90")
        and row["ci90"].get("high") is not None
        and row["ci90"].get("low") is not None
    ]
    return float(np.median(widths)) if widths else None


def comparison_conclusion(payload: dict, comparisons: list[dict]) -> dict | None:
    """k óptima y estrechamiento del IC frente a la muestra corta."""
    if not comparisons:
        return None
    other = comparisons[0]
    rec = payload.get("recommendation") or {}
    other_rec = other.get("recommendation") or {}
    width_now = _ci_width(payload.get("rows") or [])
    width_before = _ci_width(other.get("rows") or [])
    ratio = (
        width_now / width_before
        if width_now is not None and width_before not in (None, 0)
        else None
    )
    return {
        "bot": other.get("bot"),
        "k_now": rec.get("best_k"),
        "k_before": other_rec.get("best_k"),
        "trades_now": payload.get("num_trades"),
        "trades_before": other.get("num_trades"),
        "days_now": payload.get("sample_days"),
        "days_before": other.get("sample_days"),
        "ci_width_now": width_now,
        "ci_width_before": width_before,
        "ci_ratio": ratio,
    }


def run_sweep(
    bot: str,
    *,
    out_dir: str | Path | None = None,
    artifact: str | Path | None = None,
    cache_dir: str | Path | None = None,
    rules: PropRules | None = None,
    k_values: tuple[float, ...] = K_VALUES,
    paths: int = PATHS,
    seed: int = SEED,
    block: int = BLOCK,
    fee_eur: float | None = None,
    split: float | None = None,
    fee_refund_on_pass: bool | None = None,
    oracle: bool = True,
    bootstrap: int = 200,
    bootstrap_paths: int = 500,
    name: str | None = None,
    compare_with: tuple[str, ...] = (),
    adopted_k: float | None = None,
) -> dict:
    from .config import get_settings
    from .prop.rules import from_yaml

    settings = get_settings()
    out = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "swing_cfd"
    rules = rules or from_yaml(
        settings.prop.firm, settings.prop.phase, settings.prop.account_size
    )
    loaded = load_artifact(bot, out, artifact)
    rate = eurusd_rate(cache_dir or settings.data.cache_dir)
    payload = sweep(
        loaded["returns"],
        rules,
        k_values=k_values,
        paths=paths,
        seed=seed,
        block=block,
        fee_eur=fee_eur,
        split=split,
        fee_refund_on_pass=fee_refund_on_pass,
        eurusd=rate.get("rate"),
        oracle=oracle,
        bootstrap=bootstrap,
        bootstrap_paths=bootstrap_paths,
    )
    meta = loaded.get("meta") or {}
    verified = meta.get("verified") or {}
    num_trades = meta.get("num_trades") or verified.get("num_trades")
    payload.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bot": bot,
            "symbol": meta.get("symbol"),
            "variant": meta.get("params"),
            "run_id": meta.get("run_id"),
            "artifact": loaded["path"],
            "artifact_source": meta.get("source"),
            "artifact_verified": verified,
            "num_trades": num_trades,
            "sample_days": int(len(loaded["returns"])),
            "start": str(loaded["returns"].index[0].date()),
            "end": str(loaded["returns"].index[-1].date()),
            "rules": rules.describe(),
            "eurusd": rate,
            "adopted_k": adopted_k,
        }
    )
    comparisons = [
        item
        for item in (_load_comparison(other, out) for other in compare_with)
        if item is not None
    ]
    payload["comparison"] = comparisons
    payload["recommendation"] = recommendation(payload)
    payload["comparison_conclusion"] = comparison_conclusion(payload, comparisons)
    payload["files"] = write_report(
        payload, out, name or _report_name(bot)
    )
    return payload


__all__ = [
    "DEFAULT_FEE_EUR",
    "DEFAULT_SPLIT",
    "HORIZON_120",
    "HORIZON_MAX",
    "K_VALUES",
    "SweepError",
    "artifact_file",
    "eurusd_rate",
    "funded_month_payout",
    "load_artifact",
    "recommendation",
    "run_sweep",
    "save_artifact",
    "sweep",
    "write_report",
]
