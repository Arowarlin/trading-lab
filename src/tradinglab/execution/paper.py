from __future__ import annotations

from pathlib import Path

from ..audit import append_hashed
from ..db import connect, utcnow


class PaperBroker:
    """Broker interno que persiste cuenta, posiciones, órdenes y equity en SQLite.

    Aplica comisión y slippage para que el paper trading no sea optimista.
    """

    def __init__(
        self,
        db_path: str | Path,
        starting_cash: float = 100_000.0,
        commission_bps: float = 1.0,
        slippage_bps: float = 5.0,
        account: str = "paper_main",
    ) -> None:
        self.db_path = Path(db_path)
        self.starting_cash = float(starting_cash)
        self.commission_bps = float(commission_bps)
        self.slippage_bps = float(slippage_bps)
        self.account_id = str(account or "paper_main")

    def _ensure_account(self, con) -> None:
        row = con.execute("SELECT cash FROM account WHERE id = 1").fetchone()
        if row is None:
            con.execute("INSERT INTO account(id, cash) VALUES(1, ?)", (self.starting_cash,))

    def cash(self) -> float:
        with connect(self.db_path) as con:
            self._ensure_account(con)
            return float(con.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])

    def positions(self) -> list[dict]:
        with connect(self.db_path) as con:
            rows = con.execute("SELECT ticker, qty, avg_price, updated_at FROM positions ORDER BY ticker").fetchall()
            return [dict(r) for r in rows]

    def snapshot(self, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        with connect(self.db_path) as con:
            self._ensure_account(con)
            cash = float(con.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])
            rows = con.execute("SELECT ticker, qty, avg_price FROM positions").fetchall()

        positions_value = 0.0
        positions = []
        for r in rows:
            last = float(prices.get(r["ticker"], r["avg_price"]))
            value = float(r["qty"]) * last
            positions_value += value
            positions.append(
                {
                    "ticker": r["ticker"],
                    "qty": float(r["qty"]),
                    "avg_price": float(r["avg_price"]),
                    "last": last,
                    "value": value,
                    "unrealized": (last - float(r["avg_price"])) * float(r["qty"]),
                }
            )

        return {
            "cash": cash,
            "positions": positions,
            "positions_value": positions_value,
            "equity": cash + positions_value,
        }

    def submit_market(
        self,
        ticker: str,
        qty: int,
        price: float,
        *,
        bot: str = "manual",
        reason: str = "",
        run_id: int | None = None,
        risk_usd: float | None = None,
        stop_price: float | None = None,
        signal_price: float | None = None,
    ) -> dict:
        if qty == 0:
            raise ValueError("qty no puede ser 0")
        if price <= 0:
            raise ValueError("price debe ser > 0")

        ticker = ticker.upper()
        side = "buy" if qty > 0 else "sell"
        signal_px = (
            float(signal_price)
            if signal_price is not None and float(signal_price) > 0
            else float(price)
        )
        fill_px = price * (1 + self.slippage_bps / 10_000) if qty > 0 else price * (1 - self.slippage_bps / 10_000)
        notional = abs(qty) * fill_px
        fee = notional * self.commission_bps / 10_000

        with connect(self.db_path) as con:
            self._ensure_account(con)
            cash = float(con.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])

            if qty > 0 and cash < notional + fee:
                raise RuntimeError(f"efectivo insuficiente: necesitas {notional + fee:.2f}, tienes {cash:.2f}")

            row = con.execute("SELECT qty, avg_price FROM positions WHERE ticker = ?", (ticker,)).fetchone()
            held_qty = float(row["qty"]) if row else 0.0
            held_avg = float(row["avg_price"]) if row else 0.0

            if qty < 0 and abs(qty) > held_qty + 1e-9:
                raise RuntimeError(f"no puedes vender {abs(qty)} de {ticker}; tienes {held_qty:g}")

            order_id = append_hashed(
                con,
                "orders",
                {
                    "ts": utcnow(),
                    "ticker": ticker,
                    "side": side,
                    "qty": abs(qty),
                    "order_type": "market",
                    "status": "filled",
                    "bot": bot,
                    "reason": reason,
                    "run_id": run_id,
                    "risk_usd": None if risk_usd is None else float(risk_usd),
                    "stop_price": None if stop_price is None else float(stop_price),
                },
            )

            con.execute(
                "INSERT INTO fills(order_id, ts, qty, price, commission) VALUES(?,?,?,?,?)",
                (order_id, utcnow(), abs(qty), fill_px, fee),
            )
            con.execute(
                "INSERT OR REPLACE INTO order_accounts(order_id, account_id, created_at) "
                "VALUES(?,?,?)",
                (order_id, self.account_id, utcnow()),
            )

            new_qty = held_qty + qty
            if new_qty <= 1e-9:
                con.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
            else:
                if qty > 0:
                    new_avg = (held_avg * held_qty + qty * fill_px) / new_qty
                else:
                    new_avg = held_avg
                con.execute(
                    "INSERT INTO positions(ticker, qty, avg_price, updated_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(ticker) DO UPDATE SET qty=excluded.qty, avg_price=excluded.avg_price, "
                    "updated_at=excluded.updated_at",
                    (ticker, new_qty, new_avg, utcnow()),
                )

            con.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (qty * fill_px + fee,))
            new_cash = float(con.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])
            positions_value = float(
                con.execute("SELECT COALESCE(SUM(qty * avg_price), 0) AS v FROM positions").fetchone()["v"]
            )
            con.execute(
                "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
                (utcnow(), new_cash, positions_value, new_cash + positions_value),
            )

        try:
            from ..tca import record_fill as tca_record
            from ..tca import slippage_bps as tca_slip

            realized_bps = (abs(fill_px - price) / price) * 10_000.0
            tca_record(
                self.db_path,
                fill_id=order_id,
                bot=bot,
                symbol=ticker,
                side=side,
                signal_px=signal_px,
                order_px=price,
                fill_px=fill_px,
                slippage_bps=tca_slip(signal_px, fill_px, side),
                expected_cost_bps=self.slippage_bps + self.commission_bps,
                realized_cost_bps=realized_bps + self.commission_bps,
                # ENG-1 B-14: el slippage del paper es el supuesto, no una medición.
                origin="paper",
            )
        except Exception:
            pass

        return {
            "order_id": order_id,
            "ticker": ticker,
            "side": side,
            "qty": abs(qty),
            "price": round(fill_px, 4),
            "fee": round(fee, 4),
        }

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """Registra una foto de equity con precios de mercado."""
        snap = self.snapshot(prices)
        with connect(self.db_path) as con:
            con.execute(
                "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
                (utcnow(), snap["cash"], snap["positions_value"], snap["equity"]),
            )
        return float(snap["equity"])

    def equity_series(self):
        import pandas as pd

        with connect(self.db_path) as con:
            rows = con.execute("SELECT ts, equity FROM equity ORDER BY ts").fetchall()
        if not rows:
            return pd.Series(dtype=float)
        return pd.Series(
            [float(r["equity"]) for r in rows],
            index=pd.to_datetime(
                [r["ts"] for r in rows], utc=True, format="mixed"
            ),
        )
