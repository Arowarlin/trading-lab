from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tradinglab.db import connect, init_db
from tradinglab.forward_intraday import _exposure_volume, load_forward_bots
from tradinglab.journal import load_closed_trades
from tradinglab.lifecycle import register_candidate, start_incubation
from tradinglab.mt5_fills import sync_mt5_fills

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


class FakeBroker:
    def __init__(self, deals: list[dict], specs: dict | None = None):
        self.deals = deals
        self.specs = specs or {}
        self.calls: list[tuple[datetime, datetime]] = []

    def history_deals(self, start, end):
        self.calls.append((start, end))
        return list(self.deals)

    def symbol_spec(self, symbol):
        return {"contract_size": float(self.specs.get(symbol, 1.0))}


def _deal(
    deal_id: int,
    side: str,
    price: float,
    *,
    magic: int = 20261153,
    symbol: str = "US100.CASH",
    ts: str = "2026-11-11T10:00:00+00:00",
    commission: float = 1.0,
) -> dict:
    return {
        "deal_id": deal_id,
        "order_id": deal_id + 1000,
        "position_id": 999,
        "symbol": symbol,
        "side": side,
        "volume": 1.0,
        "price": price,
        "commission": commission,
        "swap": 0.0,
        "profit": 0.0,
        "magic": magic,
        "entry": 0 if side == "buy" else 1,
        "ts_utc": ts,
    }


def test_sync_mt5_fills_es_idempotente_y_guarda_manuales(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = FakeBroker(
        [
            _deal(1, "buy", 100.0),
            _deal(2, "sell", 110.0, ts="2026-11-11T11:00:00+00:00"),
            _deal(3, "buy", 200.0, magic=11111, symbol="XAUUSD"),
        ]
    )

    first = sync_mt5_fills(
        broker,
        db,
        magics={20261153: "forward:us100-trend-d1"},
        now=NOW,
    )
    assert first["inserted"] == 3
    assert first["manual"] == 1

    second = sync_mt5_fills(
        broker,
        db,
        magics={20261153: "forward:us100-trend-d1"},
        now=NOW,
    )
    assert second["inserted"] == 0

    with connect(db) as con:
        rows = con.execute(
            "SELECT deal_id, bot, symbol, side, volume, magic FROM fills "
            "ORDER BY deal_id"
        ).fetchall()
    assert [row["deal_id"] for row in rows] == [1, 2, 3]
    assert rows[0]["bot"] == "forward:us100-trend-d1"
    assert rows[2]["bot"] == "manual"
    assert rows[0]["symbol"] == "US100.CASH"


def test_journal_reconstruye_ida_y_vuelta_fifo_desde_mt5(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = FakeBroker(
        [
            _deal(10, "buy", 100.0),
            _deal(11, "sell", 110.0, ts="2026-11-11T11:00:00+00:00"),
        ]
    )
    sync_mt5_fills(
        broker,
        db,
        magics={20261153: "forward:us100-trend-d1"},
        now=NOW,
    )

    trades, diagnostics = load_closed_trades(db)
    assert diagnostics["error"] is None
    assert len(trades) == 1
    trade = trades[0]
    assert trade.bot == "forward:us100-trend-d1"
    assert trade.ticker == "US100.CASH"
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.qty == pytest.approx(1.0)
    assert trade.pnl == pytest.approx(8.0)  # 10 - 2 de comisiones
    assert trade.magic == 20261153
    assert trade.manual is False
    assert trade.entry_order_id == 0  # sin orden del laboratorio
    assert trade.exit_order_id == 0


def test_journal_reconstruye_short_fifo_desde_mt5(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = FakeBroker(
        [
            _deal(20, "sell", 110.0),
            _deal(21, "buy", 100.0, ts="2026-11-11T11:00:00+00:00"),
        ]
    )
    sync_mt5_fills(
        broker,
        db,
        magics={20261153: "forward:us100-trend-d1"},
        now=NOW,
    )
    trades, _ = load_closed_trades(db)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == "short"
    assert trade.pnl == pytest.approx(8.0)  # 10 - 2 comisiones
    assert trade.manual is False


def test_journal_usa_contract_size_en_el_pnl(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    broker = FakeBroker(
        [
            _deal(30, "buy", 2000.0, symbol="XAUUSD"),
            _deal(31, "sell", 2010.0, symbol="XAUUSD", ts="2026-11-11T11:00:00+00:00"),
        ],
        specs={"XAUUSD": 100.0},
    )
    sync_mt5_fills(
        broker,
        db,
        magics={20261153: "forward:us100-trend-d1"},
        now=NOW,
    )
    trades, _ = load_closed_trades(db)
    assert len(trades) == 1
    # 1 lote de oro = 100 oz; 10 USD de recorrido = 1.000 USD brutos.
    assert trades[0].pnl == pytest.approx(998.0)


def test_forward_swing_carga_sin_force_exit_y_con_exposicion():
    bots = {bot.id: bot for bot in load_forward_bots()}
    swing = bots["us100-trend-d1"]
    assert swing.swing is True
    assert swing.force_exit is None
    assert swing.exposure == pytest.approx(0.75)
    assert swing.timeframe == "H4"
    assert swing.enabled is False
    # Los dos forwards existentes siguen intactos.
    assert bots["eurusd-london-pullback-forward"].swing is False
    assert bots["usdjpy-tokyo-breakout-forward"].swing is False


def test_exposure_sobre_volumen_minimo_usa_el_minimo_si_no_cabe():
    # El forward opera con el volumen mínimo: 0,75 x mínimo queda por debajo
    # del mínimo del bróker, así que el tamaño efectivo es el mínimo.
    assert _exposure_volume({"volume_min": 1.0, "volume_step": 1.0}, 0.75) == 1.0
    assert _exposure_volume({"volume_min": 0.1, "volume_step": 0.1}, 0.75) == 0.1
    # Con mínimo 4 y step 1, 0,75 x 4 = 3 < 4: se usa el mínimo (4).
    assert _exposure_volume({"volume_min": 4.0, "volume_step": 1.0}, 0.75) == 4.0


def test_lifecycle_incubate_congela_criterios_sin_tocar_enabled(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    register_candidate(db, bot="us100-trend-d1", asset="US100.CASH")
    row = start_incubation(
        db,
        bot="us100-trend-d1",
        start_date="2026-11-12",
        reason="test",
        criteria_override={
            "window_days": 60,
            "min_trades": 8,
            "min_forward_sharpe": 0.0,
            "max_slippage_bps": 3.0,
            "max_guard_breaches": 0,
        },
        require_gate=False,
    )
    assert row["state"] == "incubando"
    assert row["start_date"] == "2026-11-12"
    assert row["end_date"] == "2027-01-11"
    assert row["criteria_hash"]
    assert '"window_days": 60' in row["criteria"]
    assert '"min_trades": 8' in row["criteria"]


def test_ps1_tiene_ventana_us100_y_excluye_los_existentes():
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1] / "scripts" /
              "intraday_forward_execute.ps1").read_text(encoding="utf-8")
    assert "us100-trend-d1" in script
    assert "4 * 60" in script
    assert "eurusd-london-pullback-forward,usdjpy-tokyo-breakout-forward" in script
    assert "Get-ForwardEnabled" in script
