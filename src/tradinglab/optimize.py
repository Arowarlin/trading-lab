"""Optuna con walk-forward, holdout sellado y gates DSR/PBO.

Cada trial suma al contador global de pruebas que usa el DSR. El tramo final
sellado nunca se usa para elegir parámetros; solo se evalúa una vez al final y
se etiqueta como no usado para selección. Nada activa bots.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

from . import data as data_mod
from .backtest import run as run_backtest
from .config import DEFAULT_DB, Settings, get_settings
from .global_dsr import global_srs
from .learning import (
    count_tests,
    evaluate_holdout_once,
    holdout_info,
    holdout_usage,
    record_optimization_trial,
)
from .stats import dsr_local_global, period_sharpe
from .strategies import STRATEGIES
from .validation import cscv_pbo
from .walkforward import walk_forward

MIN_DSR = 0.90
MAX_PBO = 0.30


class OptunaError(ValueError):
    pass


optuna.logging.set_verbosity(optuna.logging.WARNING)


def _sharpe(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    std = float(r.std(ddof=1))
    return float(r.mean() / std * math.sqrt(252)) if std > 1e-12 else 0.0


def suggest_params(trial: optuna.Trial, strategy: str) -> dict:
    if strategy in {"trend", "trend-ls"}:
        fast = trial.suggest_int("fast", 10, 100, step=5)
        slow = trial.suggest_int("slow", 100, 300, step=10)
        regime = trial.suggest_int("regime", 100, 300, step=10)
        if fast >= slow:
            raise optuna.TrialPruned("fast >= slow")
        return {"fast": fast, "slow": slow, "regime": regime}
    if strategy == "meanrev":
        window = trial.suggest_int("window", 5, 50, step=5)
        entry_z = trial.suggest_float("entry_z", -3.0, -1.0, step=0.25)
        exit_z = trial.suggest_float("exit_z", -0.5, 0.5, step=0.25)
        max_hold = trial.suggest_int("max_hold", 5, 30, step=5)
        if exit_z <= entry_z:
            raise optuna.TrialPruned("exit_z <= entry_z")
        return {
            "window": window,
            "entry_z": entry_z,
            "exit_z": exit_z,
            "max_hold": max_hold,
        }
    raise OptunaError(f"estrategia no soportada por Optuna: {strategy}")


def walk_forward_returns(
    frame: pd.DataFrame,
    strategy: str,
    params: dict,
    *,
    train_days: int,
    test_days: int,
    step: int,
) -> tuple[np.ndarray, list[float]]:
    """Retornos OOS por fold; la señal usa solo historia hasta cada fecha."""
    chunks: list[np.ndarray] = []
    sharpes: list[float] = []
    for start in range(train_days, len(frame) - test_days + 1, step):
        test = frame.iloc[start : start + test_days]
        history = frame.iloc[: start + test_days]
        try:
            signal = STRATEGIES[strategy](history, **params).target.loc[test.index]
            bt = run_backtest(
                test,
                signal,
                starting_cash=100_000.0,
                commission_bps=1.0,
                slippage_bps=5.0,
            )
        except Exception:
            continue
        returns = bt.returns.to_numpy(dtype=float)
        chunks.append(returns)
        sharpes.append(_sharpe(returns))
    if not chunks:
        return np.empty(0), []
    return np.concatenate(chunks), sharpes


def _trial_matrix(trial_returns: dict[int, np.ndarray]) -> np.ndarray | None:
    values = [value for value in trial_returns.values() if len(value) > 0]
    if len(values) < 2:
        return None
    length = min(len(value) for value in values)
    if length < 100:
        return None
    return np.column_stack([value[-length:] for value in values])


def run_optuna(
    symbol: str,
    strategy: str,
    *,
    start: str = "2015-01-01",
    end: str | None = None,
    trials: int = 20,
    train_days: int = 504,
    test_days: int = 126,
    step: int = 126,
    cache_dir: str | Path | None = None,
    db_path: str | Path = DEFAULT_DB,
    settings: Settings | None = None,
    study_name: str | None = None,
    sampler_seed: int = 42,
) -> dict:
    """Ejecuta Optuna sobre el desarrollo; el holdout sellado no se optimiza."""
    if strategy not in STRATEGIES:
        raise OptunaError(f"estrategia desconocida: {strategy}")
    if trials < 1:
        raise OptunaError("trials debe ser >= 1")
    settings = settings or get_settings()
    cache = Path(cache_dir or settings.data.cache_dir)
    end_date = date.fromisoformat(end) if end else datetime.now(timezone.utc).date()
    sealed = holdout_info(db_path, settings)
    sealed_start = date.fromisoformat(sealed["start_date"])
    dev_end = min(end_date, sealed_start - timedelta(days=1))
    start_date = date.fromisoformat(start)
    if dev_end <= start_date:
        raise OptunaError("Sin datos: el desarrollo termina antes de empezar")

    try:
        frame = data_mod.fetch(symbol, start_date.isoformat(), dev_end.isoformat(), cache)
    except Exception as exc:
        raise OptunaError(f"Sin datos para {symbol}: {type(exc).__name__}") from exc
    if len(frame) < train_days + test_days:
        raise OptunaError(
            f"Sin datos: {len(frame)} barras para {train_days}+{test_days}"
        )

    study_name = study_name or (
        f"optuna-{symbol.upper()}-{strategy}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    trial_returns: dict[int, np.ndarray] = {}
    trial_values: dict[int, float] = {}

    def objective(trial: optuna.Trial) -> float:
        params = suggest_params(trial, strategy)
        returns, _ = walk_forward_returns(
            frame,
            strategy,
            params,
            train_days=train_days,
            test_days=test_days,
            step=step,
        )
        if len(returns) == 0:
            raise optuna.TrialPruned("sin retornos OOS")
        value = _sharpe(returns)
        trial_returns[trial.number] = returns
        trial_values[trial.number] = value
        record_optimization_trial(
            db_path,
            study=study_name,
            trial=trial.number,
            symbol=symbol,
            strategy=strategy,
            params=params,
            value=value,
            period_start=str(frame.index[0].date()),
            period_end=str(frame.index[-1].date()),
            notes="Optuna walk-forward; desarrollo",
            settings=settings,
            sr_period=value / math.sqrt(252.0),
            periods_per_year=252.0,
        )
        return value

    study = optuna.create_study(
        direction="maximize",
        study_name=study_name,
        sampler=optuna.samplers.TPESampler(seed=sampler_seed),
    )
    study.optimize(objective, n_trials=int(trials), catch=(Exception,))
    completed = [trial for trial in study.trials if trial.value is not None]
    if not completed:
        raise OptunaError("Sin datos: ningún trial completó")

    best = study.best_trial
    best_returns = trial_returns[best.number]
    best_sharpe = _sharpe(best_returns)
    n_trials = count_tests(db_path, settings)
    trial_srs = [period_sharpe(trial_returns[item.number]) for item in completed]
    local_n = len(trial_srs)
    global_info = global_srs(db_path, "daily")
    pair = dsr_local_global(
        best_returns,
        trial_srs,
        global_info["srs"],
        local_n,
        n_trials,
        periods_per_year=252,
        global_sources=global_info["sources"],
        frequency="daily",
    )
    dsr_local = pair["local"]["dsr"]
    dsr_global = pair["global"]["dsr"]
    dsr = dsr_global
    dsr_gate = "global" if dsr_global is not None else "pendiente"
    dsr_ok = dsr is not None and dsr >= MIN_DSR

    matrix = _trial_matrix(trial_returns)
    pbo = None
    pbo_ok = False
    if matrix is not None:
        try:
            pbo = cscv_pbo(
                matrix,
                n_slices=min(16, max(4, matrix.shape[0] // 20)),
                max_combinations=2_000,
                seed=0,
            )
            pbo_ok = pbo.pbo <= MAX_PBO
        except Exception:
            pbo = None
    wf = None
    wf_ok = False
    if matrix is not None:
        try:
            train = min(252, max(60, matrix.shape[0] // 2))
            test = min(126, max(20, matrix.shape[0] // 4))
            wf = walk_forward(matrix, train_len=train, test_len=test)
            wf_ok = wf.verdict() == "ok"
        except Exception:
            wf = None

    holdout_payload: dict = {"status": "Sin datos", "used_for_selection": False}
    if end_date < sealed_start:
        holdout_payload = {
            "status": "Sin datos",
            "used_for_selection": False,
            "reason": "el periodo solicitado termina antes del holdout",
        }
    else:
        def evaluate_sealed() -> dict:
            sealed_frame = data_mod.fetch(
                symbol,
                sealed_start.isoformat(),
                end_date.isoformat(),
                cache,
            )
            if len(sealed_frame) == 0:
                raise OptunaError("Sin datos: holdout vacío")
            history = pd.concat([frame, sealed_frame])
            signal = STRATEGIES[strategy](
                history, **best.params
            ).target.loc[sealed_frame.index]
            sealed_bt = run_backtest(
                sealed_frame,
                signal,
                starting_cash=100_000.0,
                commission_bps=1.0,
                slippage_bps=5.0,
            )
            return {
                "status": "ok",
                "used_for_selection": False,
                "metrics": sealed_bt.metrics,
                "period_start": sealed_start.isoformat(),
                "period_end": end_date.isoformat(),
            }

        try:
            holdout_payload = evaluate_holdout_once(
                db_path,
                symbol=symbol,
                strategy=strategy,
                params=best.params,
                evaluator=evaluate_sealed,
                settings=settings,
                notes="Optuna holdout sellado",
            )
            holdout_payload["used_for_selection"] = False
        except Exception as exc:
            holdout_payload = {
                "status": "Sin datos",
                "used_for_selection": False,
                "reason": type(exc).__name__,
            }

    # La lectura del holdout suma una prueba; recalcula el DSR con el contador final.
    n_trials = count_tests(db_path, settings)
    global_info = global_srs(db_path, "daily")
    pair = dsr_local_global(
        best_returns,
        trial_srs,
        global_info["srs"],
        local_n,
        n_trials,
        periods_per_year=252,
        global_sources=global_info["sources"],
        frequency="daily",
    )
    dsr_local = pair["local"]["dsr"]
    dsr_global = pair["global"]["dsr"]
    dsr = dsr_global
    dsr_gate = "global" if dsr_global is not None else "pendiente"
    dsr_ok = dsr is not None and dsr >= MIN_DSR

    gates = {
        "dsr": dsr,
        "dsr_local": dsr_local,
        "dsr_global": dsr_global,
        "dsr_gate": dsr_gate,
        "metric_version": pair["local"]["metric_version"],
        "dsr_local_meta": pair["local"],
        "dsr_global_meta": pair["global"],
        "dsr_ok": dsr_ok,
        "pbo": pbo.pbo if pbo is not None else None,
        "pbo_ok": pbo_ok,
        "walk_forward_verdict": wf.verdict() if wf is not None else "Sin datos",
        "walk_forward_ok": wf_ok,
    }
    failures: list[str] = []
    if not dsr_ok:
        failures.append(f"DSR {dsr if dsr is not None else 'Sin datos'} < {MIN_DSR:.0%}")
    if not pbo_ok:
        failures.append(
            f"PBO {pbo.pbo if pbo is not None else 'Sin datos'} > {MAX_PBO:.0%}"
        )
    if not wf_ok:
        failures.append("walk-forward no aprobado o sin datos")
    proposals: list[dict] = []
    if not failures:
        proposals.append(
            {
                "id": f"optuna:{symbol.upper()}:{strategy}",
                "symbol": symbol.upper(),
                "strategy": strategy,
                "params": best.params,
                "score": best.value,
                "sharpe": best_sharpe,
                "dsr": dsr,
                "dsr_local": dsr_local,
                "dsr_global": dsr_global,
                "metric_version": pair["local"]["metric_version"],
                "pbo": pbo.pbo if pbo is not None else None,
                "walk_forward_verdict": wf.verdict() if wf is not None else None,
                "holdout": holdout_payload,
                "status": "proposed",
                "enabled": False,
                "note": "Optuna + walk-forward; requiere aprobación humana. No activa bots.",
            }
        )
    history = sorted(
        (
            {
                "trial": trial.number,
                "value": float(trial.value),
                "params": trial.params,
            }
            for trial in completed
        ),
        key=lambda row: row["value"],
        reverse=True,
    )[:20]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "study": study_name,
        "symbol": symbol.upper(),
        "strategy": strategy,
        "config": {
            "start": start_date.isoformat(),
            "dev_end": dev_end.isoformat(),
            "sealed_start": sealed_start.isoformat(),
            "trials_requested": int(trials),
            "train_days": int(train_days),
            "test_days": int(test_days),
            "step": int(step),
        },
        "trials": len(completed),
        "n_trials_dsr": n_trials,
        "best_trial": best.number,
        "best_params": best.params,
        "best_value": float(best.value),
        "best_sharpe": best_sharpe,
        "gates": gates,
        "holdout": holdout_payload,
        "holdout_usage": holdout_usage(db_path, settings),
        "proposals": proposals,
        "reason": None if proposals else "; ".join(failures),
        "history": history,
    }


def write_report(report: dict, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_text = json.dumps(report, indent=2, ensure_ascii=False)
    run_path = out / f"optuna_{stamp}.json"
    latest_path = out / "latest.json"
    run_path.write_text(json_text, encoding="utf-8")
    latest_path.write_text(json_text, encoding="utf-8")
    return {"run": str(run_path), "latest": str(latest_path)}


__all__ = [
    "MAX_PBO",
    "MIN_DSR",
    "OptunaError",
    "run_optuna",
    "suggest_params",
    "walk_forward_returns",
    "write_report",
]
