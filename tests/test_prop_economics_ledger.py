"""FUT-H1: libro real (dashboard_model.md §3-5): inmutable, invariantes, cifras exactas y alertas."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from tradinglab.prop_economics.ledger import (
    LedgerError,
    add_account,
    add_event,
    open_ledger,
    payouts,
    summary,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "tradinglab" / "prop_economics"


@pytest.fixture()
def con(tmp_path):
    c = open_ledger(tmp_path / "ledger.db")
    add_account(c, "A1", firm_id="topstep", program_id="topstep_50k_combine_xfa", rules_version="2026-11-27.1",
                origin="automated", opened_at="2027-01-02", platform="projectx")
    add_account(c, "A2", firm_id="lucid", program_id="lucid_flex_50k", rules_version="2026-11-27.1",
                origin="semi_manual", opened_at="2027-01-05")
    ev = [
        ("2027-01-02", "A1", "fee_paid", -49.0, None),
        ("2027-01-02", "A1", "account_opened", 0.0, None),
        ("2027-01-05", "A2", "fee_paid", -125.0, None),
        ("2027-01-20", "A1", "account_passed", 0.0, None),
        ("2027-01-20", "A1", "activation_paid", -149.0, None),
        ("2027-02-10", "A1", "payout_requested", 1000.0, "P1"),
        ("2027-02-11", "A1", "payout_approved", 1000.0, "P1"),
        ("2027-02-13", "A1", "payout_processed", 900.0, "P1"),
        ("2027-03-01", "A2", "payout_requested", 500.0, "P2"),
        ("2027-03-01", "A1", "subscription_paid", -14.5, None),
        ("2027-03-02", "A2", "payout_approved", 500.0, "P2"),
        ("2027-03-03", "A2", "payout_processed", 450.0, "P2"),
    ]
    for ts, acc, event, amount, pid in ev:
        add_event(c, ts=ts, account_id=acc, event=event, amount_usd=amount, payout_id=pid)
    add_event(c, ts="2027-02-18", account_id="A1", event="payout_received", amount_usd=870.0, payout_id="P1",
              amount_local=50460.0, currency_local="DOP", fx_rate=58.0, evidence_path="evidencia/p1.pdf")
    yield c
    c.close()


def test_summary_exact(con):
    s = summary(con, today=date(2027, 3, 20), budget=300.0, next_eval_price=125.0)
    assert s["costs_paid"] == pytest.approx(337.5)
    assert s["received"] == pytest.approx(870.0)
    assert s["net_real"] == pytest.approx(532.5)
    assert s["capital_max_exposed"] == pytest.approx(323.0)
    assert s["pipeline"] == pytest.approx({"requested": 1500.0, "approved": 1500.0, "processed": 1350.0,
                                           "received": 870.0, "in_transit": 450.0})
    assert s["times_days"]["requested_to_approved"]["median"] == pytest.approx(1.0)
    assert s["times_days"]["approved_to_processed"]["median"] == pytest.approx(1.5)
    assert s["times_days"]["processed_to_received"]["median"] == pytest.approx(5.0)
    assert s["by_firm"]["topstep"] == pytest.approx({"costs": 212.5, "received": 870.0, "net": 657.5})
    assert s["by_firm"]["lucid"] == pytest.approx({"costs": 125.0, "received": 0.0, "net": -125.0})
    assert s["received_local"] == {"DOP": 50460.0}
    assert s["n_payouts"]["received"] == 1 and s["n_payouts"]["processed"] == 1
    assert [a["alert"] for a in s["alerts"]] == ["payout_delayed"]


def test_budget_low_alert(con):
    s = summary(con, today=date(2027, 3, 5), budget=0.0, next_eval_price=1000.0)
    assert [a["alert"] for a in s["alerts"]] == ["budget_low"]


def test_payout_states(con):
    p = payouts(con)
    assert (p["P1"].state, p["P2"].state) == ("received", "processed")


@pytest.mark.parametrize("kwargs", [
    dict(account_id="A2", event="payout_approved", amount_usd=600.0, payout_id="P3"),      # aprobado sin pedido
    dict(account_id="A1", event="payout_received", amount_usd=10.0, payout_id="P9"),       # recibido sin procesado
    dict(account_id="A9", event="fee_paid", amount_usd=-1.0),                              # cuenta inexistente
    dict(account_id="A1", event="fee_paid", amount_usd=49.0),                              # coste en positivo
    dict(account_id="A1", event="account_failed", amount_usd=5.0),                         # estado con importe
    dict(account_id="A1", event="payout_requested", amount_usd=5.0),                       # payout sin id
    dict(account_id="A1", event="bonus", amount_usd=5.0),                                  # evento desconocido
    dict(account_id="A2", event="payout_received", amount_usd=460.0, payout_id="P2"),      # recibido > procesado
])
def test_invalid_events_rejected(con, kwargs):
    before = con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0]
    with pytest.raises(LedgerError):
        add_event(con, ts="2027-03-10", **kwargs)
    assert con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == before


def test_approved_cannot_exceed_requested(con):
    add_event(con, ts="2027-03-10", account_id="A2", event="payout_requested", amount_usd=300.0, payout_id="P4")
    with pytest.raises(LedgerError):
        add_event(con, ts="2027-03-11", account_id="A2", event="payout_approved", amount_usd=301.0, payout_id="P4")


def test_events_are_immutable(con):
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE ledger_events SET amount_usd = 0 WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM ledger_events WHERE id = 1")


def test_correction_changes_bucket(con):
    rid = con.execute("SELECT id FROM ledger_events WHERE event = 'payout_received'").fetchone()[0]
    with pytest.raises(LedgerError):
        add_event(con, ts="2027-03-12", account_id="A1", event="correction", amount_usd=-20.0, corrects_id=rid)
    add_event(con, ts="2027-03-12", account_id="A1", event="correction", amount_usd=-20.0, corrects_id=rid,
              note="comisión bancaria no descontada")
    s = summary(con, today=date(2027, 3, 12))
    assert s["received"] == pytest.approx(850.0)
    assert s["net_real"] == pytest.approx(512.5)


def test_readonly_connection_cannot_write(con, tmp_path):
    ro = open_ledger(tmp_path / "ledger.db", readonly=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO accounts VALUES ('X', 'f', 'p', 'v', NULL, 'automated', '2027-01-01')")
    ro.close()


def test_local_amount_needs_currency_and_rate(con):
    add_event(con, ts="2027-03-10", account_id="A2", event="payout_requested", amount_usd=300.0, payout_id="P5")
    add_event(con, ts="2027-03-10", account_id="A2", event="payout_approved", amount_usd=300.0, payout_id="P5")
    add_event(con, ts="2027-03-11", account_id="A2", event="payout_processed", amount_usd=270.0, payout_id="P5")
    with pytest.raises(LedgerError):
        add_event(con, ts="2027-03-14", account_id="A2", event="payout_received", amount_usd=270.0, payout_id="P5",
                  amount_local=15000.0)


def test_simulator_never_touches_the_ledger():
    for name in ("simulate.py", "project.py", "scenarios.py", "account.py", "fees.py", "paths.py", "rules.py"):
        assert "ledger" not in (SRC / name).read_text(encoding="utf-8").lower().replace("libro", ""), name
