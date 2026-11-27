"""ENG-1 · hallazgos menores sin efecto en resultados del motor (D-09, D-10)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.discovery import console, jobs


def test_d09_cuenta_informal_trials_y_no_oculta_el_error(tmp_path: Path, monkeypatch) -> None:
    lab = tmp_path / "lab.db"
    con = sqlite3.connect(lab)
    con.executescript(
        """
        CREATE TABLE lesson_tests (id INTEGER PRIMARY KEY);
        CREATE TABLE informal_trials (id INTEGER PRIMARY KEY, n INTEGER);
        INSERT INTO lesson_tests DEFAULT VALUES;
        INSERT INTO informal_trials (n) VALUES (200), (50);
        """
    )
    con.commit()
    con.close()
    counts = console.count_tests_readonly(lab)
    assert counts["informal_trials"] == 250
    assert counts["total"] == 251  # antes 1: faltaban las miradas informales

    def broken(db):
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(console.campaigns, "discovery_tests", broken)
    counts = console.count_tests_readonly(lab, tmp_path / "discovery.db")
    assert counts["discovery"] is None and counts["total"] is None  # antes 0 y 251
    assert counts["discovery_error"].startswith("Sin datos")


def test_d10_slice_bars_no_incluye_la_vela_del_dia_siguiente() -> None:
    index = pd.date_range("2024-06-30 22:00", "2024-07-01 02:00", freq="5min", tz="UTC")
    bars = pd.DataFrame({"close": np.arange(len(index), dtype=float)}, index=index)
    sliced = jobs._slice_bars(bars, None, "2024-06-30")
    assert sliced.index.max() < pd.Timestamp("2024-07-01", tz="UTC")
    assert sliced.index.max() == pd.Timestamp("2024-06-30 23:55", tz="UTC")
