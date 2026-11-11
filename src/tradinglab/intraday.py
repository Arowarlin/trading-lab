"""Investigación intradía forex/CFD con datos MT5 locales.

- Cachea velas M15/H1 ya corregidas a UTC por MT5Broker.rates.
- Modela spread por hora (si existe), slippage y comisión.
- Incluye tres estrategias acotadas y las pasa por DSR/PBO/WF/regímenes.
- No descarga datos de pago ni envía órdenes.
"""
from __future__ import annotations

import itertools
import json
import re
import uuid
from datetime import datetime, time, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DEFAULT_DB, ROOT
from .indicators import atr, ema
from .intraday_costs import asset_costs
from .learning import count_tests, get_lesson
from .profiles import get_profile
from .prop.rules import PropRules, from_yaml
from .prop.simulator import monte_carlo
from .research import deflated_sharpe
from .session import session_block
from .strategies.base import StrategyResult
from .trials import record_trial
from .validation import cscv_pbo, returns_matrix
from .walkforward import regime_gate, regime_report, walk_forward

INTRADAY_GRIDS = {
    "orb": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [8, 16]},
    "pullback": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "asian_rev": {"buffer_atr": [0.1, 0.3], "max_hold": [8, 16]},
    "orb_ny": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [8, 16]},
    "trend_intraday": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "overlap_breakout": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [4, 8]},
    "range_reversal": {"lookback": [12, 24], "entry_z": [1.5, 2.0], "max_hold": [8, 16]},
    "london_pullback": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "session_trend": {"fast": [20, 50], "slow": [100, 200], "pullback_atr": [0.25, 0.5], "max_hold": [8, 16]},
    "tokyo_breakout": {"range_bars": [4, 8], "buffer_atr": [0.1, 0.25], "max_hold": [4, 12]},
    "caja_ny": {
        "range_start": ["09:15"],
        "range_end": ["09:35"],
        "stop_rule": ["range", "atr_0.5", "atr_1.0", "atr_1.5"],
        "force_exit": ["15:45"],
        "max_trades_per_day": [1],
    },
}
ASSET_FAMILIES = {
    "US100.CASH": ("orb_ny", "trend_intraday", "caja_ny"),
    "NASDAQ": ("orb_ny", "trend_intraday", "caja_ny"),
    "XAUUSD": ("asian_rev", "overlap_breakout"),
    "EURUSD": ("range_reversal", "london_pullback"),
    "USDJPY": ("session_trend", "tokyo_breakout"),
}
DEFAULT_HORIZONS = (22, 44, 120)
COST_GRID_BPS = (0.0, 0.5, 1.0, 2.0, 3.0)
FAMILY_HYPOTHESES = {
    "orb": (
        "Ruptura del rango de apertura: la continuación de la momentum tras la "
        "apertura de Londres/NY tiene ventaja en M15."
    ),
    "pullback": (
        "Tendencia intradía con retroceso a la media: los retrocesos dentro de "
        "la tendencia ofrecen mejor precio de entrada."
    ),
    "asian_rev": (
        "Reversión del rango asiático: el rango formado en la sesión asiática "
        "suele revertirse al inicio de la sesión europea."
    ),
    "orb_ny": (
        "Ruptura del rango de apertura de Nueva York: la momentum posterior a "
        "las 09:30 ET continúa en el índice."
    ),
    "trend_intraday": (
        "Tendencia intradía en la sesión de Nueva York: el índice mantiene "
        "dirección tras la apertura."
    ),
    "overlap_breakout": (
        "Ruptura en el solape Londres/NY: el oro amplía rango cuando coinciden "
        "las dos sesiones."
    ),
    "range_reversal": (
        "Reversión a la media en rango durante Londres: los extremos del rango "
        "vuelven a la media."
    ),
    "london_pullback": (
        "Tendencia con retroceso en Londres: el retroceso a la media rápida "
        "ofrece entrada a favor de la tendencia del euro."
    ),
    "session_trend": (
        "Tendencia con filtro de sesión en USDJPY: la dirección dominante "
        "persiste durante Tokio/Londres."
    ),
    "tokyo_breakout": (
        "Ruptura tras la sesión de Tokio: el rango asiático se rompe al abrir "
        "Europa."
    ),
    "caja_ny": (
        "Caja de apertura de Nueva York: tras el rango 09:15-09:35 NY, la "
        "ruptura con retroceso limitado al borde roto tiene ventaja si el stop "
        "está fuera del rango o a N×ATR."
    ),
}


def families_for_symbol(symbol: str) -> tuple[str, ...]:
    """Familias asignadas al activo (todas si no está en el mapa)."""
    return ASSET_FAMILIES.get(str(symbol).upper(), tuple(INTRADAY_GRIDS))


# Modo de ejecución por familia. Serie es el predeterminado y ninguna familia
# existente cambia: solo una que se declare aquí como "events" usa el motor de
# eventos de forma explícita.
FAMILY_EXECUTION_MODES = {name: "series" for name in INTRADAY_GRIDS}
FAMILY_EXECUTION_MODES["caja_ny"] = "events"


def family_execution_mode(family: str) -> str:
    """Modo declarado por la familia; serie si no declara eventos."""
    return FAMILY_EXECUTION_MODES.get(str(family), "series")


TRADING_DAYS_PER_YEAR = 252
SESSION_MINUTES = 24 * 60
BAR_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}
# Barras completas por sesión de 24 h; D1 es una barra por sesión.
BARS_PER_SESSION = {
    timeframe: SESSION_MINUTES // minutes
    for timeframe, minutes in BAR_MINUTES.items()
}
BARS_PER_YEAR = {
    timeframe: TRADING_DAYS_PER_YEAR * bars
    for timeframe, bars in BARS_PER_SESSION.items()
}


def _bars_per_year(timeframe: str) -> float:
    """Barras anuales del timeframe; falla si no está en el mapa."""
    key = str(timeframe).strip().upper()
    try:
        return float(BARS_PER_YEAR[key])
    except KeyError:
        valid = ", ".join(sorted(BARS_PER_YEAR))
        raise ValueError(
            f"timeframe desconocido: {timeframe!r}; usa uno de: {valid}"
        ) from None


def _sharpe_returns(returns: pd.Series, timeframe: str) -> float:
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    if std <= 0:
        return 0.0
    return float(returns.mean() / std * np.sqrt(_bars_per_year(timeframe)))


def _sharpe_at_cost(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    cost_bps: float,
) -> float:
    net = gross - turnover * float(cost_bps) / 10_000.0
    return _sharpe_returns(net, timeframe)


def _cost_curve(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    grid: tuple[float, ...] = COST_GRID_BPS,
) -> dict[str, float]:
    return {
        str(cost): _sharpe_at_cost(gross, turnover, timeframe, cost)
        for cost in grid
    }


def break_even_cost_bps(
    gross: pd.Series,
    turnover: pd.Series,
    timeframe: str,
    *,
    upper: float = 200.0,
) -> float | None:
    """Coste uniforme por unidad de turnover donde el Sharpe neto cruza 0.

    Si el Sharpe bruto ya es <= 0, no hay coste de equilibrio positivo: 0.0.
    """
    if _sharpe_at_cost(gross, turnover, timeframe, 0.0) <= 0:
        return 0.0
    low = 0.0
    high = float(upper)
    while _sharpe_at_cost(gross, turnover, timeframe, high) > 0 and high < 10_000:
        high *= 2.0
    if _sharpe_at_cost(gross, turnover, timeframe, high) > 0:
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if _sharpe_at_cost(gross, turnover, timeframe, middle) > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def cache_file(cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in symbol).upper()
    return Path(cache_dir) / "mt5" / f"{safe}_{timeframe.upper()}.parquet"


def save_bars(df: pd.DataFrame, cache_dir: str | Path, symbol: str, timeframe: str) -> Path:
    path = cache_file(cache_dir, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    frame.index.name = "ts"
    frame.to_parquet(path)
    try:
        from .freshness import record

        last = frame.index[-1] if len(frame) else None
        if hasattr(last, "to_pydatetime"):
            last = last.to_pydatetime()
        record(
            symbol,
            timeframe,
            last_bar_utc=last,
            fetched_at_utc=datetime.now(timezone.utc),
            source="mt5",
        )
    except Exception:
        pass
    return path


def load_bars(cache_dir: str | Path, symbol: str, timeframe: str) -> pd.DataFrame:
    path = cache_file(cache_dir, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"no existe caché MT5: {path}")
    frame = pd.read_parquet(path)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame.sort_index()


def cache_metadata(df: pd.DataFrame, timeframe: str) -> dict:
    if df.empty:
        return {"rows": 0, "start": None, "end": None, "years": 0.0, "timeframe": timeframe}
    start = df.index[0]
    end = df.index[-1]
    days = max(0.0, (end - start).total_seconds() / 86400)
    return {
        "rows": int(len(df)),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": round(days / 365.25, 2),
        "timeframe": timeframe,
    }


def _spread_bps(
    df: pd.DataFrame,
    point: float,
    tick_spread_bps: pd.Series | None = None,
) -> tuple[pd.Series, bool]:
    if tick_spread_bps is not None and len(tick_spread_bps):
        hourly = pd.to_numeric(tick_spread_bps, errors="coerce").dropna()
        if len(hourly):
            mapped = pd.Series(
                [
                    float(hourly.get(ts.hour, hourly.median()))
                    for ts in df.index
                ],
                index=df.index,
            )
            reliable = bool(len(hourly) >= 2 and float(hourly.median()) > 0.0)
            return mapped, reliable
    if "spread" not in df.columns:
        return pd.Series(3.0, index=df.index), False
    raw = pd.to_numeric(df["spread"], errors="coerce").fillna(0.0)
    close = pd.to_numeric(df["close"], errors="coerce")
    spread = (
        (raw * point / close * 10_000)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    hourly = spread.groupby(spread.index.hour).median()
    mapped = pd.Series(
        [float(hourly.get(ts.hour, hourly.median())) for ts in spread.index],
        index=spread.index,
    )
    reliable = bool(len(hourly) >= 2 and float(spread.median()) > 0.0)
    return mapped, reliable


def _cost_series(value: float | pd.Series, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.reindex(index).astype(float).ffill().bfill()
    return pd.Series(float(value), index=index, dtype=float)


def backtest_intraday(
    df: pd.DataFrame,
    target: pd.Series,
    *,
    timeframe: str = "M15",
    commission_bps: float | pd.Series = 1.0,
    slippage_bps: float = 2.0,
    slippage_optimistic_bps: float | None = None,
    point: float = 0.0001,
    spread_override_bps: float | None = None,
    tick_spread_bps: pd.Series | None = None,
    spread_override_reliable: bool | None = None,
    spread_label: str | None = None,
) -> dict:
    """Retorno neto con costes por spread horario, slippage y comisión.

    `spread_override_bps=0` es solo diagnóstico: conserva la fiabilidad real
    del spread observado, pero elimina su coste para medir el Sharpe bruto.
    `tick_spread_bps` permite usar la mediana horaria de ticks Dukascopy en
    lugar del spread de las velas MT5.
    """
    close = pd.to_numeric(df["close"], errors="coerce")
    pos = target.reindex(df.index).fillna(0.0).clip(-1.0, 1.0).shift(1).fillna(0.0)
    gross = close.pct_change().fillna(0.0) * pos
    turnover = pos.diff().abs().fillna(pos.abs())
    observed_spread, reliable = _spread_bps(
        df, point, tick_spread_bps=tick_spread_bps
    )
    if spread_override_bps is None:
        spread = observed_spread
    else:
        spread = pd.Series(float(spread_override_bps), index=df.index)
        if spread_override_reliable is not None:
            reliable = bool(spread_override_reliable)
    spread_source = spread_label or (
        "ticks" if tick_spread_bps is not None else "mt5_bars"
    )
    commission = _cost_series(commission_bps, df.index)
    optimistic = (
        float(slippage_bps)
        if slippage_optimistic_bps is None
        else float(slippage_optimistic_bps)
    )
    cost_bps = commission + float(slippage_bps) + spread
    cost_optimistic = commission + optimistic + spread
    net = gross - turnover * cost_bps / 10_000.0
    net_optimistic = gross - turnover * cost_optimistic / 10_000.0
    equity = (1.0 + net).cumprod()
    std = float(net.std(ddof=1)) if len(net) > 1 else 0.0
    ann = _bars_per_year(timeframe)
    sharpe = float(net.mean() / std * np.sqrt(ann)) if std > 0 else 0.0
    sharpe_optimistic = _sharpe_returns(net_optimistic, timeframe)
    weights = turnover.clip(lower=0.0)
    weight_sum = float(weights.sum())
    calibrated_cost = (
        float((cost_bps * weights).sum() / weight_sum)
        if weight_sum > 0
        else float(cost_bps.median())
    )
    drawdown = equity / equity.cummax() - 1.0
    return {
        "returns": net,
        "equity": equity,
        "metrics": {
            "total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
            "sharpe": sharpe,
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "num_trades": int((turnover > 0).sum()),
            "bars": int(len(net)),
        },
        "spread_bps_median": float(spread.median()) if len(spread) else 0.0,
        "spread_observed_bps_median": float(observed_spread.median()) if len(observed_spread) else 0.0,
        "spread_override_bps": spread_override_bps,
        "spread_source": spread_source,
        "spread_label": spread_label,
        "spread_tick_hours": (
            int(len(tick_spread_bps)) if tick_spread_bps is not None else 0
        ),
        "spread_reliable": reliable,
        "commission_bps_median": float(commission.median()) if len(commission) else 0.0,
        "calibrated_cost_bps": calibrated_cost,
        "breakeven_cost_bps": break_even_cost_bps(gross, turnover, timeframe),
        "cost_curve_bps": _cost_curve(gross, turnover, timeframe),
        "sharpe_optimistic": sharpe_optimistic,
        "sharpe_conservative": sharpe,
        "slippage_optimistic_bps": optimistic,
    }


def _instrument_session(
    symbol: str,
) -> tuple[tuple[time, time], str, tuple[int, ...]] | None:
    """Sesión del instrumento; None si no hay datos parseables."""
    try:
        from .instruments import get_instrument

        instrument = get_instrument(symbol)
    except Exception:
        return None
    text = str(instrument.session or "").strip()
    session_tz = str(instrument.session_tz or "UTC")
    # "24/5 (pausa diaria ...)" no es una sesión continua: no inventar.
    if text.startswith("24/5") and "pausa" not in text.lower():
        return (time(0, 0), time(0, 0)), session_tz, (0, 1, 2, 3, 4)
    match = re.search(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    start = time(int(match.group(1)), int(match.group(2)))
    end = time(int(match.group(3)), int(match.group(4)))
    return (start, end), session_tz, (0, 1, 2, 3, 4)


def run_event_backtest(
    bars: pd.DataFrame,
    orders: list[dict],
    *,
    point: float = 0.01,
    commission_bps: float = 1.0,
    spread_bps: float = 10.0,
    slippage_bps: float = 5.0,
    fill_pessimism_points: int = 0,
    max_trades_per_day: int = 1,
    force_exit_time: time | None = None,
    session_offset_hours: float = 0.0,
    symbol: str | None = None,
    session_window: tuple[time, time] | None = None,
    session_tz: str | None = None,
    session_weekdays: tuple[int, ...] | None = None,
    session_rules: PropRules | None = None,
    asset_class: str = "cfd",
) -> dict:
    """Ejecuta órdenes limitadas con el modo de eventos (opt-in).

    El modo de serie de ``run_intraday`` no cambia. Este motor solo se usa
    cuando una familia lo declara explícitamente como ``"events"``.

    Reglas: una compra limitada exige ``low < level`` estricto (y ``high >
    level`` para una venta); stop y objetivo en la misma barra resuelven a
    stop; la entrada limitada se llena como mucho al nivel (nunca usa un hueco
    favorable); un stop con hueco se llena al peor precio entre el stop y el
    open; el objetivo se llena al objetivo, nunca en el hueco; la entrada y el
    objetivo no pagan spread, mientras stop y salida forzada pagan spread y
    slippage completos; la comisión se paga por lado;
    ``fill_pessimism_points`` exige superar el nivel por X puntos; se limita
    ``max_trades_per_day``; ``force_exit_time`` se convierte a UTC con el
    offset semanal de sesión. Una orden con ``type="market"`` entra al open
    de la primera barra activa y paga spread + slippage completos; las
    órdenes sin ``type`` siguen siendo limitadas.

    Guarda de sesión: si se pasan ``session_window``/``session_tz`` se
    respetan; si faltan, se intenta inferir de ``instruments`` con ``symbol``.
    Sin datos de sesión devuelve ``session_error`` y no ejecuta fills. Aplica
    además el corte de viernes y el blackout de rollover de
    ``session_rules`` (por defecto FTMO de ``config/prop.yaml``).
    """
    raw_orders = list(orders or [])
    if point <= 0:
        raise ValueError("point debe ser > 0")
    if fill_pessimism_points < 0:
        raise ValueError("fill_pessimism_points no puede ser negativo")
    if max_trades_per_day < 0:
        raise ValueError("max_trades_per_day no puede ser negativo")
    if bars is None or len(bars) == 0:
        return {
            "trades": [],
            "expired": len(raw_orders),
            "ignored": 0,
            "session_error": None,
            "session_skipped": 0,
        }

    frame = bars.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index, utc=True)
    elif frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    else:
        frame.index = frame.index.tz_convert("UTC")
    frame = frame.sort_index()
    for column in ("open", "high", "low", "close"):
        if column not in frame.columns:
            raise ValueError(f"falta columna {column} en bars")

    def session_failure(message: str) -> dict:
        return {
            "trades": [],
            "expired": len(raw_orders),
            "ignored": 0,
            "session_error": message,
            "session_skipped": int(len(frame)),
        }

    resolved_window = session_window
    resolved_tz = session_tz
    resolved_weekdays = (
        tuple(int(day) for day in session_weekdays)
        if session_weekdays is not None
        else None
    )
    if resolved_window is None and symbol:
        inferred = _instrument_session(symbol)
        if inferred is not None:
            resolved_window, inferred_tz, inferred_weekdays = inferred
            if resolved_tz is None:
                resolved_tz = inferred_tz
            if resolved_weekdays is None:
                resolved_weekdays = inferred_weekdays
    if resolved_window is None:
        target = symbol or "el símbolo"
        return session_failure(
            f"sin datos de sesión para {target}: pasa session_window/session_tz"
        )
    if resolved_tz is None:
        resolved_tz = "UTC"
    if resolved_weekdays is None:
        resolved_weekdays = (0, 1, 2, 3, 4)
    try:
        frame.index[0].tz_convert(resolved_tz)
    except Exception as exc:
        return session_failure(f"zona de sesión inválida {resolved_tz!r}: {exc}")
    if session_rules is None:
        try:
            session_rules = from_yaml("ftmo", "challenge", 100_000.0)
        except Exception as exc:
            return session_failure(f"sin reglas de sesión: {exc}")

    commission = float(commission_bps)
    spread = float(spread_bps)
    slippage = float(slippage_bps)
    pessimism = float(fill_pessimism_points) * float(point)
    prepared: list[dict] = []
    for raw in raw_orders:
        side = str(raw.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"lado inválido: {raw.get('side')!r}")
        entry_type = str(raw.get("type") or raw.get("entry_type") or "limit").lower()
        if entry_type not in {"limit", "market"}:
            raise ValueError(f"tipo de entrada inválido: {entry_type!r}")
        required = ["stop", "created_at", "expires_at"]
        if entry_type == "limit":
            required.append("level")
        for key in required:
            if key not in raw:
                raise ValueError(f"orden sin {key}")
        target = raw.get("target")
        target = None if target is None else float(target)
        created = pd.Timestamp(raw["created_at"])
        expires = pd.Timestamp(raw["expires_at"])
        created = (
            created.tz_localize("UTC")
            if created.tzinfo is None
            else created.tz_convert("UTC")
        )
        expires = (
            expires.tz_localize("UTC")
            if expires.tzinfo is None
            else expires.tz_convert("UTC")
        )
        prepared.append(
            {
                "side": side,
                "entry_type": entry_type,
                "level": (
                    float(raw["level"]) if raw.get("level") is not None else None
                ),
                "stop": float(raw["stop"]),
                "target": target,
                "created_at": created,
                "expires_at": expires,
            }
        )

    trades: list[dict] = []
    expired = 0
    ignored = 0
    session_skipped = 0
    pending = list(prepared)
    open_positions: list[dict] = []
    trades_by_day: dict = {}

    def costs(*, add_spread: bool) -> dict:
        return {
            "commission_bps": commission,
            "spread_bps": spread if add_spread else 0.0,
            "slippage_bps": slippage if add_spread else 0.0,
        }

    def force_deadline(ts: pd.Timestamp) -> pd.Timestamp | None:
        if force_exit_time is None:
            return None
        deadline = pd.Timestamp.combine(ts.date(), force_exit_time)
        if deadline.tzinfo is None:
            deadline = deadline.tz_localize("UTC")
        return deadline - pd.Timedelta(hours=float(session_offset_hours))

    def bar_allowed(ts: pd.Timestamp) -> bool:
        local = ts.tz_convert(resolved_tz)
        if local.weekday() not in resolved_weekdays:
            return False
        start, end = resolved_window
        if start != end:
            current = local.time()
            if start < end:
                inside = start <= current <= end
            else:
                inside = current >= start or current <= end
            if not inside:
                return False
        block = session_block(
            session_rules,
            now=local.to_pydatetime(),
            asset_class=asset_class,
        )
        return not block.blocked

    def exit_for(position: dict, bar: pd.Series, ts: pd.Timestamp):
        target = position.get("target")
        side = position["side"]
        if side == "buy":
            stop_hit = float(bar["low"]) <= position["stop"]
            target_hit = target is not None and float(bar["high"]) >= target
        else:
            stop_hit = float(bar["high"]) >= position["stop"]
            target_hit = target is not None and float(bar["low"]) <= target
        if stop_hit:
            if side == "buy":
                price = min(position["stop"], float(bar["open"]))
            else:
                price = max(position["stop"], float(bar["open"]))
            return "stop", price, costs(add_spread=True)
        if target_hit:
            if side == "buy":
                price = min(target, float(bar["high"]))
            else:
                price = max(target, float(bar["low"]))
            return "target", price, costs(add_spread=False)
        deadline = force_deadline(ts)
        if deadline is not None and ts >= deadline:
            return "force_exit", float(bar["close"]), costs(add_spread=True)
        return None

    def close(position: dict, exit_info: tuple, ts: pd.Timestamp) -> dict:
        reason, price, exit_costs = exit_info
        return {
            "side": position["side"],
            "entry_time": position["entry_time"],
            "entry_price": position["entry_price"],
            "exit_time": ts,
            "exit_price": float(price),
            "exit_reason": reason,
            "entry_costs": position["entry_costs"],
            "exit_costs": exit_costs,
        }

    def limit_touched(order: dict, bar: pd.Series) -> bool:
        if order["entry_type"] == "market":
            return True
        if order["side"] == "buy":
            return float(bar["low"]) < order["level"] - pessimism
        return float(bar["high"]) > order["level"] + pessimism

    for ts, bar in frame.iterrows():
        # Órdenes cuya ventana terminó antes de esta barra: expiran.
        remaining = []
        for order in pending:
            if order["expires_at"] < ts:
                expired += 1
            else:
                remaining.append(order)
        pending = remaining

        if not bar_allowed(ts):
            session_skipped += 1
            continue

        # Posiciones abiertas: stop, objetivo o salida forzosa.
        for position in list(open_positions):
            exit_info = exit_for(position, bar, ts)
            if exit_info is not None:
                trades.append(close(position, exit_info, ts))
                open_positions.remove(position)

        # Órdenes pendientes activas en esta barra.
        remaining = []
        for order in pending:
            if order["created_at"] >= ts:
                remaining.append(order)
                continue
            day = ts.date()
            if trades_by_day.get(day, 0) >= max_trades_per_day:
                ignored += 1
                continue
            if not limit_touched(order, bar):
                remaining.append(order)
                continue
            if order["entry_type"] == "market":
                entry_price = float(bar["open"])
            elif order["side"] == "buy":
                entry_price = max(order["level"], float(bar["low"]))
            else:
                entry_price = min(order["level"], float(bar["high"]))
            position = {
                "side": order["side"],
                "entry_time": ts,
                "entry_price": entry_price,
                "stop": order["stop"],
                "target": order["target"],
                "entry_costs": costs(add_spread=order["entry_type"] == "market"),
            }
            trades_by_day[day] = trades_by_day.get(day, 0) + 1
            exit_info = exit_for(position, bar, ts)
            if exit_info is not None:
                trades.append(close(position, exit_info, ts))
            else:
                open_positions.append(position)
        pending = remaining

        # Una orden que vence en esta barra no pasa a la siguiente.
        remaining = []
        for order in pending:
            if order["expires_at"] <= ts:
                expired += 1
            else:
                remaining.append(order)
        pending = remaining

    expired += len(pending)
    return {
        "trades": trades,
        "expired": expired,
        "ignored": ignored,
        "session_error": None,
        "session_skipped": session_skipped,
    }


def _session_mask(index: pd.DatetimeIndex, start_hour: int, end_hour: int) -> pd.Series:
    hours = index.hour
    return pd.Series((hours >= start_hour) & (hours < end_hour), index=index)


def opening_range_breakout(
    df: pd.DataFrame,
    *,
    range_bars: int = 4,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
    start_hour: int = 7,
    end_hour: int = 16,
) -> StrategyResult:
    """Ruptura del rango de apertura de Londres/NY (UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    mask = _session_mask(df.index, start_hour, end_hour)
    for day in sorted({ts.date() for ts in df.index}):
        session = df[mask & (pd.Index(df.index.date) == day)]
        if len(session) < range_bars + 2:
            continue
        rng = session.iloc[:range_bars]
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        pos, hold = 0.0, 0
        for i in range(range_bars, len(session)):
            bar = session.iloc[i]
            if pos == 0.0:
                atr_value = float(atr_s.loc[bar.name]) if bar.name in atr_s.index else 0.0
                if bar["close"] > hi + buffer_atr * atr_value:
                    pos = 1.0
                elif bar["close"] < lo - buffer_atr * atr_value:
                    pos = -1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos = 0.0
                    hold = 0
            target.loc[bar.name] = pos
    return StrategyResult(
        "orb",
        target,
        {"range_bars": range_bars, "buffer_atr": buffer_atr, "max_hold": max_hold},
    )


def trend_pullback(
    df: pd.DataFrame,
    *,
    fast: int = 20,
    slow: int = 100,
    pullback_atr: float = 0.25,
    max_hold: int = 8,
    start_hour: int = 0,
    end_hour: int = 24,
) -> StrategyResult:
    """Tendencia con retroceso a la media rápida, con filtro de sesión opcional."""
    close = df["close"]
    fast_ma, slow_ma, atr_s = ema(close, fast), ema(close, slow), atr(df)
    mask = _session_mask(df.index, start_hour, end_hour)
    target = pd.Series(0.0, index=df.index)
    pos, hold = 0.0, 0
    for ts, row in df.iterrows():
        if not bool(mask.loc[ts]):
            pos, hold = 0.0, 0
            target.loc[ts] = 0.0
            continue
        if pos == 0.0:
            atr_value = float(atr_s.loc[ts])
            if fast_ma.loc[ts] > slow_ma.loc[ts] and row["low"] <= fast_ma.loc[ts] - pullback_atr * atr_value:
                pos = 1.0
            elif fast_ma.loc[ts] < slow_ma.loc[ts] and row["high"] >= fast_ma.loc[ts] + pullback_atr * atr_value:
                pos = -1.0
        else:
            hold += 1
            if hold >= max_hold or (pos > 0 and fast_ma.loc[ts] < slow_ma.loc[ts]) or (pos < 0 and fast_ma.loc[ts] > slow_ma.loc[ts]):
                pos, hold = 0.0, 0
        target.loc[ts] = pos
    return StrategyResult(
        "pullback",
        target,
        {
            "fast": fast,
            "slow": slow,
            "pullback_atr": pullback_atr,
            "max_hold": max_hold,
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
    )


def range_reversal(
    df: pd.DataFrame,
    *,
    lookback: int = 24,
    entry_z: float = 1.5,
    max_hold: int = 8,
    start_hour: int = 7,
    end_hour: int = 16,
) -> StrategyResult:
    """Reversión a la media dentro de un rango móvil y una sesión."""
    close = df["close"]
    mean = close.rolling(lookback).mean()
    std = close.rolling(lookback).std(ddof=0).replace(0.0, np.nan)
    zscore = (close - mean) / std
    mask = _session_mask(df.index, start_hour, end_hour)
    target = pd.Series(0.0, index=df.index)
    pos, hold = 0.0, 0
    for ts in df.index:
        value = float(zscore.loc[ts]) if np.isfinite(zscore.loc[ts]) else 0.0
        if not bool(mask.loc[ts]) or not np.isfinite(zscore.loc[ts]):
            pos, hold = 0.0, 0
            target.loc[ts] = 0.0
            continue
        if pos == 0.0:
            if value <= -entry_z:
                pos = 1.0
            elif value >= entry_z:
                pos = -1.0
        else:
            hold += 1
            if hold >= max_hold or (pos > 0 and value >= 0.0) or (pos < 0 and value <= 0.0):
                pos, hold = 0.0, 0
        target.loc[ts] = pos
    return StrategyResult(
        "range_reversal",
        target,
        {
            "lookback": lookback,
            "entry_z": entry_z,
            "max_hold": max_hold,
            "start_hour": start_hour,
            "end_hour": end_hour,
        },
    )


def orb_ny(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=13, end_hour=20, **kwargs)


def trend_intraday(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=13, end_hour=20, **kwargs)


def overlap_breakout(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=12, end_hour=16, **kwargs)


def london_pullback(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=7, end_hour=16, **kwargs)


def session_trend(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return trend_pullback(df, start_hour=0, end_hour=16, **kwargs)


def tokyo_breakout(df: pd.DataFrame, **kwargs) -> StrategyResult:
    return opening_range_breakout(df, start_hour=0, end_hour=3, **kwargs)


def asian_range_reversal(
    df: pd.DataFrame,
    *,
    buffer_atr: float = 0.1,
    max_hold: int = 8,
) -> StrategyResult:
    """Reversión en el rango asiático (00:00-07:00 UTC)."""
    target = pd.Series(0.0, index=df.index)
    atr_s = atr(df)
    for day in sorted({ts.date() for ts in df.index}):
        day_mask = pd.Index(df.index.date) == day
        asian = df[day_mask & (pd.Index(df.index.hour) < 7)]
        rest = df[day_mask & (pd.Index(df.index.hour) >= 7)]
        if len(asian) < 4 or rest.empty:
            continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        pos, hold = 0.0, 0
        for ts, row in rest.iterrows():
            if pos == 0.0:
                atr_value = float(atr_s.loc[ts])
                if row["close"] > hi + buffer_atr * atr_value:
                    pos = -1.0
                elif row["close"] < lo - buffer_atr * atr_value:
                    pos = 1.0
            else:
                hold += 1
                if hold >= max_hold:
                    pos, hold = 0.0, 0
            target.loc[ts] = pos
    return StrategyResult(
        "asian_rev",
        target,
        {"buffer_atr": buffer_atr, "max_hold": max_hold},
    )


def session_hold(
    df: pd.DataFrame,
    *,
    session: str = "LDN",
    direction: int = 1,
    atr_k: float = 1.5,
    atr_window: int = 14,
) -> StrategyResult:
    """Entrada en la apertura de sesión, salida al cierre de la sesión.

    - `session`: `LDN` (Londres, 08:00 Europe/London) o `NY` (13:30
      Europe/London, con DST).
    - `direction`: `1` en el sentido del retorno de la sesión anterior,
      `-1` en el contrario.
    - Stop: ATR(`atr_window`) × `atr_k`. Una sola operación por sesión.
    """
    close = df["close"].astype(float)
    atr_s = atr(df)
    index = pd.DatetimeIndex(df.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    london = index.tz_convert("Europe/London")

    open_hour = 8 if str(session).upper() == "LDN" else 13
    close_hour = 16 if str(session).upper() == "LDN" else 20

    target = pd.Series(0.0, index=df.index)
    days = {}
    for stamp, local in zip(index, london):
        days.setdefault(local.date(), []).append((stamp, local))

    for day, bars in days.items():
        day_bars = [item for item in bars if open_hour <= item[1].hour < close_hour]
        if not day_bars:
            continue
        # retorno de la sesión anterior (mismo horario, día previo)
        previous = None
        for other_day, other_bars in days.items():
            if other_day >= day:
                continue
            other_session = [
                item for item in other_bars if open_hour <= item[1].hour < close_hour
            ]
            if other_session:
                previous = other_session
        if previous is None:
            continue
        first_open = float(df["open"].get(day_bars[0][0], close.iloc[0]))
        prev_close = float(close.get(previous[-1][0], first_open))
        if not prev_close:
            continue
        move = (first_open / prev_close) - 1.0
        side = int(direction) if move >= 0 else -int(direction)
        atr_value = float(atr_s.get(day_bars[0][0], 0.0))
        if atr_value <= 0:
            continue
        for stamp, _local in day_bars:
            target.loc[stamp] = float(side)
    return StrategyResult(
        "session_hold",
        target,
        {
            "session": session,
            "direction": int(direction),
            "atr_k": float(atr_k),
            "atr_window": int(atr_window),
        },
    )


def fix_flow(
    df: pd.DataFrame,
    *,
    window_min: int = 60,
    side: str = "long_usd",
    fix: str = "ecb",
    vol_filter: float | None = None,
    vol_window: int = 60,
) -> StrategyResult:
    """Flujo del fix: largo USD (corto EURUSD/GBPUSD, largo USDJPY).

    - Ventana: `window_min` minutos antes del fix (ECB 13:15 UTC o London
      16:00 Europe/London, con DST) hasta el fix. Después, plano.
    - `vol_filter`: si se indica, no opera cuando la volatilidad horaria está
      por encima de supercentil `vol_filter` de `vol_window` barras.
    """
    index = pd.DatetimeIndex(df.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    london = index.tz_convert("Europe/London")
    close = df["close"].astype(float)
    ret = close.pct_change()
    vol = ret.rolling(int(vol_window), min_periods=20).std(ddof=0)
    threshold = None
    if vol_filter is not None:
        threshold = float(vol.quantile(float(vol_filter)))

    fix_utc_hour = 13 if str(fix).lower() == "ecb" else 16
    target = pd.Series(0.0, index=df.index)
    for stamp, local in zip(index, london):
        minutes = local.hour * 60 + local.minute
        fix_minute = fix_utc_hour * 60 + 15 if str(fix).lower() == "ecb" else 16 * 60
        offset = fix_minute - minutes
        if offset < 0 or offset > int(window_min):
            continue
        if threshold is not None:
            value = float(vol.get(stamp, 0.0))
            if value > threshold:
                continue
        target.loc[stamp] = 1.0 if str(side) == "long_usd" else -1.0
    return StrategyResult(
        "fix_flow",
        target,
        {
            "window_min": int(window_min),
            "side": side,
            "fix": fix,
            "vol_filter": vol_filter,
            "vol_window": int(vol_window),
        },
    )


STRATEGIES = {
    "orb": opening_range_breakout,
    "pullback": trend_pullback,
    "asian_rev": asian_range_reversal,
    "orb_ny": orb_ny,
    "trend_intraday": trend_intraday,
    "overlap_breakout": overlap_breakout,
    "range_reversal": range_reversal,
    "london_pullback": london_pullback,
    "session_trend": session_trend,
    "tokyo_breakout": tokyo_breakout,
    "session_hold": session_hold,
    "fix_flow": fix_flow,
}


def _combos(grid: dict[str, list]) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def _aligned(series: dict[str, pd.Series]) -> tuple[np.ndarray, list[str]] | None:
    if len(series) < 2:
        return None
    frame = pd.concat(series, axis=1, join="inner").dropna()
    if len(frame) < 80:
        return None
    return returns_matrix({k: frame[k].to_numpy(dtype=float) for k in frame.columns})


def _failure_reason(
    row: dict,
    *,
    profile,
    pbo: dict | None,
    wf_verdict: str,
) -> str:
    """Motivo de descarte de una variante (vacío si pasó)."""
    if row.get("passed"):
        return ""
    parts: list[str] = []
    metrics = row.get("metrics") or {}
    if int(metrics.get("num_trades", 0)) < profile.validation.min_trades:
        parts.append(
            f"trades {int(metrics.get('num_trades', 0))} < {profile.validation.min_trades}"
        )
    dsr = row.get("dsr")
    if dsr is None or dsr < profile.validation.min_dsr:
        parts.append(f"DSR {(dsr or 0):.0%} < {profile.validation.min_dsr:.0%}")
    if pbo is None:
        parts.append("PBO sin datos")
    elif pbo.get("pbo", 1.0) > profile.validation.max_pbo:
        parts.append(f"PBO {pbo['pbo']:.0%} > {profile.validation.max_pbo:.0%}")
    if wf_verdict != "ok":
        parts.append(f"WF {wf_verdict}")
    if not (row.get("regime_gate") or {}).get("passed"):
        parts.append("régimen no aprobado")
    if not row.get("spread_reliable"):
        parts.append("spread no fiable")
    return "; ".join(parts)


def run_intraday(
    df: pd.DataFrame,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "M15",
    paths: int = 500,
    point: float = 0.0001,
    commission_bps: float | None = None,
    slippage_bps: float | None = None,
    slippage_optimistic_bps: float | None = None,
    spread_override_bps: float | None = None,
    tick_spread_bps: pd.Series | None = None,
    spread_override_reliable: bool | None = None,
    spread_label: str | None = None,
    db_path: str | Path | None = None,
    run_id: str | None = None,
    lesson_id: int | None = None,
    record: bool = True,
    families: tuple[str, ...] | None = None,
    dsr_n_trials: int | None = None,
    recalculation: dict | None = None,
) -> dict:
    """Valida las estrategias intradía con los controles existentes."""
    if recalculation is not None and record:
        raise ValueError("un recalculo de coste no puede registrar trials")
    profile = get_profile("intraday_fx")
    if profile is None:
        raise RuntimeError("falta perfil intraday_fx")
    trials_before = count_tests(db_path) if db_path is not None else None
    asset = asset_costs(symbol)
    if commission_bps is None:
        if not asset.verified:
            raise RuntimeError(
                f"comisión sin verificar para {symbol}: no se inventa la cifra"
            )
        commission = asset.commission_bps(df["close"])
        commission_source = asset.source or "sin verificar"
        commission_verified = True
    else:
        commission = float(commission_bps)
        commission_source = "override diagnóstico"
        commission_verified = False
    if slippage_bps is None:
        slippage_bps = asset.slippage_conservative_bps
    if slippage_optimistic_bps is None:
        slippage_optimistic_bps = asset.slippage_optimistic_bps
    commission_median = (
        float(commission.median())
        if isinstance(commission, pd.Series)
        else float(commission)
    )
    selected_families = tuple(families) if families else families_for_symbol(symbol)
    selected_families = tuple(
        name for name in selected_families if family_execution_mode(name) == "series"
    )
    unknown = [name for name in selected_families if name not in INTRADAY_GRIDS]
    if unknown:
        raise ValueError(f"familias intradía desconocidas: {', '.join(unknown)}")
    outcomes = []
    returns_by_id: dict[str, pd.Series] = {}
    for name in selected_families:
        grid = INTRADAY_GRIDS[name]
        for params in _combos(grid):
            result = STRATEGIES[name](df, **params)
            bt = backtest_intraday(
                df,
                result.target,
                timeframe=timeframe,
                commission_bps=commission,
                slippage_bps=slippage_bps,
                slippage_optimistic_bps=slippage_optimistic_bps,
                point=point,
                spread_override_bps=spread_override_bps,
                tick_spread_bps=tick_spread_bps,
                spread_override_reliable=spread_override_reliable,
                spread_label=spread_label,
            )
            key = f"{name}|{json.dumps(params, sort_keys=True)}"
            returns_by_id[key] = bt["returns"]
            outcomes.append(
                {
                    "strategy": name,
                    "params": params,
                    "metrics": bt["metrics"],
                    "spread_bps_median": bt["spread_bps_median"],
                    "spread_observed_bps_median": bt["spread_observed_bps_median"],
                    "spread_source": bt["spread_source"],
                    "spread_tick_hours": bt["spread_tick_hours"],
                    "spread_reliable": bt["spread_reliable"],
                    "commission_bps_median": bt["commission_bps_median"],
                    "calibrated_cost_bps": bt["calibrated_cost_bps"],
                    "breakeven_cost_bps": bt["breakeven_cost_bps"],
                    "cost_curve_bps": bt["cost_curve_bps"],
                    "sharpe_optimistic": bt["sharpe_optimistic"],
                    "sharpe_conservative": bt["sharpe_conservative"],
                }
            )

    sr_values = [row["metrics"]["sharpe"] for row in outcomes]
    sr_std = float(np.std(sr_values, ddof=1)) if len(sr_values) > 1 else 0.0
    n_trials_dsr = (
        int(dsr_n_trials)
        if dsr_n_trials is not None
        else len(outcomes) + (count_tests(db_path) if db_path is not None else 0)
    )
    for row in outcomes:
        row["dsr"] = deflated_sharpe(
            row["metrics"]["sharpe"],
            int(row["metrics"]["bars"]),
            0.0,
            3.0,
            sr_std,
            n_trials_dsr,
        )
        row["dsr_n_trials"] = n_trials_dsr

    aligned = _aligned(returns_by_id)
    pbo = None
    if aligned is not None:
        matrix, _ = aligned
        try:
            pbo = cscv_pbo(matrix, n_slices=16, max_combinations=2_000).to_dict()
        except ValueError:
            pbo = None
    train_len = min(2_016, max(126, len(df) // 4))
    test_len = min(504, max(21, len(df) // 12))
    wf = None
    if aligned is not None:
        try:
            wf = walk_forward(aligned[0], train_len=train_len, test_len=test_len)
        except ValueError:
            wf = None

    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        report = regime_report(returns_by_id[key])
        gate = regime_gate(report)
        row["regime_report"] = report.to_dict()
        row["regime_gate"] = gate.to_dict()
        row["wf_verdict"] = wf.verdict() if wf else "sin datos"
        row["pbo"] = pbo["pbo"] if pbo else None
        row["passed"] = bool(
            row["metrics"]["num_trades"] >= profile.validation.min_trades
            and row["dsr"] is not None
            and row["dsr"] >= profile.validation.min_dsr
            and pbo is not None
            and pbo["pbo"] <= profile.validation.max_pbo
            and wf is not None
            and wf.verdict() == "ok"
            and gate.passed
            and row["spread_reliable"]
        )
        if (
            spread_override_bps == 0
            and commission_median == 0
            and slippage_bps == 0
            and slippage_optimistic_bps == 0
        ):
            # Diagnóstico: nunca cuenta como candidato que avanza.
            row["passed_zero_cost_diagnostic"] = row["passed"]
            row["passed"] = False
        row["failure_reason"] = _failure_reason(
            row,
            profile=profile,
            pbo=pbo,
            wf_verdict=wf.verdict() if wf else "sin datos",
        )

    rules = [from_yaml("ftmo", "challenge", 100_000), from_yaml("topstep", "challenge", 50_000)]
    mc = []
    for row in outcomes:
        key = f"{row['strategy']}|{json.dumps(row['params'], sort_keys=True)}"
        for rule in rules:
            for horizon in DEFAULT_HORIZONS:
                sim = monte_carlo(
                    rule,
                    returns_by_id[key].to_numpy(),
                    n_paths=max(50, paths),
                    horizon=horizon,
                    block_size=5,
                    seed=42,
                )
                mc.append(
                    {
                        "firm": rule.firm,
                        "strategy": row["strategy"],
                        "params": row["params"],
                        "horizon": horizon,
                        "pass_rate": sim["pass_rate"],
                        "breach_rate": sim["breach_rate"],
                    }
                )
    calibrated_values = [
        row["calibrated_cost_bps"]
        for row in outcomes
        if row["calibrated_cost_bps"] is not None
    ]
    run = run_id or uuid.uuid4().hex[:12]
    window_start = str(df.index[0].date()) if len(df.index) else None
    window_end = str(df.index[-1].date()) if len(df.index) else None
    lesson_hypothesis = ""
    if lesson_id is not None:
        lesson = get_lesson(db_path or DEFAULT_DB, lesson_id)
        lesson_hypothesis = str(lesson.get("hypothesis") or "")
    recorded = 0
    if record and db_path is not None:
        for row in outcomes:
            record_trial(
                db_path,
                family=row["strategy"],
                hypothesis=lesson_hypothesis
                or FAMILY_HYPOTHESES.get(
                    row["strategy"], f"Familia intradía {row['strategy']}."
                ),
                symbol=symbol,
                params=row["params"],
                window_start=window_start,
                window_end=window_end,
                result={
                    "metrics": row["metrics"],
                    "dsr": row.get("dsr"),
                    "pbo": row.get("pbo"),
                    "wf_verdict": row.get("wf_verdict"),
                    "regime_passed": (row.get("regime_gate") or {}).get("passed"),
                    "calibrated_cost_bps": row.get("calibrated_cost_bps"),
                    "breakeven_cost_bps": row.get("breakeven_cost_bps"),
                    "cost_curve_bps": row.get("cost_curve_bps"),
                    "passed": row.get("passed"),
                },
                outcome="passed" if row.get("passed") else "failed",
                reason=row.get("failure_reason", ""),
                source="lesson" if lesson_id is not None else "sweep",
                run_id=run,
                lesson_id=lesson_id,
            )
            recorded += 1

    trials_after = count_tests(db_path) if db_path is not None else None
    recalc_info = None
    if recalculation is not None:
        recalc_info = dict(recalculation)
        recalc_info.update(
            {
                "strategy_trials_before": trials_before,
                "strategy_trials_after": trials_after,
                "dsr_counter_unchanged": trials_before == trials_after,
                "dsr_n_trials": n_trials_dsr,
                "trials_recorded": recorded,
            }
        )
        if trials_before != trials_after:
            raise RuntimeError(
                "el recalculo modifico el contador DSR "
                f"({trials_before} -> {trials_after})"
            )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": cache_metadata(df, timeframe),
        "profile": profile.id,
        "run_id": run,
        "trials_recorded": recorded,
        "recalculation": recalc_info,
        "window": {"start": window_start, "end": window_end},
        "dsr_n_trials": n_trials_dsr,
        "families": list(selected_families),
        "costs": {
            "commission_bps_median": commission_median,
            "commission_source": commission_source,
            "commission_verified": commission_verified,
            "slippage_bps": float(slippage_bps),
            "slippage_optimistic_bps": float(slippage_optimistic_bps),
            "spread_override_bps": spread_override_bps,
            "diagnostic_zero_costs": spread_override_bps == 0
            and commission_median == 0
            and slippage_bps == 0
            and slippage_optimistic_bps == 0,
        },
        "cost_model": {
            "symbol": symbol,
            "commission": {
                "verified": commission_verified,
                "per_lot_usd": asset.commission_per_lot_usd,
                "side": asset.commission_side,
                "source": commission_source,
                "source_date": asset.source_date,
                "effective_from": asset.effective_from,
                "source_url": asset.source_url,
                "median_bps": commission_median,
                "verified_at": "2026-11-08",
            },
            "spread": {
                "source": (
                    spread_label
                    or (
                        "Dukascopy ticks: mediana por hora"
                        if tick_spread_bps is not None
                        else "MT5 bars: columna spread, mediana por hora"
                    )
                ),
                "stat": (
                    "p75"
                    if spread_label and "p75" in str(spread_label).lower()
                    else "mediana"
                ),
                "hourly": True,
                "tick_hours": (
                    int(len(tick_spread_bps)) if tick_spread_bps is not None else 0
                ),
                "override_bps": spread_override_bps,
                "median_bps": (
                    float(np.median([row["spread_bps_median"] for row in outcomes]))
                    if outcomes
                    else None
                ),
                "reliable": all(row["spread_reliable"] for row in outcomes),
            },
            "slippage": {
                "optimistic_bps": float(slippage_optimistic_bps),
                "conservative_bps": float(slippage_bps),
                "assumption": asset.slippage_assumption,
            },
            "calibrated_cost_bps_median": (
                float(np.median(calibrated_values)) if calibrated_values else None
            ),
            "breakeven_definition": (
                "bps uniformes por unidad de turnover a los que el Sharpe neto "
                "cruza 0; 0 si el Sharpe bruto ya es <= 0"
            ),
        },
        "spread_reliable": all(row["spread_reliable"] for row in outcomes),
        "pbo": pbo,
        "walk_forward": wf.to_dict() if wf else None,
        "walk_forward_verdict": wf.verdict() if wf else "sin datos",
        "n_trials": len(outcomes),
        "passed": sum(1 for row in outcomes if row["passed"]),
        "outcomes": outcomes,
        "monte_carlo": mc,
    }


def render_markdown(report: dict) -> str:
    costs = report.get("costs") or {}
    model = report.get("cost_model") or {}
    commission = model.get("commission") or {}
    spread_model = model.get("spread") or {}
    slippage = model.get("slippage") or {}
    commission_bps = costs.get("commission_bps_median")
    spread_bps = spread_model.get("median_bps")
    lines = [
        "# Investigación intradía forex/CFD",
        "",
        f"- Símbolo: {report['symbol']} · {report['timeframe']}",
        f"- Barras: {report['bars']['rows']:,} · {report['bars']['start']} → {report['bars']['end']} · {report['bars']['years']} años",
        f"- Perfil: {report['profile']} · DSR n_trials={report.get('dsr_n_trials', report['n_trials'])}",
        f"- Spread realista: {'sí' if report['spread_reliable'] else 'NO — resultados no confiables'}",
        (
            f"- Comisión: {commission_bps:.3f} bps/lado · "
            f"{commission.get('source') or 'sin verificar'}"
            f"{' · ' + str(commission.get('source_date')) if commission.get('source_date') else ''}"
        ),
        (
            f"- Spread: {spread_bps:.3f} bps ({spread_model.get('stat', 'mediana')}; {spread_model.get('source') or 'sin datos'})"
            if spread_bps is not None
            else "- Spread: sin datos"
        ),
        (
            f"- Slippage: optimista {slippage.get('optimistic_bps')} bps / "
            f"conservador {slippage.get('conservative_bps')} bps por lado"
        ),
        (
            "- **Diagnóstico zero-cost: no usar para aprobar estrategias.**"
            if costs.get("diagnostic_zero_costs")
            else "- Modelo de costes calibrado; el avance usa el escenario conservador."
        ),
        f"- PBO: {report['pbo']['pbo']:.1%}" if report.get("pbo") else "- PBO: sin datos",
        f"- Walk-forward: {report['walk_forward_verdict']}",
        f"- Pasan: {report['passed']}/{len(report['outcomes'])}",
        "",
        "> Solo informativo; no activa bots ni cambia criterios. "
        "El riesgo intradía real puede ser mayor que el modelado.",
        "",
        "## Estrategias",
        "",
        "| Estrategia | Parámetros | Trades | Sharpe | MaxDD | DSR | WF | Régimen | Spread | Pasa |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    recalc = report.get("recalculation")
    if recalc:
        unchanged = bool(recalc.get("dsr_counter_unchanged"))
        insert_at = lines.index("## Estrategias")
        lines[insert_at:insert_at] = [
            "## Recálculo de coste",
            "",
            f"- Motivo: {recalc.get('reason') or 'recalculo de coste'}",
            f"- Spread bróker p75: {recalc.get('broker_spread_bps')} bps",
            f"- DSR n_trials original: {recalc.get('original_dsr_n_trials')} · usado: {recalc.get('dsr_n_trials')}",
            f"- `strategy_trials`: {recalc.get('strategy_trials_before')} → {recalc.get('strategy_trials_after')} · sin cambios: {'sí' if unchanged else 'NO'}",
            "- Mismas variantes; **no se crearon trials nuevos**.",
            "",
        ]
    for row in report["outcomes"]:
        lines.append(
            f"| {row['strategy']} | `{row['params']}` | {row['metrics']['num_trades']} | "
            f"{row['metrics']['sharpe']:.2f} | {row['metrics']['max_drawdown']:.1%} | "
            f"{(row['dsr'] or 0):.1%} | {row['wf_verdict']} | "
            f"{'ok' if row['regime_gate']['passed'] else 'no'} | "
            f"{'sí' if row['spread_reliable'] else 'no'} | "
            f"{'sí' if row['passed'] else 'no'} |"
        )
    def _cost_text(value: float | None) -> str:
        return "—" if value is None else f"{value:.2f}"

    lines += [
        "",
        "## Coste de equilibrio",
        "",
        "> Coste uniforme en bps por unidad de turnover. 0 bps = bruto; "
        "el avance solo usa el escenario conservador.",
        "",
        "| Estrategia | Parámetros | 0 bps | 0.5 bps | 1 bps | 2 bps | 3 bps | Equilibrio | Calibrado | Pasa |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["outcomes"]:
        curve = row.get("cost_curve_bps") or {}
        breakeven = row.get("breakeven_cost_bps")
        lines.append(
            f"| {row['strategy']} | `{row['params']}` | "
            f"{_cost_text(curve.get('0.0'))} | {_cost_text(curve.get('0.5'))} | "
            f"{_cost_text(curve.get('1.0'))} | {_cost_text(curve.get('2.0'))} | "
            f"{_cost_text(curve.get('3.0'))} | "
            f"{'sin cruce' if breakeven is None else f'{breakeven:.2f}'} | "
            f"{_cost_text(row.get('calibrated_cost_bps'))} | "
            f"{'sí' if row.get('passed') else 'no'} |"
        )
    lines += [
        "",
        "## Monte Carlo 22/44/120d",
        "",
        "| Firma | Estrategia | Horizonte | Pasa | Revienta |",
        "|---|---|---|---|---|",
    ]
    for row in report["monte_carlo"][:40]:
        lines.append(
            f"| {row['firm']} | {row['strategy']} | {row['horizon']}d | "
            f"{row['pass_rate']:.1%} | {row['breach_rate']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def write(report: dict, out_dir: str | Path = ROOT / "reports" / "research") -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "intraday.json"
    md_path = out / "intraday.md"
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    markdown = render_markdown(report)
    json_path.write_text(text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    safe = "".join(
        char if char.isalnum() or char in "-_." else "_"
        for char in str(report.get("symbol") or "sin_datos").upper()
    )
    asset_dir = out / "intraday"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_json = asset_dir / f"{safe}.json"
    asset_md = asset_dir / f"{safe}.md"
    asset_json.write_text(text, encoding="utf-8")
    asset_md.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path),
        "md": str(md_path),
        "asset_json": str(asset_json),
        "asset_md": str(asset_md),
    }


__all__ = [
    "DEFAULT_HORIZONS",
    "FAMILY_EXECUTION_MODES",
    "INTRADAY_GRIDS",
    "STRATEGIES",
    "asian_range_reversal",
    "backtest_intraday",
    "break_even_cost_bps",
    "cache_file",
    "cache_metadata",
    "family_execution_mode",
    "load_bars",
    "opening_range_breakout",
    "render_markdown",
    "run_event_backtest",
    "run_intraday",
    "save_bars",
    "trend_pullback",
]
