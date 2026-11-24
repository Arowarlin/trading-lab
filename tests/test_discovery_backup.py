"""T02 · Copia automática de discovery.db: integridad y retención sin borrar."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tradinglab.discovery import databank
from tradinglab.discovery.backup import (
    OLD_DIRNAME,
    apply_retention,
    backup_after_action,
    backup_discovery,
)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "discovery.db"
    databank.init_databank(path)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS prueba(id INTEGER PRIMARY KEY, valor TEXT)")
        con.execute("INSERT INTO prueba(valor) VALUES ('uno')")
    return path


def test_copia_de_una_base_temporal_y_integridad(tmp_path):
    source = _db(tmp_path)
    copy = backup_discovery(source, now=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
    assert copy is not None and copy.exists()
    assert copy.name == "discovery_20261124T120000Z.db"
    with sqlite3.connect(copy) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT valor FROM prueba").fetchone()[0] == "uno"


def test_retencion_conserva_30_mas_la_primera_de_cada_mes_y_no_borra(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    total = 0
    for month in range(1, 5):
        for day in range(1, 11):
            stamp = datetime(2025, month, day, 0, 0, day, tzinfo=timezone.utc)
            (directory / f"discovery_{stamp.strftime('%Y%m%dT%H%M%SZ')}.db").write_bytes(b"x")
            total += 1
    moved = apply_retention(directory, keep_recent=30)
    in_place = sorted(directory.glob("discovery_*.db"))
    in_old = sorted((directory / OLD_DIRNAME).glob("discovery_*.db"))
    assert len(in_place) == 31  # 30 últimas + la primera de enero
    assert len(in_old) == total - 31
    assert len(moved) == total - 31
    assert in_place[0].name == "discovery_20250101T000001Z.db"
    # Nada se borra: el total se conserva.
    assert len(in_place) + len(in_old) == total


def test_hook_desactivado_no_escribe(tmp_path, monkeypatch):
    source = _db(tmp_path)
    monkeypatch.setattr("tradinglab.discovery.backup.backup_enabled", lambda: False)
    assert backup_after_action(source) is None
    assert not (tmp_path / "backups").exists()


def test_nombre_libre_si_dos_copias_caen_en_el_mismo_segundo(tmp_path):
    source = _db(tmp_path)
    moment = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    first = backup_discovery(source, now=moment)
    second = backup_discovery(source, now=moment)
    assert first is not None and second is not None
    assert first != second
    assert second.name == "discovery_20261124T120001Z.db"
    assert (tmp_path / "backups").joinpath(first.name).exists()
