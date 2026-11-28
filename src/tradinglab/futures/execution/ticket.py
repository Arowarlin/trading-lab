"""Ticket semimanual y libro de ejecución (execution_spec.md §5; FUT-J2).

En las firmas que no aceptan bots (o sin la confirmación de sus condiciones), el sistema NO envía órdenes:
genera un ticket con todo lo necesario, lo notifica y espera a que una persona lo confirme y registre el
fill. El ticket caduca en ``last_entry``. Los fills manuales van al libro REAL de ejecución
(``data/futures/execution.db``); los del paper nunca entran ahí.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ...config import ROOT
from .intent import OrderIntent
from .riskcheck import RiskResult

BOOK_PATH = ROOT / "data" / "futures" / "execution.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (intent_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY AUTOINCREMENT, intent_id TEXT NOT NULL, ts TEXT NOT NULL,
    ok INTEGER NOT NULL, reasons TEXT NOT NULL, warnings TEXT NOT NULL, metrics TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, status TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fills (fill_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL, ticket_id TEXT, ts TEXT NOT NULL,
    price REAL NOT NULL, qty INTEGER NOT NULL CHECK (qty > 0), real INTEGER NOT NULL CHECK (real = 1),
    entered_by TEXT NOT NULL, evidence_path TEXT);
"""


class TicketError(ValueError):
    pass


class ExecutionBook:
    """Libro de intents, controles, tickets y fills REALES (manuales o de plataforma)."""

    def __init__(self, path: str | Path = BOOK_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)

    def record_intent(self, intent: OrderIntent, result: RiskResult, ts: datetime) -> None:
        payload = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(intent).items()}
        self.con.execute("INSERT OR IGNORE INTO intents VALUES (?, ?, ?)",
                         (intent.intent_id, intent.created_at.isoformat(), json.dumps(payload, default=str)))
        self.con.execute("INSERT INTO checks (intent_id, ts, ok, reasons, warnings, metrics) VALUES (?, ?, ?, ?, ?, ?)",
                         (intent.intent_id, ts.isoformat(), int(result.ok), json.dumps(result.reasons),
                          json.dumps(result.warnings), json.dumps(result.metrics, default=str)))
        self.con.commit()

    def ticket(self, ticket_id: str) -> dict | None:
        row = self.con.execute("SELECT ticket_id, intent_id, created_at, expires_at, status, text FROM tickets "
                               "WHERE ticket_id = ?", (ticket_id,)).fetchone()
        keys = ("ticket_id", "intent_id", "created_at", "expires_at", "status", "text")
        return None if row is None else dict(zip(keys, row))

    def fills(self) -> list[tuple]:
        return list(self.con.execute("SELECT intent_id, ticket_id, price, qty, real FROM fills ORDER BY ts"))


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    intent_id: str
    created_at: datetime
    expires_at: datetime
    text: str


def ticket_text(intent: OrderIntent, expires_at: datetime) -> str:
    target = "sin objetivo" if intent.target_price is None else f"{intent.target_price:g}"
    return (f"TICKET SEMIMANUAL · {intent.firm_id}/{intent.program_id} · cuenta {intent.account_id}\n"
            f"{intent.side.upper()} {intent.qty} {intent.contract} ({intent.root}) · {intent.entry_type} "
            f"{intent.entry_price:g} · STOP {intent.stop_price:g} · OBJETIVO {target}\n"
            f"Riesgo {intent.risk_usd:.2f} USD (costes {intent.cost_usd:.2f}{', supuestos' if intent.cost_assumed else ''})"
            f" · cerrar antes de {intent.exit_by.isoformat()}\n"
            f"Caduca: {expires_at.isoformat()} · estrategia {intent.strategy_id} · {intent.hypothesis_id}\n"
            "Paper/demo solamente. Ejecuta tú la orden y registra el fill con su evidencia.")


class TicketAdapter:
    name = "ticket"

    def __init__(self, book: ExecutionBook, notify: Callable[[str], None]):
        self.book = book
        self.notify = notify

    def submit(self, intent: OrderIntent, result: RiskResult, *, now: datetime, last_entry: datetime) -> Ticket:
        self.book.record_intent(intent, result, now)
        if intent.adapter != "ticket":
            raise TicketError("el intent no es para ticket")
        if not result.ok:
            raise TicketError("el control de riesgo rechazó el intent: " + ", ".join(result.reasons))
        if now >= last_entry:
            raise TicketError("fuera de la ventana de entrada")
        t = Ticket(str(uuid.uuid4()), intent.intent_id, now, last_entry, ticket_text(intent, last_entry))
        self.book.con.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, 'pending', ?)",
                              (t.ticket_id, t.intent_id, now.isoformat(), last_entry.isoformat(), t.text))
        self.book.con.commit()
        self.notify(t.text)
        return t

    def confirm_fill(self, ticket_id: str, *, now: datetime, price: float, qty: int, entered_by: str,
                     evidence_path: str | None = None) -> str:
        """La persona confirma que ejecutó la orden: el fill entra en el libro REAL."""
        t = self.book.ticket(ticket_id)
        if t is None:
            raise TicketError("ticket inexistente")
        if t["status"] != "pending":
            raise TicketError(f"ticket {t['status']}")
        if now >= datetime.fromisoformat(t["expires_at"]):
            self.book.con.execute("UPDATE tickets SET status = 'expired' WHERE ticket_id = ?", (ticket_id,))
            self.book.con.commit()
            raise TicketError("ticket caducado")
        fill_id = str(uuid.uuid4())
        self.book.con.execute("INSERT INTO fills VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                              (fill_id, t["intent_id"], ticket_id, now.isoformat(), price, qty, entered_by,
                               evidence_path))
        self.book.con.execute("UPDATE tickets SET status = 'confirmed' WHERE ticket_id = ?", (ticket_id,))
        self.book.con.commit()
        return fill_id
