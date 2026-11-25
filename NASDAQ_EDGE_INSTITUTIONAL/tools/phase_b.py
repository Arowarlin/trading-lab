"""Fase B · auditoría de datos y descriptivas intradía solo en DEV.

Uso:
    .venv\\Scripts\\python.exe -I NASDAQ_EDGE_INSTITUTIONAL/tools/phase_b.py

Solo lee cachés. Escribe 02_DATA/phase_b_results.json.

Reglas de no-snooping:
- Auditoría de calidad (conteos, huecos, duplicados): todo el rango.
- Cualquier cálculo con precios/retornos: solo DEV.
  NQ CME: <= 2018-12-31 (no hay más). Dukascopy: <= 2021-12-31.
- OOS-1 (2022-2023) y OOS-2 sellado (2024-01-01 → 2026-11-20) no se leen
  para estadísticas.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROJ = Path(__file__).resolve().parents[1]
NY = "America/New_York"
TICK = 0.25
DEV_END = {"NQ": "2018-12-31", "DUK": "2021-12-31"}
SEAL_START = "2024-01-01"
OR_LENS = (5, 15, 30)
POINTS = (5, 10, 15, 20, 30, 50, 100)
WINDOWS = {
    "premarket_0800_0930": ("08:00", "09:30"),
    "open_0930_0935": ("09:30", "09:35"),
    "first15_0930_0945": ("09:30", "09:45"),
    "first30_0930_1000": ("09:30", "10:00"),
    "w_0945_1000": ("09:45", "10:00"),
    "w_1000_1030": ("10:00", "10:30"),
    "w_1030_1130": ("10:30", "11:30"),
    "midday_1130_1330": ("11:30", "13:30"),
    "afternoon_1330_1600": ("13:30", "16:00"),
}


def wilson(k: int, n: int, z: float = 1.96) -> dict:
    if n == 0:
        return {"k": 0, "n": 0, "p": None, "lo": None, "hi": None}
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"k": int(k), "n": int(n), "p": round(p, 4), "lo": round(c - h, 4), "hi": round(c + h, 4)}


def pct(values, qs=(10, 25, 50, 75, 90)) -> dict:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"n": 0}
    out = {f"p{q}": round(float(np.percentile(arr, q)), 4) for q in qs}
    out["n"] = int(arr.size)
    return out


# --------------------------------------------------------------------- carga


def load(src: str) -> pd.DataFrame:
    if src == "NQ":
        df = pd.read_parquet(ROOT / "data/cache/databento/US100_M1.parquet")
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df["spread"] = np.nan
    else:
        raw = pd.read_parquet(ROOT / "data/cache/dukascopy/US100_M1.parquet")
        df = pd.DataFrame(index=raw.index)
        # Precio = bid. El ask falta en buena parte del histórico (ver calidad),
        # así que mezclar mid y bid introduciría saltos de medio spread.
        for col in ("open", "high", "low", "close"):
            df[col] = raw[col].astype(float)
        df["volume"] = raw["volume"].astype(float)
        df["spread"] = raw["ask_close"].astype(float) - raw["close"].astype(float)
        df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_index()
    df.index = df.index.tz_convert(NY)
    return df


# ------------------------------------------------------------------ calidad


def quality(src: str, df: pd.DataFrame) -> dict:
    idx = df.index
    dup = int(idx.duplicated().sum())
    o, h, low, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    incoh = int(((h < np.maximum(o, c)) | (low > np.minimum(o, c)) | (h < low)).sum())
    nonpos = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    minute = idx.hour * 60 + idx.minute
    rth = (minute >= 570) & (minute < 960) & (idx.day_of_week < 5)
    r = df[rth]
    sess = r.groupby(r.index.date)
    counts = sess.size()
    last = sess.apply(lambda x: x.index[-1].hour * 60 + x.index[-1].minute)
    early = last[last <= 13 * 60 + 15].index
    full = counts[(counts >= 380) & ~counts.index.isin(early)]
    by_year = {}
    for year, grp in counts.groupby(pd.Index([d.year for d in counts.index])):
        ok = grp[(grp >= 380) & ~grp.index.isin(early)]
        miss = float(1 - ok.sum() / (390 * len(ok))) if len(ok) else None
        by_year[int(year)] = {
            "sessions": int(len(grp)),
            "full_ge380": int(len(ok)),
            "partial_lt380": int(((grp < 380) & ~grp.index.isin(early)).sum()),
            "early_close": int(grp.index.isin(early).sum()),
            "missing_min_pct_in_full": None if miss is None else round(100 * miss, 3),
        }
    out = {
        "rows": int(len(df)),
        "first": str(idx[0]),
        "last": str(idx[-1]),
        "duplicates": dup,
        "ohlc_incoherent": incoh,
        "price_le_0": nonpos,
        "rth_sessions": int(len(counts)),
        "rth_full_sessions": int(len(full)),
        "by_year": by_year,
    }
    # Huecos > 5 min dentro de Globex (excluye pausa 17-18 ET y fin de semana)
    gaps = pd.Series(idx[1:] - idx[:-1], index=idx[1:])
    long = gaps[gaps > pd.Timedelta(minutes=5)]
    li = long.index
    prev = li - long.values
    in_break = (prev.hour == 16) | (prev.hour == 17) | (li.hour == 18)
    weekend = (prev.day_of_week == 4) & (li.day_of_week == 6)
    real = long[~(in_break | weekend)]
    out["gaps_gt5min_inside_session_by_year"] = (
        real.groupby(real.index.year).size().astype(int).to_dict()
    )
    # Alineación horaria: pico de volumen en 9:30 con y sin horario de verano
    vol = r["volume"]
    mins = r.index.hour * 60 + r.index.minute
    is_dst = pd.Series([bool(t.dst()) for t in r.index], index=r.index)
    align = {}
    for flag in (True, False):
        m = is_dst.to_numpy() == flag
        pre = vol[m & (mins >= 570) & (mins < 575)].median()
        late = vol[m & (mins >= 600) & (mins < 605)].median()
        align["dst" if flag else "std"] = {
            "median_vol_0930_0934": float(pre),
            "median_vol_1000_1004": float(late),
        }
    out["open_alignment"] = align
    # Volumen nulo en RTH
    out["rth_zero_volume_bars"] = int((vol <= 0).sum())
    if src == "DUK":
        has_ask = df["spread"].notna()
        out["ask_coverage_pct_by_year"] = (
            (100 * has_ask.groupby(df.index.year).mean()).round(1).to_dict()
        )
        sp = r["spread"]
        out["rth_spread_median_by_year"] = (
            sp.groupby(sp.index.year).median().round(3).to_dict()
        )
    return out


def detect_rolls(df: pd.DataFrame) -> list[str]:
    """Rolls NQ.c.0: salto en la primera vela Globex (18:00 ET) de mar/jun/sep/dic.

    Criterio: |apertura 18:00 − cierre previo| > 12 × mediana |Δ1m| de los 5 días previos.
    Solo se usa para excluir sesiones, nunca para elegir estrategia.
    """
    idx = df.index
    first = (idx.hour == 18) & (idx.minute == 0) & np.isin(idx.month, (3, 6, 9, 12))
    pos = np.flatnonzero(first)
    close = df["close"].to_numpy()
    opn = df["open"].to_numpy()
    d1 = np.abs(np.diff(close, prepend=close[0]))
    out = []
    for p in pos:
        if p < 7200:
            continue
        base = np.median(d1[p - 7200 : p])
        jump = abs(opn[p] - close[p - 1])
        if base > 0 and jump > 12 * base and jump >= 8:
            out.append(str(idx[p].date()))
    return out


def roll_window_days(y0: int, y1: int) -> set:
    """Ventana fija de roll NQ: del 3er viernes − 9 días al 3er viernes + 1 (mar/jun/sep/dic).

    Cubre la fecha de roll CME (jueves 8 días antes del vencimiento) y el
    vencimiento. Se excluye entera porque NQ.c.0 cambia de contrato en algún
    punto de esa ventana y la caché no trae instrument_id.
    """
    out = set()
    for y in range(y0, y1 + 1):
        for m in (3, 6, 9, 12):
            first = pd.Timestamp(year=y, month=m, day=1)
            fri = first + pd.Timedelta(days=(4 - first.day_of_week) % 7) + pd.Timedelta(weeks=2)
            for k in range(-9, 2):
                out.add(str((fri + pd.Timedelta(days=k)).date()))
    return out


# --------------------------------------------------------------- sesiones


def build(df: pd.DataFrame, end: str, exclude: set) -> pd.DataFrame:
    """Tabla por sesión con todo lo que necesitan las descriptivas."""
    d = df.loc[: pd.Timestamp(end, tz=NY) + pd.Timedelta(hours=23, minutes=59)]
    rows = []
    days = sorted(set(d.index.date))
    by_day = {k: g for k, g in d.groupby(d.index.date)}
    prev_rth = None
    for day in days:
        g = by_day[day]
        mins = (g.index.hour * 60 + g.index.minute).to_numpy()
        rth = g[(mins >= 570) & (mins < 960)]
        rmins = (rth.index.hour * 60 + rth.index.minute).to_numpy()
        # overnight: desde 18:00 del día hábil previo hasta 09:29
        if prev_rth is not None:
            prev_day = prev_rth["day"]
            od = d.loc[pd.Timestamp(prev_day, tz=NY) + pd.Timedelta(hours=18) : pd.Timestamp(day, tz=NY) + pd.Timedelta(hours=9, minutes=29)]
        else:
            od = None
        if len(rth) < 380 or rmins[-1] < 955 or pd.Timestamp(day).day_of_week >= 5:
            if len(rth) >= 380:
                pass
            prev_rth = None if len(rth) < 200 else prev_rth
            continue
        rec = {
            "day": day,
            "excluded": str(day) in exclude,
            "t": rmins,
            "o": rth["open"].to_numpy(),
            "h": rth["high"].to_numpy(),
            "l": rth["low"].to_numpy(),
            "c": rth["close"].to_numpy(),
            "v": rth["volume"].to_numpy(),
            "pm": g[(mins >= 480) & (mins < 570)],
            "onh": float(od["high"].max()) if od is not None and len(od) > 60 else np.nan,
            "onl": float(od["low"].min()) if od is not None and len(od) > 60 else np.nan,
            "pdh": prev_rth["H"] if prev_rth else np.nan,
            "pdl": prev_rth["L"] if prev_rth else np.nan,
            "pdc": prev_rth["C"] if prev_rth else np.nan,
            "pre_excluded": prev_rth["excluded"] if prev_rth else True,
        }
        rec["H"], rec["L"], rec["C"] = rec["h"].max(), rec["l"].min(), rec["c"][-1]
        rows.append(rec)
        prev_rth = rec
    # ATR(14) diario RTH con dato de la víspera (sin futuro)
    tr = []
    for i, r in enumerate(rows):
        pc = rows[i - 1]["C"] if i else r["c"][0]
        tr.append(max(r["H"] - r["L"], abs(r["H"] - pc), abs(r["L"] - pc)))
    tr = pd.Series(tr)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    for i, r in enumerate(rows):
        r["atr_prev"] = float(atr.iloc[i]) if i >= 15 else np.nan
    return rows


def first_idx(t, hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return int(np.searchsorted(t, h * 60 + m))


def stats(src: str, rows: list, news: pd.DataFrame) -> dict:
    rows = [r for r in rows if not r["excluded"] and np.isfinite(r["atr_prev"])]
    res: dict = {"sessions": len(rows), "first": str(rows[0]["day"]), "last": str(rows[-1]["day"])}
    q = np.nanpercentile([r["atr_prev"] for r in rows], [25, 50, 75])
    res["atr_prev_quartiles_dev"] = [round(float(x), 2) for x in q]

    def regime(r):
        return int(np.searchsorted(q, r["atr_prev"]))  # 0..3

    t1 = set(news[(news.tier == 1) & (news.time_et == "08:30")].date)
    fomc = set(news[news.event == "FOMC"].date)
    t2 = set(news[news.tier == 2].date)

    def daytype(r):
        s = str(r["day"])
        if s in t1:
            return "tier1_0830"
        if s in fomc:
            return "fomc"
        if s in t2:
            return "tier2"
        return "no_news"

    # 1 · ventanas
    win = {}
    for name, (a, b) in WINDOWS.items():
        rng, rel, share = [], [], []
        for r in rows:
            if name.startswith("premarket"):
                pm = r["pm"]
                if len(pm) < 60:
                    continue
                x = float(pm["high"].max() - pm["low"].min())
            else:
                i, j = first_idx(r["t"], a), first_idx(r["t"], b)
                if j <= i:
                    continue
                x = float(r["h"][i:j].max() - r["l"][i:j].min())
            rng.append(x)
            rel.append(x / r["atr_prev"])
            share.append(x / (r["H"] - r["L"]) if r["H"] > r["L"] else np.nan)
        win[name] = {"range_pts": pct(rng), "range_atr": pct(rel), "share_of_rth_range": pct(share, (50,))}
    res["windows"] = win

    # 2 · rango de apertura
    orr = {}
    for n in OR_LENS:
        pts = [float(r["h"][:n].max() - r["l"][:n].min()) for r in rows]
        orr[f"OR{n}"] = {
            "pts": pct(pts),
            "atr": pct([p / r["atr_prev"] for p, r in zip(pts, rows)]),
            "median_pts_by_year": pd.Series(pts, index=[r["day"].year for r in rows]).groupby(level=0).median().round(2).to_dict(),
            "median_pts_by_weekday": pd.Series(pts, index=[pd.Timestamp(r["day"]).day_name()[:3] for r in rows]).groupby(level=0).median().round(2).to_dict(),
        }
    res["opening_range"] = orr

    # 3 · rupturas (primer cierre M1 fuera del OR antes de las 11:30)
    brk = {}
    for n in OR_LENS:

        groups: dict = {}
        for r in rows:
            hi, lo = r["h"][:n].max(), r["l"][:n].min()
            w = hi - lo
            if w <= 0:
                continue
            end = first_idx(r["t"], "11:30")
            c = r["c"]
            out_i = None
            for k in range(n, end):
                if c[k] > hi or c[k] < lo:
                    out_i = k
                    break
            key_parts = [
                ("all", "all"),
                ("year", r["day"].year),
                ("weekday", pd.Timestamp(r["day"]).day_name()[:3]),
                ("atr_quartile", regime(r)),
                ("daytype", daytype(r)),
            ]
            if out_i is None:
                outcome = "no_break"
            else:
                up = c[out_i] > hi
                lvl = hi if up else lo
                tgt_c = lvl + w if up else lvl - w
                tgt_f = lvl + 0.5 * w if up else lvl - 0.5 * w
                outcome = "neither"
                reached_half = False
                for k in range(out_i + 1, len(c)):
                    hit_full = r["h"][k] >= tgt_c if up else r["l"][k] <= tgt_c
                    reached_half = reached_half or (r["h"][k] >= tgt_f if up else r["l"][k] <= tgt_f)
                    back = (c[k] <= hi and c[k] >= lo)
                    if hit_full:
                        outcome = "continuation"
                        break
                    if back and not reached_half:
                        outcome = "false"
                        break
                    if back:
                        outcome = "back_after_half"
                        break
            for kp in key_parts:
                groups.setdefault(kp, {"no_break": 0, "continuation": 0, "false": 0, "neither": 0, "back_after_half": 0})
                groups[kp][outcome] += 1
        tab = {}
        for (dim, val), g in groups.items():
            nb = sum(g.values()) - g["no_break"]
            tab.setdefault(dim, {})[str(val)] = {
                "sessions": sum(g.values()),
                "breaks": nb,
                "continuation": wilson(g["continuation"], nb),
                "false": wilson(g["false"], nb),
                "back_after_half": wilson(g["back_after_half"], nb),
                "neither_by_close": wilson(g["neither"], nb),
            }
        brk[f"OR{n}"] = tab
    res["breakouts"] = brk

    # 4 · VWAP: distancia a las 10:00 y toque entre 10:00 y 12:00
    bands = {"<0.5sd": 0, "0.5-1sd": 0, "1-2sd": 0, ">=2sd": 0}
    hits = {k: [0, 0] for k in bands}
    for r in rows:
        i10, i12 = first_idx(r["t"], "10:00"), first_idx(r["t"], "12:00")
        tp = (r["h"] + r["l"] + r["c"]) / 3
        v = np.maximum(r["v"], 1e-9)
        cv = np.cumsum(v)
        vwap = np.cumsum(tp * v) / cv
        var = np.cumsum(v * tp * tp) / cv - vwap**2
        sd = math.sqrt(max(var[i10 - 1], 0))
        if sd <= 0:
            continue
        z = (r["c"][i10 - 1] - vwap[i10 - 1]) / sd
        a = abs(z)
        key = "<0.5sd" if a < 0.5 else "0.5-1sd" if a < 1 else "1-2sd" if a < 2 else ">=2sd"
        touched = bool(np.any((r["l"][i10:i12] <= vwap[i10:i12]) & (r["h"][i10:i12] >= vwap[i10:i12])))
        hits[key][0] += int(touched)
        hits[key][1] += 1
    res["vwap_touch_1000_1200_by_distance_at_1000"] = {k: wilson(*v) for k, v in hits.items()}

    # 5 · alcanzar X puntos desde la apertura 9:30
    reach = {}
    for horizon in ("10:30", "16:00"):
        tab = {}
        for x in POINTS:
            up = dn = both = any_ = 0
            for r in rows:
                j = first_idx(r["t"], horizon) if horizon != "16:00" else len(r["t"])
                o = r["o"][0]
                u = r["h"][:j].max() - o >= x
                d = o - r["l"][:j].min() >= x
                up += u
                dn += d
                both += u and d
                any_ += u or d
            n = len(rows)
            tab[str(x)] = {"up": wilson(up, n), "down": wilson(dn, n), "either": wilson(any_, n), "both": wilson(both, n)}
        reach[horizon] = tab
    # y en múltiplos de ATR
    atr_tab = {}
    for m in (0.1, 0.25, 0.5, 0.75, 1.0):
        any_ = sum(
            (max(r["h"].max() - r["o"][0], r["o"][0] - r["l"].min()) >= m * r["atr_prev"]) for r in rows
        )
        atr_tab[str(m)] = wilson(int(any_), len(rows))
    reach["either_by_close_in_atr_multiples"] = atr_tab
    res["reach_from_open"] = reach

    # 6 · barridos 9:30-11:30 de PDH/PDL y ONH/ONL, reclaim en <=3 velas M5
    sweeps = {}
    for lvl_name in ("pdh", "pdl", "onh", "onl"):
        n_valid = exceed = reclaim = to_vwap = 0
        for r in rows:
            if lvl_name.startswith("pd") and r["pre_excluded"]:
                continue
            L = r[lvl_name]
            if not np.isfinite(L):
                continue
            n_valid += 1
            end = first_idx(r["t"], "11:30")
            hi_side = lvl_name.endswith("h")
            o0 = r["o"][0]
            if (hi_side and o0 > L) or (not hi_side and o0 < L):
                continue  # abre fuera del nivel: no es barrido
            ex = None
            for k in range(0, end):
                if (hi_side and r["h"][k] >= L + 2 * TICK) or (not hi_side and r["l"][k] <= L - 2 * TICK):
                    ex = k
                    break
            if ex is None:
                continue
            exceed += 1
            # cierre M5 de vuelta dentro en las 3 velas M5 siguientes (15 min)
            rc = None
            for k in range(ex, min(ex + 15, len(r["c"]))):
                if (r["t"][k] + 1) % 5 == 0:
                    if (hi_side and r["c"][k] < L) or (not hi_side and r["c"][k] > L):
                        rc = k
                        break
            if rc is None:
                continue
            reclaim += 1
            tp = (r["h"] + r["l"] + r["c"]) / 3
            v = np.maximum(r["v"], 1e-9)
            vw = np.cumsum(tp * v) / np.cumsum(v)
            target = vw[rc]
            ext = r["h"][ex : rc + 1].max() if hi_side else r["l"][ex : rc + 1].min()
            outcome = None
            for k in range(rc + 1, len(r["c"])):
                hit_t = (r["l"][k] <= target) if hi_side else (r["h"][k] >= target)
                hit_s = (r["h"][k] > ext) if hi_side else (r["l"][k] < ext)
                if hit_s:
                    outcome = False
                    break
                if hit_t:
                    outcome = True
                    break
            to_vwap += bool(outcome)
        sweeps[lvl_name] = {
            "sessions_with_level": n_valid,
            "exceed_ge_2ticks": wilson(exceed, n_valid),
            "reclaim_m5_close_within_15min": wilson(reclaim, exceed),
            "vwap_before_new_extreme_after_reclaim": wilson(to_vwap, reclaim),
        }
    res["sweeps_0930_1130"] = sweeps
    return res


def news_study(src: str, df: pd.DataFrame, news: pd.DataFrame, end: str) -> dict:
    """Estudio de eventos de las 08:30 y FOMC (rango por bloques de 5 min)."""
    d = df.loc[: pd.Timestamp(end, tz=NY) + pd.Timedelta(hours=23, minutes=59)]
    d = d[d.index.day_of_week < 5]
    mins = d.index.hour * 60 + d.index.minute
    out = {}
    specs = {
        "tier1_0830": (set(news[(news.tier == 1) & (news.time_et == "08:30")].date), 510),
        "tier2_0830": (set(news[(news.tier == 2) & (news.time_et == "08:30")].date), 510),
        "tier2_1000": (set(news[(news.tier == 2) & (news.time_et == "10:00")].date), 600),
        "fomc_1400": (set(news[news.event == "FOMC"].date), 840),
    }
    any_news = set(news.date)
    rng_by_day: dict = {}
    for t0 in sorted({s[1] for s in specs.values()}):
        blocks = {}
        for b in range(-3, 12):  # bloques de 5 min desde t0-15 hasta t0+60
            a = t0 + 5 * b
            m = (mins >= a) & (mins < a + 5)
            sub = d[m]
            g = sub.groupby(pd.Index(sub.index.date))
            blocks[b] = (g["high"].max() - g["low"].min())
        rng_by_day[t0] = pd.DataFrame(blocks)
    for name, (dates, t0) in specs.items():
        frame = rng_by_day[t0]
        idx = pd.Index([str(x) for x in frame.index])
        ev = frame[idx.isin(list(dates))]
        base = frame[~idx.isin(list(any_news))]
        if len(ev) == 0:
            continue
        med_ev = ev.median()
        med_base = base.median()
        ratio = (med_ev / med_base).round(2)
        # normalización: primer bloque >= 0 cuyo rango mediano < 1,5x base
        norm = next((5 * b for b in range(0, 12) if ratio[b] < 1.5), None)
        out[name] = {
            "event_days": int(len(ev)),
            "baseline_days": int(len(base)),
            "median_range_ratio_by_5min_block": {f"{5*b:+d}min": float(ratio[b]) for b in ratio.index},
            "median_range_pts_event": {f"{5*b:+d}min": round(float(med_ev[b]), 2) for b in med_ev.index},
            "minutes_until_ratio_below_1_5": norm,
        }
        # dirección inicial vs posterior (t0→t0+5 vs t0→t0+60)
        agree = n = 0
        pick = d[(mins == t0) | (mins == t0 + 4) | (mins == t0 + 59)]
        pmins = pick.index.hour * 60 + pick.index.minute
        p_open = pd.Series(pick["open"].to_numpy()[pmins == t0], index=pd.Index(pick.index.date)[pmins == t0])
        p_c5 = pd.Series(pick["close"].to_numpy()[pmins == t0 + 4], index=pd.Index(pick.index.date)[pmins == t0 + 4])
        p_c60 = pd.Series(pick["close"].to_numpy()[pmins == t0 + 59], index=pd.Index(pick.index.date)[pmins == t0 + 59])
        for day in ev.index:
            if day not in p_open.index or day not in p_c5.index or day not in p_c60.index:
                continue
            p0, p5, p60 = p_open[day], p_c5[day], p_c60[day]
            if p5 == p0 or p60 == p0:
                continue
            n += 1
            agree += np.sign(p5 - p0) == np.sign(p60 - p0)
        out[name]["initial5_vs_60min_same_direction"] = wilson(int(agree), n)
    return out


def main() -> None:
    news = pd.read_csv(PROJ / "02_DATA/news_calendar_history.csv", dtype=str)
    news["tier"] = news["tier"].astype(int)
    news["time_et"] = news["time_et"].fillna("")
    result = {"generated": pd.Timestamp.now(tz=NY).isoformat(), "dev_end": DEV_END, "seal_start": SEAL_START}
    for src in ("NQ", "DUK"):
        df = load(src)
        q = quality(src, df)
        rolls = detect_rolls(df) if src == "NQ" else []
        q["roll_sessions_detected"] = rolls
        # sesiones excluidas: día del roll (sesión que empieza a las 18:00 → día siguiente) y el siguiente
        excl = roll_window_days(2010, 2026) if src == "NQ" else set()
        for r in rolls:
            d0 = pd.Timestamp(r)
            for k in range(0, 4):
                excl.add(str((d0 + pd.Timedelta(days=k)).date()))
        rows = build(df, DEV_END[src], excl)
        s = stats(src, rows, news)
        s["news_event_study"] = news_study(src, df, news, DEV_END[src])
        result[src] = {"quality": q, "dev": s}
        print(src, "ok", q["rows"], s["sessions"])
    out = PROJ / "02_DATA/phase_b_results.json"
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
