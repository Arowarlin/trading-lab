"""Registro de firmas y programas con caducidad (PFIE; FUT-P1)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from ..config import ROOT
from .rules import Program, blocking_unknowns, is_expired, load_program

FIRMS_PATH = ROOT / "config" / "prop_economics" / "firms_futures.yaml"
PROGRAMS_DIR = ROOT / "config" / "prop_economics" / "programs"


def load_firms(path: str | Path = FIRMS_PATH) -> dict[str, dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    firms = data.get("firms", data)
    items = firms.values() if isinstance(firms, dict) else firms
    out = {}
    for f in items:
        fid = f.get("id") or f.get("firm_id")
        if not fid:
            raise ValueError("firma sin id")
        out[fid] = f
    return out


def load_programs(directory: str | Path = PROGRAMS_DIR) -> dict[str, Program]:
    return {p.program_id: p for p in (load_program(f) for f in sorted(Path(directory).glob("*.yaml")))}


def registry_report(today: date, *, firms: dict | None = None, programs: dict | None = None) -> dict:
    """Programas por firma, firmas sin programa, programas de firmas desconocidas y caducados."""
    firms = load_firms() if firms is None else firms
    programs = load_programs() if programs is None else programs
    real = {pid: p for pid, p in programs.items() if p.firm_id != "synthetic"}
    return {
        "programs_by_firm": {fid: sorted(pid for pid, p in real.items() if p.firm_id == fid) for fid in firms},
        "firms_without_program": sorted(fid for fid in firms if not any(p.firm_id == fid for p in real.values())),
        "unknown_firm_programs": sorted(pid for pid, p in real.items() if p.firm_id not in firms),
        "expired": sorted(pid for pid, p in real.items() if is_expired(p, today)),
        "unknowns": {pid: blocking_unknowns(p) for pid, p in real.items()},
    }
