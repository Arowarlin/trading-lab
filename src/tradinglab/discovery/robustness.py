"""Robustness Lab: todas las pruebas sobre IS+OOS-1 (OOS-2 solo en confirm).

Reutiliza stats/validation/walkforward/prop.simulator. El test contra entradas
aleatorias sobre IS+OOS-1 es informativo y no cuenta como trial del DSR;
cualquier prueba no calculable se reporta como "Sin datos" y no aprueba el
nivel 4.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

import numpy as np
import pandas as pd

from ..prop.simulator import monte_carlo_program
from ..propfund.registry import load_registry
from ..propfund.snapshots import _rules_from_account
from ..validation import cscv_pbo
from ..walkforward import regime_gate, regime_report, walk_forward
from . import campaigns, compiler, databank, dsl, fastbt, jobs, optimizer, retester
from .config import load_engine_config
from .specs import exit_spec_from_strategy, run_limits_from_strategy


def _combined(is_frame: pd.DataFrame, oos1_frame: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([is_frame, oos1_frame], axis=0, sort=False)


def _series(values: list[float], dates: list[str]) -> pd.Series:
    if not dates:
        return pd.Series(values, dtype=float)
    return pd.Series(values, index=pd.to_datetime(dates), dtype=float)


def _prepared_for(
    model: dsl.Strategy,
    bars: pd.DataFrame,
    cost,
    setup,
) -> tuple[fastbt.PreparedBars, fastbt.RunLimits]:
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    trailing = model.exit.trailing or {}
    prepared = fastbt.prepare(
        bars,
        cost,
        atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
        sessions=(limits,),
    )
    return prepared, limits


def random_baseline(
    model: dsl.Strategy,
    bars: pd.DataFrame,
    cost,
    setup,
    prepared: fastbt.PreparedBars,
    *,
    trials: int,
    seed: int,
    real_expectancy: float | None = None,
    real_trades: list | None = None,
    cache=None,
) -> dict[str, Any]:
    """Compara la estrategia con entradas aleatorias en el mismo tramo.

    Es informativo para IS+OOS-1 y requisito de nivel 4 cuando se aplica al
    holdout OOS-2. No cuenta como trial del DSR.
    """

    signals = compiler.compile(model, bars, cache=cache)
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    if real_expectancy is None or real_trades is None:
        base = fastbt.run(
            signals,
            bars,
            exit_spec_from_strategy(model),
            cost,
            limits,
            prepared=prepared,
        )
        if real_expectancy is None:
            real_expectancy = base.metrics.get("expectancy_r")
        if real_trades is None:
            real_trades = base.trades
    real = real_expectancy
    trades = list(real_trades or [])
    if real is None:
        return {
            "status": "Sin datos",
            "percentile": None,
            "real_expectancy_r": None,
            "trials": 0,
            "valid_trials": 0,
            "note": "no cuenta como trial del DSR",
        }
    n_long = sum(1 for trade in trades if trade.side == "long")
    n_short = sum(1 for trade in trades if trade.side == "short")
    if n_long + n_short == 0:
        return {
            "status": "Sin datos",
            "percentile": None,
            "real_expectancy_r": float(real),
            "trials": 0,
            "valid_trials": 0,
            "entries_long": 0,
            "entries_short": 0,
            "reason": "sin operaciones reales en el tramo",
            "note": "no cuenta como trial del DSR",
        }
    mask = next(iter(prepared.masks.values())).allowed_entry
    positions = np.arange(len(bars))
    eligible = np.flatnonzero(mask & (positions >= signals.valid_from))
    if n_long + n_short > len(eligible):
        return {
            "status": "Sin datos",
            "percentile": None,
            "real_expectancy_r": float(real),
            "trials": 0,
            "valid_trials": 0,
            "entries_long": int(n_long),
            "entries_short": int(n_short),
            "reason": "entradas reales > barras elegibles",
            "note": "no cuenta como trial del DSR",
        }
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(int(trials)):
        picks = rng.sample(eligible.tolist(), n_long + n_short)
        long_sig = np.zeros(len(bars), dtype=bool)
        short_sig = np.zeros(len(bars), dtype=bool)
        long_sig[picks[:n_long]] = True
        short_sig[picks[n_long:]] = True
        result = fastbt.run(
            fastbt.Signals(long_sig, short_sig, signals.valid_from),
            bars,
            exit_spec_from_strategy(model),
            cost,
            limits,
            prepared=prepared,
        )
        value = result.metrics.get("expectancy_r")
        if value is not None:
            values.append(float(value))
    if not values:
        return {
            "status": "Sin datos",
            "percentile": None,
            "real_expectancy_r": float(real),
            "trials": int(trials),
            "valid_trials": 0,
            "entries_long": int(n_long),
            "entries_short": int(n_short),
            "note": "no cuenta como trial del DSR",
        }
    percentile = float(np.mean(np.asarray(values) < float(real)) * 100.0)
    return {
        "status": "ok",
        "percentile": percentile,
        "real_expectancy_r": float(real),
        "random_expectancy_mean": float(np.mean(values)),
        "trials": int(trials),
        "valid_trials": len(values),
        "entries_long": int(n_long),
        "entries_short": int(n_short),
        "seed": int(seed),
        "note": "no cuenta como trial del DSR",
    }


def _mc_trades(trades, *, paths: int, seed: int) -> dict[str, Any]:
    values = np.asarray(
        [float(trade.r_net) for trade in trades if trade.r_net is not None],
        dtype=float,
    )
    if values.size < 2:
        return {"status": "Sin datos"}
    rng = np.random.default_rng(seed)
    shuffle_expectancy = np.zeros(paths)
    resample_expectancy = np.zeros(paths)
    shuffle_dd = np.zeros(paths)
    resample_dd = np.zeros(paths)
    for index in range(paths):
        shuffled = rng.permutation(values)
        resampled = rng.choice(values, size=values.size, replace=True)
        shuffle_expectancy[index] = shuffled.mean()
        resample_expectancy[index] = resampled.mean()
        shuffle_dd[index] = (np.cumsum(shuffled) - np.maximum.accumulate(np.cumsum(shuffled))).min()
        resample_dd[index] = (np.cumsum(resampled) - np.maximum.accumulate(np.cumsum(resampled))).min()
    return {
        "status": "ok",
        "trades": int(values.size),
        "paths": int(paths),
        "shuffle_expectancy_mean": float(shuffle_expectancy.mean()),
        "shuffle_expectancy_p5": float(np.percentile(shuffle_expectancy, 5)),
        "resample_expectancy_mean": float(resample_expectancy.mean()),
        "resample_expectancy_p5": float(np.percentile(resample_expectancy, 5)),
        "shuffle_dd_p5": float(np.percentile(shuffle_dd, 5)),
        "resample_dd_p5": float(np.percentile(resample_dd, 5)),
    }


def _bootstrap(daily: pd.Series, *, paths: int, seed: int) -> dict[str, Any]:
    values = pd.to_numeric(daily, errors="coerce").dropna().to_numpy(dtype=float)
    block = 5
    if values.size < block:
        return {"status": "Sin datos"}
    rng = np.random.default_rng(seed)
    expectancies = np.zeros(paths)
    drawdowns = np.zeros(paths)
    blocks = int(np.ceil(values.size / block))
    for index in range(paths):
        starts = rng.integers(0, max(1, values.size - block + 1), size=blocks)
        sample = np.concatenate([values[start : start + block] for start in starts])[
            : values.size
        ]
        expectancies[index] = sample.mean()
        cumulative = np.cumsum(sample)
        drawdowns[index] = (cumulative - np.maximum.accumulate(cumulative)).min()
    return {
        "status": "ok",
        "paths": int(paths),
        "block_days": block,
        "expectancy_mean": float(expectancies.mean()),
        "expectancy_p5": float(np.percentile(expectancies, 5)),
        "dd_p5": float(np.percentile(drawdowns, 5)),
    }


WF_INFORMATIVE_MIN_TEST_TRADES = 2


def _normal_date(value: Any):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp.date()


def _frontier_frame(
    campaign_id: str, db_path
) -> tuple[pd.DataFrame | None, list[int]]:
    frontier = databank.frontier(campaign_id, db_path=db_path)
    series = {}
    for row in frontier:
        if row["dates"]:
            series[row["strategy_id"]] = _series(row["returns"], row["dates"])
    return _business_day_frame(series)


def _population_sample_frame(
    campaign_id: str, db_path, size: int
) -> tuple[pd.DataFrame | None, list[int]]:
    """Muestra fija de la población evaluada en IS (ENG-1 S1, puertas v3).

    El PBO y el WF del frontier miden estrategias ya elegidas por el GA con el
    mismo IS (D-01, D-02). Una muestra aleatoria de todas las estrategias
    evaluadas no está elegida, así que el WF mide si "elegir la mejor en el
    pasado" funciona después. La semilla depende solo del id de campaña.
    """

    rows = databank.list_strategies(campaign_id=campaign_id, limit=None, db_path=db_path)
    series = {}
    for row in rows:
        for item in databank.list_evaluations(row["id"], db_path=db_path):
            if item["segment"] != "fitness_is":
                continue
            dates = (item.get("metrics") or {}).get("return_dates") or []
            if dates:
                series[int(row["id"])] = _series(item["returns"].tolist(), dates)
            break
    ids = sorted(series)
    if len(ids) > size:
        seed = int(hashlib.sha256(str(campaign_id).encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        ids = sorted(int(value) for value in rng.choice(ids, size=size, replace=False))
    return _business_day_frame({key: series[key] for key in ids})


def _business_day_frame(series: dict[int, pd.Series]) -> tuple[pd.DataFrame | None, list[int]]:
    if len(series) < 2:
        return None, []
    frame = pd.concat(series, axis=1, sort=True).fillna(0.0)
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    frame.index = index.normalize()
    frame = frame[~frame.index.duplicated(keep="last")]
    # Serie diaria regular (lunes-viernes): los días sin operación son 0.
    # Sin esto, los pliegues del WF y los bloques del PBO son "días con
    # operación" y no días de calendario.
    calendar = pd.bdate_range(frame.index.min(), frame.index.max())
    frame = frame.reindex(calendar, fill_value=0.0)
    return frame, list(series)


def _wf_trade_frequency(
    frame: pd.DataFrame,
    fold_details: list[dict[str, Any]],
    trade_times_by_strategy: dict[int, list[Any]] | None,
    strategy_ids: list[int],
) -> dict[str, Any]:
    """Operaciones cerradas por ventana de prueba del WF.

    Usa la variante elegida en cada pliegue (no la estrategia finalista), que
    es la que el walk-forward evalúa. Cuenta cierres porque el R diario se
    atribuye al día de salida.
    """

    if trade_times_by_strategy is None or not fold_details:
        return {}
    dates = [_normal_date(value) for value in pd.Index(frame.index).tolist()]
    times = {
        int(sid): [_normal_date(value) for value in values]
        for sid, values in trade_times_by_strategy.items()
    }
    counts: list[int] = []
    for fold in fold_details:
        selected = int(fold.get("selected"))
        if selected < 0 or selected >= len(strategy_ids):
            continue
        strategy_id = int(strategy_ids[selected])
        start = int(fold.get("test_start"))
        end = int(fold.get("test_end"))
        if start < 0 or end > len(dates) or end <= start:
            continue
        first = dates[start]
        last = dates[end - 1]
        counts.append(
            sum(1 for stamp in times.get(strategy_id, []) if first <= stamp <= last)
        )
    if not counts:
        return {}
    median = float(np.median(counts))
    informative = median >= float(WF_INFORMATIVE_MIN_TEST_TRADES)
    return {
        "test_trades_per_fold": counts,
        "test_trades_median": median,
        "wf_informative": bool(informative),
        "wf_label": (
            None
            if informative
            else "WF no informativo (baja frecuencia)"
        ),
    }


def variant_trade_times(
    campaign_id: str,
    *,
    frame: pd.DataFrame | None = None,
    setup=None,
    cost=None,
    db_path=None,
) -> dict[int, list[Any]]:
    """Cierres por estrategia del *frontier* sobre el tramo IS (nunca OOS-2)."""

    if frame is None or setup is None or cost is None:
        from . import campaigns, perturb

        _combined, _campaign, setup, cost = perturb.load_campaign_inputs(
            campaign_id, db_path=db_path
        )
        frame = campaigns.load_segment(campaign_id, "is", db_path=db_path)
    frontier = databank.frontier(campaign_id, db_path=db_path)
    out: dict[int, list[Any]] = {}
    for row in frontier:
        strategy = databank.get_strategy(row["strategy_id"], db_path=db_path)
        if strategy is None:
            continue
        model = dsl.Strategy.model_validate(strategy["dsl"])
        prepared, limits = _prepared_for(model, frame, cost, setup)
        result = fastbt.run(
            compiler.compile(model, frame),
            frame,
            exit_spec_from_strategy(model),
            cost,
            limits,
            prepared=prepared,
        )
        out[int(row["strategy_id"])] = [
            trade.exit_time for trade in result.trades
        ]
    return out


def wf_trade_frequency(
    campaign_id: str,
    trade_times_by_strategy: dict[int, list[Any]] | None,
    *,
    db_path=None,
) -> dict[str, Any]:
    """Repite el conteo de operaciones por ventana sobre una campaña."""

    frame, strategy_ids = _frontier_frame(campaign_id, db_path)
    if frame is None:
        return {}
    from ..walkforward import walk_forward

    config = load_engine_config().robustness
    try:
        wf = walk_forward(
            frame.to_numpy(dtype=float),
            train_len=int(config.wf_train_days),
            test_len=int(config.wf_test_days),
        )
    except ValueError:
        return {}
    return _wf_trade_frequency(
        frame, wf.fold_details, trade_times_by_strategy, strategy_ids
    )


def _pbo_wf(
    campaign_id: str,
    db_path,
    *,
    trade_times_by_strategy: dict[int, list[Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_engine_config().robustness
    gates_v3 = int(config.gates_version) == 3
    train_days, test_days = int(config.wf_train_days), int(config.wf_test_days)
    if gates_v3:
        frame, strategy_ids = _population_sample_frame(
            campaign_id, db_path, int(config.v3_population_sample)
        )
        campaign = databank.get_campaign(campaign_id, db_path=db_path) or {}
        timeframe = str(campaign.get("timeframe") or "").upper()
        if timeframe in config.v3_wf_windows:
            train_days, test_days = (int(v) for v in config.v3_wf_windows[timeframe])
    else:
        frame, strategy_ids = _frontier_frame(campaign_id, db_path)
    if frame is None:
        return (
            {"status": "Sin datos", "pbo": None, "reason": "menos de 2 estrategias"},
            {"status": "Sin datos", "ok": False, "reason": "menos de 2 estrategias"},
        )
    matrix = frame.to_numpy(dtype=float)
    pbo_result: dict[str, Any]
    if matrix.shape[1] < int(config.pbo_min_strategies):
        pbo_result = {
            "status": "Sin datos",
            "pbo": None,
            "n_variants": int(matrix.shape[1]),
            "pbo_min_strategies": int(config.pbo_min_strategies),
            "reason": "faltan estrategias para PBO",
        }
    else:
        try:
            result = cscv_pbo(
                matrix,
                n_slices=int(config.pbo_slices),
                seed=0,
            )
            pbo_result = {"status": "ok", **result.to_dict()}
        except Exception as exc:  # noqa: BLE001
            pbo_result = {
                "status": "Sin datos",
                "pbo": None,
                "reason": f"{type(exc).__name__}: {exc}",
            }
    fold_details: list[dict[str, Any]] = []
    try:
        wf = walk_forward(
            matrix,
            train_len=train_days,
            test_len=test_days,
        )
        fold_details = list(wf.fold_details)
        verdict = wf.verdict(
            min_stitched_sharpe=float(config.wf_min_oos_sharpe),
            min_efficiency=float(config.wf_min_efficiency),
        )
        wf_result = {
            "status": "ok" if wf.n_folds >= 3 else "Sin datos",
            "verdict": verdict if wf.n_folds >= 3 else "Sin datos",
            "ok": (
                wf.n_folds >= 3
                and verdict == "ok"
                and wf.stitched_sharpe > float(config.wf_min_oos_sharpe)
                and wf.efficiency >= float(config.wf_min_efficiency)
            ),
            **wf.to_dict(),
            "thresholds": {
                "min_oos_sharpe": float(config.wf_min_oos_sharpe),
                "min_efficiency": float(config.wf_min_efficiency),
                "min_frac_positive": 0.5,
                "min_rank_pct": 0.5,
                "min_stability": 0.3,
                "min_folds": 3,
            },
        }
        if wf.n_folds < 3:
            wf_result["reason"] = f"folds insuficientes ({wf.n_folds} < 3)"
    except Exception as exc:  # noqa: BLE001
        wf_result = {
            "status": "Sin datos",
            "ok": False,
            "verdict": "Sin datos",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    gate_meta = {
        "gates_version": 3 if gates_v3 else 2,
        "matrix": "population_sample" if gates_v3 else "frontier",
        "n_variants_matrix": int(matrix.shape[1]),
        "wf_windows": [train_days, test_days],
    }
    pbo_result.update(gate_meta)
    wf_result.update(gate_meta)
    if trade_times_by_strategy is not None and fold_details and not gates_v3:
        wf_result.update(
            _wf_trade_frequency(
                frame,
                fold_details,
                trade_times_by_strategy,
                strategy_ids,
            )
        )
    return pbo_result, wf_result


def _risk_for_account(account_id: str) -> float | None:
    try:
        account = load_registry().accounts.get(str(account_id))
    except Exception:  # noqa: BLE001 - registro no disponible
        return None
    if account is None:
        return None
    risk = account.risk.per_trade_risk_pct
    if risk is None or float(risk) <= 0.0:
        return None
    return float(risk)


def account_regime(
    daily_r: pd.Series,
    risk_pct: float,
    *,
    years: tuple[int, ...] | None = None,
    min_obs: int = 20,
) -> dict[str, Any]:
    """Regímenes sobre retorno de cuenta, no sobre R.

    Convierte la serie diaria de R a retorno de cuenta con
    ``per_trade_risk_pct`` y solo exige los años que realmente tienen datos en
    el tramo (nunca 2018/2020 si la campaña empieza en 2021). No modifica
    ``walkforward.py``.
    """

    series = pd.to_numeric(daily_r, errors="coerce").dropna()
    if not isinstance(series.index, pd.DatetimeIndex):
        return {
            "status": "Sin datos",
            "passed": False,
            "reasons": ["índice sin fechas"],
            "years": {},
            "missing": [],
            "min_obs": int(min_obs),
        }
    account = series.astype(float) * float(risk_pct)
    if years is None:
        counts = account.groupby(account.index.year).size()
        years = tuple(
            sorted(
                int(year)
                for year, count in counts.items()
                if int(count) >= int(min_obs)
            )
        )
    report = regime_report(
        account, years=tuple(int(year) for year in years), min_obs=int(min_obs)
    )
    gate = regime_gate(report)
    return {
        "status": "Sin datos" if report.missing else "ok",
        "passed": bool(gate.passed),
        "reasons": list(gate.reasons),
        "risk_per_trade_pct": float(risk_pct),
        **report.to_dict(),
    }


def _regime(daily: pd.Series, risk_pct: float | None) -> dict[str, Any]:
    if risk_pct is None or float(risk_pct) <= 0.0:
        return {
            "status": "Sin datos",
            "passed": False,
            "reasons": ["per_trade_risk_pct Sin datos"],
            "years": {},
            "missing": [],
            "min_obs": 20,
        }
    return account_regime(daily, float(risk_pct))


def _challenge(daily_r: pd.Series) -> dict[str, Any]:
    config = load_engine_config().robustness
    registry = load_registry()
    results: dict[str, Any] = {}
    any_pass = False
    for account_id in config.challenge_accounts:
        account = registry.accounts.get(account_id)
        if account is None:
            results[account_id] = {"status": "Sin datos", "reason": "cuenta no registrada"}
            continue
        risk = account.risk.per_trade_risk_pct
        if risk is None or risk <= 0 or len(daily_r) < 2:
            results[account_id] = {"status": "Sin datos", "reason": "riesgo diario Sin datos"}
            continue
        try:
            if account.legacy_account:
                from ..accounts import load_accounts, rules_for_account

                legacy = load_accounts().get(account.legacy_account)
                if legacy is None:
                    results[account_id] = {
                        "status": "Sin datos",
                        "reason": (
                            f"cuenta legacy no registrada: "
                            f"{account.legacy_account}"
                        ),
                    }
                    continue
                rules = rules_for_account(legacy)
            else:
                rules = _rules_from_account(account, {})
            simulation = monte_carlo_program(
                [
                    rules,
                    rules.with_phase(
                        "verification",
                        profit_target_pct=0.05,
                        min_trading_days=4,
                        max_days=None,
                    ),
                ]
                if rules.program == "2-step"
                else [rules],
                pd.to_numeric(daily_r, errors="coerce").dropna().to_numpy(dtype=float)
                * float(risk),
                n_paths=int(config.challenge_paths),
                horizon=180,
                seed=42,
                block_size=5,
            )
            passed = float(simulation["pass_rate"]) > float(simulation["breach_rate"])
            any_pass = any_pass or passed
            results[account_id] = {
                "status": "ok",
                "passed": passed,
                "risk_per_trade_pct": float(risk),
                **simulation,
            }
        except Exception as exc:  # noqa: BLE001
            results[account_id] = {
                "status": "Sin datos",
                "reason": f"{type(exc).__name__}: {exc}",
            }
    computed = [item for item in results.values() if item.get("status") == "ok"]
    return {
        "status": "ok" if computed else "Sin datos",
        "passed": any_pass,
        "accounts": results,
    }


def _hour_streaks(trades, tz: str) -> tuple[dict[str, Any], dict[str, Any]]:
    groups: dict[tuple[int, int], list[float]] = {}
    streak_win = 0
    streak_loss = 0
    best_win = 0
    best_loss = 0
    for trade in trades:
        if trade.r_net is None:
            continue
        stamp = trade.entry_time.tz_convert(tz)
        key = (int(stamp.hour), int(stamp.weekday()))
        groups.setdefault(key, []).append(float(trade.r_net))
        value = float(trade.r_net)
        if value > 0:
            streak_win += 1
            streak_loss = 0
        elif value < 0:
            streak_loss += 1
            streak_win = 0
        best_win = max(best_win, streak_win)
        best_loss = max(best_loss, streak_loss)
    hour_weekday = {
        f"{hour:02d}:{weekday}": {
            "trades": len(values),
            "expectancy_r": float(np.mean(values)),
        }
        for (hour, weekday), values in sorted(groups.items())
    }
    return (
        {"status": "ok" if hour_weekday else "Sin datos", "groups": hour_weekday},
        {
            "status": "ok",
            "max_winning_streak": int(best_win),
            "max_losing_streak": int(best_loss),
        },
    )


def run(
    strategy_id: int,
    *,
    frame: pd.DataFrame | None = None,
    db_path=None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Ejecuta todo el Robustness Lab de una estrategia (IS+OOS-1)."""

    config = load_engine_config().robustness
    strategy = databank.get_strategy(strategy_id, db_path=db_path)
    if strategy is None:
        raise ValueError(f"estrategia no encontrada: {strategy_id}")
    campaign_id = str(strategy["campaign_id"])
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise ValueError(f"campaña no registrada: {campaign_id}")
    from .guard import require_approved_campaign

    require_approved_campaign(campaign, action="robustness")
    model = dsl.Strategy.model_validate(strategy["dsl"])
    setup = jobs.QueueSetup.from_campaign(campaign, bars=None)
    from ..propfund.costs import load_profile

    profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
    cost = fastbt.cost_from_profile(
        profile,
        use_p75=bool(setup.use_p75),
        cost_model_version=setup.cost_model_version,
    )
    is_frame = campaigns.load_segment(campaign_id, "is", frame=frame, db_path=db_path)
    oos1_frame = campaigns.load_segment(
        campaign_id, "oos1", frame=frame, db_path=db_path
    )
    bars = _combined(is_frame, oos1_frame)
    prepared, limits = _prepared_for(model, bars, cost, setup)
    signals = compiler.compile(model, bars)
    base = fastbt.run(
        signals,
        bars,
        exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
    )
    base_metrics = {
        "expectancy_r": base.metrics.get("expectancy_r"),
        "profit_factor": base.metrics.get("profit_factor"),
        "max_dd_r": base.metrics.get("max_dd_r"),
        "trades": int(base.metrics.get("trades") or 0),
    }
    is_limits = run_limits_from_strategy(model, setup, close_at_end=True)
    is_prepared = fastbt.prepare(
        is_frame,
        cost,
        atr_windows=(model.exit.stop.n, 14),
        sessions=(is_limits,),
    )
    is_result = fastbt.run(
        compiler.compile(model, is_frame),
        is_frame,
        exit_spec_from_strategy(model),
        cost,
        is_limits,
        prepared=is_prepared,
    )
    databank.add_evaluation(
        strategy_id,
        segment="fitness_is",
        cost_profile=setup.cost_profile(),
        metrics={
            **dict(is_result.metrics),
            "raw": {"expectancy_r": is_result.metrics.get("expectancy_r")},
            "is": dict(is_result.metrics),
            "return_dates": [stamp.isoformat() for stamp in is_result.daily_r.index],
        },
        trades_count=len(is_result.trades),
        returns=is_result.daily_r,
        db_path=db_path,
    )
    oos1_limits = run_limits_from_strategy(model, setup, close_at_end=True)
    oos1_prepared = fastbt.prepare(
        oos1_frame,
        cost,
        atr_windows=(model.exit.stop.n, 14),
        sessions=(oos1_limits,),
    )
    oos1_result = fastbt.run(
        compiler.compile(model, oos1_frame),
        oos1_frame,
        exit_spec_from_strategy(model),
        cost,
        oos1_limits,
        prepared=oos1_prepared,
    )
    databank.add_evaluation(
        strategy_id,
        segment="oos1",
        cost_profile=setup.cost_profile(),
        metrics={
            **dict(oos1_result.metrics),
            "return_dates": [stamp.isoformat() for stamp in oos1_result.daily_r.index],
        },
        trades_count=len(oos1_result.trades),
        returns=oos1_result.daily_r,
        db_path=db_path,
    )
    resampled = retester.retest(
        model, is_frame, oos1_frame, cost, setup
    )
    random_result = random_baseline(
        model,
        bars,
        cost,
        setup,
        prepared,
        trials=int(config.random_trials),
        seed=int(campaign["config"].get("seed", 0)) + 1_000,
    )
    mc_trades = _mc_trades(
        base.trades,
        paths=int(config.mc_paths),
        seed=int(campaign["config"].get("seed", 0)) + 2_000,
    )
    bootstrap = _bootstrap(
        base.daily_r,
        paths=int(config.bootstrap_paths),
        seed=int(campaign["config"].get("seed", 0)) + 3_000,
    )
    pbo, wf = _pbo_wf(
        campaign_id,
        db_path,
        trade_times_by_strategy=variant_trade_times(
            campaign_id,
            frame=is_frame,
            setup=setup,
            cost=cost,
            db_path=db_path,
        ),
    )
    regime = _regime(base.daily_r, _risk_for_account(setup.account))
    challenge = _challenge(base.daily_r)
    hour_weekday, streaks = _hour_streaks(base.trades, model.session.tz or setup.session_tz)
    prepared_is, _ = _prepared_for(model, is_frame, cost, setup)
    plateau = optimizer.plateau(
        model, is_frame, cost, setup, prepared_is
    )

    validations = {
        "retest": resampled,
        "test_vs_random_insample": random_result,
        "mc_trades": mc_trades,
        "bootstrap": bootstrap,
        "pbo": pbo,
        "wf": wf,
        "regime": regime,
        "challenge": challenge,
        "hour_weekday": hour_weekday,
        "streaks": streaks,
        "optimizer_plateau": plateau,
    }
    passed = {
        "retest": bool(resampled.get("stress_cost_x1_5_ok"))
        and bool(resampled.get("slippage_plus_2_ok")),
        "pbo": bool(pbo.get("pbo") is not None and float(pbo["pbo"]) <= 0.30),
        "wf": bool(wf.get("ok")),
        "regime": bool(regime.get("passed")),
        "challenge": bool(challenge.get("passed")),
        "mc_trades": bool(
            (mc_trades.get("shuffle_expectancy_p5") or -1.0) > 0.0
            or (mc_trades.get("resample_expectancy_p5") or -1.0) > 0.0
        ),
        "bootstrap": bool((bootstrap.get("expectancy_p5") or -1.0) > 0.0),
    }
    for name, result in validations.items():
        databank.add_validation(
            strategy_id,
            name,
            result,
            passed.get(name),
            db_path=db_path,
        )
    return {
        "strategy_id": int(strategy_id),
        "campaign_id": campaign_id,
        "base": base_metrics,
        "validations": validations,
        "passed": passed,
        "pbo_min_strategies": int(config.pbo_min_strategies),
    }


__all__ = [
    "WF_INFORMATIVE_MIN_TEST_TRADES",
    "account_regime",
    "random_baseline",
    "run",
    "variant_trade_times",
    "wf_trade_frequency",
]
