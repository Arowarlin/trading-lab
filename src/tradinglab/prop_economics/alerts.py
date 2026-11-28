"""Avisos del PFIE (FUT-P5): reglas caducadas o a punto, incógnitas, páginas cambiadas. Solo lectura.

No programa nada: ``lab propecon watch`` se ejecuta a mano (una tarea programada exige la aprobación del
operador, AGENTS.md).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .registry import load_firms, load_programs, registry_report
from .rules import is_expired
from .sources import SNAPSHOTS, latest_change


def collect_alerts(today: date, *, warn_days: int = 7, snapshots: Path = SNAPSHOTS) -> list[dict]:
    programs = load_programs()
    alerts: list[dict] = []
    for pid, p in sorted(programs.items()):
        if p.firm_id == "synthetic":
            continue
        if is_expired(p, today):
            alerts.append({"alert": "rules_expired", "program": pid})
        elif is_expired(p, today + timedelta(days=warn_days)):
            alerts.append({"alert": "rules_expiring", "program": pid,
                           "expires_on": (p.consulted_at + timedelta(days=p.expires_after_days)).isoformat()})
    rep = registry_report(today, firms=load_firms(), programs=programs)
    for pid, unknowns in sorted(rep["unknowns"].items()):
        if unknowns:
            alerts.append({"alert": "rules_unknown", "program": pid, "keys": unknowns})
    if snapshots.exists():
        for firm_dir in sorted(d for d in snapshots.iterdir() if d.is_dir()):
            for page_dir in sorted(d for d in firm_dir.iterdir() if d.is_dir()):
                ch = latest_change(firm_dir.name, page_dir.name, root=snapshots)
                if ch["changed"]:
                    alerts.append({"alert": "source_changed", "firm": ch["firm"], "page": ch["page"],
                                   "diff": ch["diff"][:2000]})
    return alerts
