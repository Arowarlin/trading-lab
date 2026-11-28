"""Research B (NY open), familia FUT-RB-1: detectores, conteo sin desenlaces y evaluador único — FUT-D2/D3.

Reglas fijas de docs/futures/research/RB_spec.md §4-§8. Entrada: velas M1 de UNA raíz con índice en hora de
Nueva York (minuto de inicio) y columnas open/high/low/close. El OOS-2 (≥ 2024-01-01, OP-8) se descarta
antes de cualquier cálculo.

* ``detect`` devuelve eventos SIN desenlace (lo único permitido antes de registrar: conteos y stops).
* ``evaluate`` calcula R neta y los criterios; solo se ejecuta sobre datos reales después de que el
  operador registre la familia (AGENTS.md). Los tests usan velas sintéticas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import numpy as np
import pandas as pd

OOS2_START = pd.Timestamp("2024-01-01", tz="America/New_York")


@dataclass(frozen=True)
class Spec:
    tick: float
    point_value: float
    tick_value: float
    commission_side: float


@dataclass(frozen=True)
class Event:
    hypothesis: str
    session: date
    side: int                  # +1 largo, −1 corto
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float | None
    exit_time: pd.Timestamp    # inicio de la vela en cuyo cierre se sale por tiempo


def seal(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.loc[bars.index < OOS2_START]


def _at(day: pd.DataFrame, hhmm: str) -> pd.Series | None:
    t = time.fromisoformat(hhmm)
    rows = day.loc[day.index.time == t]
    return None if rows.empty else rows.iloc[0]


def _window(day: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    s, e = time.fromisoformat(start), time.fromisoformat(end)
    return day.loc[(day.index.time >= s) & (day.index.time <= e)]


def _ts(d: date, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{d.isoformat()} {hhmm}", tz="America/New_York")


def _rth_range(day: pd.DataFrame) -> float | None:
    w = _window(day, "09:30", "15:59")
    return None if w.empty else float(w["high"].max() - w["low"].min())


def detect(bars: pd.DataFrame, hypothesis: str, spec: Spec, *, gc: bool = False) -> list[Event]:
    """Eventos de RB-02, RB-04, RB-07 o RB-08 (regla fija; una operación por sesión)."""
    bars = seal(bars).sort_index()
    days = {d: g for d, g in bars.groupby(bars.index.date)}
    order = sorted(days)
    out: list[Event] = []
    ranges: list[float] = []
    for i, d in enumerate(order):
        day = days[d]
        prev = days[order[i - 1]] if i > 0 else None
        m_r20 = float(np.median(ranges[-20:])) if len(ranges) >= 20 else None
        ev = None
        if hypothesis == "RB-02":
            o_s, c_s, e_s, x_s = ("08:20", "08:24", "08:25", "09:19") if gc else ("09:30", "09:34", "09:35", "10:29")
            first, last, nxt = _at(day, o_s), _at(day, c_s), _at(day, e_s)
            if first is not None and last is not None and nxt is not None and last["close"] != first["open"]:
                side = 1 if last["close"] > first["open"] else -1
                w = _window(day, o_s, c_s)
                stop = w["low"].min() - spec.tick if side > 0 else w["high"].max() + spec.tick
                ev = Event(hypothesis, d, side, _ts(d, e_s), float(nxt["open"]), float(stop), None, _ts(d, x_s))
        elif hypothesis == "RB-07" and prev is not None and m_r20:
            a, b, entry = _at(day, "09:59"), _at(prev, "15:59"), _at(day, "15:30")
            if a is not None and b is not None and entry is not None and a["close"] != b["close"]:
                side = 1 if a["close"] > b["close"] else -1
                dist = 0.25 * m_r20
                ev = Event(hypothesis, d, side, _ts(d, "15:30"), float(entry["open"]),
                           float(entry["open"] - side * dist), None, _ts(d, "15:59"))
        elif hypothesis == "RB-08" and prev is not None and m_r20:
            op, pc, entry = _at(day, "09:30"), _at(prev, "15:59"), _at(day, "09:31")
            if op is not None and pc is not None and entry is not None:
                g = float(op["open"] - pc["close"])
                if abs(g) >= 0.25 * m_r20 and g != 0:
                    side = -1 if g > 0 else 1
                    e = float(entry["open"])
                    ev = Event(hypothesis, d, side, _ts(d, "09:31"), e, e - side * abs(g), float(pc["close"]),
                               _ts(d, "11:29"))
        elif hypothesis == "RB-04" and prev is not None:
            ev = _rb04(day, prev, d, spec, gc)
        if ev is not None:
            out.append(ev)
        r = _rth_range(day)
        if r is not None:
            ranges.append(r)
    return out


def _rb04(day: pd.DataFrame, prev: pd.DataFrame, d: date, spec: Spec, gc: bool) -> Event | None:
    open_t, last_scan, flat = ("08:20", "11:29", "13:24") if gc else ("09:30", "11:29", "15:54")
    on = pd.concat([_window(prev, "18:00", "23:59"), _window(day, "00:00", (pd.Timestamp(f"2000-01-01 {open_t}")
                                                                         - pd.Timedelta(minutes=1)).strftime("%H:%M"))])
    first = _at(day, open_t)
    if on.empty or first is None:
        return None
    onh, onl = float(on["high"].max()), float(on["low"].min())
    if not (onl < first["open"] < onh):
        return None
    scan = _window(day, open_t, last_scan)
    for k, (ts, bar) in enumerate(scan.iterrows()):
        up, down = bar["high"] >= onh + spec.tick, bar["low"] <= onl - spec.tick
        if up and down:
            return None
        if not (up or down):
            continue
        for j in range(k, min(k + 5, len(scan))):
            sig = scan.iloc[j]
            back = sig["close"] < onh if up else sig["close"] > onl
            if back and j + 1 < len(scan):
                nxt = scan.iloc[j + 1]
                extreme = scan.iloc[k:j + 1]["high"].max() + spec.tick if up else scan.iloc[k:j + 1]["low"].min() - spec.tick
                side = -1 if up else 1
                return Event("RB-04", d, side, scan.index[j + 1], float(nxt["open"]), float(extreme), (onh + onl) / 2,
                             _ts(d, flat))
        return None
    return None


def cost_r(ev: Event, spec: Spec, slip_ticks: int = 1) -> float:
    return 2 * (spec.commission_side + slip_ticks * spec.tick_value) / (abs(ev.entry - ev.stop) * spec.point_value)


def count_events(bars: pd.DataFrame, hypothesis: str, spec: Spec, *, gc: bool = False) -> pd.DataFrame:
    """FUT-D2: conteo por año SIN desenlaces (eventos, excluidos por coste y por stop < 2 ticks)."""
    rows = []
    for ev in detect(bars, hypothesis, spec, gc=gc):
        stop_ticks = abs(ev.entry - ev.stop) / spec.tick
        rows.append({"year": ev.session.year, "event": 1, "stop_lt_2_ticks": int(stop_ticks < 2),
                     "cost_filter": int(stop_ticks >= 2 and cost_r(ev, spec) > 0.25)})
    if not rows:
        return pd.DataFrame(columns=["events", "stop_lt_2_ticks", "cost_filter", "tradable"])
    df = pd.DataFrame(rows).groupby("year").sum().rename(columns={"event": "events"})
    df["tradable"] = df["events"] - df["stop_lt_2_ticks"] - df["cost_filter"]
    return df


def outcome(ev: Event, bars: pd.DataFrame, spec: Spec, slip_ticks: int = 1) -> float | None:
    """R neta del evento con los fills de RB_spec §4 (stop primero; objetivo atravesado; salida por tiempo)."""
    risk_pts = abs(ev.entry - ev.stop)
    if risk_pts / spec.tick < 2 or cost_r(ev, spec) > 0.25:
        return None
    path = bars.loc[(bars.index >= ev.entry_time) & (bars.index <= ev.exit_time)]
    exit_px = float(path["close"].iloc[-1])
    for ts, bar in path.iterrows():
        hit_stop = bar["low"] <= ev.stop if ev.side > 0 else bar["high"] >= ev.stop
        if hit_stop:
            exit_px = min(ev.stop, bar["open"]) if ev.side > 0 else max(ev.stop, bar["open"])
            break
        if ev.target is not None:
            hit_t = bar["high"] >= ev.target + spec.tick if ev.side > 0 else bar["low"] <= ev.target - spec.tick
            if hit_t:
                exit_px = ev.target
                break
    gross = ev.side * (exit_px - ev.entry) * spec.point_value
    cost = 2 * (spec.commission_side + slip_ticks * spec.tick_value)
    return (gross - cost) / (risk_pts * spec.point_value)


def newey_west_t(x: np.ndarray, lags: int = 5) -> float:
    """t de la media con error estándar HAC de Newey-West (núcleo de Bartlett)."""
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / np.sqrt(s / n)) if s > 0 else float("inf")


def evaluate(bars: pd.DataFrame, hypothesis: str, spec: Spec, *, t_crit: float, split: date, mu_star_r: float = 0.08,
             gc: bool = False) -> dict:
    """FUT-D3: evaluación ÚNICA de una prueba registrada (RB_spec §8)."""
    bars = seal(bars)
    evs = detect(bars, hypothesis, spec, gc=gc)
    base = [(ev, outcome(ev, bars, spec, 1)) for ev in evs]
    base = [(ev, r) for ev, r in base if r is not None]
    if len(base) < 3:
        return {"verdict": "Sin datos", "n": len(base)}
    r1 = np.array([r for _, r in base])
    r2 = np.array([outcome(ev, bars, spec, 2) for ev, _ in base])
    first = np.array([r for ev, r in base if ev.session < split])
    second = np.array([r for ev, r in base if ev.session >= split])
    t = newey_west_t(r1)
    res = {"n": int(r1.size), "mean_r": float(r1.mean()), "t_hac": t, "mean_r_2ticks": float(np.mean(r2)),
           "mean_first": float(first.mean()) if first.size else None,
           "mean_second": float(second.mean()) if second.size else None}
    if t < t_crit:
        res["verdict"] = "rechazada"
    elif res["mean_r_2ticks"] <= 0:
        res["verdict"] = "rechazada por costes"
    elif not first.size or not second.size or np.sign(first.mean()) != np.sign(second.mean()):
        res["verdict"] = "inconclusa"
    else:
        res["verdict"] = "candidata" if res["mean_r"] >= mu_star_r else "candidata, no monetizable todavía en prop"
    return res
