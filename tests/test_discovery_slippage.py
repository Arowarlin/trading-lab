"""T12 · Slippage medido: celdas, propuesta y costs.yaml intacto."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
import yaml

from tradinglab.discovery import slippage_measured


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "lab.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE tca(
            id INTEGER PRIMARY KEY, fill_id INTEGER, bot TEXT, account TEXT,
            symbol TEXT, side TEXT, signal_px REAL, order_px REAL,
            fill_px REAL, slippage_bps REAL, latency_ms REAL,
            expected_cost_bps REAL, realized_cost_bps REAL, ts_utc TEXT
        );
        CREATE TABLE orders(
            id INTEGER PRIMARY KEY, ts TEXT, ticker TEXT, order_type TEXT,
            status TEXT
        );
        CREATE TABLE order_accounts(
            order_id INTEGER PRIMARY KEY, account_id TEXT, created_at TEXT
        );
        CREATE TABLE fills(
            id INTEGER PRIMARY KEY, account TEXT, symbol TEXT, side TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO orders(id, ts, ticker, order_type, status)"
        " VALUES(1, '2026-11-24T10:15:00+00:00', 'XAUUSD', 'limit', 'filled')"
    )
    con.execute(
        "INSERT INTO order_accounts(order_id, account_id, created_at)"
        " VALUES(1, 'CFD-001', '2026-11-24T10:15:00+00:00')"
    )
    for index in range(40):
        con.execute(
            "INSERT INTO tca(fill_id, bot, account, symbol, side, order_px,"
            " fill_px, ts_utc) VALUES(1, 'bot', NULL, 'XAUUSD', 'buy',"
            " 2000.0, 2000.1, '2026-11-24T10:15:00+00:00')"
        )
    for index in range(10):
        con.execute(
            "INSERT INTO tca(fill_id, bot, account, symbol, side, order_px,"
            " fill_px, ts_utc) VALUES(NULL, 'bot', NULL, 'EURUSD', 'sell',"
            " 1.1, 1.10002, '2026-11-24T10:20:00+00:00')"
        )
    con.execute("INSERT INTO fills(account, symbol, side) VALUES('ftmo_demo','XAUUSD','buy')")
    con.commit()
    con.close()
    return path


def _costs(tmp_path: Path) -> Path:
    path = tmp_path / "costs.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "accounts": {
                    "CFD-001": {
                        "symbols": {
                            "XAUUSD": {"slippage_price": 0.15},
                            "EURUSD": {"slippage_price": 0.00005},
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_mide_mediana_p75_y_n_por_celda(tmp_path):
    cells = slippage_measured.measure_slippage(_db(tmp_path))
    gold = next(cell for cell in cells if cell.symbol == "XAUUSD")
    assert gold.account == "CFD-001"
    assert gold.order_type == "limit"
    assert gold.band == "08-12"
    assert gold.n == 40
    assert gold.median_price == pytest.approx(0.1)
    assert gold.p75_price == pytest.approx(0.1)
    assert gold.status == "measured"

    euro = next(cell for cell in cells if cell.symbol == "EURUSD")
    assert euro.n == 10
    assert euro.status == "Sin datos"


def test_propuesta_mide_solo_con_n_suficiente_y_no_toca_costs(tmp_path):
    cells = slippage_measured.measure_slippage(_db(tmp_path))
    costs = _costs(tmp_path)
    original = costs.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    proposal = slippage_measured.build_proposal(cells, costs_path=costs)
    after = hashlib.sha256(costs.read_bytes()).hexdigest()
    assert before == after

    gold = proposal["accounts"]["CFD-001"]["symbols"]["XAUUSD"]
    assert gold["source"] == "measured"
    assert gold["slippage_price"] == pytest.approx(0.1)
    assert gold["measured_at"] is not None
    euro = proposal["accounts"]["CFD-001"]["symbols"]["EURUSD"]
    assert euro["source"] == "assumption"
    assert euro["slippage_price"] == 0.00005

    output = slippage_measured.write_proposal(
        proposal, path=tmp_path / "costs.measured.yaml"
    )
    assert output.exists()
    saved = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert saved["accounts"]["CFD-001"]["symbols"]["XAUUSD"]["source"] == "measured"
    assert costs.read_bytes() == original


def test_inventario_cuenta_tablas(tmp_path):
    inventory = slippage_measured.fills_inventory(_db(tmp_path))
    assert inventory["tables"]["tca"] == 50
    assert inventory["tables"]["orders"] == 1
    assert inventory["fills"][0]["symbol"] == "XAUUSD"
