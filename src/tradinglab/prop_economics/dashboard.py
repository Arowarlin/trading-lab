"""Carga útil del panel de economía de futuros (dashboard_model.md §1-5; FUT-H2/P6). Solo lectura.

Tres bloques que NUNCA se suman: ``real`` (libro del operador), ``nominal`` (saldo que muestra la firma,
de snapshots de la plataforma) y ``simulated`` (motor EV, siempre con la ventaja supuesta). Además el
registro de programas, el ranking con evidencia y los avisos del PFIE.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import ROOT
from .alerts import collect_alerts
from .ledger import open_ledger, summary
from .registry import load_firms, load_programs, registry_report
from .scoring import score_firms

LEDGER_PATH = ROOT / "data" / "prop_economics" / "ledger.db"
SIM_REPORTS = ROOT / "data" / "prop_economics" / "reports"


def _today() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


def economics_payload(*, today: date | None = None, ledger_path: Path = LEDGER_PATH,
                      reports_dir: Path = SIM_REPORTS) -> dict:
    day = today or _today()
    if Path(ledger_path).exists():
        con = open_ledger(ledger_path, readonly=True)
        try:
            real = {"status": "ok", **summary(con, today=day)}
        finally:
            con.close()
    else:
        real = {"status": "Sin datos: no hay libro real todavía"}
    reports = sorted(Path(reports_dir).glob("*.json")) if Path(reports_dir).exists() else []
    simulated = {"label": "SIMULADO · ventaja supuesta", "reports": [p.name for p in reports[-20:]]}
    firms = load_firms()
    return {
        "generated_for": day.isoformat(),
        "real": real,
        "nominal": {"status": "Sin datos: no hay snapshots de plataforma (FUT-J)"},
        "simulated": simulated,
        "catalog": {fid: {"automation": (f.get("automation") or {}).get("category"),
                          "execution_mode": f.get("execution_mode")} for fid, f in firms.items()},
        "registry": registry_report(day, firms=firms, programs=load_programs()),
        "ranking": score_firms(),
        "alerts": collect_alerts(day),
    }
