"""Condicionadores causales: flags diarios por fecha y símbolo.

Cada flag marca días con una característica de mercado:

- `pre_fomc`: 24 h antes de una reunión de la FOMC con rueda de prensa (los
  datos vienen de `macro_events`; **sin dato no hay flag** y se avisa).
- `tom_window`: días -5..+3 hábiles alrededor del día delEmployment Report.
- `month_end_selloff`: los 5 días hábiles previos al fin de mes.
- `monday_overnight`: lunes.
- `boundary_extreme`: el precio o el retorno de 20 días están a más de 2
  desviaciones típicas de su propia historia.
- `regime_ok`: el régimen que calcula `regimes.py` es favorable.

**Todo es causal**: para la fecha `t` solo se usan datos hasta `t-1`. Por eso
la estadística y la volatilidad se calculan con la serie desplazada una barra.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CONFIG_DIR
from .db import connect, init_db

FLAGS = (
    "pre_fomc",
    "tom_window",
    "month_end_selloff",
    "monday_overnight",
    "boundary_extreme",
    "regime_ok",
)


def business_days_around(day: date, before: int, after: int) -> list[date]:
    """Días hábiles en la ventana [-before, +after] alrededor de `day`."""
    days: list[date] = []
    current = day
    for _ in range(int(before)):
        current -= timedelta(days=1)
        if current.weekday() < 5:
            days.append(current)
    days.append(day)
    current = day
    for _ in range(int(after)):
        current += timedelta(days=1)
        if current.weekday() < 5:
            days.append(current)
    return sorted(set(days))


def _event_dates(db_path: str | Path, keyword: str) -> tuple[list[date], str | None]:
    """Fechas de eventos que contienen `keyword`. Sin datos: lista vacía."""
    try:
        init_db(db_path)
        with connect(db_path) as con:
            rows = con.execute("SELECT * FROM macro_events").fetchall()
    except Exception as exc:
        return [], f"sin datos de macro_events: {exc}"
    out: list[date] = []
    for row in rows:
        keys = row.keys()
        title = ""
        for key in ("title", "name", "event"):
            if key in keys:
                title = str(row[key] or "")
                break
        if keyword.upper() not in title.upper():
            continue
        raw = None
        for key in ("ts", "event_date", "date", "starts_at"):
            if key in keys:
                raw = row[key]
                break
        if raw is None:
            continue
        text = str(raw)[:10]
        try:
            out.append(datetime.fromisoformat(text).date())
        except ValueError:
            continue
    if not out:
        return [], f"sin datos: no hay eventos con '{keyword}' registrados"
    return sorted(set(out)), None


def fomc_dates(db_path: str | Path) -> tuple[list[date], str | None]:
    """Fechas de la FOMC con rueda de prensa (24 h antes)."""
    dates, error = _event_dates(db_path, "FOMC")
    if error:
        return [], error
    return dates, None


def employment_dates(db_path: str | Path) -> tuple[list[date], str | None]:
    """Fechas del Employment Report (ventana -5..+3 hábiles)."""
    dates, error = _event_dates(db_path, "EMPLOYMENT")
    if error:
        return [], error
    return dates, None


def boundary_flags(close: pd.Series, *, window: int = 252, k: float = 2.0) -> pd.Series:
    """`|precio - SMA252| / desv típica` o `|retorno 20d| / desv típica` > k.

    Causal: la media y la desviación del día `t` usan la serie hasta `t-1`.
    """
    series = pd.Series(close, dtype=float)
    shifted = series.shift(1)
    mean = shifted.rolling(window, min_periods=60).mean()
    std = shifted.rolling(window, min_periods=60).std(ddof=0)
    distance = ((shifted - mean) / std.replace(0.0, np.nan)).abs()
    ret20 = series.pct_change(20).shift(1)
    ret_std = ret20.rolling(window, min_periods=60).std(ddof=0)
    move = (ret20.abs() / ret_std.replace(0.0, np.nan))
    flag = (distance > k) | (move > k)
    return flag.fillna(False).rename("boundary_extreme")


def regime_flags(returns: pd.Series, *, years=(2018, 2020, 2022), min_return: float = 0.0) -> pd.Series:
    """Régimen favorable por día (según `regimes.regime_report`)."""
    try:
        from .regimes import regime_gate, regime_report

        report = regime_report(returns, years=years, min_obs=20)
        gate = regime_gate(report, min_return=min_return)
    except Exception:
        return pd.Series(False, index=returns.index, name="regime_ok")
    ok_years = {
        int(year)
        for year, passed in (gate.get("years") or {}).items()
        if passed
    }
    flags = []
    for stamp in returns.index:
        year = pd.Timestamp(stamp).year
        flags.append(year in ok_years)
    return pd.Series(flags, index=returns.index, name="regime_ok")


def flags_series(
    symbol: str,
    close: pd.Series,
    *,
    db_path: str | Path | None = None,
    fomc: list[date] | None = None,
    employment: list[date] | None = None,
    window: int = 252,
    k: float = 2.0,
) -> tuple[pd.DataFrame, list[str]]:
    """Flags por fecha. Devuelve el frame y la lista de avisos (sin datos)."""
    index = pd.DatetimeIndex(close.index)
    warnings: list[str] = []
    path = Path(db_path) if db_path is not None else None

    if fomc is None:
        if path is None:
            fomc, error = [], "sin datos: no hay base de datos para macro_events"
        else:
            fomc, error = fomc_dates(path)
        if error:
            warnings.append(error)
    if employment is None:
        if path is None:
            employment, error = [], "sin datos: no hay base de datos para macro_events"
        else:
            employment, error = employment_dates(path)
        if error:
            warnings.append(error)

    fomc_days: set[date] = set()
    for event in fomc or []:
        fomc_days.add(event - timedelta(days=1))
    employment_days: set[date] = set()
    for event in employment or []:
        employment_days.update(business_days_around(event, 5, 3))

    rows: list[dict[str, bool]] = []
    for stamp in index:
        day = pd.Timestamp(stamp).date()
        rows.append(
            {
                "pre_fomc": day in fomc_days,
                "tom_window": day in employment_days,
                "month_end_selloff": _month_end_window(day),
                "monday_overnight": day.weekday() == 0,
            }
        )
    frame = pd.DataFrame(rows, index=index)
    frame["boundary_extreme"] = boundary_flags(close, window=window, k=k).to_numpy()
    frame["regime_ok"] = regime_flags(
        pd.Series(close, index=index, dtype=float).pct_change().fillna(0.0)
    ).to_numpy()
    return frame, warnings


def _month_end_window(day: date) -> bool:
    """Los 5 días hábiles previos al fin de mes."""
    probe = day
    count = 0
    for _ in range(12):
        if probe.month != day.month:
            break
        if probe.weekday() < 5:
            count += 1
        probe += timedelta(days=1)
    return count <= 5


def today_flags(symbol: str, *, db_path: str | Path | None = None) -> dict:
    """Flags de la última sesión disponible del símbolo (para la API)."""
    from .config import get_settings
    from .data import fetch

    settings = get_settings()
    path = Path(db_path) if db_path is not None else None
    try:
        df = fetch(symbol, "2020-01-01", "", settings.data.cache_dir)
    except Exception as exc:
        return {"symbol": symbol, "flags": {}, "warnings": [str(exc)[:160]]}
    frame, warnings = flags_series(symbol, df["close"].astype(float), db_path=path)
    if frame.empty:
        return {"symbol": symbol, "flags": {}, "warnings": ["sin datos"]}
    last = frame.iloc[-1]
    return {
        "symbol": symbol,
        "date": str(frame.index[-1].date()),
        "flags": {name: bool(last.get(name, False)) for name in FLAGS},
        "warnings": warnings,
    }


__all__ = [
    "bot_multiplier_table",
    "FLAGS",
    "boundary_flags",
    "business_days_around",
    "employment_dates",
    "flags_series",
    "fomc_dates",
    "regime_flags",
    "today_flags",
]


def bot_multiplier_table(bot_id: str, path: Path | None = None) -> dict[str, float]:
    """Multiplicadores por condicionador de un bot (`config/bots.yaml`).

    La tabla es opcional: si el bot no la tiene, todos los flags valen 1,0.
    """
    file_path = Path(path) if path else CONFIG_DIR / "bots.yaml"
    if not file_path.exists():
        return {}
    try:
        import yaml

        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    for bot in raw.get("bots") or []:
        if str(bot.get("id")) != str(bot_id):
            continue
        table = bot.get("conditioners") or {}
        if not isinstance(table, dict):
            return {}
        out: dict[str, float] = {}
        for flag, value in table.items():
            try:
                out[str(flag)] = float(value)
            except (TypeError, ValueError):
                continue
        return out
    return {}
