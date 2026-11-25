"""Tests sintéticos del motor de la Fase C (sin datos reales)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location("phase_c", TOOLS / "phase_c.py")
pc = importlib.util.module_from_spec(_spec)
sys.modules["phase_c"] = pc
_spec.loader.exec_module(pc)
pb = pc.pb
ZERO = pc.Costs(slip_ticks=0, comm_usd=0)


def _sessions(last_path: np.ndarray, n_flat: int = 20) -> list[dict]:
    frames = []
    days = pd.bdate_range("2015-04-01", periods=n_flat + 1)
    for d in days:
        path = last_path if d == days[-1] else 100 + 0.5 * np.sin(np.arange(390) / 7)
        idx = pd.date_range(f"{d.date()} 09:30", periods=390, freq="1min", tz=pb.NY)
        frames.append(
            pd.DataFrame(
                {"open": path, "high": path + 0.25, "low": path - 0.25, "close": path, "volume": 100.0, "spread": np.nan},
                index=idx,
            )
        )
    rows = pb.build(pd.concat(frames), str(days[-1].date()), set())
    return pc.prepare(rows)


def _stats():
    return {k: 0 for k in ("limit_unfilled", "bad_stop", "target_lt_1R", "no_trade_size", "blocked_daily")}


def _flat_session():
    r = _sessions(np.full(390, 100.0))[-1]
    for k in ("o", "h", "l", "c"):
        r[k] = r[k].copy()
    return r


def test_stop_first_when_stop_and_tp_in_same_bar():
    r = _flat_session()
    j = int(np.searchsorted(r["t"], 600))  # 10:00
    r["h"][j], r["l"][j] = 120.0, 80.0  # la misma vela toca TP1 y stop
    od = pc.Order(k5=int(np.flatnonzero(r["b"]["end_min"] == 600)[0]), side=1, stop=95.0)
    tr = pc.simulate_session(r, [od], ZERO, _stats())
    assert tr[0].reason == "stop" and tr[0].r_net == -1.0


def test_tp1_then_breakeven_and_full_tp2():
    r = _flat_session()
    k5 = int(np.flatnonzero(r["b"]["end_min"] == 600)[0])
    j = int(np.searchsorted(r["t"], 600))
    r["h"][j + 1] = 105.5  # TP1 (riesgo 5 → TP1 105)
    r["l"][j + 3] = 99.5  # vuelve a BE
    tr = pc.simulate_session(r, [pc.Order(k5, 1, 95.0)], ZERO, _stats())
    assert tr[0].reason == "be" and abs(tr[0].r_net - 0.5) < 1e-9

    r = _flat_session()
    r["h"][j + 1] = 105.5
    r["l"][j + 2 :] = 100.5  # no vuelve a BE
    r["h"][j + 4] = 111.0  # TP2 = 110
    tr = pc.simulate_session(r, [pc.Order(k5, 1, 95.0)], ZERO, _stats())
    assert tr[0].reason == "tp2" and abs(tr[0].r_net - 1.5) < 1e-9


def test_costs_reduce_r_and_size_gate():
    r = _flat_session()
    k5 = int(np.flatnonzero(r["b"]["end_min"] == 600)[0])
    st = _stats()
    tr = pc.simulate_session(r, [pc.Order(k5, 1, 100.0 - 80.0)], pc.Costs(), st)  # 80 pt × $2 = $160 > $150
    assert tr == [] and st["no_trade_size"] == 1
    j = int(np.searchsorted(r["t"], 600))
    r["l"][j + 2] = 94.0
    tr = pc.simulate_session(r, [pc.Order(k5, 1, 95.0)], pc.Costs(), _stats())
    assert tr[0].r_net < -1.0  # slippage de entrada y stop + comisión


def test_daily_stop_after_two_losses():
    r = _flat_session()
    orders = []
    for m in (600, 620, 640, 660):
        k5 = int(np.flatnonzero(r["b"]["end_min"] == m)[0])
        j = int(np.searchsorted(r["t"], m))
        r["l"][j + 1] = 94.0
        orders.append(pc.Order(k5, 1, 95.0))
    st = _stats()
    tr = pc.simulate_session(r, orders, ZERO, st)
    assert len(tr) == 2 and st["blocked_daily"] == 1


def test_model_a_signal_ignores_future_bars():
    path = np.full(390, 100.0)
    path[:15] = np.linspace(99.0, 101.0, 15)
    path[15:25] = np.linspace(101.0, 104.0, 10)
    s1 = _sessions(path)[-1]
    o1 = pc.model_a(s1, 15, False)
    path2 = path.copy()
    path2[40:] = 50.0  # el futuro cambia por completo
    s2 = _sessions(path2)[-1]
    o2 = pc.model_a(s2, 15, False)
    assert o1 and o2 and o1[0].k5 == o2[0].k5 and o1[0].side == 1
    assert abs(o1[0].stop - o2[0].stop) < 1e-9


def test_variant_count_matches_preregistration():
    assert len(pc.VARIANTS) == 22
    assert sum(n.startswith("E_") for n in pc.VARIANTS) == 4
