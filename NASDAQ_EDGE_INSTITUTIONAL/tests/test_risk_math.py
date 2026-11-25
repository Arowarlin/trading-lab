"""Espejo en Python del motor de riesgo del indicador Pine (auditoría monetaria MNQ/NQ).

Replica exactamente las fórmulas de 04_PINE_SCRIPT/Nasdaq_Edge_Indicator.pine:
    perContract = stopPts * pv + commRT + 2 * slipTicks * tick * pv
    contracts   = min(floor(budget / perContract), firmMaxContracts, newsCap)
    budget      = min(riesgo, riesgo_max, perdida_dia_restante, dll_firma_restante,
                      distancia_umbral - colchon) * mult_tier3
"""

from __future__ import annotations

import math

MNQ = {"pv": 2.0, "tick": 0.25}
NQ = {"pv": 20.0, "tick": 0.25}


def per_contract(stop_pts, inst, comm, slip_ticks):
    return stop_pts * inst["pv"] + comm + 2 * slip_ticks * inst["tick"] * inst["pv"]


def budget(risk=150, risk_max=250, day_loss=300, pnl_today=0, firm_dll=None, balance=50000, dd=48000, buffer=100, mult=1.0):
    rem_personal = day_loss + min(pnl_today, 0)
    rem_firm = firm_dll + min(pnl_today, 0) if firm_dll else 1e9
    return min(risk, risk_max, rem_personal, rem_firm, balance - dd - buffer) * mult


def contracts(b, pc, firm_max, news_cap=10**6):
    raw = math.floor(b / pc) if pc > 0 else 0
    return max(0, min(raw, firm_max, news_cap))


def test_tick_values():
    assert MNQ["tick"] * MNQ["pv"] == 0.50
    assert NQ["tick"] * NQ["pv"] == 5.00


def test_mnq_reference_case():
    pc = per_contract(20, MNQ, comm=1.50, slip_ticks=1)  # 40 + 1,50 + 1,00
    assert pc == 42.5
    assert contracts(budget(), pc, firm_max=50) == 3  # riesgo previsto 127,50 ≤ 150


def test_nq_same_stop_is_no_trade():
    pc = per_contract(20, NQ, comm=5.76, slip_ticks=1)  # 400 + 5,76 + 10
    assert contracts(budget(), pc, firm_max=5) == 0


def test_daily_loss_and_streak_budget():
    assert budget(pnl_today=-200) == 100  # quedan 100 de 300
    assert budget(pnl_today=-300) == 0
    assert budget(balance=48150, dd=48000) == 50  # colchón de 100 sobre el umbral


def test_topstep_tier1_cap_and_firm_cap():
    pc = per_contract(2, MNQ, comm=1.50, slip_ticks=1)  # 6,50 → 23 por presupuesto
    assert contracts(budget(), pc, firm_max=50) == 23
    assert contracts(budget(), pc, firm_max=50, news_cap=3) == 3
    assert contracts(budget(), pc, firm_max=20) == 20


def test_tier3_halves_budget():
    assert budget(mult=0.5) == 75
