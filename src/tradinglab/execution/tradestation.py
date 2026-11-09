"""TradeStation WebAPI v3 en modo SIM: diagnóstico y lectura de cuenta.

La integración es deliberadamente de solo lectura hasta validar la cuenta, los
permisos y el flujo OAuth. `submit_market`/`close_position` solo responden en
dry-run; nunca envían órdenes a TradeStation.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import load_secrets
from ..db import connect, utcnow

AUTH_TOKEN_URL = "https://signin.tradestation.com/oauth/token"
SIM_MARKER = "sim-api.tradestation.com"


class TradeStationError(RuntimeError):
    pass


class TradeStationAuthError(TradeStationError):
    pass


class TradeStationIdentityError(TradeStationError):
    pass


def _list_payload(payload: Any, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _first_number(payload: dict, *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


class TradeStationBroker:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        account_id: str | None = None,
        base_url: str = "https://sim-api.tradestation.com/v3",
        dry_run: bool = True,
        require_simulated: bool = True,
        db_path: str | Path | None = None,
        timeout_s: float = 30.0,
        http: httpx.Client | None = None,
        auth_url: str = AUTH_TOKEN_URL,
    ) -> None:
        load_secrets()
        self.client_id = client_id or os.getenv("TRADESTATION_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv(
            "TRADESTATION_CLIENT_SECRET", ""
        )
        self.refresh_token = refresh_token or os.getenv(
            "TRADESTATION_REFRESH_TOKEN", ""
        )
        self.account_id = account_id or os.getenv("TRADESTATION_ACCOUNT_ID")
        self.base_url = str(base_url).rstrip("/")
        self.auth_url = auth_url
        self.dry_run = bool(dry_run)
        self.require_simulated = bool(require_simulated)
        self.db_path = Path(db_path) if db_path else None
        self.timeout_s = float(timeout_s)
        self._http = http or httpx.Client(timeout=self.timeout_s)
        self._owns_http = http is None
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._account: dict | None = None
        if self.require_simulated and SIM_MARKER not in self.base_url:
            raise TradeStationIdentityError(
                "TradeStation requiere la URL SIM "
                "(https://sim-api.tradestation.com/v3); no se conecta a live."
            )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _refresh_access_token(self) -> str:
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise TradeStationAuthError(
                "faltan TRADESTATION_CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN"
            )
        try:
            response = self._http.post(
                self.auth_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                },
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise TradeStationAuthError(
                f"TradeStation no disponible: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise TradeStationAuthError(
                f"TradeStation rechazó el refresh token (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TradeStationAuthError("respuesta OAuth no JSON") from exc
        token = payload.get("access_token")
        if not token:
            raise TradeStationAuthError("OAuth sin access_token")
        self._access_token = str(token)
        self._expires_at = time.time() + max(60, int(payload.get("expires_in", 1200)) - 60)
        if payload.get("refresh_token"):
            self.refresh_token = str(payload["refresh_token"])
        return self._access_token

    def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._expires_at:
            return self._access_token
        return self._refresh_access_token()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        token = self._ensure_token()
        url = f"{self.base_url}{path}"
        response = self._http.request(
            method,
            url,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            token = self._refresh_access_token()
            response = self._http.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise TradeStationError(
                f"TradeStation HTTP {response.status_code} en {path}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise TradeStationError(f"TradeStation respuesta no JSON en {path}") from exc

    def accounts(self) -> list[dict]:
        payload = self._request("GET", "/brokerage/accounts")
        return _list_payload(payload, "Accounts", "accounts")

    def account(self) -> dict:
        if self._account is not None:
            return self._account
        accounts = self.accounts()
        if not accounts:
            raise TradeStationIdentityError("TradeStation no devolvió cuentas")
        chosen = None
        if self.account_id:
            wanted = str(self.account_id)
            chosen = next(
                (
                    item
                    for item in accounts
                    if str(item.get("AccountID") or item.get("AccountId")) == wanted
                ),
                None,
            )
            if chosen is None:
                raise TradeStationIdentityError(
                    f"la cuenta {wanted} no aparece en TradeStation"
                )
        else:
            chosen = accounts[0]
            self.account_id = str(
                chosen.get("AccountID") or chosen.get("AccountId") or ""
            )
        self._account = chosen
        return chosen

    def balances(self, account_id: str | None = None) -> list[dict]:
        target = account_id or str(self.account()["AccountID"])
        payload = self._request(
            "GET", f"/brokerage/accounts/{target}/balances"
        )
        return _list_payload(payload, "Balances", "balances")

    def positions(self, account_id: str | None = None) -> list[dict]:
        target = account_id or str(self.account()["AccountID"])
        payload = self._request(
            "GET", f"/brokerage/accounts/{target}/positions"
        )
        return _list_payload(payload, "Positions", "positions")

    def quotes(self, symbols: list[str] | tuple[str, ...]) -> list[dict]:
        if not symbols:
            return []
        joined = ",".join(str(symbol).upper() for symbol in symbols)
        payload = self._request("GET", f"/marketdata/quotes/{joined}")
        return _list_payload(payload, "Quotes", "quotes")

    def snapshot(self, prices: dict | None = None) -> dict:
        balances = self.balances()
        balance = balances[0] if balances else {}
        detail = balance.get("BalanceDetail") or balance
        equity = _first_number(detail, "Equity", "TotalEquity", "AccountValue")
        cash = _first_number(detail, "CashBalance", "Cash", "CashAvailable")
        positions_value = (
            equity - cash
            if equity is not None and cash is not None
            else _first_number(detail, "PositionsValue", "MarketValue")
        )
        return {
            "equity": equity,
            "cash": cash,
            "positions_value": positions_value,
            "positions": self.positions(),
            "raw_balance": balance,
        }

    def health(self) -> dict:
        accounts = self.accounts()
        chosen = accounts[0] if accounts else {}
        if self.account_id:
            wanted = str(self.account_id)
            chosen = next(
                (
                    item
                    for item in accounts
                    if str(item.get("AccountID") or item.get("AccountId")) == wanted
                ),
                chosen,
            )
        if self.account_id and chosen:
            found = str(chosen.get("AccountID") or chosen.get("AccountId") or "")
            if found != str(self.account_id):
                raise TradeStationIdentityError(
                    f"la cuenta {self.account_id} no aparece en TradeStation"
                )
        if chosen:
            self._account = chosen
            self.account_id = str(
                chosen.get("AccountID") or chosen.get("AccountId") or ""
            )
        return {
            "ok": bool(accounts),
            "base_url": self.base_url,
            "simulated": SIM_MARKER in self.base_url,
            "account_id": str(
                chosen.get("AccountID") or chosen.get("AccountId") or ""
            ),
            "account_type": chosen.get("AccountType"),
            "accounts": len(accounts),
            "dry_run": self.dry_run,
        }

    def submit_market(self, *args, **kwargs) -> dict:
        if not self.dry_run:
            raise TradeStationError(
                "envío de órdenes TradeStation deshabilitado hasta validar la cuenta"
            )
        return {
            "status": "dry_run",
            "broker": "tradestation",
            "account_id": self.account_id,
            "args": list(args),
            "kwargs": kwargs,
        }

    def close_position(self, *args, **kwargs) -> dict:
        if not self.dry_run:
            raise TradeStationError(
                "cierre de posiciones TradeStation deshabilitado hasta validar la cuenta"
            )
        return {
            "status": "dry_run",
            "broker": "tradestation",
            "account_id": self.account_id,
            "args": list(args),
            "kwargs": kwargs,
        }

    def record_event(self, message: str) -> None:
        if not self.db_path:
            return
        try:
            with connect(self.db_path) as con:
                con.execute(
                    "INSERT INTO events(ts, level, source, message) VALUES(?,?,?,?)",
                    (utcnow(), "info", "tradestation", message[:500]),
                )
        except Exception:
            pass


__all__ = [
    "AUTH_TOKEN_URL",
    "SIM_MARKER",
    "TradeStationAuthError",
    "TradeStationBroker",
    "TradeStationError",
    "TradeStationIdentityError",
]
