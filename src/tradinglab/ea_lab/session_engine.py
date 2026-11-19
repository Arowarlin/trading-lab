# ruff: noqa
"""Copia de ``ea_us100_engine.run`` con anclajes de sesión parametrizados.

La lógica de entrada, salida, riesgo y puntuación es **idéntica** al motor
original. Solo cambian las horas/zonas que definen el rango de apertura, la
sesión principal (VWAP, régimen, gap), la sesión nocturna previa, el premarket
opcional, la ventana de entradas y el cierre forzado.

Por defecto reproduce los anclajes de Nueva York del motor original. El test
``tests/test_ea_lab_session_equivalence.py`` exige que, con esos anclajes,
produzca exactamente las mismas operaciones que ``ea_us100_engine.run``.

El índice de ``df`` debe ser hora local de Nueva York sin tz (como la caché del
EA) o un ``DatetimeIndex`` con tz. Las ventanas que cruzan medianoche usan
``in_sess``; la sesión nocturna puede empezar y terminar en zonas distintas.
"""
import math
from collections import deque

import numpy as np
import pandas as pd

from ..nyse_calendar import (
    EARLY_CLOSES as EARLY_CLOSE,
    effective_flat_min,
    is_full_holiday,
)

DEF = dict(
    ny_offset_h=7, or_end=945, trade_start=935, trade_end=1130, flat_at=1545,
    atr_len=14, or_avg_days=20, fb_window=6,
    use_pd=True, use_on=True, use_pm=True, use_or=True, sweep_cool=10, sweep_window=12,
    fvg_min_atr=0.15, fvg_ext=40, fvg_max=20, fvg_prox_atr=1.0, htf_min=15,
    vwap_ext_sd=2.0, rvol_len=20, rvol_thr=1.5, rvol_low=0.7,
    piv_l=5, piv_r=5,
    w=(25, 20, 20, 15, 10, 10), mode='cons', min_score=70, req_fvg=False,
    allow_long=True, allow_short=True,
    sl_mode='struct', sl_atr=1.5, sl_buf=0.25 * 4, max_sl_atr=3.0, min_sl=2.0,
    rr=2.0, be=True, be_r=1.0, be_off=0.5, trail=False, trail_atr=2.0,
    max_trades=3, daily_loss_r=2.0, regime=None, reg_len=20, max_consec=99,
    gap_min=0.0, gap_len=20, be_off_r=None, trail_start_r=0.0, cooldown=5,
    max_spread=3.0, slip=0.5,
)

SESSION_DEF = dict(
    tz="America/New_York",
    or_start="09:30",
    or_end="09:45",
    rth_start="09:30",
    rth_end="16:00",
    on_start="18:00",
    on_end="09:30",
    on_start_tz="America/New_York",
    on_end_tz="America/New_York",
    pm_start="08:00",
    trade_start="09:35",
    trade_end="11:30",
    flat_at="15:45",
    calendar="nyse",
    min_before_flat=60,
)

VERSION = "3.2-session"


def in_sess(m, a, b):
    return a <= m < b if a < b else (m >= a or m < b)


def hm(x):
    return (x // 100) * 60 + x % 100


def to_minutes(value) -> int:
    """Acepta ``"08:15"``, ``815`` o ``495`` y devuelve minutos desde medianoche."""
    if value is None:
        raise ValueError("hora vacía")
    if isinstance(value, str):
        text = value.strip()
        if ":" in text:
            hour, minute = text.split(":", 1)
            return int(hour) * 60 + int(minute)
        value = int(text)
    return hm(int(value))


def entry_allowed(minute: int, flat_min: int, min_before: int = 60) -> bool:
    """False si quedan menos de ``min_before`` minutos hasta el cierre efectivo."""
    return int(flat_min) - int(minute) >= int(min_before)


class SessHL:
    def __init__(self):
        self.ch = self.cl = self.ph = self.pl = math.nan
        self.prev_in = False

    def upd(self, ins, h, l):
        if ins and not self.prev_in:
            self.ch, self.cl = h, l
        elif ins:
            self.ch = max(self.ch, h) if not math.isnan(self.ch) else h
            self.cl = min(self.cl, l) if not math.isnan(self.cl) else l
        if not ins and self.prev_in:
            self.ph, self.pl = self.ch, self.cl
        self.prev_in = ins
        return self.ph, self.pl


def resolve_session(p: dict, session: dict | None = None) -> dict:
    """Fusiona los anclajes con ``SESSION_DEF`` y, si no hay, los deriva del setfile."""
    if session is None and "session" in p:
        session = p["session"]
    if session is None:
        session = {
            "or_start": "09:30",
            "or_end": p.get("or_end", DEF["or_end"]),
            "rth_start": "09:30",
            "rth_end": "16:00",
            "on_start": "18:00",
            "on_end": "09:30",
            "pm_start": "08:00",
            "trade_start": p.get("trade_start", DEF["trade_start"]),
            "trade_end": p.get("trade_end", DEF["trade_end"]),
            "flat_at": p.get("flat_at", DEF["flat_at"]),
            "calendar": "nyse",
        }
    out = dict(SESSION_DEF)
    out.update(session)
    tz = str(out["tz"])
    out["on_start_tz"] = str(out.get("on_start_tz") or tz)
    out["on_end_tz"] = str(out.get("on_end_tz") or tz)
    for key in ("or_start", "or_end", "rth_start", "rth_end", "on_start", "on_end",
                "trade_start", "trade_end", "flat_at"):
        out[key + "_min"] = to_minutes(out[key])
    out["pm_start_min"] = None if out.get("pm_start") in (None, "") else to_minutes(out["pm_start"])
    out["min_before_flat"] = int(out.get("min_before_flat", 60))
    if out["flat_at_min"] <= out["trade_end_min"]:
        raise ValueError("flat_at debe ser posterior a trade_end (sin cruce de medianoche)")
    return out


def _local_index(index: pd.DatetimeIndex, tz: str) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (utc, minutos locales, día local, índices)."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is None and tz == "America/New_York":
        # Equivalencia exacta con el motor original: la caché ya está en NY.
        utc = idx.tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
        local = idx
        smin = (local.hour * 60 + local.minute).to_numpy(dtype=np.int32)
        sday = (local.year * 10000 + local.month * 100 + local.day).to_numpy(dtype=np.int64)
        return utc, smin, sday, idx
    if idx.tz is None:
        utc = idx.tz_localize("America/New_York", ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
    else:
        utc = idx.tz_convert("UTC")
    local = utc.tz_convert(tz)
    smin = (local.hour * 60 + local.minute).to_numpy(dtype=np.int32)
    sday = (local.year * 10000 + local.month * 100 + local.day).to_numpy(dtype=np.int64)
    return utc, smin, sday, local


def _weekday(day: int) -> int:
    return pd.Timestamp(year=day // 10000, month=(day // 100) % 100, day=day % 100).weekday()


def _on_mask(
    utc: pd.DatetimeIndex,
    smin: np.ndarray,
    *,
    tz: str,
    on_start_tz: str,
    on_start_min: int,
    on_end_tz: str,
    on_end_min: int,
) -> np.ndarray:
    """Máscara de la sesión nocturna; admite inicio y fin en zonas distintas."""
    if on_start_tz == on_end_tz:
        local = utc.tz_convert(on_start_tz)
        minutes = (local.hour * 60 + local.minute).to_numpy(dtype=int)
        return np.array([in_sess(int(m), on_start_min, on_end_min) for m in minutes], dtype=bool)

    # Ventana que empieza en una zona y termina en otra (p. ej. cierre NY → 09:00 Tokio).
    end_local = utc.tz_convert(on_end_tz)
    end_dates = end_local.normalize().tz_localize(None)
    windows: dict[pd.Timestamp, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for date in pd.DatetimeIndex(end_dates).unique():
        prior = date - pd.Timedelta(days=1)
        start = pd.Timestamp(
            year=prior.year, month=prior.month, day=prior.day,
            hour=on_start_min // 60, minute=on_start_min % 60, tz=on_start_tz,
        )
        end = pd.Timestamp(
            year=date.year, month=date.month, day=date.day,
            hour=on_end_min // 60, minute=on_end_min % 60, tz=on_end_tz,
        )
        windows[date] = (start.tz_convert("UTC"), end.tz_convert("UTC"))
    mask = np.zeros(len(utc), dtype=bool)
    for i, (stamp, date) in enumerate(zip(utc, end_dates)):
        start, end = windows[pd.Timestamp(date)]
        mask[i] = start <= stamp < end
    return mask


def run(df, p=None, start=None, end=None, session=None):
    P = dict(DEF)
    if p:
        P.update(p)
    S = resolve_session(P, session)
    t = df.index
    O = df.open.values; H = df.high.values; L = df.low.values; C = df.close.values
    V = df.tickvol.values.astype(float); SP = df.spread.values * 0.01
    utc, nym, nyday, _local = _local_index(t, S["tz"])
    # HTF (M15) en las barras cerradas
    htf = df[['high', 'low', 'open', 'close']].resample(f"{P['htf_min']}min", label='left', closed='left').agg(
        {'high': 'max', 'low': 'min', 'open': 'first', 'close': 'last'}).dropna()
    hidx = htf.index.searchsorted(t, side='right') - 1
    hH = htf.high.values; hL = htf.low.values; hO = htf.open.values; hC = htf.close.values

    S_OR = S["or_start_min"]; E_OR = S["or_end_min"]
    S_RTH, E_RTH = S["rth_start_min"], S["rth_end_min"]
    S_ON, E_ON = S["on_start_min"], S["on_end_min"]
    S_PM = S["pm_start_min"]
    S_TR, E_TR = S["trade_start_min"], S["trade_end_min"]
    S_FL = S["flat_at_min"]
    flat_hm = (S_FL // 60) * 100 + S_FL % 60
    calendar = P['early_close'] if 'early_close' in P else EARLY_CLOSE
    calendar_mode = S["calendar"]
    flat_min = S_FL
    holiday = False
    tot_w = sum(P['w']) or 1.0
    nSw, nFvg, nVw, nSt, nRv, nOr = [x * 100.0 / tot_w for x in P['w']]

    on_mask = _on_mask(
        utc, nym,
        tz=S["tz"],
        on_start_tz=S["on_start_tz"],
        on_start_min=S_ON,
        on_end_tz=S["on_end_tz"],
        on_end_min=E_ON,
    )

    rth, onh, pmh = SessHL(), SessHL(), SessHL()
    atr = math.nan; trs = []
    vq = deque(maxlen=P['rvol_len'])
    orH = orL = math.nan; orDone = False; brokeUp = brokeDn = False; brkUp = brkDn = -1
    orW = deque(maxlen=P['or_avg_days'])
    prev_inOR = False
    lvl_hist = {k: deque([math.nan] * 3, maxlen=3) for k in ('pdh', 'pdl', 'onh', 'onl', 'pmh', 'pml', 'orh', 'orl')}
    sw_last = {k: -10 ** 9 for k in lvl_hist}
    lastBullSw = lastBearSw = -10 ** 9; lastBullLow = lastBearHigh = math.nan
    fvgs = []
    cPV = cV = cP2V = 0.0; prev_inV = False
    lastPH = lastPL = math.nan; phB = plB = False; trend = 0
    prev_nyday = None; prev_hidx = -1
    dcl = []; reg_up = reg_dn = True
    gaps = []; gap_ok = True

    trades = []
    pos = None
    tradesToday = 0; dayR = 0.0; locked = False; lastEntry = -10 ** 9; consec = 0
    pending = None
    n = len(df)
    for i in range(n):
        m = nym[i]
        if i == 0 or nyday[i] != nyday[i - 1]:
            if calendar_mode == "nyse":
                flat_min = effective_flat_min(int(nyday[i]), flat_hm, calendar)
                holiday = is_full_holiday(int(nyday[i]))
            else:
                flat_min = S_FL
                holiday = _weekday(int(nyday[i])) >= 5
        # ── 1) ejecución al OPEN de la barra i (orden de la barra i-1) ─────
        if pending is not None and pos is None and not holiday and entry_allowed(m, flat_min, S["min_before_flat"]):
            d, sl0 = pending
            sp = SP[i]
            if d == 1:
                ent = O[i] + sp + P['slip']; risk = ent - sl0
                if risk < P['min_sl']:
                    sl0 = ent - max(P['sl_atr'] * atr, P['min_sl']); risk = ent - sl0
                tp = ent + P['rr'] * risk
            else:
                ent = O[i] - P['slip']; risk = sl0 - ent
                if risk < P['min_sl']:
                    sl0 = ent + max(P['sl_atr'] * atr, P['min_sl']); risk = sl0 - ent
                tp = ent - P['rr'] * risk
            pos = dict(d=d, ent=ent, sl=sl0, tp=tp, risk=risk, i0=i, t0=t[i], nym=m)
            tradesToday += 1
        pending = None
        # ── 2) salidas durante la barra i ─────────────────────────────────
        if pos is not None:
            d = pos['d']; sp = SP[i]; ex = None; why = ''
            if m >= flat_min and i > pos['i0']:
                ex = O[i] if d == 1 else O[i] + sp; why = 'EOD'
            elif d == 1:
                if L[i] <= pos['sl']:
                    ex = min(pos['sl'], O[i]) - P['slip']; why = 'SL'
                elif H[i] >= pos['tp']:
                    ex = pos['tp']; why = 'TP'
            else:
                if H[i] + sp >= pos['sl']:
                    ex = max(pos['sl'], O[i] + sp) + P['slip']; why = 'SL'
                elif L[i] + sp <= pos['tp']:
                    ex = pos['tp']; why = 'TP'
            if ex is not None:
                r = (ex - pos['ent']) * d / pos['risk']
                trades.append(dict(t=pos['t0'], t_exit=t[i], ent=pos['ent'], d=d, r=r, why=why, risk=pos['risk'], nym=pos['nym']))
                dayR += r
                consec = consec + 1 if r < 0 else 0
                if dayR <= -P['daily_loss_r']:
                    locked = True
                pos = None
        # ── 3) actualización del estado con la barra i cerrada ─────────────
        if prev_nyday is not None and nyday[i] != prev_nyday:
            tradesToday = 0; dayR = 0.0; locked = False; consec = 0
        prev_nyday = nyday[i]
        h, l, c, o = H[i], L[i], C[i], O[i]
        tr = h - l if i == 0 else max(h - l, abs(h - C[i - 1]), abs(l - C[i - 1]))
        if math.isnan(atr):
            trs.append(tr)
            if len(trs) >= P['atr_len']:
                atr = sum(trs) / len(trs)
        else:
            atr = (atr * (P['atr_len'] - 1) + tr) / P['atr_len']
        if math.isnan(atr):
            continue
        vq.append(V[i]); vs = sum(vq) / len(vq)
        rvol = V[i] / vs if vs > 0 else math.nan
        rvolOk = rvol >= P['rvol_thr']; rvolLow = rvol < P['rvol_low']

        inRTH = in_sess(m, S_RTH, E_RTH); inON = bool(on_mask[i])
        inPM = False if S_PM is None else in_sess(m, S_PM, E_ON)
        inOR = in_sess(m, S_OR, E_OR); inTR = in_sess(m, S_TR, E_TR); inFL = m >= flat_min
        if (not inRTH) and rth.prev_in:
            dcl.append(C[i - 1])
            if P['regime'] == 'sma' and len(dcl) >= P['reg_len']:
                sma = sum(dcl[-P['reg_len']:]) / P['reg_len']
                reg_up = dcl[-1] > sma; reg_dn = dcl[-1] < sma
        if inRTH and not rth.prev_in and len(dcl) > 0:
            g = abs(o - dcl[-1])
            if P['gap_min'] > 0 and len(gaps) >= 5:
                med = float(np.median(gaps[-P['gap_len']:]))
                gap_ok = med > 0 and g / med >= P['gap_min']
            else:
                gap_ok = True
            gaps.append(g)
        pdh, pdl = rth.upd(inRTH, h, l); onh_, onl_ = onh.upd(inON, h, l); pmh_, pml_ = pmh.upd(inPM, h, l)

        # Opening range
        if inOR and not prev_inOR:
            orH, orL = h, l; orDone = False; brokeUp = brokeDn = False; brkUp = brkDn = -1
        elif inOR:
            orH = max(orH, h); orL = min(orL, l)
        if (not inOR) and prev_inOR and not math.isnan(orH):
            orDone = True; orW.append(orH - orL)
        prev_inOR = inOR
        orMid = (orH + orL) / 2
        if orDone and not brokeUp and c > orH:
            brokeUp = True; brkUp = i
        if orDone and not brokeDn and c < orL:
            brokeDn = True; brkDn = i
        if brokeUp and brkUp >= 0 and 0 < i - brkUp <= P['fb_window'] and c < orH:
            brokeUp = False
        if brokeDn and brkDn >= 0 and 0 < i - brkDn <= P['fb_window'] and c > orL:
            brokeDn = False

        # Sweeps
        levels = dict(pdh=(pdh, P['use_pd'], 1), onh=(onh_, P['use_on'], 1), pmh=(pmh_, P['use_pm'], 1),
                      orh=(orH if orDone else math.nan, P['use_or'], 1),
                      pdl=(pdl, P['use_pd'], -1), onl=(onl_, P['use_on'], -1), pml=(pml_, P['use_pm'], -1),
                      orl=(orL if orDone else math.nan, P['use_or'], -1))
        bull = bear = False
        for k, (lv, on, side) in levels.items():
            hist = lvl_hist[k]; hist.append(lv)
            if not on or math.isnan(lv) or hist[0] != lv:
                continue
            if side == 1:
                raw = c < lv and (h > lv or (C[i - 1] > lv and C[i - 2] <= lv))
            else:
                raw = c > lv and (l < lv or (C[i - 1] < lv and C[i - 2] >= lv))
            if raw and i - sw_last[k] > P['sweep_cool']:
                sw_last[k] = i
                if side == 1:
                    bear = True
                else:
                    bull = True
        if bull:
            lastBullSw = i; lastBullLow = min(l, L[i - 1])
        if bear:
            lastBearSw = i; lastBearHigh = max(h, H[i - 1])
        recBull = i - lastBullSw <= P['sweep_window']; recBear = i - lastBearSw <= P['sweep_window']

        # FVG
        if i >= 2:
            gu = l - H[i - 2]; gd = L[i - 2] - h
            if gu > 0 and gu >= P['fvg_min_atr'] * atr:
                fvgs.append([i, True, l, H[i - 2]])
            if gd > 0 and gd >= P['fvg_min_atr'] * atr:
                fvgs.append([i, False, L[i - 2], h])
        hi = hidx[i]
        if hi != prev_hidx and hi >= 3:
            a, b = hi - 1, hi - 3
            gu = hL[a] - hH[b]; gd = hL[b] - hH[a]
            if gu > 0 and gu >= P['fvg_min_atr'] * atr:
                fvgs.append([i, True, hL[a], hH[b]])
            if gd > 0 and gd >= P['fvg_min_atr'] * atr:
                fvgs.append([i, False, hL[b], hH[a]])
        prev_hidx = hi
        while len(fvgs) > P['fvg_max']:
            fvgs.pop(0)
        bNear = sNear = inB = inS = False
        keep = []
        for f in fvgs:
            fi, fb, top, bot = f
            filled = l <= bot if fb else h >= top
            if filled or i - fi > P['fvg_ext']:
                continue
            keep.append(f)
            if fb:
                if c >= bot and c - top <= P['fvg_prox_atr'] * atr: bNear = True
                if bot <= c <= top: inB = True
            else:
                if c <= top and bot - c <= P['fvg_prox_atr'] * atr: sNear = True
                if bot <= c <= top: inS = True
        fvgs = keep

        # VWAP
        inV = inRTH
        if inV and not prev_inV:
            cPV = cV = cP2V = 0.0
        if inV:
            src = (h + l + c) / 3
            cPV += src * V[i]; cV += V[i]; cP2V += src * src * V[i]
        prev_inV = inV
        if cV > 0:
            vw = cPV / cV; sd = math.sqrt(max(cP2V / cV - vw * vw, 0.0))
            dsd = (c - vw) / sd if sd > 0 else 0.0
            above, below = c > vw, c < vw
        else:
            vw = math.nan; dsd = 0.0; above = below = False

        # Estructura
        R, Lp = P['piv_r'], P['piv_l']
        if i >= R + Lp:
            ci = i - R
            ch, cl = H[ci], L[ci]
            if ch > H[ci - Lp:ci].max() and ch >= H[ci + 1:i + 1].max():
                lastPH = ch; phB = False
            if cl < L[ci - Lp:ci].min() and cl <= L[ci + 1:i + 1].min():
                lastPL = cl; plB = False
        if not math.isnan(lastPH) and not phB and c > lastPH:
            phB = True; trend = 1
        if not math.isnan(lastPL) and not plB and c < lastPL:
            plB = True; trend = -1

        # Score
        cSwL = 1.0 if recBull and lastBullSw >= lastBearSw else 0.0
        cSwS = 1.0 if recBear and lastBearSw >= lastBullSw else 0.0
        cFvgL = 1.0 if bNear and not inS else 0.0
        cFvgS = 1.0 if sNear and not inB else 0.0
        cVwL = (0.5 if dsd > P['vwap_ext_sd'] else 1.0) if above else 0.0
        cVwS = (0.5 if -dsd > P['vwap_ext_sd'] else 1.0) if below else 0.0
        cStL = 1.0 if trend == 1 else 0.0; cStS = 1.0 if trend == -1 else 0.0
        cRv = 1.0 if rvolOk else (0.5 if rvol >= 1.0 else 0.0)
        cOrL = (1.0 if c > orH else 0.5 if c > orMid else 0.0) if orDone else 0.0
        cOrS = (1.0 if c < orL else 0.5 if c < orMid else 0.0) if orDone else 0.0
        sL = nSw * cSwL + nFvg * cFvgL + nVw * cVwL + nSt * cStL + nRv * cRv + nOr * cOrL
        sS = nSw * cSwS + nFvg * cFvgS + nVw * cVwS + nSt * cStS + nRv * cRv + nOr * cOrS
        vetoL = cSwS == 1 or (trend == -1 and below) or inS or rvolLow
        vetoS = cSwL == 1 or (trend == 1 and above) or inB or rvolLow

        if pos is not None:
            d = pos['d']
            if d == 1:
                if P['be'] and pos['sl'] < pos['ent'] + (P['be_off_r'] or 0) * pos['risk'] - 1e-9 and h >= pos['ent'] + P['be_r'] * pos['risk']:
                    pos['sl'] = pos['ent'] + (P['be_off_r'] * pos['risk'] if P['be_off_r'] is not None else P['be_off'])
                if P['trail'] and h - pos['ent'] >= P['trail_start_r'] * pos['risk']:
                    pos['sl'] = max(pos['sl'], h - P['trail_atr'] * atr)
            else:
                if P['be'] and pos['sl'] > pos['ent'] - (P['be_off_r'] or 0) * pos['risk'] + 1e-9 and l + SP[i] <= pos['ent'] - P['be_r'] * pos['risk']:
                    pos['sl'] = pos['ent'] - (P['be_off_r'] * pos['risk'] if P['be_off_r'] is not None else P['be_off'])
                if P['trail'] and pos['ent'] - (l + SP[i]) >= P['trail_start_r'] * pos['risk']:
                    pos['sl'] = min(pos['sl'], l + SP[i] + P['trail_atr'] * atr)
        if start is not None and t[i] < start: continue
        if end is not None and t[i] > end: continue
        if i + 1 >= n:
            continue
        if P['mode'] == 'cons':
            mL = cSwL == 1 and cVwL > 0 and cStL == 1 and (not P['req_fvg'] or cFvgL == 1)
            mS = cSwS == 1 and cVwS > 0 and cStS == 1 and (not P['req_fvg'] or cFvgS == 1)
        else:
            mL = (cSwL == 1 or (brokeUp and c > orH)) and cVwL > 0
            mS = (cSwS == 1 or (brokeDn and c < orL)) and cVwS > 0
        okL = P['allow_long'] and gap_ok and reg_up and inTR and orDone and not vetoL and sL >= P['min_score'] and mL
        okS = P['allow_short'] and gap_ok and reg_dn and inTR and orDone and not vetoS and sS >= P['min_score'] and mS
        can = inTR and not inFL and not holiday and entry_allowed(m, flat_min, S["min_before_flat"]) and tradesToday < P['max_trades'] and not locked and consec < P['max_consec'] and pos is None and i - lastEntry > P['cooldown'] and SP[i] <= P['max_spread']
        if not can or not (okL or okS):
            pass
        else:
            minsl = P['min_sl']
            if okL:
                ssl = (lastBullLow - P['sl_buf']) if (recBull and not math.isnan(lastBullLow)) else (lastPL - P['sl_buf'] if not math.isnan(lastPL) else math.nan)
                atrsl = c - max(P['sl_atr'] * atr, minsl)
                sl = atrsl if (P['sl_mode'] == 'atr' or math.isnan(ssl) or c - ssl < minsl or c - ssl > P['max_sl_atr'] * atr) else ssl
                pending = (1, sl)
            else:
                ssl = (lastBearHigh + P['sl_buf']) if (recBear and not math.isnan(lastBearHigh)) else (lastPH + P['sl_buf'] if not math.isnan(lastPH) else math.nan)
                atrsl = c + max(P['sl_atr'] * atr, minsl)
                sl = atrsl if (P['sl_mode'] == 'atr' or math.isnan(ssl) or ssl - c < minsl or ssl - c > P['max_sl_atr'] * atr) else ssl
                pending = (-1, sl)
            lastEntry = i
    return pd.DataFrame(trades)


def stats(tr):
    if len(tr) == 0:
        return dict(n=0)
    r = tr.r.values
    w = r[r > 0]; ls = r[r <= 0]
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()
    pf = w.sum() / -ls.sum() if ls.sum() < 0 else np.inf
    return dict(n=len(r), win=round(len(w) / len(r) * 100, 1), pf=round(pf, 2), expR=round(r.mean(), 3),
                totR=round(r.sum(), 1), maxDD_R=round(dd, 1), avgW=round(w.mean() if len(w) else 0, 2),
                avgL=round(ls.mean() if len(ls) else 0, 2))
