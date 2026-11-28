"""Libro REAL de prop firms (docs/futures/research/dashboard_model.md §3-5) — FUT-H1.

Solo lo escribe el operador (comando manual con evidencia). El simulador no lo importa ni lo abre en
escritura. Los eventos son inmutables: SQLite rechaza UPDATE y DELETE; una corrección es un evento
``correction`` con ``corrects_id`` y un importe delta.

Dinero ganado = solo ``payout_received``. Neto real = recibido − costes pagados.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from statistics import median

COST_EVENTS = frozenset({"fee_paid", "reset_paid", "activation_paid", "subscription_paid", "transfer_fee"})
STATE_EVENTS = frozenset({"account_opened", "account_passed", "account_failed", "account_closed", "to_live"})
PAYOUT_EVENTS = ("payout_requested", "payout_approved", "payout_rejected", "payout_processed", "payout_received")
EVENTS = COST_EVENTS | STATE_EVENTS | frozenset(PAYOUT_EVENTS) | {"correction"}
PAYOUT_ORDER = {"payout_requested": 0, "payout_approved": 1, "payout_processed": 2, "payout_received": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    firm_id TEXT NOT NULL,
    program_id TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    platform TEXT,
    origin TEXT NOT NULL CHECK (origin IN ('automated', 'semi_manual')),
    opened_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    event TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    amount_local REAL,
    currency_local TEXT,
    fx_rate REAL,
    payout_id TEXT,
    corrects_id INTEGER REFERENCES ledger_events(id),
    evidence_path TEXT,
    note TEXT
);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger_events
BEGIN SELECT RAISE(ABORT, 'ledger_events es inmutable: usa un evento correction'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger_events
BEGIN SELECT RAISE(ABORT, 'ledger_events es inmutable: usa un evento correction'); END;
"""


class LedgerError(ValueError):
    """El evento violaría una regla del libro real."""


def open_ledger(path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
    con.execute("PRAGMA foreign_keys = ON")
    con.row_factory = sqlite3.Row
    return con


def add_account(con: sqlite3.Connection, account_id: str, *, firm_id: str, program_id: str, rules_version: str,
                origin: str, opened_at: str, platform: str | None = None) -> None:
    con.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_id, firm_id, program_id, rules_version, platform, origin, opened_at))
    con.commit()


@dataclass
class Payout:
    payout_id: str
    account_id: str
    amounts: dict[str, float] = field(default_factory=dict)   # evento -> importe (con correcciones)
    dates: dict[str, str] = field(default_factory=dict)       # evento -> primera fecha
    rejected: bool = False

    @property
    def state(self) -> str:
        if self.rejected:
            return "rejected"
        reached = [e for e in PAYOUT_ORDER if e in self.amounts]
        return max(reached, key=PAYOUT_ORDER.get).removeprefix("payout_") if reached else "none"


def _events(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM ledger_events ORDER BY ts, id")]


def _effective(events: list[dict]) -> list[dict]:
    """Aplica las correcciones: el delta suma al importe del evento corregido."""
    by_id = {e["id"]: dict(e) for e in events if e["event"] != "correction"}
    for e in events:
        if e["event"] == "correction":
            by_id[e["corrects_id"]]["amount_usd"] += e["amount_usd"]
    return sorted(by_id.values(), key=lambda e: (e["ts"], e["id"]))


def payouts(con: sqlite3.Connection) -> dict[str, Payout]:
    return _payouts_from(_effective(_events(con)))


def _payouts_from(events: list[dict]) -> dict[str, Payout]:
    out: dict[str, Payout] = {}
    for e in events:
        if e["event"] not in PAYOUT_EVENTS:
            continue
        p = out.setdefault(e["payout_id"], Payout(e["payout_id"], e["account_id"]))
        if e["event"] == "payout_rejected":
            p.rejected = True
            p.dates.setdefault("payout_rejected", e["ts"])
            continue
        p.amounts[e["event"]] = p.amounts.get(e["event"], 0.0) + e["amount_usd"]
        p.dates.setdefault(e["event"], e["ts"])
    return out


def check_invariants(events: list[dict], account_ids: set[str]) -> list[str]:
    """Los 7 invariantes de dashboard_model.md §3 (el 6 y el 7 los garantizan SQLite y el diseño)."""
    errors: list[str] = []
    for e in events:
        if e["account_id"] not in account_ids:
            errors.append(f"evento {e['id']}: cuenta inexistente {e['account_id']}")
    for p in _payouts_from(_effective(events)).values():
        a = p.amounts
        if "payout_approved" in a and a["payout_approved"] > a.get("payout_requested", 0.0) + 1e-9:
            errors.append(f"{p.payout_id}: aprobado > pedido")
        if "payout_processed" in a and "payout_approved" not in a:
            errors.append(f"{p.payout_id}: procesado sin aprobado")
        if "payout_processed" in a and a["payout_processed"] > a.get("payout_approved", 0.0) + 1e-9:
            errors.append(f"{p.payout_id}: procesado > aprobado")
        if "payout_received" in a and "payout_processed" not in a:
            errors.append(f"{p.payout_id}: recibido sin procesado")
        if "payout_received" in a and a["payout_received"] > a.get("payout_processed", 0.0) + 0.01:
            errors.append(f"{p.payout_id}: recibido > procesado + 0,01")
    return errors


def add_event(con: sqlite3.Connection, *, ts: str, account_id: str, event: str, amount_usd: float,
              payout_id: str | None = None, corrects_id: int | None = None, amount_local: float | None = None,
              currency_local: str | None = None, fx_rate: float | None = None, evidence_path: str | None = None,
              note: str | None = None) -> int:
    """Añade un evento si respeta las reglas; si no, LedgerError y no escribe nada."""
    if event not in EVENTS:
        raise LedgerError(f"evento desconocido: {event}")
    datetime.fromisoformat(ts)
    if event in COST_EVENTS and amount_usd > 0:
        raise LedgerError("los costes van en negativo")
    if event in STATE_EVENTS and amount_usd != 0:
        raise LedgerError("los cambios de estado llevan importe 0")
    if event in PAYOUT_EVENTS:
        if not payout_id:
            raise LedgerError("los eventos de payout necesitan payout_id")
        if amount_usd < 0 or (event == "payout_rejected" and amount_usd != 0):
            raise LedgerError("importe de payout no válido")
    if event == "correction":
        if corrects_id is None or note is None:
            raise LedgerError("una corrección necesita corrects_id y note")
        target = con.execute("SELECT event FROM ledger_events WHERE id = ?", (corrects_id,)).fetchone()
        if target is None or target["event"] == "correction":
            raise LedgerError("corrects_id debe apuntar a un evento existente que no sea una corrección")
    elif corrects_id is not None:
        raise LedgerError("corrects_id solo vale para correction")
    if event == "payout_received" and amount_local is not None and (currency_local is None or fx_rate is None):
        raise LedgerError("con importe local hacen falta moneda y tipo de cambio")
    accounts = {r["account_id"] for r in con.execute("SELECT account_id FROM accounts")}
    candidate = {"id": -1, "ts": ts, "account_id": account_id, "event": event, "amount_usd": float(amount_usd),
                 "payout_id": payout_id, "corrects_id": corrects_id}
    errors = check_invariants([*_events(con), candidate], accounts)
    if errors:
        raise LedgerError("; ".join(errors))
    cur = con.execute(
        "INSERT INTO ledger_events (ts, account_id, event, amount_usd, amount_local, currency_local, fx_rate, "
        "payout_id, corrects_id, evidence_path, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, account_id, event, float(amount_usd), amount_local, currency_local, fx_rate, payout_id, corrects_id,
         evidence_path, note))
    con.commit()
    return int(cur.lastrowid)


def _days(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400.0


def summary(con: sqlite3.Connection, *, today: date, budget: float | None = None, delay_days: float = 10.0,
            next_eval_price: float | None = None) -> dict:
    """Cifras del dashboard (dashboard_model.md §4) y alertas (§5) del libro real."""
    events = _effective(_events(con))
    accounts = {r["account_id"]: dict(r) for r in con.execute("SELECT * FROM accounts")}
    costs = -sum(e["amount_usd"] for e in events if e["event"] in COST_EVENTS)
    received = sum(e["amount_usd"] for e in events if e["event"] == "payout_received")
    running, max_out = 0.0, 0.0
    for e in events:
        if e["event"] in COST_EVENTS:
            running -= e["amount_usd"]
        elif e["event"] == "payout_received":
            running -= e["amount_usd"]
        max_out = max(max_out, running)
    pays = _payouts_from(events)
    pipeline = {k: sum(p.amounts.get(f"payout_{k}", 0.0) for p in pays.values())
                for k in ("requested", "approved", "processed", "received")}
    pipeline["in_transit"] = sum(p.amounts["payout_processed"] for p in pays.values() if p.state == "processed")
    lags = {"requested_to_approved": [], "approved_to_processed": [], "processed_to_received": []}
    for p in pays.values():
        for key, (a, b) in {"requested_to_approved": ("payout_requested", "payout_approved"),
                            "approved_to_processed": ("payout_approved", "payout_processed"),
                            "processed_to_received": ("payout_processed", "payout_received")}.items():
            if a in p.dates and b in p.dates:
                lags[key].append(_days(p.dates[a], p.dates[b]))
    times = {k: {"median": median(v), "max": max(v), "n": len(v)} if v else None for k, v in lags.items()}
    by_firm: dict[str, dict] = {}
    by_account: dict[str, dict] = {}
    for e in events:
        acc = accounts[e["account_id"]]
        for key, bucket in ((acc["firm_id"], by_firm), (e["account_id"], by_account)):
            row = bucket.setdefault(key, {"costs": 0.0, "received": 0.0})
            if e["event"] in COST_EVENTS:
                row["costs"] -= e["amount_usd"]
            elif e["event"] == "payout_received":
                row["received"] += e["amount_usd"]
    for bucket in (by_firm, by_account):
        for row in bucket.values():
            row["net"] = row["received"] - row["costs"]
    local: dict[str, float] = {}
    for e in _events(con):
        if e["event"] == "payout_received" and e["currency_local"]:
            local[e["currency_local"]] = local.get(e["currency_local"], 0.0) + float(e["amount_local"] or 0.0)
    alerts = []
    for p in pays.values():
        if p.state == "processed" and _days(p.dates["payout_processed"], today.isoformat()) > delay_days:
            alerts.append({"alert": "payout_delayed", "payout_id": p.payout_id, "account_id": p.account_id})
    if budget is not None and next_eval_price is not None and budget + received - costs < next_eval_price:
        alerts.append({"alert": "budget_low", "cash": budget + received - costs})
    return {"costs_paid": costs, "received": received, "net_real": received - costs,
            "capital_max_exposed": max_out, "pipeline": pipeline, "times_days": times,
            "by_firm": by_firm, "by_account": by_account, "received_local": local, "alerts": alerts,
            "n_payouts": {s: sum(1 for p in pays.values() if p.state == s)
                          for s in ("requested", "approved", "processed", "received", "rejected")}}
