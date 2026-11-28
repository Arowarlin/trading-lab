"""Compatibilidad estrategia ↔ firma y programa, con las reglas que lo deciden (PFIE; FUT-P3).

Silencio ≠ permiso: una política de bots no verificada cuenta como no permitida para una estrategia
automática. Cada motivo cita su regla.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .rules import Program, max_contracts_for

# Umbrales de microscalping publicados (segundos de duración mínima), con margen ×3 en el criterio NR-A2.
MICROSCALPING_S = {"lucid": 5, "tradeify": 10, "tradeday": 10}


@dataclass(frozen=True)
class StrategyProfile:
    automated: bool
    platform: str                  # "nt8" | "projectx" | "tradovate" | "ticket"
    root: str
    max_micro_eq: float
    median_hold_s: float
    last_exit_local: time          # hora local (zona del flat_by del programa) de la última salida
    trades_news: bool


def verdict(firm: dict, program: Program, profile: StrategyProfile, platform_support: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    conditions: list[str] = []
    cat = (firm.get("automation") or {}).get("category", "unverified")
    if profile.automated:
        if cat in {"prohibited", "unverified"}:
            reasons.append(f"automatización {cat} (firms_futures.yaml)")
        elif cat == "conditional":
            conditions.append("automatización condicional: confirmar condiciones por escrito (firm_conditions_ack)")
    if profile.platform not in (platform_support.get(firm["id"]) or []):
        reasons.append(f"plataforma {profile.platform} no soportada (execution.yaml/platform_support)")
    limit = MICROSCALPING_S.get(firm["id"])
    if limit is not None and profile.median_hold_s < 3 * limit:
        reasons.append(f"duración mediana {profile.median_hold_s:g} s < 3 × {limit} s (microscalping)")
    for phase in ("evaluation", "funded"):
        cap = max_contracts_for(program, phase, 0.0) if getattr(program.phases, phase) is not None else None
        if cap is not None:
            cap_micro = cap if program.instrument_unit == "micro" else 10 * cap
            if profile.max_micro_eq > cap_micro:
                reasons.append(f"{profile.max_micro_eq:g} micro-eq > máximo {cap_micro} en {phase}")
    flat = program.phases.evaluation.flat_by
    if flat is None or flat.value is None:
        conditions.append("hora de cierre sin dato")
    else:
        hh, mm = str(flat.value).split()[0].split(":")
        if profile.last_exit_local > time(int(hh), int(mm)):
            reasons.append(f"última salida {profile.last_exit_local} > cierre obligatorio {flat.value}")
    news = program.compliance.get("news_t1") or program.compliance.get("news")
    if profile.trades_news and news is not None and news.window_minutes:
        conditions.append(f"noticias: ventana de ±{news.window_minutes} min en {news.phases or 'todas las fases'}")
    if reasons:
        return "incompatible", reasons + conditions
    if conditions:
        return "con_condiciones", conditions
    return "compatible", []
