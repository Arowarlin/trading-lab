from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from ..db import connect, utcnow

logger = logging.getLogger(__name__)


class AlpacaError(RuntimeError):
    pass


class AlpacaBroker:
    """Adaptador de ejecución para Alpaca (paper por defecto).

    Requiere ALPACA_API_KEY y ALPACA_SECRET_KEY en el entorno/.env.
    Salvaguarda: si `paper=False`, exige ALLOW_LIVE=YES para enviar órdenes.
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        db_path: str | Path | None = None,
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

    def health(self) -> dict:
        account = self.client.get_account()
        return {
            "ok": True,
            "paper": self.paper,
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

        result = {
            "order_id": str(order.id),
            "ticker": ticker.upper(),
            "side": "buy" if qty > 0 else "sell",
            "qty": int(abs(qty)),
            "status": str(order.status),
            "submitted_at": str(order.submitted_at),
        }

        if self.db_path:
            try:
                with connect(self.db_path) as con:
                    con.execute(
                        "INSERT INTO orders(ts, ticker, side, qty, order_type, status, broker_id, bot, reason, run_id, "
                        "risk_usd, stop_price) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            utcnow(),
                            result["ticker"],
                            result["side"],
                            result["qty"],
                            "market",
                            result["status"],
                            result["order_id"],
                            bot,
                            reason,
                            run_id,
                            None if risk_usd is None else float(risk_usd),
                            None if stop_price is None else float(stop_price),
                        ),
                    )
            except Exception:
                pass

        return result

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
