"""Research A, familia FUT-RA-1: evaluador único con fills L1b y criterios de RA_spec §4 y §7 — FUT-C3.

Consume los eventos de ``research_a.detect`` (sin desenlaces) y los convierte en R neta con cotizaciones L1b
de MNQ (``quotes``: ``ts_event``, ``bid``, ``ask``, ``bid_size``, ``ask_size``) y trades (``ts_event``,
``price``, ``size``). Reglas fijas:

* ``t_señal`` = cierre de la vela del evento (``minute + 60 s``); entrada a mercado en ``t_señal + L`` con
  ``L = 0,5 s``, al ask (largo) o al bid (corto); si el tamaño no cabe en el mejor nivel, 1 tick peor.
* Stop a mercado: se dispara con el primer trade en el stop o más allá y se llena al bid (largo) / ask
  (corto) en ``t_disparo + L``.
* Objetivo 1,5 R: límite en la rejilla de ticks, redondeado HACIA FUERA de la entrada (un límite solo puede ir
  en un precio negociable; hacia fuera es lo conservador); solo se llena si un trade lo atraviesa 1 tick. Salida
  por tiempo a los 15 minutos de la entrada, al bid/ask. Stop y objetivo en el mismo segundo: gana el stop.
* Filtro de coste ex ante (RA_spec §4): si ``|close de la vela de señal − stop| < 4,2`` puntos, no se opera y se
  cuenta en ``cost_filtered`` (la misma entrada proxy que ``research_a.count_events``).
* Latencia de estrés del criterio (c): ``L + 1 s`` (RA_spec §4 y §7: «latencia +1 s», es decir 1,5 s);
  ``L + 5 s`` solo se informa.
* ``R_net = (dir·(salida − entrada)·2 − 2·comisión − 2·slip·tick·punto) / (|entrada − stop|·2)``, con
  comisión 0,75 USD por lado (dato del operador, 2026-11-25; OP-7 pendiente).

El estrés de ``+1 tick por lado`` (criterio b) se aplica como coste sobre el riesgo base, igual que
``research_b.outcome(slip_ticks=1)``. Los tests usan cotizaciones y trades sintéticos: **no se ejecuta con
datos reales** hasta que el operador registre FUT-RA-1 (RA_spec §7).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

from tradinglab.futures.research_a import detect

NY = "America/New_York"
BAR_SECONDS = 60
LATENCY_STRESS_S = 1.0          # se SUMA a la latencia base (criterio c)
LATENCY_INFO_S = 5.0            # se suma a la base; solo informativo
COST_STOP_POINTS = 4.2          # RA_spec §4: coste_R > 0,30 ⇔ stop < 4,2 puntos
MU_STAR_R = 0.08


@dataclass(frozen=True)
class Spec:
    tick: float = 0.25
    point_value: float = 2.0
    commission_side: float = 0.75
    latency_s: float = 0.5
    size: int = 1
    hold_s: int = 900
    target_r: float = 1.5
    slip_ticks: int = 0


BASE = Spec()


def _need(frame: pd.DataFrame, columns: tuple[str, ...], source: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"Sin datos: {source}.{missing[0]}")


def _book(frame: pd.DataFrame, columns: tuple[str, ...], source: str) -> pd.DataFrame:
    """Copia indexada por ``ts_event`` (UTC) y ordenada; el resto de columnas se exige tal cual."""
    _need(frame, ("ts_event", *columns), source)
    out = frame.copy()
    out["ts_event"] = pd.DatetimeIndex(pd.to_datetime(out["ts_event"], utc=True))
    return out.sort_values("ts_event", kind="stable").set_index("ts_event")


def _first_at(index: pd.DatetimeIndex, when: pd.Timestamp) -> int | None:
    """Primera fila con ``ts_event >= when`` (o ``None`` si no hay)."""
    i = int(index.searchsorted(when, side="left"))
    return i if i < index.size else None


def _event_time(minute) -> pd.Timestamp:
    t = pd.Timestamp(minute)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    return t.tz_convert("UTC")


def _entry_fill(q: pd.DataFrame, when: pd.Timestamp, side: int, spec: Spec) -> tuple[float, pd.Timestamp] | None:
    i = _first_at(q.index, when)
    if i is None:
        return None
    row = q.iloc[i]
    price = float(row["ask"] if side > 0 else row["bid"])
    available = float(row["ask_size"] if side > 0 else row["bid_size"])
    if available < spec.size:
        price += side * spec.tick
    return price, q.index[i]


def _exit_fill(q: pd.DataFrame, when: pd.Timestamp, side: int) -> tuple[float, pd.Timestamp] | None:
    i = _first_at(q.index, when)
    if i is None:
        return None
    row = q.iloc[i]
    return float(row["bid"] if side > 0 else row["ask"]), q.index[i]


def _on_grid(price: float, side: int, tick: float) -> float:
    """Precio de un límite de salida en la rejilla de ticks, redondeado hacia fuera de la entrada."""
    steps = price / tick
    steps = np.ceil(steps - 1e-9) if side > 0 else np.floor(steps + 1e-9)
    return float(steps * tick)


def simulate(ev: dict, quotes: pd.DataFrame, trades: pd.DataFrame, spec: Spec = BASE) -> dict | None:
    """Fills L1b y R neta de un evento de ``research_a.detect``. ``None`` = Sin datos."""
    return _simulate(ev, _book(quotes, ("bid", "ask", "bid_size", "ask_size"), "quotes"),
                     _book(trades, ("price",), "trades"), spec)


def _simulate(ev: dict, q: pd.DataFrame, t: pd.DataFrame, spec: Spec) -> dict | None:
    side, stop = int(ev["side"]), float(ev["stop"])
    signal = _event_time(ev["minute"]) + pd.Timedelta(seconds=BAR_SECONDS)
    filled = _entry_fill(q, signal + pd.Timedelta(seconds=spec.latency_s), side, spec)
    if filled is None:
        return None
    entry, entry_time = filled
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    target = _on_grid(entry + side * spec.target_r * risk, side, spec.tick)
    end = entry_time + pd.Timedelta(seconds=spec.hold_s)
    win = t.iloc[t.index.searchsorted(entry_time, side="right"):t.index.searchsorted(end, side="left")]
    prices = win["price"].to_numpy(float)
    if side > 0:
        hit_stop = np.flatnonzero(prices <= stop)
        hit_target = np.flatnonzero(prices >= target + spec.tick)
    else:
        hit_stop = np.flatnonzero(prices >= stop)
        hit_target = np.flatnonzero(prices <= target - spec.tick)
    t_stop = win.index[hit_stop[0]] if hit_stop.size else None
    t_target = win.index[hit_target[0]] if hit_target.size else None
    if t_stop is not None and (t_target is None or t_stop.floor("s") <= t_target.floor("s")):
        out = _exit_fill(q, t_stop + pd.Timedelta(seconds=spec.latency_s), side)
        if out is None:
            return None
        exit_price, exit_time, kind = out[0], out[1], "stop"
    elif t_target is not None:
        exit_price, exit_time, kind = float(target), t_target, "target"
    else:
        out = _exit_fill(q, end, side)
        if out is None:
            return None
        exit_price, exit_time, kind = out[0], out[1], "time"
    cost = 2 * (spec.commission_side + spec.slip_ticks * spec.tick * spec.point_value)
    r = (side * (exit_price - entry) * spec.point_value - cost) / (risk * spec.point_value)
    return {"entry": entry, "stop": stop, "target": target, "exit": exit_price, "exit_kind": kind,
            "entry_time": entry_time, "exit_time": exit_time,
            "hold_s": float((exit_time - entry_time).total_seconds()), "r_net": float(r)}


def cr1_t(x: np.ndarray, sessions: np.ndarray) -> float:
    """t de la media con error estándar agrupado por sesión (CR1): Var = G/(G−1)·Σ_g S_g²/n²."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 2:
        return float("nan")
    u = x - x.mean()
    sums = pd.DataFrame({"u": u, "s": np.asarray(sessions)}).groupby("s", sort=False)["u"].sum().to_numpy()
    g = sums.size
    if g < 2:
        return float("nan")
    var = (g / (g - 1)) * float((sums ** 2).sum()) / n ** 2
    if var <= 0:
        return float("inf") if x.mean() != 0 else 0.0
    return float(x.mean() / np.sqrt(var))


def verdict(*, n: int, mean_r: float, t_cr1: float, t_crit: float, mean_r_1tick: float,
            mean_r_latency: float, mean_first: float | None, mean_second: float | None,
            mu_star_r: float = MU_STAR_R) -> str:
    """Veredicto literal de RA_spec §7, en el orden (a) → (b) → (c) → (d) → (f)."""
    if n < 2 or np.isnan(t_cr1):
        return "Sin datos"
    if t_cr1 < t_crit:
        return "rechazada"
    if mean_r_1tick <= 0:
        return "rechazada por costes"
    if mean_r_latency <= 0:
        return "rechazada por latencia"
    if mean_first is None or mean_second is None or not (np.sign(mean_first) == np.sign(mean_second) != 0):
        return "inconclusa"
    return "candidata" if mean_r >= mu_star_r else "candidata, no monetizable todavía en prop"


def _close_lookup(bars: pd.DataFrame):
    """``close`` de la vela de señal (índice en hora de Nueva York), la entrada proxy del filtro de coste."""
    idx = pd.DatetimeIndex(bars.index)
    closes = pd.Series(bars["close"].to_numpy(float), index=idx.tz_localize(NY) if idx.tz is None else
                       idx.tz_convert(NY))

    def close(minute) -> float:
        ts = pd.Timestamp(minute)
        ts = ts.tz_localize(NY) if ts.tzinfo is None else ts.tz_convert(NY)
        return float(closes.loc[ts])
    return close


def evaluate(bars: pd.DataFrame, refs: pd.DataFrame, footprints: pd.DataFrame | None, hypothesis: str,
             quotes: pd.DataFrame, trades: pd.DataFrame, *, t_crit: float, split: date,
             mu_star_r: float = MU_STAR_R, spec: Spec = BASE) -> dict:
    """Evaluación ÚNICA de una prueba registrada (RA_spec §7) sobre las señales de ``research_a.detect``.

    ``split`` separa las dos mitades del criterio (d). Los eventos con stop < 4,2 puntos no se operan y se
    cuentan en ``cost_filtered``. Un evento sin cotización en cualquiera de los tres escenarios del criterio
    (base, +1 tick por lado, L + 1 s) queda Sin datos y se cuenta en ``dropped``; ``L + 5 s`` es informativo.
    """
    events = detect(bars, refs, footprints, hypothesis)
    q = _book(quotes, ("bid", "ask", "bid_size", "ask_size"), "quotes")
    t = _book(trades, ("price",), "trades")
    cost_spec = replace(spec, slip_ticks=spec.slip_ticks + 1)
    lat_spec = replace(spec, latency_s=spec.latency_s + LATENCY_STRESS_S)
    info_spec = replace(spec, latency_s=spec.latency_s + LATENCY_INFO_S)
    close = _close_lookup(bars)
    tradable, cost_filtered = [], 0
    for ev in events:
        if abs(close(ev["minute"]) - float(ev["stop"])) < COST_STOP_POINTS:
            cost_filtered += 1
            continue
        tradable.append(ev)
    rows, info = [], []
    for ev in tradable:
        late = _simulate(ev, q, t, info_spec)
        if late is not None:
            info.append(late["r_net"])
        base = _simulate(ev, q, t, spec)
        stressed_cost = _simulate(ev, q, t, cost_spec)
        stressed_lat = _simulate(ev, q, t, lat_spec)
        if base is None or stressed_cost is None or stressed_lat is None:
            continue
        rows.append((ev, base, stressed_cost, stressed_lat))
    out = {"hypothesis": hypothesis, "events": len(events), "cost_filtered": cost_filtered, "n": len(rows),
           "dropped": len(tradable) - len(rows),
           "mean_r_latency_5s_info": float(np.mean(info)) if info else "Sin datos"}
    if len(rows) < 2:
        out["verdict"] = "Sin datos"
        return out
    r = np.array([b["r_net"] for _, b, _, _ in rows])
    sessions = np.array([pd.Timestamp(ev["minute"]).date() for ev, *_ in rows])
    t = cr1_t(r, sessions)
    first = np.array([b["r_net"] for ev, b, _, _ in rows if pd.Timestamp(ev["minute"]).date() < split])
    second = np.array([b["r_net"] for ev, b, _, _ in rows if pd.Timestamp(ev["minute"]).date() >= split])
    out.update({"mean_r": float(r.mean()), "t_cr1": t, "t_crit": float(t_crit),
                "mean_r_1tick": float(np.mean([c["r_net"] for _, _, c, _ in rows])),
                "mean_r_latency": float(np.mean([s["r_net"] for _, _, _, s in rows])),
                "mean_first": float(first.mean()) if first.size else None,
                "mean_second": float(second.mean()) if second.size else None,
                "median_hold_s": float(np.median([b["hold_s"] for _, b, _, _ in rows]))})
    out["verdict"] = verdict(n=len(rows), mean_r=out["mean_r"], t_cr1=t, t_crit=t_crit,
                             mean_r_1tick=out["mean_r_1tick"], mean_r_latency=out["mean_r_latency"],
                             mean_first=out["mean_first"], mean_second=out["mean_second"],
                             mu_star_r=mu_star_r)
    if out["median_hold_s"] < 30.0:
        out["hold_note"] = "no operable en firmas con reglas de microscalping"
    return out
