"""Tests de FUT-T2: servidor MCP ``tradinglab-state`` de solo lectura.

Sin red, sin descargas y sin escribir fuera de ``tmp_path``: el libro sintético se
construye a mano con cifras exactas (``dashboard_model.md §4``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from tradinglab.config import ROOT
from tradinglab.mcp_state import server as state
from tradinglab.prop_economics import ledger

TODAY = "2026-11-28"


def _json(obj: object) -> object:
    """Ida y vuelta por JSON: falla si hay Decimal, fecha, numpy o NaN."""
    return json.loads(json.dumps(obj, allow_nan=False))


def _synthetic_ledger(path: Path) -> None:
    """Libro real mínimo: 500 de coste y un payout P1 de 1.000 pedidos y 900 recibidos."""
    con = ledger.open_ledger(path)
    try:
        ledger.add_account(con, "A1", firm_id="f1", program_id="p1", rules_version="v1",
                           origin="semi_manual", opened_at="2026-01-05")
        ledger.add_event(con, ts="2026-01-05T09:00:00", account_id="A1", event="fee_paid",
                         amount_usd=-500.0, evidence_path="recibo.pdf")
        ledger.add_event(con, ts="2026-01-06T09:00:00", account_id="A1", event="payout_requested",
                         amount_usd=1000.0, payout_id="P1")
        ledger.add_event(con, ts="2026-01-08T09:00:00", account_id="A1", event="payout_approved",
                         amount_usd=1000.0, payout_id="P1")
        ledger.add_event(con, ts="2026-01-10T09:00:00", account_id="A1", event="payout_processed",
                         amount_usd=900.0, payout_id="P1")
        ledger.add_event(con, ts="2026-01-12T09:00:00", account_id="A1", event="payout_received",
                         amount_usd=900.0, payout_id="P1", amount_local=800.0, currency_local="EUR",
                         fx_rate=0.9)
    finally:
        con.close()


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_las_cuatro_herramientas_estan_registradas() -> None:
    names = {t.name for t in asyncio.run(state.server.list_tools())}
    assert names == {"programs", "ranking", "alerts", "ledger_summary"}


def test_cada_herramienta_devuelve_json_serializable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.db"
    _synthetic_ledger(path)
    monkeypatch.setattr(state, "LEDGER_PATH", path)
    results = {
        "programs": state.programs(TODAY),
        "ranking": state.ranking(),
        "alerts": state.alerts(TODAY),
        "ledger_summary": state.ledger_summary(TODAY),
    }
    for name, result in results.items():
        assert _json(result) == result, name


def test_ledger_summary_cifras_exactas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.db"
    _synthetic_ledger(path)
    monkeypatch.setattr(state, "LEDGER_PATH", path)
    out = state.ledger_summary("2026-01-20")
    assert out["costs_paid"] == 500.0
    assert out["received"] == 900.0
    assert out["net_real"] == 400.0
    assert out["capital_max_exposed"] == 500.0
    assert out["pipeline"] == {"requested": 1000.0, "approved": 1000.0, "processed": 900.0,
                               "received": 900.0, "in_transit": 0}
    assert out["times_days"] == {
        "requested_to_approved": {"median": 2.0, "max": 2.0, "n": 1},
        "approved_to_processed": {"median": 2.0, "max": 2.0, "n": 1},
        "processed_to_received": {"median": 2.0, "max": 2.0, "n": 1},
    }
    assert out["by_firm"] == {"f1": {"costs": 500.0, "received": 900.0, "net": 400.0}}
    assert out["by_account"] == {"A1": {"costs": 500.0, "received": 900.0, "net": 400.0}}
    assert out["received_local"] == {"EUR": 800.0}
    assert out["alerts"] == []
    assert out["n_payouts"] == {"requested": 0, "approved": 0, "processed": 0, "received": 1, "rejected": 0}


def test_la_conexion_del_servidor_no_puede_escribir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.db"
    _synthetic_ledger(path)
    monkeypatch.setattr(state, "LEDGER_PATH", path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    con = state._open_readonly()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("INSERT INTO ledger_events (ts, account_id, event, amount_usd) "
                        "VALUES ('2026-01-13T09:00:00', 'A1', 'fee_paid', -1.0)")
        with pytest.raises(sqlite3.OperationalError):
            con.execute("DELETE FROM ledger_events")
    finally:
        con.close()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_sin_libro_responde_sin_datos_y_no_crea_nada(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "no_existe" / "ledger.db"
    monkeypatch.setattr(state, "LEDGER_PATH", path)
    out = state.ledger_summary(TODAY)
    assert out == {"status": "Sin datos", "path": str(path)}
    assert not path.exists()
    assert not path.parent.exists()


def test_las_herramientas_no_escriben_en_el_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ledger.db"
    _synthetic_ledger(path)
    monkeypatch.setattr(state, "LEDGER_PATH", path)
    roots = [r for r in (ROOT / "config", ROOT / "data") if r.exists()]
    before = {str(r): _snapshot(r) for r in roots}
    state.programs(TODAY)
    state.ranking()
    state.alerts(TODAY)
    state.ledger_summary(TODAY)
    assert {str(r): _snapshot(r) for r in roots} == before
