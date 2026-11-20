from __future__ import annotations

import json
import os
import sqlite3
import zipfile
from pathlib import Path

from tradinglab.backup_check import (
    TABLES,
    TIME_COLUMNS,
    verify_backup,
    verify_latest_backup,
)


def _db(path: Path, rows: dict[str, list[str]]) -> None:
    con = sqlite3.connect(path)
    try:
        for table in TABLES:
            con.execute(
                f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {TIME_COLUMNS[table]} TEXT)"
            )
            for index, ts in enumerate(rows.get(table, []), 1):
                con.execute(
                    f"INSERT INTO {table}(id, {TIME_COLUMNS[table]}) VALUES (?, ?)",
                    (index, ts),
                )
        con.commit()
    finally:
        con.close()


def _zip(
    tmp_path: Path,
    rows: dict[str, list[str]],
    backup_at: str,
    *,
    name: str = "trading-lab_test.zip",
    manifest: bool = True,
    counts: dict[str, int] | None = None,
) -> Path:
    stage = tmp_path / f"stage_{Path(name).stem}"
    (stage / "data").mkdir(parents=True, exist_ok=True)
    db = stage / "data" / "lab.db"
    _db(db, rows)
    if manifest:
        payload = {
            "version": 1,
            "backup_at": backup_at,
            "database": {
                "integrity_check": "ok",
                "counts": counts or {table: len(rows.get(table, [])) for table in TABLES},
            },
        }
        (stage / "MANIFEST.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        if manifest:
            zf.write(stage / "MANIFEST.json", "MANIFEST.json")
        zf.write(db, "data/lab.db")
    return archive


def test_verify_backup_ok_y_tolera_filas_posteriores(tmp_path):
    backup_at = "2026-11-16T13:00:00+00:00"
    archive = _zip(
        tmp_path,
        {"fills": ["2026-11-16T12:00:00+00:00"]},
        backup_at,
    )
    live = tmp_path / "live.db"
    _db(
        live,
        {
            "fills": [
                "2026-11-16T12:00:00+00:00",
                "2026-11-16T14:00:00+00:00",
            ]
        },
    )
    report = verify_backup(archive, live)
    assert report["ok"] is True
    assert report["restored"]["fills"] == 1
    assert report["live_before"]["fills"] == 1


def test_verify_backup_falla_si_falta_una_fila_anterior(tmp_path):
    backup_at = "2026-11-16T13:00:00+00:00"
    archive = _zip(
        tmp_path,
        {"fills": ["2026-11-16T10:00:00+00:00"]},
        backup_at,
    )
    live = tmp_path / "live.db"
    _db(
        live,
        {
            "fills": [
                "2026-11-16T10:00:00+00:00",
                "2026-11-16T11:00:00+00:00",
            ]
        },
    )
    report = verify_backup(archive, live)
    assert report["ok"] is False
    assert any("fills" in problem for problem in report["problems"])


def test_verify_backup_falla_sin_manifiesto(tmp_path):
    archive = _zip(
        tmp_path,
        {"fills": ["2026-11-16T10:00:00+00:00"]},
        "2026-11-16T13:00:00+00:00",
        manifest=False,
    )
    live = tmp_path / "live.db"
    _db(live, {"fills": ["2026-11-16T10:00:00+00:00"]})
    report = verify_backup(archive, live)
    assert report["ok"] is False
    assert "MANIFEST.json" in report["detail"]


def test_verify_latest_backup_usa_el_mas_reciente(tmp_path, monkeypatch):
    backup_at = "2026-11-16T13:00:00+00:00"
    _zip(
        tmp_path,
        {"fills": ["2026-11-16T10:00:00+00:00"]},
        backup_at,
        name="trading-lab_20261116_100000.zip",
    )
    latest = _zip(
        tmp_path,
        {"fills": ["2026-11-16T12:00:00+00:00"]},
        backup_at,
        name="trading-lab_20261116_130000.zip",
    )
    live = tmp_path / "live.db"
    _db(live, {"fills": ["2026-11-16T12:00:00+00:00"]})
    monkeypatch.setenv("TRADINGLAB_BACKUP_DIR", str(tmp_path))
    report = verify_latest_backup(live)
    assert report["ok"] is True
    assert Path(report["backup"]).name == latest.name


def test_verify_latest_backup_desempata_por_nombre_con_mtime_igual(tmp_path, monkeypatch):
    backup_at = "2026-11-16T13:00:00+00:00"
    older = _zip(
        tmp_path,
        {"fills": ["2026-11-16T10:00:00+00:00"]},
        backup_at,
        name="trading-lab_20261116_100000.zip",
    )
    newer = _zip(
        tmp_path,
        {"fills": ["2026-11-16T12:00:00+00:00"]},
        backup_at,
        name="trading-lab_20261116_130000.zip",
    )
    stamp = older.stat().st_mtime
    os.utime(older, (stamp, stamp))
    os.utime(newer, (stamp, stamp))
    live = tmp_path / "live.db"
    _db(live, {"fills": ["2026-11-16T12:00:00+00:00"]})
    monkeypatch.setenv("TRADINGLAB_BACKUP_DIR", str(tmp_path))
    report = verify_latest_backup(live)
    assert report["ok"] is True
    assert Path(report["backup"]).name == newer.name
