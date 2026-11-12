from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tradinglab import cli as cli_mod
from tradinglab.audit import (
    CHAINED_TABLES,
    append_hashed,
    chain_state,
    verify_chain,
)
from tradinglab.db import connect, init_db


def _order(con, *, ticker: str = "SPY", qty: float = 10.0, ts: str = "2026-01-01") -> int:
    return append_hashed(
        con,
        "orders",
        {
            "ts": ts,
            "ticker": ticker,
            "side": "buy",
            "qty": qty,
            "order_type": "market",
            "status": "filled",
            "bot": "test",
            "reason": "unit",
        },
    )


def _action(con, *, action: str = "start", ts: str = "2026-01-01") -> int:
    return append_hashed(
        con,
        "console_actions",
        {
            "ts": ts,
            "action": action,
            "params": json.dumps({"a": 1}),
            "result": "ok",
            "ok": 1,
            "actor": "test",
            "detail": "",
        },
    )


def test_cadena_valida(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for index in range(5):
            _order(con, qty=10.0 + index, ts=f"2026-01-0{index + 1}")
    result = verify_chain("orders", db)
    assert result["ok"] is True
    assert result["first_break_id"] is None
    assert result["n"] == 5
    assert result["hashed"] == 5
    assert result["legacy"] == 0


def test_append_hashed_usa_los_defaults_de_la_tabla(tmp_path: Path) -> None:
    """Una columna con DEFAULT no debe romper el hash al leer la fila."""
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        append_hashed(
            con,
            "orders",
            {
                "ts": "2026-01-01",
                "ticker": "SPY",
                "side": "buy",
                "qty": 1.0,
                "status": "filled",
                "bot": "test",
                "reason": "sin order_type: usa el DEFAULT",
            },
        )
    result = verify_chain("orders", db)
    assert result["ok"] is True
    assert result["first_break_id"] is None


def test_fila_alterada_se_detecta(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        ids = [_order(con, ts=f"2026-01-0{index + 1}") for index in range(3)]
    with connect(db) as con:
        con.execute("UPDATE orders SET qty = 999 WHERE id = ?", (ids[1],))
    result = verify_chain("orders", db)
    assert result["ok"] is False
    assert result["first_break_id"] == ids[1]


def test_fila_borrada_se_detecta(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        ids = [_order(con, ts=f"2026-01-0{index + 1}") for index in range(3)]
    with connect(db) as con:
        con.execute("DELETE FROM orders WHERE id = ?", (ids[1],))
    result = verify_chain("orders", db)
    assert result["ok"] is False
    assert result["first_break_id"] == ids[2]


def test_filas_antigas_sin_hash_no_rompen(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO orders(ts, ticker, side, qty, order_type, status) "
            "VALUES(?,?,?,?,?,?)",
            ("2025-12-01", "SPY", "buy", 5.0, "market", "filled"),
        )
        con.execute(
            "INSERT INTO console_actions(ts, action, params, result, ok) "
            "VALUES(?,?,?,?,?)",
            ("2025-12-01", "start", "{}", "ok", 1),
        )
    with connect(db) as con:
        _order(con)
        _action(con)
    for table in CHAINED_TABLES:
        result = verify_chain(table, db)
        assert result["ok"] is True
        assert result["legacy"] == 1
        assert result["hashed"] == 1


def test_migracion_es_idempotente(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _order(con)
        con.execute("ALTER TABLE orders DROP COLUMN row_hash")
        con.execute("ALTER TABLE orders DROP COLUMN prev_hash")
    init_db(db)
    init_db(db)
    with connect(db) as con:
        columns = [
            row["name"] for row in con.execute("PRAGMA table_info(orders)").fetchall()
        ]
        rows = con.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]
        hashes = con.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE row_hash IS NOT NULL"
        ).fetchone()["n"]
    assert "row_hash" in columns and "prev_hash" in columns
    assert rows == 1
    assert hashes == 0  # las filas antiguas no se reescriben


def test_append_hashed_rechaza_tabla_desconocida(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con, pytest.raises(ValueError):
        append_hashed(con, "signals", {"ts": "2026-01-01"})


def test_chain_state_cubre_las_tablas(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _order(con)
        _action(con)
    state = chain_state(db)
    assert state["ok"] is True
    assert set(state["tables"]) == set(CHAINED_TABLES)


def test_cli_audit_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _order(con)
    monkeypatch.setattr("tradinglab.audit.DEFAULT_DB", db)
    result = CliRunner().invoke(cli_mod.app, ["audit", "verify"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_cli_audit_verify_detecta_rotura(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        row_id = _order(con)
    with connect(db) as con:
        con.execute("UPDATE orders SET qty = 1 WHERE id = ?", (row_id,))
    monkeypatch.setattr("tradinglab.audit.DEFAULT_DB", db)
    result = CliRunner().invoke(cli_mod.app, ["audit", "verify", "--no-alert"])
    assert result.exit_code == 1
    assert "ROTA" in result.output
