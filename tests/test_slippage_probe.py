from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradinglab.db import connect, init_db
from tradinglab.slippage_probe import (
    SlippageProbeError,
    report,
    run_probe,
    slippage_bps,
)


class FakeBroker:
    def __init__(
        self,
        *,
        mode: str = "demo",
        identity_ok: bool = True,
        volume_min: float = 0.01,
        bid: float = 1.1000,
        ask: float = 1.1002,
        requote_first: bool = False,
    ) -> None:
        self.mode = mode
        self.identity_ok = identity_ok
        self.volume_min = volume_min
        self.bid = bid
        self.ask = ask
        self.requote_first = requote_first
        self.submit_calls = 0
        self.orders: list[dict] = []
        self.closed: list[dict] = []
        self._positions: list[dict] = []
        self._ticket = 100

    def health(self) -> dict:
        return {
            "mode": self.mode,
            "identity_ok": self.identity_ok,
            "connected": True,
            "trade_allowed": True,
        }

    def symbol_spec(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "volume_min": self.volume_min,
            "volume_step": 0.01,
            "digits": 5,
            "point": 0.00001,
        }

    def tick(self, symbol: str) -> dict:
        return {"bid": self.bid, "ask": self.ask}

    def submit_market(self, symbol: str, volume: float, **kwargs) -> dict:
        self.submit_calls += 1
        if self.requote_first and self.submit_calls == 1:
            raise RuntimeError("MT5 rechazó la orden [10004]: requote")
        side = "buy" if volume > 0 else "sell"
        fill = self.ask + 0.0002 if side == "buy" else self.bid - 0.0002
        ticket = self._ticket
        self._ticket += 1
        self.orders.append(
            {"ticket": ticket, "side": side, "volume": abs(volume), "price": fill}
        )
        self._positions.append(
            {"ticket": ticket, "symbol": symbol, "side": side, "volume": abs(volume)}
        )
        return {
            "ok": True,
            "order_id": ticket,
            "deal_id": ticket + 1000,
            "price": fill,
            "retcode": 10009,
            "symbol": symbol,
            "side": side,
            "volume": abs(volume),
        }

    def positions(self, symbol: str | None = None) -> list[dict]:
        if symbol is None:
            return [dict(item) for item in self._positions]
        return [
            dict(item)
            for item in self._positions
            if item["symbol"].upper() == symbol.upper()
        ]

    def close_position(self, ticket: int, volume: float | None = None) -> dict:
        position = next(
            (item for item in self._positions if item["ticket"] == ticket), None
        )
        if position is None:
            raise RuntimeError(f"no existe la posición {ticket}")
        side = "sell" if position["side"] == "buy" else "buy"
        fill = self.bid - 0.0001 if side == "sell" else self.ask + 0.0001
        self._positions.remove(position)
        self.closed.append(
            {"ticket": ticket, "side": side, "volume": position["volume"], "price": fill}
        )
        return {
            "ok": True,
            "ticket": ticket,
            "price": fill,
            "volume": position["volume"],
            "retcode": 10009,
        }


def _clock() -> datetime:
    return datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)


def _probe(broker: FakeBroker, db: Path, **kwargs):
    return run_probe(
        broker,
        "EURUSD",
        orders=kwargs.pop("orders", 2),
        volume=kwargs.pop("volume", None),
        spacing_s=kwargs.pop("spacing_s", 0.0),
        max_orders=kwargs.pop("max_orders", 3),
        max_orders_day=kwargs.pop("max_orders_day", 6),
        db_path=db,
        sleep=lambda _: None,
        clock=_clock,
        **kwargs,
    )


def test_slippage_bps_signo_por_lado() -> None:
    assert slippage_bps("buy", 100.0, 100.01) == pytest.approx(1.0)
    assert slippage_bps("sell", 100.0, 99.99) == pytest.approx(1.0)
    assert slippage_bps("buy", 100.0, 99.99) == pytest.approx(-1.0)


def test_probe_registra_entrada_y_cierre_por_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    broker = FakeBroker()
    result = _probe(broker, db, orders=2)
    assert result["filled_round_trips"] == 2
    assert result["sent_orders"] == 4
    assert len(broker.closed) == 2
    assert broker.positions() == []
    with connect(db) as con:
        rows = con.execute(
            "SELECT side, leg, order_type, requested, filled, slippage_bps, "
            "volume, requote FROM broker_slippage ORDER BY id"
        ).fetchall()
    assert len(rows) == 4
    assert [row["leg"] for row in rows] == ["entry", "close", "entry", "close"]
    assert all(row["order_type"] == "market" for row in rows)
    assert all(row["volume"] == pytest.approx(0.01) for row in rows)
    assert all(row["requote"] == 0 for row in rows)
    assert all(row["filled"] is not None for row in rows)
    assert rows[0]["side"] == "buy"
    assert rows[1]["side"] == "sell"
    assert rows[2]["side"] == "sell"
    assert rows[3]["side"] == "buy"
    assert all(float(row["slippage_bps"]) > 0 for row in rows)


def test_probe_aborta_si_no_es_demo(tmp_path: Path) -> None:
    broker = FakeBroker(mode="real")
    with pytest.raises(SlippageProbeError, match="no demo"):
        _probe(broker, tmp_path / "lab.db")
    assert broker.submit_calls == 0


def test_probe_aborta_si_identity_no_es_true(tmp_path: Path) -> None:
    broker = FakeBroker(identity_ok=False)
    with pytest.raises(SlippageProbeError, match="identity_ok"):
        _probe(broker, tmp_path / "lab.db")
    assert broker.submit_calls == 0


def test_probe_aborta_si_volumen_no_es_el_minimo(tmp_path: Path) -> None:
    broker = FakeBroker(volume_min=0.01)
    with pytest.raises(SlippageProbeError, match="volumen mínimo"):
        _probe(broker, tmp_path / "lab.db", volume=0.02)
    assert broker.submit_calls == 0


def test_probe_aborta_si_orders_excede_el_tope(tmp_path: Path) -> None:
    broker = FakeBroker()
    with pytest.raises(SlippageProbeError, match="tope por ejecución"):
        _probe(broker, tmp_path / "lab.db", orders=4, max_orders=3)
    assert broker.submit_calls == 0


def test_probe_aborta_si_supera_el_tope_diario(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    broker = FakeBroker()
    _probe(broker, db, orders=1, max_orders=1, max_orders_day=1)
    with pytest.raises(SlippageProbeError, match="tope diario"):
        _probe(broker, db, orders=1, max_orders=1, max_orders_day=1)


def test_probe_registra_requote_y_continua(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    broker = FakeBroker(requote_first=True)
    result = _probe(broker, db, orders=2)
    assert result["requotes"] == 1
    assert result["filled_round_trips"] == 1
    with connect(db) as con:
        rows = con.execute(
            "SELECT leg, requote, filled, retcode, error FROM broker_slippage "
            "ORDER BY id"
        ).fetchall()
    assert rows[0]["leg"] == "entry"
    assert rows[0]["requote"] == 1
    assert rows[0]["filled"] is None
    assert rows[0]["retcode"] == 10004
    assert "requote" in rows[0]["error"].lower()
    assert all(row["requote"] == 0 for row in rows[1:])


def test_report_agrupa_mediana_y_p75(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for index, value in enumerate((1.0, 3.0, 5.0, 9.0)):
            con.execute(
                "INSERT INTO broker_slippage"
                "(ts, symbol, side, hour_utc, requested, filled, slippage_bps, "
                "volume, order_type, leg, requote, retcode, error) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"2026-11-09T1{index}:00:00+00:00",
                    "EURUSD",
                    "buy",
                    10 + index,
                    100.0,
                    100.0 + value / 100,
                    value,
                    0.01,
                    "market",
                    "entry",
                    0,
                    10009,
                    None,
                ),
            )
    payload = report(db)
    assert payload["rows"] == 4
    assert payload["filled_rows"] == 4
    by_symbol = payload["by_symbol"][0]
    assert by_symbol["n"] == 4
    assert by_symbol["median_bps"] == pytest.approx(4.0)
    assert by_symbol["p75_bps"] == pytest.approx(6.0)
    assert len(payload["by_side"]) == 1
    assert len(payload["by_hour"]) == 4


def test_report_sin_datos(tmp_path: Path) -> None:
    payload = report(tmp_path / "lab.db")
    assert payload["rows"] == 0
    assert payload["by_symbol"] == []
