"""Fase C · motor de backtest de las 22 variantes preregistradas (A–E).

Uso (solo tras el registro del operador en informal_trials):
    .venv\\Scripts\\python.exe -I NASDAQ_EDGE_INSTITUTIONAL/tools/phase_c.py --run

Sin `--run` solo comprueba el registro y sale. Nunca lee OOS-2 (>= 2024-01-01).

Convenciones (fijadas antes de ejecutar; ver 03_BACKTEST/Backtest_Methodology.md):
- Señales al cierre de vela M5; ejecución y salidas sobre M1.
- Orden de mercado: apertura de la vela M1 siguiente ± slippage.
- Orden límite: se llena si el precio la atraviesa 1 tick; sin slippage.
- Stop y TP en la misma vela M1 → primero el stop.
- Gestión común: 50 % en TP1 = 1R, stop a break-even, 50 % en TP2 (2R o el
  objetivo del modelo). Si el objetivo del modelo < 1R, no hay operación.
- Ventana de entrada 9:35–11:30 ET; cierre forzoso 15:55 ET.
- Máximo 3 operaciones al día; parar tras 2 pérdidas o −2R en el día.
- Riesgo fijo $150 en MNQ ($2/pt): contratos = floor(150 / (riesgo_pt × 2 + comisión)).
  Con 0 contratos → NO TRADE (se cuenta).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parent
_spec = importlib.util.spec_from_file_location("phase_b", HERE / "phase_b.py")
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)

TICK = 0.25
MNQ_PT = 2.0
RISK_USD = 150.0
ENTRY_START, ENTRY_END, FLAT = 9 * 60 + 35, 11 * 60 + 30, 15 * 60 + 55
PERIODS = {
    "NQ": {"DEV": ("2010-06-01", "2018-12-31")},
    "DUK": {"DEV": ("2012-01-01", "2021-12-31"), "OOS1": ("2022-01-01", "2023-12-31")},
}
SEAL = "2024-01-01"


@dataclass(frozen=True)
class Costs:
    slip_ticks: float = 1.0  # por lado, órdenes de mercado y stops
    comm_usd: float = 1.50  # ida y vuelta por MNQ [HIPÓTESIS: comisión real Sin datos]


@dataclass
class Order:
    k5: int  # índice de la vela M5 de señal (entrada tras su cierre)
    side: int  # +1 largo, −1 corto
    stop: float
    kind: str = "market"  # market | limit
    limit: float = math.nan
    expiry_min: int = ENTRY_END  # minuto ET hasta el que vale la límite
    target: float = math.nan  # TP2 del modelo; NaN → 2R
    tag: str = ""


@dataclass
class Trade:
    day: str
    tag: str
    side: int
    entry_min: int
    entry: float
    stop: float
    risk_pts: float
    contracts: int
    exit_min: int
    r_gross: float
    r_net: float
    usd_net: float
    reason: str
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------- utilidades


def m5(r: dict) -> dict:
    """Agrega las M1 de RTH a M5 etiquetadas por apertura (9:30, 9:35…)."""
    t = r["t"]
    slot = (t - 570) // 5
    out = {"slot": [], "o": [], "h": [], "l": [], "c": [], "v": [], "end_min": [], "last_i": []}
    for s in np.unique(slot):
        idx = np.flatnonzero(slot == s)
        out["slot"].append(int(s))
        out["o"].append(r["o"][idx[0]])
        out["h"].append(r["h"][idx].max())
        out["l"].append(r["l"][idx].min())
        out["c"].append(r["c"][idx[-1]])
        out["v"].append(r["v"][idx].sum())
        out["end_min"].append(570 + 5 * int(s) + 5)
        out["last_i"].append(int(idx[-1]))
    return {k: np.asarray(v) for k, v in out.items()}


def vwap_sd(r: dict) -> tuple[np.ndarray, np.ndarray]:
    tp = (r["h"] + r["l"] + r["c"]) / 3
    v = np.maximum(r["v"], 1e-9)
    cv = np.cumsum(v)
    vw = np.cumsum(tp * v) / cv
    var = np.maximum(np.cumsum(v * tp * tp) / cv - vw**2, 0)
    return vw, np.sqrt(var)


def atr_series(h, low, c, n=14) -> np.ndarray:
    tr = np.empty(len(h))
    tr[0] = h[0] - low[0]
    tr[1:] = np.maximum(h[1:] - low[1:], np.maximum(abs(h[1:] - c[:-1]), abs(low[1:] - c[:-1])))
    out = np.full(len(h), np.nan)
    if len(h) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(h)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def adx_series(h, low, c, n=14) -> np.ndarray:
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(low, prepend=low[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - low, np.maximum(abs(h - np.roll(c, 1)), abs(low - np.roll(c, 1))))
    tr[0] = h[0] - low[0]
    a = 1.0 / n
    s_tr = pd.Series(tr).ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(pdm).ewm(alpha=a, adjust=False).mean() / s_tr
    ndi = 100 * pd.Series(ndm).ewm(alpha=a, adjust=False).mean() / s_tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean().to_numpy()


def prepare(rows: list[dict]) -> list[dict]:
    """Añade M5, VWAP, ATR M5 continuo, ADX M15 (cerrado) y perfil de la víspera."""
    sess = []
    allh, alll, allc, owner = [], [], [], []
    for i, r in enumerate(rows):
        b = m5(r)
        r["b"] = b
        vw, sd = vwap_sd(r)
        r["vwap"], r["sd"] = vw, sd
        allh += list(b["h"])
        alll += list(b["l"])
        allc += list(b["c"])
        owner += [i] * len(b["h"])
        sess.append(r)
    atr = atr_series(np.array(allh), np.array(alll), np.array(allc))
    owner = np.array(owner)
    for i, r in enumerate(sess):
        r["atr5"] = atr[owner == i]
    # M15 continuo (3 M5) para ADX; valor disponible solo al cierre de cada M15
    h15, l15, c15, own15, end15 = [], [], [], [], []
    for i, r in enumerate(sess):
        b = r["b"]
        for j in range(0, len(b["h"]) - 2, 3):
            h15.append(b["h"][j : j + 3].max())
            l15.append(b["l"][j : j + 3].min())
            c15.append(b["c"][j + 2])
            own15.append(i)
            end15.append(b["end_min"][j + 2])
    adx = adx_series(np.array(h15), np.array(l15), np.array(c15))
    own15, end15, c15 = np.array(own15), np.array(end15), np.array(c15)
    for i, r in enumerate(sess):
        m = own15 == i
        r["adx15"] = (end15[m], adx[m])
        r["c15"] = c15[m]
    # Perfil de volumen de la sesión anterior (desde cierres M1; aproximación)
    for i, r in enumerate(sess):
        r["profile"] = None
        if i and not r["pre_excluded"]:
            p = sess[i - 1]
            r["profile"] = value_area(p["c"], p["v"])
    # RVOL: volumen acumulado hasta cada M5 frente a la mediana de 20 sesiones previas
    cum = [np.cumsum(r["b"]["v"]) for r in sess]
    for i, r in enumerate(sess):
        prev = [c for c in cum[max(0, i - 20) : i] if len(c) == len(cum[i])]
        r["rvol"] = cum[i] / np.median(np.vstack(prev), axis=0) if len(prev) >= 10 else None
    return sess


def value_area(close, vol, step=1.0, share=0.70):
    bins = np.floor(close / step) * step
    s = pd.Series(vol).groupby(bins).sum().sort_index()
    if s.sum() <= 0:
        return None
    poc_i = int(np.argmax(s.to_numpy()))
    lo = hi = poc_i
    tot = s.iloc[poc_i]
    vals = s.to_numpy()
    while tot < share * vals.sum():
        up = vals[hi + 1] if hi + 1 < len(vals) else -1
        dn = vals[lo - 1] if lo - 1 >= 0 else -1
        if up < 0 and dn < 0:
            break
        if up >= dn:
            hi += 1
            tot += up
        else:
            lo -= 1
            tot += dn
    idx = s.index.to_numpy()
    return {"poc": float(idx[poc_i]) + step / 2, "val": float(idx[lo]), "vah": float(idx[hi]) + step}


def adx_at(r: dict, minute: int) -> float:
    ends, vals = r["adx15"]
    m = ends <= minute
    return float(vals[m][-1]) if m.any() else math.nan


# ----------------------------------------------------------------- modelos


def model_a(r: dict, n_or: int, retest: bool) -> list[Order]:
    b = r["b"]
    k_or = n_or // 5
    hi, lo = b["h"][:k_or].max(), b["l"][:k_or].min()
    for k in range(k_or, len(b["c"])):
        if b["end_min"][k] > ENTRY_END:
            break
        side = 1 if b["c"][k] > hi + TICK / 2 else -1 if b["c"][k] < lo - TICK / 2 else 0
        if not side:
            continue
        a = r["atr5"][k]
        lvl = hi if side > 0 else lo
        opp = lo if side > 0 else hi
        if retest:
            entry_ref = lvl
            vol_stop = entry_ref - side * a if math.isfinite(a) else opp
            stop = max(opp, vol_stop) if side > 0 else min(opp, vol_stop)
            return [Order(k, side, stop, "limit", lvl, min(b["end_min"][k] + 30, ENTRY_END), tag="A")]
        entry_ref = b["c"][k]
        vol_stop = entry_ref - side * a if math.isfinite(a) else opp
        stop = max(opp, vol_stop) if side > 0 else min(opp, vol_stop)
        return [Order(k, side, stop, tag="A")]
    return []


def model_b(r: dict, level: str, displacement: bool) -> list[Order]:
    b = r["b"]
    out = []
    names = ("pdh", "pdl") if level == "PD" else ("onh", "onl")
    if level == "PD" and r["pre_excluded"]:
        return []
    for nm in names:
        L = r[nm]
        if not math.isfinite(L):
            continue
        hi_side = nm.endswith("h")
        if (hi_side and b["o"][0] > L) or (not hi_side and b["o"][0] < L):
            continue
        ex = None
        for k in range(len(b["c"])):
            if b["end_min"][k] > ENTRY_END:
                break
            if (hi_side and b["h"][k] >= L + 2 * TICK) or (not hi_side and b["l"][k] <= L - 2 * TICK):
                ex = k
                break
        if ex is None:
            continue
        for k in range(ex, min(ex + 3, len(b["c"]))):
            if b["end_min"][k] > ENTRY_END:
                break
            back = b["c"][k] < L if hi_side else b["c"][k] > L
            if not back:
                continue
            if displacement:
                a = r["atr5"][k]
                if not (math.isfinite(a) and b["h"][k] - b["l"][k] >= 1.5 * a):
                    break
            ext = b["h"][ex : k + 1].max() if hi_side else b["l"][ex : k + 1].min()
            side = -1 if hi_side else 1
            out.append(Order(k, side, ext - side * TICK, tag=f"B-{nm}"))
            break
    return sorted(out, key=lambda o: o.k5)


def model_c(r: dict, mode: str, regime: bool) -> list[Order]:
    b = r["b"]
    out = []
    for k in range(1, len(b["c"])):
        end = b["end_min"][k]
        if end > ENTRY_END:
            break
        if end < ENTRY_START:
            continue
        i = b["last_i"][k]
        vw, sd = r["vwap"][i], r["sd"][i]
        if sd <= 0:
            continue
        adx = adx_at(r, end)
        if mode == "rev":
            if regime and not (math.isfinite(adx) and adx < 20):
                continue
            ip = b["last_i"][k - 1]
            vp, sp = r["vwap"][ip], r["sd"][ip]
            if b["c"][k - 1] > vp + 2 * sp and b["c"][k] < vw + 2 * sd:
                ext = b["h"][max(0, k - 6) : k + 1].max()
                out.append(Order(k, -1, ext + TICK, target=vw, tag="C-rev"))
            elif b["c"][k - 1] < vp - 2 * sp and b["c"][k] > vw - 2 * sd:
                ext = b["l"][max(0, k - 6) : k + 1].min()
                out.append(Order(k, 1, ext - TICK, target=vw, tag="C-rev"))
        else:
            if regime and not (math.isfinite(adx) and adx > 25):
                continue
            if k < 6:
                continue
            slope = vw - r["vwap"][b["last_i"][k - 6]]
            if slope > 0 and b["l"][k] <= vw + 0.5 * sd and b["c"][k] > vw:
                out.append(Order(k, 1, min(b["l"][k], vw - 0.5 * sd) - TICK, tag="C-cont"))
            elif slope < 0 and b["h"][k] >= vw - 0.5 * sd and b["c"][k] < vw:
                out.append(Order(k, -1, max(b["h"][k], vw + 0.5 * sd) + TICK, tag="C-cont"))
    return out


def model_d(r: dict, structure: bool, mid: bool) -> list[Order]:
    b = r["b"]
    out = []
    for k in range(2, len(b["c"])):
        end = b["end_min"][k]
        if end > ENTRY_END:
            break
        a = r["atr5"][k - 1]
        if not math.isfinite(a) or abs(b["c"][k - 1] - b["o"][k - 1]) < 2 * a:
            continue
        bull = b["c"][k - 1] > b["o"][k - 1] and b["l"][k] > b["h"][k - 2]
        bear = b["c"][k - 1] < b["o"][k - 1] and b["h"][k] < b["l"][k - 2]
        if not (bull or bear):
            continue
        side = 1 if bull else -1
        if structure:
            ends = r["adx15"][0]
            c15 = r["c15"][ends <= end]
            if len(c15) < 5 or np.sign(c15[-1] - c15[-5]) != side:
                continue
        top, bot = (b["l"][k], b["h"][k - 2]) if bull else (b["l"][k - 2], b["h"][k])
        price = (top + bot) / 2 if mid else (top if bull else bot)
        stop = bot - TICK if bull else top + TICK
        out.append(Order(k, side, stop, "limit", price, min(end + 60, ENTRY_END), tag="D"))
    return out


def model_e(r: dict, mode: str, rvol: bool) -> list[Order]:
    va = r["profile"]
    if va is None:
        return []
    b = r["b"]
    val, vah, poc = va["val"], va["vah"], va["poc"]
    out = []
    for k in range(1, len(b["c"])):
        end = b["end_min"][k]
        if end > ENTRY_END:
            break
        if end < ENTRY_START:
            continue
        if rvol and (r["rvol"] is None or not r["rvol"][k] >= 1.2):
            continue
        inside = val <= b["c"][k] <= vah
        if mode == "accept":
            if not (inside and val <= b["c"][k - 1] <= vah):
                continue
            if b["o"][0] > vah:
                out.append(Order(k, -1, b["h"][k - 1 : k + 1].max() + TICK, target=val, tag="E-acc"))
            elif b["o"][0] < val:
                out.append(Order(k, 1, b["l"][k - 1 : k + 1].min() - TICK, target=vah, tag="E-acc"))
        else:
            prev_out_hi = b["c"][k - 1] > vah
            prev_out_lo = b["c"][k - 1] < val
            if inside and prev_out_hi:
                out.append(Order(k, -1, b["h"][max(0, k - 6) : k + 1].max() + TICK, target=poc, tag="E-rej"))
            elif inside and prev_out_lo:
                out.append(Order(k, 1, b["l"][max(0, k - 6) : k + 1].min() - TICK, target=poc, tag="E-rej"))
    return out


VARIANTS = {
    **{f"A_OR{n}_{e}": (model_a, (n, e == "retest")) for n in (5, 15, 30) for e in ("close", "retest")},
    **{f"B_{lv}_{c}": (model_b, (lv, c == "disp")) for lv in ("PD", "ON") for c in ("reclaim", "disp")},
    **{f"C_{m}_{f}": (model_c, (m, f == "F")) for m in ("rev", "cont") for f in ("noF", "F")},
    **{f"D_{s}_{p}": (model_d, (s == "struct", p == "mid")) for s in ("iso", "struct") for p in ("mid", "edge")},
    **{f"E_{m}_{v}": (model_e, (m, v == "rvol")) for m in ("accept", "reject") for v in ("norvol", "rvol")},
}
assert len(VARIANTS) == 22


# --------------------------------------------------------------- simulador


def simulate_session(r: dict, orders: list[Order], costs: Costs, stats: dict) -> list[Trade]:
    t, o, h, low, c = r["t"], r["o"], r["h"], r["l"], r["c"]
    slip = costs.slip_ticks * TICK
    trades: list[Trade] = []
    busy_until = -1
    losses = 0
    day_r = 0.0
    for od in sorted(orders, key=lambda x: x.k5):
        if len(trades) >= 3 or losses >= 2 or day_r <= -2.0:
            stats["blocked_daily"] += 1
            break
        sig_end = int(r["b"]["end_min"][od.k5])
        if sig_end < ENTRY_START or sig_end > ENTRY_END or sig_end < busy_until:
            continue
        j = int(np.searchsorted(t, sig_end))
        if j >= len(t):
            continue
        side = od.side
        # entrada
        if od.kind == "market":
            entry_i, entry = j, o[j] + side * slip
        else:
            entry_i = None
            for k in range(j, len(t)):
                if t[k] >= od.expiry_min:
                    break
                if (side > 0 and low[k] <= od.limit - TICK) or (side < 0 and h[k] >= od.limit + TICK):
                    entry_i, entry = k, od.limit
                    break
            if entry_i is None:
                stats["limit_unfilled"] += 1
                continue
        risk = (entry - od.stop) * side
        if risk < 2 * TICK:
            stats["bad_stop"] += 1
            continue
        tp1 = entry + side * risk
        tp2 = od.target if math.isfinite(od.target) else entry + side * 2 * risk
        if (tp2 - entry) * side < risk:
            stats["target_lt_1R"] += 1
            continue
        contracts = int(RISK_USD // (risk * MNQ_PT + costs.comm_usd))
        if contracts < 1:
            stats["no_trade_size"] += 1
            continue
        stop = od.stop
        half_done = False
        pts = 0.0
        exit_i, reason = None, ""
        for k in range(entry_i, len(t)):
            if t[k] >= FLAT:
                px = o[k] - side * slip
                pts += (0.5 if half_done else 1.0) * (px - entry) * side
                exit_i, reason = k, "time"
                break
            hit_stop = (low[k] <= stop) if side > 0 else (h[k] >= stop)
            if hit_stop:
                px = stop - side * slip
                pts += (0.5 if half_done else 1.0) * (px - entry) * side
                exit_i, reason = k, "be" if half_done else "stop"
                break
            if not half_done and ((h[k] >= tp1) if side > 0 else (low[k] <= tp1)):
                pts += 0.5 * risk
                half_done = True
                stop = entry
                continue  # conservador: no se evalúa TP2 en la misma vela
            if half_done and ((h[k] >= tp2) if side > 0 else (low[k] <= tp2)):
                pts += 0.5 * (tp2 - entry) * side
                exit_i, reason = k, "tp2"
                break
        if exit_i is None:
            px = c[-1] - side * slip
            pts += (0.5 if half_done else 1.0) * (px - entry) * side
            exit_i, reason = len(t) - 1, "eod"
        comm_pts = costs.comm_usd / MNQ_PT
        r_gross = pts / risk  # tras slippage, antes de comisión
        r_net = (pts - comm_pts) / risk
        usd = contracts * (pts * MNQ_PT - costs.comm_usd)
        trades.append(
            Trade(str(r["day"]), od.tag, side, int(t[entry_i]), float(entry), float(od.stop), float(risk), contracts, int(t[exit_i]), float(r_gross), float(r_net), float(usd), reason)
        )
        busy_until = int(t[exit_i]) + 1
        day_r += r_net
        losses += r_net < 0
    return trades


def run_variant(sess: list[dict], name: str, costs: Costs) -> tuple[list[Trade], dict]:
    fn, args = VARIANTS[name]
    stats = {k: 0 for k in ("limit_unfilled", "bad_stop", "target_lt_1R", "no_trade_size", "blocked_daily")}
    out = []
    for r in sess:
        if r["excluded"]:
            continue
        out += simulate_session(r, fn(r, *args), costs, stats)
    return out, stats


# ----------------------------------------------------------------- métricas


def metrics(trades: list[Trade], sessions: list[str]) -> dict:
    if not trades:
        return {"n": 0}
    df = pd.DataFrame([t.__dict__ for t in trades])
    r = df["r_net"]
    wins, losses = r[r > 0], r[r <= 0]
    daily = df.groupby("day")["r_net"].sum().reindex(sessions, fill_value=0.0)
    eq = daily.cumsum()
    dd = float((eq - eq.cummax()).min())
    sd = daily.std(ddof=1)
    dsd = daily[daily < 0].std(ddof=1)
    yearly = df.groupby(df["day"].str[:4])["r_net"].agg(["count", "mean", "sum"]).round(4)
    top = daily.sort_values(ascending=False)
    drop = max(1, int(round(0.01 * len(daily))))
    return {
        "n": int(len(df)),
        "win_rate": round(float((r > 0).mean()), 4),
        "pf": round(float(wins.sum() / -losses.sum()), 3) if losses.sum() < 0 else None,
        "exp_r_net": round(float(r.mean()), 4),
        "exp_r_gross": round(float(df["r_gross"].mean()), 4),
        "avg_win_r": round(float(wins.mean()), 3) if len(wins) else None,
        "avg_loss_r": round(float(losses.mean()), 3) if len(losses) else None,
        "sum_r": round(float(r.sum()), 2),
        "usd_net": round(float(df["usd_net"].sum()), 0),
        "max_dd_r": round(dd, 2),
        "sharpe_ann": round(float(daily.mean() / sd * math.sqrt(252)), 3) if sd > 0 else None,
        "sortino_ann": round(float(daily.mean() / dsd * math.sqrt(252)), 3) if dsd and dsd > 0 else None,
        "daily_sr_period": float(daily.mean() / sd) if sd > 0 else 0.0,
        "sum_r_without_top1pct_days": round(float(top.iloc[drop:].sum()), 2),
        "by_year": {k: v for k, v in yearly.to_dict("index").items()},
        "by_hour": df.groupby(df["entry_min"] // 60)["r_net"].agg(["count", "mean"]).round(4).to_dict("index"),
        "by_weekday": df.groupby(pd.to_datetime(df["day"]).dt.day_name().str[:3])["r_net"].agg(["count", "mean"]).round(4).to_dict("index"),
        "exit_reasons": df["reason"].value_counts().to_dict(),
        "contracts_median": float(df["contracts"].median()),
    }


def registered(db: Path) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return list(con.execute("select id, n, reason from informal_trials where reason like '%NASDAQ EDGE Fase C%'"))
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    reg = registered(ROOT / "data/lab.db")
    if not reg:
        raise SystemExit("BLOQUEADO: falta el registro 'NASDAQ EDGE Fase C' en informal_trials (data/lab.db)")
    print("registro:", reg)
    if not args.run:
        return
    news = pd.read_csv(PROJ / "02_DATA/news_calendar_history.csv", dtype=str)
    news_days = {
        "tier1": set(news[news.tier == "1"].date),
        "any": set(news.date),
    }
    scenarios = {"zero_cost": Costs(slip_ticks=0, comm_usd=0), "base": Costs(), "slip2": Costs(slip_ticks=2), "slip4": Costs(slip_ticks=4), "comm2x": Costs(comm_usd=3.0)}
    (PROJ / "03_BACKTEST/trades").mkdir(parents=True, exist_ok=True)
    out: dict = {"generated": pd.Timestamp.now(tz=pb.NY).isoformat(), "scenarios": {k: v.__dict__ for k, v in scenarios.items()}}
    for src, periods in PERIODS.items():
        df = pb.load(src)
        excl = pb.roll_window_days(2010, 2026) if src == "NQ" else set()
        for per, (a, z) in periods.items():
            assert z < SEAL
            d = df.loc[pd.Timestamp(a, tz=pb.NY) - pd.Timedelta(days=40) : pd.Timestamp(z, tz=pb.NY) + pd.Timedelta(hours=23, minutes=59)]
            rows = [r for r in pb.build(d, z, excl) if str(r["day"]) >= a]
            sess = prepare(rows)
            days = [str(r["day"]) for r in sess if not r["excluded"]]
            for name in VARIANTS:
                if name.startswith("E_") and src != "NQ":
                    continue
                res = {}
                for sc, costs in scenarios.items():
                    trades, st = run_variant(sess, name, costs)
                    m = metrics(trades, days)
                    m["skips"] = st
                    if sc == "base" and trades:
                        tdf = pd.DataFrame([t.__dict__ for t in trades])
                        m["news_tier1_days"] = round(float(tdf[tdf.day.isin(news_days["tier1"])].r_net.mean()), 4) if tdf.day.isin(news_days["tier1"]).any() else None
                        m["no_news_days"] = round(float(tdf[~tdf.day.isin(news_days["any"])].r_net.mean()), 4)
                        tdf.to_csv(PROJ / f"03_BACKTEST/trades/{src}_{per}_{name}.csv", index=False)
                    res[sc] = m
                out.setdefault(src, {}).setdefault(per, {})[name] = res
                b = res["base"]
                print(src, per, name, b.get("n"), b.get("exp_r_net"), b.get("pf"))
    (PROJ / "03_BACKTEST/phase_c_results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
