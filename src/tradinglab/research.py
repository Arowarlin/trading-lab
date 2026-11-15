from __future__ import annotations

import hashlib
import itertools
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as data_mod
from .backtest import run as run_backtest
from .datacheck import check_frame
from .prop.rules import PropRules
from .prop.simulator import monte_carlo
from .stats import dsr_from_returns, period_sharpe
from .strategies import STRATEGIES
from .validation import cscv_pbo, returns_matrix
from .walkforward import regime_gate, regime_report, walk_forward

# Rejillas deliberadamente pequeñas: el objetivo es encontrar candidatos
# robustos, no hacer fuerza bruta sobre miles de combinaciones (sobreajuste).
GRIDS: dict[str, dict[str, list]] = {
    "trend": {"fast": [20, 50], "slow": [100, 200], "regime": [200]},
    "trend-ls": {"fast": [20, 50], "slow": [100, 200], "regime": [200]},
    "meanrev": {
        "window": [10, 20],
        "entry_z": [-1.5, -2.0],
        "exit_z": [0.0],
        "max_hold": [5, 10],
    },
    "sector_momentum": {
        "lookback": [20, 60, 120],
        "vol_window": [10, 20],
        "vol_mult": [1.0, 1.25],
    },
    "overnight_reversal": {
        "long_only": [False, True],
    },
}

DEFAULT_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "IWM", "EURUSD=X"]


@dataclass
class ResearchConfig:
    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    strategies: list[str] = field(default_factory=lambda: list(GRIDS))
    start: str = "2015-01-01"
    end: str = ""
    account_size: float = 100_000.0
    paths: int = 2_000
    horizon: int = 120
    block_size: int = 5
    min_trades: int = 20
    # Las variantes con pocas operaciones no se proponen, pero se listan como
    # "casi propuestas" para revisarlas a mano si están cerca del umbral.
    near_miss_slack: int = 5
    min_pass: float = 0.35
    min_oos_pass: float = 0.25
    min_dsr: float = 0.90
    wf_folds: int = 4
    min_wf_positive: int = 2
    wf_train_len: int = 504
    wf_test_len: int = 126
    # CSCV: 16 bloques -> 12.870 combinaciones. Se puede muestrear para tests.
    pbo_slices: int = 16
    pbo_max_combinations: int | None = None
    pbo_seed: int = 0
    max_pbo: float = 0.30
    regime_years: tuple[int, ...] = (2018, 2020, 2022)
    regime_min_obs: int = 20
    regime_min_return: float = 0.0
    max_breach: float = 0.15
    holdout_fraction: float = 0.30
    exposures: list[float] = field(default_factory=lambda: [1.0, 0.5])
    commission_bps: float = 1.0
    slippage_bps: float = 5.0


def _combos(strategy: str) -> list[dict]:
    grid = GRIDS.get(strategy)
    if not grid:
        raise ValueError(f"sin rejilla para la estrategia '{strategy}'")
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _score(pass_rate: float, breach_rate: float, sharpe: float) -> float:
    """Ventaja neta contra las reglas, con el Sharpe como desempate suave."""
    return (pass_rate - breach_rate) + 0.01 * max(min(sharpe, 3.0), -3.0)




def _block_metrics(returns, blocks: int) -> list[dict]:
    r = returns.dropna().astype(float)
    if blocks < 2 or len(r) < blocks * 5:
        return []
    chunks = np.array_split(r.to_numpy(), blocks)
    out = []
    for chunk in chunks:
        if len(chunk) == 0:
            continue
        total = float(np.prod(1.0 + chunk) - 1.0)
        std = float(np.std(chunk, ddof=1)) if len(chunk) > 1 else 0.0
        sharpe = float(np.mean(chunk) / std * np.sqrt(252)) if std > 0 else 0.0
        out.append({"return": total, "sharpe": sharpe})
    return out


def _year_returns(returns) -> dict[str, float]:
    r = returns.dropna()
    if not hasattr(r.index, "year"):
        return {}
    out = {}
    for year, group in r.groupby(r.index.year):
        out[str(int(year))] = float((1.0 + group).prod() - 1.0)
    return out


def _with_benchmark_regimes(
    regime_payload: dict,
    benchmark_years: dict[str, dict],
) -> dict:
    """Añade drawdown/retorno de buy&hold a cada régimen (informativo)."""
    for year, stats in (regime_payload.get("years") or {}).items():
        benchmark = benchmark_years.get(str(year)) or {}
        stats["buy_hold_max_drawdown"] = benchmark.get("max_drawdown")
        stats["buy_hold_total_return"] = benchmark.get("total_return")
    return regime_payload


def _aligned_returns(
    series_by_variant: dict[str, pd.Series],
) -> tuple[np.ndarray, list[str]] | None:
    """Construye la matriz común (T, N) de retornos diarios netos.

    Alineación explícita y documentada:
    - se usa la **intersección** de fechas de todas las variantes;
    - se eliminan NaN/inf y cualquier fila incompleta (`dropna`);
    - no se rellena con ceros ni se inventan retornos: una fecha sin dato
      simplemente se recorta del tramo común.

    Si quedan menos de dos filas o menos de dos variantes, no hay matriz
    válida y la validación devuelve `None`.
    """
    if len(series_by_variant) < 2:
        return None
    cleaned = {
        name: series.astype(float).replace([np.inf, -np.inf], np.nan)
        for name, series in series_by_variant.items()
    }
    frame = pd.concat(cleaned, axis=1, join="inner").dropna()
    if len(frame) < 2:
        return None
    return returns_matrix({name: frame[name].to_numpy(dtype=float) for name in frame.columns})


def _pbo_payload(
    series_by_variant: dict[str, pd.Series],
    cfg: ResearchConfig,
    *,
    scope: str,
) -> dict | None:
    """Calcula CSCV/PBO y devuelve un dict serializable, o None si no aplica."""
    aligned = _aligned_returns(series_by_variant)
    if aligned is None:
        return None
    matrix, _names = aligned
    try:
        result = cscv_pbo(
            matrix,
            n_slices=cfg.pbo_slices,
            max_combinations=cfg.pbo_max_combinations,
            seed=cfg.pbo_seed,
        )
    except ValueError:
        # Muestra insuficiente o columnas inválidas: no se inventa un PBO.
        return None
    payload = result.to_dict()
    payload["verdict"] = result.verdict(cfg.max_pbo)
    payload["scope"] = scope
    payload["max_pbo"] = cfg.max_pbo
    # Diagnóstico informativo: variantes con retornos casi constantes.
    # No altera el PBO ni el criterio de propuesta.
    stds = np.std(matrix, axis=0, ddof=1)
    flat_threshold = 1e-10
    flat_mask = stds <= flat_threshold
    flat_count = int(np.sum(flat_mask))
    nonflat_count = int(matrix.shape[1] - flat_count)
    payload["flat_variants"] = flat_count
    payload["flat_std_threshold"] = flat_threshold
    payload["n_variants_nonflat"] = nonflat_count
    payload["pbo_excluding_flat"] = result.pbo
    payload["verdict_excluding_flat"] = result.verdict(cfg.max_pbo)
    if flat_count and nonflat_count >= 2:
        try:
            nonflat = cscv_pbo(
                matrix[:, ~flat_mask],
                n_slices=cfg.pbo_slices,
                max_combinations=cfg.pbo_max_combinations,
                seed=cfg.pbo_seed,
            )
            payload["pbo_excluding_flat"] = nonflat.pbo
            payload["verdict_excluding_flat"] = nonflat.verdict(cfg.max_pbo)
            payload["n_combinations_excluding_flat"] = nonflat.n_combinations
        except ValueError:
            payload["pbo_excluding_flat"] = None
            payload["verdict_excluding_flat"] = None
    elif nonflat_count < 2:
        payload["pbo_excluding_flat"] = None
        payload["verdict_excluding_flat"] = None
    return payload


def _walk_forward_payload(
    series_by_variant: dict[str, pd.Series],
    cfg: ResearchConfig,
) -> dict | None:
    """Walk-forward global sobre la misma matriz alineada que usa el PBO."""
    aligned = _aligned_returns(series_by_variant)
    if aligned is None:
        return None
    matrix, _names = aligned
    try:
        result = walk_forward(
            matrix,
            train_len=cfg.wf_train_len,
            test_len=cfg.wf_test_len,
        )
    except ValueError:
        return None
    payload = result.to_dict()
    payload["verdict"] = result.verdict()
    payload["scope"] = "global"
    return payload


def run_research(
    cfg: ResearchConfig,
    rules: PropRules,
    cache_dir: str | Path,
    *,
    artifacts_dir: str | Path | None = None,
    extra_trials: int = 0,
) -> dict:
    """Escanea activos × estrategias × parámetros y puntúa contra las reglas.

    Si `artifacts_dir` se indica, guarda la curva de equity de cada resultado
    y la de buy&hold del mismo activo en parquet. No cambia ningún criterio.
    """
    end = cfg.end or datetime.now(timezone.utc).date().isoformat()
    results: list[dict] = []
    result_returns: list[pd.Series] = []
    errors: list[dict] = []
    datachecks: dict[str, dict] = {}
    artifact_root = Path(artifacts_dir) if artifacts_dir is not None else None
    if artifact_root is not None:
        artifact_root.mkdir(parents=True, exist_ok=True)
    # Retornos diarios netos por variante (sin escalar por exposición: el
    # Sharpe es invariante a la escala). No se serializan en el reporte.
    daily_returns: dict[str, pd.Series] = {}
    daily_returns_by_symbol: dict[str, dict[str, pd.Series]] = defaultdict(dict)

    for symbol in cfg.symbols:
        try:
            df = data_mod.fetch(symbol, cfg.start, end, cache_dir)
        except Exception as exc:  # un símbolo roto no debe tumbar el barrido
            errors.append({"symbol": symbol, "error": str(exc)[:300]})
            continue

        if len(df) < 260:
            errors.append({"symbol": symbol, "error": f"histórico insuficiente ({len(df)} barras)"})
            continue

        cache_file = data_mod.cache_path(cache_dir, symbol, cfg.start, end)
        datacheck = check_frame(
            df,
            symbol,
            timeframe="1d",
            cache_path=str(cache_file),
        )
        datachecks[symbol] = datacheck
        if datacheck["status"] == "falla":
            errors.append(
                {
                    "symbol": symbol,
                    "error": "datacheck falla: " + "; ".join(datacheck["reasons"]),
                    "datacheck": datacheck,
                }
            )
            continue

        bh_returns = df["close"].astype(float).pct_change().fillna(0.0)
        bh_regime = regime_report(
            bh_returns,
            years=cfg.regime_years,
            min_obs=cfg.regime_min_obs,
        )
        bh_regime_years = bh_regime.to_dict().get("years") or {}
        starting_cash = float(rules.account_size)
        bh_equity = starting_cash * df["close"].astype(float) / float(df["close"].iloc[0])

        for strategy in cfg.strategies:
            for params in _combos(strategy):
                try:
                    sig = STRATEGIES[strategy](df, **params)
                    bt = run_backtest(
                        df,
                        sig.target,
                        starting_cash=rules.account_size,
                        commission_bps=cfg.commission_bps,
                        slippage_bps=cfg.slippage_bps,
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "symbol": symbol,
                            "strategy": strategy,
                            "params": params,
                            "error": str(exc)[:300],
                        }
                    )
                    continue

                m = bt.metrics
                sharpe = float(m.get("sharpe", 0.0))
                cagr = float(m.get("cagr", 0.0))
                returns = bt.returns
                skew = float(returns.skew()) if len(returns) > 2 else 0.0
                kurtosis = float(returns.kurt()) + 3.0 if len(returns) > 3 else 3.0
                sample_days = len(returns)
                wf_blocks = _block_metrics(returns, cfg.wf_folds)
                wf_returns = [b["return"] for b in wf_blocks]
                year_returns = _year_returns(returns)
                regime = regime_report(
                    returns,
                    years=cfg.regime_years,
                    min_obs=cfg.regime_min_obs,
                )
                regime_check = regime_gate(regime, min_return=cfg.regime_min_return)
                regime_payload = _with_benchmark_regimes(
                    regime.to_dict(), bh_regime_years
                )
                variant_key = f"{strategy}|{json.dumps(params, sort_keys=True)}"
                daily_returns[f"{symbol}|{variant_key}"] = bt.returns
                daily_returns_by_symbol[symbol][variant_key] = bt.returns
                split = max(1, int(len(bt.returns) * (1.0 - cfg.holdout_fraction)))
                oos_returns = bt.returns.iloc[split:]
                oos_start = (
                    str(bt.equity.index[split].date()) if split < len(bt.equity) else None
                )
                oos_end = str(bt.equity.index[-1].date())
                for exposure in cfg.exposures:
                    try:
                        mc = monte_carlo(
                            rules,
                            bt.returns * exposure,
                            n_paths=cfg.paths,
                            horizon=cfg.horizon,
                            block_size=cfg.block_size,
                        )
                        oos = (
                            monte_carlo(
                                rules,
                                oos_returns * exposure,
                                n_paths=max(200, cfg.paths // 2),
                                horizon=cfg.horizon,
                                block_size=cfg.block_size,
                            )
                            if len(oos_returns) >= 120
                            else None
                        )
                    except Exception as exc:
                        errors.append(
                            {
                                "symbol": symbol,
                                "strategy": strategy,
                                "params": params,
                                "exposure": exposure,
                                "error": str(exc)[:300],
                            }
                        )
                        continue

                    pass_rate = float(mc["pass_rate"])
                    breach_rate = float(mc["breach_rate"])
                    artifact_rel = None
                    artifact_rows = None
                    if artifact_root is not None:
                        digest = hashlib.sha256(
                            (
                                f"{symbol}|{strategy}|{exposure:g}|"
                                f"{json.dumps(params, sort_keys=True)}"
                            ).encode("utf-8")
                        ).hexdigest()[:16]
                        artifact_rel = f"artifacts/{digest}.parquet"
                        frame = pd.DataFrame(
                            {
                                "equity": bt.equity.astype(float),
                                "buy_hold": bh_equity.reindex(bt.equity.index).astype(float),
                            }
                        ).dropna()
                        if not frame.empty:
                            frame.index.name = "ts"
                            frame.to_parquet(artifact_root / f"{digest}.parquet")
                            artifact_rows = len(frame)
                        if bt.trade_pnls:
                            trades_frame = pd.DataFrame(
                                {
                                    "pnl": bt.trade_pnls,
                                    "day": bt.trade_days
                                    or [""] * len(bt.trade_pnls),
                                }
                            )
                            trades_frame.to_parquet(
                                artifact_root / f"{digest}.trades.parquet"
                            )
                    results.append(
                        {
                            "symbol": symbol,
                            "strategy": strategy,
                            "params": params,
                            "exposure": exposure,
                            "sharpe": sharpe,
                            "cagr": cagr * exposure,
                            "max_drawdown": float(m.get("max_drawdown", 0.0)) * exposure,
                            "max_drawdown_usd": m.get("max_drawdown_usd"),
                            "num_trades": int(m.get("num_trades", 0)),
                            "win_rate": float(m.get("win_rate", 0.0)),
                            "exposure_avg": float(m.get("exposure", 0.0)),
                            "sqn": m.get("sqn"),
                            "recovery_factor": m.get("recovery_factor"),
                            "risk_of_ruin": m.get("risk_of_ruin"),
                            "risk_of_ruin_assumptions": m.get("risk_of_ruin_assumptions"),
                            "metrics_warning": m.get("metrics_warning"),
                            "pass_rate": pass_rate,
                            "pass_ci95": list(mc["pass_ci95"]),
                            "breach_rate": breach_rate,
                            "timeout_rate": float(mc["timeout_rate"]),
                            "median_days_to_pass": mc["median_days_to_pass"],
                            "oos_pass_rate": float(oos["pass_rate"]) if oos else None,
                            "oos_breach_rate": float(oos["breach_rate"]) if oos else None,
                            "oos_start": oos_start,
                            "oos_end": oos_end,
                            "sample_days": sample_days,
                            "skew": skew,
                            "kurtosis": kurtosis,
                            "wf_blocks": wf_blocks,
                            "wf_positive_folds": sum(1 for x in wf_returns if x > 0),
                            "wf_min_return": min(wf_returns) if wf_returns else None,
                            "wf_median_return": statistics.median(wf_returns) if wf_returns else None,
                            "regime_report": regime_payload,
                            "regime_gate": regime_check.to_dict(),
                            "year_returns": year_returns,
                            "datacheck": datacheck,
                            "artifact": artifact_rel,
                            "artifact_rows": artifact_rows,
                            "score": _score(pass_rate, breach_rate, sharpe),
                        }
                    )
                    result_returns.append(returns)

    results.sort(key=lambda r: r["score"], reverse=True)

    # Estabilidad de familia: mediana de pass_rate entre las variantes de
    # parámetros del mismo activo/estrategia/escala. Evita proponer un pico
    # aislado que solo funciona con una combinación concreta.
    families: dict[tuple, list[float]] = defaultdict(list)
    for r in results:
        families[(r["symbol"], r["strategy"], r["exposure"])].append(r["pass_rate"])
    for r in results:
        values = families[(r["symbol"], r["strategy"], r["exposure"])]
        r["family_size"] = len(values)
        r["family_median_pass"] = statistics.median(values)

    trial_srs = [period_sharpe(series) for series in daily_returns.values()]
    sr_std = statistics.pstdev(trial_srs) if len(trial_srs) > 1 else 0.0
    n_trials = len(results) + max(0, int(extra_trials))
    for r, returns in zip(results, result_returns):
        payload = dsr_from_returns(
            returns, trial_srs, n_trials, periods_per_year=252
        )
        r["dsr"] = payload["dsr"]
        r["dsr_v2"] = payload["dsr"]
        r["metric_version"] = payload["metric_version"]
        r["dsr_n_trials"] = n_trials
        r["dsr_trial_sr_std"] = payload["trial_sr_std_period"]
        r["dsr_meta"] = {
            "sr_period": payload["sr_period"],
            "sr0_period": payload["sr0_period"],
            "skew": payload["skew"],
            "kurt": payload["kurt"],
            "annualized_sr": payload["annualized_sr"],
        }

    pbo_by_symbol: dict[str, dict] = {}
    for symbol, series_by_variant in daily_returns_by_symbol.items():
        payload = _pbo_payload(series_by_variant, cfg, scope=symbol)
        if payload is not None:
            pbo_by_symbol[symbol] = payload
    pbo = _pbo_payload(daily_returns, cfg, scope="global")
    # Sin PBO calculable no se proponen bots: el sobreajuste no está validado.
    pbo_ok = pbo is not None and pbo["pbo"] <= cfg.max_pbo
    pbo_symbol_ok = {
        symbol: payload["pbo"] <= cfg.max_pbo for symbol, payload in pbo_by_symbol.items()
    }
    wf_payload = _walk_forward_payload(daily_returns, cfg)
    wf_ok = wf_payload is not None and wf_payload["verdict"] == "ok"

    def base_eligible(r: dict) -> bool:
        """Filtros que ya existían antes de PBO/WF/regímenes."""
        return (
            r["pass_rate"] >= cfg.min_pass
            and r["breach_rate"] <= cfg.max_breach
            and (r["oos_pass_rate"] is None or r["oos_pass_rate"] >= cfg.min_oos_pass)
            and r["sharpe"] > 0
            and r["family_median_pass"] >= cfg.min_pass
            and (r.get("dsr") is not None and r["dsr"] >= cfg.min_dsr)
            and r.get("wf_positive_folds", 0) >= cfg.min_wf_positive
            and (r.get("datacheck") or {}).get("status") != "falla"
        )

    def validation_failures(r: dict) -> list[str]:
        """Motivos nuevos: datacheck, PBO global/activo, walk-forward y regímenes."""
        failures: list[str] = []
        datacheck = r.get("datacheck") or {}
        if datacheck.get("status") == "falla":
            failures.append(
                "datacheck: " + "; ".join(datacheck.get("reasons") or ["falla"])
            )
        if not pbo_ok:
            failures.append(
                f"PBO global no disponible o > {cfg.max_pbo:.0%}"
            )
        elif not pbo_symbol_ok.get(r["symbol"], True):
            failures.append(
                f"PBO de {r['symbol']} > {cfg.max_pbo:.0%}"
            )
        if not wf_ok:
            failures.append("walk-forward global no aprobado")
        gate = r.get("regime_gate") or {}
        if not gate.get("passed"):
            reasons = gate.get("reasons") or ["régimen no aprobado"]
            failures.append("regímenes: " + "; ".join(reasons))
        return failures

    def core_eligible(r: dict) -> bool:
        return base_eligible(r) and not validation_failures(r)

    proposals = [r for r in results if core_eligible(r) and r["num_trades"] >= cfg.min_trades]

    min_watch_trades = max(0, cfg.min_trades - cfg.near_miss_slack)
    validation_misses = [
        r
        for r in results
        if base_eligible(r)
        and r["num_trades"] >= min_watch_trades
        and validation_failures(r)
    ]
    few_trades = [
        r
        for r in results
        if base_eligible(r)
        and not validation_failures(r)
        and min_watch_trades <= r["num_trades"] < cfg.min_trades
    ]
    near_miss_rows: list[tuple[dict, str, str]] = []
    for r in validation_misses[:8]:
        note = "No accionable: falla validación nueva: " + "; ".join(validation_failures(r))
        near_miss_rows.append((r, "watchlist_validation", note))
    for r in few_trades[:5]:
        note = f"No accionable: {r['num_trades']} operaciones < mínimo {cfg.min_trades}."
        near_miss_rows.append((r, "watchlist_few_trades", note))
    seen: set[str] = set()
    near_misses: list[tuple[dict, str, str]] = []
    for row in sorted(near_miss_rows, key=lambda item: item[0]["score"], reverse=True):
        r, status, note = row
        rid = (
            f"{r['symbol']}:{r['strategy']}:x{r['exposure']:g}:"
            f"{json.dumps(r['params'], sort_keys=True)}"
        )
        if rid in seen:
            continue
        seen.add(rid)
        near_misses.append(row)
    near_misses = near_misses[:10]

    def _public(r: dict, status: str, note: str) -> dict:
        return {
            "id": (
                f"{r['symbol']}:{r['strategy']}:x{r['exposure']:g}:"
                f"{json.dumps(r['params'], sort_keys=True)}"
            ),
            "symbol": r["symbol"],
            "strategy": r["strategy"],
            "params": r["params"],
            "exposure": r["exposure"],
            "score": r["score"],
            "pass_rate": r["pass_rate"],
            "breach_rate": r["breach_rate"],
            "oos_pass_rate": r["oos_pass_rate"],
            "oos_breach_rate": r["oos_breach_rate"],
            "num_trades": r["num_trades"],
            "family_median_pass": r["family_median_pass"],
            "dsr": r.get("dsr"),
            "dsr_n_trials": r.get("dsr_n_trials"),
            "dsr_trial_sr_std": r.get("dsr_trial_sr_std"),
            "wf_positive_folds": r.get("wf_positive_folds"),
            "wf_folds": cfg.wf_folds,
            "pbo_symbol": pbo_by_symbol.get(r["symbol"], {}).get("pbo"),
            "pbo_global": pbo["pbo"] if pbo else None,
            "walk_forward_verdict": wf_payload["verdict"] if wf_payload else None,
            "walk_forward_stitched_sharpe": (
                wf_payload["stitched_sharpe"] if wf_payload else None
            ),
            "regime_report": r.get("regime_report") or {},
            "regime_gate": r.get("regime_gate") or {},
            "validation_failures": validation_failures(r),
            "year_returns": r.get("year_returns") or {},
            "artifact": r.get("artifact"),
            "artifact_rows": r.get("artifact_rows"),
            "max_drawdown": r["max_drawdown"],
            "sharpe": r["sharpe"],
            "sqn": r.get("sqn"),
            "recovery_factor": r.get("recovery_factor"),
            "risk_of_ruin": r.get("risk_of_ruin"),
            "risk_of_ruin_assumptions": r.get("risk_of_ruin_assumptions"),
            "metrics_warning": r.get("metrics_warning"),
            "status": status,
            "datacheck_status": (r.get("datacheck") or {}).get("status"),
            "datacheck_reasons": (r.get("datacheck") or {}).get("reasons") or [],
            "enabled": False,
            "note": note,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules": rules.describe(),
        "rules_meta": asdict(rules),
        "learning_trials": max(0, int(extra_trials)),
        "pbo": pbo,
        "pbo_ok": pbo_ok,
        "pbo_by_symbol": pbo_by_symbol,
        "walk_forward": wf_payload,
        "walk_forward_ok": wf_ok,
        "dsr_n_trials": n_trials,
        "dsr_trial_sr_std": sr_std,
        "config": {
            "symbols": cfg.symbols,
            "strategies": cfg.strategies,
            "start": cfg.start,
            "end": end,
            "paths": cfg.paths,
            "horizon": cfg.horizon,
            "block_size": cfg.block_size,
            "min_trades": cfg.min_trades,
            "near_miss_slack": cfg.near_miss_slack,
            "min_pass": cfg.min_pass,
            "min_oos_pass": cfg.min_oos_pass,
            "min_dsr": cfg.min_dsr,
            "wf_folds": cfg.wf_folds,
            "min_wf_positive": cfg.min_wf_positive,
            "wf_train_len": cfg.wf_train_len,
            "wf_test_len": cfg.wf_test_len,
            "pbo_slices": cfg.pbo_slices,
            "pbo_max_combinations": cfg.pbo_max_combinations,
            "pbo_seed": cfg.pbo_seed,
            "max_pbo": cfg.max_pbo,
            "regime_years": list(cfg.regime_years),
            "regime_min_obs": cfg.regime_min_obs,
            "regime_min_return": cfg.regime_min_return,
            "max_breach": cfg.max_breach,
            "holdout_fraction": cfg.holdout_fraction,
            "exposures": cfg.exposures,
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
            "family_stability": True,
        },
        "results": results,
        "datachecks": datachecks,
        "proposals": [
            _public(
                p,
                "proposed",
                "Requiere aprobación humana; el bucle no activa bots solo.",
            )
            for p in proposals
        ],
        "near_misses": [
            _public(p, status, note) for p, status, note in near_misses
        ],
        "errors": errors,
        "candidates": len(results),
    }


def render_markdown(report: dict, top: int = 25) -> str:
    cfg = report["config"]
    top_result = report["results"][0] if report.get("results") else {}
    oos_start = top_result.get("oos_start")
    oos_end = top_result.get("oos_end")
    oos_range = f"{oos_start} → {oos_end}" if oos_start else "último tramo de la muestra"
    warning = (
        "> Aviso: al elegir el mejor de cientos de variantes el resultado está sesgado "
        f"al alza. La columna OOS es el filtro mínimo de estabilidad, no una garantía: "
        f"el tramo reservado ({oos_range}) puede caer en un régimen favorable y dar "
        "tasas muy altas que no se repetirán en otro mercado."
    )
    pbo = report.get("pbo")
    pbo_line = (
        f"- PBO (CSCV): {pbo['pbo']:.1%} · veredicto {pbo.get('verdict', '—')} · "
        f"{pbo.get('n_variants', 0)} variantes · {pbo.get('n_slices', 0)} bloques · "
        f"{pbo.get('n_combinations', 0):,} combinaciones"
        if pbo
        else "- PBO (CSCV): no disponible (muestra insuficiente o <2 variantes)"
    )
    wf = report.get("walk_forward")
    wf_line = (
        f"- Walk-forward global: veredicto {wf.get('verdict', '—')} · "
        f"Sharpe stitched {wf['stitched_sharpe']:,.2f} · "
        f"folds positivos {wf['frac_positive']:.0%} · "
        f"eficiencia {wf['efficiency']:,.2f} · "
        f"rank mediano {wf['median_rank_pct']:.0%} · "
        f"estabilidad {wf['stability']:.0%} · {wf['n_folds']} folds"
        if wf
        else "- Walk-forward global: no disponible (muestra insuficiente)"
    )
    lines = [
        "# Investigación de estrategias",
        "",
        f"- Generado: {report['generated_at']}",
        f"- Reglas: {report['rules']}",
        f"- Activos: {', '.join(cfg['symbols'])}",
        f"- Estrategias: {', '.join(cfg['strategies'])}",
        f"- Muestra: {cfg['start']} → {cfg['end']} · "
        f"{cfg['paths']} paths · horizonte {cfg['horizon']} días · bloque {cfg['block_size']}",
        f"- Escalas de exposición: {', '.join(f'{x:g}' for x in cfg['exposures'])}",
        f"- Validación out-of-sample: último {cfg['holdout_fraction']:.0%} de la muestra",
        f"- Ventana OOS: {oos_range}",
        f"- Variantes evaluadas: {report['candidates']}",
        f"- Holdout: {(report.get('holdout_usage') or {}).get('reads', 0)} lecturas / "
        f"{(report.get('holdout_usage') or {}).get('configs', 0)} configuraciones",
        f"- Walk-forward clásico: {cfg.get('wf_folds', 4)} bloques",
        pbo_line,
        wf_line,
        f"- DSR: n_trials = {report.get('dsr_n_trials', 0):,} · "
        f"σ(Sharpe de las pruebas) = {report.get('dsr_trial_sr_std', 0):.4f}",
        "",
        warning,
        "",
        "## Ranking",
        "",
        "| # | Activo | Estrategia | Parámetros | Escala | Sharpe | CAGR | MaxDD | Trades | Pasa | Revienta | Pasa OOS | Score | DSR | WF | Gate |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    datachecks = report.get("datachecks") or {}
    if datachecks:
        lines += [
            "",
            "## Calidad de datos",
            "",
            "| Activo | Estado | Motivo |",
            "|---|---|---|",
        ]
        for symbol, dc in sorted(datachecks.items()):
            reasons = "; ".join(dc.get("reasons") or []) or "sin avisos"
            lines.append(f"| {symbol} | {dc.get('status', 'Sin datos')} | {reasons} |")

    quantstats = report.get("quantstats") or {}
    if quantstats.get("reports"):
        lines += ["", "## Informes QuantStats", ""]
        for row in quantstats["reports"]:
            lines.append(
                f"- {row.get('symbol', 'Sin datos')}: `{row.get('path')}` "
                f"(benchmark {row.get('benchmark', 'Sin datos')})"
            )

    def pct(x: float) -> str:
        return f"{x * 100:,.1f}%"

    def pct_opt(x) -> str:
        return "—" if x is None else pct(x)

    def gate_text(r: dict) -> str:
        return "sí" if (r.get("regime_gate") or {}).get("passed") else "no"

    for i, r in enumerate(report["results"][:top], 1):
        params = " ".join(f"{k}={v}" for k, v in r["params"].items())
        lines.append(
            f"| {i} | {r['symbol']} | {r['strategy']} | {params} | "
            f"{r['exposure']:g}× | {r['sharpe']:,.2f} | {pct(r['cagr'])} | "
            f"{pct(r['max_drawdown'])} | {r['num_trades']} | {pct(r['pass_rate'])} | "
            f"{pct(r['breach_rate'])} | {pct_opt(r.get('oos_pass_rate'))} | {r['score']:,.3f} | {pct_opt(r.get('dsr'))} | "
            f"{r.get('wf_positive_folds', 0)}/{cfg.get('wf_folds', 4)} | {gate_text(r)} |"
        )

    lines += [
        "",
        "## Métricas informativas",
        "",
        "Solo informativas: no cambian ningún criterio de propuesta. Con N<30 se muestran como aviso.",
        "",
        "| # | Activo | Estrategia | Escala | N | SQN | Recovery | Ruina | Aviso |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(report["results"][:10], 1):
        sqn = r.get("sqn")
        recovery = r.get("recovery_factor")
        ruin = r.get("risk_of_ruin")
        lines.append(
            f"| {i} | {r['symbol']} | {r['strategy']} | {r['exposure']:g}× | "
            f"{r['num_trades']} | {f'{sqn:,.2f}' if sqn is not None else 'Sin datos'} | "
            f"{f'{recovery:,.2f}' if recovery is not None else 'Sin datos'} | "
            f"{f'{ruin:.4%}' if ruin is not None else 'Sin datos'} | "
            f"{r.get('metrics_warning') or '—'} |"
        )

    lines += [
        "",
        "## Regímenes (top 5)",
        "",
        "| # | Activo | Estrategia | 2018 | 2020 | 2022 | Gate | Motivo |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(report["results"][:5], 1):
        stats = (r.get("regime_report") or {}).get("years") or {}
        fallback = r.get("year_returns") or {}
        returns = {
            year: (stats.get(year) or {}).get("total_return", fallback.get(year))
            for year in ("2018", "2020", "2022")
        }
        gate = r.get("regime_gate") or {}
        reasons = "; ".join(gate.get("reasons") or []) or "—"
        lines.append(
            f"| {i} | {r['symbol']} | {r['strategy']} | "
            f"{pct_opt(returns['2018'])} | {pct_opt(returns['2020'])} | "
            f"{pct_opt(returns['2022'])} | {gate_text(r)} | {reasons} |"
        )

    lines += [
        "",
        "## Drawdown por régimen (top 5, informativo)",
        "",
        "| # | Activo | Estrategia | 2018 DD | 2018 B&H | 2020 DD | 2020 B&H | 2022 DD | 2022 B&H |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(report["results"][:5], 1):
        stats = (r.get("regime_report") or {}).get("years") or {}
        values = []
        for year in ("2018", "2020", "2022"):
            item = stats.get(year) or {}
            values.extend(
                [
                    pct_opt(item.get("max_drawdown")),
                    pct_opt(item.get("buy_hold_max_drawdown")),
                ]
            )
        lines.append(
            f"| {i} | {r['symbol']} | {r['strategy']} | " + " | ".join(values) + " |"
        )
    lines += [
        "",
        "> DD = max drawdown de la variante; B&H = max drawdown de comprar y mantener "
        "el mismo activo en el mismo régimen. Es solo informativo y **no** forma "
        "parte del gate de propuesta.",
    ]

    if wf:
        lines += [
            "",
            "## Walk-forward global",
            "",
            "| Veredicto | Sharpe stitched | Folds positivos | Eficiencia | Rank mediano | Estabilidad | Folds | Variantes | Train | Test |",
            "|---|---|---|---|---|---|---|---|---|---|",
            f"| {wf.get('verdict', '—')} | {wf['stitched_sharpe']:,.2f} | "
            f"{wf['frac_positive']:.0%} | {wf['efficiency']:,.2f} | "
            f"{wf['median_rank_pct']:.0%} | {wf['stability']:.0%} | "
            f"{wf['n_folds']} | {wf['n_variants']} | {wf['train_len']} | {wf['test_len']} |",
            "",
            "> La eficiencia es la mediana de Sharpe(OOS)/Sharpe(IS) por fold; "
            "la estabilidad mide si se repite la misma variante elegida. Una "
            "variante con edge persistente debería superar 0 en las tres métricas.",
        ]

    pbo_rows = []
    if pbo:
        pbo_rows.append(("Global", pbo))
    for symbol, payload in sorted(report.get("pbo_by_symbol", {}).items()):
        pbo_rows.append((symbol, payload))
    if pbo_rows:
        lines += [
            "",
            "## Sobreajuste (CSCV)",
            "",
            "| Ámbito | PBO | Veredicto | Variantes | Planas | PBO sin planas | Bloques | Combinaciones | Filas |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for scope, payload in pbo_rows:
            nonflat_pbo = payload.get("pbo_excluding_flat")
            lines.append(
                f"| {scope} | {pct(payload['pbo'])} | {payload.get('verdict', '—')} | "
                f"{payload.get('n_variants', 0)} | {payload.get('flat_variants', 0)} | "
                f"{pct_opt(nonflat_pbo)} | {payload.get('n_slices', 0)} | "
                f"{payload.get('n_combinations', 0):,} | {payload.get('rows_used', 0):,} |"
            )
        lines += [
            "",
            "> PBO ≤ "
            f"{cfg.get('max_pbo', 0.30):.0%} se considera aceptable; cerca del 50% "
            "elegir la mejor variante es esencialmente azar. Sin PBO calculable no "
            "se proponen bots.",
            "",
            "> **Diagnóstico de variantes planas:** se cuenta como plana una columna "
            "con desviación típica diaria ≤ 1e-10. El PBO sin planas es solo "
            "informativo: no cambia el criterio de propuesta. Si no hay planas, "
            "coincide con el PBO normal.",
            "",
            "> **Nota metodológica:** con ~11 años de datos diarios el PBO de una "
            "sola muestra es ruidoso (en ruido puro puede variar aproximadamente "
            "entre 0.12 y 0.73). Se interpreta como **alarma**, no como prueba. "
            "Un régimen sin datos **no aprueba**.",
        ]

    lines += [
        "",
        "## Propuestas",
        "",
        f"Criterios: pasa ≥ {cfg['min_pass']:.0%}, revienta ≤ {cfg['max_breach']:.0%}, "
        f"OOS ≥ {cfg['min_oos_pass']:.0%}, Sharpe > 0, trades ≥ {cfg['min_trades']}, "
        f"DSR ≥ {cfg.get('min_dsr', 0.90):.0%}, WF positivos ≥ "
        f"{cfg.get('min_wf_positive', 2)}/{cfg.get('wf_folds', 4)}, PBO ≤ "
        f"{cfg.get('max_pbo', 0.30):.0%} (global y por activo), walk-forward "
        f"global con veredicto ok, régimen aprobado en "
        f"{'/'.join(str(y) for y in cfg.get('regime_years', [2018, 2020, 2022]))} "
        f"y mediana de la familia ≥ {cfg['min_pass']:.0%}.",
        "",
    ]
    if report["proposals"]:
        lines += [
            "| Activo | Estrategia | Parámetros | Escala | Trades | Pasa | Revienta | OOS | DSR | Familia | Score |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for p in report["proposals"]:
            params = " ".join(f"{k}={v}" for k, v in p["params"].items())
            lines.append(
                f"| {p['symbol']} | {p['strategy']} | {params} | {p['exposure']:g}× | "
                f"{p['num_trades']} | {pct(p['pass_rate'])} | {pct(p['breach_rate'])} | "
                f"{pct_opt(p.get('oos_pass_rate'))} | {pct_opt(p.get('dsr'))} | "
                f"{pct_opt(p.get('family_median_pass'))} | {p['score']:,.3f} |"
            )
        lines += [
            "",
            "> `enabled: false` — ninguna propuesta se activa automáticamente. "
            "Para promoverla: revisar el backtest, añadirla a `config/bots.yaml` y "
            "volver a simular con datos intradía.",
        ]
    else:
        lines.append(
            "Ningún candidato cumple los criterios. Es un resultado válido: "
            "no pagues un challenge con estas estrategias todavía."
        )

    near_misses = report.get("near_misses", [])
    if near_misses:
        slack = cfg.get("near_miss_slack", 5)
        lines += [
            "",
            "## Casi propuestas (no accionables)",
            "",
            "Incluye dos casos: variantes que fallan **solo** los controles nuevos "
            "(PBO, walk-forward global o régimen) y variantes que pasan la "
            f"validación pero tienen pocas operaciones "
            f"({max(0, cfg['min_trades'] - slack)}-{cfg['min_trades'] - 1} trades). "
            "Se listan para vigilancia; **no se proponen**.",
            "",
            "| Activo | Estrategia | Parámetros | Escala | Trades | Pasa | Revienta | OOS | DSR | Familia | Score | Estado | Motivo |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for p in near_misses:
            params = " ".join(f"{k}={v}" for k, v in p["params"].items())
            lines.append(
                f"| {p['symbol']} | {p['strategy']} | {params} | {p['exposure']:g}× | "
                f"{p['num_trades']} | {pct(p['pass_rate'])} | {pct(p['breach_rate'])} | "
                f"{pct_opt(p.get('oos_pass_rate'))} | {pct_opt(p.get('dsr'))} | "
                f"{pct_opt(p.get('family_median_pass'))} | {p['score']:,.3f} | "
                f"`{p.get('status', '—')}` | {p.get('note', '—')} |"
            )
        lines += [
            "",
            "> Un resultado alto con pocos trades puede desaparecer al añadir dos "
            "años de datos. La familia de parámetros ayuda, pero no sustituye una "
            "muestra amplia.",
        ]

    if report["errors"]:
        lines += ["", "## Errores", ""]
        lines += [f"- `{e}`" for e in report["errors"][:20]]

    lines += [
        "",
        "---",
        "Aproximación con retornos diarios: el riesgo intradía real es mayor. "
        "No es asesoramiento financiero.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(report: dict, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_text = json.dumps(report, indent=2, ensure_ascii=False)
    md_text = render_markdown(report)

    files = {
        "run_json": out / f"research_{stamp}.json",
        "run_md": out / f"research_{stamp}.md",
        "latest_json": out / "latest.json",
        "latest_md": out / "latest.md",
        "proposals_json": out / "proposals.json",
        "proposals_md": out / "proposals.md",
    }
    for key in ("run_json", "latest_json"):
        files[key].write_text(json_text, encoding="utf-8")
    for key in ("run_md", "latest_md"):
        files[key].write_text(md_text, encoding="utf-8")

    proposals = {
        "generated_at": report["generated_at"],
        "rules": report["rules"],
        "auto_enable": False,
        "pbo": report.get("pbo"),
        "walk_forward": report.get("walk_forward"),
        "datachecks": report.get("datachecks", {}),
        "quantstats": report.get("quantstats") or {},
        "holdout_usage": report.get("holdout_usage") or {},
        "proposals": report["proposals"],
        "near_misses": report.get("near_misses", []),
    }
    files["proposals_json"].write_text(
        json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    proposals_md = [
        "# Propuestas de bots",
        "",
        f"Generado: {report['generated_at']}",
        "",
        "Ninguna propuesta está activa. Requieren revisión y aprobación humana.",
        "",
    ]
    if report["proposals"]:
        for p in report["proposals"]:
            oos = (
                f", OOS {p['oos_pass_rate']:.1%}"
                if p.get("oos_pass_rate") is not None
                else ""
            )
            family = (
                f", familia {p['family_median_pass']:.1%}"
                if p.get("family_median_pass") is not None
                else ""
            )
            proposals_md.append(
                f"- **{p['symbol']} · {p['strategy']}** "
                f"({json.dumps(p['params'], ensure_ascii=False)}, escala {p['exposure']:g}×) — "
                f"pasa {p['pass_rate']:.1%}, revienta {p['breach_rate']:.1%}{oos}{family} · "
                f"`{p['status']}`"
            )
    else:
        proposals_md.append("- Sin propuestas que cumplan los criterios.")

    near_misses = report.get("near_misses", [])
    if near_misses:
        proposals_md += [
            "",
            "## Casi propuestas (no accionables)",
            "",
            "Fallan solo los controles nuevos (PBO/walk-forward/régimen) o tienen "
            "menos operaciones que el mínimo. No se activan ni se proponen.",
            "",
        ]
        for p in near_misses:
            proposals_md.append(
                f"- **{p['symbol']} · {p['strategy']}** "
                f"({json.dumps(p['params'], ensure_ascii=False)}, escala {p['exposure']:g}×) — "
                f"{p['num_trades']} trades, pasa {p['pass_rate']:.1%}, "
                f"revienta {p['breach_rate']:.1%} · `{p['status']}` — {p.get('note', '')}"
            )
    files["proposals_md"].write_text("\n".join(proposals_md) + "\n", encoding="utf-8")

    return {k: str(v) for k, v in files.items()}


__all__ = [
    "ResearchConfig",
    "GRIDS",
    "DEFAULT_SYMBOLS",
    "run_research",
    "render_markdown",
    "write_outputs",
]
