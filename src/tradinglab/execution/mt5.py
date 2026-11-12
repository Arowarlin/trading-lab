from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import floor
from pathlib import Path

import pandas as pd

from ..audit import append_hashed
from ..db import connect, utcnow
from ..instruments import Instrument, InstrumentError, get_instrument
from .mt5_offsets import (
    infer_bar_offsets,
    map_offsets,
    offset_periods,
    weekly_offsets,
)


class MT5Error(RuntimeError):
    pass


class MT5IdentityError(MT5Error):
    """La cuenta conectada no es la esperada. Nunca se envía una orden tras esto."""


def _mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise MT5Error(
            "Falta el paquete MetaTrader5. Instálalo con: uv pip install MetaTrader5"
        ) from exc
    return mt5


def server_offset_from_tick(tick_time: float, now: float) -> float | None:
    """Deduce el offset del servidor MT5 a partir de un tick.

    Un tick fresco cumple ``tick_time ≈ now + offset``. Se redondea a medias
    horas y se exige un residuo pequeño. Los ticks viejos (raw negativo) se
    rechazan: antes producían offsets negativos falsos al cerrar el mercado.
    """
    raw = float(tick_time) - float(now)
    offset = round(raw / 1_800.0) * 0.5
    residual = raw - offset * 3_600.0
    if 0 <= offset <= 14 and abs(residual) < 300:
        return offset
    return None


def normalize_volume(volume: float, min_lot: float, max_lot: float, step: float) -> float:
    """Ajusta el volumen al step del bróker, siempre hacia abajo y dentro de límites."""
    if volume <= 0:
        return 0.0
    if step <= 0:
        raise MT5Error("volume_step inválido")
    v = min(float(volume), float(max_lot))
    v = floor(v / step + 1e-9) * step
    v = round(v, 8)
    if v < min_lot - 1e-12:
        return 0.0
    return v


class MT5Broker:
    """Adaptador para MetaTrader 5 (forex y CFDs).

    Salvaguardas:
      * `dry_run=True` valida y devuelve la orden sin enviarla.
      * Guard de identidad: exige el `login`/`server` configurados y, por
        defecto, una cuenta DEMO. Si no coincide, aborta antes de operar.
      * Si la cuenta es REAL exige ALLOW_LIVE=YES (igual que Alpaca).
      * Exige que "Algo Trading" esté activo en el terminal.
    """

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        magic: int = 20261105,
        deviation: int = 20,
        dry_run: bool = True,
        db_path: str | Path | None = None,
        timeout_ms: int = 60_000,
        server_utc_offset_hours: float | None = None,
        require_demo: bool = True,
    ) -> None:
        self.path = str(path) if path else None
        self.login = int(login) if login else None
        self.password = password or os.getenv("MT5_PASSWORD")
        self.server = server or os.getenv("MT5_SERVER")
        self.magic = int(magic)
        self.deviation = int(deviation)
        self.dry_run = bool(dry_run)
        self.require_demo = bool(require_demo)
        self.db_path = Path(db_path) if db_path else None
        self.timeout_ms = int(timeout_ms)
        self.server_utc_offset_hours = server_utc_offset_hours
        self._server_offset = float(server_utc_offset_hours or 0.0)
        self._offset_source = "config" if server_utc_offset_hours is not None else "unknown"
        self._offset_cache = (
            Path(db_path).parent / "cache" / "mt5_offset.json" if db_path else None
        )
        self.rate_offset_periods: list[dict] = []
        self._connected = False

    # ------------------------------------------------------------- conexión

    def connect(self) -> dict:
        mt5 = _mt5()
        if self._connected:
            return self.health()

        kwargs: dict = {"timeout": self.timeout_ms}
        if self.path:
            kwargs["path"] = self.path
        if self.login:
            kwargs["login"] = self.login
            if self.password:
                kwargs["password"] = self.password
            if self.server:
                kwargs["server"] = self.server

        if not mt5.initialize(**kwargs):
            code, msg = mt5.last_error()
            raise MT5Error(f"No se pudo inicializar MT5 ({code}): {msg}")

        account = mt5.account_info()
        if account is None:
            mt5.shutdown()
            raise MT5Error(
                "MT5 arrancó pero no hay cuenta conectada. Abre el terminal e inicia sesión."
            )

        problems = self._identity_problems(account)
        if problems:
            mt5.shutdown()
            raise MT5IdentityError(
                "Guard de identidad MT5: "
                + "; ".join(problems)
                + ". No se enviará ninguna orden. Corrige MT5_LOGIN/MT5_SERVER "
                "o desactiva require_demo solo si es intencional."
            )

        self._connected = True
        if self.server_utc_offset_hours is None:
            self._resolve_offset(self._detect_server_offset(mt5))
        return self.health()

    def _identity_problems(self, account) -> list[str]:
        """Comprueba login, servidor y tipo de cuenta antes de operar."""
        mode = {0: "demo", 1: "contest", 2: "real"}.get(int(account.trade_mode), "desconocido")
        problems: list[str] = []
        if self.login is not None and int(account.login) != int(self.login):
            problems.append(f"login esperado {self.login}, conectado {int(account.login)}")
        if self.server and str(account.server).strip().lower() != str(self.server).strip().lower():
            problems.append(f"servidor esperado {self.server}, conectado {account.server}")
        if self.require_demo and mode == "real":
            problems.append("cuenta REAL detectada con require_demo=True")
        return problems

    def _require_identity(self) -> None:
        """Revalidación justo antes de enviar: la cuenta pudo cambiar en caliente."""
        mt5 = self._require()
        account = mt5.account_info()
        if account is None:
            raise MT5IdentityError("sin cuenta MT5 al revalidar identidad")
        problems = self._identity_problems(account)
        if problems:
            raise MT5IdentityError(
                "Guard de identidad MT5: " + "; ".join(problems) + ". Orden cancelada."
            )

    def _detect_server_offset(self, mt5) -> float | None:
        """Deduce el desfase del servidor comparando un tick fresco con UTC.

        Los servidores MT5 suelen ir en GMT+2/GMT+3, no en UTC. Si el mercado
        está cerrado el tick es viejo y no se puede deducir: se usa el valor
        configurado (o 0.0).
        """
        now = time.time()
        for sym in ("EURUSD", "USDJPY", "XAUUSD", "GBPUSD"):
            t = mt5.symbol_info_tick(sym)
            if t is None or not t.time:
                continue
            offset = server_offset_from_tick(t.time, now)
            if offset is not None:
                return offset
        return None

    def _load_cached_offset(self) -> float | None:
        """Último offset detectado, útil con el mercado cerrado."""
        if not self._offset_cache or not self._offset_cache.exists():
            return None
        try:
            data = json.loads(self._offset_cache.read_text(encoding="utf-8"))
            offset = float(data["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        stored_server = str(data.get("server") or "")
        if self.server and stored_server and stored_server.lower() != self.server.lower():
            return None
        stored_login = data.get("login")
        if self.login is not None and stored_login is not None and int(stored_login) != self.login:
            return None
        return offset

    def _save_cached_offset(self, offset: float) -> None:
        if not self._offset_cache:
            return
        try:
            self._offset_cache.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "offset": float(offset),
                "server": self.server,
                "login": self.login,
                "detected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            self._offset_cache.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _resolve_offset(self, detected: float | None) -> None:
        """Decide el offset: config > detección fresca > caché > desconocido."""
        if self.server_utc_offset_hours is not None:
            self._server_offset = float(self.server_utc_offset_hours)
            self._offset_source = "config"
            return
        if detected is not None:
            self._server_offset = float(detected)
            self._offset_source = "detectado"
            self._save_cached_offset(float(detected))
            return
        cached = self._load_cached_offset()
        if cached is not None:
            self._server_offset = cached
            self._offset_source = "cache"
            return
        self._offset_source = "unknown"

    def _to_utc(self, ts: int | float) -> datetime:
        """Convierte una hora del servidor MT5 a UTC real."""
        server = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        return server - timedelta(hours=self._server_offset)

    def shutdown(self) -> None:
        if self._connected:
            _mt5().shutdown()
            self._connected = False

    def __enter__(self) -> "MT5Broker":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()

    def _require(self):
        if not self._connected:
            self.connect()
        return _mt5()

    # ---------------------------------------------------------------- estado

    def health(self) -> dict:
        mt5 = _require_mt5(self._connected)
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or account is None:
            raise MT5Error("terminal o cuenta no disponibles")
        mode = {0: "demo", 1: "contest", 2: "real"}.get(int(account.trade_mode), "desconocido")
        return {
            "connected": bool(terminal.connected),
            "trade_allowed": bool(terminal.trade_allowed),
            "algo_trading": bool(terminal.trade_allowed),
            "path": terminal.path,
            "build": terminal.build,
            "login": int(account.login),
            "name": account.name,
            "server": account.server,
            "company": account.company,
            "currency": account.currency,
            "mode": mode,
            "leverage": int(account.leverage),
            "balance": float(account.balance),
            "equity": float(account.equity),
            "margin": float(account.margin),
            "margin_free": float(account.margin_free),
            "margin_level": float(account.margin_level),
            "profit": float(account.profit),
            "server_utc_offset_hours": self._server_offset if self._offset_source != "unknown" else None,
            "offset_source": self._offset_source,
            "offset_known": self._offset_source != "unknown",
            "identity_ok": not self._identity_problems(account),
            "expected_login": self.login,
            "expected_server": self.server,
            "require_demo": self.require_demo,
        }

    def account(self) -> dict:
        return self.health()

    def symbol_spec(self, symbol: str) -> dict:
        mt5 = self._require()
        info = mt5.symbol_info(symbol)
        if info is None:
            if not mt5.symbol_select(symbol, True):
                raise MT5Error(f"Símbolo no disponible en el terminal: {symbol}")
            info = mt5.symbol_info(symbol)
        if info is None:
            raise MT5Error(f"symbol_info devolvió None para {symbol}")
        if not info.visible:
            mt5.symbol_select(symbol, True)
        return {
            "symbol": info.name,
            "digits": int(info.digits),
            "point": float(info.point),
            "tick_size": float(info.trade_tick_size or info.point),
            "tick_value": float(info.trade_tick_value),
            "contract_size": float(info.trade_contract_size),
            "volume_min": float(info.volume_min),
            "volume_max": float(info.volume_max),
            "volume_step": float(info.volume_step),
            "stops_level": int(info.trade_stops_level),
            "filling_mode": int(info.filling_mode),
            "spread": int(info.spread),
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
            "bid": float(info.bid),
            "ask": float(info.ask),
            "trade_mode": int(info.trade_mode),
        }

    def symbols(self) -> list[dict]:
        """Símbolos del terminal con su grupo (`path`) y su spec.

        Solo lectura: no selecciona, no modifica y no envía nada. El grupo sale
        del `path` del bróker ("Forex", "Metals CFD", "Cash II CFD"...) y es más
        fiable que adivinar por el nombre.
        """
        mt5 = self._require()
        rows = mt5.symbols_get() or []
        found: list[dict] = []
        for item in rows:
            raw_path = getattr(item, "path", "") or ""
            parts = [part for part in raw_path.split("\\") if part]
            found.append(
                {
                    "symbol": item.name,
                    "group": parts[0] if parts else "",
                    "path": raw_path,
                    "digits": int(item.digits),
                    "tick_size": float(item.trade_tick_size or item.point),
                    "contract_size": float(item.trade_contract_size),
                    "volume_min": float(item.volume_min),
                }
            )
        return found

    def instrument(self, symbol: str) -> Instrument:
        """Especificación del bróker combinada con el registro local."""
        spec = self.symbol_spec(symbol)
        try:
            base = get_instrument(symbol)
        except InstrumentError:
            base = Instrument(
                symbol=symbol.upper(),
                asset_class="forex" if spec["tick_value"] < 5 else "equity",
                quote_ccy=spec["currency_profit"] or "USD",
                tick_size=spec["tick_size"],
                tick_value=spec["tick_value"],
                contract_size=spec["contract_size"],
            )
        return replace(
            base,
            symbol=spec["symbol"],
            tick_size=spec["tick_size"],
            tick_value=spec["tick_value"],
            contract_size=spec["contract_size"],
            min_lot=spec["volume_min"],
            max_lot=spec["volume_max"],
            lot_step=spec["volume_step"],
        )

    def tick(self, symbol: str) -> dict:
        mt5 = self._require()
        t = mt5.symbol_info_tick(symbol)

        # El símbolo puede existir pero no estar en Market Watch: sin selección
        # MT5 devuelve bid/ask a 0 hasta que el terminal se suscribe.
        if t is None or (t.bid <= 0 and t.ask <= 0):
            mt5.symbol_select(symbol, True)
            for _ in range(30):
                time.sleep(0.1)
                t = mt5.symbol_info_tick(symbol)
                if t is not None and (t.bid > 0 or t.ask > 0):
                    break

        if t is None or (t.bid <= 0 and t.ask <= 0):
            raise MT5Error(
                f"sin tick para {symbol}. Añádelo a Market Watch en el terminal "
                "y comprueba que la cuenta tiene datos del servidor."
            )
        return {
            "symbol": symbol,
            "bid": float(t.bid),
            "ask": float(t.ask),
            "last": float(t.last),
            "spread": float(t.ask - t.bid),
            "time": self._to_utc(t.time),
            "server_time": datetime.fromtimestamp(t.time, tz=timezone.utc),
            "volume": float(t.volume),
        }

    def rates(self, symbol: str, timeframe: str = "H1", count: int = 500) -> pd.DataFrame:
        """Velas del terminal, indexadas en UTC real con offset por periodo.

        El offset de cada barra se infiere de los bordes semanales (apertura del
        domingo y cierre del viernes en hora de servidor) contra las 17:00 de
        America/New_York. No se aplica un único offset a todo el histórico.
        """
        mt5 = self._require()
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
        }
        key = timeframe.upper()
        if key not in tf_map:
            raise MT5Error(f"timeframe no soportado: {timeframe}. Usa {', '.join(tf_map)}")

        self.symbol_spec(symbol)  # asegura que está seleccionado
        raw = mt5.copy_rates_from_pos(symbol, tf_map[key], 0, int(count))
        if raw is None or len(raw) == 0:
            raise MT5Error(f"sin histórico para {symbol} {key}: {mt5.last_error()}")

        df = pd.DataFrame(raw)
        server_time = pd.to_datetime(df["time"], unit="s", utc=True)
        try:
            offsets = infer_bar_offsets(server_time, key)
        except ValueError as exc:
            raise MT5Error(
                f"No se pudo inferir el offset por periodo para {symbol} {key}: {exc}. "
                "No se aplica un offset global."
            ) from exc
        self.rate_offset_periods = offset_periods(server_time, offsets)
        df["time"] = server_time - pd.to_timedelta(offsets.to_numpy(), unit="h")
        df = df.set_index("time").rename(columns={"tick_volume": "volume"})
        cols = ["open", "high", "low", "close", "volume", "spread"]
        return df[[c for c in cols if c in df.columns]].astype(float)

    def copy_ticks(
        self,
        symbol: str,
        desde: datetime,
        hasta: datetime,
    ) -> pd.DataFrame:
        """Ticks del bróker en UTC, etiquetados con el offset semanal.

        Solo lectura: usa ``copy_ticks_range`` con ``COPY_TICKS_ALL``. El offset
        de cada semana se infiere de barras M15 alrededor del rango (el mismo
        método que ``rates``), no de un offset global. Devuelve ``ts`` UTC,
        ``bid`` y ``ask``; los ticks inválidos (bid/ask <= 0 o ask < bid) se
        descartan. Si no hay ticks, devuelve un DataFrame vacío.
        """
        if not isinstance(desde, datetime) or not isinstance(hasta, datetime):
            raise MT5Error("desde y hasta deben ser datetime")
        if desde.tzinfo is None:
            desde = desde.replace(tzinfo=timezone.utc)
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=timezone.utc)
        desde = desde.astimezone(timezone.utc)
        hasta = hasta.astimezone(timezone.utc)
        if hasta <= desde:
            raise MT5Error("hasta debe ser posterior a desde")

        mt5 = self._require()
        self.symbol_spec(symbol)
        offset = float(self._server_offset)

        # Barras M15 holgadas para confirmar apertura/cierre semanal y DST.
        bar_from = desde - timedelta(days=14)
        bar_to = hasta + timedelta(days=2)
        bars = mt5.copy_rates_range(
            symbol,
            mt5.TIMEFRAME_M15,
            bar_from + timedelta(hours=offset),
            bar_to + timedelta(hours=offset),
        )
        if bars is None or len(bars) == 0:
            raise MT5Error(
                f"sin barras M15 para inferir el offset semanal de {symbol}"
            )
        bar_frame = pd.DataFrame(bars)
        if "time" not in bar_frame.columns:
            raise MT5Error(f"barras sin columna time para {symbol}")
        server_bars = pd.to_datetime(bar_frame["time"], unit="s", utc=True)
        try:
            offsets = infer_bar_offsets(server_bars, "M15")
        except ValueError as exc:
            raise MT5Error(
                f"No se pudo inferir el offset semanal de {symbol}: {exc}"
            ) from exc
        self.rate_offset_periods = offset_periods(server_bars, offsets)
        weekly = weekly_offsets(server_bars, offsets)

        # La API interpreta las fechas en hora del servidor. Se añade el offset
        # actual y un día de margen; luego se filtra por UTC real.
        pad = timedelta(days=1)
        raw = mt5.copy_ticks_range(
            symbol,
            desde + timedelta(hours=offset) - pad,
            hasta + timedelta(hours=offset) + pad,
            mt5.COPY_TICKS_ALL,
        )
        if raw is None or len(raw) == 0:
            return pd.DataFrame(columns=["ts", "bid", "ask"])
        frame = pd.DataFrame(raw)
        if "time" in frame.columns:
            server_ticks = pd.to_datetime(frame["time"], unit="s", utc=True)
        elif "time_msc" in frame.columns:
            server_ticks = pd.to_datetime(frame["time_msc"], unit="ms", utc=True)
        else:
            raise MT5Error(f"ticks sin columna time/time_msc para {symbol}")
        mapped = map_offsets(server_ticks, weekly)
        frame["ts"] = pd.DatetimeIndex(server_ticks) - pd.to_timedelta(
            mapped.to_numpy(), unit="h"
        )
        frame = frame[["ts", "bid", "ask"]].copy()
        frame["bid"] = pd.to_numeric(frame["bid"], errors="coerce")
        frame["ask"] = pd.to_numeric(frame["ask"], errors="coerce")
        frame = frame[
            (frame["bid"] > 0)
            & (frame["ask"] > 0)
            & (frame["ask"] >= frame["bid"])
        ]
        frame = frame[(frame["ts"] >= desde) & (frame["ts"] <= hasta)]
        return frame.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)

    def positions(self, symbol: str | None = None) -> list[dict]:
        mt5 = self._require()
        raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if raw is None:
            return []
        out = []
        for p in raw:
            side = "buy" if int(p.type) == mt5.POSITION_TYPE_BUY else "sell"
            out.append(
                {
                    "ticket": int(p.ticket),
                    "symbol": p.symbol,
                    "side": side,
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "price_current": float(p.price_current),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "profit": float(p.profit),
                    "swap": float(getattr(p, "swap", 0.0)),
                    "commission": float(getattr(p, "commission", 0.0)),
                    "magic": int(p.magic),
                    "comment": p.comment,
                    "time": self._to_utc(p.time),
                }
            )
        return out

    def snapshot(self, prices: dict[str, float] | None = None) -> dict:
        acc = self.health()
        positions = self.positions()
        return {
            "cash": acc["balance"],
            "balance": acc["balance"],
            "equity": acc["equity"],
            "margin": acc["margin"],
            "margin_free": acc["margin_free"],
            "positions": positions,
            "positions_value": sum(p["volume"] for p in positions),
            "open_lots": sum(p["volume"] for p in positions),
        }

    # -------------------------------------------------------------- órdenes

    def _assert_can_trade(self, mt5) -> dict:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or account is None:
            raise MT5Error("terminal o cuenta no disponibles")

        real = int(account.trade_mode) == mt5.ACCOUNT_TRADE_MODE_REAL
        if real and os.getenv("ALLOW_LIVE") != "YES":
            raise MT5Error(
                "Cuenta REAL bloqueada. Define ALLOW_LIVE=YES solo si es intencional."
            )
        if not terminal.trade_allowed:
            raise MT5Error(
                "El terminal tiene 'Algo Trading' desactivado. Actívalo antes de enviar órdenes."
            )
        if not account.trade_expert and real:
            raise MT5Error("La cuenta no permite trading experto (trade_expert=false).")
        return {"real": real, "trade_allowed": bool(terminal.trade_allowed)}

    def _filling_candidates(self, filling_mode: int, mt5) -> list[int]:
        out = []
        if filling_mode & 2:
            out.append(mt5.ORDER_FILLING_IOC)
        if filling_mode & 1:
            out.append(mt5.ORDER_FILLING_FOK)
        out.append(mt5.ORDER_FILLING_RETURN)
        return out

    def _round_price(self, price: float, digits: int) -> float:
        return round(float(price), int(digits))

    def submit_market(
        self,
        symbol: str,
        volume: float,
        *,
        sl: float | None = None,
        tp: float | None = None,
        comment: str = "tradinglab",
        magic: int | None = None,
        dry_run: bool | None = None,
        bot: str = "manual",
        reason: str = "",
        run_id: int | None = None,
        risk_usd: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        """Envía una orden a mercado. `volume` positivo = compra, negativo = venta."""
        if volume == 0:
            raise ValueError("volume no puede ser 0")

        dry = self.dry_run if dry_run is None else bool(dry_run)
        mt5 = self._require()
        self._assert_can_trade(mt5)
        if not dry:
            # Defensa en profundidad: la cuenta pudo cambiar desde connect().
            self._require_identity()

        side = "buy" if volume > 0 else "sell"
        spec = self.symbol_spec(symbol)
        vol = normalize_volume(
            abs(volume), spec["volume_min"], spec["volume_max"], spec["volume_step"]
        )
        if vol <= 0:
            raise MT5Error(
                f"volumen {abs(volume):g} menor que el mínimo {spec['volume_min']:g} "
                f"(step {spec['volume_step']:g})"
            )

        tick = self.tick(symbol)
        price = tick["ask"] if volume > 0 else tick["bid"]
        digits = spec["digits"]
        effective_magic = self.magic if magic is None else int(magic)

        stop_distance = spec["stops_level"] * spec["point"]
        if sl is not None:
            sl = self._round_price(sl, digits)
            if abs(price - sl) < stop_distance:
                raise MT5Error(
                    f"SL a {abs(price - sl):.5f} del precio; el bróker exige "
                    f"al menos {stop_distance:.5f}"
                )
        if tp is not None:
            tp = self._round_price(tp, digits)
            if abs(tp - price) < stop_distance:
                raise MT5Error(
                    f"TP a {abs(tp - price):.5f} del precio; el bróker exige "
                    f"al menos {stop_distance:.5f}"
                )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": spec["symbol"],
            "volume": vol,
            "type": mt5.ORDER_TYPE_BUY if volume > 0 else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": self.deviation,
            "magic": effective_magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp

        if dry:
            return {
                "ok": True,
                "dry_run": True,
                "symbol": spec["symbol"],
                "side": side,
                "volume": vol,
                "price": price,
                "sl": sl,
                "tp": tp,
                "request": request,
            }

        last_error: str | None = None
        for filling in self._filling_candidates(spec["filling_mode"], mt5):
            request["type_filling"] = filling
            result = mt5.order_send(request)
            if result is None:
                last_error = f"order_send=None ({mt5.last_error()})"
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                try:
                    from ..tca import record_fill as tca_record
                    from ..tca import slippage_bps as tca_slip

                    fill_px = float(result.price or price)
                    tca_record(
                        self.db_path,
                        bot=bot,
                        symbol=spec["symbol"],
                        side=side,
                        signal_px=price,
                        order_px=price,
                        fill_px=fill_px,
                        slippage_bps=tca_slip(price, fill_px, side),
                        expected_cost_bps=float(getattr(self, "slippage_bps", 0.0) or 0.0),
                        realized_cost_bps=abs(fill_px - price) / price * 10_000.0,
                    )
                except Exception:
                    pass
                return self._record(
                    result=result,
                    spec=spec,
                    side=side,
                    vol=vol,
                    sl=sl,
                    tp=tp,
                    bot=bot,
                    reason=reason,
                    run_id=run_id,
                    risk_usd=risk_usd,
                    stop_price=stop_price,
                    magic=effective_magic,
                )
            if result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                raise MT5Error(
                    f"MT5 rechazó la orden [{result.retcode}]: {result.comment}"
                )
            last_error = f"filling {filling}: {result.comment}"

        raise MT5Error(f"No se pudo enviar la orden: {last_error}")

    def _record(
        self,
        *,
        result,
        spec,
        side,
        vol,
        sl,
        tp,
        bot,
        reason,
        run_id,
        risk_usd=None,
        stop_price=None,
        magic: int | None = None,
    ) -> dict:
        payload = {
            "ok": True,
            "dry_run": False,
            "order_id": int(result.order),
            "deal_id": int(result.deal),
            "retcode": int(result.retcode),
            "symbol": spec["symbol"],
            "side": side,
            "volume": float(result.volume or vol),
            "price": float(result.price),
            "sl": sl,
            "tp": tp,
            "comment": result.comment,
            "magic": magic,
        }
        if self.db_path:
            try:
                with connect(self.db_path) as con:
                    append_hashed(
                        con,
                        "orders",
                        {
                            "ts": utcnow(),
                            "ticker": spec["symbol"],
                            "side": side,
                            "qty": float(result.volume or vol),
                            "order_type": "market",
                            "status": "filled",
                            "broker_id": str(result.order),
                            "bot": bot,
                            "reason": reason,
                            "run_id": run_id,
                            "risk_usd": None if risk_usd is None else float(risk_usd),
                            "stop_price": None if stop_price is None else float(stop_price),
                            "magic": None if magic is None else int(magic),
                        },
                    )
            except Exception:
                pass
        return payload

    def modify_position(
        self, ticket: int, *, sl: float | None = None, tp: float | None = None
    ) -> dict:
        mt5 = self._require()
        self._assert_can_trade(mt5)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5Error(f"no existe la posición {ticket}")
        p = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": p.symbol,
            "position": int(ticket),
            "sl": float(sl if sl is not None else p.sl),
            "tp": float(tp if tp is not None else p.tp),
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            raise MT5Error(f"no se pudo modificar {ticket}: {getattr(result, 'comment', mt5.last_error())}")
        return {"ok": True, "ticket": ticket, "sl": request["sl"], "tp": request["tp"]}

    def close_position(self, ticket: int, volume: float | None = None) -> dict:
        mt5 = self._require()
        self._assert_can_trade(mt5)
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise MT5Error(f"no existe la posición {ticket}")
        p = positions[0]
        vol = float(volume if volume is not None else p.volume)
        if vol > float(p.volume) + 1e-9:
            raise MT5Error(f"volumen {vol} > posición {p.volume}")

        spec = self.symbol_spec(p.symbol)
        tick = self.tick(p.symbol)
        is_buy = int(p.type) == mt5.POSITION_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "position": int(ticket),
            "volume": vol,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick["bid"] if is_buy else tick["ask"],
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        last_error = None
        for filling in self._filling_candidates(spec["filling_mode"], mt5):
            request["type_filling"] = filling
            result = mt5.order_send(request)
            if result is None:
                last_error = f"order_send=None ({mt5.last_error()})"
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return {
                    "ok": True,
                    "ticket": ticket,
                    "order_id": int(result.order),
                    "deal_id": int(result.deal),
                    "volume": float(result.volume or vol),
                    "price": float(result.price),
                }
            if result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                raise MT5Error(f"MT5 rechazó el cierre [{result.retcode}]: {result.comment}")
            last_error = f"filling {filling}: {result.comment}"
        raise MT5Error(f"No se pudo cerrar {ticket}: {last_error}")

    # -------------------------------------------------------------- histórico

    def history_deals(
        self, start: datetime, end: datetime
    ) -> list[dict]:
        """Deals de compra/venta del terminal en UTC. Solo lectura.

        Devuelve una fila por deal (entrada o salida), con `deal_id` único y
        `ts_utc` convertido desde la hora del servidor. Los deals de balance
        (tipo 2+) se descartan porque no son operaciones.
        """
        mt5 = self._require()
        raw = mt5.history_deals_get(start, end) or []
        out: list[dict] = []
        for deal in raw:
            kind = int(getattr(deal, "type", -1))
            if kind not in (0, 1):
                continue
            out.append(
                {
                    "deal_id": int(deal.ticket),
                    "order_id": int(getattr(deal, "order", 0) or 0),
                    "position_id": int(getattr(deal, "position_id", 0) or 0),
                    "symbol": str(getattr(deal, "symbol", "") or ""),
                    "side": "buy" if kind == 0 else "sell",
                    "volume": float(deal.volume),
                    "price": float(deal.price),
                    "commission": float(getattr(deal, "commission", 0.0) or 0.0),
                    "swap": float(getattr(deal, "swap", 0.0) or 0.0),
                    "profit": float(getattr(deal, "profit", 0.0) or 0.0),
                    "magic": int(getattr(deal, "magic", 0) or 0),
                    "entry": int(getattr(deal, "entry", 0) or 0),
                    "ts_utc": self._to_utc(deal.time).isoformat(),
                }
            )
        out.sort(key=lambda item: (item["ts_utc"], item["deal_id"]))
        return out

    def balance_curve(self, days: int = 180) -> pd.Series:
        """Curva de balance realizada reconstruida desde los deals (no incluye flotante)."""
        mt5 = self._require()
        acc = mt5.account_info()
        if acc is None:
            raise MT5Error("sin cuenta")
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=days), now + timedelta(days=1))
        if not deals:
            return pd.Series(dtype=float)

        rows = sorted(deals, key=lambda d: (d.time, d.ticket))
        pnl = [(int(d.time), float(d.profit) + float(d.swap) + float(d.commission)) for d in rows]
        total = sum(p for _, p in pnl)
        running = float(acc.balance) - total
        idx, values = [], []
        for ts, delta in pnl:
            running += delta
            idx.append(self._to_utc(ts))
            values.append(running)
        return pd.Series(values, index=pd.to_datetime(idx)).sort_index()

    def equity_series(self, days: int = 180) -> pd.Series:
        return self.balance_curve(days)


def copy_ticks(symbol: str, desde: datetime, hasta: datetime) -> pd.DataFrame:
    """Ticks del bróker en UTC. Solo lectura.

    Llama a ``mt5.copy_ticks_range`` con ``COPY_TICKS_ALL`` y devuelve las
    columnas exactas ``ts`` (UTC, tz-aware), ``bid`` y ``ask``, ordenadas por
    ``ts``. Si MT5 devuelve ``None`` o vacío, devuelve un DataFrame vacío con
    esas columnas; no lanza excepción, no rellena datos y no escribe en disco.
    """
    mt5 = _mt5()
    raw = mt5.copy_ticks_range(symbol, desde, hasta, mt5.COPY_TICKS_ALL)
    columns = ["ts", "bid", "ask"]
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(raw)
    stamps = pd.to_datetime(frame["time"], unit="s", utc=True)
    out = pd.DataFrame(
        {
            "ts": stamps,
            "bid": pd.to_numeric(frame["bid"], errors="coerce"),
            "ask": pd.to_numeric(frame["ask"], errors="coerce"),
        }
    )
    return out.sort_values("ts").reset_index(drop=True)


def _require_mt5(connected: bool):
    if not connected:
        raise MT5Error("MT5 no está conectado: llama a connect() primero")
    return _mt5()


__all__ = ["MT5Broker", "MT5Error", "normalize_volume"]
