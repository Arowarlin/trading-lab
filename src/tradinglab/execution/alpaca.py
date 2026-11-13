from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from ..audit import append_hashed
from ..db import connect, utcnow

logger = logging.getLogger(__name__)


class AlpacaError(RuntimeError):
    pass


class AlpacaBroker:
    """Adaptador de ejecución para Alpaca (paper por defecto).

    Requiere ALPACA_API_KEY y ALPACA_SECRET_KEY en el entorno/.env.
    Salvaguarda: si `paper=False`, exige ALLOW_LIVE=YES para enviar órdenes.
    Además, toda orden queda registrada en `orders`/`fills` con la cuenta y el
    bot que la originó; sin eso la reconciliación no puede separar F13 del
    daytrader.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        db_path: str | Path | None = None,
        account: str = "alpaca_paper",
    ) -> None:
        from alpaca.trading.client import TradingClient

        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        if not self.api_key or not self.secret_key:
            raise AlpacaError("Faltan ALPACA_API_KEY / ALPACA_SECRET_KEY en .env")

        self.paper = paper
        if not paper and os.getenv("ALLOW_LIVE") != "YES":
            raise AlpacaError("Modo live bloqueado: define ALLOW_LIVE=YES solo si es intencional")

        self.client = TradingClient(self.api_key, self.secret_key, paper=paper)
        self.db_path = Path(db_path) if db_path else None
        self.account_id = str(account or "alpaca_paper")

    # ------------------------------------------------------------ identidad

    @staticmethod
    def _value(value, default: str = "") -> str:
        if value is None:
            return default
        return str(getattr(value, "value", value))

    def _base_url(self) -> str:
        base = getattr(self.client, "_base_url", None)
        return self._value(base, "")

    def health(self) -> dict:
        base_url = self._base_url()
        paper_api = bool(base_url) and "paper-api" in base_url.lower()
        if self.paper and base_url and not paper_api:
            raise AlpacaError(
                f"la URL de Alpaca no es paper-api: {base_url}"
            )
        account = self.client.get_account()
        return {
            "ok": True,
            "paper": self.paper,
            "paper_api": paper_api or not base_url,
            "base_url": base_url,
            "status": str(account.status),
            "currency": account.currency,
            "cash": float(account.cash),
            "equity": float(account.equity),
            "buying_power": float(account.buying_power),
            "blocked": bool(getattr(account, "trading_blocked", False)),
        }

    def cash(self) -> float:
        return float(self.client.get_account().cash)

    def positions(self) -> list[dict]:
        out = []
        for p in self.client.get_all_positions():
            out.append(
                {
                    "ticker": p.symbol,
                    "qty": float(p.qty),
                    "avg_price": float(p.avg_entry_price),
                    "last": float(p.current_price or p.avg_entry_price),
                    "value": float(p.market_value or 0.0),
                    "unrealized": float(p.unrealized_pl or 0.0),
                }
            )
        return out

    def snapshot(self, prices: dict[str, float] | None = None) -> dict:
        account = self.client.get_account()
        positions = self.positions()
        positions_value = sum(p["value"] for p in positions)
        return {
            "cash": float(account.cash),
            "positions": positions,
            "positions_value": positions_value,
            "equity": float(account.equity),
        }

    # --------------------------------------------------------------- órdenes

    @classmethod
    def _order_status(cls, order) -> str:
        return cls._value(getattr(order, "status", ""), "").lower()

    @staticmethod
    def _filled_qty(order) -> float:
        try:
            return float(getattr(order, "filled_qty", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _filled_price(order) -> float | None:
        raw = getattr(order, "filled_avg_price", None)
        if raw in (None, ""):
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _insert_fill(
        self,
        con,
        db_order_id: int,
        *,
        bot: str,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        ts: str | None = None,
    ) -> bool:
        exists = con.execute(
            "SELECT 1 FROM fills WHERE order_id = ? AND account = ? LIMIT 1",
            (int(db_order_id), self.account_id),
        ).fetchone()
        if exists:
            return False
        stamp = ts or utcnow()
        con.execute(
            "INSERT INTO fills("
            "order_id, ts, qty, price, commission, bot, account, symbol, side, "
            "volume, swap, deal_id, magic, ts_utc, contract_size"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(db_order_id),
                stamp,
                abs(float(qty)),
                float(price),
                0.0,
                str(bot or "manual")[:80],
                self.account_id,
                symbol.upper(),
                side,
                abs(float(qty)),
                0.0,
                None,
                None,
                stamp,
                None,
            ),
        )
        return True

    def submit_market(
        self,
        ticker: str,
        qty: int,
        price: float | None = None,
        *,
        bot: str = "manual",
        reason: str = "",
        run_id: int | None = None,
        risk_usd: float | None = None,
        stop_price: float | None = None,
    ) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        if qty == 0:
            raise ValueError("qty no puede ser 0")

        side = OrderSide.BUY if qty > 0 else OrderSide.SELL
        side_text = "buy" if qty > 0 else "sell"
        request = MarketOrderRequest(
            symbol=ticker.upper(),
            qty=int(abs(qty)),
            side=side,
            time_in_force=TimeInForce.DAY,
        )

        try:
            order = self.client.submit_order(request)
        except Exception as exc:
            raise AlpacaError(f"Alpaca rechazó la orden: {exc}") from exc

        status = self._order_status(order)
        filled_qty = self._filled_qty(order)
        filled_px = self._filled_price(order)
        db_order_id: int | None = None
        recorded = False
        if self.db_path:
            try:
                with connect(self.db_path) as con:
                    db_order_id = append_hashed(
                        con,
                        "orders",
                        {
                            "ts": utcnow(),
                            "ticker": ticker.upper(),
                            "side": side_text,
                            "qty": int(abs(qty)),
                            "order_type": "market",
                            "status": status or "submitted",
                            "broker_id": str(order.id),
                            "bot": bot,
                            "reason": reason,
                            "run_id": run_id,
                            "risk_usd": None if risk_usd is None else float(risk_usd),
                            "stop_price": None if stop_price is None else float(stop_price),
                        },
                    )
                    con.execute(
                        "INSERT OR REPLACE INTO order_accounts"
                        "(order_id, account_id, created_at) VALUES(?,?,?)",
                        (db_order_id, self.account_id, utcnow()),
                    )
                    if filled_qty > 0 and filled_px is not None:
                        self._insert_fill(
                            con,
                            db_order_id,
                            bot=bot,
                            symbol=ticker,
                            side=side_text,
                            qty=filled_qty,
                            price=filled_px,
                            ts=str(getattr(order, "filled_at", "") or "") or None,
                        )
                    recorded = True
            except Exception as exc:
                logger.error(
                    "Alpaca: la orden %s se envió pero no se pudo registrar: %s",
                    order.id,
                    exc,
                )

        try:
            from ..tca import record_fill as tca_record

            tca_record(
                self.db_path,
                bot=bot,
                symbol=ticker.upper(),
                side=side_text,
                signal_px=price,
                order_px=price,
                expected_cost_bps=float(getattr(self, "slippage_bps", 0.0) or 0.0),
            )
        except Exception:
            pass

        return {
            "order_id": str(order.id),
            "db_order_id": db_order_id,
            "recorded": recorded,
            "ticker": ticker.upper(),
            "side": side_text,
            "qty": int(abs(qty)),
            "status": status or "submitted",
            "filled_qty": filled_qty,
            "filled_avg_price": filled_px,
            "submitted_at": str(getattr(order, "submitted_at", "") or ""),
        }

    def sync_fills(self, *, bot: str | None = None, limit: int = 50) -> dict:
        """Trae los fills de órdenes Alpaca ya enviadas y los deja en SQLite.

        Es idempotente: una orden solo produce una fila en `fills`. Se llama
        desde `lab reconcile --account alpaca_paper` antes de comparar, porque
        una orden enviada tras el cierre se llena en la apertura siguiente.
        """
        if not self.db_path:
            return {"checked": 0, "synced": 0, "orders": []}
        with connect(self.db_path) as con:
            rows = [
                dict(row)
                for row in con.execute(
                    "SELECT o.id, o.broker_id, o.ticker, o.side, o.qty, o.bot "
                    "FROM orders o WHERE o.broker_id IS NOT NULL "
                    "AND (? IS NULL OR o.bot = ?) "
                    "AND o.status NOT IN ('canceled','cancelled','rejected','expired') "
                    "AND NOT EXISTS (SELECT 1 FROM fills f WHERE f.order_id = o.id) "
                    "ORDER BY o.id DESC LIMIT ?",
                    (bot, bot, max(1, int(limit))),
                ).fetchall()
            ]
        synced = 0
        details: list[dict] = []
        for row in rows:
            try:
                order = self.client.get_order_by_id(str(row["broker_id"]))
            except Exception as exc:
                details.append(
                    {"order_id": row["id"], "status": "error", "error": str(exc)[:200]}
                )
                continue
            qty = self._filled_qty(order)
            price = self._filled_price(order)
            status = self._order_status(order)
            if qty > 0 and price is not None:
                with connect(self.db_path) as con:
                    if self._insert_fill(
                        con,
                        int(row["id"]),
                        bot=str(row.get("bot") or "manual"),
                        symbol=str(row["ticker"]),
                        side=str(row["side"]),
                        qty=qty,
                        price=price,
                        ts=str(getattr(order, "filled_at", "") or "") or None,
                    ):
                        synced += 1
            details.append(
                {
                    "order_id": row["id"],
                    "broker_id": row["broker_id"],
                    "status": status,
                    "filled_qty": qty,
                    "filled_avg_price": price,
                }
            )
        return {"checked": len(rows), "synced": synced, "orders": details}

    def mark_to_market(self, prices: dict[str, float] | None = None) -> float:
        return self.snapshot(prices)["equity"]

    def equity_series(self) -> pd.Series:
        from alpaca.trading.requests import GetPortfolioHistoryRequest

        for period in ("1M", "3M"):
            try:
                request = GetPortfolioHistoryRequest(
                    period=period, timeframe="1D"
                )
                history = self.client.get_portfolio_history(
                    history_filter=request
                )
            except Exception as exc:
                logger.warning(
                    "Alpaca portfolio history %s falló: %s", period, exc
                )
                continue

            if isinstance(history, dict):
                stamps = history.get("timestamp") or []
                equity = history.get("equity") or []
            else:
                stamps = getattr(history, "timestamp", None) or []
                equity = getattr(history, "equity", None) or []
            if not stamps or not equity:
                continue
            try:
                values = [float(value) for value in equity]
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Alpaca portfolio history %s con equity inválido: %s",
                    period,
                    exc,
                )
                continue
            index = pd.to_datetime(list(stamps), unit="s", utc=True)
            series = pd.Series(values, index=index).dropna()
            if len(series):
                return series

        equity_now = float(self.snapshot()["equity"])
        logger.warning(
            "Alpaca sin historial de portfolio en 1M/3M; "
            "se usa el equity actual %.2f como snapshot",
            equity_now,
        )
        return pd.Series([equity_now], index=[pd.Timestamp.now(tz="UTC")])
