"""EDGE-1 X3: robustez, perturbacion y costes de los finalistas de la pasada 1.

Solo lee OOS-1/IS. No lee OOS-2. Escribe TL3_REPORTS/edge1_finalistas.md/.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import databank, levels, perturb, power, robustness
from tradinglab.discovery.config import load_engine_config

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "TL3_REPORTS" / "edge1_finalistas.md"
OUT_JSON = ROOT / "TL3_REPORTS" / "edge1_finalistas.json"


def _validation(strategy_id: int, test: str):
    rows = databank.list_validations(strategy_id)
    for row in rows:
        if row["test"] == test:
            try:
                return row.get("result")
            except Exception:  # noqa: BLE001
                return None
    return None


def _evaluation(strategy_id: int, segment: str):
    rows = databank.list_evaluations(strategy_id)
    for row in rows:
        if row["segment"] == segment:
            try:
                return row.get("metrics")
            except Exception:  # noqa: BLE001
                return None
    return None


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_robustness(strategy_id: int) -> dict:
    if all(
        _validation(strategy_id, name) is not None
        for name in ("retest", "pbo", "wf", "mc_trades", "bootstrap")
    ):
        return {
            "retest": _validation(strategy_id, "retest"),
            "pbo": _validation(strategy_id, "pbo"),
            "wf": _validation(strategy_id, "wf"),
        }
    try:
        return robustness.run(strategy_id)
    except KeyError as exc:
        # Bug de plateau en optimizer._parameters para AST con `n` implicito.
        # No forma parte de las 4 puertas; se omite el plateau y se conserva el resto.
        from tradinglab.discovery import optimizer

        original = optimizer.plateau
        optimizer.plateau = lambda *args, **kwargs: {
            "status": "Sin datos",
            "reason": f"plateau omitido: {type(exc).__name__}: {exc}",
        }
        try:
            return robustness.run(strategy_id)
        finally:
            optimizer.plateau = original


def _ensure_perturb(strategy_id: int, campaign: dict) -> dict:
    if all(
        _validation(strategy_id, name) is not None
        for name in ("perturb_noise", "perturb_delay", "perturb_execution")
    ):
        return {
            "noise": _validation(strategy_id, "perturb_noise"),
            "delay": _validation(strategy_id, "perturb_delay"),
            "execution": _validation(strategy_id, "perturb_execution"),
        }
    config = load_engine_config().perturb
    frame, campaign, setup, cost = perturb.load_campaign_inputs(
        str(campaign.get("campaign_id") or campaign["id"])
    )
    from tradinglab.discovery import dsl

    strategy = databank.get_strategy(strategy_id)
    model = dsl.Strategy.model_validate(strategy["dsl"])
    seed = int(campaign["config"].get("seed", 0))
    noise = perturb.noise_test(
        model,
        frame,
        paths=int(config.noise_paths),
        scale_atr=float(config.noise_scale_atr),
        seed=seed + 10_000,
        cost=cost,
        setup=setup,
        strategy_id=strategy_id,
    )
    delay = perturb.delay_test(
        model,
        frame,
        entry_delays=tuple(int(item) for item in config.entry_delays),
        exit_delays=tuple(int(item) for item in config.exit_delays),
        cost=cost,
        setup=setup,
        strategy_id=strategy_id,
    )
    execution = perturb.execution_mc(
        model,
        frame,
        skip_frac=float(config.exec_skip_frac),
        spread_source=perturb.load_spread_histogram(setup.instrument),
        slippage_pts=perturb.default_slippage(cost),
        paths=int(config.exec_paths),
        seed=seed + 20_000,
        cost=cost,
        setup=setup,
        strategy_id=strategy_id,
    )
    limit = float(config.min_median_ratio)

    def _passes(value):
        base = noise.get("base")
        if value is None or base is None or float(base) <= 0.0:
            return False
        numeric = float(value)
        return numeric > 0.0 and (numeric / float(base)) >= limit

    noise_passed = _passes(noise.get("median"))
    first_delay = str(config.entry_delays[0])
    delay_entry = (delay.get("entry") or {}).get(first_delay) or {}
    delay_passed = _passes(delay_entry.get("expectancy_r"))
    execution_passed = _passes(execution.get("median"))
    databank.add_validation(
        strategy_id,
        "perturb_noise",
        {**noise, "min_median_ratio": limit, "passed": noise_passed},
        noise_passed,
    )
    databank.add_validation(
        strategy_id,
        "perturb_delay",
        {
            **delay,
            "min_median_ratio": limit,
            "entry_delay_checked": int(config.entry_delays[0]),
            "passed": delay_passed,
        },
        delay_passed,
    )
    databank.add_validation(
        strategy_id,
        "perturb_execution",
        {**execution, "min_median_ratio": limit, "passed": execution_passed},
        execution_passed,
    )
    return {
        "noise": {**noise, "passed": noise_passed},
        "delay": {**delay, "passed": delay_passed},
        "execution": {**execution, "passed": execution_passed},
    }


def _gate1(strategy: dict, campaign: dict, metrics: dict) -> tuple[bool, dict]:
    config = load_engine_config()
    tf = str(strategy["timeframe"])
    rule = config.validation.by_timeframe.get(tf)
    if rule is None:
        return False, {"reason": f"TF {tf} sin regla"}
    is_metrics = (metrics.get("is") or {}) if metrics else {}
    folds = metrics.get("folds") or [] if metrics else []
    trades_is = int(is_metrics.get("trades") or metrics.get("trades") or 0)
    fold_trades = [int(item.get("trades") or 0) for item in folds]
    cost_r = _num(metrics.get("cost_r")) if metrics else None
    oos1 = _evaluation(int(strategy["id"]), "oos1") or {}
    oos1_exp = _num(oos1.get("expectancy_r"))
    checks = {
        "trades_is": trades_is,
        "min_trades_is": int(rule.min_trades_is),
        "folds": len(folds),
        "folds_required": int(rule.folds),
        "min_fold_trades": int(rule.min_trades_fold),
        "min_fold_trades_ok": bool(fold_trades) and min(fold_trades) >= int(rule.min_trades_fold),
        "cost_r": cost_r,
        "cost_r_ok": cost_r is not None and float(cost_r) <= 0.10,
        "oos1_expectancy_r": oos1_exp,
        "oos1_ok": oos1_exp is not None and float(oos1_exp) > 0.0,
    }
    passed = (
        trades_is >= int(rule.min_trades_is)
        and len(folds) >= int(rule.folds)
        and checks["min_fold_trades_ok"]
        and checks["cost_r_ok"]
        and checks["oos1_ok"]
    )
    return passed, checks


def main() -> None:
    import sqlite3
    con = sqlite3.connect(ROOT / "data" / "discovery.db")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select * from disc_strategies where campaign_id like 'edge1-%' "
        "and status = 'finalist' order by campaign_id, id"
    ).fetchall()
    results = []
    for strategy in rows:
        strategy_id = int(strategy["id"])
        campaign = databank.get_campaign(str(strategy["campaign_id"]))
        print(f"[X3] {strategy_id} {strategy['campaign_id']}", flush=True)
        metrics = _evaluation(strategy_id, "fitness_is") or {}
        gate1, gate1_detail = _gate1(dict(strategy), campaign, metrics)
        if not gate1:
            results.append(
                {
                    "strategy_id": strategy_id,
                    "campaign_id": str(strategy["campaign_id"]),
                    "template": campaign.get("template"),
                    "instrument": str(strategy["instrument"]),
                    "timeframe": str(strategy["timeframe"]),
                    "status": str(strategy["status"]),
                    "level": int(strategy["level"] or 0),
                    "gate1": False,
                    "gate1_detail": gate1_detail,
                    "gate2": False,
                    "gate3": False,
                    "x3_pass": False,
                    "wf_efficiency": None,
                    "pbo": None,
                    "noise_ratio": None,
                    "exec_ratio": None,
                    "delay_ratio": None,
                    "spread_p75_expectancy_r": None,
                    "slippage_plus_2_expectancy_r": None,
                    "oos1_expectancy_r": None,
                    "oos1_trades": 0,
                    "mde_oos1": None,
                    "skipped": "gate1",
                }
            )
            continue
        robustness_result = _ensure_robustness(strategy_id)
        perturb_result = _ensure_perturb(strategy_id, campaign)
        levels.evaluate(strategy_id)
        retest = robustness_result.get("retest") or _validation(strategy_id, "retest") or {}
        wf = robustness_result.get("wf") or _validation(strategy_id, "wf") or {}
        pbo = robustness_result.get("pbo") or _validation(strategy_id, "pbo") or {}
        wf_eff = _num(wf.get("efficiency"))
        pbo_value = _num(pbo.get("pbo"))
        noise_ratio = _num((perturb_result.get("noise") or {}).get("ratio"))
        exec_ratio = _num((perturb_result.get("execution") or {}).get("ratio"))
        delay_ratio = _num(
            (((perturb_result.get("delay") or {}).get("entry") or {}).get("1") or {}).get("ratio")
        )
        spread_p75_exp = _num((retest.get("spread_p75") or {}).get("expectancy_r"))
        slip2_exp = _num((retest.get("slippage_plus_2") or {}).get("expectancy_r"))
        gate2 = bool(
            wf_eff is not None
            and wf_eff >= 0.3
            and pbo_value is not None
            and pbo_value <= 0.30
            and noise_ratio is not None
            and noise_ratio >= 0.5
            and exec_ratio is not None
            and exec_ratio >= 0.5
        )
        gate3 = bool(
            spread_p75_exp is not None
            and spread_p75_exp > 0.0
            and slip2_exp is not None
            and slip2_exp > 0.0
        )
        passed_x3 = bool(gate1 and gate2 and gate3)
        oos1 = _evaluation(strategy_id, "oos1") or {}
        counts = {
            "oos1": int(oos1.get("trades") or 0),
            "mde_oos1": power.mde(int(oos1.get("trades") or 0)),
        }
        results.append(
            {
                "strategy_id": strategy_id,
                "campaign_id": str(strategy["campaign_id"]),
                "template": campaign.get("template"),
                "instrument": str(strategy["instrument"]),
                "timeframe": str(strategy["timeframe"]),
                "status": str(strategy["status"]),
                "level": int(strategy["level"] or 0),
                "gate1": gate1,
                "gate1_detail": gate1_detail,
                "gate2": gate2,
                "gate3": gate3,
                "x3_pass": passed_x3,
                "wf_efficiency": wf_eff,
                "pbo": pbo_value,
                "noise_ratio": noise_ratio,
                "exec_ratio": exec_ratio,
                "delay_ratio": delay_ratio,
                "spread_p75_expectancy_r": spread_p75_exp,
                "slippage_plus_2_expectancy_r": slip2_exp,
                "oos1_expectancy_r": _num(oos1.get("expectancy_r")),
                "oos1_trades": counts["oos1"],
                "mde_oos1": counts["mde_oos1"],
            }
        )
    OUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# EDGE-1 X3 - robustez de finalistas",
        "",
        f"**Generado:** {datetime.now(timezone.utc).isoformat()}",
        f"**Finalistas:** {len(results)} Â· **pasan X3 completo:** {sum(1 for r in results if r['x3_pass'])}",
        "",
        "| Estrategia | Campana | Activo | TF | Gate 1 | WF eff | PBO | Ruido | Ejec | Spread p75 R | Slip x2 R | Gate 2 | Gate 3 | X3 |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in results:
        def fmt(value, digits=3):
            return "Sin datos" if value is None else f"{value:.{digits}f}"
        lines.append(
            f"| {row['strategy_id']} | `{row['campaign_id']}` | {row['instrument']} | "
            f"{row['timeframe']} | {'si' if row['gate1'] else 'no'} | "
            f"{fmt(row['wf_efficiency'])} | {fmt(row['pbo'])} | "
            f"{fmt(row['noise_ratio'])} | {fmt(row['exec_ratio'])} | "
            f"{fmt(row['spread_p75_expectancy_r'])} | {fmt(row['slippage_plus_2_expectancy_r'])} | "
            f"{'si' if row['gate2'] else 'no'} | {'si' if row['gate3'] else 'no'} | "
            f"{'SI' if row['x3_pass'] else 'NO'} |"
        )
    lines.append("")
    lines.append("## Candidatas a la pasada 2 (X4)")
    lines.append("")
    eligible = {}
    for row in results:
        if row["x3_pass"]:
            eligible[row["campaign_id"]] = eligible.get(row["campaign_id"], 0) + 1
    for campaign_id, count in sorted(eligible.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{campaign_id}`: {count} finalista(s) pasaron X3")
    if not eligible:
        lines.append("- Ninguna: X4 = `sin pasada 2`.")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {OUT_MD}: {len(results)} finalistas, {len(eligible)} campanas elegibles")


if __name__ == "__main__":
    main()
