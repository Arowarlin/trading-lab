"""Spread histórico por barra a partir del ASK de Dukascopy (T11).

Regla: ``s_t = (ask_t − bid_t) · m_h^bróker / m_h^Dukascopy``, con ``m_h`` la
mediana por hora local en la ventana común más reciente de 90 días.

Si un símbolo no tiene ASK válido, el resultado es **Sin datos** y el llamador
usa la mediana horaria del bróker. Este módulo no descarga nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from ..config import ROOT

DUKASCOPY_DIR = ROOT / "data" / "cache" / "dukascopy"
SNAPSHOT_DIR = ROOT / "data" / "discovery" / "snapshots"
DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True)
class AskAvailability:
    source: str
    symbol: str
    timeframe: str
    rows: int
    ask_rows: int
    first_ask: str | None
    last_ask: str | None

    @property
    def pct(self) -> float:
        return 100.0 * self.ask_rows / self.rows if self.rows else 0.0

    @property
    def status(self) -> str:
        return "OK" if self.ask_rows else "Sin datos"


def _columns(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in frame.columns}


def spread_bps_from_ask(frame: pd.DataFrame) -> pd.Series:
    """Spread en bps por barra: ``(ask_close − close) / close · 1e4``."""

    columns = _columns(frame)
    if "ask_close" not in columns or "close" not in columns:
        raise ValueError("Sin datos: la serie no tiene ask_close")
    ask = pd.to_numeric(frame[columns["ask_close"]], errors="coerce")
    bid = pd.to_numeric(frame[columns["close"]], errors="coerce")
    spread = (ask - bid) / bid * 10_000.0
    spread = spread.where(np.isfinite(spread) & (spread >= 0.0))
    spread.name = "spread_bps"
    return spread


def _infer_timeframe(frame: pd.DataFrame, stem: str) -> str:
    known = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
    parts = stem.split("_")
    if len(parts) >= 2 and parts[1].upper() in known:
        return parts[1].upper()
    if len(frame.index) < 3:
        return ""
    minutes = (
        pd.Series(frame.index).diff().dt.total_seconds().div(60).median()
    )
    mapping = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}
    return mapping.get(int(minutes), f"{int(minutes)}m")


def ask_availability(
    *,
    root: Path = ROOT,
    include_snapshots: bool = True,
) -> list[AskAvailability]:
    """Inventario de ASK válido por archivo; no descarga ni escribe."""

    rows: list[AskAvailability] = []
    roots: list[tuple[str, Path]] = [("dukascopy", root / "data" / "cache" / "dukascopy")]
    if include_snapshots:
        roots.append(("snapshot", root / "data" / "discovery" / "snapshots"))
    for source, directory in roots:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.parquet")):
            try:
                frame = pd.read_parquet(path, columns=None)
            except Exception:  # noqa: BLE001 - archivo ilegible se marca Sin datos
                continue
            columns = _columns(frame)
            symbol = path.stem.split("_")[0]
            timeframe = _infer_timeframe(frame, path.stem)
            if "ask_close" not in columns:
                rows.append(AskAvailability(source, symbol, timeframe, len(frame), 0, None, None))
                continue
            ask = pd.to_numeric(frame[columns["ask_close"]], errors="coerce")
            valid = ask.dropna()
            rows.append(
                AskAvailability(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    rows=len(frame),
                    ask_rows=int(len(valid)),
                    first_ask=(
                        pd.Timestamp(valid.index.min()).isoformat() if len(valid) else None
                    ),
                    last_ask=(
                        pd.Timestamp(valid.index.max()).isoformat() if len(valid) else None
                    ),
                )
            )
    return rows


def load_ask_series(
    symbol: str,
    *,
    root: Path = ROOT,
    directory: Path | None = None,
) -> pd.DataFrame | None:
    """Carga ``close`` y ``ask_close`` del caché M1; ``None`` si no hay ASK."""

    target = (directory or root / "data" / "cache" / "dukascopy") / f"{symbol.upper()}_M1.parquet"
    if not target.exists():
        return None
    try:
        frame = pd.read_parquet(target, columns=["close", "ask_close"])
    except Exception:  # noqa: BLE001
        return None
    if "ask_close" not in frame.columns:
        return None
    frame = frame.loc[pd.to_numeric(frame["ask_close"], errors="coerce").notna()]
    if frame.empty:
        return None
    return frame


def local_hour_medians(
    spread_bps: pd.Series, *, session_tz: str
) -> dict[int, float]:
    values = spread_bps.dropna()
    if values.empty:
        return {}
    hours = values.index.tz_convert(session_tz).hour
    return {
        int(hour): float(group.median())
        for hour, group in values.groupby(hours)
        if np.isfinite(float(group.median()))
    }


def scale_factors(
    dukascopy_median: Mapping[int, float],
    broker_median: Mapping[int, float],
) -> dict[int, float]:
    """``m_h^bróker / m_h^Dukascopy`` por hora local compartida."""

    factors: dict[int, float] = {}
    for hour, value in dukascopy_median.items():
        reference = broker_median.get(int(hour))
        if reference is None:
            continue
        if float(value) > 0.0 and np.isfinite(float(reference)):
            factors[int(hour)] = float(reference) / float(value)
    return factors


def _common_window(
    frame: pd.DataFrame,
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    if start is None or end is None:
        return frame
    first = pd.Timestamp(start)
    last = pd.Timestamp(end)
    if first.tzinfo is None:
        first = first.tz_localize("UTC")
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    return frame.loc[(frame.index >= first) & (frame.index <= last)]


def historical_spread_provider(
    symbol: str,
    *,
    session_tz: str,
    broker_median_by_hour: Mapping[int, float],
    start: str | None = None,
    end: str | None = None,
    root: Path = ROOT,
    directory: Path | None = None,
) -> Callable[[pd.DataFrame], np.ndarray | None]:
    """Devuelve un proveedor ``bars -> spread_bps`` o ``None`` si no hay ASK."""

    cache: dict[int, np.ndarray | None] = {}
    source = load_ask_series(symbol, root=root, directory=directory)
    if source is None:
        return lambda _bars: None
    full_spread = spread_bps_from_ask(source).dropna()
    if full_spread.empty:
        return lambda _bars: None
    window = _common_window(source, start=start, end=end)
    window_spread = spread_bps_from_ask(window).dropna()
    duka_median = local_hour_medians(window_spread, session_tz=session_tz)
    factors = scale_factors(duka_median, broker_median_by_hour)
    if not factors:
        return lambda _bars: None
    fallback = float(np.median(list(factors.values())))
    factor_series = pd.Series(
        [factors.get(int(hour), fallback) for hour in full_spread.index.tz_convert(session_tz).hour],
        index=full_spread.index,
        dtype=float,
    )
    scaled = full_spread * factor_series

    def provider(bars: pd.DataFrame) -> np.ndarray | None:
        key = id(bars)
        if key in cache:
            return cache[key]
        aligned = scaled.reindex(bars.index, method="ffill")
        if aligned.isna().any():
            aligned = aligned.fillna(float(scaled.median()))
        values = aligned.to_numpy(dtype=float)
        cache[key] = values
        return values

    return provider


def choose_spread_model(
    *,
    cost_model_version: int = 1,
    configured: str | None = None,
    has_ask: bool = False,
) -> str:
    """Resuelve ``p75_static`` / ``hourly_median`` / ``historical_scaled``."""

    model = str(configured or "").strip().lower()
    if model in {"hourly_median"}:
        return "hourly_median"
    if model == "historical_scaled":
        return "historical_scaled" if has_ask else "hourly_median"
    if model in {"p75_static", "p75", ""}:
        if int(cost_model_version) >= 2:
            return "historical_scaled" if has_ask else "hourly_median"
        return "p75_static"
    raise ValueError(f"spread_model desconocido: {configured!r}")


_ASK_CACHE: dict[tuple[str, str | None], bool] = {}


def has_historical_ask(symbol: str, *, root: Path = ROOT, directory: Path | None = None) -> bool:
    key = (str(symbol).upper(), str(directory) if directory else None)
    if key not in _ASK_CACHE:
        _ASK_CACHE[key] = load_ask_series(symbol, root=root, directory=directory) is not None
    return _ASK_CACHE[key]


def historical_report(
    *,
    root: Path = ROOT,
    session_tz: str = "America/New_York",
) -> str:
    """Informe Markdown de spread medio y p75 por año, símbolo y hora."""

    lines = [
        "# Spread histórico por barra (T11)",
        "",
        "Fuente: ASK de Dukascopy ya descargado. Solo se usan barras con ASK",
        "válido; el resto se marca **Sin datos**. No se ha descargado nada.",
        "",
        "## Disponibilidad de ASK",
        "",
        "| Fuente | Símbolo | TF | Barras | Con ASK | % | Primera | Última |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    availability = ask_availability(root=root)
    for item in availability:
        lines.append(
            f"| {item.source} | {item.symbol} | {item.timeframe} | {item.rows} | "
            f"{item.ask_rows} | {item.pct:.1f}% | {item.first_ask or 'Sin datos'} | "
            f"{item.last_ask or 'Sin datos'} |"
        )
    lines += [
        "",
        "## Spread por año, símbolo y hora local",
        "",
        "| Símbolo | Año | Hora | n | Medio bps | p75 bps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for path in sorted((root / "data" / "cache" / "dukascopy").glob("*_M1.parquet")):
        symbol = path.stem.split("_")[0]
        frame = load_ask_series(symbol, root=root)
        if frame is None:
            continue
        spread = spread_bps_from_ask(frame).dropna()
        if spread.empty:
            continue
        local = spread.index.tz_convert(session_tz)
        grouped = spread.groupby([local.year, local.hour])
        for (year, hour), values in grouped:
            if len(values) < 30:
                continue
            lines.append(
                f"| {symbol} | {int(year)} | {int(hour):02d} | {len(values)} | "
                f"{float(values.mean()):.3f} | {float(values.quantile(0.75)):.3f} |"
            )
    lines += [
        "",
        "## Criterio",
        "",
        "`s_t = (ask_t − bid_t) · m_h^bróker / m_h^Dukascopy`; `m_h` es la mediana",
        "por hora local en la ventana común más reciente de 90 días. El p75 solo",
        "se usa en los escenarios de estrés (`cost_x1_5` y `spread_p75`).",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "AskAvailability",
    "DEFAULT_WINDOW_DAYS",
    "ask_availability",
    "choose_spread_model",
    "has_historical_ask",
    "historical_report",
    "historical_spread_provider",
    "load_ask_series",
    "local_hour_medians",
    "scale_factors",
    "spread_bps_from_ask",
]
