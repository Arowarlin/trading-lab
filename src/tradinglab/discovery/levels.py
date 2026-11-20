"""Niveles deterministas 1–4, veredicto y confirmación OOS-2.

La IA nunca cambia niveles. Cualquier prueba no calculable cuenta como no
superada y se muestra como "Sin datos"; el nivel 4 nunca pasa por falta de
datos.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..config import DEFAULT_DB
from ..stats import dsr_from_returns, period_sharpe
from . import campaigns, databank, dsl, fastbt, jobs, robustness
from .config import load_engine_config
from .specs import exit_spec_from_strategy, run_limits_from_strategy


def load_tests(strategy_id: int, *, db_path=None) -> dict[str, Any]:
    return {
        row["test"]: row["result"]
        for row in databank.list_validations(strategy_id, db_path=db_path)
    }


def _evaluation_metrics(
    strategy_id: int, segment: str, *, db_path
) -> dict[str, Any] | None:
    evaluations = databank.list_evaluations(strategy_id, db_path=db_path)
    for evaluation in evaluations:
        if evaluation["segment"] == segment:
            return evaluation["metrics"]
    return None


def _verdict(
    level: int,
    tests: dict[str, Any],
    is_expectancy: float | None,
    oos1: float | None,
    oos2: float | None,
    pbo_value: float | None,
    *,
    is_finalist: bool,
) -> str:
    if level >= 4:
        return "ROBUSTA"
    if (
        is_expectancy is not None
        and float(is_expectancy) > 0
        and (
            (oos1 is not None and float(oos1) <= 0)
            or (oos2 is not None and float(oos2) <= 0)
            or (pbo_value is not None and float(pbo_value) > 0.5)
        )
    ):
        return "SOBREAJUSTADA"
    if not is_finalist:
        return "SIN VEREDICTO"
    cost15 = (
        (tests.get("retest") or {}).get("cost_x1_5") or {}
    ).get("expectancy_r")
    slip2 = (
        (tests.get("retest") or {}).get("slippage_plus_2") or {}
    ).get("expectancy_r")
    challenge_ok = (tests.get("challenge") or {}).get("passed")
    wf_ok = (tests.get("wf") or {}).get("ok")
    regime_ok = (tests.get("regime") or {}).get("passed")
    random_oos2 = (tests.get("test_vs_random_oos2") or {}).get("percentile")
    fragile = (
        (cost15 is not None and float(cost15) <= 0.0)
        or (slip2 is not None and float(slip2) <= 0.0)
        or challenge_ok is False
        or wf_ok is False
        or regime_ok is False
        or (random_oos2 is not None and float(random_oos2) < 95.0)
    )
    if fragile:
        return "FRÁGIL"
    if level >= 3:
        return "MODERADA"
    return "SIN VEREDICTO"


def evaluate(
    strategy_id: int,
    *,
    db_path=None,
    tests: dict[str, Any] | None = None,
    campaign: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strategy = databank.get_strategy(strategy_id, db_path=db_path)
    if strategy is None:
        raise ValueError(f"estrategia no encontrada: {strategy_id}")
    campaign = campaign or databank.get_campaign(
        str(strategy["campaign_id"]), db_path=db_path
    )
    if campaign is None:
        raise ValueError(f"campaña no registrada: {strategy['campaign_id']}")
    tests = load_tests(strategy_id, db_path=db_path) if tests is None else tests
    is_metrics = _evaluation_metrics(strategy_id, "fitness_is", db_path=db_path)
    oos1_metrics = _evaluation_metrics(strategy_id, "oos1", db_path=db_path)
    oos2_metrics = _evaluation_metrics(strategy_id, "oos2", db_path=db_path)
    is_full = (
        (is_metrics or {}).get("is", {}).get("expectancy_r")
        if isinstance(is_metrics, dict)
        else None
    )
    is_expectancy = is_full
    oos1 = (oos1_metrics or {}).get("expectancy_r")
    oos2 = (oos2_metrics or {}).get("expectancy_r")
    pbo_value = (tests.get("pbo") or {}).get("pbo")
    dsr_confirm = (tests.get("dsr_confirm") or {}).get("dsr")
    challenge_ok = (tests.get("challenge") or {}).get("passed")
    wf_ok = (tests.get("wf") or {}).get("ok")
    regime_ok = (tests.get("regime") or {}).get("passed")
    retest = tests.get("retest") or {}
    random_insample = (tests.get("test_vs_random_insample") or {}).get(
        "percentile"
    )
    random_oos2 = (tests.get("test_vs_random_oos2") or {}).get("percentile")
    cost15 = (retest.get("cost_x1_5") or {}).get("expectancy_r")
    slip2 = (retest.get("slippage_plus_2") or {}).get("expectancy_r")
    is_finalist = str(strategy["status"]) == "finalist"
    min_trades_oos2 = int(load_engine_config().robustness.min_trades_oos2)
    oos2_trades = (oos2_metrics or {}).get("trades")
    enough_oos2 = (
        oos2_trades is not None and int(oos2_trades) >= min_trades_oos2
    )

    level = 1
    if (
        is_expectancy is not None
        and float(is_expectancy) > 0
        and str(strategy["status"]) not in {"rejected", "archived"}
    ):
        level = 2
    level3 = (
        is_finalist
        and is_expectancy is not None
        and float(is_expectancy) > 0.0
        and cost15 is not None
        and float(cost15) > 0.0
    )
    if level3:
        level = 3
    level4 = (
        level3
        and enough_oos2
        and oos2 is not None
        and float(oos2) > 0.0
        and dsr_confirm is not None
        and float(dsr_confirm) >= 0.90
        and pbo_value is not None
        and float(pbo_value) <= 0.30
        and wf_ok is True
        and regime_ok is True
        and slip2 is not None
        and float(slip2) > 0.0
        and challenge_ok is True
        and random_oos2 is not None
        and float(random_oos2) >= 95.0
    )
    if level4:
        level = 4
    verdict = _verdict(
        level,
        tests,
        is_expectancy,
        oos1,
        oos2,
        pbo_value,
        is_finalist=is_finalist,
    )
    databank.set_strategy_verdict(strategy_id, level, verdict, db_path=db_path)

    missing = [
        name
        for name, value in (
            ("test_vs_random_oos2", random_oos2),
            ("cost_x1_5", cost15),
            ("slippage_plus_2", slip2),
            ("oos2", oos2),
            ("dsr_confirm", dsr_confirm),
            ("min_trades_oos2", min_trades_oos2 if enough_oos2 else None),
        )
        if value is None
    ]
    for name in ("pbo", "wf", "regime", "challenge"):
        record = tests.get(name)
        absent = record is None or str(record.get("status") or "") == "Sin datos"
        if name == "pbo" and record is not None:
            absent = absent or record.get("pbo") is None
        if name in {"regime", "challenge"} and record is not None:
            absent = absent or record.get("passed") is None
        if absent and name not in missing:
            missing.append(name)
    return {
        "strategy_id": int(strategy_id),
        "campaign_id": str(strategy["campaign_id"]),
        "level": int(level),
        "verdict": verdict,
        "is_expectancy_r": is_expectancy,
        "oos1_expectancy_r": oos1,
        "oos2_expectancy_r": oos2,
        "trades_oos2": oos2_trades,
        "min_trades_oos2": min_trades_oos2,
        "dsr_confirm": dsr_confirm,
        "pbo": pbo_value,
        "wf_ok": wf_ok,
        "regime_ok": regime_ok,
        "challenge_ok": challenge_ok,
        "test_vs_random_insample_pct": random_insample,
        "test_vs_random_oos2_pct": random_oos2,
        "cost_x1_5_expectancy_r": cost15,
        "slippage_plus_2_expectancy_r": slip2,
        "level3": level3,
        "level4": level4,
        "sin_datos": missing,
    }


def _trial_srs(strategy_id: int, campaign_id: str, k: int, *, db_path) -> list[float]:
    finalists = databank.list_strategies(
        campaign_id=campaign_id, status="finalist", limit=None, db_path=db_path
    )
    values: list[float] = []
    for finalist in finalists:
        frames = []
        for segment in ("fitness_is", "oos1"):
            metrics = _evaluation_metrics(
                int(finalist["id"]), segment, db_path=db_path
            )
            if not metrics:
                continue
            dates = metrics.get("return_dates") or []
            evaluation = [
                item
                for item in databank.list_evaluations(
                    int(finalist["id"]), db_path=db_path
                )
                if item["segment"] == segment
            ]
            if not evaluation or not dates:
                continue
            frames.append(
                pd.Series(evaluation[0]["returns"], index=pd.to_datetime(dates))
            )
        if frames:
            combined = pd.concat(frames, sort=False)
            try:
                values.append(period_sharpe(combined.to_numpy(dtype=float)))
            except Exception:  # noqa: BLE001
                continue
    return values[:k]


def confirm(
    strategy_id: int,
    *,
    approved_by_operator: bool = False,
    frame: pd.DataFrame | None = None,
    db_path=None,
    learning_db=None,
) -> dict[str, Any]:
    """Lectura única de OOS-2 y DSR de confirmación (solo nivel 3)."""

    if not approved_by_operator:
        raise PermissionError(
            "confirm requiere --approved-by-operator; no se ha leído OOS-2"
        )
    strategy = databank.get_strategy(strategy_id, db_path=db_path)
    if strategy is None:
        raise ValueError(f"estrategia no encontrada: {strategy_id}")
    campaign_id = str(strategy["campaign_id"])
    campaign = databank.get_campaign(campaign_id, db_path=db_path)
    if campaign is None:
        raise ValueError(f"campaña no registrada: {campaign_id}")
    tests = load_tests(strategy_id, db_path=db_path)
    current = evaluate(
        strategy_id, db_path=db_path, tests=tests, campaign=campaign
    )
    if current["level"] < 3:
        raise ValueError(
            f"la estrategia no pasó el nivel 3 (nivel {current['level']})"
        )
    k = campaign.get("n_finalists")
    if k is None:
        k = len(
            databank.list_strategies(
                campaign_id=campaign_id,
                status="finalist",
                limit=None,
                db_path=db_path,
            )
        )
    k = int(k or 0)
    if k < 1:
        raise ValueError("Sin datos: K de finalistas no disponible")
    oos2_frame = campaigns.read_holdout(strategy_id, frame=frame, db_path=db_path)
    model = dsl.Strategy.model_validate(strategy["dsl"])
    setup = jobs.QueueSetup.from_campaign(campaign, bars=None)
    from ..propfund.costs import load_profile

    profile = load_profile(setup.account, setup.instrument, firm=setup.firm)
    cost = fastbt.cost_from_profile(profile, use_p75=bool(setup.use_p75))
    limits = run_limits_from_strategy(model, setup, close_at_end=True)
    trailing = model.exit.trailing or {}
    prepared = fastbt.prepare(
        oos2_frame,
        cost,
        atr_windows=(model.exit.stop.n, int(trailing.get("n", 14))),
        sessions=(limits,),
    )
    from . import compiler

    signals = compiler.compile(model, oos2_frame)
    result = fastbt.run(
        signals,
        oos2_frame,
        exit_spec_from_strategy(model),
        cost,
        limits,
        prepared=prepared,
    )
    oos2_metrics = {
        **dict(result.metrics),
        "return_dates": [stamp.isoformat() for stamp in result.daily_r.index],
    }
    databank.add_evaluation(
        strategy_id,
        segment="oos2",
        cost_profile=setup.cost_profile(),
        metrics=oos2_metrics,
        trades_count=len(result.trades),
        returns=result.daily_r,
        db_path=db_path,
    )
    config = load_engine_config().robustness
    min_trades = int(config.min_trades_oos2)
    trades_oos2 = len(result.trades)
    enough_trades = trades_oos2 >= min_trades

    if enough_trades:
        random_oos2 = robustness.random_baseline(
            model,
            oos2_frame,
            cost,
            setup,
            prepared,
            trials=int(config.random_trials),
            seed=int(campaign["config"].get("seed", 0)) + 4_000,
            real_expectancy=result.metrics.get("expectancy_r"),
            real_trades=result.trades,
        )
    else:
        random_oos2 = {
            "status": "Sin datos",
            "percentile": None,
            "reason": (
                f"operaciones OOS-2 {trades_oos2} < min_trades_oos2 "
                f"{min_trades}"
            ),
            "trades_oos2": trades_oos2,
            "min_trades_oos2": min_trades,
            "note": "no cuenta como trial del DSR",
        }
    random_oos2["scope"] = "oos2"
    random_oos2["trades_oos2"] = trades_oos2
    random_oos2["min_trades_oos2"] = min_trades

    if not enough_trades:
        dsr = {
            "status": "Sin datos",
            "dsr": None,
            "kind": "Sin datos",
            "reason": (
                f"operaciones OOS-2 {trades_oos2} < min_trades_oos2 "
                f"{min_trades}"
            ),
            "k_finalists": k,
            "trades_oos2": trades_oos2,
            "min_trades_oos2": min_trades,
        }
        trial_srs = []
    else:
        trial_srs = _trial_srs(strategy_id, campaign_id, k, db_path=db_path)
        if k > 1 and len(trial_srs) < k:
            dsr = {
                "status": "Sin datos",
                "dsr": None,
                "kind": "Sin datos",
                "reason": (
                    f"faltan series IS+OOS-1 de finalistas "
                    f"({len(trial_srs)} de {k})"
                ),
                "k_finalists": k,
                "trial_srs_available": len(trial_srs),
            }
        else:
            try:
                if k == 1:
                    dsr = dsr_from_returns(
                        result.daily_r.to_numpy(dtype=float),
                        [],
                        n_trials=1,
                        periods_per_year=252.0,
                        benchmark_sr=0.0,
                    )
                    dsr["kind"] = "psr_sr0"
                    dsr["note"] = "K=1: PSR frente a SR 0"
                else:
                    dsr = dsr_from_returns(
                        result.daily_r.to_numpy(dtype=float),
                        trial_srs,
                        n_trials=k,
                        periods_per_year=252.0,
                    )
                    dsr["kind"] = "dsr_k_finalists"
            except Exception as exc:  # noqa: BLE001 - Sin datos, no se aprueba
                dsr = {
                    "status": "Sin datos",
                    "dsr": None,
                    "kind": "Sin datos",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "k_finalists": k,
                }
    dsr["k_finalists"] = k
    dsr["trial_srs_available"] = len(trial_srs)
    dsr["trades_oos2"] = trades_oos2
    dsr["min_trades_oos2"] = min_trades
    databank.add_validation(
        strategy_id, "oos2", oos2_metrics, float(oos2_metrics.get("expectancy_r") or 0.0) > 0.0,
        db_path=db_path,
    )
    databank.add_validation(
        strategy_id,
        "test_vs_random_oos2",
        random_oos2,
        (random_oos2.get("percentile") is not None)
        and float(random_oos2["percentile"]) >= 95.0,
        db_path=db_path,
    )
    databank.add_validation(
        strategy_id, "dsr_confirm", dsr, float(dsr.get("dsr") or 0.0) >= 0.90,
        db_path=db_path,
    )
    tests = load_tests(strategy_id, db_path=db_path)
    updated = evaluate(
        strategy_id, db_path=db_path, tests=tests, campaign=campaign
    )
    from ..learning import count_tests

    global_tests = count_tests(
        learning_db or DEFAULT_DB, discovery_db=db_path
    )
    updated["global_dsr_tests"] = int(global_tests)
    updated["oos2"] = oos2_metrics
    updated["dsr_confirm"] = dsr
    updated["test_vs_random_oos2"] = random_oos2
    return updated


__all__ = ["confirm", "evaluate", "load_tests"]
