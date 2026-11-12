"""Campaña de investigación registrada (2026-11-A).

Demo/solo lectura. Este módulo **no activa nada**, no envía órdenes y no toca
`config/*.yaml` de bots. Como mucho registra candidatos en el ciclo de vida.

Cuatro piezas:

1. **Universo por coste** (`build_universe`): spec del bróker, spread mediano por
   hora de las últimas barras H1, comisión de FTMO desde `config/costs.yaml` y
   ATR mediano en H1/H4/D1 (D1 construido desde H4). Un activo es elegible en un
   timeframe si el datacheck no falla y `cost_atr < 0,05`. Sin comisión
   verificada no hay `cost_atr`: queda fuera con "Sin datos". `fetch` re-mide
   la elegibilidad con las velas completas de todos los candidatos, así que
   H1/H4 no se deciden con una muestra corta.
2. **Familias sin unidad de barra** (`family_target`): `tsmom`, `st_reversal`,
   `vol_breakout` y `calendar` se expresan en horas o días y se escalan al
   timeframe con la densidad observada de barras por día de sesión, para que un
   lookback de 20 días signifique lo mismo en H1, H4 y D1.
3. **Registro con una sola pasada** (`register_campaign`): `N_total` se escribe
   **antes** de correr nada y `count_tests` lo suma entero. El holdout se sella
   con un hash del trozo exacto de datos; el hash de la configuración impide
   cambiar la rejilla después de ver resultados. El corte es una fecha común y
   el holdout no baja de dos años: si la serie más corta no los deja, se sacan
   del universo los activos que lo limitan (`trim_for_holdout`).
4. **Descubrimiento, meseta y confirmación** (`run_discovery`, `apply_plateau`,
   `run_holdout`) más el informe con mapas de calor SVG propios.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .config import ROOT
from .db import connect, init_db
from .indicators import atr
from .intraday import BAR_MINUTES, BARS_PER_YEAR, backtest_intraday, cache_file
from .intraday_costs import asset_costs
from .strategies.swing import daily_bars, trading_day
from .trials import record_trial

# ------------------------------------------------------------------ constantes

TIMEFRAMES = ("H1", "H4", "D1")
BAR_HOURS = {tf: minutes / 60.0 for tf, minutes in BAR_MINUTES.items()}

COST_ATR_MAX = 0.05
SLIPPAGE_BPS = 2.0
DISCOVERY_PCT = 0.70

#: El holdout común no puede ser más corto que esto. Si el 70 % de la serie
#: más corta deja menos, se sacan del universo los activos que lo limitan en
#: vez de acortar el holdout de todos.
MIN_HOLDOUT_YEARS = 2.0
#: Series mínimas para que la meseta entre activos (clúster) tenga sentido.
MIN_SERIES = 2
DAYS_PER_YEAR = 365.0

MIN_TRADES = 30
SHARPE_MIN = 0.5
NEIGHBOURS_REQUIRED = 2
CORR_CLUSTER = 0.6
DSR_MIN = 0.90
PBO_MAX = 0.30
MC_KELLY = (0.5, 0.75)

MAX_VARIANTS = 4
INDICES_ONLY = {"calendar"}

#: Barras por defecto del universo. D1 no se descarga: se construye desde H4
#: porque la inferencia de offset por tramos no puede confirmarlo (Etapa 3m).
UNIVERSE_BARS = {"H1": 2_000, "H4": 6_000}

CAMPAIGNS_DIR = ROOT / "config" / "campaigns"
REPORT_DIR = ROOT / "reports" / "research" / "campaign"


class CampaignError(ValueError):
    """Error de configuración o de orden de la campaña."""


#: Las familias se declaran en horas o días. La variante es el eje de parámetro
#: que usa la regla de meseta: las 4 variantes están ordenadas y cada celda
#: tiene como vecinas a las otras tres.
FAMILY_VARIANTS: dict[str, list[dict]] = {
    "tsmom": [
        {"variant": "lb20", "lookback_days": 20.0, "vol_days": 20.0},
        {"variant": "lb60", "lookback_days": 60.0, "vol_days": 20.0},
        {"variant": "lb120", "lookback_days": 120.0, "vol_days": 20.0},
        {"variant": "lb250", "lookback_days": 250.0, "vol_days": 20.0},
    ],
    "st_reversal": [
        {"variant": "hold1", "entry_z": 1.5, "hold_days": 1.0, "lookback_days": 20.0},
        {"variant": "hold2", "entry_z": 1.5, "hold_days": 2.0, "lookback_days": 20.0},
        {"variant": "hold3", "entry_z": 1.5, "hold_days": 3.0, "lookback_days": 20.0},
        {"variant": "hold5", "entry_z": 1.5, "hold_days": 5.0, "lookback_days": 20.0},
    ],
    "vol_breakout": [
        {"variant": "n10", "range_days": 10.0, "atr_ratio": 1.0, "atr_window": 14},
        {"variant": "n20", "range_days": 20.0, "atr_ratio": 1.0, "atr_window": 14},
        {"variant": "n40", "range_days": 40.0, "atr_ratio": 1.0, "atr_window": 14},
        {"variant": "n60", "range_days": 60.0, "atr_ratio": 1.0, "atr_window": 14},
    ],
    "calendar": [
        {"variant": "eom", "kind": "end_of_month", "days": 3},
        {"variant": "dow0", "kind": "day_of_week", "weekday": 0},
        {"variant": "dow2", "kind": "day_of_week", "weekday": 2},
        {"variant": "dow4", "kind": "day_of_week", "weekday": 4},
    ],
}

FAMILIES = tuple(FAMILY_VARIANTS)

FAMILY_HYPOTHESIS = {
    "tsmom": (
        "El retorno de las últimas N sesiones predice el de la siguiente, "
        "escalado por volatilidad."
    ),
    "st_reversal": (
        "Un retorno diario a más de 1,5 desviaciones por debajo de su media "
        "revierte en 1-5 sesiones."
    ),
    "vol_breakout": (
        "Cerrar por encima del máximo de N sesiones con volatilidad por encima "
        "de su mediana continúa el movimiento."
    ),
    "calendar": (
        "El día de la semana y el cierre de mes tienen sesgo en índices cash."
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- escalado


def bars_per_day(timeframe: str) -> float:
    """Barras nominales por día de 24 h en un timeframe."""
    key = str(timeframe).strip().upper()
    try:
        return 24.0 / BAR_HOURS[key]
    except KeyError:
        valid = ", ".join(sorted(BAR_HOURS))
        raise CampaignError(
            f"timeframe desconocido: {timeframe!r}; usa uno de: {valid}"
        ) from None


def bars_for_days(timeframe: str, days: float) -> int:
    """Lookback en días → barras, con el mapa nominal 24 h."""
    return max(1, int(round(float(days) * bars_per_day(timeframe))))


def bars_for_hours(timeframe: str, hours: float) -> int:
    """Lookback en horas → barras."""
    key = str(timeframe).strip().upper()
    if key not in BAR_HOURS:
        raise CampaignError(f"timeframe desconocido: {timeframe!r}")
    return max(1, int(round(float(hours) / BAR_HOURS[key])))


def observed_bars_per_day(frame: pd.DataFrame) -> float:
    """Densidad real de barras por día de sesión del propio marco."""
    index = pd.DatetimeIndex(frame.index)
    if not len(index):
        return 0.0
    sessions = int(index.normalize().nunique())
    return float(len(index)) / float(sessions) if sessions else 0.0


def resolved_bars(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    days: float = 0.0,
    hours: float = 0.0,
) -> int:
    """Barras que ocupan `days`/`hours` en este marco concreto.

    El mapa nominal (24 h/día) vale para EURUSD, pero un índice cash no abre
    24 h. Usar la densidad observada hace que un lookback de 20 días cubra el
    mismo tiempo de reloj en H1, H4 y D1, que es lo que exige comparar la misma
    familia entre timeframes adyacentes.
    """
    if days:
        density = observed_bars_per_day(frame)
        if density > 0.0:
            return max(1, int(round(float(days) * density)))
        return bars_for_days(timeframe, days)
    return bars_for_hours(timeframe, hours)


# ----------------------------------------------------------------- familias


def _require_history(
    frame: pd.DataFrame,
    needed: int,
    *,
    family: str,
    variant: str,
) -> None:
    """Sin histórico suficiente no se inventa una señal plana.

    Devolver ceros en silencio convertiría una celda muerta en una vecina con
    Sharpe 0, que la regla de meseta leería como "no positiva" por una razón
    falsa. Se falla y la celda queda registrada como fallida con el motivo.
    """
    if len(frame) <= needed:
        raise CampaignError(
            f"histórico insuficiente para {family}/{variant}: "
            f"{len(frame)} barras, necesita más de {needed}"
        )


def required_history(
    frame: pd.DataFrame,
    timeframe: str,
    family: str,
    params: dict | None = None,
) -> int:
    """Barras mínimas para que la familia tenga señal causal.

    Es la misma cuenta que usa `_require_history`, expuesta para planificar:
    con el corte común se puede saber antes de correr qué celdas no tienen
    historia y dejarlas fuera del `N_total` en vez de gastar una prueba en un
    fallo garantizado.
    """
    name = str(family).strip().lower()
    values = dict(params or {})
    if name == "tsmom":
        return (
            resolved_bars(frame, timeframe, days=float(values.get("lookback_days", 60.0)))
            + resolved_bars(frame, timeframe, days=float(values.get("vol_days", 20.0)))
            + 1
        )
    if name == "st_reversal":
        return (
            resolved_bars(frame, timeframe, days=float(values.get("lookback_days", 20.0)))
            + resolved_bars(frame, timeframe, days=float(values.get("hold_days", 3.0)))
            + 1
        )
    if name == "vol_breakout":
        return (
            resolved_bars(frame, timeframe, days=float(values.get("range_days", 20.0)))
            + int(values.get("atr_window", 14))
            + 1
        )
    if name == "calendar":
        return 0
    raise CampaignError(f"familia desconocida: {family!r}")


def _tsmom(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    lookback_days: float,
    vol_days: float = 20.0,
) -> pd.Series:
    """Momentum de serie temporal, escalado por volatilidad.

    La escala usa la mediana expansiva de la volatilidad desplazada una barra:
    el objetivo no ve el futuro. Sin desplazar, la mediana de toda la muestra
    sería lookahead.
    """
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    lookback = resolved_bars(frame, timeframe, days=lookback_days)
    vol_bars = resolved_bars(frame, timeframe, days=vol_days)
    _require_history(
        frame,
        required_history(
            frame,
            timeframe,
            "tsmom",
            {"lookback_days": lookback_days, "vol_days": vol_days},
        ),
        family="tsmom",
        variant=f"lb{lookback_days:g}",
    )
    momentum = close / close.shift(lookback) - 1.0
    vol = close.pct_change().rolling(vol_bars, min_periods=vol_bars).std()
    reference = vol.expanding(min_periods=vol_bars).median().shift(1)
    scale = (reference / vol).clip(lower=0.0, upper=1.0)
    signal = (momentum > 0.0).astype(float) * scale.fillna(0.0)
    return signal.clip(0.0, 1.0).fillna(0.0)


def _st_reversal(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    entry_z: float = 1.5,
    hold_days: float,
    lookback_days: float = 20.0,
) -> pd.Series:
    """Reversión: entrar largo tras una caída anómala y salir a los N días."""
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    returns = close.pct_change()
    lookback = resolved_bars(frame, timeframe, days=lookback_days)
    hold = resolved_bars(frame, timeframe, days=hold_days)
    _require_history(
        frame,
        required_history(
            frame,
            timeframe,
            "st_reversal",
            {"lookback_days": lookback_days, "hold_days": hold_days},
        ),
        family="st_reversal",
        variant=f"hold{hold_days:g}",
    )
    mean = returns.rolling(lookback, min_periods=lookback).mean()
    std = returns.rolling(lookback, min_periods=lookback).std()
    z = ((returns - mean) / std.replace(0.0, np.nan)).fillna(0.0)
    trigger = z < -abs(float(entry_z))
    out = np.zeros(len(frame), dtype=float)
    armed_until = -1
    for position in range(len(frame)):
        if position <= armed_until:
            out[position] = 1.0
            continue
        if bool(trigger.iloc[position]):
            armed_until = position + hold - 1
            out[position] = 1.0
    return pd.Series(out, index=frame.index, dtype=float)


def _vol_breakout(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    range_days: float,
    atr_ratio: float = 1.0,
    atr_window: int = 14,
) -> pd.Series:
    """Ruptura del rango de N días con filtro de volatilidad ATR.

    Entra cuando el cierre supera el máximo de las N sesiones previas y el ATR
    está por encima de `atr_ratio` veces su mediana expansiva. Sale cuando el
    cierre pierde el mínimo de la mitad del rango o cuando se cumple el tiempo
    máximo de mantenimiento (`range_days`), para que la familia no degenera en
    comprar y aguantar.
    """
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    span = resolved_bars(frame, timeframe, days=range_days)
    exit_span = max(1, span // 2)
    max_hold = span
    _require_history(
        frame,
        required_history(
            frame,
            timeframe,
            "vol_breakout",
            {"range_days": range_days, "atr_window": atr_window},
        ),
        family="vol_breakout",
        variant=f"n{range_days:g}",
    )
    high = pd.to_numeric(frame["high"], errors="coerce").astype(float)
    low = pd.to_numeric(frame["low"], errors="coerce").astype(float)
    ceiling = high.rolling(span, min_periods=span).max().shift(1)
    floor = low.rolling(exit_span, min_periods=exit_span).min().shift(1)
    volatility = atr(frame, window=int(atr_window))
    reference = volatility.expanding(min_periods=int(atr_window)).median().shift(1)
    enough = volatility >= (float(atr_ratio) * reference)
    enter = (close > ceiling) & enough.fillna(False)
    leave = close < floor
    out = np.zeros(len(frame), dtype=float)
    holding = False
    held = 0
    for position in range(len(frame)):
        if holding:
            held += 1
            if bool(leave.iloc[position]) or held >= max_hold:
                holding = False
                held = 0
        elif bool(enter.iloc[position]):
            holding = True
            held = 0
        out[position] = 1.0 if holding else 0.0
    return pd.Series(out, index=frame.index, dtype=float)


def _calendar(
    frame: pd.DataFrame,
    *,
    kind: str,
    days: int | None = None,
    weekday: int | None = None,
) -> pd.Series:
    """Sesgo de calendario: día de la semana o últimos días del mes.

    El domingo por la noche cuenta como lunes (`trading_day`), igual que en el
    resto del laboratorio.
    """
    index = pd.DatetimeIndex(frame.index)
    if kind == "day_of_week":
        if weekday is None:
            raise CampaignError("day_of_week exige weekday")
        mask = trading_day(index).day_of_week == int(weekday)
        return pd.Series(mask.astype(float), index=frame.index, dtype=float)
    if kind == "end_of_month":
        if not days or int(days) <= 0:
            raise CampaignError("end_of_month exige days > 0")
        sessions = pd.Series(trading_day(index), index=frame.index)
        # Año*100 + mes en vez de Period: `to_period` avisa y descarta la zona.
        month_key = sessions.dt.year * 100 + sessions.dt.month
        order = sessions.groupby(month_key).rank(method="dense", ascending=False)
        mask = order <= int(days)
        return pd.Series(mask.astype(float), index=frame.index, dtype=float)
    raise CampaignError(f"calendario desconocido: {kind!r}")


def family_target(
    frame: pd.DataFrame,
    timeframe: str,
    family: str,
    params: dict | None = None,
) -> pd.Series:
    """Objetivo de exposición (0..1) de una familia en un marco y timeframe.

    La señal se decide al cierre de cada barra; el motor la aplica en la
    siguiente, así que no hay lookahead.
    """
    name = str(family).strip().lower()
    values = dict(params or {})
    if name == "tsmom":
        return _tsmom(
            frame,
            timeframe,
            lookback_days=float(values.get("lookback_days", 60.0)),
            vol_days=float(values.get("vol_days", 20.0)),
        )
    if name == "st_reversal":
        return _st_reversal(
            frame,
            timeframe,
            entry_z=float(values.get("entry_z", 1.5)),
            hold_days=float(values.get("hold_days", 3.0)),
            lookback_days=float(values.get("lookback_days", 20.0)),
        )
    if name == "vol_breakout":
        return _vol_breakout(
            frame,
            timeframe,
            range_days=float(values.get("range_days", 20.0)),
            atr_ratio=float(values.get("atr_ratio", 1.0)),
            atr_window=int(values.get("atr_window", 14)),
        )
    if name == "calendar":
        return _calendar(
            frame,
            kind=str(values.get("kind", "")),
            days=values.get("days"),
            weekday=values.get("weekday"),
        )
    raise CampaignError(f"familia desconocida: {family!r}")


# ------------------------------------------------------------------ universo


#: Grupos del bróker que entran en el universo. Los exóticos, cripto, acciones
#: y agrícolas quedan fuera por diseño.
GROUP_ASSET_CLASS = {
    "Forex": "forex",
    "Metals CFD": "metals",
    "Cash CFD": "indices",
    "Cash II CFD": "indices",
    "Cash III CFD": "indices",
}

ENERGY_HINTS = ("OIL", "NATGAS", "HEATOIL")


def classify_symbol(group: str, name: str) -> str | None:
    """Clase del activo, o None si queda fuera del universo."""
    upper = str(name).upper()
    if any(hint in upper for hint in ENERGY_HINTS):
        return "energy"
    return GROUP_ASSET_CLASS.get(str(group))


def spread_by_hour(frame: pd.DataFrame, point: float) -> pd.Series:
    """Spread mediano por hora en bps del precio (índice 0..23)."""
    if "spread" not in frame.columns:
        return pd.Series(dtype=float)
    close = pd.to_numeric(frame["close"], errors="coerce")
    raw = pd.to_numeric(frame["spread"], errors="coerce").fillna(0.0)
    bps = (
        (raw * float(point) / close * 10_000.0)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    bps = bps[bps >= 0.0]
    if bps.empty:
        return pd.Series(dtype=float)
    return bps.groupby(bps.index.hour).median().sort_index()


def atr_stats(frame: pd.DataFrame, window: int = 14) -> dict:
    """ATR mediano en precio y en bps del precio."""
    if frame.empty:
        return {"atr_price": None, "atr_bps": None, "rows": 0}
    series = atr(frame, window=int(window)).dropna()
    close = pd.to_numeric(frame["close"], errors="coerce")
    price = float(close.median()) if len(close) else 0.0
    if series.empty or price <= 0.0:
        return {"atr_price": None, "atr_bps": None, "rows": int(series.size)}
    median = float(series.median())
    return {
        "atr_price": median,
        "atr_bps": median / price * 10_000.0,
        "rows": int(series.size),
    }


def cost_atr(roundtrip_bps: float | None, atr_bps: float | None) -> float | None:
    """Coste de ida y vuelta expresado en ATR del timeframe.

    Los dos términos son fracciones del precio, así que la razón es
    `roundtrip_bps / atr_bps` y no depende del nivel de precio.
    """
    if roundtrip_bps is None or atr_bps is None:
        return None
    if not np.isfinite(roundtrip_bps) or not np.isfinite(atr_bps) or atr_bps <= 0:
        return None
    return float(roundtrip_bps) / float(atr_bps)


def roundtrip_bps(
    spread_bps: float | None,
    commission_side_bps: float | None,
    slippage_bps: float = SLIPPAGE_BPS,
) -> float | None:
    """Coste de ida y vuelta: 1 spread + 2 slippage + 2 comisiones de lado."""
    if spread_bps is None or commission_side_bps is None:
        return None
    return (
        float(spread_bps)
        + 2.0 * float(slippage_bps)
        + 2.0 * float(commission_side_bps)
    )


def _check_status(frame: pd.DataFrame, symbol: str, timeframe: str, path: Path) -> dict:
    from .datacheck import check_frame

    label = {"H1": "1h", "H4": "4h", "D1": "1d"}.get(timeframe, timeframe.lower())
    try:
        result = check_frame(frame, symbol, timeframe=label, cache_path=path)
    except Exception as exc:  # el datacheck nunca debe tumbar el universo
        return {"status": "falla", "reasons": [f"datacheck no ejecutable: {exc}"]}
    return {
        "status": result.get("status", "falla"),
        "reasons": list(result.get("reasons") or []),
    }


def _commission_side_bps(symbol: str, frame: pd.DataFrame) -> dict:
    """Comisión por lado en bps.

    Distingue dos cosas que no son lo mismo:

    - `verified`: la comisión está en `config/costs.yaml` con fuente y fecha.
    - `convertible`: además se puede pasar a bps con el precio del propio marco.

    Un cruce sin USD (AUDCAD, EURGBP...) cobra 2,50 USD por lote, pero su
    nocional está en la divisa cotizada: para pasar a bps haría falta el tipo
    de cambio de esa divisa a USD, que aquí no se inventa. Queda `verified`
    pero **no convertible**, y sin `cost_atr` no es elegible.
    """
    cost = asset_costs(symbol)
    if not cost.verified:
        return {
            "verified": False,
            "convertible": False,
            "commission_side_bps": None,
            "note": "Sin datos: comisión FTMO no verificada en config/costs.yaml",
        }
    base = {
        "verified": True,
        "convertible": False,
        "commission_side_bps": None,
        "commission_type": cost.commission_type,
        "source": cost.source,
        "source_date": cost.source_date,
        "effective_from": cost.effective_from,
        "source_url": cost.source_url,
    }
    try:
        series = cost.commission_bps(
            pd.to_numeric(frame["close"], errors="coerce").astype(float)
        )
        value = float(series.median())
    except Exception as exc:
        return {
            **base,
            "note": f"Sin datos: comisión verificada pero no convertible a bps ({exc})",
        }
    return {**base, "convertible": True, "commission_side_bps": value, "note": ""}


def build_universe(
    broker,
    *,
    bars: dict | None = None,
    cache_dir: str | Path | None = None,
    save: bool = True,
) -> dict:
    """Mide el universo y devuelve la tabla completa.

    Solo lectura: pide velas al terminal, calcula spread y ATR y lee la
    comisión del catálogo. No calcula retornos de estrategia.
    """
    sizes = dict(UNIVERSE_BARS)
    sizes.update(bars or {})
    target_dir = Path(cache_dir) if cache_dir else (ROOT / "data" / "cache")

    rows = broker.symbols() if hasattr(broker, "symbols") else []
    if not rows:
        raise CampaignError("el bróker no devolvió símbolos")

    entries: list[dict] = []
    for item in rows:
        name = str(item.get("symbol") or item.get("name") or "").strip()
        group = str(item.get("group") or "").strip()
        asset_class = classify_symbol(group, name)
        if not name or asset_class is None:
            continue
        entries.append({"mt5_name": name, "group": group, "asset_class": asset_class})

    entries.sort(key=lambda row: (row["asset_class"], row["mt5_name"]))
    symbols: list[dict] = []
    for entry in entries:
        symbols.append(
            _measure_symbol(
                broker,
                entry,
                sizes=sizes,
                cache_dir=target_dir,
                save=save,
            )
        )

    eligible = {tf: [] for tf in TIMEFRAMES}
    for row in symbols:
        for tf in TIMEFRAMES:
            if row["eligible"].get(tf):
                eligible[tf].append(row["symbol"])

    universe = {
        "campaign": "2026-11-A",
        "generated_at": _now(),
        "source": "MT5 FTMO-Demo (solo lectura)",
        "bars": {
            "H1": int(sizes["H1"]),
            "H4": int(sizes["H4"]),
            "D1": "construido desde H4 (daily_bars)",
        },
        "thresholds": {
            "cost_atr_max": COST_ATR_MAX,
            "slippage_bps": SLIPPAGE_BPS,
            "commission": "config/costs.yaml (Sin datos si no verificada)",
        },
        "counts": {
            "measured": len(symbols),
            "verified_commission": sum(
                1 for row in symbols if row["commission"]["verified"]
            ),
            "convertible_commission": sum(
                1 for row in symbols if row["commission"].get("convertible")
            ),
            "eligible": {tf: len(eligible[tf]) for tf in TIMEFRAMES},
        },
        "eligible_by_timeframe": eligible,
        "symbols": symbols,
    }
    return universe


def _apply_measurements(
    row: dict,
    frames: dict[str, pd.DataFrame],
    paths: dict[str, Path],
    point: float,
) -> dict:
    """Mide spread, ATR, datacheck y coste sobre unos marcos ya descargados.

    La usan tanto la medición del universo (velas cortas) como la
    re-medición del `fetch` (velas completas). Así la elegibilidad de H1/H4 no
    depende de cuántas barras se pidieron en la primera pasada.
    """
    key = str(row["symbol"]).upper()
    row["spread_bps_median"] = None
    row["spread_bps_by_hour"] = {}
    row.pop("spread_source", None)
    row["atr"] = {}
    row["cost_atr"] = {}
    row["datacheck"] = {}
    row["eligible"] = {}
    for tf in TIMEFRAMES:
        row["reason"].pop(tf, None)
    row["reason"].pop("spread", None)

    for source in ("H1", "H4"):
        frame = frames.get(source)
        if frame is None or frame.empty:
            continue
        hourly = spread_by_hour(frame, point)
        if len(hourly):
            row["spread_bps_median"] = float(hourly.median())
            row["spread_bps_by_hour"] = {
                str(int(hour)): float(value) for hour, value in hourly.items()
            }
            row["spread_source"] = source
            break
    else:
        row["reason"]["spread"] = "Sin datos: ni H1 ni H4 traen spread"

    commission: dict | None = None
    for tf in TIMEFRAMES:
        frame = frames.get(tf)
        if frame is None or frame.empty:
            row["datacheck"][tf] = {"status": "Sin datos", "reasons": []}
            row["atr"][tf] = {"atr_price": None, "atr_bps": None, "rows": 0}
            row["cost_atr"][tf] = None
            row["eligible"][tf] = False
            row["reason"].setdefault(tf, "Sin datos: sin velas")
            continue
        row["datacheck"][tf] = _check_status(frame, key, tf, paths.get(tf, Path(".")))
        row["atr"][tf] = atr_stats(frame)
        if commission is None:
            commission = _commission_side_bps(key, frame)
    if commission is None:
        commission = {
            "verified": False,
            "convertible": False,
            "commission_side_bps": None,
            "note": "Sin datos: sin velas para convertir la comisión",
        }
    row["commission"] = commission

    for tf in TIMEFRAMES:
        atr_bps = row["atr"].get(tf, {}).get("atr_bps")
        total = roundtrip_bps(
            row["spread_bps_median"], commission.get("commission_side_bps")
        )
        ratio = cost_atr(total, atr_bps)
        row["cost_atr"][tf] = ratio
        check = row["datacheck"].get(tf, {}).get("status")
        if not commission.get("verified"):
            row["eligible"][tf] = False
            row["reason"][tf] = "Sin datos: comisión FTMO no verificada"
        elif not commission.get("convertible"):
            row["eligible"][tf] = False
            row["reason"][tf] = str(
                commission.get("note") or "Sin datos: comisión no convertible a bps"
            )
        elif check in (None, "Sin datos"):
            row["eligible"][tf] = False
            row["reason"][tf] = "Sin datos: sin datacheck"
        elif check == "falla":
            row["eligible"][tf] = False
            row["reason"][tf] = "datacheck falla: " + "; ".join(
                row["datacheck"][tf].get("reasons") or []
            )[:160]
        elif ratio is None:
            row["eligible"][tf] = False
            row["reason"][tf] = "Sin datos: cost_atr no calculable"
        elif ratio >= COST_ATR_MAX:
            row["eligible"][tf] = False
            row["reason"][tf] = f"cost_atr {ratio:.4f} >= {COST_ATR_MAX}"
        else:
            row["eligible"][tf] = True
            row["reason"][tf] = f"cost_atr {ratio:.4f} < {COST_ATR_MAX}"
    return row


def _measure_symbol(
    broker,
    entry: dict,
    *,
    sizes: dict,
    cache_dir: Path,
    save: bool,
) -> dict:
    name = entry["mt5_name"]
    key = name.upper()
    row: dict = {
        "symbol": key,
        "mt5_name": name,
        "group": entry["group"],
        "asset_class": entry["asset_class"],
        "spec": {},
        "commission": {"verified": False, "convertible": False, "commission_side_bps": None},
        "spread_bps_median": None,
        "spread_bps_by_hour": {},
        "atr": {},
        "cost_atr": {},
        "datacheck": {},
        "eligible": {},
        "reason": {},
    }
    try:
        spec = broker.symbol_spec(name)
        row["spec"] = {
            "tick_size": spec.get("tick_size"),
            "contract_size": spec.get("contract_size"),
            "volume_min": spec.get("volume_min"),
            "digits": spec.get("digits"),
        }
        point = float(spec.get("tick_size") or spec.get("point") or 0.01)
    except Exception as exc:
        row["reason"]["spec"] = f"Sin datos: {exc}"
        point = 0.01

    frames: dict[str, pd.DataFrame] = {}
    paths: dict[str, Path] = {}
    for tf in ("H1", "H4"):
        path = cache_file(cache_dir, key, tf)
        try:
            frame = broker.rates(name, tf, int(sizes[tf]))
            if frame is None or frame.empty:
                row["reason"][tf] = "Sin datos: sin velas"
                continue
            if save:
                from .intraday import save_bars

                path = save_bars(frame, cache_dir, key, tf)
            frames[tf] = frame
            paths[tf] = path
        except Exception as exc:
            row["reason"][tf] = f"Sin datos: {exc}"
    if "H4" in frames:
        try:
            frames["D1"] = daily_bars(frames["H4"])
            paths["D1"] = paths["H4"]
        except Exception as exc:
            row["reason"]["D1"] = f"Sin datos: {exc}"
    return _apply_measurements(row, frames, paths, point)


# ------------------------------------------------- re-medición con velas completas


def universe_symbols(universe: dict) -> list[str]:
    """Todos los activos medidos del universo (candidatos), elegibles o no.

    `lab campaign fetch` descarga H1/H4 de esta lista completa: la elegibilidad
    de un timeframe no puede decidir qué datos se descargan para medirla. La
    energía queda fuera por diseño (no tiene comisión FTMO verificada), igual
    que en `GROUP_ASSET_CLASS`.
    """
    classes = set(GROUP_ASSET_CLASS.values())
    return sorted(
        {
            str(row["symbol"]).upper()
            for row in universe.get("symbols") or []
            if row.get("symbol") and str(row.get("asset_class") or "") in classes
        }
    )


def campaign_symbols(universe: dict) -> list[str]:
    """Activos que finalmente entran en alguna celda de la campaña."""
    return sorted(
        {
            str(name).upper()
            for timeframe in TIMEFRAMES
            for name in (universe.get("eligible_by_timeframe") or {}).get(timeframe) or []
        }
    )


def refresh_universe_eligibility(universe: dict) -> dict:
    """Reconstruye `eligible_by_timeframe` y los contadores desde las filas."""
    eligible: dict[str, list[str]] = {tf: [] for tf in TIMEFRAMES}
    for row in universe.get("symbols") or []:
        for timeframe in TIMEFRAMES:
            if (row.get("eligible") or {}).get(timeframe):
                eligible[timeframe].append(str(row["symbol"]).upper())
    universe["eligible_by_timeframe"] = eligible
    counts = universe.setdefault("counts", {})
    counts["eligible"] = {tf: len(eligible[tf]) for tf in TIMEFRAMES}
    counts["verified_commission"] = sum(
        1
        for row in universe.get("symbols") or []
        if (row.get("commission") or {}).get("verified")
    )
    counts["convertible_commission"] = sum(
        1
        for row in universe.get("symbols") or []
        if (row.get("commission") or {}).get("convertible")
    )
    universe["campaign_symbols"] = campaign_symbols(universe)
    return universe


def reassess_universe(
    universe: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
    *,
    cache_dir: str | Path | None = None,
) -> dict:
    """Vuelve a medir la elegibilidad con las velas completas del `fetch`.

    Rompe el círculo del universo: `lab campaign universe` mide con pocas
    barras y `lab campaign fetch` descarga el máximo de H1/H4 para todos los
    candidatos; aquí se recalculan spread, ATR, datacheck y `cost_atr` con esas
    velas antes de decidir qué es elegible.
    """
    target_dir = Path(cache_dir) if cache_dir else (ROOT / "data" / "cache")
    rows: list[dict] = []
    for row in universe.get("symbols") or []:
        symbol = str(row["symbol"]).upper()
        spec = row.get("spec") or {}
        point = float(spec.get("tick_size") or 0.01)
        symbol_frames = {
            timeframe: frames[(symbol, timeframe)]
            for timeframe in TIMEFRAMES
            if (symbol, timeframe) in frames
            and frames[(symbol, timeframe)] is not None
            and not frames[(symbol, timeframe)].empty
        }
        paths = {
            timeframe: cache_file(target_dir, symbol, timeframe)
            for timeframe in symbol_frames
        }
        if "D1" in symbol_frames:
            paths["D1"] = paths.get("H4", cache_file(target_dir, symbol, "H4"))
        _apply_measurements(row, symbol_frames, paths, point)
        rows.append(row)
    universe["symbols"] = rows
    return refresh_universe_eligibility(universe)


def write_universe(universe: dict, out_dir: str | Path | None = None) -> dict:
    """Escribe `universe.md` y `universe.json`."""
    target = Path(out_dir) if out_dir else REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "universe.json"
    md_path = target / "universe.md"
    json_path.write_text(
        json.dumps(universe, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_universe(universe), encoding="utf-8")
    return {"md": str(md_path), "json": str(json_path)}


def _fmt(value, digits: int = 4, suffix: str = "") -> str:
    if value is None:
        return "Sin datos"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return "Sin datos"
    return f"{number:.{digits}f}{suffix}"


def render_universe(universe: dict) -> str:
    counts = universe.get("counts") or {}
    eligible = universe.get("eligible_by_timeframe") or {}
    lines = [
        "# Universo por coste — campaña 2026-11-A",
        "",
        f"- Generado: {universe.get('generated_at')}",
        f"- Fuente: {universe.get('source')}",
        f"- Barras: H1 {universe['bars']['H1']:,} · H4 {universe['bars']['H4']:,} · "
        f"D1 {universe['bars']['D1']}",
        f"- Umbral: `cost_atr < {universe['thresholds']['cost_atr_max']}` · "
        f"slippage {universe['thresholds']['slippage_bps']} bps por lado",
        f"- Activos medidos: **{counts.get('measured', 0)}** · "
        f"con comisión verificada: **{counts.get('verified_commission', 0)}** · "
        f"convertible a bps: **{counts.get('convertible_commission', 0)}**",
        "",
        "## Elegibles por timeframe",
        "",
        "| Timeframe | Elegibles | Activos |",
        "|---|---|---|",
    ]
    for tf in TIMEFRAMES:
        names = eligible.get(tf) or []
        lines.append(
            f"| {tf} | {len(names)} | {', '.join(names) if names else 'Sin datos'} |"
        )
    plan = universe.get("plan") or {}
    if plan:
        excluded = plan.get("excluded") or []
        excluded_assets = plan.get("excluded_assets") or []
        lines += [
            "",
            "## Corte común y celdas",
            "",
            f"- Fecha de corte común: **{plan.get('cutoff_utc')}**",
            f"- Holdout común: **{_fmt(plan.get('holdout_years'), 2)} años** "
            f"(mínimo exigido: {_fmt(plan.get('min_holdout_years', 2.0), 1)} años)",
            f"- `N_total` con historia suficiente: **{plan.get('n_total')}** "
            f"({plan.get('per_timeframe')})",
            f"- Celdas excluidas por historia: **{len(excluded)}**",
            "",
            "## Activos excluidos por holdout corto",
            "",
        ]
        if excluded_assets:
            lines += [
                "| Activo | Serie limitante | Barras | Inicio | Fin | Holdout antes | Motivo |",
                "|---|---|---|---|---|---|---|",
            ]
            for item in excluded_assets:
                lines.append(
                    "| {symbol} | {tf} | {rows} | {start} | {end} | {years} años | {why} |".format(
                        symbol=item.get("symbol"),
                        tf=item.get("timeframe", "Sin datos"),
                        rows=item.get("rows", "Sin datos"),
                        start=str(item.get("start") or "Sin datos")[:10],
                        end=str(item.get("end") or "Sin datos")[:10],
                        years=_fmt(item.get("holdout_years_before"), 2),
                        why=item.get("reason") or "Sin datos",
                    )
                )
        else:
            lines.append(
                "Ninguno: todas las series elegibles dejan un holdout común de "
                "al menos dos años."
            )
        lines += [""]
        if excluded:
            lines += [
                "### Celdas excluidas por historia",
                "",
                "| Activo | TF | Familia | Variante | Descubrimiento | Necesita | Motivo |",
                "|---|---|---|---|---|---|---|",
            ]
            for cell in excluded:
                lines.append(
                    "| {symbol} | {tf} | {family} | {variant} | {disc} | {need} | {why} |".format(
                        symbol=cell.get("symbol"),
                        tf=cell.get("timeframe"),
                        family=cell.get("family"),
                        variant=cell.get("variant"),
                        disc=cell.get("discovery_rows", "Sin datos"),
                        need=cell.get("needed", "Sin datos"),
                        why=cell.get("reason"),
                    )
                )
            lines.append("")
        series = universe.get("series") or []
        if series:
            lines += [
                "### Series y reparto",
                "",
                "| Activo | TF | Barras | Inicio | Fin | Descubrimiento | Holdout |",
                "|---|---|---|---|---|---|---|",
            ]
            for item in series:
                lines.append(
                    "| {symbol} | {tf} | {rows} | {start} | {end} | {disc} | {hold} |".format(
                        symbol=item["symbol"],
                        tf=item["timeframe"],
                        rows=item["rows"],
                        start=str(item["start"])[:10],
                        end=str(item["end"])[:10],
                        disc=item["discovery_rows"],
                        hold=item["holdout_rows"],
                    )
                )
            lines.append("")
    lines += [
        "",
        "Elegible = datacheck distinto de `falla` **y** `cost_atr < 0,05`. "
        "Sin comisión verificada en `config/costs.yaml` no hay `cost_atr`: "
        "el activo queda fuera con **Sin datos**.",
        "",
        "## Tabla completa",
        "",
        "| Activo | Clase | Tick | Contrato | Vol. mín | Spread bps | Comisión | "
        "ATR H1 | ATR H4 | ATR D1 | cost_atr H1 | cost_atr H4 | cost_atr D1 | "
        "Elegible H1 | H4 | D1 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in universe.get("symbols") or []:
        spec = row.get("spec") or {}
        commission = row.get("commission") or {}
        atrs = row.get("atr") or {}
        ratios = row.get("cost_atr") or {}
        flags = row.get("eligible") or {}
        if commission.get("convertible"):
            commission_text = _fmt(commission.get("commission_side_bps"), 3, " bps/lado")
        elif commission.get("verified"):
            commission_text = "Sin datos (no convertible)"
        else:
            commission_text = "Sin datos"
        lines.append(
            "| {symbol} | {cls} | {tick} | {contract} | {vol} | {spread} | "
            "{commission} | {a1} | {a4} | {ad} | {c1} | {c4} | {cd} | "
            "{e1} | {e4} | {ed} |".format(
                symbol=row.get("symbol"),
                cls=row.get("asset_class"),
                tick=_fmt(spec.get("tick_size"), 5),
                contract=_fmt(spec.get("contract_size"), 0),
                vol=_fmt(spec.get("volume_min"), 2),
                spread=_fmt(row.get("spread_bps_median"), 3),
                commission=commission_text,
                a1=_fmt((atrs.get("H1") or {}).get("atr_bps"), 1),
                a4=_fmt((atrs.get("H4") or {}).get("atr_bps"), 1),
                ad=_fmt((atrs.get("D1") or {}).get("atr_bps"), 1),
                c1=_fmt(ratios.get("H1"), 4),
                c4=_fmt(ratios.get("H4"), 4),
                cd=_fmt(ratios.get("D1"), 4),
                e1="sí" if flags.get("H1") else "no",
                e4="sí" if flags.get("H4") else "no",
                ed="sí" if flags.get("D1") else "no",
            )
        )
    lines += [
        "",
        "## Por qué quedan fuera los demás",
        "",
        "`config/costs.yaml` cubre los 51 símbolos de los grupos MT5 Forex (28), "
        "Metals CFD (9) y Cash CFD / Cash II CFD / Cash III CFD (14 índices), "
        "cada uno con su fuente y fecha. Quedan fuera, con **Sin datos**:",
        "",
        "- **Exóticos, cripto, acciones y agrícolas**: no están en la tabla de "
        "costes y no se les supone comisión.",
        "- **Commodities y energía** (`USOIL.CASH`, `UKOIL.CASH`, `NATGAS.CASH`, "
        "`HEATOIL.C`) aunque MT5 los agrupe en Cash II/Commodities: son energía, "
        "no índices.",
        "- **Cruces sin USD** (AUDCAD, EURGBP, GBPJPY...): la comisión está "
        "verificada (2,50 USD/lote/lado) pero el nocional está en la divisa "
        "cotizada y pasar a bps exige un tipo de cambio que aquí no se inventa. "
        "Quedan marcados como *verificada pero no convertible*.",
        "",
        "El spread y el slippage no vienen de la tabla: el spread es la mediana "
        "por hora de las velas H1 y el slippage es el supuesto conservador de "
        "2 bps por lado.",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------- registro y N_total


def init_campaigns(db_path: str | Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL UNIQUE,
                registered_at TEXT NOT NULL,
                n_total INTEGER NOT NULL,
                discovery_pct REAL NOT NULL,
                config_hash TEXT NOT NULL,
                holdout_hash TEXT,
                run_id TEXT,
                started_at TEXT,
                finished_at TEXT,
                note TEXT
            )
            """
        )
        con.commit()


def variants_for(family: str) -> list[dict]:
    try:
        return list(FAMILY_VARIANTS[str(family).strip().lower()])
    except KeyError:
        raise CampaignError(f"familia desconocida: {family!r}") from None


def applies_to(family: str, asset_class: str) -> bool:
    """`calendar` solo se prueba en índices cash."""
    name = str(family).strip().lower()
    if name in INDICES_ONLY:
        return str(asset_class).strip().lower() == "indices"
    return True


def compute_n_total(universe: dict) -> dict:
    """`N_total` exacto antes de correr nada.

    Suma, por timeframe, los activos elegibles en ese timeframe por las familias
    que aplican a su clase y las variantes de cada familia. `calendar` no cuenta
    para activos que no son índices porque no se llega a probar.
    """
    by_symbol = {
        str(row["symbol"]).upper(): row for row in universe.get("symbols") or []
    }
    eligible = universe.get("eligible_by_timeframe") or {}
    per_timeframe: dict[str, int] = {}
    detail: dict[str, list[dict]] = {}
    for tf in TIMEFRAMES:
        cells = 0
        rows: list[dict] = []
        for name in eligible.get(tf) or []:
            row = by_symbol.get(str(name).upper())
            if row is None:
                continue
            asset_class = str(row.get("asset_class") or "")
            families = [
                family for family in FAMILIES if applies_to(family, asset_class)
            ]
            variants = sum(len(variants_for(family)) for family in families)
            cells += variants
            rows.append(
                {
                    "symbol": str(name).upper(),
                    "asset_class": asset_class,
                    "families": families,
                    "variants": variants,
                }
            )
        per_timeframe[tf] = cells
        detail[tf] = rows
    return {
        "n_total": int(sum(per_timeframe.values())),
        "per_timeframe": per_timeframe,
        "detail": detail,
        "assets": {
            tf: len(eligible.get(tf) or []) for tf in TIMEFRAMES
        },
        "families": list(FAMILIES),
        "variants_per_family": {
            family: len(variants_for(family)) for family in FAMILIES
        },
    }


def campaign_config(universe: dict, campaign: str, *,
                    skip_adjacent_if_empty: bool = False) -> dict:
    """Configuración de la campaña a partir del universo final y su plan.

    No registra nada: la misma función alimenta `lab campaign plan` (escribe el
    yaml) y `lab campaign register` (sellaría), para que no puedan divergir.
    """
    plan = universe.get("plan") or {}
    if not plan:
        raise CampaignError(
            "falta el plan con el corte común: corre antes `lab campaign fetch`."
        )
    symbols = campaign_symbols(universe)
    if not symbols:
        raise CampaignError("sin activos elegibles: no hay nada que planificar")
    totals = compute_n_total(universe)
    symbol_set = set(symbols)
    broker_names = {
        str(row["symbol"]).upper(): str(row.get("mt5_name") or row["symbol"])
        for row in universe.get("symbols") or []
        if str(row["symbol"]).upper() in symbol_set
    }
    # Elegibilidad y clase por timeframe: el descubrimiento corre **solo** las
    # celdas que entraron en `N_total`. Sin esto correría H1/H4 aunque no
    # tengan activos elegibles y el denominador del DSR quedaría desalineado.
    eligible_by_timeframe = {
        str(timeframe).upper(): [str(name).upper() for name in (names or [])]
        for timeframe, names in (universe.get("eligible_by_timeframe") or {}).items()
    }
    asset_classes = {
        str(row["symbol"]).upper(): str(row.get("asset_class") or "")
        for row in universe.get("symbols") or []
        if str(row["symbol"]).upper() in symbol_set
    }
    excluded_assets = [
        str(item.get("symbol")).upper()
        for item in (plan.get("excluded_assets") or universe.get("excluded_assets") or [])
        if item.get("symbol")
    ]
    config = {
        "id": campaign,
        "universe": symbols,
        "mt5_names": broker_names,
        "timeframes": ["H1", "H4", "D1"],
        "families": list(FAMILIES),
        "variants_per_family": {
            family: len(variants_for(family)) for family in FAMILIES
        },
        "eligible_by_timeframe": eligible_by_timeframe,
        "asset_classes": asset_classes,
        "discovery_pct": float(DISCOVERY_PCT),
        "holdout_pct": float(round(1.0 - DISCOVERY_PCT, 2)),
        "cutoff_utc": plan.get("cutoff_utc"),
        "n_total": int(plan.get("n_total") or 0),
        "n_total_detail": dict(plan.get("per_timeframe") or {}),
        "n_total_theoretical": int(totals["n_total"]),
        "holdout_years": round(float(plan.get("holdout_years") or 0.0), 4),
        "min_holdout_years": float(
            plan.get("min_holdout_years", MIN_HOLDOUT_YEARS)
        ),
        "excluded_assets": excluded_assets,
        "holdout_hash": plan.get("holdout_hash"),
        "holdout_series": list(plan.get("holdout_series") or []),
        "excluded_cells": len(plan.get("excluded") or []),
        "plateau": (
            {"skip_adjacent_if_empty": True}
            if skip_adjacent_if_empty else {}
        ),
    }
    if config["n_total"] <= 0:
        raise CampaignError(
            "N_total es 0 con el corte común: no hay celdas con historia suficiente"
        )
    per_timeframe_total = sum(
        int(value) for value in (config["n_total_detail"] or {}).values()
    )
    if per_timeframe_total != config["n_total"]:
        raise CampaignError(
            "N_total no cuadra con el detalle por timeframe: "
            f"{config['n_total']} != {per_timeframe_total}"
        )
    config["config_hash"] = campaign_hash(config)
    return config


def campaign_hash(config: dict) -> str:
    """Huella de la rejilla. Cambiar algo cambia el hash y rompe el sello."""
    payload = {
        "id": config.get("id"),
        "universe": sorted(str(s).upper() for s in config.get("universe") or []),
        "timeframes": list(config.get("timeframes") or TIMEFRAMES),
        "families": {
            str(family): variants_for(family)
            for family in (config.get("families") or FAMILIES)
        },
        "discovery_pct": float(config.get("discovery_pct", DISCOVERY_PCT)),
        "cutoff_utc": config.get("cutoff_utc"),
        "n_total": int(config.get("n_total") or 0),
    }
    if config.get("plateau"):
        payload["plateau"] = config["plateau"]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def holdout_hash(rows: list[dict], cutoff: pd.Timestamp | str | None = None) -> str:
    """Huella del trozo exacto de datos sellado.

    Incluye la fecha de corte común: cambiar el corte cambia el hash y rompe el
    sello, aunque el número de filas coincida.
    """
    clean = sorted(
        (
            {
                "symbol": str(row["symbol"]).upper(),
                "timeframe": str(row["timeframe"]).upper(),
                "start": str(row["start"]),
                "end": str(row["end"]),
                "rows": int(row["rows"]),
            }
            for row in rows
        ),
        key=lambda item: (item["symbol"], item["timeframe"]),
    )
    payload = {
        "cutoff_utc": None if cutoff is None else str(_stamp(cutoff)),
        "series": clean,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def register_campaign(
    db_path: str | Path,
    config: dict,
    *,
    note: str = "",
) -> dict:
    """Registra la campaña una sola vez y fija `N_total` en `count_tests`."""
    init_campaigns(db_path)
    campaign_id = str(config.get("id") or "").strip()
    if not campaign_id:
        raise CampaignError("la campaña necesita id")
    n_total = int(config.get("n_total") or 0)
    if n_total <= 0:
        raise CampaignError("N_total debe ser > 0 y calcularse antes de registrar")
    digest = campaign_hash(config)
    with connect(db_path) as con:
        existing = con.execute(
            "SELECT * FROM campaign_registry WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        if existing is not None:
            raise CampaignError(
                f"la campaña {campaign_id} ya está registrada: solo se corre una vez"
            )
        con.execute(
            "INSERT INTO campaign_registry"
            "(campaign_id, registered_at, n_total, discovery_pct, config_hash,"
            " holdout_hash, note) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                campaign_id,
                _now(),
                n_total,
                float(config.get("discovery_pct", DISCOVERY_PCT)),
                digest,
                config.get("holdout_hash"),
                str(note or "")[:2000],
            ),
        )
        con.commit()
        row = con.execute(
            "SELECT * FROM campaign_registry WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
    return dict(row)


def finish_campaign(db_path: str | Path, campaign_id: str) -> dict:
    """Marca la campaña como terminada. Solo una vez, tras escribir el informe."""
    init_campaigns(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM campaign_registry WHERE campaign_id = ?",
            (str(campaign_id),),
        ).fetchone()
        if row is None:
            raise CampaignError(f"la campaña {campaign_id} no está registrada")
        if row["finished_at"]:
            raise CampaignError(
                f"la campaña {campaign_id} ya terminó el {row['finished_at']}"
            )
        con.execute(
            "UPDATE campaign_registry SET finished_at = ? WHERE campaign_id = ?",
            (_now(), str(campaign_id)),
        )
        con.commit()
        row = con.execute(
            "SELECT * FROM campaign_registry WHERE campaign_id = ?",
            (str(campaign_id),),
        ).fetchone()
    return dict(row)


def load_campaign(db_path: str | Path, campaign_id: str) -> dict:
    init_campaigns(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM campaign_registry WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
    if row is None:
        raise CampaignError(f"campaña no registrada: {campaign_id}")
    return dict(row)


def load_campaign_yaml(path: str | Path) -> dict:
    target = Path(path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CampaignError(f"configuración inválida: {target}")
    return data


# --------------------------------------------------------------- particiones


def _stamp(value) -> pd.Timestamp:
    """Timestamp UTC comparable, venga naive o con zona."""
    stamp = pd.Timestamp(value)
    if stamp.tz is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def common_cutoff(
    frames: dict[tuple[str, str], pd.DataFrame],
    discovery_pct: float = DISCOVERY_PCT,
) -> pd.Timestamp | None:
    """Fecha de corte única: el 70 % de la serie **más corta**.

    Se elige la serie con menos barras (la que antes se queda sin historia) y
    se toma la fecha de su punto `discovery_pct`. Esa fecha deja el 30 % final
    de esa serie para el holdout y vale para todas: la meseta entre activos
    solo puede mirar datos anteriores a ella.

    Las series con más barras conservan un holdout distinto (puede ser menor
    del 30 % en barras): el corte es una fecha común, no una fracción común.
    """
    candidates = [
        (len(frame), str(symbol).upper(), str(timeframe).upper(), frame)
        for (symbol, timeframe), frame in frames.items()
        if frame is not None and len(frame) >= 2
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    shortest = candidates[0][3]
    position = int(round(len(shortest) * float(discovery_pct)))
    position = max(1, min(len(shortest) - 1, position))
    return _stamp(shortest.index[position])


def _limiting_series(
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
) -> dict | None:
    """Serie con el holdout más corto desde el corte común.

    Es la que limita la ventana sellada: si el corte deja menos de dos años
    hasta su última barra, hay que sacar ese activo del universo.
    """
    if cutoff is None:
        return None
    stamp = _stamp(cutoff)
    best: tuple[tuple, dict] | None = None
    for (symbol, timeframe), frame in frames.items():
        if frame is None or frame.empty:
            continue
        end = _stamp(frame.index[-1])
        span = end - stamp
        candidate = {
            "symbol": str(symbol).upper(),
            "timeframe": str(timeframe).upper(),
            "rows": int(len(frame)),
            "start": str(pd.Timestamp(frame.index[0])),
            "end": str(pd.Timestamp(frame.index[-1])),
            "seconds": float(span.total_seconds()),
        }
        key = (
            candidate["seconds"],
            candidate["rows"],
            candidate["symbol"],
            candidate["timeframe"],
        )
        if best is None or key < best[0]:
            best = (key, candidate)
    return best[1] if best is not None else None


def holdout_years(
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
) -> float | None:
    """Años del holdout común: del corte a la última barra que antes acaba."""
    limit = _limiting_series(frames, cutoff)
    if limit is None:
        return None
    return float(limit["seconds"]) / (DAYS_PER_YEAR * 86_400.0)


def trim_for_holdout(
    frames: dict[tuple[str, str], pd.DataFrame],
    *,
    discovery_pct: float = DISCOVERY_PCT,
    min_years: float = MIN_HOLDOUT_YEARS,
) -> dict | None:
    """Quita activos por la cola hasta que el holdout común dure ≥ `min_years`.

    No se acorta el holdout de todos: se saca del universo el activo cuya serie
    limita la ventana (la que antes acaba o la más corta que fija el corte), se
    recalcula el corte con las series restantes y se repite. Nunca se recorta
    una serie para que quepa.

    Devuelve `None` (Sin datos) si el universo se queda vacío o con menos de
    `MIN_SERIES` series.
    """
    remaining = {
        (str(symbol).upper(), str(timeframe).upper()): frame
        for (symbol, timeframe), frame in frames.items()
        if frame is not None and not frame.empty
    }
    excluded: list[dict] = []
    while remaining:
        cutoff = common_cutoff(remaining, discovery_pct)
        if cutoff is None:
            return None
        limit = _limiting_series(remaining, cutoff)
        if limit is None:
            return None
        years = float(limit["seconds"]) / (DAYS_PER_YEAR * 86_400.0)
        assets = {symbol for symbol, _ in remaining}
        if years >= float(min_years):
            if len(assets) < MIN_SERIES:
                return None
            return {
                "frames": remaining,
                "cutoff": cutoff,
                "excluded": excluded,
                "holdout_years": years,
                "assets": len(assets),
                "series": len(remaining),
            }
        excluded.append(
            {
                "symbol": limit["symbol"],
                "timeframe": limit["timeframe"],
                "rows": limit["rows"],
                "start": limit["start"],
                "end": limit["end"],
                "cutoff_before": str(_stamp(cutoff)),
                "holdout_years_before": round(years, 4),
                "reason": (
                    f"holdout común de {years:.2f} años < {float(min_years):g}: "
                    f"se excluye el activo con la serie que limita el holdout "
                    f"({limit['rows']} barras {limit['timeframe']}, "
                    f"{limit['start'][:10]} → {limit['end'][:10]})"
                ),
            }
        )
        remaining = {
            key: frame
            for key, frame in remaining.items()
            if key[0] != limit["symbol"]
        }
    return None


def _cutoff_for(
    config: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
) -> pd.Timestamp | None:
    """Corte común: el del yaml si existe; si no, se deriva de las series."""
    stored = config.get("cutoff_utc")
    if stored:
        return _stamp(stored)
    return common_cutoff(frames, float(config.get("discovery_pct", DISCOVERY_PCT)))


def split_frame(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp | str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descubrimiento (< corte) y holdout (>= corte) con una fecha común."""
    if frame.empty:
        return frame, frame
    if cutoff is None:
        return frame, frame.iloc[:0]
    stamp = _stamp(cutoff)
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        stamp = stamp.tz_convert(None)
    return frame[index < stamp], frame[index >= stamp]


def holdout_rows(
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
) -> list[dict]:
    """Fechas y tamaños del trozo sellado de cada serie, con el corte común."""
    rows = []
    for (symbol, timeframe), frame in sorted(frames.items()):
        _, sealed = split_frame(frame, cutoff)
        if sealed.empty:
            continue
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start": str(pd.Timestamp(sealed.index[0])),
                "end": str(pd.Timestamp(sealed.index[-1])),
                "rows": int(len(sealed)),
            }
        )
    return rows


def seal_ends(config: dict) -> dict[tuple[str, str], str]:
    """Fin sellado de cada serie, tal como quedó al escribir el yaml.

    El yaml guarda la última barra de cada trozo sellado. Al correr, el holdout
    se recorta a esa fecha: si el terminal ha añadido barras después del sello,
    no entran en la confirmación.
    """
    ends: dict[tuple[str, str], str] = {}
    series = config.get("holdout_series")
    if not isinstance(series, list):
        return ends
    for row in series:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        timeframe = str(row.get("timeframe") or "").upper()
        end = row.get("end")
        if symbol and timeframe and end:
            ends[(symbol, timeframe)] = str(end)
    return ends


def clip_seal(frame: pd.DataFrame, end: str | None) -> pd.DataFrame:
    """Recorta una serie a su fin sellado, sin mirar barras posteriores."""
    if frame is None or frame.empty or not end:
        return frame
    stamp = _stamp(end)
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        stamp = stamp.tz_convert(None)
    return frame[index <= stamp]



def plan_cells(
    universe: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
) -> dict:
    """Celdas que se pueden correr con el corte común, y las que no.

    Una celda entra en el `N_total` solo si el descubrimiento tiene más barras
    que las que exige su familia. Así el denominador del DSR cuenta pruebas
    reales y las celdas sin historia quedan listadas con su motivo.
    """
    by_symbol = {
        str(row["symbol"]).upper(): row for row in universe.get("symbols") or []
    }
    eligible = universe.get("eligible_by_timeframe") or {}
    runnable: list[dict] = []
    excluded: list[dict] = []
    for timeframe in TIMEFRAMES:
        for name in eligible.get(timeframe) or []:
            symbol = str(name).upper()
            row = by_symbol.get(symbol)
            frame = frames.get((symbol, timeframe))
            if row is None or frame is None or frame.empty:
                excluded.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "family": "*",
                        "variant": "*",
                        "reason": "Sin datos: sin velas para la celda",
                    }
                )
                continue
            discovery, _ = split_frame(frame, cutoff)
            asset_class = str(row.get("asset_class") or "")
            for family in FAMILIES:
                if not applies_to(family, asset_class):
                    continue
                for params in variants_for(family):
                    needed = required_history(frame, timeframe, family, params)
                    if len(discovery) <= needed:
                        excluded.append(
                            {
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "family": family,
                                "variant": params["variant"],
                                "discovery_rows": int(len(discovery)),
                                "needed": int(needed),
                                "reason": (
                                    f"historia insuficiente con el corte común: "
                                    f"{len(discovery)} barras, necesita más de {needed}"
                                ),
                            }
                        )
                        continue
                    runnable.append(
                        {
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "family": family,
                            "variant": params["variant"],
                            "discovery_rows": int(len(discovery)),
                            "needed": int(needed),
                        }
                    )
    per_timeframe: dict[str, int] = {tf: 0 for tf in TIMEFRAMES}
    for cell in runnable:
        per_timeframe[cell["timeframe"]] += 1
    return {
        "cutoff_utc": None if cutoff is None else str(_stamp(cutoff)),
        "n_total": int(len(runnable)),
        "per_timeframe": per_timeframe,
        "runnable": runnable,
        "excluded": excluded,
    }


def series_summary(
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
) -> list[dict]:
    """Tamaño, fechas y reparto de cada serie con el corte común."""
    rows: list[dict] = []
    for (symbol, timeframe), frame in sorted(frames.items()):
        if frame.empty:
            continue
        discovery, sealed = split_frame(frame, cutoff)
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": int(len(frame)),
                "start": str(pd.Timestamp(frame.index[0])),
                "end": str(pd.Timestamp(frame.index[-1])),
                "discovery_rows": int(len(discovery)),
                "holdout_rows": int(len(sealed)),
                "holdout_start": (
                    str(pd.Timestamp(sealed.index[0])) if len(sealed) else None
                ),
            }
        )
    return rows


def prepare_campaign(
    universe: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
    *,
    discovery_pct: float = DISCOVERY_PCT,
    min_holdout_years: float = MIN_HOLDOUT_YEARS,
    cache_dir: str | Path | None = None,
    reassess: bool = True,
) -> dict:
    """Universo final + plan con un holdout común de al menos dos años.

    1. Re-mide la elegibilidad con las velas completas del `fetch` (rompe el
       círculo de H1/H4).
    2. Quita del universo los activos que dejan el holdout común por debajo de
       `min_holdout_years`, recalculando el corte en cada vuelta.
    3. Calcula las celdas con historia y sella el holdout con su fecha.

    No registra nada: es solo el plan que después escribe el yaml.
    """
    import copy

    work = copy.deepcopy(universe)
    if reassess:
        reassess_universe(work, frames, cache_dir=cache_dir)
    candidates = set(campaign_symbols(work))
    if not candidates:
        raise CampaignError("Sin datos: ningún activo elegible tras medir coste")
    candidate_frames = {
        (str(symbol).upper(), str(timeframe).upper()): frame
        for (symbol, timeframe), frame in frames.items()
        if str(symbol).upper() in candidates
        and frame is not None
        and not frame.empty
    }
    trimmed = trim_for_holdout(
        candidate_frames,
        discovery_pct=discovery_pct,
        min_years=min_holdout_years,
    )
    if trimmed is None:
        raise CampaignError(
            "Sin datos: no hay series suficientes con un holdout común de "
            f"{float(min_holdout_years):g} años"
        )
    kept = trimmed["frames"]
    excluded_symbols = {str(item["symbol"]).upper() for item in trimmed["excluded"]}
    if excluded_symbols:
        refresh_universe_eligibility(work)
        work["eligible_by_timeframe"] = {
            str(timeframe).upper(): [
                str(name).upper()
                for name in (names or [])
                if str(name).upper() not in excluded_symbols
            ]
            for timeframe, names in (work.get("eligible_by_timeframe") or {}).items()
        }
        work["campaign_symbols"] = campaign_symbols(work)

    cutoff = trimmed["cutoff"]
    plan = plan_cells(work, kept, cutoff)
    if int(plan["n_total"]) <= 0:
        raise CampaignError(
            "Sin datos: N_total es 0 con el corte común; ninguna celda tiene "
            "historia suficiente"
        )
    sealed = holdout_rows(kept, cutoff)
    plan["holdout_hash"] = holdout_hash(sealed, cutoff)
    plan["holdout_series"] = sealed
    plan["holdout_years"] = float(trimmed["holdout_years"])
    plan["min_holdout_years"] = float(min_holdout_years)
    plan["excluded_assets"] = list(trimmed["excluded"])
    plan["assets"] = int(trimmed["assets"])
    plan["series"] = int(trimmed["series"])
    work["bars"] = {**CAMPAIGN_BARS, "D1": "desde H4"}
    work["generated_at"] = _now()
    work["cutoff_utc"] = plan["cutoff_utc"]
    work["holdout_years"] = plan["holdout_years"]
    work["excluded_assets"] = list(trimmed["excluded"])
    work["series"] = series_summary(kept, cutoff)
    work["plan"] = plan
    return work


# ----------------------------------------------------------- descubrimiento


def _hourly_spread(frame: pd.DataFrame, point: float) -> pd.Series:
    hourly = spread_by_hour(frame, point)
    if hourly.empty:
        return pd.Series(dtype=float)
    return hourly


#: Barras para el motor de la campaña: "máximo disponible" del terminal. Con
#: 70/30 el descubrimiento se queda con ~35.000 barras H1, sitio de sobra para
#: lookbacks de 250 días.
CAMPAIGN_BARS = {"H1": 50_000, "H4": 50_000}


def require_live_data(
    broker,
    *,
    references: tuple[str, ...] = ("EURUSD", "XAUUSD", "US500.cash"),
    max_age_minutes: float = 15.0,
    now: datetime | None = None,
) -> dict:
    """Exige mercado abierto y offset confirmado antes de descargar.

    Un tick fresco del bróker prueba las dos cosas: que el mercado está abierto
    y que la hora del servidor se puede situar en UTC. Si el offset es
    desconocido o el último tick es viejo, no se descarga nada: se devuelve
    **Sin datos**, no una serie con la hora mal.
    """
    health = broker.health() if hasattr(broker, "health") else {}
    if not health.get("offset_known"):
        raise CampaignError(
            "Sin datos: offset del servidor sin confirmar; no se descarga nada"
        )
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    failures: list[str] = []
    for name in references:
        try:
            tick = broker.tick(name)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            continue
        stamp = tick.get("time")
        if stamp is None:
            failures.append(f"{name}: sin hora de tick")
            continue
        stamp = _stamp(stamp)
        age = (moment - stamp.to_pydatetime()).total_seconds() / 60.0
        if age <= float(max_age_minutes):
            return {
                "symbol": name,
                "tick_time": str(stamp),
                "age_minutes": round(float(age), 2),
                "offset_utc_hours": health.get("server_utc_offset_hours"),
                "offset_source": health.get("offset_source"),
            }
        failures.append(f"{name}: último tick hace {age:.0f} min")
    raise CampaignError(
        "Sin datos: mercado cerrado o sin ticks frescos ("
        + "; ".join(failures)
        + ")"
    )


def load_campaign_frames(
    broker,
    symbols: list[str],
    *,
    names: dict[str, str] | None = None,
    bars: dict | None = None,
    cache_dir: str | Path | None = None,
    save: bool = True,
) -> tuple[dict[tuple[str, str], pd.DataFrame], dict[str, float]]:
    """H1 y H4 (máximo disponible) de los candidatos y D1 construido desde H4.

    `symbols` son las claves en mayúsculas del universo; `names` traduce cada
    clave al nombre exacto del bróker (`US100.cash`, no `US100.CASH`), que es
    el que exige el terminal. Los marcos se indexan siempre por la clave.

    Se piden **todos** los candidatos, no solo los ya elegibles: la
    elegibilidad de H1/H4 se mide después con estas velas completas.
    """
    sizes = dict(CAMPAIGN_BARS)
    sizes.update(bars or {})
    mapping = {str(k).upper(): str(v) for k, v in (names or {}).items()}
    target_dir = Path(cache_dir) if cache_dir else (ROOT / "data" / "cache")
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    points: dict[str, float] = {}
    for symbol in symbols:
        key = str(symbol).upper()
        broker_name = mapping.get(key, symbol)
        try:
            spec = broker.symbol_spec(broker_name)
            points[key] = float(spec.get("tick_size") or spec.get("point") or 0.01)
        except Exception:
            points[key] = 0.01
        raw: dict[str, pd.DataFrame] = {}
        for timeframe in ("H1", "H4"):
            try:
                frame = broker.rates(broker_name, timeframe, int(sizes[timeframe]))
                if frame is None or frame.empty:
                    continue
                frame = frame[~frame.index.duplicated(keep="last")].sort_index()
                if save:
                    from .intraday import save_bars

                    save_bars(frame, target_dir, key, timeframe)
                raw[timeframe] = frame
                frames[(key, timeframe)] = frame
            except Exception:
                continue
        if "H4" in raw:
            try:
                frames[(key, "D1")] = daily_bars(raw["H4"])
            except Exception:
                pass
    return frames, points


def _costs_for(symbol: str, frame: pd.DataFrame) -> tuple[float | pd.Series, float]:
    cost = asset_costs(symbol)
    if not cost.verified:
        raise CampaignError(f"sin comisión verificada para {symbol}")
    commission = cost.commission_bps(
        pd.to_numeric(frame["close"], errors="coerce").astype(float)
    )
    return commission, float(cost.slippage_conservative_bps or SLIPPAGE_BPS)


def backtest_variant(
    symbol: str,
    timeframe: str,
    frame: pd.DataFrame,
    family: str,
    params: dict,
    *,
    point: float = 0.01,
    hourly_spread: pd.Series | None = None,
) -> dict:
    """Backtest neto de una celda con costes calibrados."""
    target = family_target(frame, timeframe, family, params)
    commission, slippage = _costs_for(symbol, frame)
    result = backtest_intraday(
        frame,
        target,
        timeframe=timeframe,
        commission_bps=commission,
        slippage_bps=slippage,
        point=float(point),
        tick_spread_bps=hourly_spread if hourly_spread is not None else None,
    )
    metrics = dict(result["metrics"])
    metrics["calibrated_cost_bps"] = result.get("calibrated_cost_bps")
    metrics["spread_reliable"] = result.get("spread_reliable")
    return {"metrics": metrics, "returns": result["returns"]}


def _annualization(timeframe: str) -> float:
    return float(BARS_PER_YEAR.get(str(timeframe).upper(), 252))


def run_discovery(
    db_path: str | Path,
    config: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
    *,
    points: dict[str, float] | None = None,
    persist: bool = True,
    resume: bool = False,
) -> dict:
    """Corre la rejilla sobre el 70 % y registra cada celda en `strategy_trials`.

    Las celdas se registran con `counted=False`: `N_total` ya entró entero al
    registrar la campaña, así que contarlas otra vez inflaría el denominador
    del DSR.

    `resume=True` reanuda un run que se cortó por un fallo de código, no por
    haber visto resultados: reutiliza el `run_id` y recalcula las celdas en
    memoria (`persist=False`) sin volver a insertarlas. La rejilla y los
    umbrales son los mismos, así que el resultado es idéntico.
    """
    record = load_campaign(db_path, str(config["id"]))
    started = record.get("started_at")
    run_id = str(record.get("run_id") or hashlib.sha256(
        f"{config['id']}|{record['config_hash']}".encode("utf-8")
    ).hexdigest()[:12])
    if started and not resume:
        raise CampaignError(
            f"la campaña {config['id']} ya se ejecutó el {started}"
        )
    if resume:
        if not started or not record.get("run_id"):
            raise CampaignError(
                f"la campaña {config['id']} no tiene un run a medias que reanudar"
            )
        if record.get("finished_at"):
            raise CampaignError(
                f"la campaña {config['id']} ya terminó el {record['finished_at']}"
            )
        persist = False
    if str(record.get("config_hash")) != campaign_hash(config):
        raise CampaignError(
            "la rejilla cambió respecto al registro: el hash no coincide"
        )
    if not started:
        with connect(db_path) as con:
            con.execute(
                "UPDATE campaign_registry SET started_at = ?, run_id = ? "
                "WHERE campaign_id = ?",
                (_now(), run_id, str(config["id"])),
            )
            con.commit()

    tick = dict(points or {})
    cutoff = _cutoff_for(config, frames)
    eligible = {
        str(timeframe).upper(): {str(name).upper() for name in (names or [])}
        for timeframe, names in (config.get("eligible_by_timeframe") or {}).items()
    }
    asset_classes = {
        str(key).upper(): str(value)
        for key, value in (config.get("asset_classes") or {}).items()
    }
    timeframes = {
        str(timeframe).upper() for timeframe in (config.get("timeframes") or TIMEFRAMES)
    }
    cells: list[dict] = []
    skipped = 0
    returns_by_id: dict[str, pd.Series] = {}
    for (symbol, timeframe), frame in sorted(frames.items()):
        if str(timeframe).upper() not in timeframes:
            continue
        allowed = eligible.get(str(timeframe).upper())
        if allowed is not None and str(symbol).upper() not in allowed:
            continue
        discovery, _ = split_frame(frame, cutoff)
        if len(discovery) < 80:
            continue
        # El coste del descubrimiento se calibra solo con su trozo: ni el
        # spread del holdout entra en la condición de meseta.
        hourly = _hourly_spread(discovery, tick.get(symbol, 0.01))
        asset_class = asset_classes.get(str(symbol).upper(), "")
        for family in config.get("families") or FAMILIES:
            if asset_class and not applies_to(family, asset_class):
                continue
            for params in variants_for(family):
                if len(discovery) <= required_history(frame, timeframe, family, params):
                    skipped += 1
                    continue
                key = f"{symbol}|{timeframe}|{family}|{params['variant']}"
                cell = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "family": family,
                    "variant": params["variant"],
                    "params": dict(params),
                }
                try:
                    outcome = backtest_variant(
                        symbol,
                        timeframe,
                        discovery,
                        family,
                        params,
                        point=tick.get(symbol, 0.01),
                        hourly_spread=hourly,
                    )
                    metrics = outcome["metrics"]
                    returns_by_id[key] = outcome["returns"]
                    cell.update(
                        {
                            "sharpe": float(metrics.get("sharpe") or 0.0),
                            "trades": int(metrics.get("num_trades") or 0),
                            "max_drawdown": float(metrics.get("max_drawdown") or 0.0),
                            "total_return": float(metrics.get("total_return") or 0.0),
                            "bars": int(metrics.get("bars") or 0),
                            "outcome": "passed",
                            "reason": "",
                        }
                    )
                except Exception as exc:
                    cell.update(
                        {
                            "sharpe": 0.0,
                            "trades": 0,
                            "max_drawdown": 0.0,
                            "total_return": 0.0,
                            "bars": 0,
                            "outcome": "failed",
                            "reason": str(exc)[:300],
                        }
                    )
                if persist:
                    record_trial(
                        db_path,
                        family=family,
                        hypothesis=FAMILY_HYPOTHESIS.get(family, family),
                        symbol=symbol,
                        params={**cell["params"], "timeframe": timeframe},
                        window_start=str(discovery.index[0]),
                        window_end=str(discovery.index[-1]),
                        result={
                            "sharpe": cell["sharpe"],
                            "trades": cell["trades"],
                            "max_drawdown": cell["max_drawdown"],
                            "total_return": cell["total_return"],
                            "bars": cell["bars"],
                        },
                        outcome=cell["outcome"],
                        reason=cell["reason"],
                        source="campaign",
                        run_id=run_id,
                        counted=False,
                    )
                cells.append(cell)
    return {
        "campaign": config["id"],
        "run_id": run_id,
        "cutoff_utc": None if cutoff is None else str(cutoff),
        "cells": cells,
        "returns_by_id": returns_by_id,
        "n_cells": len(cells),
        "n_skipped": skipped,
    }


# ------------------------------------------------------------------- meseta


def correlation_clusters(
    frames: dict[tuple[str, str], pd.DataFrame],
    cutoff: pd.Timestamp | str | None,
    threshold: float = CORR_CLUSTER,
) -> dict[str, dict[str, float]]:
    """Pares de activos con correlación de retornos por encima del umbral.

    Se mide sobre el retorno de la barra del propio activo **antes del corte
    común**: no depende de la estrategia ni mira el holdout, así que no
    introduce sesgo en la condición de clúster.
    """
    by_timeframe: dict[str, dict[str, pd.Series]] = {}
    for (symbol, timeframe), frame in frames.items():
        discovery, _ = split_frame(frame, cutoff)
        if len(discovery) < 80:
            continue
        by_timeframe.setdefault(timeframe, {})[symbol] = (
            pd.to_numeric(discovery["close"], errors="coerce")
            .astype(float)
            .pct_change()
        )
    clusters: dict[str, dict[str, float]] = {}
    for timeframe, series in by_timeframe.items():
        frame = pd.concat(series, axis=1, join="inner").dropna()
        if len(frame) < 80 or frame.shape[1] < 2:
            continue
        matrix = frame.corr()
        for left in matrix.columns:
            for right in matrix.columns:
                if left == right:
                    continue
                value = matrix.loc[left, right]
                if np.isfinite(value) and float(value) > float(threshold):
                    clusters.setdefault(f"{left}|{timeframe}", {})[right] = float(value)
    return clusters


ADJACENT = {"H1": ("H4",), "H4": ("H1", "D1"), "D1": ("H4",)}


def apply_plateau(
    cells: list[dict],
    clusters: dict[str, dict[str, float]],
    *,
    skip_adjacent_if_empty: bool = False,
) -> list[dict]:
    """Marca cada celda con las cuatro condiciones de meseta.

    (a) Sharpe neto > 0,5 con ≥ 30 trades.
    (b) Al menos 2 de sus 3 vecinas de parámetro con Sharpe neto > 0.
    (c) La misma familia y variante positiva en un timeframe adyacente.
    (d) Positiva en un activo de su clúster de correlación (> 0,6).
    """
    index = {
        (cell["symbol"], cell["timeframe"], cell["family"], cell["variant"]): cell
        for cell in cells
    }
    result: list[dict] = []
    for cell in cells:
        symbol = cell["symbol"]
        timeframe = cell["timeframe"]
        family = cell["family"]
        variant = cell["variant"]
        neighbours = [
            index.get((symbol, timeframe, family, other["variant"]))
            for other in variants_for(family)
            if other["variant"] != variant
        ]
        neighbours = [item for item in neighbours if item is not None]
        positive_neighbours = sum(1 for item in neighbours if item["sharpe"] > 0.0)
        adjacent_hits = [
            index.get((symbol, other, family, variant)) for other in ADJACENT.get(timeframe, ())
        ]
        adjacent_timeframes = ADJACENT.get(timeframe, ())
        adjacent_present = any(
            str(other_cell.get("timeframe")) in adjacent_timeframes
            for other_cell in cells
        )
        adjacent_exempt = bool(skip_adjacent_if_empty and not adjacent_present)
        adjacent_ok = adjacent_exempt or any(
            item is not None and item["sharpe"] > 0.0 for item in adjacent_hits
        )
        related = clusters.get(f"{symbol}|{timeframe}", {})
        cluster_hits = [
            index.get((other, timeframe, family, variant)) for other in related
        ]
        cluster_ok = any(
            item is not None and item["sharpe"] > 0.0 for item in cluster_hits
        )
        condition_a = cell["sharpe"] > SHARPE_MIN and cell["trades"] >= MIN_TRADES
        condition_b = positive_neighbours >= NEIGHBOURS_REQUIRED
        failed = []
        if not condition_a:
            failed.append(
                f"a: Sharpe {cell['sharpe']:.2f} / {cell['trades']} trades"
            )
        if not condition_b:
            failed.append(f"b: {positive_neighbours} de {len(neighbours)} vecinas")
        if not adjacent_ok:
            failed.append(f"c: sin positivo en {', '.join(ADJACENT.get(timeframe, ()))}")
        if not cluster_ok:
            failed.append(
                "d: sin positivo en clúster"
                if related
                else "d: sin activos correlacionados > 0,6"
            )
        result.append(
            {
                **cell,
                "neighbours_positive": positive_neighbours,
                "neighbours_total": len(neighbours),
                "adjacent_ok": adjacent_ok,
                "adjacent_exempt": adjacent_exempt,
                "cluster_ok": cluster_ok,
                "cluster": sorted(related),
                "plateau": condition_a and condition_b and adjacent_ok and cluster_ok,
                "failed": failed,
            }
        )
    return result


def candidates(plateau_cells: list[dict]) -> list[dict]:
    return [cell for cell in plateau_cells if cell.get("plateau")]


# --------------------------------------------------------------- confirmación


def run_holdout(
    db_path: str | Path,
    config: dict,
    frames: dict[tuple[str, str], pd.DataFrame],
    selected: list[dict],
    *,
    points: dict[str, float] | None = None,
    prior_tests: int = 0,
    paths: int = 5_000,
    seed: int = 42,
) -> list[dict]:
    """Abre el holdout **solo** para las candidatas y aplica los cuatro filtros."""
    from .prop.rules import from_yaml
    from .prop.simulator import monte_carlo
    from .research import deflated_sharpe
    from .swing import daily_returns
    from .validation import cscv_pbo, returns_matrix

    record = load_campaign(db_path, str(config["id"]))
    n_total = int(record["n_total"])
    n_trials = n_total + int(prior_tests)
    tick = dict(points or {})
    rules = from_yaml("ftmo", "challenge", 100_000.0)
    cutoff = _cutoff_for(config, frames)
    ends = seal_ends(config)
    confirmed: list[dict] = []
    for cell in selected:
        symbol = cell["symbol"]
        timeframe = cell["timeframe"]
        frame = frames.get((symbol, timeframe))
        if frame is None:
            cell.update({"holdout_sharpe": None, "confirmed": False, "verdict": "Sin datos"})
            continue
        _, sealed = split_frame(frame, cutoff)
        sealed = clip_seal(sealed, ends.get((symbol, timeframe)))
        if len(sealed) < 80:
            cell.update({"holdout_sharpe": None, "confirmed": False, "verdict": "Sin datos"})
            continue
        hourly = _hourly_spread(sealed, tick.get(symbol, 0.01))
        outcome = backtest_variant(
            symbol,
            timeframe,
            sealed,
            cell["family"],
            cell["params"],
            point=tick.get(symbol, 0.01),
            hourly_spread=hourly,
        )
        metrics = outcome["metrics"]
        returns = outcome["returns"]
        sharpe = float(metrics.get("sharpe") or 0.0)
        sr_std = abs(sharpe) / np.sqrt(max(2, int(metrics.get("bars") or 2)))
        dsr = deflated_sharpe(
            sharpe,
            int(metrics.get("bars") or 0),
            float(pd.Series(returns).skew()),
            float(pd.Series(returns).kurtosis() + 3.0),
            float(sr_std),
            n_trials,
        )
        matrix = returns_matrix({"cell": returns})
        pbo = None
        if matrix is not None:
            try:
                pbo = float(cscv_pbo(matrix).pbo)
            except Exception:
                pbo = None
        daily = daily_returns(returns)
        simulations = {}
        for kelly in MC_KELLY:
            try:
                sim = monte_carlo(
                    rules,
                    daily.to_numpy() * float(kelly),
                    n_paths=int(paths),
                    horizon=60,
                    seed=int(seed),
                    block_size=5,
                )
                simulations[str(kelly)] = {
                    "pass_rate": float(sim.get("pass_rate") or 0.0),
                    "breach_rate": float(sim.get("breach_rate") or 0.0),
                }
            except Exception as exc:
                simulations[str(kelly)] = {"error": str(exc)[:200]}
        passed = (
            sharpe > 0.0
            and dsr is not None
            and float(dsr) >= DSR_MIN
            and pbo is not None
            and float(pbo) < PBO_MAX
        )
        cell.update(
            {
                "holdout_sharpe": sharpe,
                "holdout_trades": int(metrics.get("num_trades") or 0),
                "holdout_max_drawdown": float(metrics.get("max_drawdown") or 0.0),
                "dsr": None if dsr is None else float(dsr),
                "dsr_n_trials": n_trials,
                "pbo": pbo,
                "monte_carlo": simulations,
                "confirmed": bool(passed),
                "verdict": "confirmada" if passed else "no confirmada",
            }
        )
        if passed:
            confirmed.append(cell)
    return confirmed


# ------------------------------------------------------------------- informe


def _colour(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "#e8e8e8"
    clipped = max(-1.0, min(1.0, float(value)))
    if clipped >= 0.0:
        ratio = clipped
        red = int(255 - 90 * ratio)
        green = int(190 + 50 * ratio)
        blue = int(255 - 130 * ratio)
    else:
        ratio = -clipped
        red = int(190 + 50 * ratio)
        green = int(255 - 90 * ratio)
        blue = int(255 - 130 * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def svg_heatmap(
    title: str,
    rows: list[str],
    columns: list[str],
    values: dict[tuple[str, str], float | None],
) -> str:
    """Mapa de calor SVG sin dependencias: activo × timeframe."""
    cell_w, cell_h = 96, 30
    pad_left, pad_top, pad_bottom = 150, 46, 14
    width = pad_left + cell_w * max(1, len(columns)) + 12
    height = pad_top + cell_h * max(1, len(rows)) + pad_bottom
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Segoe UI, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="10" y="20" font-size="13" font-weight="600" fill="#222">{title}</text>',
        '<text x="10" y="36" font-size="10" fill="#666">Sharpe neto · descubrimiento 70 %</text>',
    ]
    for column_index, column in enumerate(columns):
        x = pad_left + column_index * cell_w + cell_w / 2
        parts.append(
            f'<text x="{x:.0f}" y="{pad_top - 6}" font-size="11" text-anchor="middle" '
            f'fill="#333">{column}</text>'
        )
    for row_index, row in enumerate(rows):
        y = pad_top + row_index * cell_h
        parts.append(
            f'<text x="{pad_left - 8}" y="{y + cell_h / 2 + 4:.0f}" font-size="11" '
            f'text-anchor="end" fill="#333">{row}</text>'
        )
        for column_index, column in enumerate(columns):
            value = values.get((row, column))
            x = pad_left + column_index * cell_w
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_w - 2}" height="{cell_h - 2}" '
                f'fill="{_colour(value)}" stroke="#ffffff"/>'
            )
            label = "Sin datos" if value is None else f"{value:.2f}"
            parts.append(
                f'<text x="{x + cell_w / 2 - 1:.0f}" y="{y + cell_h / 2 + 4:.0f}" '
                f'font-size="10" text-anchor="middle" fill="#222">{label}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def write_report(
    campaign_id: str,
    plateau_cells: list[dict],
    confirmed: list[dict],
    *,
    n_total: int,
    out_dir: str | Path | None = None,
) -> dict:
    """Informe con mapas de calor por familia, tabla de candidatas y confirmadas."""
    target = Path(out_dir) if out_dir else REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    symbols = sorted({cell["symbol"] for cell in plateau_cells})
    charts: list[str] = []
    for family in FAMILIES:
        subset = [cell for cell in plateau_cells if cell["family"] == family]
        if not subset:
            continue
        values: dict[tuple[str, str], float | None] = {}
        for cell in subset:
            values[(cell["symbol"], cell["timeframe"])] = cell["sharpe"]
        svg = svg_heatmap(f"{family} · {campaign_id}", symbols, list(TIMEFRAMES), values)
        name = f"heatmap_{family}.svg"
        (target / name).write_text(svg, encoding="utf-8")
        charts.append(name)

    heading = (
        f"# Campaña {campaign_id} — 0 confirmadas"
        if not confirmed
        else f"# Campaña {campaign_id} — {len(confirmed)} confirmadas"
    )
    lines = [
        heading,
        "",
        f"- Generado: {_now()}",
        f"- `N_total` registrado antes de correr: **{n_total}**",
        f"- Celdas evaluadas en descubrimiento: {len(plateau_cells)}",
        f"- Candidatas tras la meseta: {len(candidates(plateau_cells))}",
        f"- Confirmadas en el holdout: **{len(confirmed)}**",
        "",
        "## Mapas de calor",
        "",
    ]
    lines += [f"![{name}]({name})" for name in charts]
    lines += [
        "",
        "## Candidatas y sus vecinas",
        "",
        "| Activo | TF | Familia | Variante | Sharpe | Trades | Vecinas > 0 | "
        "Adyacente | Clúster | Holdout | DSR | PBO | Veredicto |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in candidates(plateau_cells):
        lines.append(
            "| {symbol} | {tf} | {family} | {variant} | {sharpe:.2f} | {trades} | "
            "{nb}/{nt} | {adj} | {clus} | {ho} | {dsr} | {pbo} | {verdict} |".format(
                symbol=cell["symbol"],
                tf=cell["timeframe"],
                family=cell["family"],
                variant=cell["variant"],
                sharpe=cell["sharpe"],
                trades=cell["trades"],
                nb=cell["neighbours_positive"],
                nt=cell["neighbours_total"],
                adj="sí" if cell["adjacent_ok"] else "no",
                clus="sí" if cell["cluster_ok"] else "no",
                ho=_fmt(cell.get("holdout_sharpe"), 2),
                dsr=_fmt(cell.get("dsr"), 3),
                pbo=_fmt(cell.get("pbo"), 3),
                verdict=cell.get("verdict", "Sin datos"),
            )
        )
    lines += ["", "## Confirmadas", ""]
    if confirmed:
        for cell in confirmed:
            lines.append(
                f"- **{cell['symbol']} · {cell['timeframe']} · {cell['family']} · "
                f"{cell['variant']}** — Sharpe holdout {cell['holdout_sharpe']:.2f}, "
                f"DSR {cell['dsr']:.3f} (n_trials {cell['dsr_n_trials']}), "
                f"PBO {cell['pbo']:.3f}"
            )
    else:
        lines.append(
            "Ninguna celda superó las cuatro condiciones de meseta y los cuatro "
            "filtros del holdout. No se registra ningún candidato."
        )
    lines += [
        "",
        "## Condición que falla por celda",
        "",
        "| Activo | TF | Familia | Variante | Fallan |",
        "|---|---|---|---|---|",
    ]
    for cell in plateau_cells:
        if cell["plateau"]:
            continue
        lines.append(
            f"| {cell['symbol']} | {cell['timeframe']} | {cell['family']} | "
            f"{cell['variant']} | {'; '.join(cell['failed']) or 'Sin datos'} |"
        )
    text = "\n".join(lines)
    path = target / f"{campaign_id}.md"
    path.write_text(text, encoding="utf-8")
    return {"md": str(path), "charts": charts}


__all__ = [
    "BAR_HOURS",
    "COST_ATR_MAX",
    "DISCOVERY_PCT",
    "FAMILIES",
    "FAMILY_VARIANTS",
    "INDICES_ONLY",
    "MAX_VARIANTS",
    "MIN_HOLDOUT_YEARS",
    "MIN_SERIES",
    "TIMEFRAMES",
    "CampaignError",
    "apply_plateau",
    "applies_to",
    "atr_stats",
    "backtest_variant",
    "bars_for_days",
    "bars_for_hours",
    "bars_per_day",
    "build_universe",
    "campaign_config",
    "campaign_hash",
    "campaign_symbols",
    "candidates",
    "classify_symbol",
    "clip_seal",
    "common_cutoff",
    "compute_n_total",
    "correlation_clusters",
    "cost_atr",
    "family_target",
    "finish_campaign",
    "holdout_hash",
    "holdout_rows",
    "holdout_years",
    "init_campaigns",
    "load_campaign",
    "load_campaign_frames",
    "load_campaign_yaml",
    "observed_bars_per_day",
    "plan_cells",
    "prepare_campaign",
    "reassess_universe",
    "refresh_universe_eligibility",
    "register_campaign",
    "render_universe",
    "require_live_data",
    "required_history",
    "resolved_bars",
    "roundtrip_bps",
    "run_discovery",
    "run_holdout",
    "seal_ends",
    "series_summary",
    "spread_by_hour",
    "split_frame",
    "svg_heatmap",
    "trim_for_holdout",
    "universe_symbols",
    "variants_for",
    "write_report",
    "write_universe",
]
