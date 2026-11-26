"""C1 · Deriva de USDJPY hacia el fix de Tokio en días gotobi (prueba única prerregistrada).

Prerregistro: docs/engineering/EDGE_RESEARCH_PLAN.md §2. Este script aplica la
regla **tal como está escrita**; no tiene parámetros que optimizar.

- Día gotobi: 5, 10, 15, 20, 25 y último día hábil del mes. Si cae en fin de
  semana o festivo japonés, se adelanta al día hábil anterior.
- Entrada: ASK de apertura de la vela M1 de las 09:00 JST (00:00 UTC; Japón no
  tiene horario de verano).
- Salida: BID de cierre de la vela M1 de las 09:54 JST (00:54 UTC).
- Placebo: la misma ventana en días hábiles que no son gotobi (no suma pruebas).
- Periodo: 2003-01-01 .. 2022-12-31. **Nada de 2023 en adelante** (OOS-2 sellado).
- Veredicto (prerregistrado): t HAC (Newey-West, 5 retardos) de la media neta
  < 1,645 → ``rejected``; media neta > 0 con signo distinto en 2003-2012 y
  2013-2022 → ``inconclusive``; si no, ``candidate`` (no validado).

Candados: no se ejecuta sin ``--approved-by-operator`` (registrar y ejecutar
suma +1 al contador de pruebas: AGENTS.md) y aborta si los datos cargados
contienen alguna marca >= 2023-01-01. Nunca imputa velas ausentes: el evento
cuenta como "Sin datos".
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PERIOD_START = pd.Timestamp("2003-01-01", tz="UTC")
SEALED_FROM = pd.Timestamp("2023-01-01", tz="UTC")
ENTRY_UTC = (0, 0)  # 09:00 JST
EXIT_UTC = (0, 54)  # 09:54 JST
PIP = 0.01
GOTOBI_DAYS = (5, 10, 15, 20, 25)
HAC_LAGS = 5
T_CRIT = 1.645
HALVES = (("2003-2012", "2003-01-01", "2012-12-31"), ("2013-2022", "2013-01-01", "2022-12-31"))


class SealedDataError(RuntimeError):
    """Los datos incluyen el tramo sellado (2023+)."""


def load_jp_holidays(path: Path) -> set:
    """Fechas de la primera columna del CSV oficial (``YYYY/M/D``), cualquier codificación."""

    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "shift_jis", "cp932"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - defensivo
        raise ValueError(f"no se pudo decodificar {path}")
    days = set()
    for line in text.splitlines():
        first = line.split(",")[0].strip()
        try:
            days.add(pd.Timestamp(first.replace("/", "-")).date())
        except ValueError:
            continue  # cabecera
    if not days:
        raise ValueError(f"Sin datos: {path} no contiene fechas")
    return days


def _business(day, holidays: set) -> bool:
    return day.weekday() < 5 and day not in holidays


def gotobi_days(start: str, end: str, holidays: set) -> list:
    """Días gotobi efectivos (ya movidos al hábil anterior) entre ``start`` y ``end``."""

    out = set()
    for month in pd.period_range(start, end, freq="M"):
        first = month.to_timestamp().date()
        last = (month.to_timestamp() + pd.offsets.MonthEnd(0)).date()
        candidates = [first.replace(day=d) for d in GOTOBI_DAYS]
        cursor = last
        while not _business(cursor, holidays):
            cursor -= pd.Timedelta(days=1).to_pytimedelta()
        candidates.append(cursor)
        for day in candidates:
            moved = day
            while not _business(moved, holidays):
                moved -= pd.Timedelta(days=1).to_pytimedelta()
            if pd.Timestamp(start).date() <= moved <= pd.Timestamp(end).date():
                out.add(moved)
    return sorted(out)


def event_returns(frame: pd.DataFrame, days: list) -> pd.Series:
    """Pips brutos por día: BID cierre 09:54 JST − ASK apertura 09:00 JST. NaN si falta una vela."""

    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    work = frame.set_axis(index.tz_convert("UTC"))
    values = {}
    for day in days:
        base = pd.Timestamp(day, tz="UTC")
        entry_at = base + pd.Timedelta(hours=ENTRY_UTC[0], minutes=ENTRY_UTC[1])
        exit_at = base + pd.Timedelta(hours=EXIT_UTC[0], minutes=EXIT_UTC[1])
        if entry_at not in work.index or exit_at not in work.index:
            values[day] = np.nan
            continue
        entry = work.at[entry_at, "ask_open"]
        exit_ = work.at[exit_at, "close"]
        values[day] = (float(exit_) - float(entry)) / PIP if pd.notna(entry) and pd.notna(exit_) else np.nan
    return pd.Series(values, dtype=float)


def hac_t(values: np.ndarray, lags: int = HAC_LAGS) -> float:
    """t de la media con varianza Newey-West (núcleo de Bartlett)."""

    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan")
    centered = x - x.mean()
    gamma0 = float(centered @ centered) / n
    long_run = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        cov = float(centered[lag:] @ centered[:-lag]) / n
        long_run += 2.0 * (1.0 - lag / (lags + 1.0)) * cov
    if long_run <= 0:
        return float("nan")
    return float(x.mean() / math.sqrt(long_run / n))


@dataclass
class C1Result:
    n_events: int
    n_missing: int
    mean_gross_pips: float
    mean_net_pips: float
    t_hac: float
    halves: dict
    placebo: dict
    verdict: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def evaluate(frame: pd.DataFrame, holidays: set, commission_pips_rt: float) -> C1Result:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    if (index.tz_convert("UTC") >= SEALED_FROM).any():
        raise SealedDataError("los datos incluyen marcas >= 2023-01-01 (OOS-2 sellado)")
    for column in ("ask_open", "close"):
        if column not in frame.columns:
            raise ValueError(f"Sin datos: falta la columna {column} (hace falta BID y ASK)")
    start, end = "2003-01-01", "2022-12-31"
    gotobi = gotobi_days(start, end, holidays)
    gotobi_set = set(gotobi)
    gross = event_returns(frame, gotobi)
    net = gross - float(commission_pips_rt)
    valid = net.dropna()
    t = hac_t(valid.to_numpy())
    halves = {}
    for label, a, b in HALVES:
        part = valid[(valid.index >= pd.Timestamp(a).date()) & (valid.index <= pd.Timestamp(b).date())]
        halves[label] = {"n": int(len(part)), "mean_net_pips": float(part.mean()) if len(part) else None}
    others = [
        day.date()
        for day in pd.bdate_range(start, end)
        if day.date() not in gotobi_set and day.date() not in holidays
    ]
    placebo_net = (event_returns(frame, others) - float(commission_pips_rt)).dropna()
    placebo = {
        "n": int(len(placebo_net)),
        "mean_net_pips": float(placebo_net.mean()) if len(placebo_net) else None,
        "t_hac": hac_t(placebo_net.to_numpy()),
    }
    mean_net = float(valid.mean()) if len(valid) else float("nan")
    signs = [h["mean_net_pips"] for h in halves.values()]
    if not math.isfinite(t) or t < T_CRIT:
        verdict = "rejected"
    elif any(s is None or s <= 0 for s in signs):
        verdict = "inconclusive"
    else:
        verdict = "candidate"
    return C1Result(
        n_events=int(len(valid)),
        n_missing=int(net.isna().sum()),
        mean_gross_pips=float(gross.dropna().mean()) if gross.notna().any() else float("nan"),
        mean_net_pips=mean_net,
        t_hac=t,
        halves=halves,
        placebo=placebo,
        verdict=verdict,
    )


def load_period(cache: Path) -> pd.DataFrame:
    frame = pd.read_parquet(cache)
    frame.columns = [str(c).lower() for c in frame.columns]
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if index.tz is None:
        index = index.tz_localize("UTC")
    frame = frame.set_axis(index.tz_convert("UTC"))
    # Se recorta antes de cualquier cálculo: el tramo sellado no llega a evaluate().
    return frame.loc[(frame.index >= PERIOD_START) & (frame.index < SEALED_FROM), ["ask_open", "close"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", required=True, help="USDJPY_M1.parquet de Dukascopy (con ASK)")
    parser.add_argument("--jp-holidays", required=True, help="CSV oficial de festivos japoneses")
    parser.add_argument("--commission-pips-rt", type=float, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--approved-by-operator", action="store_true")
    args = parser.parse_args(argv)
    if not args.approved_by_operator:
        parser.error("C1 suma +1 al contador de pruebas: requiere --approved-by-operator (AGENTS.md)")
    result = evaluate(load_period(Path(args.cache)), load_jp_holidays(Path(args.jp_holidays)),
                      args.commission_pips_rt)
    Path(args.out).write_text(json.dumps(result.as_dict(), indent=2, default=str), encoding="utf-8")
    print(json.dumps(result.as_dict(), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
