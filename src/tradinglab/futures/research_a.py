"""Research A (microestructura y order flow), familia FUT-RA-1: detectores y conteo sin desenlaces — FUT-C2.

Reglas fijas de docs/futures/research/RA_spec.md §3-§5 para las hipótesis A, C, D, E, H e I. Entrada: velas
M1 de NQ con índice en hora de Nueva York (``orderflow.minute_bars``), referencias móviles por minuto del día
(``orderflow.rolling_refs``) y footprint por minuto y nivel (``orderflow.footprint``). El OOS-2 (≥ 2024-01-01,
OP-8) se descarta ANTES de construir cualquier rasgo.

* ``detect`` devuelve eventos SIN desenlace: ``minute``, ``side`` y ``stop``. Es lo único permitido antes de
  registrar la familia (RA_spec §1: antes de registrar, solo conteos sin desenlaces).
* ``count_events`` cuenta eventos, filtro de coste y operables por hipótesis y año. NO calcula P&L, R, salidas
  ni objetivos alcanzados.

Lecturas fijadas en FUT-C2:

* ``sC``: 1,4826·MAD de ``cvd_t − cvd_{t−30}`` en las 20 sesiones previas, en el mismo minuto del día.
* ``medL``: mediana del pool de volúmenes ``B+S`` no nulos por nivel de las 20 sesiones previas.
* Hipótesis D: el apilamiento es la racha completa de niveles consecutivos con desequilibrio; el stop va en su
  nivel más bajo (largo) o más alto (corto) ± 1 tick. Si una vela tiene apilamiento en las dos direcciones,
  manda el largo.
* Filtro de coste de ``count_events``: sin cotizaciones todavía (FUT-C3), la entrada proxy es el ``close`` de
  la vela de señal, así que ``cost_filter`` cuenta ``|close − stop| < 4,2`` puntos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

NY = "America/New_York"
TICK = 0.25
OOS2_START = pd.Timestamp("2024-01-01", tz=NY)
WINDOW = ("09:45", "15:30")
MAX_EVENTS = 3
GAP_MINUTES = 15
COST_STOP_POINTS = 4.2
HYPOTHESES = ("A", "C", "D", "E", "H", "I")
BAR_COLUMNS = ("open", "high", "low", "close", "volume", "delta", "cvd")
REF_COLUMNS = ("medV", "medRng", "s_delta")


def _ny(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    idx = pd.DatetimeIndex(out.index)
    out.index = idx.tz_localize(NY) if idx.tz is None else idx.tz_convert(NY)
    return out


def _ny_minutes(values) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(values))
    return idx.tz_localize(NY) if idx.tz is None else idx.tz_convert(NY)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], source: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"Sin datos: {source}.{missing[0]}")


def seal(bars: pd.DataFrame) -> pd.DataFrame:
    """Descarta las filas del holdout sellado (OP-8) antes de construir cualquier rasgo."""
    b = _ny(bars)
    return b.loc[b.index < OOS2_START]


def _mad(w: np.ndarray) -> float:
    return float(np.median(np.abs(w - np.median(w))))


def s_c(bars: pd.DataFrame, *, sessions: int = 20) -> pd.Series:
    """``sC``: 1,4826·MAD de ``cvd_t − cvd_{t−30}`` en las ``sessions`` sesiones previas, por minuto del día."""
    b = seal(bars).sort_index()
    _require(b, BAR_COLUMNS, "bars")
    session = pd.Series(b.index.date, index=b.index)
    d30 = b["cvd"] - b["cvd"].groupby(session).shift(30)
    mod = pd.Series(b.index.strftime("%H:%M"), index=b.index)
    scale = d30.groupby(mod).transform(
        lambda s: s.shift(1).rolling(sessions, min_periods=sessions).apply(_mad, raw=True))
    return (1.4826 * scale).rename("s_c")


def med_l(footprints: pd.DataFrame, *, sessions: int = 20) -> pd.Series:
    """``medL`` por sesión: mediana del pool de volúmenes ``B+S`` no nulos por nivel de las ``sessions``
    sesiones previas con footprint. Solo pasado."""
    _require(footprints, ("buy", "sell"), "footprints")
    minute = _ny_minutes(footprints.index.get_level_values(0))
    total = footprints["buy"].to_numpy(float) + footprints["sell"].to_numpy(float)
    frame = pd.DataFrame({"session": pd.Index(minute.date), "total": total})
    frame = frame.loc[frame["total"] > 0].sort_values("session", kind="stable")
    grouped = frame.groupby("session", sort=True)["total"]
    order = sorted(grouped.groups)
    arrays = [grouped.get_group(s).to_numpy() for s in order]
    values = {s: float(np.median(np.concatenate(arrays[i - sessions:i])))
              for i, s in enumerate(order) if i >= sessions}
    return pd.Series(values, name="medL", dtype=float)


def _cvd_at_extreme(df: pd.DataFrame, column: str, *, upper: bool) -> pd.Series:
    """``cvd_{t0}`` con ``t0 = argmax/argmin`` de ``column`` en ``[t−30, t−1]`` (primera aparición del extremo)."""
    vals = df[column].to_numpy(float)
    cvd = df["cvd"].to_numpy(float)
    out = np.full(vals.size, np.nan)
    keys = df["session"].to_numpy()
    edges = np.flatnonzero(keys[1:] != keys[:-1]) + 1
    for a, b in zip(np.r_[0, edges], np.r_[edges, keys.size], strict=True):
        if b - a <= 30:
            continue
        w = sliding_window_view(vals[a:b], 30)[:-1]
        c = sliding_window_view(cvd[a:b], 30)[:-1]
        k = w.argmax(axis=1) if upper else w.argmin(axis=1)
        out[a + 30:b] = c[np.arange(k.size), k]
    return pd.Series(out, index=df.index)


def _prepare(bars: pd.DataFrame, refs: pd.DataFrame, footprints: pd.DataFrame | None, *,
             need_med_l: bool) -> pd.DataFrame:
    b = seal(bars).sort_index()
    _require(b, BAR_COLUMNS, "bars")
    _require(refs, REF_COLUMNS, "refs")
    df = b.copy()
    df["session"] = df.index.date
    df["mod"] = df.index.strftime("%H:%M")
    r = _ny(refs).reindex(df.index)
    for col in REF_COLUMNS:
        df[col] = r[col].to_numpy(float)
    scale = df["s_delta"].where(df["s_delta"] > 0)
    df["z"] = df["delta"] / scale
    grp = df.groupby("session", sort=False)
    df["r30_max"] = grp["high"].transform(lambda s: s.rolling(30).max().shift(1))
    df["r30_min"] = grp["low"].transform(lambda s: s.rolling(30).min().shift(1))
    df["cvd30"] = grp["cvd"].transform(lambda s: s.shift(30))
    df["s_c"] = s_c(df)
    df["medL"] = df["session"].map(med_l(footprints)) if need_med_l else np.nan
    df["in_window"] = (df["mod"] >= WINDOW[0]) & (df["mod"] <= WINDOW[1])
    return df


def _longest_run(levels: list[int]) -> tuple[int, int, int]:
    """(longitud, primer nivel, último nivel) de la racha más larga de niveles consecutivos."""
    best = (0, 0, 0)
    start = prev = None
    for k in sorted(set(levels)):
        if prev is not None and k == prev + 1:
            length = k - start + 1
        else:
            start, length = k, 1
        if length > best[0]:
            best = (length, start, k)
        prev = k
    return best


def _stacked_levels(df: pd.DataFrame, footprints: pd.DataFrame) -> dict[pd.Timestamp, dict[str, int | None]]:
    """Por minuto con vela: nivel del apilamiento de compra (el más bajo) y de venta (el más alto)."""
    _require(footprints, ("buy", "sell"), "footprints")
    minute = _ny_minutes(footprints.index.get_level_values(0))
    frame = pd.DataFrame({"minute": minute,
                          "level": np.asarray(footprints.index.get_level_values(1)),
                          "buy": footprints["buy"].to_numpy(float),
                          "sell": footprints["sell"].to_numpy(float)})
    out: dict[pd.Timestamp, dict[str, int | None]] = {}
    for ts, grp in frame.groupby("minute", sort=False):
        if ts not in df.index:
            continue
        floor = float(df.at[ts, "medL"])
        if not np.isfinite(floor):
            continue
        buy = dict(zip(grp["level"].to_list(), grp["buy"].to_list(), strict=True))
        sell = dict(zip(grp["level"].to_list(), grp["sell"].to_list(), strict=True))
        levels = sorted(set(buy) | set(sell))
        long_imbalance = [k for k in levels
                          if buy.get(k, 0.0) > 0 and buy[k] >= 3 * sell.get(k - 1, 0.0) and buy[k] >= floor]
        short_imbalance = [k for k in levels
                           if sell.get(k, 0.0) > 0 and sell[k] >= 3 * buy.get(k + 1, 0.0) and sell[k] >= floor]
        n_long, low_level, _ = _longest_run(long_imbalance)
        n_short, _, high_level = _longest_run(short_imbalance)
        out[ts] = {"long": low_level if n_long >= 3 else None,
                   "short": high_level if n_short >= 3 else None}
    return out


def _signal(df: pd.DataFrame, hypothesis: str, footprints: pd.DataFrame | None,
            tick: float) -> pd.DataFrame:
    """Filas con señal: columnas ``side`` (+1/−1) y ``stop``. Sin desenlace."""
    o, h, lo, c = df["open"], df["high"], df["low"], df["close"]
    v, d = df["volume"], df["delta"]
    med_v = df["medV"]
    side = pd.Series(0, index=df.index, dtype=int)
    stop = pd.Series(np.nan, index=df.index, dtype=float)
    if hypothesis == "A":
        long_ = (df["z"] <= -3) & (c >= o) & (v >= 2 * med_v)
        short = (df["z"] >= 3) & (c <= o) & (v >= 2 * med_v)
        stop = stop.mask(short, h + tick).mask(long_, lo - tick)
        side = side.mask(short, -1).mask(long_, 1)
    elif hypothesis == "C":
        cvd_hi = _cvd_at_extreme(df, "high", upper=True)
        cvd_lo = _cvd_at_extreme(df, "low", upper=False)
        short = (h > df["r30_max"]) & (df["cvd"] < cvd_hi - df["s_c"])
        long_ = (lo < df["r30_min"]) & (df["cvd"] > cvd_lo + df["s_c"])
        stop = stop.mask(short, h + tick).mask(long_, lo - tick)
        side = side.mask(short, -1).mask(long_, 1)
    elif hypothesis == "D":
        if footprints is None:
            raise ValueError("Sin datos: footprints (la hipótesis D necesita B_t(k) y S_t(k))")
        for ts, stack in _stacked_levels(df, footprints).items():
            mid = (float(df.at[ts, "high"]) + float(df.at[ts, "low"])) / 2.0
            close = float(df.at[ts, "close"])
            if stack["long"] is not None and close >= mid:
                side.at[ts], stop.at[ts] = 1, stack["long"] * tick - tick
            elif stack["short"] is not None and close <= mid:
                side.at[ts], stop.at[ts] = -1, stack["short"] * tick + tick
    elif hypothesis == "E":
        short = (c > df["r30_max"] + tick) & (d < 0)
        long_ = (c < df["r30_min"] - tick) & (d > 0)
        stop = stop.mask(short, h + tick).mask(long_, lo - tick)
        side = side.mask(short, -1).mask(long_, 1)
    elif hypothesis == "H":
        short = (c < df["r30_min"] - tick) & (df["z"] <= -2) & (df["cvd"] - df["cvd30"] < 0)
        long_ = (c > df["r30_max"] + tick) & (df["z"] >= 2) & (df["cvd"] - df["cvd30"] > 0)
        stop = stop.mask(short, h + tick).mask(long_, lo - tick)
        side = side.mask(short, -1).mask(long_, 1)
    elif hypothesis == "I":
        long_ = (v >= 3 * med_v) & (h - lo >= 2 * df["medRng"]) & (d > 0) & (c > o)
        short = (v >= 3 * med_v) & (h - lo >= 2 * df["medRng"]) & (d < 0) & (c < o)
        stop = stop.mask(short, h + tick).mask(long_, lo - tick)
        side = side.mask(short, -1).mask(long_, 1)
    rows = side != 0
    return pd.DataFrame({"side": side[rows], "stop": stop[rows]}, index=df.index[rows])


def _scan(df: pd.DataFrame, hypothesis: str, footprints: pd.DataFrame | None, tick: float) -> list[dict]:
    """Eventos en la ventana 09:45-15:30, máximo 3 por sesión e hipótesis y separados ≥ 15 minutos."""
    sig = _signal(df, hypothesis, footprints, tick)
    if sig.empty:
        return []
    sig = sig.loc[df.loc[sig.index, "in_window"].to_numpy()]
    gap = pd.Timedelta(minutes=GAP_MINUTES)
    out: list[dict] = []
    for _, day in sig.groupby(sig.index.date, sort=True):
        last: pd.Timestamp | None = None
        n = 0
        for ts, row in day.iterrows():
            if n >= MAX_EVENTS:
                break
            if last is not None and ts - last < gap:
                continue
            out.append({"minute": ts, "side": int(row["side"]), "stop": float(row["stop"])})
            last, n = ts, n + 1
    return out


def detect(bars: pd.DataFrame, refs: pd.DataFrame, footprints: pd.DataFrame | None,
           hypothesis: str, *, tick: float = TICK) -> list[dict]:
    """Eventos de una hipótesis de RA-1 (A, C, D, E, H o I), SIN desenlace: ``minute``, ``side`` y ``stop``."""
    h = str(hypothesis).strip().upper()
    if h not in HYPOTHESES:
        raise ValueError(f"hipótesis fuera de FUT-RA-1: {hypothesis}")
    if h == "D" and footprints is None:
        raise ValueError("Sin datos: footprints (la hipótesis D necesita B_t(k) y S_t(k))")
    df = _prepare(bars, refs, footprints, need_med_l=h == "D")
    return _scan(df, h, footprints, tick)


def count_events(bars: pd.DataFrame, refs: pd.DataFrame, footprints: pd.DataFrame | None = None, *,
                 tick: float = TICK) -> pd.DataFrame:
    """FUT-C2: eventos, filtro de coste y operables por (hipótesis, año). Sin P&L, R, salidas ni objetivos.

    Sin ``footprints`` la hipótesis D no se cuenta (**Sin datos**); no se inventa.
    """
    df = _prepare(bars, refs, footprints, need_med_l=footprints is not None)
    rows: list[dict] = []
    for h in HYPOTHESES:
        if h == "D" and footprints is None:
            continue
        for ev in _scan(df, h, footprints, tick):
            risk = abs(float(df.at[ev["minute"], "close"]) - ev["stop"])
            rows.append({"hypothesis": h, "year": int(ev["minute"].year), "event": 1,
                         "cost_filter": int(risk < COST_STOP_POINTS)})
    columns = ["events", "cost_filter", "tradable"]
    names = ["hypothesis", "year"]
    if not rows:
        return pd.DataFrame(columns=columns,
                            index=pd.MultiIndex(levels=[[], []], codes=[[], []], names=names))
    out = pd.DataFrame(rows).groupby(names).sum().rename(columns={"event": "events"})
    out["tradable"] = out["events"] - out["cost_filter"]
    return out[columns]
