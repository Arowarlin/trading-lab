from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import floor
from pathlib import Path

import pandas as pd

from ..db import connect, utcnow
from ..instruments import Instrument, InstrumentError, get_instrument


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
        """Velas del terminal, indexadas en UTC real (corrige el desfase del servidor)."""
        if self._offset_source == "unknown":
            raise MT5Error(
                "No se pudo determinar el offset del servidor MT5 (mercado cerrado y "
                "sin caché). Configura mt5.server_utc_offset_hours o reintenta con el "
                "mercado abierto."
            )
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
        df["time"] = (
            pd.to_datetime(df["time"], unit="s", utc=True)
            - pd.Timedelta(hours=self._server_offset)
        )
        df = df.set_index("time").rename(columns={"tick_volume": "volume"})
        cols = ["open", "high", "low", "close", "volume", "spread"]
        return df[[c for c in cols if c in df.columns]].astype(float)

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
            "magic": self.magic if magic is None else int(magic),
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
                )
            if result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                raise MT5Error(
                    f"MT5 rechazó la orden [{result.retcode}]: {result.comment}"
                )
            last_error = f"filling {filling}: {result.comment}"

        raise MT5Error(f"No se pudo enviar la orden: {last_error}")

    def _record(self, *, result, spec, side, vol, sl, tp, bot, reason, run_id) -> dict:
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
        }
        if self.db_path:
            try:
                with connect(self.db_path) as con:
                    con.execute(
                        "INSERT INTO orders(ts, ticker, side, qty, order_type, status, broker_id, "
                        "bot, reason, run_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            utcnow(),
                            spec["symbol"],
                            side,
                            float(result.volume or vol),
                            "market",
                            "filled",
                            str(result.order),
                            bot,
                            reason,
                            run_id,
                        ),
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


def _require_mt5(connected: bool):
    if not connected:
        raise MT5Error("MT5 no está conectado: llama a connect() primero")
    return _mt5()


__all__ = ["MT5Broker", "MT5Error", "normalize_volume"]
