"""Modo operador de la consola: solo paper/demo, armado por PIN y 2 pasos.

No guarda secretos en `.env` ni en logs. El PIN vive en el keyring del sistema.
El estado armado y los tokens de confirmación viven en memoria del servidor:
se pierden al reiniciar (desarmado por defecto).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .accounts import (
    AccountDefinition,
    effective_limits,
    load_accounts,
    rules_for_account,
)
from .config import KEYRING_SERVICE, Settings
from .db import connect, utcnow
from .intel.calendar import DbCalendarProvider, calendar_block_for_rules
from .killswitch import allows_order
from .killswitch import ensure as ensure_killswitch
from .prop.guard import AccountSnapshot, PropGuard, evaluate_account
from .risk import check_order
from .runtime import (
    console_actions,
    get_bot_state,
    init_runtime,
    record_console_action,
    set_bot_enabled,
)
from .session import session_block

PIN_KEY = "CONSOLE_PIN"
PIN_RE = re.compile(r"^\d{6,12}$")
PIN_MIN_DIGITS = 6
SUPPORTED_PLATFORMS = {"internal", "paper", "alpaca", "mt5"}
TRADEABLE_STATUSES = {"active", "demo", "paper", "simulated"}
ACTIONS = {
    "order",
    "close",
    "flatten",
    "run_bot",
    "bot_enable",
    "bot_disable",
    "killswitch_activate",
    "killswitch_reset",
}


class OperatorError(RuntimeError):
    def __init__(self, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.status = status


def _default_pin_get() -> str | None:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, PIN_KEY)
    except Exception:
        return None


def _default_pin_set(value: str) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, PIN_KEY, value)


def pin_configured(getter: Callable[[], str | None] | None = None) -> bool:
    return bool((getter or _default_pin_get)())


def pin_needs_rotation(getter: Callable[[], str | None] | None = None) -> bool:
    """Avisa si el PIN guardado es más corto que el mínimo actual.

    No borra ni bloquea el PIN corto: solo pide rotarlo.
    """
    pin = str((getter or _default_pin_get)() or "")
    return bool(pin) and len(pin) < PIN_MIN_DIGITS


def set_pin(pin: str, setter: Callable[[str], None] | None = None) -> None:
    """Guarda el PIN en keyring. Nunca se escribe en .env ni en logs."""
    if not PIN_RE.match(pin or ""):
        raise ValueError("El PIN debe tener entre 6 y 12 dígitos.")
    try:
        (setter or _default_pin_set)(pin)
    except Exception as exc:
        raise RuntimeError("No se pudo guardar el PIN en el keyring.") from exc


def _digest(action: str, payload: dict) -> str:
    raw = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")


def _sanitize_error(exc: BaseException) -> str:
    """Error de auditoría sin rutas locales ni secretos."""
    text = f"{type(exc).__name__}: {exc}"
    text = _PATH_RE.sub("<ruta>", text)
    return text[:300]


class OperatorSession:
    """Armado por PIN, caducidad y tokens de confirmación de un solo uso."""

    def __init__(
        self,
        *,
        pin_getter: Callable[[], str | None] | None = None,
        now: Callable[[], datetime] | None = None,
        arm_ttl_seconds: int = 900,
        confirm_ttl_seconds: int = 60,
        max_attempts: int = 5,
        lock_seconds: int = 300,
        db_path: str | Path | None = None,
    ) -> None:
        self._pin_getter = pin_getter or _default_pin_get
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.arm_ttl_seconds = max(60, int(arm_ttl_seconds))
        self.confirm_ttl_seconds = max(5, int(confirm_ttl_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.lock_seconds = max(10, int(lock_seconds))
        self.db_path = Path(db_path) if db_path is not None else None
        self._lock = threading.RLock()
        self._armed_until: datetime | None = None
        self._failures = 0
        self._locked_until: datetime | None = None
        self._confirmations: dict[str, dict] = {}

    def _current(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _load_pin_state(self) -> tuple[int, datetime | None]:
        if self.db_path is not None:
            try:
                init_runtime(self.db_path)
                with connect(self.db_path) as con:
                    row = con.execute(
                        "SELECT failures, locked_until FROM operator_pin_state WHERE id = 1"
                    ).fetchone()
                if row is None:
                    return 0, None
                locked: datetime | None = None
                if row["locked_until"]:
                    try:
                        locked = datetime.fromisoformat(str(row["locked_until"]))
                    except ValueError:
                        locked = None
                    if locked is not None:
                        if locked.tzinfo is None:
                            locked = locked.replace(tzinfo=timezone.utc)
                        locked = locked.astimezone(timezone.utc)
                return int(row["failures"] or 0), locked
            except Exception:
                pass
        return self._failures, self._locked_until

    def _store_pin_state(self, failures: int, locked_until: datetime | None) -> None:
        self._failures = int(failures)
        self._locked_until = locked_until
        if self.db_path is None:
            return
        try:
            init_runtime(self.db_path)
            with connect(self.db_path) as con:
                con.execute(
                    "INSERT INTO operator_pin_state"
                    "(id, failures, locked_until, updated_at) "
                    "VALUES(1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "failures=excluded.failures, "
                    "locked_until=excluded.locked_until, "
                    "updated_at=excluded.updated_at",
                    (
                        int(failures),
                        locked_until.isoformat() if locked_until else None,
                        utcnow(),
                    ),
                )
        except Exception:
            pass

    def status(self) -> dict:
        with self._lock:
            now = self._current()
            if self._armed_until and now >= self._armed_until:
                self._armed_until = None
                self._confirmations.clear()
            failures, locked_until = self._load_pin_state()
            if locked_until is not None and now >= locked_until:
                failures, locked_until = 0, None
                self._store_pin_state(0, None)
            locked = locked_until is not None and now < locked_until
            seconds_left = (
                max(0, int((self._armed_until - now).total_seconds()))
                if self._armed_until
                else 0
            )
            return {
                "armed": bool(self._armed_until and now < self._armed_until),
                "expires_at": self._armed_until.isoformat()
                if self._armed_until
                else None,
                "seconds_left": seconds_left,
                "pin_configured": pin_configured(self._pin_getter),
                "pin_needs_rotation": pin_needs_rotation(self._pin_getter),
                "attempts_left": 0
                if locked
                else max(0, self.max_attempts - failures),
                "locked": bool(locked),
                "locked_until": locked_until.isoformat()
                if locked and locked_until
                else None,
                "arm_minutes": round(self.arm_ttl_seconds / 60.0, 1),
                "confirm_seconds": self.confirm_ttl_seconds,
            }

    def _check_pin_locked(self, now: datetime) -> None:
        _, locked_until = self._load_pin_state()
        if locked_until and now < locked_until:
            raise OperatorError(
                "PIN bloqueado temporalmente. Espera antes de reintentar.", 429
            )
        if locked_until and now >= locked_until:
            self._store_pin_state(0, None)

    def _verify(self, pin: str) -> None:
        with self._lock:
            now = self._current()
            self._check_pin_locked(now)
            expected = self._pin_getter()
            if not expected:
                raise OperatorError(
                    "PIN no configurado. Ejecuta `lab operator pin` primero.", 403
                )
            if not hmac.compare_digest(str(pin or ""), str(expected)):
                failures, _ = self._load_pin_state()
                failures += 1
                if failures >= self.max_attempts:
                    self._store_pin_state(
                        0,
                        now + timedelta(seconds=self.lock_seconds),
                    )
                    raise OperatorError(
                        "PIN incorrecto. Bloqueado temporalmente.", 429
                    )
                self._store_pin_state(failures, None)
                raise OperatorError(
                    f"PIN incorrecto. Intentos restantes: "
                    f"{self.max_attempts - failures}.",
                    403,
                )
            self._store_pin_state(0, None)

    def verify_pin(self, pin: str) -> None:
        """Verifica PIN para acciones sensibles sin armar el modo operador."""
        self._verify(pin)

    def arm(self, pin: str) -> dict:
        self._verify(pin)
        with self._lock:
            now = self._current()
            self._armed_until = now + timedelta(seconds=self.arm_ttl_seconds)
            self._confirmations.clear()
            return self.status()

    def disarm(self) -> dict:
        with self._lock:
            self._armed_until = None
            self._confirmations.clear()
            return self.status()

    def require_armed(self) -> None:
        with self._lock:
            now = self._current()
            if not self._armed_until or now >= self._armed_until:
                self._armed_until = None
                self._confirmations.clear()
                raise OperatorError(
                    "Modo operador desarmado o caducado. Arma con PIN.", 403
                )

    def issue(self, action: str, payload: dict) -> tuple[str, str]:
        self.require_armed()
        with self._lock:
            now = self._current()
            token = secrets.token_urlsafe(24)
            expires = now + timedelta(seconds=self.confirm_ttl_seconds)
            for key, item in list(self._confirmations.items()):
                if item["expires_at"] <= now or item.get("used"):
                    self._confirmations.pop(key, None)
            if len(self._confirmations) >= 20:
                oldest = min(
                    self._confirmations.items(),
                    key=lambda item: item[1]["created_at"],
                )[0]
                self._confirmations.pop(oldest, None)
            self._confirmations[token] = {
                "action": action,
                "digest": _digest(action, payload),
                "expires_at": expires,
                "created_at": now,
                "used": False,
            }
            return token, expires.isoformat()

    def consume(self, token: str, action: str, payload: dict) -> None:
        self.require_armed()
        with self._lock:
            now = self._current()
            item = self._confirmations.pop(str(token or ""), None)
            if item is None:
                raise OperatorError("Token de confirmación inválido o ya usado.", 403)
            if item["expires_at"] <= now:
                raise OperatorError("Token de confirmación caducado.", 403)
            if item["action"] != action or item["digest"] != _digest(action, payload):
                raise OperatorError(
                    "El token no coincide con la operación o cambió el precio.",
                    403,
                )


class OperatorService:
    """Acciones paper/demo con guard, kill-switch, blackout y auditoría."""

    def __init__(
        self,
        settings: Settings,
        db_path: str | Path,
        *,
        session: OperatorSession | None = None,
        broker_factory: Callable[[AccountDefinition], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.db_path = Path(db_path)
        cfg = settings.operator
        self.session = session or OperatorSession(
            db_path=self.db_path,
            arm_ttl_seconds=cfg.arm_minutes * 60,
            confirm_ttl_seconds=cfg.confirm_seconds,
            max_attempts=cfg.max_pin_attempts,
            lock_seconds=cfg.lock_seconds,
        )
        self._broker_factory = broker_factory or self._default_broker

    # --------------------------------------------------------------- estado

    def status(self) -> dict:
        return {
            "mode": self.settings.mode,
            "can_operate": self.settings.mode != "live",
            "session": self.session.status(),
            "accounts": self._accounts_status(),
            "bots": self._bots_status(),
            "audit": console_actions(self.db_path, 25),
            "limits": {
                "actions": sorted(ACTIONS),
                "paper_demo_only": True,
                "live_blocked": self.settings.mode == "live",
            },
        }

    def arm(self, pin: str) -> dict:
        try:
            state = self.session.arm(pin)
        except OperatorError as exc:
            self._audit("arm", {}, "denegado", False, reason=str(exc))
            raise
        self._audit("arm", {}, "armado", True)
        return state

    def disarm(self) -> dict:
        state = self.session.disarm()
        self._audit("disarm", {}, "desarmado", True)
        return state

    def audit(self, limit: int = 50) -> list[dict]:
        return console_actions(self.db_path, limit)

    def _accounts_status(self) -> list[dict]:
        out = []
        for account in load_accounts().values():
            allowed, reason = self._account_allowed(account)
            out.append(
                {
                    "id": account.id,
                    "name": account.name,
                    "type": account.type,
                    "status": account.status,
                    "platform": account.platform,
                    "pocket": account.pocket,
                    "tradeable": allowed,
                    "reason": reason,
                }
            )
        return out

    def _bots_status(self) -> list[dict]:
        try:
            from .orchestrator import load_bots

            bots = load_bots()
        except Exception:
            return []
        out = []
        for spec in bots:
            locked = self._f13_bot_locked(spec.id)
            state = get_bot_state(self.db_path, spec.id)
            out.append(
                {
                    "id": spec.id,
                    "account": spec.account,
                    "profile": spec.profile,
                    "yaml_enabled": spec.yaml_enabled,
                    "enabled": spec.enabled,
                    "runtime": state,
                    "f13_locked": locked,
                    "can_enable": bool(
                        spec.yaml_enabled and not locked and not spec.enabled
                    ),
                    "can_disable": bool(spec.enabled and not locked),
                }
            )
        return out

    def _f13_bot_locked(self, bot: str) -> bool:
        try:
            from .f13 import status as f13_status

            frozen = f13_status(self.db_path)
        except Exception as exc:
            self._audit(
                "f13_status_error",
                {"bot": bot},
                "bloqueado",
                False,
                reason=_sanitize_error(exc),
            )
            return True
        return bool(frozen and str(frozen.get("bot")) == bot)

    def _account_allowed(self, account: AccountDefinition) -> tuple[bool, str | None]:
        if self.settings.mode == "live":
            return False, "mode=live: la consola no opera en live"
        if account.status not in TRADEABLE_STATUSES:
            return False, f"estado {account.status}: no es paper/demo"
        if account.platform not in SUPPORTED_PLATFORMS:
            return False, f"plataforma {account.platform}: sin cuenta demo activa"
        if account.platform == "mt5" and not self.settings.mt5.require_demo:
            return False, "MT5 require_demo=False: la consola exige demo"
        return True, None

    def _account_for(self, account_id: str) -> AccountDefinition:
        account = load_accounts().get(str(account_id or ""))
        if account is None:
            raise OperatorError(f"cuenta desconocida: {account_id}", 404)
        allowed, reason = self._account_allowed(account)
        if not allowed:
            raise OperatorError(f"cuenta rechazada: {reason}", 403)
        return account

    def _default_broker(self, account: AccountDefinition):
        from .execution.alpaca import AlpacaBroker
        from .execution.paper import PaperBroker

        if account.platform in {"internal", "paper"}:
            return PaperBroker(
                self.db_path,
                self.settings.starting_cash,
                self.settings.execution.commission_bps,
                self.settings.execution.slippage_bps,
            )
        if account.platform == "alpaca":
            return AlpacaBroker(paper=True, db_path=self.db_path)
        if account.platform == "mt5":
            from .execution import get_mt5_broker

            return get_mt5_broker(self.settings, self.db_path, dry_run=False)
        raise OperatorError(
            f"plataforma {account.platform}: sin cuenta paper/demo activa", 403
        )

    def _connect_broker(self, account: AccountDefinition):
        broker = self._broker_factory(account)
        connect = getattr(broker, "connect", None)
        if callable(connect):
            try:
                connect()
            except Exception as exc:
                raise OperatorError(
                    f"no se pudo conectar/verificar la cuenta: {exc}", 409
                ) from exc
        health = getattr(broker, "health", None)
        if callable(health):
            try:
                payload = health()
            except Exception as exc:
                self._shutdown(broker)
                raise OperatorError(f"guard de identidad: {exc}", 409) from exc
            if payload.get("paper") is False:
                self._shutdown(broker)
                raise OperatorError("La cuenta no es paper. Rechazada.", 403)
            mode = str(payload.get("mode") or "").lower()
            if mode in {"real", "live"}:
                self._shutdown(broker)
                raise OperatorError("La cuenta es real. Rechazada.", 403)
        return broker

    @staticmethod
    def _shutdown(broker) -> None:
        shutdown = getattr(broker, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass

    # ------------------------------------------------------------- preview

    def preview(self, action: str, params: dict, *, actor: str = "console") -> dict:
        self.session.require_armed()
        try:
            plan = self._plan(action, params)
        except OperatorError as exc:
            self._audit(action, params, "denegado", False, actor, str(exc))
            raise
        token, expires = self.session.issue(action, plan["payload"])
        return {
            "ok": True,
            "action": action,
            "summary": plan["summary"],
            "payload": plan["payload"],
            "token": token,
            "expires_at": expires,
            "confirm_seconds": self.session.confirm_ttl_seconds,
        }

    def execute(
        self,
        action: str,
        params: dict,
        token: str,
        *,
        actor: str = "console",
    ) -> dict:
        self.session.require_armed()
        try:
            plan = self._plan(action, params)
            self.session.consume(token, action, plan["payload"])
            result = self._run(action, plan)
        except OperatorError as exc:
            self._audit(action, params, "denegado", False, actor, str(exc))
            raise
        except Exception as exc:
            self._audit(action, params, "error", False, actor, str(exc)[:500])
            raise OperatorError(f"falló la acción: {exc}", 409) from exc
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        self._audit(
            action,
            plan["payload"],
            "ejecutado",
            ok,
            actor,
            json.dumps(result, ensure_ascii=False, default=str)[:800],
        )
        return {"ok": ok, "action": action, "result": result, "summary": plan["summary"]}

    def reset_killswitch(self, *, pin: str, confirm: bool) -> dict:
        if not confirm:
            raise OperatorError("El reset del kill-switch exige confirmación.", 403)
        self.session.verify_pin(pin)
        from .killswitch import reset

        state = reset(self.db_path, confirm=True)
        self._audit("killswitch_reset", {}, "reset", True)
        return {
            "ok": True,
            "killswitch": {
                "active": state.active,
                "reason": state.reason,
                "reset_at": state.reset_at,
            },
        }

    def activate_killswitch(self, reason: str = "", confirm: bool = False) -> dict:
        if not confirm:
            raise OperatorError("Activar el kill-switch exige confirmación.", 403)
        from .killswitch import activate

        state = activate(
            self.db_path,
            reason=reason or "activación manual desde la consola",
            confirm=True,
        )
        self._audit("killswitch_activate", {"reason": reason}, "activado", True)
        return {
            "ok": True,
            "killswitch": {
                "active": state.active,
                "reason": state.reason,
                "triggered_at": state.triggered_at,
            },
        }

    # ---------------------------------------------------------------- plan

    def _plan(self, action: str, params: dict) -> dict:
        if action not in ACTIONS:
            raise OperatorError(f"acción desconocida: {action}", 400)
        if self.settings.mode == "live":
            raise OperatorError("mode=live: la consola solo opera paper/demo.", 403)
        if action == "order":
            return self._plan_order(params)
        if action == "close":
            return self._plan_close(params)
        if action == "flatten":
            return self._plan_flatten(params)
        if action == "run_bot":
            return self._plan_run_bot(params)
        if action in {"bot_enable", "bot_disable"}:
            return self._plan_bot_toggle(action, params)
        raise OperatorError(f"acción no disponible aquí: {action}", 400)

    def _plan_order(self, params: dict) -> dict:
        account = self._account_for(params.get("account"))
        from .market_pilots import allows_market, market_for_account

        allowed, reason = allows_market(
            self.db_path, market_for_account(account)
        )
        if not allowed:
            raise OperatorError(reason, 409)
        ticker = str(params.get("ticker") or "").strip().upper()
        if not re.match(r"^[A-Z0-9.\-=^]{1,12}$", ticker):
            raise OperatorError("ticker inválido", 400)
        if account.pocket == "intraday_fx":
            from .asset_aliases import symbol_allowed

            allowed, reason = symbol_allowed(self.db_path, ticker)
            if not allowed:
                raise OperatorError(reason, 409)
        side = str(params.get("side") or "").lower()
        if side not in {"buy", "sell"}:
            raise OperatorError("side debe ser buy o sell", 400)
        qty = float(params.get("qty") or 0)
        if qty <= 0:
            raise OperatorError("qty debe ser > 0", 400)
        equity_platform = account.platform in {"internal", "paper", "alpaca"}
        if equity_platform and int(qty) != qty:
            raise OperatorError("qty debe ser entera para acciones/ETF", 400)
        price = float(params.get("price") or 0)
        if price <= 0:
            price = self._last_price(ticker)
        sl = float(params.get("sl") or 0)
        if sl <= 0:
            raise OperatorError("SL obligatorio para abrir", 400)
        if side == "buy" and sl >= price:
            raise OperatorError("SL debe estar por debajo del precio de compra", 400)
        if side == "sell" and sl <= price:
            raise OperatorError("SL debe estar por encima del precio de venta", 400)

        from .riskpause import pause_status

        try:
            pause = pause_status(
                self.db_path, account.id, tz=self.settings.timezone
            )
        except Exception as exc:
            raise OperatorError(f"pausa de riesgo no disponible: {exc}", 409) from exc
        if pause.get("paused"):
            raise OperatorError(
                f"pausa de aperturas: {pause.get('reason')}", 409
            )

        broker = self._connect_broker(account)
        try:
            snap = broker.snapshot({ticker: price})
            positions = broker.positions()
            equity = float(snap["equity"])
            cash = float(snap["cash"])
            rules = rules_for_account(account)
            limits = effective_limits(self.db_path, account)
            ks, _ = ensure_killswitch(
                self.db_path,
                broker.equity_series(),
                self.settings.risk,
                current=equity,
                tz=self.settings.timezone,
            )
            if not allows_order(ks, 1):
                raise OperatorError(f"kill-switch activo: {ks.reason}", 409)
            blackout = calendar_block_for_rules(
                DbCalendarProvider(self.db_path), rules
            )
            if blackout.blocked:
                raise OperatorError(f"blackout de noticias: {blackout.reason}", 409)
            session = session_block(
                rules,
                asset_class=(
                    "futures"
                    if account.pocket == "intraday_futures"
                    else "cfd"
                    if account.pocket == "intraday_fx"
                    else "equity"
                ),
            )
            if session.blocked:
                raise OperatorError(f"sesión bloqueada: {session.reason}", 409)

            state = PropGuard.state_from_equity(
                rules,
                broker.equity_series(),
                initial_balance=rules.account_size,
                open_positions=len(positions),
            )
            state.equity = equity
            open_risk = sum(
                abs(float(position.get("value") or 0.0)) * 0.02
                for position in positions
            )
            risk_per_unit = abs(price - sl)
            if account.platform == "mt5":
                try:
                    spec = broker.symbol_spec(ticker)
                    contract_size = float(spec["contract_size"])
                except Exception as exc:
                    raise OperatorError(
                        f"sin especificación del símbolo {ticker}: {exc}", 409
                    ) from exc
                risk_usd = qty * risk_per_unit * contract_size
                if rules.max_lots is not None and qty > float(rules.max_lots):
                    raise OperatorError(
                        f"lotes {qty:g} > máximo {rules.max_lots:g}", 409
                    )
            else:
                risk_usd = qty * risk_per_unit
            if rules.max_positions and len(positions) >= rules.max_positions:
                raise OperatorError(
                    f"máximo de posiciones alcanzado ({rules.max_positions})", 409
                )
            report = evaluate_account(
                rules,
                AccountSnapshot(
                    equity=equity,
                    day_start_equity=state.day_start_equity,
                    initial_balance=rules.account_size,
                    peak_equity=state.peak_equity or equity,
                    realized_pnl_today=state.closed_pnl_today,
                    open_positions=len(positions),
                    open_risk_usd=open_risk,
                    trades_today=self._console_trades_today(account.id),
                ),
                limits=limits,
                proposed_risk_usd=risk_usd,
            )
            if not report.allowed:
                raise OperatorError(f"guard de cuenta: {report.reason}", 409)

            if equity_platform:
                check = check_order(
                    equity=equity,
                    cash=cash,
                    price=price,
                    qty=int(qty),
                    current_positions=len(positions),
                    gross_exposure=float(snap["positions_value"]),
                    cfg=self.settings.risk,
                )
                if not check.approved or check.qty <= 0:
                    raise OperatorError(f"guard de riesgo: {check.reason}", 409)
                if check.qty < qty:
                    qty = float(check.qty)
                    risk_usd = qty * abs(price - sl)

            risk_pct = (risk_usd / equity) if equity > 0 else None
            daily_limit = float(limits.daily_loss_pct) * float(rules.account_size)
            daily_loss = max(0.0, float(state.day_start_equity) - equity)
            daily_used = (
                min(1.0, daily_loss / daily_limit) if daily_limit > 0 else None
            )
            summary = {
                "action": "order",
                "account": account.id,
                "account_name": account.name,
                "mode": self.settings.mode,
                "platform": account.platform,
                "symbol": ticker,
                "side": side,
                "qty": qty,
                "price": round(price, 6),
                "sl": round(sl, 6),
                "risk_usd": round(risk_usd, 2),
                "risk_pct": round(risk_pct, 6) if risk_pct is not None else None,
                "equity": round(equity, 2),
                "daily_used_pct": round(daily_used, 6) if daily_used is not None else None,
                "remaining_usd": round(report.remaining_usd, 2),
                "guard": report.reason,
            }
            payload = {
                "kind": "order",
                "account": account.id,
                "symbol": ticker,
                "side": side,
                "qty": qty,
                "price": price,
                "sl": sl,
            }
            return {"summary": summary, "payload": payload}
        finally:
            self._shutdown(broker)

    def _plan_close(self, params: dict) -> dict:
        account = self._account_for(params.get("account"))
        broker = self._connect_broker(account)
        try:
            positions = broker.positions()
            position = self._find_position(account, positions, params)
            qty = self._position_qty(account, position, params.get("qty"))
            summary = {
                "action": "close",
                "account": account.id,
                "account_name": account.name,
                "mode": self.settings.mode,
                "platform": account.platform,
                "symbol": self._position_symbol(account, position),
                "qty": qty,
                "note": "cierre/reducción: no lo bloquea el kill-switch",
            }
            payload = {
                "kind": "close",
                "account": account.id,
                "identifier": self._position_identifier(account, position),
                "qty": qty,
            }
            price = float(params.get("price") or 0)
            if price > 0:
                payload["price"] = price
            return {"summary": summary, "payload": payload}
        finally:
            self._shutdown(broker)

    def _plan_flatten(self, params: dict) -> dict:
        account = self._account_for(params.get("account"))
        broker = self._connect_broker(account)
        try:
            positions = broker.positions()
            if not positions:
                raise OperatorError("La cuenta no tiene posiciones abiertas.", 409)
            items = [
                {
                    "identifier": self._position_identifier(account, position),
                    "symbol": self._position_symbol(account, position),
                    "qty": self._position_qty(account, position, None),
                }
                for position in positions
            ]
            return {
                "summary": {
                    "action": "flatten",
                    "account": account.id,
                    "account_name": account.name,
                    "mode": self.settings.mode,
                    "positions": items,
                    "note": "cierre total: no lo bloquea el kill-switch",
                },
                "payload": {
                    "kind": "flatten",
                    "account": account.id,
                    "positions": [
                        {"identifier": item["identifier"], "qty": item["qty"]}
                        for item in items
                    ],
                },
            }
        finally:
            self._shutdown(broker)

    def _plan_run_bot(self, params: dict) -> dict:
        from .orchestrator import load_bots

        bot_id = str(params.get("bot") or "").strip()
        spec = next((item for item in load_bots() if item.id == bot_id), None)
        if spec is None:
            raise OperatorError(f"bot desconocido: {bot_id}", 404)
        if not spec.enabled:
            raise OperatorError(
                f"bot {bot_id} desactivado (YAML o runtime); no se ejecuta.", 409
            )
        account = self._account_for(spec.account)
        from .market_pilots import allows_market, market_for_bot

        allowed, reason = allows_market(self.db_path, market_for_bot(spec))
        if not allowed:
            raise OperatorError(reason, 409)
        return {
            "summary": {
                "action": "run_bot",
                "bot": spec.id,
                "account": account.id,
                "account_name": account.name,
                "profile": spec.profile,
                "mode": self.settings.mode,
                "note": "ejecuta el orquestador real del bot; cada orden pasa por guard",
            },
            "payload": {"kind": "run_bot", "bot": spec.id},
        }

    def _plan_bot_toggle(self, action: str, params: dict) -> dict:
        from .orchestrator import load_bots

        bot_id = str(params.get("bot") or "").strip()
        spec = next((item for item in load_bots() if item.id == bot_id), None)
        if spec is None:
            raise OperatorError(f"bot desconocido: {bot_id}", 404)
        if self._f13_bot_locked(bot_id):
            raise OperatorError(
                "F13 está congelado/iniciado: su bot no se puede activar ni "
                "modificar desde la consola.",
                403,
            )
        enabled = action == "bot_enable"
        if enabled and not spec.yaml_enabled:
            raise OperatorError(
                "El YAML mantiene este bot desactivado; la consola no puede "
                "activarlo. Edita config/bots.yaml manualmente.",
                403,
            )
        if spec.enabled == enabled:
            raise OperatorError(
                f"El bot ya está {'activado' if enabled else 'desactivado'}.", 409
            )
        return {
            "summary": {
                "action": action,
                "bot": spec.id,
                "account": spec.account,
                "profile": spec.profile,
                "before_enabled": spec.enabled,
                "after_enabled": enabled,
                "yaml_enabled": spec.yaml_enabled,
                "reason": str(params.get("reason") or ""),
            },
            "payload": {
                "kind": action,
                "bot": spec.id,
                "enabled": enabled,
            },
        }

    # --------------------------------------------------------------- run

    def _run(self, action: str, plan: dict) -> dict:
        if action == "order":
            return self._execute_order(plan["payload"])
        if action == "close":
            return self._execute_close(plan["payload"])
        if action == "flatten":
            return self._execute_flatten(plan["payload"])
        if action == "run_bot":
            return self._execute_run_bot(plan["payload"])
        if action in {"bot_enable", "bot_disable"}:
            return self._execute_bot_toggle(action, plan["payload"])
        raise OperatorError(f"acción no ejecutable: {action}", 400)

    def _execute_order(self, payload: dict) -> dict:
        account = self._account_for(payload["account"])
        broker = self._connect_broker(account)
        try:
            signed = payload["qty"] if payload["side"] == "buy" else -payload["qty"]
            if account.platform in {"internal", "paper", "alpaca"}:
                order = broker.submit_market(
                    payload["symbol"],
                    int(signed),
                    payload["price"],
                    bot="console",
                    reason=f"operator:{payload['sl']:.6f}",
                )
            else:
                order = broker.submit_market(
                    payload["symbol"],
                    float(signed),
                    sl=payload["sl"],
                    bot="console",
                    reason="operator",
                )
            return {"ok": True, "order": order}
        finally:
            self._shutdown(broker)

    def _execute_close(self, payload: dict) -> dict:
        account = self._account_for(payload["account"])
        broker = self._connect_broker(account)
        try:
            positions = broker.positions()
            position = self._find_position_by_identifier(
                account, positions, payload["identifier"]
            )
            if position is None:
                raise OperatorError("La posición ya no existe.", 409)
            qty = float(payload["qty"])
            if account.platform == "mt5":
                result = broker.close_position(
                    int(payload["identifier"]), volume=qty
                )
            elif account.platform == "projectx":
                result = broker.close_position(
                    str(payload["identifier"]), bot="console", reason="operator"
                )
            else:
                if int(qty) != qty:
                    raise OperatorError(
                        "qty fraccionaria no soportada para acciones/ETF", 409
                    )
                price = float(payload.get("price") or 0) or self._last_price(
                    self._position_symbol(account, position)
                )
                result = broker.submit_market(
                    self._position_symbol(account, position),
                    -int(qty),
                    price,
                    bot="console",
                    reason="operator-close",
                )
            return {"ok": True, "close": result}
        finally:
            self._shutdown(broker)

    def _execute_flatten(self, payload: dict) -> dict:
        account = self._account_for(payload["account"])
        broker = self._connect_broker(account)
        results = []
        errors = []
        try:
            for item in payload["positions"]:
                try:
                    positions = broker.positions()
                    position = self._find_position_by_identifier(
                        account, positions, item["identifier"]
                    )
                    if position is None:
                        errors.append(f"{item['identifier']}: ya no existe")
                        continue
                    if account.platform == "mt5":
                        result = broker.close_position(
                            int(item["identifier"]), volume=float(item["qty"])
                        )
                    elif account.platform == "projectx":
                        result = broker.close_position(
                            str(item["identifier"]),
                            bot="console",
                            reason="operator-flatten",
                        )
                    else:
                        if int(item["qty"]) != float(item["qty"]):
                            raise OperatorError(
                                "qty fraccionaria no soportada para acciones/ETF",
                                409,
                            )
                        price = self._last_price(
                            self._position_symbol(account, position)
                        )
                        result = broker.submit_market(
                            self._position_symbol(account, position),
                            -int(item["qty"]),
                            price,
                            bot="console",
                            reason="operator-flatten",
                        )
                    results.append({"identifier": item["identifier"], "result": result})
                except Exception as exc:
                    errors.append(f"{item['identifier']}: {exc}")
            return {"ok": not errors, "closed": results, "errors": errors}
        finally:
            self._shutdown(broker)

    def _execute_run_bot(self, payload: dict) -> dict:
        from .orchestrator import load_bots, run_bot
        from .profiles import load_profiles

        spec = next((item for item in load_bots() if item.id == payload["bot"]), None)
        if spec is None:
            raise OperatorError(f"bot desconocido: {payload['bot']}", 404)
        if not spec.enabled:
            raise OperatorError("El bot se desactivó después del preview.", 409)
        account = self._account_for(spec.account)
        profile = load_profiles().get(spec.profile or "")
        broker = self._connect_broker(account)
        try:
            actions = run_bot(
                spec,
                self.settings,
                broker,
                dry_run=False,
                profile=profile,
                account=account,
                limits=effective_limits(self.db_path, account),
                max_cluster_risk_pct=(
                    profile.max_cluster_risk_pct if profile else None
                ),
            )
            executed = [
                action for action in actions if action.status == "ejecutado"
            ]
            return {
                "ok": True,
                "actions": [action.__dict__ for action in actions],
                "executed": len(executed),
            }
        finally:
            self._shutdown(broker)

    def _execute_bot_toggle(self, action: str, payload: dict) -> dict:
        from .orchestrator import load_bots

        spec = next((item for item in load_bots() if item.id == payload["bot"]), None)
        if spec is None:
            raise OperatorError(f"bot desconocido: {payload['bot']}", 404)
        if self._f13_bot_locked(spec.id):
            raise OperatorError(
                "F13 está congelado/iniciado: cambio rechazado.", 403
            )
        result = set_bot_enabled(
            self.db_path,
            bot=spec.id,
            enabled=bool(payload["enabled"]),
            yaml_enabled=spec.yaml_enabled,
            actor="console",
            reason="cambio desde la consola",
        )
        return {"ok": True, "runtime": result}

    # ------------------------------------------------------------- helpers

    def _last_price(self, ticker: str) -> float:
        from .data import fetch

        end = date.today()
        start = end - timedelta(days=90)
        try:
            frame = fetch(
                ticker,
                start.isoformat(),
                end.isoformat(),
                self.settings.data.cache_dir,
            )
            if frame is None or frame.empty or "close" not in frame:
                raise ValueError("sin cierres")
            price = float(frame["close"].iloc[-1])
            if price <= 0:
                raise ValueError("precio no válido")
            return price
        except Exception as exc:
            raise OperatorError(
                f"Sin datos de precio para {ticker}; indica un precio.", 409
            ) from exc

    def _console_trades_today(self, account_id: str) -> int:
        try:
            with connect(self.db_path) as con:
                row = con.execute(
                    "SELECT COUNT(*) AS n FROM orders WHERE bot = ? AND ts >= ?",
                    ("console", utcnow()[:10]),
                ).fetchone()
            return int(row["n"])
        except Exception:
            return 0

    @staticmethod
    def _position_symbol(account: AccountDefinition, position: dict) -> str:
        if account.platform == "mt5":
            return str(position.get("symbol") or "")
        if account.platform == "projectx":
            return str(position.get("contract_id") or "")
        return str(position.get("ticker") or "").upper()

    @staticmethod
    def _position_identifier(account: AccountDefinition, position: dict) -> str:
        if account.platform == "mt5":
            return str(position.get("ticket"))
        if account.platform == "projectx":
            return str(position.get("contract_id"))
        return str(position.get("ticker") or "").upper()

    @staticmethod
    def _position_qty(
        account: AccountDefinition, position: dict, requested: Any
    ) -> float:
        current = (
            float(position.get("volume") or 0.0)
            if account.platform == "mt5"
            else float(position.get("qty") or position.get("size") or 0.0)
        )
        qty = current if requested in (None, "") else float(requested)
        if qty <= 0 or qty > current + 1e-9:
            raise OperatorError("qty de cierre inválida", 400)
        return qty

    def _find_position(
        self,
        account: AccountDefinition,
        positions: list[dict],
        params: dict,
    ) -> dict:
        identifier = str(params.get("ticket") or params.get("ticker") or "").strip()
        position = self._find_position_by_identifier(account, positions, identifier)
        if position is None:
            raise OperatorError(f"posición no encontrada: {identifier}", 404)
        return position

    def _find_position_by_identifier(
        self,
        account: AccountDefinition,
        positions: list[dict],
        identifier: str,
    ) -> dict | None:
        key = str(identifier or "").strip().upper()
        for position in positions:
            if self._position_identifier(account, position).upper() == key:
                return position
        return None

    def _audit(
        self,
        action: str,
        params: dict,
        result: str,
        ok: bool,
        actor: str = "console",
        reason: str = "",
    ) -> None:
        try:
            record_console_action(
                self.db_path,
                action=action,
                params=params,
                result=result,
                ok=ok,
                actor=actor,
                detail=reason,
            )
        except Exception:
            pass


__all__ = [
    "ACTIONS",
    "OperatorError",
    "OperatorService",
    "OperatorSession",
    "PIN_KEY",
    "PIN_MIN_DIGITS",
    "pin_configured",
    "pin_needs_rotation",
    "set_pin",
]
