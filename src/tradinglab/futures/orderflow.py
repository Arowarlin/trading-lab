"""Rasgos de order flow L1a (docs/futures/research/RA_spec.md §3) — FUT-C1. Sin datos reales en los tests.

Entrada: trades con ``ts_event`` (UTC), ``price``, ``size`` y ``side`` (``B`` = compra agresora,
``A`` = venta agresora, ``N`` = sin lado: se excluye y se cuenta). El esquema real se confirma en FUT-B2.
El OOS-2 de futuros (≥ 2024-01-01, OP-8) se descarta ANTES de cualquier cálculo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"
OOS2_START = pd.Timestamp("2024-01-01", tz="UTC")


def seal(trades: pd.DataFrame, cutoff: pd.Timestamp = OOS2_START) -> tuple[pd.DataFrame, int]:
    """Descarta las filas del holdout sellado. Devuelve (trades, filas descartadas)."""
    ts = pd.to_datetime(trades["ts_event"], utc=True)
    keep = ts < cutoff
    return trades.loc[keep].assign(ts_event=ts[keep]), int((~keep).sum())


def signed(trades: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Añade el agresor ``a`` (+1/−1); excluye ``side = N`` y cuenta cuántas filas quitó."""
    side = trades["side"].astype(str).str.upper()
    known = side.isin(["A", "B"])
    out = trades.loc[known].copy()
    out["a"] = np.where(side[known] == "B", 1, -1)
    return out, int((~known).sum())


def minute_bars(trades: pd.DataFrame, *, rth: tuple[str, str] = ("09:30", "15:59")) -> pd.DataFrame:
    """Velas de 1 minuto en RTH (hora de NY): OHLC, V, Δ y CVD que se reinicia en cada sesión a las 9:30."""
    t, _ = seal(trades)
    t, _ = signed(t)
    local = t["ts_event"].dt.tz_convert(NY)
    t = t.assign(minute=local.dt.floor("min"))
    hhmm = t["minute"].dt.strftime("%H:%M")
    t = t.loc[(hhmm >= rth[0]) & (hhmm <= rth[1])]
    t = t.sort_values("ts_event")
    g = t.groupby("minute")
    bars = pd.DataFrame({
        "open": g["price"].first(), "high": g["price"].max(), "low": g["price"].min(), "close": g["price"].last(),
        "volume": g["size"].sum(), "delta": g.apply(lambda x: float((x["a"] * x["size"]).sum()), include_groups=False),
        "trades": g.size(),
    })
    bars["session"] = bars.index.date
    bars["cvd"] = bars.groupby("session")["delta"].cumsum()
    return bars


def footprint(trades: pd.DataFrame, tick: float) -> pd.DataFrame:
    """Volumen agresor por vela de 1 minuto y nivel (en ticks): columnas ``buy`` (B_t(k)) y ``sell`` (S_t(k))."""
    t, _ = seal(trades)
    t, _ = signed(t)
    t = t.assign(minute=t["ts_event"].dt.tz_convert(NY).dt.floor("min"),
                 level=np.round(t["price"] / tick).astype(int))
    t["buy"] = np.where(t["a"] > 0, t["size"], 0)
    t["sell"] = np.where(t["a"] < 0, t["size"], 0)
    return t.groupby(["minute", "level"])[["buy", "sell"]].sum()


def diagonal_buy_imbalances(fp_minute: pd.DataFrame, *, ratio: float = 3.0, min_level_volume: float = 0.0) -> list[int]:
    """Niveles k con B(k) ≥ ratio·S(k−1) y B(k) ≥ min_level_volume (una vela del footprint)."""
    buy = fp_minute["buy"].to_dict()
    sell = fp_minute["sell"].to_dict()
    levels = sorted(buy)
    return [k for k in levels if buy[k] >= min_level_volume and buy[k] > 0 and buy[k] >= ratio * sell.get(k - 1, 0)]


def stacked(levels: list[int], n: int = 3) -> bool:
    """¿Hay al menos ``n`` niveles consecutivos?"""
    run = best = 0
    prev = None
    for k in sorted(levels):
        run = run + 1 if prev is not None and k == prev + 1 else 1
        best = max(best, run)
        prev = k
    return best >= n


def rolling_refs(bars: pd.DataFrame, *, sessions: int = 20) -> pd.DataFrame:
    """Referencias por minuto del día SOLO con las ``sessions`` sesiones anteriores: medV, sΔ (1,4826·MAD), medRng."""
    b = bars.assign(mod=bars.index.strftime("%H:%M"), rng=bars["high"] - bars["low"])
    out = []
    for _, grp in b.groupby("mod"):
        grp = grp.sort_index()
        prev_v = grp["volume"].shift(1).rolling(sessions, min_periods=sessions)
        prev_r = grp["rng"].shift(1).rolling(sessions, min_periods=sessions)
        prev_d = grp["delta"].shift(1)
        mad = prev_d.rolling(sessions, min_periods=sessions).apply(
            lambda w: float(np.median(np.abs(w - np.median(w)))), raw=True)
        out.append(pd.DataFrame({"medV": prev_v.median(), "medRng": prev_r.median(), "s_delta": 1.4826 * mad},
                                index=grp.index))
    return pd.concat(out).sort_index()
