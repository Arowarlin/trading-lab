"""Un mercado a la vez: pilotos por mercado y gate de aperturas.

Seleccionar un piloto NO activa bots, NO congela F13 y NO envía órdenes. Solo
marca qué mercado puede abrir posiciones mientras el modo piloto esté activo;
los cierres/reducciones nunca se bloquean.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import ROOT, Settings
from .db import connect, init_db, utcnow
from .market_agents import market_for_symbol

PILOTS_FILE = ROOT / "config" / "market_pilots.yaml"
PROFILE_MARKET = {
    "intraday_fx": "forex",
    "intraday_futures": "futures",
    "swing_cfd": "cfd",
}


class PilotError(ValueError):
    pass


@dataclass(frozen=True)
class PilotSpec:
    market: str
    label: str
    bot: str | None
    profile: str
    status: str
    reason: str


def load_pilots(path: str | Path | None = None) -> dict[str, PilotSpec]:
    path = Path(path) if path else PILOTS_FILE
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for market, item in (raw.get("pilots") or {}).items():
        data = item or {}
        out[str(market)] = PilotSpec(
            market=str(market),
            label=str(data.get("label") or market),
            bot=data.get("bot"),
            profile=str(data.get("profile") or ""),
            status=str(data.get("status") or "not_started"),
            reason=str(data.get("reason") or ""),
        )
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS market_pilot_state (
    market TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS market_pilot_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    market TEXT NOT NULL,
    before_active INTEGER,
    after_active INTEGER NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT
);
"""


def init_pilots(db_path: str | Path) -> None:
    init_db(db_path)
    with connect(db_path) as con:
        con.executescript(SCHEMA)


def _states(db_path: str | Path) -> dict[str, dict]:
    init_pilots(db_path)
    with connect(db_path) as con:
        rows = con.execute("SELECT * FROM market_pilot_state").fetchall()
    return {row["market"]: dict(row) for row in rows}


def active_market(db_path: str | Path) -> str | None:
    active = [
        market
        for market, state in _states(db_path).items()
        if int(state.get("active") or 0) == 1
    ]
    if len(active) > 1:
        raise PilotError(
            "estado inconsistente: más de un mercado activo; limpia los pilotos"
        )
    return active[0] if active else None


def pilot_status(
    db_path: str | Path, settings: Settings | None = None
) -> dict:
    settings = settings or Settings()
    specs = load_pilots()
    states = _states(db_path)
    rows = []
    for market, spec in sorted(specs.items()):
        state = states.get(market) or {}
        rows.append(
            {
                "market": market,
                "label": spec.label,
                "bot": spec.bot,
                "profile": spec.profile,
                "status": spec.status,
                "reason": spec.reason,
                "active": bool(int(state.get("active") or 0)),
                "updated_at": state.get("updated_at"),
                "updated_by": state.get("updated_by"),
            }
        )
    return {
        "active_market": active_market(db_path),
        "count": len(rows),
        "pilots": rows,
        "mode": settings.mode,
        "note": "Seleccionar un piloto no activa bots ni F13; solo limita aperturas.",
    }


def select_pilot(
    db_path: str | Path,
    market: str,
    *,
    confirm: bool,
    actor: str = "cli",
    specs: dict[str, PilotSpec] | None = None,
) -> dict:
    if not confirm:
        raise PilotError("seleccionar un piloto exige confirmación explícita")
    specs = specs if specs is not None else load_pilots()
    spec = specs.get(market)
    if spec is None:
        raise PilotError(f"mercado desconocido: {market}")
    if spec.status == "blocked":
        raise PilotError(f"{market} bloqueado: {spec.reason}")
    init_pilots(db_path)
    with connect(db_path) as con:
        for key, state in _states(db_path).items():
            if int(state.get("active") or 0) == 1 and key != market:
                con.execute(
                    "UPDATE market_pilot_state SET active=0, updated_at=?, updated_by=?, "
                    "reason=? WHERE market=?",
                    (utcnow(), actor, f"cambio a {market}", key),
                )
                con.execute(
                    "INSERT INTO market_pilot_history"
                    "(ts, market, before_active, after_active, actor, reason) "
                    "VALUES(?,?,?,?,?,?)",
                    (utcnow(), key, 1, 0, actor, f"cambio a {market}"),
                )
        con.execute(
            "INSERT INTO market_pilot_state(market, active, updated_at, updated_by, reason) "
            "VALUES(?,?,?,?,?) ON CONFLICT(market) DO UPDATE SET "
            "active=1, updated_at=excluded.updated_at, updated_by=excluded.updated_by, "
            "reason=excluded.reason",
            (market, 1, utcnow(), actor, "piloto seleccionado"),
        )
        con.execute(
            "INSERT INTO market_pilot_history"
            "(ts, market, before_active, after_active, actor, reason) "
            "VALUES(?,?,?,?,?,?)",
            (utcnow(), market, None, 1, actor, "piloto seleccionado"),
        )
    return pilot_status(db_path)


def clear_pilots(
    db_path: str | Path, *, confirm: bool, actor: str = "cli"
) -> dict:
    if not confirm:
        raise PilotError("limpiar pilotos exige confirmación explícita")
    init_pilots(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT market FROM market_pilot_state WHERE active=1"
        ).fetchall()
        con.execute(
            "UPDATE market_pilot_state SET active=0, updated_at=?, updated_by=?, "
            "reason='pilotos limpiados'",
            (utcnow(), actor),
        )
        for row in rows:
            con.execute(
                "INSERT INTO market_pilot_history"
                "(ts, market, before_active, after_active, actor, reason) "
                "VALUES(?,?,?,?,?,?)",
                (utcnow(), row["market"], 1, 0, actor, "pilotos limpiados"),
            )
    return pilot_status(db_path)


def market_for_bot(spec) -> str | None:
    if getattr(spec, "profile", None) in PROFILE_MARKET:
        return PROFILE_MARKET[spec.profile]
    for symbol in getattr(spec, "universe", []) or []:
        try:
            return market_for_symbol(symbol)
        except Exception:
            continue
    return None


def market_for_account(account) -> str | None:
    return {
        "intraday_fx": "forex",
        "intraday_futures": "futures",
        "swing_cfd": "cfd",
    }.get(getattr(account, "pocket", ""))


def allows_market(db_path: str | Path, market: str | None) -> tuple[bool, str]:
    active = active_market(db_path)
    if active is None:
        return True, "sin piloto activo"
    if market == active:
        return True, f"piloto activo: {active}"
    return False, f"piloto activo {active}; mercado {market or 'sin datos'} bloqueado"


__all__ = [
    "PILOTS_FILE",
    "PilotError",
    "PilotSpec",
    "active_market",
    "allows_market",
    "clear_pilots",
    "init_pilots",
    "load_pilots",
    "market_for_account",
    "market_for_bot",
    "pilot_status",
    "select_pilot",
]
