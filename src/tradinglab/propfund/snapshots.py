"""Snapshots y posiciones de solo lectura para el riesgo global del Prop Fund.

* **Nunca envía órdenes**: solo se adjunta al terminal MT5 ya abierto y lee
  cuenta y posiciones. No cierra ni modifica nada.
* **Sin credenciales**: no pasa ``login``/``password``/``server`` a
  ``MetaTrader5.initialize`` ni llama a ``mt5.login``. Si ``terminal64.exe`` no
  está en ejecución devuelve ``Sin datos`` sin arrancar el terminal.
* **Fail-closed**: exige cuenta DEMO y que el login y el servidor coincidan con
  los configurados (``MT5_LOGIN``/``MT5_SERVER``). Cualquier duda es
  ``Sin datos``, nunca un dato inventado.
* Las posiciones de los magics protegidos (EA ``us100-ftmo1``, ``ai_trader`` y
  forward) se leen por ``magic`` y se suman al riesgo global; el módulo no las
  toca.

El adaptador ``MT5Broker`` se importa tal cual: aquí solo se sustituye su
``connect()`` por una conexión adjunta al terminal abierto. ``shutdown()`` no se
llama nunca: la conexión IPC de este proceso se libera al terminar el proceso.
"""

from __future__ import annotations

import copy
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..accounts import load_accounts, rules_for_account
from ..config import ROOT, Settings
from ..execution.mt5 import MT5Broker, MT5Error
from .instruments import notional_usd, resolve
from .models import CfdCategory, ConnectionState, Market, PropAccount
from .registry import CONFIG_DIR, RegistryError, load_registry
from .risk import AccountSnapshot, PositionView, exposure_by_underlying

#: Cuenta del carril FTMO que hoy está conectada al terminal.
CONNECTED_LEGACY_ACCOUNT = "ftmo_demo"

#: TTL de la caché del bloque de exposición (segundos).
CACHE_TTL_SECONDS = 60.0

_SELL = {"sell", "short"}

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_READ_LOCK = threading.Lock()


# --------------------------------------------------------------------- utilidades


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mt5_module():
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise MT5Error(
            "Falta el paquete MetaTrader5. Instálalo con: uv pip install MetaTrader5"
        ) from exc
    return mt5


def _terminal_running() -> bool | None:
    """¿Hay un ``terminal64.exe`` en ejecución? Solo lectura, sin dependencias.

    Devuelve ``None`` si no se pudo comprobar (sistema sin ``tasklist`` o error).
    """
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip().lower()
    if not text or "no tasks" in text or "no hay tareas" in text:
        return False
    return "terminal64.exe" in text


def _note(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


# ------------------------------------------------------------------ conexión MT5


class AttachOnlyBroker(MT5Broker):
    """``MT5Broker`` que solo se adjunta al terminal abierto, sin credenciales.

    Reutiliza ``health()``, ``positions()``, ``symbol_spec()``,
    ``equity_series()`` y ``history_deals()`` del adaptador original. No llama a
    ``mt5.login()`` ni a ``mt5.shutdown()`` y jamás usa métodos de órdenes.
    """

    def __init__(self, *, expected_login: int, expected_server: str, **kwargs) -> None:
        super().__init__(dry_run=True, require_demo=True, **kwargs)
        self.expected_login = int(expected_login)
        self.expected_server = str(expected_server)

    def connect(self) -> dict:
        mt5 = _mt5_module()
        if self._connected:
            return self.health()

        running = _terminal_running()
        if running is False:
            raise MT5Error("MT5 no está abierto")
        if running is None:
            raise MT5Error("Sin datos: no se pudo comprobar si MT5 está abierto")

        kwargs: dict = {"timeout": self.timeout_ms}
        if self.path:
            kwargs["path"] = self.path
        # Sin login/password/server a propósito: el terminal es compartido con
        # el EA us100-ftmo1, ai_trader y el forward y no puede re-loguearse.
        if not mt5.initialize(**kwargs):
            code, msg = mt5.last_error()
            raise MT5Error(f"No se pudo adjuntar a MT5 ({code}): {msg}")

        account = mt5.account_info()
        if account is None:
            raise MT5Error("Sin datos: MT5 no tiene ninguna cuenta iniciada")
        problems = self._attach_problems(account)
        if problems:
            raise MT5Error("Cuenta MT5 no verificada: " + "; ".join(problems))

        self._connected = True
        if self.server_utc_offset_hours is None and self._offset_source == "unknown":
            try:
                self._resolve_offset(self._detect_server_offset(mt5))
            except Exception:
                pass
        return self.health()

    def _attach_problems(self, account) -> list[str]:
        mode = {0: "demo", 1: "contest", 2: "real"}.get(int(account.trade_mode), "desconocido")
        problems: list[str] = []
        if mode != "demo":
            problems.append(f"cuenta {mode}; se exige demo")
        if int(account.login) != self.expected_login:
            problems.append(f"login esperado {self.expected_login}, conectado {int(account.login)}")
        server = str(account.server or "").strip().lower()
        if server != self.expected_server.strip().lower():
            problems.append(f"servidor esperado {self.expected_server}, conectado {account.server}")
        return problems


def _expected_identity(settings: Settings) -> tuple[int, str] | None:
    login = settings.mt5.login
    server = settings.mt5.server
    if login is None or not str(server or "").strip():
        return None
    return int(login), str(server).strip()


def default_broker_factory(account: PropAccount, *, settings: Settings | None = None) -> AttachOnlyBroker:
    """Crea el broker de solo lectura para la cuenta espejo de ``ftmo_demo``."""
    legacy = account.legacy_account or ""
    if legacy != CONNECTED_LEGACY_ACCOUNT:
        raise MT5Error(
            f"Sin datos: identidad MT5 no configurada para {legacy or account.id}"
        )
    settings = settings or Settings.load()
    expected = _expected_identity(settings)
    if expected is None:
        raise MT5Error(
            "Sin datos: define MT5_LOGIN y MT5_SERVER para verificar la cuenta ftmo_demo"
        )
    return AttachOnlyBroker(
        expected_login=expected[0],
        expected_server=expected[1],
        path=settings.mt5.terminal_path,
        timeout_ms=5000,
        server_utc_offset_hours=settings.mt5.server_utc_offset_hours,
    )


# ------------------------------------------------------------------ atribución


def magic_lanes(account_id: str) -> dict[int, tuple[str, str]]:
    """``magic → (estrategia, carril)`` leído de la configuración existente."""
    lanes: dict[int, tuple[str, str]] = {}
    try:
        from ..ea_registry import load_eas

        for ea in load_eas():
            if ea.account != account_id:
                continue
            strategy = ea.bot_id
            magics = {int(ea.magic), *(int(item) for item in ea.managed_magics)}
            for magic in magics:
                lanes[magic] = (strategy, "ea")
    except Exception:
        pass
    try:
        from ..ai_trader import load_config as load_ai_config

        cfg = load_ai_config() or {}
        if str(cfg.get("account") or "") == account_id:
            for style, item in (cfg.get("styles") or {}).items():
                magic = (item or {}).get("magic")
                if magic is not None:
                    lanes[int(magic)] = (f"ai:{style}", "ai_trader")
    except Exception:
        pass
    try:
        from ..forward_intraday import load_forward_bots

        for bot in load_forward_bots():
            if bot.account != account_id:
                continue
            lanes[int(bot.magic)] = (bot.strategy or f"forward:{bot.id}", "forward")
    except Exception:
        pass
    return lanes


def _lane_for(magic: int, lanes: dict[int, tuple[str, str]]) -> tuple[str, str]:
    if magic in lanes:
        return lanes[magic]
    if magic == 0:
        return "manual", "manual"
    return f"desconocido:{magic}", "desconocida"


# --------------------------------------------------------------------- posiciones


@dataclass(frozen=True)
class ObservedPosition:
    """``PositionView`` + los datos de MT5 necesarios para mostrarla."""

    position: PositionView
    ticket: int
    magic: int
    lane: str
    symbol_broker: str
    sl: float = 0.0
    tp: float = 0.0
    floating_usd: float = 0.0

    def as_dict(self) -> dict:
        pos = self.position
        item = resolve(pos.symbol)
        notional = notional_usd(
            pos.symbol, pos.quantity, pos.price, contract_size=pos.contract_size
        )
        return {
            "account": pos.account,
            "firm": pos.firm,
            "strategy": pos.strategy,
            "lane": self.lane,
            "symbol": self.symbol_broker or pos.symbol,
            "instrument": item.id,
            "underlying": item.underlying,
            "market": item.market.value,
            "side": "long" if pos.quantity > 0 else "short",
            "quantity": pos.quantity,
            "price": pos.price,
            "contract_size": pos.contract_size,
            "notional_usd": None if notional is None else round(notional, 2),
            "risk_usd": None if pos.risk_usd is None else round(pos.risk_usd, 2),
            "magic": self.magic,
            "ticket": self.ticket,
            "sl": self.sl or None,
            "tp": self.tp or None,
            "floating_usd": round(self.floating_usd, 2),
        }


def _position_risk_usd(
    item, quantity: float, price: float, sl: float, contract_size: float | None
) -> float | None:
    """Pérdida en USD hasta el SL; ``None`` si no se puede medir."""
    if sl <= 0 or price <= 0:
        return None
    distance = abs(price - sl)
    if distance == 0:
        return 0.0
    if item.market is Market.FUTURES:
        if item.multiplier is None:
            return None
        return abs(quantity) * distance * item.multiplier
    size = contract_size if contract_size is not None else item.contract_size
    if size is None:
        return None
    if item.category == CfdCategory.FOREX.value:
        base, quote = item.currencies
        if base == "USD":  # USDJPY y similares: el P&L va en la cotizada
            return abs(quantity) * size * distance / price
        if quote != "USD":
            return None
    return abs(quantity) * size * distance


def _spec_lookup(broker):
    cache: dict[str, dict] = {}

    def spec(symbol: str) -> dict:
        if symbol not in cache:
            try:
                cache[symbol] = broker.symbol_spec(symbol) or {}
            except Exception:
                cache[symbol] = {}
        return cache[symbol]

    return spec


def build_observed_positions(
    account: PropAccount,
    raw_positions: list[dict],
    *,
    lanes: dict[int, tuple[str, str]],
    spec_for_symbol,
) -> tuple[list[ObservedPosition], list[str]]:
    """Convierte las posiciones de MT5 en ``PositionView`` (sin modificar nada)."""
    out: list[ObservedPosition] = []
    notes: list[str] = []
    for raw in raw_positions:
        symbol_broker = str(raw.get("symbol") or "")
        try:
            item = resolve(symbol_broker)
        except KeyError:
            notes.append(f"Sin datos: {symbol_broker} fuera del universo Prop Fund")
            continue
        volume = float(raw.get("volume") or 0.0)
        if volume <= 0:
            notes.append(f"Sin datos: {symbol_broker} sin volumen")
            continue
        side = str(raw.get("side") or "").strip().lower()
        quantity = -volume if side in _SELL else volume
        price = float(raw.get("price_current") or 0.0) or float(raw.get("price_open") or 0.0)
        if price <= 0:
            notes.append(f"Sin datos: {symbol_broker} sin precio actual")
            continue
        spec = spec_for_symbol(symbol_broker) if item.market is Market.CFD else {}
        contract_size = float(spec["contract_size"]) if spec.get("contract_size") else None
        sl = float(raw.get("sl") or 0.0)
        magic = int(raw.get("magic") or 0)
        strategy, lane = _lane_for(magic, lanes)
        risk_usd = _position_risk_usd(item, quantity, price, sl, contract_size)
        if risk_usd is not None:
            risk_usd = round(risk_usd, 2)
        if risk_usd is None and sl <= 0:
            notes.append(f"Sin datos: {symbol_broker} sin stop loss; riesgo abierto parcial")
        position = PositionView(
            account=account.id,
            firm=account.firm,
            strategy=strategy,
            symbol=item.id,
            quantity=quantity,
            price=price,
            contract_size=contract_size,
            risk_usd=risk_usd,
        )
        floating = (
            float(raw.get("profit") or 0.0)
            + float(raw.get("swap") or 0.0)
            + float(raw.get("commission") or 0.0)
        )
        out.append(
            ObservedPosition(
                position=position,
                ticket=int(raw.get("ticket") or 0),
                magic=magic,
                lane=lane,
                symbol_broker=symbol_broker,
                sl=sl,
                tp=float(raw.get("tp") or 0.0),
                floating_usd=floating,
            )
        )
    return out, _dedupe(notes)


# ---------------------------------------------------------------------- snapshot


def _trades_today(broker, now: datetime, tz_name: str) -> int:
    start = now - timedelta(days=2)
    deals = broker.history_deals(start, now + timedelta(days=1)) or []
    tz = ZoneInfo(tz_name)
    today = now.astimezone(tz).date()
    count = 0
    for deal in deals:
        if int(deal.get("entry") or 0) != 1:  # solo cierres (DEAL_ENTRY_OUT)
            continue
        raw = str(deal.get("ts_utc") or "")
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        if moment.astimezone(tz).date() == today:
            count += 1
    return count


def build_account_snapshot(
    account: PropAccount,
    broker,
    health: dict,
    positions: list[ObservedPosition],
    *,
    rules,
    now: datetime,
) -> tuple[AccountSnapshot | None, list[str]]:
    """``AccountSnapshot`` desde ``health`` + curva de equity + deals."""
    notes: list[str] = []
    if health.get("offset_known") is False:
        return None, ["Sin datos: desfase del servidor MT5 desconocido"]
    balance = float(health.get("balance") or 0.0)
    equity = float(health.get("equity") or 0.0)
    if equity <= 0:
        return None, ["Sin datos: equity MT5 no disponible"]

    try:
        curve = broker.equity_series(180)
    except Exception as exc:
        return None, [f"Sin datos: curva de equity no disponible ({_note(exc)})"]
    if curve is None or len(curve) == 0:
        return None, ["Sin datos: curva de equity vacía"]

    from ..prop.guard import PropGuard

    try:
        state = PropGuard.state_from_equity(
            rules,
            curve,
            initial_balance=rules.account_size,
            open_positions=len(positions),
        )
    except Exception as exc:
        return None, [f"Sin datos: estado de equity no disponible ({_note(exc)})"]

    try:
        trades_today = _trades_today(broker, now, rules.reset_tz)
    except Exception as exc:
        return None, [f"Sin datos: historial de operaciones no disponible ({_note(exc)})"]

    known = [p.position.risk_usd for p in positions if p.position.risk_usd is not None]
    missing = sum(1 for p in positions if p.position.risk_usd is None)
    if missing:
        notes.append(f"Sin datos: riesgo abierto parcial; {missing} posiciones sin stop o especificación")

    snapshot = AccountSnapshot(
        account=account.id,
        balance=balance,
        equity=equity,
        day_start_equity=float(state.day_start_equity),
        peak_equity=float(state.peak_equity),
        trades_today=trades_today,
        open_positions=len(positions),
        open_risk_usd=round(sum(known), 2),
    )
    return snapshot, _dedupe(notes)


# ------------------------------------------------------------------- recolección


@dataclass
class AccountBundle:
    account: str
    legacy: str | None
    firm: str
    ok: bool
    snapshot: AccountSnapshot | None
    positions: list[ObservedPosition] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    identity: dict | None = None
    generated_at: str = ""

    @property
    def status(self) -> str:
        return "ok" if self.ok else "Sin datos"

    def as_dict(self) -> dict:
        return {
            "account": self.account,
            "legacy": self.legacy,
            "firm": self.firm,
            "ok": self.ok,
            "status": self.status,
            "snapshot": asdict(self.snapshot) if self.snapshot else None,
            "positions": [item.as_dict() for item in self.positions],
            "notes": list(self.notes),
            "identity": self.identity,
            "generated_at": self.generated_at,
            "read_only": True,
        }


def collect_account(
    account: PropAccount,
    *,
    broker=None,
    broker_factory=None,
    settings: Settings | None = None,
    rules=None,
    now: datetime | None = None,
) -> AccountBundle:
    """Lee una cuenta MT5 y construye su snapshot y sus posiciones. Nunca falla."""
    moment = _as_utc(now)
    generated = moment.isoformat()
    try:
        if broker is None:
            broker = (
                broker_factory(account)
                if broker_factory is not None
                else default_broker_factory(account, settings=settings)
            )
        health = broker.connect() or {}
    except Exception as exc:
        return AccountBundle(
            account=account.id,
            legacy=account.legacy_account,
            firm=account.firm,
            ok=False,
            snapshot=None,
            notes=[_note(exc)],
            generated_at=generated,
        )

    identity = {
        key: health.get(key) for key in ("login", "server", "mode", "connected")
    }
    if str(health.get("mode") or "") != "demo":
        return AccountBundle(
            account=account.id, legacy=account.legacy_account, firm=account.firm,
            ok=False, snapshot=None, identity=identity,
            notes=["Sin datos: la cuenta MT5 no es demo"], generated_at=generated,
        )
    if health.get("connected") is False:
        return AccountBundle(
            account=account.id, legacy=account.legacy_account, firm=account.firm,
            ok=False, snapshot=None, identity=identity,
            notes=["Sin datos: terminal MT5 desconectado del bróker"], generated_at=generated,
        )

    try:
        raw_positions = broker.positions() or []
    except Exception as exc:
        return AccountBundle(
            account=account.id, legacy=account.legacy_account, firm=account.firm,
            ok=False, snapshot=None, identity=identity,
            notes=[f"Sin datos: posiciones no disponibles ({_note(exc)})"], generated_at=generated,
        )

    lanes = magic_lanes(account.legacy_account or account.id)
    positions, notes = build_observed_positions(
        account,
        raw_positions,
        lanes=lanes,
        spec_for_symbol=_spec_lookup(broker),
    )

    if rules is None:
        try:
            legacy = account.legacy_account or ""
            rules = rules_for_account(load_accounts()[legacy])
        except Exception as exc:
            notes.append(f"Sin datos: reglas de cuenta no disponibles ({_note(exc)})")

    snapshot = None
    if rules is not None:
        snapshot, snap_notes = build_account_snapshot(
            account, broker, health, positions, rules=rules, now=moment
        )
        notes.extend(snap_notes)
    else:
        notes.append("Sin datos: snapshot de cuenta no disponible")

    return AccountBundle(
        account=account.id,
        legacy=account.legacy_account,
        firm=account.firm,
        ok=True,
        snapshot=snapshot,
        positions=positions,
        notes=_dedupe(notes),
        identity=identity,
        generated_at=generated,
    )


def _eligible_accounts(reg) -> list[PropAccount]:
    allowed = {ConnectionState.DEMO, ConnectionState.PAPER}
    return [
        account
        for account in reg.accounts.values()
        if account.platform == "mt5"
        and not account.template
        and account.connection_state in allowed
    ]


def _build_exposure(*, config_dir: Path, broker_factory, settings, now: datetime,
                    ttl_seconds: float = CACHE_TTL_SECONDS) -> dict:
    generated = _as_utc(now).isoformat()
    try:
        reg = load_registry(config_dir)
    except (RegistryError, ValueError) as exc:
        return {
            "ok": False,
            "status": "Sin datos",
            "source": "mt5",
            "read_only": True,
            "generated_at": generated,
            "ttl_seconds": ttl_seconds,
            "accounts": [],
            "positions": [],
            "by_underlying": {},
            "totals": {"net_notional_usd": 0.0, "gross_notional_usd": 0.0},
            "notes": [f"Sin datos: registro Prop Fund inválido ({exc})"],
        }

    accounts = _eligible_accounts(reg)
    bundles = [
        collect_account(
            account,
            broker_factory=broker_factory,
            settings=settings,
            now=now,
        )
        for account in accounts
    ]
    observed = [item for bundle in bundles for item in bundle.positions]
    by_underlying = exposure_by_underlying([item.position for item in observed]) if observed else {}
    totals = {
        "net_notional_usd": round(
            sum(float(row.get("net_notional_usd") or 0.0) for row in by_underlying.values()), 2
        ),
        "gross_notional_usd": round(
            sum(float(row.get("gross_notional_usd") or 0.0) for row in by_underlying.values()), 2
        ),
    }
    notes: list[str] = []
    for bundle in bundles:
        notes.extend(f"{bundle.account}: {note}" for note in bundle.notes)
    if not accounts:
        notes.append("Sin datos: no hay cuentas MT5 en DEMO/PAPER")
    ok = any(bundle.ok for bundle in bundles)
    return {
        "ok": ok,
        "status": "ok" if ok else "Sin datos",
        "source": "mt5",
        "read_only": True,
        "generated_at": generated,
        "ttl_seconds": ttl_seconds,
        "accounts": [bundle.as_dict() for bundle in bundles],
        "positions": [item.as_dict() for item in observed],
        "by_underlying": by_underlying,
        "totals": totals,
        "notes": _dedupe(notes),
    }


def collect_exposure(
    *,
    root: Path = ROOT,
    config_dir: Path | None = None,
    now: datetime | None = None,
    settings: Settings | None = None,
    broker_factory=None,
    ttl_seconds: float = CACHE_TTL_SECONDS,
) -> dict:
    """Bloque ``exposure`` del endpoint. Caché de 60 s; nunca lanza."""
    if config_dir is None:
        config_dir = root / "config" / "propfund" if root != ROOT else CONFIG_DIR
    key = str(config_dir)
    bypass = broker_factory is not None or ttl_seconds <= 0
    if not bypass:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit and (time.monotonic() - hit[0]) < ttl_seconds:
            return copy.deepcopy(hit[1])

    moment = _as_utc(now)
    try:
        with _READ_LOCK:
            data = _build_exposure(
                config_dir=Path(config_dir),
                broker_factory=broker_factory,
                settings=settings,
                now=moment,
                ttl_seconds=ttl_seconds,
            )
    except Exception as exc:  # última red de seguridad: el endpoint no falla
        data = {
            "ok": False,
            "status": "Sin datos",
            "source": "mt5",
            "read_only": True,
            "generated_at": moment.isoformat(),
            "ttl_seconds": ttl_seconds,
            "accounts": [],
            "positions": [],
            "by_underlying": {},
            "totals": {"net_notional_usd": 0.0, "gross_notional_usd": 0.0},
            "notes": [f"Sin datos: {_note(exc)}"],
        }
    if not bypass:
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic(), copy.deepcopy(data))
    return data


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


__all__ = [
    "AccountBundle",
    "AttachOnlyBroker",
    "CACHE_TTL_SECONDS",
    "ObservedPosition",
    "build_account_snapshot",
    "build_observed_positions",
    "clear_cache",
    "collect_account",
    "collect_exposure",
    "default_broker_factory",
    "magic_lanes",
]
