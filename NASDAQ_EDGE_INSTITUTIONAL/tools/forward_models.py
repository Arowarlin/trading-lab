"""Modelos congelados del forward NQEDGE (NQF-A, NQF-B, NQF-C).

Solo mecanica: detectan senales, stops y objetivos. **No** calculan P&L ni
resultados. La comision de MNQ es un input obligatorio del operador; si falta,
`contracts_for_risk` lanza `MissingInput` ("Sin datos").

Reglas congeladas el 2026-11-25 (antes de mirar datos forward):

- NQF-A: OR de 15 min (9:30-9:44 ET). Entrada al cierre de la primera vela M5
  que cierra > ORH + 1 tick (o < ORL - 1 tick), sin retest. Stop en el lado
  opuesto de la OR o 1xATR5 desde el cierre, el mas cercano. Objetivo 2R.
- NQF-B: nivel ON (ONH/ONL). Barrido >= 2 ticks y cierre M5 de vuelta dentro
  (hasta 3 velas desde el barrido). Entrada en contra. Stop 1 tick mas alla
  del extremo del barrido. Objetivo VWAP del momento de la senal.
- NQF-C: reversion al VWAP. Cierre M5 fuera de VWAP +/- 2 sigma y cierre
  siguiente de vuelta dentro. Entrada en contra. Stop en el extremo de las
  ultimas 6 velas M5 +/- 1 tick. Objetivo VWAP.
- Comunes: entrada en la apertura de la vela M1 siguiente + slippage; si SL y
  TP caen en la misma vela, primero el SL; flat 15:55 ET; ventana 9:35-11:30;
  FOMC sin entradas; Tier 1 dentro de la sesion, cierre 5 min antes y sin
  entradas en +/- 5 min.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TICK = 0.25
MNQ_USD_PER_POINT = 2.0
RISK_USD = 150.0
ENTRY_START = 9 * 60 + 35
ENTRY_END = 11 * 60 + 30
FLAT = 15 * 60 + 55
SESS_OPEN = 9 * 60 + 30
SESS_CLOSE = 16 * 60

VARIANTS = ("NQF-A", "NQF-B", "NQF-C")


class MissingInput(ValueError):
    """Falta un dato del operador; nunca se sustituye por una hipotesis."""


@dataclass(frozen=True)
class Signal:
    variant: str
    day: str
    k5: int
    entry_min: int
    side: int
    stop: float
    target: float | None
    tag: str


# ------------------------------------------------------------------ preparacion


def m5(r: dict) -> dict:
    """Agrega M1 RTH a velas M5 etiquetadas por apertura (9:30, 9:35...)."""
    t = np.asarray(r["t"])
    slot = (t - SESS_OPEN) // 5
    out = {"slot": [], "o": [], "h": [], "l": [], "c": [], "v": [], "end_min": [], "last_i": []}
    for s in np.unique(slot):
        idx = np.flatnonzero(slot == s)
        out["slot"].append(int(s))
        out["o"].append(r["o"][idx[0]])
        out["h"].append(r["h"][idx].max())
        out["l"].append(r["l"][idx].min())
        out["c"].append(r["c"][idx[-1]])
        out["v"].append(r["v"][idx].sum())
        out["end_min"].append(SESS_OPEN + 5 * int(s) + 5)
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


def prepare_sessions(rows: list[dict]) -> list[dict]:
    """Devuelve copias con M5, VWAP/sigma y ATR5 continuo entre sesiones."""
    out = []
    allh, alll, allc, owner = [], [], [], []
    for i, r in enumerate(rows):
        rec = dict(r)
        b = m5(rec)
        rec["b"] = b
        rec["vwap"], rec["sd"] = vwap_sd(rec)
        allh += list(b["h"])
        alll += list(b["l"])
        allc += list(b["c"])
        owner += [i] * len(b["h"])
        out.append(rec)
    atr = atr_series(np.array(allh), np.array(alll), np.array(allc))
    owner = np.asarray(owner)
    for i, rec in enumerate(out):
        rec["atr5"] = atr[owner == i]
    return out


# --------------------------------------------------------------------- senales


def _window_ok(end_min: int) -> bool:
    return ENTRY_START <= end_min <= ENTRY_END


def signal_a(r: dict, or_min: int = 15) -> list[Signal]:
    b = r["b"]
    if len(b["c"]) <= or_min // 5:
        return []
    k_or = or_min // 5
    hi = float(b["h"][:k_or].max())
    lo = float(b["l"][:k_or].min())
    for k in range(k_or, len(b["c"])):
        end = int(b["end_min"][k])
        if end > ENTRY_END:
            break
        close = float(b["c"][k])
        side = 1 if close > hi + TICK else -1 if close < lo - TICK else 0
        if not side:
            continue
        a = float(r["atr5"][k])
        if side > 0:
            stop = max(lo, close - a) if math.isfinite(a) else lo
        else:
            stop = min(hi, close + a) if math.isfinite(a) else hi
        return [
            Signal("NQF-A", str(r["day"]), k, end, side, float(stop), None, "A-OR15")
        ]
    return []


def signal_b(r: dict, level: str = "ON") -> list[Signal]:
    b = r["b"]
    names = ("onh", "onl") if level == "ON" else ("pdh", "pdl")
    out: list[Signal] = []
    for nm in names:
        lvl = r.get(nm, math.nan)
        if not math.isfinite(lvl):
            continue
        hi_side = nm.endswith("h")
        if (hi_side and b["o"][0] > lvl) or (not hi_side and b["o"][0] < lvl):
            continue
        ex = None
        for k in range(len(b["c"])):
            if int(b["end_min"][k]) > ENTRY_END:
                break
            if (hi_side and b["h"][k] >= lvl + 2 * TICK) or (
                not hi_side and b["l"][k] <= lvl - 2 * TICK
            ):
                ex = k
                break
        if ex is None:
            continue
        for k in range(ex, min(ex + 3, len(b["c"]))):
            end = int(b["end_min"][k])
            if end > ENTRY_END:
                break
            back = b["c"][k] < lvl if hi_side else b["c"][k] > lvl
            if not back:
                continue
            ext = float(b["h"][ex : k + 1].max()) if hi_side else float(b["l"][ex : k + 1].min())
            side = -1 if hi_side else 1
            i = int(b["last_i"][k])
            out.append(
                Signal(
                    "NQF-B",
                    str(r["day"]),
                    k,
                    end,
                    side,
                    ext - side * TICK,
                    float(r["vwap"][i]),
                    f"B-{nm}",
                )
            )
            break
    return sorted(out, key=lambda s: s.k5)


def signal_c(r: dict) -> list[Signal]:
    b = r["b"]
    out: list[Signal] = []
    for k in range(1, len(b["c"])):
        end = int(b["end_min"][k])
        if end > ENTRY_END:
            break
        if end < ENTRY_START:
            continue
        i = int(b["last_i"][k])
        vw, sd = float(r["vwap"][i]), float(r["sd"][i])
        if sd <= 0:
            continue
        ip = int(b["last_i"][k - 1])
        vp, sp = float(r["vwap"][ip]), float(r["sd"][ip])
        if b["c"][k - 1] > vp + 2 * sp and b["c"][k] < vw + 2 * sd:
            ext = float(b["h"][max(0, k - 6) : k + 1].max())
            out.append(Signal("NQF-C", str(r["day"]), k, end, -1, ext + TICK, vw, "C-rev"))
        elif b["c"][k - 1] < vp - 2 * sp and b["c"][k] > vw - 2 * sd:
            ext = float(b["l"][max(0, k - 6) : k + 1].min())
            out.append(Signal("NQF-C", str(r["day"]), k, end, 1, ext - TICK, vw, "C-rev"))
    return out


def signals_for(r: dict, variant: str) -> list[Signal]:
    if variant == "NQF-A":
        return signal_a(r)
    if variant == "NQF-B":
        return signal_b(r, "ON")
    if variant == "NQF-C":
        return signal_c(r)
    raise ValueError(f"variante desconocida: {variant}")


# ----------------------------------------------------------------------- riesgo


def contracts_for_risk(
    stop_points: float,
    commission_side_usd: float | None,
    *,
    slip_ticks: float = 1.0,
    risk_usd: float = RISK_USD,
) -> int:
    """Contratos = floor(riesgo / (stop_pt x 2 USD + comision x 2 + slippage x 2)).

    `commission_side_usd` es el input del operador por contrato y lado. Si falta,
    no se inventa: `MissingInput`.
    """
    if commission_side_usd is None:
        raise MissingInput("Sin datos: comision MNQ por contrato y lado del operador")
    stop_points = abs(float(stop_points))
    if not math.isfinite(stop_points) or stop_points <= 0:
        return 0
    commission = 2.0 * float(commission_side_usd)
    slip = 2.0 * float(slip_ticks) * TICK * MNQ_USD_PER_POINT
    return int(risk_usd // (stop_points * MNQ_USD_PER_POINT + commission + slip))


# ------------------------------------------------------------------ ejecucion


def same_bar_outcome(
    entry: float, stop: float, target: float, high: float, low: float, side: int
) -> str | None:
    """Si SL y TP caen en la misma vela, gana el SL (regla congelada)."""
    hit_stop = low <= stop if side > 0 else high >= stop
    hit_target = high >= target if side > 0 else low <= target
    if hit_stop:
        return "stop"
    if hit_target:
        return "target"
    return None


def target_price(signal: Signal, entry: float) -> float:
    if signal.target is not None:
        return float(signal.target)
    risk = abs(entry - signal.stop)
    return entry + signal.side * 2.0 * risk


def load_news(project: Path) -> tuple[set[str], list[tuple[str, int, str]]]:
    """FOMC (dia completo) y Tier 1 con hora (NFP/CPI/PPI)."""
    import csv

    fomc: set[str] = set()
    with (project / "02_DATA/fomc_dates.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            fomc.add(str(row["date"]).strip())
    tier1: list[tuple[str, int, str]] = []
    with (project / "02_DATA/news_calendar_history.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if int(row["tier"]) != 1:
                continue
            raw = (row.get("time_et") or "").strip()
            if not raw:
                continue
            hh, mm = (int(part) for part in raw.split(":", 1))
            tier1.append((str(row["date"]).strip(), hh * 60 + mm, str(row["event"])))
    return fomc, tier1


def news_reason(
    day: str,
    entry_min: int,
    fomc: set[str],
    tier1: list[tuple[str, int, str]],
    *,
    window_min: int = 5,
) -> str | None:
    """Motivo por el que una entrada queda bloqueada, o None."""
    if day in fomc:
        return "fomc"
    for d, minute, event in tier1:
        if d != day:
            continue
        if SESS_OPEN <= minute <= SESS_CLOSE and abs(entry_min - minute) <= window_min:
            return f"tier1_pre:{event}"
    return None


def news_exit_minute(
    day: str, tier1: list[tuple[str, int, str]], *, before_min: int = 5
) -> int | None:
    """Minuto ET en el que hay que estar fuera por un Tier 1 dentro de la sesion."""
    mins = [
        minute - before_min
        for d, minute, _ in tier1
        if d == day and SESS_OPEN <= minute <= SESS_CLOSE
    ]
    return min(mins) if mins else None


@dataclass(frozen=True)
class Execution:
    entry_min: int
    entry: float
    stop: float
    target: float
    exit_min: int
    exit_price: float
    reason: str
    contracts: int


def execute_signal(
    r: dict,
    signal: Signal,
    *,
    contracts: int,
    slip_ticks: float = 1.0,
    news_exit: int | None = None,
) -> Execution | None:
    """Ejecuta una senal sobre M1. No devuelve R ni USD (solo precios y motivo)."""
    t, o, h, low = r["t"], r["o"], r["h"], r["l"]
    end = int(signal.entry_min)
    j = int(np.searchsorted(t, end))
    if j >= len(t):
        return None
    slip = slip_ticks * TICK
    entry = float(o[j]) + signal.side * slip
    stop = float(signal.stop)
    target = target_price(signal, entry)
    if (target - entry) * signal.side < abs(entry - stop):
        return None
    exit_i, exit_px, reason = None, float("nan"), ""
    for k in range(j, len(t)):
        if int(t[k]) >= FLAT:
            exit_i, exit_px, reason = k, float(o[k]) - signal.side * slip, "flat"
            break
        if news_exit is not None and int(t[k]) >= news_exit:
            exit_i, exit_px, reason = k, float(o[k]) - signal.side * slip, "news"
            break
        hit = same_bar_outcome(
            entry, stop, target, float(h[k]), float(low[k]), signal.side
        )
        if hit == "stop":
            exit_i, exit_px, reason = k, stop - signal.side * slip, "stop"
            break
        if hit == "target":
            exit_i, exit_px, reason = k, target, "target"
            break
    if exit_i is None:
        exit_i, exit_px, reason = len(t) - 1, float(r["c"][-1]) - signal.side * slip, "eod"
    return Execution(
        entry_min=end,
        entry=entry,
        stop=stop,
        target=target,
        exit_min=int(t[exit_i]),
        exit_price=exit_px,
        reason=reason,
        contracts=int(contracts),
    )


def r_net(
    execution: Execution, signal: Signal, commission_side_usd: float, *, slip_ticks: float = 1.0
) -> float:
    """R neto de una operacion. Solo para F7; no se llama en F3/F5."""
    risk = abs(execution.entry - execution.stop)
    if risk <= 0:
        raise ValueError("stop invalido")
    gross = (execution.exit_price - execution.entry) * signal.side
    commission_pts = 2.0 * commission_side_usd / MNQ_USD_PER_POINT
    return (gross - commission_pts) / risk
