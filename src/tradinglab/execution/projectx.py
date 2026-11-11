from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from ..audit import append_hashed
from ..db import connect, utcnow


class ProjectXError(RuntimeError):
    pass


class ProjectXAuthError(ProjectXError):
    pass


class ProjectXIdentityError(ProjectXError):
    """La cuenta no es la esperada o no es simulada. Nunca se envía una orden tras esto."""


ORDER_TYPES = {
    "limit": 1,
    "market": 2,
    "stop_limit": 3,
    "stop": 4,
    "trailing_stop": 5,
    "join_bid": 6,
    "join_ask": 7,
}

ORDER_SIDES = {"sell": 0, "buy": 1}  # 0 = Bid, 1 = Ask

ORDER_STATUS = {
    0: "none",
    1: "open",
    2: "filled",
    3: "cancelled",
    4: "expired",
    5: "rejected",
    6: "pending",
    7: "pending_cancellation",
    8: "suspended",
}


class ProjectXBroker:
    """Adaptador para el gateway ProjectX (TopstepX).

    Salvaguardas:
      * `dry_run=True`: valida y devuelve la orden sin enviarla.
      * Guard de identidad: por defecto exige una cuenta simulada y con
        `canTrade=true`. Una cuenta real exige `ALLOW_LIVE=YES`.
      * El login se hace con API key; no se guarda la contraseña.
      * Topstep no permite VPS/VPN para el flujo de órdenes: ejecutar en el PC.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        api_key: str | None = None,
        account_id: int | None = None,
        dry_run: bool = True,
        require_simulated: bool = True,
        db_path: str | Path | None = None,
        timeout_s: float = 30.0,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("PROJECTX_BASE_URL") or "https://api.topstepx.com").rstrip("/")
        self.username = username or os.getenv("PROJECTX_USERNAME", "")
        self.api_key = api_key or os.getenv("PROJECTX_API_KEY", "")
        self.account_id = int(account_id) if account_id else _env_int("PROJECTX_ACCOUNT_ID")
        self.dry_run = bool(dry_run)
        self.require_simulated = bool(require_simulated)
        self.db_path = Path(db_path) if db_path else None
        self._http = http or httpx.Client(timeout=timeout_s)
        self._owns_http = http is None
        self._token: str | None = None
        self._account: dict[str, Any] | None = None

    # ------------------------------------------------------------- conexión

    def login(self) -> str:
        if self._token:
            return self._token
        if not self.username or not self.api_key:
            raise ProjectXAuthError(
                "Faltan PROJECTX_USERNAME / PROJECTX_API_KEY en .env"
            )
        data = self._post(
            "/api/Auth/loginKey",
            {"userName": self.username, "apiKey": self.api_key},
            auth=False,
        )
        if not data.get("success") or not data.get("token"):
            raise ProjectXAuthError(
                f"Login ProjectX rechazado: {data.get('errorMessage') or data.get('errorCode')}"
            )
        self._token = str(data["token"])
        return self._token

    def accounts(self) -> list[dict]:
        self.login()
        data = self._post("/api/Account/search", {"onlyActiveAccounts": True})
        if not data.get("success"):
            raise ProjectXError(
                f"ProjectX no devolvió cuentas: {data.get('errorMessage') or data.get('errorCode')}"
            )
        return list(data.get("accounts") or [])

    def account(self) -> dict:
        if self._account:
            return self._account
        accounts = self.accounts()
        if not accounts:
            raise ProjectXIdentityError("La API key no tiene cuentas activas.")

        chosen = None
        if self.account_id is not None:
            chosen = next((a for a in accounts if int(a.get("id", 0)) == self.account_id), None)
            if chosen is None:
                raise ProjectXIdentityError(
                    f"La cuenta {self.account_id} no está entre las cuentas activas."
                )
        else:
            chosen = next(
                (a for a in accounts if a.get("canTrade") and a.get("isVisible")),
                next((a for a in accounts if a.get("canTrade")), accounts[0]),
            )

        if not chosen.get("canTrade", False):
            raise ProjectXIdentityError("La cuenta seleccionada tiene canTrade=false.")
        if not chosen.get("simulated", False):
            if self.require_simulated:
                raise ProjectXIdentityError(
                    "La cuenta no es simulada. Usa require_simulated=false y ALLOW_LIVE=YES "
                    "solo si es intencional."
                )
            if os.getenv("ALLOW_LIVE") != "YES":
                raise ProjectXIdentityError(
                    "Cuenta real bloqueada: define ALLOW_LIVE=YES solo si es intencional."
                )

        self._account = chosen
        return chosen

    def health(self) -> dict:
        account = self.account()
        return {
            "ok": True,
            "account_id": int(account["id"]),
            "name": account.get("name"),
            "balance": float(account.get("balance") or 0.0),
            "simulated": bool(account.get("simulated")),
            "can_trade": bool(account.get("canTrade")),
            "dry_run": self.dry_run,
            "require_simulated": self.require_simulated,
            "base_url": self.base_url,
        }

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    # -------------------------------------------------------------- catálogo

    def search_contracts(self, text: str, live: bool = False) -> list[dict]:
        self.login()
        data = self._post(
            "/api/Contract/search",
            {"searchText": text, "live": live},
        )
        if not data.get("success"):
            raise ProjectXError(
                f"Búsqueda de contratos falló: {data.get('errorMessage') or data.get('errorCode')}"
            )
        return list(data.get("contracts") or [])

    def resolve_contract(self, symbol: str, live: bool = False) -> dict:
        symbol = symbol.strip().upper()
        contracts = self.search_contracts(symbol, live=live)
        if not contracts:
            raise ProjectXError(f"No hay contratos para '{symbol}' (live={live}).")

        exact = [
            c for c in contracts
            if str(c.get("name", "")).upper() == symbol and c.get("activeContract", False)
        ]
        if exact:
            return exact[0]
        active = [c for c in contracts if c.get("activeContract", False)]
        if active:
            return active[0]
        return contracts[0]

    # ------------------------------------------------------------------ órdenes

    def place_order(
        self,
        contract_id: str,
        side: str,
        size: int,
        *,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_price: float | None = None,
        stop_loss_ticks: int | None = None,
        take_profit_ticks: int | None = None,
        custom_tag: str = "",
        bot: str = "manual",
        reason: str = "",
    ) -> dict:
        side_l = side.strip().lower()
        type_l = order_type.strip().lower()
        if side_l not in ORDER_SIDES:
            raise ValueError("side debe ser 'buy' o 'sell'")
        if type_l not in ORDER_TYPES:
            raise ValueError(f"order_type inválido: {order_type}")
        if int(size) <= 0:
            raise ValueError("size debe ser positivo")

        account = self.account()
        payload: dict[str, Any] = {
            "accountId": int(account["id"]),
            "contractId": contract_id,
            "type": ORDER_TYPES[type_l],
            "side": ORDER_SIDES[side_l],
            "size": int(size),
            "customTag": custom_tag[:64],
        }
        if limit_price is not None:
            payload["limitPrice"] = float(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = float(stop_price)
        if stop_loss_ticks:
            payload["stopLossBracket"] = {"ticks": int(stop_loss_ticks), "type": ORDER_TYPES["stop"]}
        if take_profit_ticks:
            payload["takeProfitBracket"] = {"ticks": int(take_profit_ticks), "type": ORDER_TYPES["limit"]}

        preview = {
            "account_id": payload["accountId"],
            "contract_id": contract_id,
            "side": side_l,
            "size": int(size),
            "order_type": type_l,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "stop_loss_ticks": stop_loss_ticks,
            "take_profit_ticks": take_profit_ticks,
            "dry_run": self.dry_run,
        }

        if self.dry_run:
            preview["order_id"] = None
            preview["status"] = "preview"
            return preview

        data = self._post("/api/Order/place", payload)
        if not data.get("success"):
            raise ProjectXError(
                f"ProjectX rechazó la orden: {data.get('errorMessage') or data.get('errorCode')}"
            )

        result = {
            "order_id": data.get("orderId"),
            "account_id": payload["accountId"],
            "contract_id": contract_id,
            "side": side_l,
            "size": int(size),
            "order_type": type_l,
            "status": "submitted",
            "dry_run": False,
        }
        self._record(result, bot=bot, reason=reason)
        return result

    def open_orders(self) -> list[dict]:
        account = self.account()
        data = self._post("/api/Order/searchOpen", {"accountId": int(account["id"])})
        if not data.get("success"):
            raise ProjectXError(
                f"No se pudieron leer las órdenes abiertas: {data.get('errorMessage')}"
            )
        return [
            {
                "order_id": o.get("id"),
                "contract_id": o.get("contractId"),
                "status": ORDER_STATUS.get(int(o.get("status", 0)), str(o.get("status"))),
                "type": o.get("type"),
                "side": "buy" if int(o.get("side", 0)) == 1 else "sell",
                "size": o.get("size"),
                "filled": o.get("fillVolume"),
                "price": o.get("filledPrice"),
            }
            for o in (data.get("orders") or [])
        ]

    # ---------------------------------------------------------------- posiciones

    def positions(self) -> list[dict]:
        account = self.account()
        data = self._post("/api/Position/searchOpen", {"accountId": int(account["id"])})
        if not data.get("success"):
            raise ProjectXError(
                f"No se pudieron leer las posiciones: {data.get('errorMessage')}"
            )
        return [
            {
                "position_id": p.get("id"),
                "contract_id": p.get("contractId"),
                "name": p.get("contractDisplayName"),
                "side": "long" if int(p.get("type", 0)) == 1 else "short",
                "size": p.get("size"),
                "avg_price": p.get("averagePrice"),
            }
            for p in (data.get("positions") or [])
        ]

    def close_position(self, contract_id: str, *, bot: str = "manual", reason: str = "") -> dict:
        account = self.account()
        payload = {"accountId": int(account["id"]), "contractId": contract_id}

        if self.dry_run:
            return {
                "account_id": payload["accountId"],
                "contract_id": contract_id,
                "status": "preview",
                "dry_run": True,
            }

        data = self._post("/api/Position/closeContract", payload)
        if not data.get("success"):
            raise ProjectXError(
                f"ProjectX no cerró la posición: {data.get('errorMessage') or data.get('errorCode')}"
            )
        result = {
            "account_id": payload["accountId"],
            "contract_id": contract_id,
            "status": "closed",
            "dry_run": False,
        }
        self._record(
            {
                "order_id": None,
                "account_id": payload["accountId"],
                "contract_id": contract_id,
                "side": "close",
                "size": 0,
                "order_type": "close",
                "status": "closed",
            },
            bot=bot,
            reason=reason,
        )
        return result

    # ------------------------------------------------------------------ interno

    def _post(self, path: str, payload: dict, *, auth: bool = True) -> dict:
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.login()}"
        try:
            response = self._http.post(
                f"{self.base_url}{path}", json=payload, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProjectXError(
                f"ProjectX HTTP {exc.response.status_code} en {path}: {exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProjectXError(f"ProjectX no responde en {path}: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise ProjectXError(f"Respuesta no JSON de ProjectX en {path}") from exc

    def _record(self, order: dict, *, bot: str, reason: str) -> None:
        if not self.db_path:
            return
        try:
            with connect(self.db_path) as con:
                append_hashed(
                    con,
                    "orders",
                    {
                        "ts": utcnow(),
                        "ticker": str(order.get("contract_id")),
                        "side": str(order.get("side")),
                        "qty": float(order.get("size") or 0),
                        "order_type": str(order.get("order_type")),
                        "status": str(order.get("status")),
                        "broker_id": (
                            str(order.get("order_id"))
                            if order.get("order_id") is not None
                            else None
                        ),
                        "bot": bot,
                        "reason": reason,
                    },
                )
        except (sqlite3.Error, OSError):
            pass


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None
