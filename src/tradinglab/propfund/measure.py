"""Spreads medidos por cuenta CFD → ``config/propfund/costs.yaml``.

* Fuente: tabla ``broker_spreads`` (``tradinglab.broker_costs``), con filas
  horarias medidas sobre ticks del bróker (``source="broker"``).
* ``spread_price`` = **mediana** de las medianas horarias (``median_bps``).
  ``spread_p75_price`` = **percentil 75** de los p75 horarios (``p75_bps``),
  más conservador que la mediana de los p75.
* Los bps se convierten a unidades de precio con el último **cierre
  completado** disponible en la caché local de MT5 (``data/cache/mt5``).
  No se descarga nada ni se inventa un precio: si no hay cierre, el símbolo
  queda ``Sin datos``.
* ``broker_spreads`` no guarda la cuenta: la medición se atribuye al terminal
  que la produjo. Hoy solo ``ftmo_demo`` (espejo de CFD-001) ejecuta
  ``lab costs broker``.
* Si falta un dato: ``null`` + ``needs_verification: true``. Nunca se
  sobrescribe un valor medido con ``null``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from ..broker_costs import DB_PATH, SOURCE_BROKER, load_spreads
from ..config import ROOT
from .costs import PROPFUND_COSTS_PATH, broker_symbol
from .instruments import resolve
from .models import Market
from .registry import load_registry

MT5_CACHE_DIR = ROOT / "data" / "cache" / "mt5"
AI_TRADER_PATH = ROOT / "config" / "ai_trader.yaml"
#: Minutos de cada vela; el cierre de una vela es su apertura + duración.
TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
#: Aviso si la medición o el cierre tienen más horas que esto.
STALE_HOURS = 48.0


@dataclass
class SymbolMeasure:
    symbol: str
    broker_symbol: str
    status: str                      # ok | sin datos | sin cierre
    hours: int = 0
    ticks: int = 0
    from_ts: str | None = None
    measured_at: str | None = None
    p50_bps: float | None = None
    p75_bps: float | None = None
    last_close: float | None = None
    last_close_ts: str | None = None
    close_timeframe: str | None = None
    spread_price: float | None = None
    spread_p75_price: float | None = None
    slippage_price: float | None = None
    source: str = ""
    stale_hours: float | None = None
    close_age_hours: float | None = None

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# ------------------------------------------------------------------ utilidades
def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")


def _iso_max(values) -> str | None:
    best = None
    for value in values:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        try:
            ts = _utc(value)
        except (TypeError, ValueError):
            continue
        if best is None or ts > best:
            best = ts
    return best.isoformat() if best is not None else None


def _iso_min(values) -> str | None:
    best = None
    for value in values:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        try:
            ts = _utc(value)
        except (TypeError, ValueError):
            continue
        if best is None or ts < best:
            best = ts
    return best.isoformat() if best is not None else None


def _age_hours(iso: str | None, now) -> float | None:
    if not iso:
        return None
    return round((_utc(now) - _utc(iso)).total_seconds() / 3600.0, 1)


def price_from_bps(bps: float, close: float, *, decimals: int = 6) -> float:
    """Convierte un spread en bps a unidades de precio con el cierre dado."""
    return round(float(bps) / 10_000.0 * float(close), decimals)


# ------------------------------------------------------------------ lecturas
def load_slippage_prices(path: str | Path = AI_TRADER_PATH) -> dict[str, float]:
    """Slippage por símbolo de ``config/ai_trader.yaml`` (solo lectura).

    El archivo es un componente protegido: se lee, nunca se escribe.
    """
    target = Path(path)
    if not target.exists():
        return {}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    raw = ((data.get("global") or {}).get("slippage_price") or {})
    prices: dict[str, float] = {}
    for key, value in raw.items():
        try:
            prices[resolve(str(key)).id] = float(value)
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def read_last_close(cache_dir: str | Path, broker: str, *, now=None) -> dict | None:
    """Último cierre completado en la caché MT5, sin red.

    Prueba todas las temporalidades disponibles y se queda con la vela cuyo
    cierre es más reciente. Descarta la vela en curso (cierre > ``now``).
    """
    root = Path(cache_dir)
    if not root.exists():
        return None
    now_ts = _utc(now or datetime.now(timezone.utc))
    best: dict | None = None
    for timeframe, minutes in TIMEFRAME_MINUTES.items():
        path = root / f"{broker.upper()}_{timeframe}.parquet"
        if not path.exists():
            continue
        try:
            frame = pd.read_parquet(path, columns=["close"])
        except (OSError, ValueError, KeyError):
            continue
        if frame.empty:
            continue
        index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
        delta = pd.Timedelta(minutes=minutes)
        for position in range(len(index) - 1, -1, -1):
            close_ts = index[position] + delta
            if close_ts > now_ts:
                continue        # vela en curso o futura
            price = float(frame["close"].iloc[position])
            if not math.isfinite(price) or price <= 0:
                break
            candidate = {
                "price": price,
                "bar_open": index[position].isoformat(),
                "close_ts": close_ts.isoformat(),
                "timeframe": timeframe,
            }
            if best is None or _utc(candidate["close_ts"]) > _utc(best["close_ts"]):
                best = candidate
            break
    return best


def spread_stats(rows: pd.DataFrame | None) -> dict:
    """p50 de las medianas horarias y p75 de los p75 horarios."""
    empty = {
        "hours": 0, "ticks": 0, "p50_bps": None, "p75_bps": None,
        "from_ts": None, "measured_at": None,
    }
    if rows is None or len(rows) == 0:
        return empty
    medians = pd.to_numeric(rows.get("median_bps"), errors="coerce")
    p75s = pd.to_numeric(rows.get("p75_bps"), errors="coerce")
    medians = medians.dropna() if medians is not None else pd.Series(dtype=float)
    p75s = p75s.dropna() if p75s is not None else pd.Series(dtype=float)
    ticks = (
        pd.to_numeric(rows["n_ticks"], errors="coerce").fillna(0)
        if "n_ticks" in rows else pd.Series(dtype=float)
    )
    return {
        "hours": int(rows["hour_utc"].nunique()) if "hour_utc" in rows else 0,
        "ticks": int(ticks.sum()),
        "p50_bps": float(medians.median()) if len(medians) else None,
        "p75_bps": float(p75s.quantile(0.75)) if len(p75s) else None,
        "from_ts": _iso_min(rows["from_ts"] if "from_ts" in rows else []),
        "measured_at": _iso_max(rows["to_ts"] if "to_ts" in rows else []),
    }


# ------------------------------------------------------------------ escritura
def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


class _CostDumper(yaml.SafeDumper):
    """Evita la notación científica en los precios (1.0e-05 → 0.00001)."""


def _represent_float(dumper: yaml.SafeDumper, value: float):
    text = f"{value:.10f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return dumper.represent_scalar("tag:yaml.org,2002:float", text)


_CostDumper.add_representer(float, _represent_float)


def _apply_updates(text: str, account_id: str, updates: dict[str, dict]) -> str:
    """Reescribe solo el bloque ``symbols`` de la cuenta, conservando el resto."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)

    start = None
    for position, line in enumerate(lines):
        if _indent(line) == 2 and line.strip() == f"{account_id}:":
            start = position
            break
    if start is None:
        raise ValueError(f"{account_id}: no existe el bloque de la cuenta en costs.yaml")

    end = len(lines)
    for position in range(start + 1, len(lines)):
        stripped = lines[position].strip()
        if stripped and not stripped.startswith("#") and _indent(lines[position]) <= 2:
            end = position
            break

    symbols_line = None
    for position in range(start + 1, end):
        if _indent(lines[position]) == 4 and lines[position].strip() == "symbols:":
            symbols_line = position
            break
    if symbols_line is None:
        raise ValueError(f"{account_id}: sin bloque 'symbols' en costs.yaml")

    block_end = end
    for position in range(symbols_line + 1, end):
        stripped = lines[position].strip()
        if stripped and not stripped.startswith("#") and _indent(lines[position]) <= 4:
            block_end = position
            break

    loaded = yaml.safe_load(newline.join(lines[symbols_line:block_end])) or {}
    symbols = dict(loaded.get("symbols") or {})
    for symbol, values in updates.items():
        entry = dict(symbols.get(symbol) or {})
        entry.update(values)
        symbols[symbol] = entry

    rendered = yaml.dump(
        {"symbols": symbols}, Dumper=_CostDumper, sort_keys=False, allow_unicode=True,
        default_flow_style=False, width=10_000,
    ).rstrip("\n").split("\n")
    lines[symbols_line:block_end] = [f"    {line}" if line else line for line in rendered]
    return newline.join(lines)


# ------------------------------------------------------------------ sincronización
def sync_spreads(
    account_id: str,
    *,
    write: bool = False,
    db_path: str | Path = DB_PATH,
    costs_path: str | Path = PROPFUND_COSTS_PATH,
    cache_dir: str | Path = MT5_CACHE_DIR,
    ai_trader_path: str | Path = AI_TRADER_PATH,
    source: str = SOURCE_BROKER,
    now=None,
    close_prices: dict[str, float] | None = None,
    registry=None,
) -> dict:
    """Mide y (con ``write=True``) escribe los spreads de una cuenta CFD.

    Dry-run por defecto. Devuelve el informe con un registro por símbolo.
    ``close_prices`` permite inyectar cierres en tests; en producción se leen
    de la caché local de MT5.
    """
    reg = registry or load_registry()
    account = reg.accounts.get(account_id)
    if account is None:
        raise ValueError(f"{account_id}: cuenta no registrada en config/propfund/accounts.yaml")
    if account.market is not Market.CFD:
        raise ValueError(f"{account_id}: sync-spreads solo aplica a cuentas CFD")

    costs_file = Path(costs_path)
    with costs_file.open("r", encoding="utf-8", newline="") as handle:
        raw_text = handle.read()   # conserva los finales de línea (CRLF en Windows)
    document = yaml.safe_load(raw_text) or {}
    profile = ((document.get("accounts") or {}).get(account_id) or {})
    existing = dict(profile.get("symbols") or {})
    if not existing:
        raise ValueError(f"{account_id}: sin bloque de símbolos en {costs_file}")

    order = list(existing)
    for symbol in account.allowed_instruments:
        if symbol not in order:
            order.append(symbol)

    slippages = load_slippage_prices(ai_trader_path)
    now_ts = _utc(now or datetime.now(timezone.utc))
    measures: list[SymbolMeasure] = []
    warnings: list[str] = []
    updates: dict[str, dict] = {}

    for symbol in order:
        try:
            item = resolve(symbol)
        except KeyError:
            warnings.append(f"{symbol}: fuera del universo Prop Fund; se omite")
            continue
        if item.market is not Market.CFD:
            continue
        broker = broker_symbol(item.id)
        current = dict(existing.get(item.id) or {})
        stats = spread_stats(load_spreads(db_path, symbol=broker, source=source))

        if close_prices is not None:
            price = close_prices.get(item.id)
            last = {"price": float(price), "close_ts": None, "timeframe": "inyectado"} if price else None
        else:
            last = read_last_close(cache_dir, broker, now=now_ts)

        slippage = slippages.get(item.id)
        if slippage is None and current.get("slippage_price") is not None:
            slippage = float(current["slippage_price"])
        slippage_source = (
            "config/ai_trader.yaml global.slippage_price"
            if item.id in slippages else ("costs.yaml" if slippage is not None else "Sin datos")
        )

        status = "sin datos"
        spread_price = None
        spread_p75_price = None
        if stats["p50_bps"] is None or stats["p75_bps"] is None:
            source_text = (
                f"spread: Sin datos (broker_spreads sin filas para {broker}) "
                f"· slippage: {slippage_source}"
            )
        elif last is None:
            status = "sin cierre"
            source_text = (
                f"spread: Sin datos de cierre local para convertir bps ({broker}) "
                f"· slippage: {slippage_source}"
            )
        else:
            status = "ok"
            spread_price = price_from_bps(stats["p50_bps"], last["price"])
            spread_p75_price = price_from_bps(stats["p75_bps"], last["price"])
            source_text = (
                f"spread: broker_spreads · {broker} · p50 de medianas horarias y "
                f"p75 de p75 horarios ({stats['hours']} h) "
                f"· slippage: {slippage_source}"
            )

        measure = SymbolMeasure(
            symbol=item.id,
            broker_symbol=broker,
            status=status,
            hours=stats["hours"],
            ticks=stats["ticks"],
            from_ts=stats["from_ts"],
            measured_at=stats["measured_at"],
            p50_bps=stats["p50_bps"],
            p75_bps=stats["p75_bps"],
            last_close=last["price"] if last else None,
            last_close_ts=last["close_ts"] if last else None,
            close_timeframe=last["timeframe"] if last else None,
            spread_price=spread_price,
            spread_p75_price=spread_p75_price,
            slippage_price=slippage,
            source=source_text,
            stale_hours=_age_hours(stats["measured_at"], now_ts),
            close_age_hours=_age_hours(last["close_ts"] if last else None, now_ts),
        )
        measures.append(measure)

        if status == "ok":
            update = {
                "spread_price": spread_price,
                "spread_p75_price": spread_p75_price,
                "source": source_text,
                "measured_at": stats["measured_at"],
                "needs_verification": False,
            }
            if slippage is not None:
                update["slippage_price"] = slippage
            updates[item.id] = update
        else:
            warnings.append(f"{item.id}: {'Sin datos' if status == 'sin datos' else 'sin cierre local'}")
            if current.get("spread_price") is None and current.get("spread_p75_price") is None:
                update = {
                    "spread_price": None,
                    "spread_p75_price": None,
                    "needs_verification": True,
                    "source": source_text,
                }
                if slippage is not None:
                    update["slippage_price"] = slippage
                updates[item.id] = update

        if measure.stale_hours is not None and measure.stale_hours > STALE_HOURS:
            warnings.append(
                f"{item.id}: medición de hace {measure.stale_hours:.0f} h (>{STALE_HOURS:.0f} h)"
            )
        if measure.close_age_hours is not None and measure.close_age_hours > STALE_HOURS:
            warnings.append(
                f"{item.id}: último cierre de hace {measure.close_age_hours:.0f} h "
                f"(>{STALE_HOURS:.0f} h)"
            )

    written = False
    if write and updates:
        costs_file.write_text(
            _apply_updates(raw_text, account_id, updates), encoding="utf-8", newline=""
        )
        written = True

    return {
        "account": account_id,
        "firm": account.firm,
        "market": account.market.value,
        "dry_run": not write,
        "written": written,
        "costs_path": str(costs_file),
        "source": source,
        "symbols": [measure.as_dict() for measure in measures],
        "planned": sorted(updates),
        "warnings": warnings,
        "ok": all(measure.status == "ok" for measure in measures) if measures else False,
    }


__all__ = [
    "AI_TRADER_PATH",
    "MT5_CACHE_DIR",
    "STALE_HOURS",
    "SymbolMeasure",
    "load_slippage_prices",
    "price_from_bps",
    "read_last_close",
    "spread_stats",
    "sync_spreads",
]
