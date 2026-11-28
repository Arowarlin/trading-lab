"""Servidor MCP ``tradinglab-state`` de solo lectura (FUT-T2).

Da a Claude y a OpenCode las mismas respuestas sobre el estado del laboratorio
(``docs/futures/02_EXTENSIONES_CLAUDE_CODE.md §4``). Las cuatro herramientas son
de **solo lectura**: no escriben ficheros, no crean bases y el libro real se abre
siempre con ``mode=ro``. Si el libro no existe, ``ledger_summary`` responde
«Sin datos» (``dashboard_model.md §1``) sin crearlo.

Transporte stdio. Arranque::

    python -m tradinglab.mcp_state.server
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server import MCPServer

from ..config import ROOT
from ..prop_economics import ledger
from ..prop_economics.alerts import collect_alerts
from ..prop_economics.registry import registry_report
from ..prop_economics.scoring import score_firms

LEDGER_PATH = ROOT / "data" / "prop_economics" / "ledger.db"
NY_TZ = ZoneInfo("America/New_York")

server = MCPServer(
    "tradinglab-state",
    description="Estado de solo lectura de TradingLab: programas, ranking, avisos y libro real.",
)


def _today(today: str | None) -> date:
    """Fecha de trabajo: la que pase el operador (YYYY-MM-DD) o el día en Nueva York."""
    return date.fromisoformat(today) if today else datetime.now(NY_TZ).date()


def _open_readonly(path: str | Path | None = None) -> sqlite3.Connection:
    """Abre el libro real en solo lectura: única puerta del servidor a SQLite."""
    return ledger.open_ledger(path or LEDGER_PATH, readonly=True)


@server.tool()
def programs(today: str | None = None) -> dict:
    """Programas por firma, firmas sin programa, programas huérfanos, caducados e incógnitas."""
    return registry_report(_today(today))


@server.tool()
def ranking() -> dict:
    """Ranking ponderado de firmas; las incompletas van aparte, sin total."""
    return score_firms()


@server.tool()
def alerts(today: str | None = None, warn_days: int = 7) -> list[dict]:
    """Avisos: reglas caducadas o a punto de caducar, incógnitas y páginas de fuente cambiadas."""
    return collect_alerts(_today(today), warn_days=warn_days)


@server.tool()
def ledger_summary(today: str | None = None) -> dict:
    """Cifras del libro real (pagado, recibido y neto). Sin libro: «Sin datos»."""
    path = LEDGER_PATH
    if not path.exists():
        return {"status": "Sin datos", "path": str(path)}
    con = _open_readonly(path)
    try:
        return ledger.summary(con, today=_today(today))
    finally:
        con.close()


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
