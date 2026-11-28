"""FUT-J2: ticket semimanual (caduca en last_entry; el fill manual va al libro real)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tradinglab.config import ROOT
from tradinglab.futures.execution.intent import build_intent, load_execution_config
from tradinglab.futures.execution.riskcheck import AccountView, CheckContext, check
from tradinglab.futures.execution.ticket import ExecutionBook, TicketAdapter, TicketError
from tradinglab.prop_economics.rules import load_program

CT = ZoneInfo("America/Chicago")
NOW = datetime(2026, 12, 1, 10, 0, tzinfo=CT)
CFG = load_execution_config()
TOPSTEP = load_program(ROOT / "config" / "prop_economics" / "programs" / "topstep_50k_combine_xfa.yaml")


def make(adapter="ticket", stop=20990.0):
    i = build_intent(program=TOPSTEP, cfg=CFG, strategy_id="S1", hypothesis_id="forward:t", account_id="A",
                     phase="evaluation", root="MNQ", contract="MNQZ6", side="buy", qty=5, entry_type="limit",
                     entry_price=21000.0, stop_price=stop, target_price=21015.0,
                     exit_by=datetime(2026, 12, 1, 14, 0, tzinfo=CT), origin="semi_manual", adapter=adapter,
                     signal_hash="h", created_at=NOW)
    res = check(i, TOPSTEP, AccountView("A", 50000.0, 50000.0),
                CheckContext(now=NOW, firm_category="prohibited", policy_risk_usd=500.0), CFG)
    return i, res


@pytest.fixture()
def adapter(tmp_path):
    sent: list[str] = []
    a = TicketAdapter(ExecutionBook(tmp_path / "exec.db"), sent.append)
    a.sent = sent
    return a


def test_ticket_created_and_notified(adapter):
    i, res = make()
    assert res.ok, res.reasons
    t = adapter.submit(i, res, now=NOW, last_entry=NOW + timedelta(hours=5))
    assert len(adapter.sent) == 1
    for piece in ("TICKET SEMIMANUAL", "BUY 5 MNQZ6", "STOP 20990", "OBJETIVO 21015", "Riesgo 111.10 USD"):
        assert piece in t.text
    assert adapter.book.ticket(t.ticket_id)["status"] == "pending"


def test_confirm_records_real_fill(adapter):
    i, res = make()
    t = adapter.submit(i, res, now=NOW, last_entry=NOW + timedelta(hours=5))
    adapter.confirm_fill(t.ticket_id, now=NOW + timedelta(minutes=3), price=21000.25, qty=5, entered_by="operador")
    assert adapter.book.fills() == [(i.intent_id, t.ticket_id, 21000.25, 5, 1)]
    assert adapter.book.ticket(t.ticket_id)["status"] == "confirmed"
    with pytest.raises(TicketError):
        adapter.confirm_fill(t.ticket_id, now=NOW + timedelta(minutes=4), price=21000.0, qty=5, entered_by="x")


def test_ticket_expires_at_last_entry(adapter):
    i, res = make()
    t = adapter.submit(i, res, now=NOW, last_entry=NOW + timedelta(minutes=10))
    with pytest.raises(TicketError):
        adapter.confirm_fill(t.ticket_id, now=NOW + timedelta(minutes=10), price=21000.0, qty=5, entered_by="x")
    assert adapter.book.ticket(t.ticket_id)["status"] == "expired"
    assert adapter.book.fills() == []


def test_rejected_intent_never_becomes_ticket(adapter):
    i, res = make(stop=21010.0)                       # stop al lado equivocado
    assert not res.ok
    with pytest.raises(TicketError):
        adapter.submit(i, res, now=NOW, last_entry=NOW + timedelta(hours=5))
    assert adapter.sent == []
    assert adapter.book.con.execute("SELECT COUNT(*) FROM checks").fetchone()[0] == 1   # el control queda registrado


def test_wrong_adapter_and_late_submit(adapter):
    i, res = make(adapter="paper")
    with pytest.raises(TicketError):
        adapter.submit(i, res, now=NOW, last_entry=NOW + timedelta(hours=5))
    i, res = make()
    with pytest.raises(TicketError):
        adapter.submit(i, res, now=NOW, last_entry=NOW)


def test_fills_table_rejects_simulated_rows(adapter):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        adapter.book.con.execute("INSERT INTO fills VALUES ('f', 'i', NULL, 't', 1.0, 1, 0, 'sim', NULL)")
