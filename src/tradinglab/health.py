"""Salud de cuenta 0-100 y retorno ajustado por flujos (TWR).

Puntuación determinista y documentada. Los pesos viven en
`config/ops.yaml -> fund_health.weights`. Si falta un componente, se ignora y
se informa `coverage`; nunca se inventa el dato que falta.
"""
from __future__ import annotations

from typing import Any

from .config import FundHealthSettings

DRIFT_SCORE = {"ok": 100.0, "vigilar": 50.0, "deriva": 0.0}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def time_weighted_return(
    equity_curve: list[dict], flows: list[dict]
) -> dict:
    """TWR diario con depósitos/retiros externos.

    Se toma el último equity de cada día. El flujo del día se resta al equity
    final antes de calcular el retorno del subperiodo:
        r = (equity_fin - flujo_neto) / equity_inicio - 1
    Depósitos suman; retiros restan. Sin equity suficiente: sin datos.
    """
    by_day: dict[str, float] = {}
    for point in equity_curve or []:
        stamp = str(point.get("ts") or "")
        value = point.get("equity")
        if not stamp or value is None:
            continue
        by_day[stamp[:10]] = float(value)
    days = sorted(by_day)
    if len(days) < 2:
        return {
            "twr": None,
            "days": len(days),
            "flows": len(flows or []),
            "reason": "Sin datos: se necesitan al menos 2 cierres diarios",
        }
    signed_flows: dict[str, float] = {}
    for flow in flows or []:
        stamp = str(flow.get("ts") or "")
        if not stamp:
            continue
        amount = float(flow.get("amount") or 0.0)
        if str(flow.get("kind")) == "withdrawal":
            amount = -amount
        signed_flows[stamp[:10]] = signed_flows.get(stamp[:10], 0.0) + amount
    growth = 1.0
    used_flows = 0
    for index in range(1, len(days)):
        start = by_day[days[index - 1]]
        end = by_day[days[index]]
        if start <= 0:
            return {
                "twr": None,
                "days": len(days),
                "flows": len(flows or []),
                "reason": "Sin datos: equity inicial no positivo",
            }
        flow = signed_flows.get(days[index], 0.0)
        if flow:
            used_flows += 1
        growth *= (end - flow) / start
    return {
        "twr": growth - 1.0,
        "days": len(days),
        "flows": used_flows,
        "reason": None,
    }


def _concentration_score(
    trades: list[Any], max_concentration: float
) -> tuple[float | None, str]:
    if not trades:
        return None, "Sin datos: sin operaciones cerradas"
    net = sum(float(trade.pnl) for trade in trades)
    if net <= 0:
        return None, "Sin datos: el neto no es positivo"
    top3 = sum(
        sorted((float(trade.pnl) for trade in trades), reverse=True)[:3]
    )
    share = top3 / net
    if max_concentration <= 0:
        return None, "Sin datos: max_concentration <= 0"
    score = 100.0 * (1.0 - min(1.0, max(0.0, share) / max_concentration))
    return _clamp(score), f"top3/neto {share:.1%} · máximo {max_concentration:.0%}"


def _streak_score(trades: list[Any], max_streak: int) -> tuple[float | None, str]:
    if not trades:
        return None, "Sin datos: sin operaciones cerradas"
    ordered = sorted(trades, key=lambda trade: (trade.exit_ts, trade.exit_fill_id))
    streak = 0
    for trade in reversed(ordered):
        if float(trade.pnl) < 0:
            streak += 1
        else:
            break
    if max_streak <= 0:
        return None, "Sin datos: max_streak <= 0"
    score = 100.0 * (1.0 - min(1.0, streak / max_streak))
    return _clamp(score), f"racha perdedora {streak} · máximo {max_streak}"


def score_account(
    *,
    usage: dict,
    trades: list[Any],
    drift_statuses: list[str] | None,
    cfg: FundHealthSettings,
) -> dict:
    """Score 0-100 con desglose por componente y cobertura."""
    weights = cfg.weights.model_dump()
    total_weight = sum(float(value) for value in weights.values())
    components: dict[str, dict] = {}

    daily_used = usage.get("daily_used_pct")
    if daily_used is None:
        components["daily_cushion"] = {
            "score": None,
            "weight": float(weights.get("daily_cushion", 0.0)),
            "detail": "Sin datos de uso diario",
        }
    else:
        score = 100.0 * (1.0 - min(1.0, max(0.0, float(daily_used))))
        components["daily_cushion"] = {
            "score": _clamp(score),
            "weight": float(weights.get("daily_cushion", 0.0)),
            "detail": f"usado {float(daily_used):.1%} del límite diario",
        }

    max_used = usage.get("drawdown_used_pct")
    if max_used is None:
        components["drawdown_cushion"] = {
            "score": None,
            "weight": float(weights.get("drawdown_cushion", 0.0)),
            "detail": "Sin datos de drawdown",
        }
    else:
        score = 100.0 * (1.0 - min(1.0, max(0.0, float(max_used))))
        components["drawdown_cushion"] = {
            "score": _clamp(score),
            "weight": float(weights.get("drawdown_cushion", 0.0)),
            "detail": f"usado {float(max_used):.1%} del límite máximo",
        }

    streak_score, streak_detail = _streak_score(trades, cfg.max_streak)
    components["streak"] = {
        "score": streak_score,
        "weight": float(weights.get("streak", 0.0)),
        "detail": streak_detail,
    }

    statuses = [status for status in (drift_statuses or []) if status in DRIFT_SCORE]
    if statuses:
        worst = min(DRIFT_SCORE[status] for status in statuses)
        components["drift"] = {
            "score": worst,
            "weight": float(weights.get("drift", 0.0)),
            "detail": " · ".join(statuses),
        }
    else:
        components["drift"] = {
            "score": None,
            "weight": float(weights.get("drift", 0.0)),
            "detail": "Sin datos de deriva",
        }

    concentration_score, concentration_detail = _concentration_score(
        trades, cfg.max_concentration
    )
    components["concentration"] = {
        "score": concentration_score,
        "weight": float(weights.get("concentration", 0.0)),
        "detail": concentration_detail,
    }

    available = [
        item
        for item in components.values()
        if item["score"] is not None and item["weight"] > 0
    ]
    available_weight = sum(item["weight"] for item in available)
    coverage = (available_weight / total_weight) if total_weight > 0 else 0.0
    score = (
        sum(item["score"] * item["weight"] for item in available)
        / available_weight
        if available_weight > 0
        else None
    )
    if score is None:
        label = "Sin datos"
    elif score >= 80:
        label = "ok"
    elif score >= 60:
        label = "vigilar"
    else:
        label = "riesgo"
    return {
        "score": round(score, 1) if score is not None else None,
        "label": label,
        "coverage": round(coverage, 4),
        "partial": coverage < 1.0 - 1e-9,
        "components": components,
        "weights_total": round(total_weight, 6),
    }


__all__ = ["score_account", "time_weighted_return"]
